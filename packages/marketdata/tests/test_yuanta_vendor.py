"""元大 SparkAPI(透過本機轉接服務 services/yuanta_gateway)作為台股報價與 K 線來源。

轉接服務 API(實測 2026-10-02,見 vault reference_yuanta_sparkapi_gotchas):
- POST {base}/quotes  body {"items":[{"market":"TSE|OTC|ESB","code":"2330"}]} → {"data":[row...]}
  市場別填錯的代碼會被略過(不報錯、不回傳)→ vendor 依序以 TSE、OTC、ESB 查,只把沒查到的帶到下一輪。
  row:market code name price prev_close open high low volume(張) limit_up limit_down bid ask time
- GET {base}/kline?market&code&period&start&end → {"data":[{time,open,high,low,close,volume(張)}]}
  分 K 的 time 是 K 棒「結束」時間;PanWatch 分 K(Yahoo)用「開始」時間 → 減一個週期。
- 轉接服務不在、未登入 → vendor 抛例外,讓 Engine 改用下一個來源。
"""

from __future__ import annotations

from datetime import date

import pytest

import marketdata.vendors.yuanta as yv
from marketdata.client import MarketData
from marketdata.defaults import StaticConfigProvider
from marketdata.ports import SourceConfig
from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.symbol import Symbol

BASE = "http://gw:2885"
CFG = {"base_url": BASE, "token": "tk", "days": 3}


def _row(code, market, price, prev, name="X"):
    return {"market": market, "code": code, "name": name, "price": price, "prev_close": prev,
            "open": prev, "high": price, "low": prev, "volume": 1234, "limit_up": 0, "limit_down": 0,
            "bid": price, "ask": price, "time": "13:30:00.000"}


@pytest.fixture
def gw(monkeypatch):
    """假轉接服務:記錄請求;依 (market, code) 回應。"""
    state = {"posts": [], "gets": [], "board": {"2330": "TSE", "6488": "OTC", "7795": "ESB"},
             "klines": {}, "down": False}

    def fake_post(url, *, host_key, json_body, headers=None, **kw):
        state["posts"].append((url, json_body, headers, kw))
        if state["down"]:
            return None
        rows = []
        for it in json_body["items"]:
            if state["board"].get(it["code"]) == it["market"]:
                rows.append(_row(it["code"], it["market"], 100.0, 98.0, name=f"N{it['code']}"))
        return {"data": rows}

    def fake_get(url, *, host_key, params=None, headers=None, **kw):
        state["gets"].append((url, dict(params or {}), headers, kw))
        if state["down"]:
            return None
        key = (params["market"], params["code"], params["period"])
        return {"data": state["klines"].get(key, [])}

    monkeypatch.setattr(yv, "market_post", fake_post)
    monkeypatch.setattr(yv, "market_get", fake_get)
    monkeypatch.setattr(yv, "_today", lambda: date(2026, 10, 2))
    return state


def test_registered_for_quote_and_kline_tw_only():
    assert VENDOR_CLASSES_BY_TYPE["quote"]["yuanta"].supports_markets == {"TW"}
    assert VENDOR_CLASSES_BY_TYPE["kline"]["yuanta"].supports_markets == {"TW"}


# ---------- 報價 ----------

def test_quotes_resolve_board_in_three_passes(gw):
    out = yv.YuantaQuoteVendor().fetch([Symbol.parse(c, "TW") for c in ("2330", "6488", "7795", "9999")], CFG)
    markets = [[it["market"] for it in body["items"]] for _, body, _, _ in gw["posts"]]
    assert markets == [["TSE"] * 4, ["OTC"] * 3, ["ESB"] * 2]   # 只把沒查到的帶到下一輪
    assert sorted(q.symbol for q in out) == ["2330", "6488", "7795"]
    q = next(q for q in out if q.symbol == "2330")
    assert q.market == "TW" and q.name == "N2330"
    assert q.current_price == 100.0 and q.prev_close == 98.0
    assert q.change_amount == pytest.approx(2.0) and q.change_pct == pytest.approx(2.0 / 98 * 100)
    assert q.volume == 1234                       # 張,與 TWSE mis 一致


def test_quotes_stop_early_when_all_found(gw):
    yv.YuantaQuoteVendor().fetch([Symbol.parse("2330", "TW")], CFG)
    assert len(gw["posts"]) == 1


def test_quotes_send_token_and_disable_proxy(gw):
    yv.YuantaQuoteVendor().fetch([Symbol.parse("2330", "TW")], CFG)
    url, _, headers, kw = gw["posts"][0]
    assert url == f"{BASE}/quotes"
    assert headers["Authorization"] == "Bearer tk"
    assert kw.get("trust_env") is False          # 本機服務不走系統代理


def test_quotes_without_token_has_no_auth_header(gw):
    yv.YuantaQuoteVendor().fetch([Symbol.parse("2330", "TW")], {"base_url": BASE})
    assert "Authorization" not in (gw["posts"][0][2] or {})


def test_default_base_url(gw):
    yv.YuantaQuoteVendor().fetch([Symbol.parse("2330", "TW")], {})
    assert gw["posts"][0][0] == "http://host.containers.internal:2885/quotes"


