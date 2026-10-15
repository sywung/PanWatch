"""yuantaData 集保股權分散 vendor：PanWatch 改從自架 yuantaData 服務讀（資料由它統一收集保存）。

網路只經 `marketdata.vendors.yuantadata.market_get`（測試替換，簽章 `fake(url, **kwargs)`，
回傳有 status_code／json() 的物件）。fallback 靠既有 Engine 優先序；歷史走新的
`MarketData.shareholders_history(symbol, skip_dates=...)`：依來源優先序逐一嘗試，第一個非空者勝。
"""

from __future__ import annotations

import pytest

import marketdata.vendors.yuantadata as yd
from marketdata.client import MarketData
from marketdata.defaults import StaticConfigProvider
from marketdata.ports import SourceConfig
from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.symbol import Symbol
from marketdata.types import ShareholderItem
from marketdata.vendors import tdcc_web

BASE = "http://yuantadata:8090"
CFG = {"base_url": BASE, "token": "secret"}


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _levels(thousand=84.77, holders=3_020_649):
    rows = [{"level": n, "holders": n, "shares": n * 100, "pct": 1.0} for n in range(1, 15)]
    rows.append({"level": 15, "holders": 1487, "shares": 1, "pct": thousand})
    rows.append({"level": 16, "holders": 0, "shares": 0, "pct": 0.0})
    rows.append({"level": 17, "holders": holders, "shares": 25_932_370_067, "pct": 100.0})
    return rows


def _item(date, thousand=84.77, holders=3_020_649, levels=True):
    row = {"data_date": date, "holder_num": holders, "avg_shares": 8584.1, "big_holder_ratio": 87.54,
           "thousand_lot_ratio": thousand, "source": "web"}
    if levels:
        row["levels"] = _levels(thousand, holders)
    return row


