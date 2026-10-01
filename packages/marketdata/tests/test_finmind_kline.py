"""FinMind TaiwanStockPrice 日K:台股 Yahoo 备援。"""

import inspect

import pytest

import marketdata.vendors.finmind as fm
from marketdata.http import market_get as real_market_get
from marketdata.symbol import Symbol


def _row(date, o, c, hi, lo, vol=1000):
    return {"date": date, "stock_id": "2330", "Trading_Volume": vol,
            "open": o, "close": c, "max": hi, "min": lo, "spread": 0}


def _install(monkeypatch, payload):
    calls = []

    def fake_market_get(url, **kwargs):
        # 绑定真实签名:传错/漏传参数在这里就会炸,而不是到线上才炸
        inspect.signature(real_market_get).bind(url, **kwargs)
        calls.append((url, kwargs))
        return payload

    monkeypatch.setattr(fm, "market_get", fake_market_get)
    return calls


def test_finmind_supports_tw_and_futures():
    # F4 起同一个 vendor 也提供期货(TWF)日 K,见 test_finmind_futures_kline.py
    assert fm.FinMindKlineVendor.supports_markets == {"TW", "TWF"}


def test_parses_rows_into_sorted_bars(monkeypatch):
    payload = {"status": 200, "msg": "success", "data": [
        _row("2026-09-30", 2470.0, 2480.0, 2490.0, 2460.0, 30000),
        _row("2026-09-29", 2450.0, 2465.0, 2470.0, 2440.0, 20000),
    ]}
    calls = _install(monkeypatch, payload)

    out = fm.FinMindKlineVendor().fetch([Symbol.parse("2330", "TW")], {"days": 60})

    assert [b.date for b in out] == ["2026-09-29", "2026-09-30"]
    b = out[1]
    # FinMind 栏位名是 max/min,不是 high/low
    assert (b.open, b.close, b.high, b.low, b.volume) == (2470.0, 2480.0, 2490.0, 2460.0, 30000.0)
    params = calls[0][1]["params"]
    assert params["dataset"] == "TaiwanStockPrice" and params["data_id"] == "2330"
    assert "Authorization" not in (calls[0][1].get("headers") or {})


def test_token_sent_as_bearer(monkeypatch):
    calls = _install(monkeypatch, {"status": 200, "data": []})
    fm.FinMindKlineVendor().fetch([Symbol.parse("2330", "TW")], {"token": " abc "})
    assert calls[0][1]["headers"]["Authorization"] == "Bearer abc"


def test_trims_to_requested_days(monkeypatch):
    rows = [_row(f"2026-09-{d:02d}", 1, 1, 1, 1) for d in range(1, 21)]
    _install(monkeypatch, {"status": 200, "data": rows})
    out = fm.FinMindKlineVendor().fetch([Symbol.parse("2330", "TW")], {"days": 5})
    assert [b.date for b in out] == [f"2026-09-{d}" for d in range(16, 21)]


def test_skips_malformed_and_non_positive_rows(monkeypatch):
    payload = {"status": 200, "data": [
        _row("2026-09-29", 10.0, 11.0, 12.0, 9.0),
        {"date": "2026-09-30", "open": "x", "close": 1, "max": 1, "min": 1},
        {"date": "2026-10-01"},  # 缺价格
        _row("2026-10-02", 0, 0, 0, 0),  # 无成交日不能当成价格 0
        "garbage",
    ]}
    _install(monkeypatch, payload)
    out = fm.FinMindKlineVendor().fetch([Symbol.parse("2330", "TW")], {})
    assert [b.date for b in out] == ["2026-09-29"]


def test_api_error_status_raises(monkeypatch):
    _install(monkeypatch, {"status": 402, "msg": "Requests reach the upper limit."})
    with pytest.raises(RuntimeError, match="upper limit"):
        fm.FinMindKlineVendor().fetch([Symbol.parse("2330", "TW")], {})


def test_network_failure_returns_empty(monkeypatch):
    _install(monkeypatch, None)
    assert fm.FinMindKlineVendor().fetch([Symbol.parse("2330", "TW")], {}) == []


def test_non_tw_symbol_makes_no_request(monkeypatch):
    calls = _install(monkeypatch, {"status": 200, "data": []})
    assert fm.FinMindKlineVendor().fetch([Symbol.parse("AAPL", "US")], {}) == []
    assert calls == []
