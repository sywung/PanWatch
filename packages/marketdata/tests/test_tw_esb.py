"""兴柜(ESB)报价:mis 没有兴柜 → Fugle(需 key)→ 柜买兴柜盘后行情(免 key)。

兴柜没有昨收概念,涨跌以「前一日均价」为参考价(Fugle referencePrice / 柜买 PreviousAveragePrice)。
另外验证报价 Engine 的「缺的代码才问下一个来源并合并」。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import marketdata.vendors.fugle as fv
from marketdata.cache import TTLCache
from marketdata.defaults import InMemoryMetricsSink, StaticConfigProvider
from marketdata.engine import Engine
from marketdata.ports import SourceConfig
from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.symbol import Symbol
from marketdata.types import Quote, Request
from marketdata.vendors import tw_bulk
from marketdata.vendors.base import QuoteVendor

FX = Path(__file__).parent / "fixtures" / "tw"


def S(code):
    return Symbol.parse(code, "TW")


# ---------------------------------------------------------------- Fugle


@pytest.fixture
def fugle_http(monkeypatch):
    calls = []

    def fake_get(url, *, headers=None, **k):
        calls.append({"url": url, "headers": headers or {}})
        if url.endswith("/intraday/quote/1260"):
            return json.loads((FX / "fugle_quote_1260.json").read_text(encoding="utf-8"))
        return None  # 404 时 market_get 回 None

    monkeypatch.setattr(fv, "market_get", fake_get)
    return calls


def test_fugle_registered_for_tw():
    cls = VENDOR_CLASSES_BY_TYPE["quote"]["fugle"]
    assert cls.supports_markets == {"TW"}


def test_fugle_quote_uses_reference_price(fugle_http):
    out = fv.FugleQuoteVendor().fetch([S("1260")], {"api_key": "k-123"})
    assert len(out) == 1 and isinstance(out[0], Quote)
    q = out[0]
    assert q.symbol == "1260" and q.market == "TW" and q.name == "富味鄉"
    assert q.current_price == 31.95
    assert q.prev_close == 31.18                       # 兴柜参考价=前一日均价
    assert abs(q.change_amount - 0.77) < 1e-9
    assert abs(q.change_pct - 2.47) < 1e-9
    assert q.volume == 27892
    assert fugle_http[0]["url"] == "https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/1260"
    assert fugle_http[0]["headers"].get("X-API-KEY") == "k-123"


def test_fugle_without_key_makes_no_request(fugle_http):
    assert fv.FugleQuoteVendor().fetch([S("1260")], {}) == []
    assert fv.FugleQuoteVendor().fetch([S("1260")], {"api_key": "  "}) == []
    assert fugle_http == []


def test_fugle_not_found_is_skipped(fugle_http):
    out = fv.FugleQuoteVendor().fetch([S("1260"), S("9999")], {"api_key": "k"})
    assert [q.symbol for q in out] == ["1260"]


# ---------------------------------------------------------------- 柜买兴柜盘后


@pytest.fixture
def esb_bulk(monkeypatch):
    tw_bulk.reset_cache()
    monkeypatch.setattr(
        tw_bulk, "_download",
        lambda url, params=None: (FX / "tpex_esb_latest.json").read_text(encoding="utf-8")
        if "tpex_esb_latest_statistics" in url else (_ for _ in ()).throw(AssertionError(url)),
    )
    yield
    tw_bulk.reset_cache()


def test_tpex_esb_registered():
    assert VENDOR_CLASSES_BY_TYPE["quote"]["tpex_esb"].supports_markets == {"TW"}


def test_tpex_esb_quote_from_latest_statistics(esb_bulk):
    v = VENDOR_CLASSES_BY_TYPE["quote"]["tpex_esb"]()
    q = {x.symbol: x for x in v.fetch([S("1260"), S("2330")], {})}
    assert set(q) == {"1260"}  # 2330 不是兴柜
    r = q["1260"]
    assert r.name == "富味鄉" and r.current_price == 31.95
    assert r.prev_close == 30.77
    assert abs(r.change_pct - (31.95 - 30.77) / 30.77 * 100) < 1e-9
    assert r.high_price == 32.0 and r.low_price == 30.45 and r.volume == 51646


# ---------------------------------------------------------------- Engine 缺的才问下一家


class _V(QuoteVendor):
    supports_markets = {"TW"}

    def __init__(self, name, prices):
        self.name = name
        self.prices = prices
        self.asked: list[list[str]] = []

    def fetch(self, symbols, config):
        self.asked.append([s.code for s in symbols])
        return [Quote(symbol=s.code, market="TW", current_price=self.prices[s.code])
                for s in symbols if s.code in self.prices]


def _engine(vendors, *, fill_missing):
    cfg = StaticConfigProvider({"quote": [SourceConfig(vendor=v.name, config={}, enabled=True, priority=i)
                                          for i, v in enumerate(vendors)]})
    return Engine(datatype="quote", vendors={v.name: v for v in vendors}, config=cfg,
                  metrics=InMemoryMetricsSink(), cache=TTLCache(default_ttl_sec=5.0),
                  default_ttl=5.0, fill_missing=fill_missing)


def test_engine_fill_missing_merges_across_vendors():
    mis = _V("mis", {"2330": 1000.0, "6488": 1100.0})
    fugle = _V("fugle", {"1260": 31.95, "2330": 999.0})
    resp = _engine([mis, fugle], fill_missing=True).fetch(
        Request(symbols=("2330", "1260", "6488"), market="TW"))
    got = {q.symbol: q.current_price for q in resp.data}
    assert got == {"2330": 1000.0, "6488": 1100.0, "1260": 31.95}  # 先到者优先,不被后者覆盖
    assert fugle.asked == [["1260"]]                                # 只问缺的


def test_engine_fill_missing_stops_when_complete():
    mis = _V("mis", {"2330": 1000.0})
    fugle = _V("fugle", {"2330": 1.0})
    _engine([mis, fugle], fill_missing=True).fetch(Request(symbols=("2330",), market="TW"))
    assert fugle.asked == []


def test_engine_default_behavior_unchanged():
    mis = _V("mis", {"2330": 1000.0})
    fugle = _V("fugle", {"1260": 31.95})
    resp = _engine([mis, fugle], fill_missing=False).fetch(
        Request(symbols=("2330", "1260"), market="TW"))
    assert [q.symbol for q in resp.data] == ["2330"]
    assert fugle.asked == []


def test_market_data_quote_engine_fills_missing():
    from marketdata import MarketData

    md = MarketData(config=StaticConfigProvider({}))
    assert md._quote_engine.fill_missing is True
    assert md._kline_engine.fill_missing is False
