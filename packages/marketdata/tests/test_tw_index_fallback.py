"""台股指数报价:MIS 拿不到时依报价来源设定退到 yuantaData(2026-10-07,MIS 封锁本机 IP 期间首页加权/柜买指数无价格)。

yuantaData 指数代码实测:加权 IX0001(market=TSE)、柜买 IX0043(market=OTC)。
"""
import pytest

import marketdata.vendors.twse as tw
import marketdata.vendors.yuantadata as yd
from marketdata import MarketData, StaticConfigProvider
from marketdata.ports import SourceConfig

YD_CFG = {"base_url": "http://yd.test:8090", "token": "t"}


def _md(*sources: SourceConfig) -> MarketData:
    return MarketData(config=StaticConfigProvider({"quote": list(sources)}))


TWSE = SourceConfig(vendor="twse", priority=1)
YD = SourceConfig(vendor="yuantadata", priority=2, config=YD_CFG)


def _mis_row(code, z, y):
    return {"c": code, "z": z, "y": y, "v": "0", "t": "0"}


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload


def _yd_row(symbol, market, price, prev):
    return {"symbol": symbol, "market": market, "name": "x", "price": price, "prev_close": prev,
            "open": price, "high": price, "low": price, "volume_lots": 0}


@pytest.fixture
def yd_calls(monkeypatch):
    calls = []

    def fake_request(url, config, *, params, symbol=""):
        calls.append((url, dict(params), config.get("base_url")))
        rows = {("IX0001", "TSE"): _yd_row("IX0001", "TSE", 49741.57, 49822.55),
                ("IX0043", "OTC"): _yd_row("IX0043", "OTC", 431.17, 430.86)}
        data = [rows[(s, params.get("market"))] for s in params["symbols"].split(",")
                if (s, params.get("market")) in rows]
        return _Resp({"data": data, "no_quote": []})

    monkeypatch.setattr(yd, "_request", fake_request)
    return calls


def _mis(monkeypatch, rows):
    monkeypatch.setattr(tw, "market_get", lambda *a, **k: None if rows is None else {"msgArray": rows})


def _by_symbol(out):
    return {row["symbol"]: row for row in out}


def test_yuantadata_index_quotes_maps_codes_and_markets(yd_calls):
    out = _by_symbol(yd.fetch_tw_index_quotes(YD_CFG, {"TWII", "TPEX"}))
    assert set(out) == {"TWII", "TPEX"}
    assert out["TWII"]["current_price"] == 49741.57
    assert out["TWII"]["change_amount"] == pytest.approx(49741.57 - 49822.55)
    assert out["TWII"]["change_pct"] == pytest.approx((49741.57 - 49822.55) / 49822.55 * 100)
    assert out["TWII"]["prev_close"] == 49822.55
    assert out["TPEX"]["current_price"] == 431.17
    sent = {(p["symbols"], p["market"]) for _, p, _ in yd_calls}
    assert sent == {("IX0001", "TSE"), ("IX0043", "OTC")}
    assert all(url == "http://yd.test:8090/api/v1/market/quotes" for url, _, _ in yd_calls)


def test_yuantadata_index_quotes_only_requests_wanted(yd_calls):
    out = yd.fetch_tw_index_quotes(YD_CFG, {"TPEX"})
    assert [r["symbol"] for r in out] == ["TPEX"]
    assert [p["symbols"] for _, p, _ in yd_calls] == ["IX0043"]


def test_falls_back_to_yuantadata_when_mis_blocked(monkeypatch, yd_calls):
    _mis(monkeypatch, None)  # MIS 断线/熔断
    out = _by_symbol(_md(TWSE, YD).tw_index_quotes())
    assert set(out) == {"TWII", "TPEX"}
    assert out["TWII"]["current_price"] == 49741.57


def test_mis_result_kept_and_only_missing_index_fetched(monkeypatch, yd_calls):
    _mis(monkeypatch, [_mis_row("t00", "50000.0", "49900.0")])  # 只有加权
    out = _by_symbol(_md(TWSE, YD).tw_index_quotes())
    assert out["TWII"]["current_price"] == 50000.0  # MIS 优先
    assert out["TPEX"]["current_price"] == 431.17
    assert [p["symbols"] for _, p, _ in yd_calls] == ["IX0043"]


def test_no_yuantadata_call_when_mis_has_both(monkeypatch, yd_calls):
    _mis(monkeypatch, [_mis_row("t00", "50000.0", "49900.0"), _mis_row("o00", "430.0", "429.0")])
    out = _md(TWSE, YD).tw_index_quotes()
    assert {r["symbol"] for r in out} == {"TWII", "TPEX"}
    assert yd_calls == []


def test_yuantadata_not_used_when_source_disabled(monkeypatch, yd_calls):
    _mis(monkeypatch, None)
    disabled = SourceConfig(vendor="yuantadata", priority=2, enabled=False, config=YD_CFG)
    assert _md(TWSE, disabled).tw_index_quotes() == []
    assert yd_calls == []


def test_respects_source_priority(monkeypatch, yd_calls):
    _mis(monkeypatch, [_mis_row("t00", "50000.0", "49900.0"), _mis_row("o00", "430.0", "429.0")])
    first = SourceConfig(vendor="yuantadata", priority=0, config=YD_CFG)
    out = _by_symbol(_md(TWSE, first).tw_index_quotes())
    assert out["TWII"]["current_price"] == 49741.57  # yuantaData 排在前面就先用它


def test_mis_still_used_when_no_quote_sources_configured(monkeypatch, yd_calls):
    _mis(monkeypatch, [_mis_row("t00", "50000.0", "49900.0")])
    out = _md().tw_index_quotes()  # 旧行为:没有任何报价来源设定时照样打 MIS
    assert [r["symbol"] for r in out] == ["TWII"]


def test_yuantadata_failure_is_swallowed(monkeypatch):
    _mis(monkeypatch, [_mis_row("t00", "50000.0", "49900.0")])

    def boom(*a, **k):
        raise RuntimeError("yuantaData down")

    monkeypatch.setattr(yd, "_request", boom)
    out = _md(TWSE, YD).tw_index_quotes()
    assert [r["symbol"] for r in out] == ["TWII"]
