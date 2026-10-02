"""TradingAgents 深度分析读得到台股新闻(Yahoo 奇摩),不只重大讯息。

2026-10-02:台股路由改走 PanWatch 后,get_news 只回 collect() 收的重大讯息(events);
ETF 多半没有重大讯息 → 新闻分析师拿到「没有个股新闻」。台股新闻源(yahoo_tw)已可用,
collect() 要一并收集,get_news 输出新闻段落。
A 股不加(从台湾连东财新闻常逾时,且 A 股已有公告),行为不变。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.modules.automation.tradingagents import agent as agent_module
from src.modules.automation.tradingagents import data_context
from src.modules.automation.tradingagents import toolkit_adapter as ta
from src.modules.automation.tradingagents.agent import TradingAgentsAgent
from src.platform.marketdata import marketdata_client
from src.platform.marketdata.collectors.news_collector import NewsItem
from src.platform.marketdata.models import MarketCode


def _news(title, minute):
    return NewsItem(
        source="yahoo_tw", external_id=title, title=title, content="",
        publish_time=datetime(2026, 10, 2, 9, minute), symbols=["00685L"], url="",
    )


def _fake_md():
    md = MagicMock()
    md.quotes = MagicMock(return_value=[])
    md.klines = MagicMock(return_value=[])
    md.capital_flow = MagicMock(return_value=None)
    md.events = MagicMock(return_value=[])
    return md


def _collect(stock, md_news):
    context = MagicMock()
    context.watchlist = [stock]
    from src.platform.marketdata.collectors.kline_collector import KlineCollector

    # 其他来源一律假掉(技术指标在 K 线为空时会自己连网抓)
    with patch.object(agent_module, "get_market_data", _fake_md), \
            patch.object(marketdata_client, "md_news", md_news), \
            patch.object(data_context, "fetch_financial_abstract", lambda symbol: None), \
            patch.object(KlineCollector, "get_technical_indicators", lambda self, *a, **k: None):
        return asyncio.run(TradingAgentsAgent().collect(context))


def test_collect_gathers_tw_news_with_tw_market():
    """台股:collect() 以 market=TW 收集近 7 天新闻,存进 data["news"]。"""
    calls = []

    def fake_md_news(symbols, since_hours=2, names=None, markets=None):
        calls.append((symbols, since_hours, names, markets))
        return [_news("台股開盤", 5)]

    stock = SimpleNamespace(symbol="00685L", name="群益臺灣加權正2", market=MarketCode.TW)
    data = _collect(stock, fake_md_news)

    assert calls == [(["00685L"], 168, {"00685L": "群益臺灣加權正2"}, {"00685L": "TW"})]
    assert [n.title for n in data["news"]] == ["台股開盤"]


def test_collect_does_not_fetch_news_for_a_share():
    """A 股:不额外收集新闻(行为不变)。"""
    def forbidden(*a, **k):
        raise AssertionError("A 股不应收集新闻")

    stock = SimpleNamespace(symbol="600519", name="贵州茅台", market=MarketCode.CN)
    data = _collect(stock, forbidden)

    assert data.get("news") in (None, [])


def test_collect_news_failure_degrades_to_empty():
    """新闻来源失败:不影响整轮分析,news 为空。"""
    def boom(*a, **k):
        raise RuntimeError("yahoo down")

    stock = SimpleNamespace(symbol="2330", name="台積電", market=MarketCode.TW)
    data = _collect(stock, boom)

    assert data["news"] == []


def _ctx(news, events=()):
    return ta.panwatch_data_context({
        "stock": SimpleNamespace(symbol="00685L", name="群益臺灣加權正2", market=MarketCode.TW),
        "quote": {}, "klines": [], "events": list(events), "news": news,
    })


def test_get_news_includes_tw_news_when_no_events(monkeypatch):
    """没有重大讯息时,get_news 仍输出新闻标题,而不是「没有个股新闻」。"""
    monkeypatch.setattr(ta, "_real_route_to_vendor", lambda *a, **k: "UPSTREAM")
    with _ctx([_news("台股開盤小漲", 23), _news("ETF 規模創高", 10)]):
        out = ta._patched_route_to_vendor("get_news", "00685L", "2026-09-25", "2026-10-02")

    assert "台股開盤小漲" in out and "ETF 規模創高" in out
    assert "No company-specific news" not in out
    assert out.index("台股開盤小漲") < out.index("ETF 規模創高")  # 新的在前


def test_get_news_includes_both_events_and_news(monkeypatch):
    """重大讯息与新闻都有时两段都给。"""
    monkeypatch.setattr(ta, "_real_route_to_vendor", lambda *a, **k: "UPSTREAM")
    event = SimpleNamespace(title="董事會決議配息", publish_time="2026-10-01 17:00")
    with _ctx([_news("台股開盤小漲", 23)], events=[event]):
        out = ta._patched_route_to_vendor("get_news", "00685L", "2026-09-25", "2026-10-02")

    assert "董事會決議配息" in out and "台股開盤小漲" in out


def test_get_news_without_events_or_news_keeps_no_fabrication_notice(monkeypatch):
    """两者都没有:维持「不要编造」提示。"""
    monkeypatch.setattr(ta, "_real_route_to_vendor", lambda *a, **k: "UPSTREAM")
    with _ctx([]):
        out = ta._patched_route_to_vendor("get_news", "00685L", "2026-09-25", "2026-10-02")

    assert "DO NOT pull unrelated global news" in out