def test_quotes_skip_zero_price_rows(gw, monkeypatch):
    """尚未成交(價格 0)不算有效報價,讓下一個來源接手。"""
    def zero_post(url, *, host_key, json_body, headers=None, **kw):
        return {"data": [_row("2330", "TSE", 0.0, 98.0)]}

    monkeypatch.setattr(yv, "market_post", zero_post)
    assert yv.YuantaQuoteVendor().fetch([Symbol.parse("2330", "TW")], CFG) == []


def test_quotes_gateway_down_raises(gw):
    gw["down"] = True
    with pytest.raises(RuntimeError):
        yv.YuantaQuoteVendor().fetch([Symbol.parse("2330", "TW")], CFG)


# ---------- 日 K ----------

def _k(t, c, v=10):
    return {"time": t, "open": c, "high": c, "low": c, "close": c, "volume": v}


def test_daily_kline_volume_in_shares_and_trimmed(gw):
    gw["klines"][("TSE", "2330", "1d")] = [
        _k("2026-09-29 00:00:00", 1), _k("2026-09-30 00:00:00", 2),
        _k("2026-10-01 00:00:00", 3), _k("2026-10-02 00:00:00", 4, v=13869),
    ]
    bars = yv.YuantaKlineVendor().fetch([Symbol.parse("2330", "TW")], CFG)   # days=3
    assert [b.date for b in bars] == ["2026-09-30", "2026-10-01", "2026-10-02"]
    assert bars[-1].volume == 13_869_000         # 張 → 股(與 Yahoo/FinMind 一致)
    url, params, headers, kw = gw["gets"][0]
    assert url == f"{BASE}/kline" and params["period"] == "1d"
    assert params["end"] == "2026-10-02" and params["start"] <= "2026-09-25"


def test_daily_kline_tries_otc_then_esb(gw):
    gw["klines"][("ESB", "7795", "1d")] = [_k("2026-10-02 00:00:00", 9)]
    bars = yv.YuantaKlineVendor().fetch([Symbol.parse("7795", "TW")], CFG)
    assert [p["market"] for _, p, _, _ in gw["gets"]] == ["TSE", "OTC", "ESB"]
    assert bars and bars[0].close == 9


def test_daily_kline_gateway_down_raises(gw):
    gw["down"] = True
    with pytest.raises(RuntimeError):
        yv.YuantaKlineVendor().fetch([Symbol.parse("2330", "TW")], CFG)


# ---------- 分 K ----------

def test_intraday_uses_bar_start_time(gw):
    """元大 30 分 K 的 09:30 是 09:00–09:30 那根 → PanWatch 記為 09:00。"""
    gw["klines"][("TSE", "2330", "30m")] = [
        _k("2026-10-02 09:30:00", 1, v=5), _k("2026-10-02 10:00:00", 2, v=6),
    ]
    bars = yv.YuantaKlineVendor().fetch_intraday("2330", "30m", CFG)
    assert [b.date for b in bars] == ["2026-10-02 09:00", "2026-10-02 09:30"]
    assert bars[0].volume == 5000
    _, params, _, _ = gw["gets"][0]
    assert params["period"] == "30m" and params["start"] <= "2026-08-04"   # 約 60 天,對齊 Yahoo range


def test_intraday_unsupported_interval_returns_empty(gw):
    assert yv.YuantaKlineVendor().fetch_intraday("2330", "2h", CFG) == []
    assert gw["gets"] == []


# ---------- MarketData.intraday_klines 走元大(啟用時) ----------

def _md(enabled=True):
    return MarketData(config=StaticConfigProvider({
        "kline": [SourceConfig(vendor="yuanta", priority=18, enabled=enabled, config={"base_url": BASE})],
    }))


def test_intraday_klines_prefers_yuanta_when_enabled(gw, monkeypatch):
    gw["klines"][("TSE", "2330", "30m")] = [_k("2026-10-02 09:30:00", 1)]
    import marketdata.vendors.kline as kv

    def no_yahoo(*a, **k):
        raise AssertionError("元大有資料時不應再打 Yahoo")

    monkeypatch.setattr(kv, "market_get", no_yahoo)
    bars = _md().intraday_klines("2330", market="TW", interval="30m")
    assert [b.date for b in bars] == ["2026-10-02 09:00"]


def test_intraday_klines_falls_back_to_yahoo_when_yuanta_fails(gw, monkeypatch):
    gw["down"] = True
    import marketdata.vendors.kline as kv

    yahoo_calls = []

    def fake_yahoo(url, **kw):
        yahoo_calls.append(url)
        return {"chart": {"result": [{"timestamp": [1790902800], "indicators": {"quote": [
            {"open": [1.0], "close": [1.0], "high": [1.0], "low": [1.0], "volume": [100]}]}}]}}

    monkeypatch.setattr(kv, "market_get", fake_yahoo)
    bars = _md().intraday_klines("2330", market="TW", interval="30m")
    assert yahoo_calls and bars


def test_intraday_klines_ignores_disabled_yuanta(gw, monkeypatch):
    import marketdata.vendors.kline as kv

    monkeypatch.setattr(kv, "market_get", lambda *a, **k: None)
    _md(enabled=False).intraday_klines("2330", market="TW", interval="30m")
    assert gw["gets"] == []
