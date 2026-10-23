"""台股／台指期专属资料进入研究图证据(上游 0be7318 改为研究图后的移植合约)。

旧版把这些内容拼进 prompts/*.txt;研究图改为按 domain 分派证据给各角色,
所以台股资料必须落在对应 domain 的证据里,角色才看得到:
- technical:缠论摘要(仅作参考)、台指期的期货脉络
- flow:三大法人买卖超文字、集保股权分散摘要(只读本机 DB,不打网络)
- market:台股/期货的市场规则(单位、涨跌幅、可当冲、期货价差)
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.modules.automation.base import AgentContext, PortfolioInfo
from src.modules.research.orchestration import evidence as ev
from src.modules.research.orchestration import taiwan
from src.platform.marketdata.models import MarketCode
from src.platform.runtime.config import AppConfig, Settings, StockConfig

CHAN = {"day": {"bi": [{"dir": "up", "sure": True}], "zs": [{"zd": 100.0, "zg": 110.0}], "position": "above",
                "bsp": [{"type": "1", "is_buy": True, "time": "2026-10-20", "sure": True}]},
        "m30": None, "nesting": {"confirmed": False}}
THREE_INSTITUTIONS = {"type": "three_institutions", "status": "法人买超", "foreign": 1_200_000,
                      "investment_trust": 300_000, "dealer": -50_000, "total": 1_450_000}


def _pack(technical=None, capital_flow=None):
    return SimpleNamespace(quote={"current_price": 100.0}, technical=technical or {}, missing=[],
                           capital_flow=capital_flow, sources=[], news=None, events=None)


def _context(keys, language="zh-TW"):
    stocks = [StockConfig(symbol=s, market=m, name=f"QA {s}") for m, s in keys]
    return AgentContext(SimpleNamespace(model="script"), SimpleNamespace(),
                        AppConfig(Settings(_env_file=None), stocks), portfolio=PortfolioInfo(),
                        suppress_notify=True, report_language=language)


def _agent(name, data_for):
    async def collect(scoped):
        return data_for(scoped.watchlist)
    return SimpleNamespace(name=name, collect=collect, price_alert_threshold=3.0,
                           stop_loss_warning=-5.0, take_profit_warning=10.0)


def _prepare(agent, context):
    prepared, _details, _snapshots = asyncio.run(ev.prepare(agent, context, "run-tw"))
    assert prepared is not None
    return prepared


def _domain(prepared, stock_key, domain):
    items = [e.content for e in prepared.evidence if e.stock_key == stock_key and e.domain == domain]
    assert items, f"{stock_key} 缺少 {domain} 证据"
    return items


@pytest.fixture
def dispersion_calls(monkeypatch):
    calls = []

    def fake(symbol, market, language):
        calls.append((symbol, market, language))
        return "集保 2026-10-16:千張大戶 84.77%(+0.12pp),總人數 3,020,649(-1,234)"

    monkeypatch.setattr(taiwan, "read_dispersion_line", fake)
    return calls


def test_tw_stock_evidence_includes_chan_flow_dispersion_and_rules(dispersion_calls):
    agent = _agent("premarket_outlook", lambda stocks: {
        "signal_packs": {"2330": _pack(technical={"chan": CHAN}, capital_flow=THREE_INSTITUTIONS)},
        "indices": [],
    })
    prepared = _prepare(agent, _context([(MarketCode.TW, "2330")]))

    technical = _domain(prepared, "TW:2330", "technical")[0]
    assert technical["chan_summary"], "缠论摘要要以文字放进 technical 证据"
    assert "仅作参考" in technical["chan_note"]

    flow = _domain(prepared, "TW:2330", "flow")[0]
    assert flow["capital_flow_summary"], "三大法人买卖超要附文字摘要(单位为股)"
    assert flow["shareholder_dispersion"].startswith("集保")
    assert dispersion_calls == [("2330", "TW", "zh-TW")]

    rules = " ".join(str(c) for c in _domain(prepared, "TW:2330", "market"))
    assert "三大法人" in rules and "±10%" in rules and "当冲" in rules


def test_twf_evidence_includes_futures_context_and_futures_rules(dispersion_calls):
    futures_ctx = {"contract": "TXFK6", "basis": 120.0, "marker": "futures"}
    agent = _agent("intraday_monitor", lambda stocks: {
        "signal_pack": _pack(technical={"chan": CHAN}),
        "futures_context": futures_ctx,
    })
    prepared = _prepare(agent, _context([(MarketCode.TWF, "TXF")]))

    technical = _domain(prepared, "TWF:TXF", "technical")[0]
    assert technical["futures_context"]["contract"] == "TXFK6"
    rules = " ".join(str(c) for c in _domain(prepared, "TWF:TXF", "market"))
    assert "價差" in rules or "价差" in rules
    assert "台股说明" not in rules, "期货不能套用台股(三大法人、融资融券)规则"
    assert dispersion_calls == [], "期货没有集保资料"


def test_daily_report_futures_context_is_keyed_by_symbol(dispersion_calls):
    agent = _agent("premarket_outlook", lambda stocks: {
        "signal_packs": {"TXF": _pack()},
        "futures_contexts": {"TXF": {"contract": "TXFK6"}},
        "indices": [],
    })
    prepared = _prepare(agent, _context([(MarketCode.TWF, "TXF")]))
    assert _domain(prepared, "TWF:TXF", "technical")[0]["futures_context"] == {"contract": "TXFK6"}


def test_cn_stock_gets_no_taiwan_extras(dispersion_calls):
    agent = _agent("premarket_outlook", lambda stocks: {
        "signal_packs": {"600519": _pack(capital_flow={"status": "主力流入", "main_net_inflow": 1e8})},
        "indices": [],
    })
    prepared = _prepare(agent, _context([(MarketCode.CN, "600519")]))

    technical = _domain(prepared, "CN:600519", "technical")[0]
    flow = _domain(prepared, "CN:600519", "flow")[0]
    assert "futures_context" not in technical and "shareholder_dispersion" not in flow
    assert dispersion_calls == []
    assert not [e for e in prepared.evidence if e.stock_key == "CN:600519" and e.domain == "market"
                and "market_rules" in e.content]


def test_dispersion_failure_does_not_break_research(monkeypatch):
    def boom(symbol, market, language):
        raise RuntimeError("db locked")

    monkeypatch.setattr(taiwan, "read_dispersion_line", boom)
    agent = _agent("premarket_outlook", lambda stocks: {"signal_packs": {"2330": _pack()}, "indices": []})
    prepared = _prepare(agent, _context([(MarketCode.TW, "2330")]))
    assert "shareholder_dispersion" not in _domain(prepared, "TW:2330", "flow")[0]


def test_read_dispersion_line_only_reads_local_db(monkeypatch):
    seen = []

    def fake_line(db, symbol, market, language):
        seen.append((symbol, market, language))
        return "集保摘要"

    import src.modules.market.shareholder_dispersion as svc
    monkeypatch.setattr(svc, "dispersion_line_for", fake_line)
    assert taiwan.read_dispersion_line("2330", "TW", "zh-TW") == "集保摘要"
    assert seen == [("2330", "TW", "zh-TW")]
    assert taiwan.read_dispersion_line("TXF", "TWF", "zh-TW") == ""


def test_premarket_collect_feeds_tw_indices_into_indices(monkeypatch):
    from src.modules.automation import premarket_outlook as pm

    class FakeMD:
        def tw_index_quotes(self):
            return [{"symbol": "TWII", "name": "加權指數", "current_price": 23000.0, "change_pct": 0.5}]

    async def fake_build(self, **kwargs):
        return {"2330": _pack()}

    monkeypatch.setattr(pm, "get_market_data", lambda: FakeMD(), raising=False)
    monkeypatch.setattr(pm.SignalPackBuilder, "build_for_symbols", fake_build)

    async def no_context(self, **kwargs):
        return {}

    monkeypatch.setattr(pm.ContextBuilder, "build_symbol_contexts", no_context)
    context = _context([(MarketCode.TW, "2330")])
    context._research_collect = True
    data = asyncio.run(pm.PremarketOutlookAgent().collect(context))
    names = [item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
             for item in data.get("indices") or []]
    assert "加權指數" in names


def test_intraday_fast_collect_attaches_futures_context(monkeypatch):
    from src.modules.automation import intraday_monitor as im

    quote = SimpleNamespace(current_price=48461.0)

    async def fake_build(self, **kwargs):
        return {"TXF": SimpleNamespace(quote=quote, technical={})}

    monkeypatch.setattr(im.SignalPackBuilder, "build_for_symbols", fake_build)
    monkeypatch.setattr(im, "build_futures_context", lambda code, q, now=None: {"contract": "TXFK6"})
    agent = im.IntradayMonitorAgent()
    agent.bypass_market_hours = True
    context = _context([(MarketCode.TWF, "TXF")])
    context._research_fast = True
    data = asyncio.run(agent.collect(context))
    assert data["futures_context"] == {"contract": "TXFK6"}