def install_http(monkeypatch, responder):
    calls = []

    def fake(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return responder(url, kwargs)

    monkeypatch.setattr(yd, "market_get", fake)
    return calls


def _vendor():
    cls = VENDOR_CLASSES_BY_TYPE["shareholders"]["yuantadata"]
    assert cls.supports_markets == {"TW"}
    return cls()


def S(code):
    return Symbol.parse(code, "TW")


# ---------------------------------------------------------------- fetch（每檔最新一週）


def test_fetch_batches_symbols_and_maps_to_shareholder_items(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: Response(200, {
        "items": {"2330": _item("2026-10-08"), "6488": _item("2026-10-08", 40.0, 90_000)}, "missing": []}))
    out = {x.symbol: x for x in _vendor().fetch([S("2330"), S("6488")], CFG)}
    assert len(calls) == 1 and calls[0]["url"] == f"{BASE}/api/v1/market/dispersion"
    assert calls[0]["params"]["symbols"] == "2330,6488" and calls[0]["params"]["levels"] == "latest"
    assert calls[0]["headers"] == {"Authorization": "Bearer secret"}
    item = out["2330"]
    assert isinstance(item, ShareholderItem)
    assert item.report_date == "2026-10-08" and item.holder_num == 3_020_649
    assert item.thousand_lot_ratio == 84.77 and item.big_holder_ratio == 87.54
    assert item.avg_shares == pytest.approx(8584.1)
    assert [r["level"] for r in item.levels] == list(range(1, 18))
    assert out["6488"].holder_num == 90_000


def test_fetch_omits_missing_symbols_and_chunks_at_50(monkeypatch):
    def responder(url, kw):
        wanted = kw["params"]["symbols"].split(",")
        return Response(200, {"items": {c: _item("2026-10-08") for c in wanted if c != "1102"}, "missing": []})

    calls = install_http(monkeypatch, responder)
    codes = [f"{1100 + i}" for i in range(60)]
    out = _vendor().fetch([S(c) for c in codes], CFG)
    assert len(calls) == 2 and len(calls[0]["params"]["symbols"].split(",")) == 50
    assert "1102" not in {x.symbol for x in out} and len(out) == 59


def test_fetch_requires_base_url_and_raises_on_http_errors_so_engine_can_fall_back(monkeypatch):
    install_http(monkeypatch, lambda url, kw: Response(502, {}))
    with pytest.raises(RuntimeError):
        _vendor().fetch([S("2330")], {"base_url": "", "token": ""})
    with pytest.raises(Exception):
        _vendor().fetch([S("2330")], CFG)
    install_http(monkeypatch, lambda url, kw: None)          # market_get 失敗回 None
    with pytest.raises(Exception):
        _vendor().fetch([S("2330")], CFG)


def test_fetch_returns_empty_list_when_service_has_nothing(monkeypatch):
    install_http(monkeypatch, lambda url, kw: Response(200, {"items": {}, "missing": ["2330"]}))
    assert _vendor().fetch([S("2330")], CFG) == []


def test_fetch_without_token_sends_no_authorization_header(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: Response(200, {"items": {}, "missing": []}))
    _vendor().fetch([S("2330")], {"base_url": BASE, "token": ""})
    assert not calls[0]["headers"]


# ---------------------------------------------------------------- history（單檔歷史）


def _history_payload(status="done", *dates):
    return {"symbol": "2330", "backfill_status": status, "count": len(dates),
            "items": [_item(d, 84.0 + i * 0.01) for i, d in enumerate(dates)]}


def test_history_requests_all_levels_and_returns_date_levels_pairs(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: Response(200, _history_payload("done", "2026-10-02", "2026-10-08")))
    out = _vendor().history("2330", CFG, skip_dates=())
    assert calls[0]["url"] == f"{BASE}/api/v1/market/dispersion/2330"
    assert calls[0]["params"] == {"weeks": 52, "levels": "all"}
    assert [d for d, _ in out] == ["2026-10-02", "2026-10-08"]
    assert all(len(levels) == 17 for _, levels in out)


def test_history_drops_skip_dates(monkeypatch):
    install_http(monkeypatch, lambda url, kw: Response(200, _history_payload("done", "2026-10-02", "2026-10-08")))
    out = _vendor().history("2330", CFG, skip_dates={"2026-10-02"})
    assert [d for d, _ in out] == ["2026-10-08"]


def test_history_returns_empty_while_service_backfill_is_unfinished_so_next_source_can_try(monkeypatch):
    install_http(monkeypatch, lambda url, kw: Response(200, _history_payload("pending", "2026-10-08")))
    assert _vendor().history("2330", CFG, skip_dates=()) == []
    install_http(monkeypatch, lambda url, kw: Response(200, _history_payload("error", "2026-10-08")))
    assert _vendor().history("2330", CFG, skip_dates=()) == []
    install_http(monkeypatch, lambda url, kw: Response(200, _history_payload("pending", "2026-10-02", "2026-10-08")))
    assert len(_vendor().history("2330", CFG, skip_dates=())) == 2            # 已經有 ≥2 週就先用


def test_history_unknown_or_unavailable_is_empty_and_http_error_raises(monkeypatch):
    install_http(monkeypatch, lambda url, kw: Response(200, {"symbol": "9999", "backfill_status": "unknown",
                                                              "count": 0, "items": []}))
    assert _vendor().history("9999", CFG, skip_dates=()) == []
    install_http(monkeypatch, lambda url, kw: Response(500, {}))
    with pytest.raises(Exception):
        _vendor().history("2330", CFG, skip_dates=())


def test_history_rejects_malformed_symbol_without_request(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: Response(200, {}))
    assert _vendor().history("23 30;x", CFG, skip_dates=()) == []
    assert calls == []


# ---------------------------------------------------------------- TDCC 直連來源也要有 history（fallback）


def test_tdcc_vendor_history_delegates_to_web_fetch_via_module_attribute(monkeypatch):
    seen = []
    monkeypatch.setattr(tdcc_web, "fetch_history",
                        lambda code, weeks=52, skip_dates=(), **kw: seen.append((code, set(skip_dates))) or [("2026-10-08", _levels())])
    out = VENDOR_CLASSES_BY_TYPE["shareholders"]["tdcc"]().history("2330", {}, skip_dates={"2026-10-02"})
    assert seen == [("2330", {"2026-10-02"})] and [d for d, _ in out] == ["2026-10-08"]


# ---------------------------------------------------------------- MarketData.shareholders_history 路由


def _md(*sources):
    return MarketData(config=StaticConfigProvider({"shareholders": list(sources)}))


YD = SourceConfig(vendor="yuantadata", config=CFG, enabled=True, priority=0)
TD = SourceConfig(vendor="tdcc", config={}, enabled=True, priority=1)


def _tdcc_web(monkeypatch, weeks=("2026-10-08",)):
    calls = []
    monkeypatch.setattr(tdcc_web, "fetch_history",
                        lambda code, weeks_=52, skip_dates=(), **kw: calls.append(code) or [(d, _levels()) for d in weeks])
    return calls


def test_history_prefers_yuantadata_and_does_not_hit_tdcc(monkeypatch):
    install_http(monkeypatch, lambda url, kw: Response(200, _history_payload("done", "2026-10-02", "2026-10-08")))
    direct = _tdcc_web(monkeypatch)
    out = _md(YD, TD).shareholders_history("2330", skip_dates=())
    assert [d for d, _ in out] == ["2026-10-02", "2026-10-08"] and direct == []


def test_history_falls_back_to_tdcc_when_yuantadata_unfinished_or_down(monkeypatch):
    direct = _tdcc_web(monkeypatch, weeks=("2026-10-08", "2026-10-02"))
    install_http(monkeypatch, lambda url, kw: Response(200, _history_payload("pending", "2026-10-08")))
    assert len(_md(YD, TD).shareholders_history("2330", skip_dates=())) == 2
    install_http(monkeypatch, lambda url, kw: Response(503, {}))
    assert len(_md(YD, TD).shareholders_history("2330", skip_dates=())) == 2
    assert direct == ["2330", "2330"]


def test_history_skips_disabled_sources_and_respects_priority(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: Response(200, _history_payload("done", "2026-10-08")))
    direct = _tdcc_web(monkeypatch)
    disabled_yd = SourceConfig(vendor="yuantadata", config=CFG, enabled=False, priority=0)
    _md(disabled_yd, TD).shareholders_history("2330", skip_dates=())
    assert calls == [] and direct == ["2330"]
    swapped = [SourceConfig(vendor="tdcc", config={}, enabled=True, priority=0),
               SourceConfig(vendor="yuantadata", config=CFG, enabled=True, priority=1)]
    _md(*swapped).shareholders_history("2330", skip_dates=())
    assert direct == ["2330", "2330"] and calls == []                           # tdcc 在前且有資料 → 不用呼叫 yuantaData


def test_history_all_sources_empty_or_failing_returns_empty_and_never_raises(monkeypatch):
    install_http(monkeypatch, lambda url, kw: Response(500, {}))
    monkeypatch.setattr(tdcc_web, "fetch_history", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("blocked")))
    assert _md(YD, TD).shareholders_history("2330", skip_dates=()) == []
    assert _md().shareholders_history("2330", skip_dates=()) == []


def test_history_only_for_tw_symbols(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: Response(200, {}))
    direct = _tdcc_web(monkeypatch)
    assert _md(YD, TD).shareholders_history("AAPL", skip_dates=(), market="US") == []
    assert calls == [] and direct == []
