"""新闻按市场路由:台股代码必须走台股新闻源(yahoo_tw),不能被当成 A 股送去东财/雪球。

浏览器验收(2026-10-01)发现:台股 2330 与个股期货详情页的新闻全是东财的大陆车市新闻。
根因:md_news 调 MarketData.news() 时没传 market,一律按 "CN" 查——
yahoo_tw(supports_markets={"TW"})被跳过,东财个股新闻用「台積電」搜出含「台」字的无关新闻。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from marketdata.types import NewsArticle

from src.modules.market.api import news as news_api
from src.platform.marketdata import marketdata_client
from src.platform.marketdata.collectors import news_collector
from src.platform.marketdata.collectors.news_collector import NewsCollector, NewsItem

NOW = datetime.now(timezone.utc)


def _article(source, ext_id, symbols, minutes_ago=0):
    return NewsArticle(
        source=source, external_id=ext_id, title=f"title-{ext_id}", content="",
        publish_time=NOW - timedelta(minutes=minutes_ago), symbols=list(symbols),
    )


class FakeMarketData:
    """记录每次 news() 调用的 market 与代码;按 market 回不同来源的文章。"""

    def __init__(self):
        self.calls: list[tuple[str, list[str]]] = []

    def news(self, symbols, *, market="CN", since_hours=2, names=None, now=None):
        self.calls.append((market, list(symbols)))
        if market == "TW":
            return [_article("yahoo_tw", f"tw-{s}", [s], minutes_ago=5) for s in symbols]
        return [_article("eastmoney_news", f"cn-{s}", [s], minutes_ago=1) for s in symbols]


def _install_fake_md(monkeypatch) -> FakeMarketData:
    fake = FakeMarketData()
    monkeypatch.setattr(marketdata_client, "get_market_data", lambda: fake)
    return fake


# ---------- md_news:按市场分组 ----------

def test_md_news_routes_tw_symbols_to_tw_market(monkeypatch):
    """md_news 带 markets 时,台股代码以 market="TW" 查询。"""
    fake = _install_fake_md(monkeypatch)

    items = marketdata_client.md_news(
        ["2330"], 24, {"2330": "台積電"}, markets={"2330": "TW"},
    )

    assert fake.calls == [("TW", ["2330"])]
    assert [it.source for it in items] == ["yahoo_tw"]


def test_md_news_splits_mixed_watchlist_by_market(monkeypatch):
    """自选混合台股与 A 股:各市场分别查询,结果合并且按发布时间倒序。"""
    fake = _install_fake_md(monkeypatch)

    items = marketdata_client.md_news(
        ["2330", "600519", "2317"], 24, None,
        markets={"2330": "TW", "600519": "CN", "2317": "TW"},
    )

    by_market = {m: sorted(syms) for m, syms in fake.calls}
    assert by_market == {"TW": ["2317", "2330"], "CN": ["600519"]}
    assert len(fake.calls) == 2  # 每个市场只查一次,不是每个代码一次
    assert {it.external_id for it in items} == {"tw-2330", "tw-2317", "cn-600519"}
    times = [it.publish_time for it in items]
    assert times == sorted(times, reverse=True)


def test_md_news_dedupes_across_markets(monkeypatch):
    """不同市场查询回同一 external_id 时只保留一条。"""
    class DupMD(FakeMarketData):
        def news(self, symbols, *, market="CN", since_hours=2, names=None, now=None):
            self.calls.append((market, list(symbols)))
            return [_article("x", "same-id", symbols)]

    fake = DupMD()
    monkeypatch.setattr(marketdata_client, "get_market_data", lambda: fake)

    items = marketdata_client.md_news(["2330", "600519"], 24, None,
                                      markets={"2330": "TW", "600519": "CN"})

    assert [it.external_id for it in items] == ["same-id"]


def test_md_news_without_markets_keeps_legacy_single_call(monkeypatch):
    """不传 markets(旧调用方)行为不变:一次查询、不指定 market。"""
    fake = _install_fake_md(monkeypatch)

    marketdata_client.md_news(["600519"], 24, None)

    assert fake.calls == [("CN", ["600519"])]


def test_md_news_unknown_symbol_falls_back_to_cn(monkeypatch):
    """markets 里查不到的代码按 CN 查(与旧行为一致),已知的仍走各自市场。"""
    fake = _install_fake_md(monkeypatch)

    marketdata_client.md_news(["2330", "600519"], 24, None, markets={"2330": "TW"})

    assert sorted(fake.calls) == [("CN", ["600519"]), ("TW", ["2330"])]


# ---------- NewsCollector:未给 markets 时从自选股表查 ----------

def test_collector_passes_explicit_markets(monkeypatch):
    """fetch_all(markets=...) 原样传给 md_news。"""
    seen = {}

    def fake_md_news(symbols, since_hours=2, names=None, markets=None):
        seen["markets"] = markets
        return []

    monkeypatch.setattr(marketdata_client, "md_news", fake_md_news)

    asyncio.run(NewsCollector.from_database().fetch_all(
        symbols=["2330"], since_hours=24, markets={"2330": "TW"},
    ))

    assert seen["markets"] == {"2330": "TW"}


def test_collector_looks_up_markets_when_not_given(monkeypatch):
    """旧调用方(日报/信号包/采集)只给代码:由 _lookup_markets 从 Stock 表补上市场。"""
    seen = {}

    def fake_md_news(symbols, since_hours=2, names=None, markets=None):
        seen["markets"] = markets
        return []

    monkeypatch.setattr(marketdata_client, "md_news", fake_md_news)
    monkeypatch.setattr(news_collector, "_lookup_markets",
                        lambda symbols: {"2330": "TW", "600519": "CN"})

    asyncio.run(NewsCollector.from_database().fetch_all(
        symbols=["2330", "600519"], since_hours=24,
    ))

    assert seen["markets"] == {"2330": "TW", "600519": "CN"}


# ---------- /api/news ----------

class FakeDB:
    def __init__(self, stocks):
        self._stocks = stocks

    def query(self, _model):
        return SimpleNamespace(all=lambda: list(self._stocks))


def _call_get_news(monkeypatch, *, stocks, symbols="", names="", market="",
                   filter_related=True, items=None):
    seen = {}

    async def fake_fetch_all(self, symbols=None, since_hours=2, symbol_names=None, markets=None):
        seen.update(symbols=symbols, markets=markets)
        return list(items or [])

    monkeypatch.setattr(NewsCollector, "fetch_all", fake_fetch_all)
    result = asyncio.run(news_api.get_news(
        symbols=symbols, names=names, hours=168, limit=50,
        filter_related=filter_related, source="", market=market, db=FakeDB(stocks),
    ))
    return result, seen


def _tw_item(symbol="2330"):
    return NewsItem(
        source="yahoo_tw", external_id=f"y-{symbol}", title="法說會前瞻", content="",
        publish_time=datetime.now(), symbols=[symbol], importance=0, url="",
    )


def test_api_by_name_uses_watchlist_market(monkeypatch):
    """names=台積電 且自选里有 2330(TW):采集时带 market TW,yahoo_tw 新闻被视为相关。"""
    stocks = [SimpleNamespace(symbol="2330", name="台積電", market="TW")]

    result, seen = _call_get_news(monkeypatch, stocks=stocks, names="台積電",
                                  items=[_tw_item()])

    assert seen["markets"] == {"2330": "TW"}
    assert [r.source for r in result] == ["yahoo_tw"]


def test_api_explicit_market_for_symbol_not_in_watchlist(monkeypatch):
    """个股期货详情查标的现货(2330 不在自选):前端带 market=TW,仍按台股查询。"""
    result, seen = _call_get_news(monkeypatch, stocks=[], symbols="2330", market="TW",
                                  items=[_tw_item()])

    assert seen["symbols"] == ["2330"]
    assert seen["markets"] == {"2330": "TW"}
    assert [r.source for r in result] == ["yahoo_tw"]


def test_api_explicit_market_overrides_name_miss(monkeypatch):
    """names 查不到自选(标的不在自选)且带 market 时,不能直接回空——要退回用 symbols 查。"""
    result, seen = _call_get_news(monkeypatch, stocks=[], names="台積電", symbols="2330",
                                  market="TW", items=[_tw_item()])

    assert seen["markets"] == {"2330": "TW"}
    assert len(result) == 1


def test_api_mixed_watchlist_without_params(monkeypatch):
    """不带 symbols/names(全部自选):每个代码各自带自己的市场。"""
    stocks = [
        SimpleNamespace(symbol="2330", name="台積電", market="TW"),
        SimpleNamespace(symbol="600519", name="贵州茅台", market="CN"),
    ]

    _, seen = _call_get_news(monkeypatch, stocks=stocks)

    assert seen["markets"] == {"2330": "TW", "600519": "CN"}


# ---------- 研究模块:已知市场时直接传 ----------

def test_message_context_passes_known_market(monkeypatch):
    """AI 消息面摘要已知 symbol/market,直接把市场传给新闻采集。"""
    from src.modules.research.api import insights

    seen = {}

    async def fake_fetch_all(self, symbols=None, since_hours=2, symbol_names=None, markets=None):
        seen["markets"] = markets
        return []

    monkeypatch.setattr(NewsCollector, "fetch_all", fake_fetch_all)

    class DB:
        def query(self, _model):
            stock = SimpleNamespace(symbol="2330", name="台積電", market="TW")
            q = SimpleNamespace()
            q.filter = lambda *a, **k: q
            q.first = lambda: stock
            return q

    asyncio.run(insights._fetch_message_context(DB(), "2330", "TW"))

    assert seen["markets"] == {"2330": "TW"}
