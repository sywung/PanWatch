"""Yahoo 日K 支持台股:先试上市 .TW,无数据再试上柜 .TWO。"""

import marketdata.vendors.kline as kv
from marketdata.symbol import Symbol

_TS1 = 1782864000  # 2026-07-01 UTC
_TS2 = 1782950400


def _payload():
    q = {"open": [100.0, 101.0], "high": [102.0, 103.0], "low": [99.0, 100.0],
         "close": [101.0, 102.0], "volume": [1000, 2000]}
    return {"chart": {"result": [{"timestamp": [_TS1, _TS2], "indicators": {"quote": [q]}}], "error": None}}


def _install(monkeypatch, responder):
    urls = []

    def fake_market_get(url, **k):
        urls.append(url)
        return responder(url)

    monkeypatch.setattr(kv, "market_get", fake_market_get)
    return urls


def test_yahoo_kline_supports_tw():
    assert "TW" in kv.YahooKlineVendor.supports_markets


def test_listed_stock_uses_tw_suffix_only(monkeypatch):
    urls = _install(monkeypatch, lambda u: _payload() if u.endswith("/2330.TW") else None)
    out = kv.YahooKlineVendor().fetch([Symbol.parse("2330", "TW")], {"days": 60})
    assert len(out) == 2 and out[0].date == "2026-07-01" and out[1].close == 102.0
    assert len(urls) == 1 and urls[0].endswith("/2330.TW")


def test_otc_stock_falls_back_to_two_suffix(monkeypatch):
    # .TW 对上柜股回 404(market_get → None)
    urls = _install(monkeypatch, lambda u: _payload() if u.endswith("/6488.TWO") else None)
    out = kv.YahooKlineVendor().fetch([Symbol.parse("6488", "TW")], {"days": 60})
    assert len(out) == 2
    assert [u.rsplit("/", 1)[1] for u in urls] == ["6488.TW", "6488.TWO"]


def test_empty_result_also_triggers_two_fallback(monkeypatch):
    empty = {"chart": {"result": [], "error": None}}
    urls = _install(monkeypatch, lambda u: _payload() if u.endswith("/6488.TWO") else empty)
    out = kv.YahooKlineVendor().fetch([Symbol.parse("6488", "TW")], {"days": 60})
    assert len(out) == 2 and len(urls) == 2


def test_neither_suffix_returns_empty(monkeypatch):
    urls = _install(monkeypatch, lambda u: None)
    assert kv.YahooKlineVendor().fetch([Symbol.parse("9999", "TW")], {"days": 60}) == []
    assert len(urls) == 2
