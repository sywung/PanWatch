"""台股接进分析层:加权指数、组合基准、三大法人资金面、盘中/日报文字。"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from marketdata import Bar
from marketdata.types import CapitalFlow as MdCapitalFlow
from src.platform.marketdata.models import MarketCode

ROOT = Path(__file__).resolve().parents[1]


def _tw_flow(**kw):
    base = dict(
        symbol="2330", name="台積電", main_net_inflow=None, main_net_inflow_pct=None,
        super_net_inflow=None, big_net_inflow=None, mid_net_inflow=None, small_net_inflow=None,
        foreign_net=702_594.0, trust_net=761_722.0, dealer_net=399_899.0,
        institutional_net=1_864_215.0, unit="股", trade_date="2026-09-30",
    )
    base.update(kw)
    return MdCapitalFlow(**base)


@pytest.fixture
def fake_md(monkeypatch):
    """替换宿主取得的 MarketData 实例,记录调用。"""
    calls = {}

    class _MD:
        def capital_flow(self, symbol, *, market="CN"):
            calls.setdefault("capital_flow", []).append((symbol, market))
            return _tw_flow(symbol=symbol) if market == "TW" else None

        def index_klines(self, code, *, market, days=120):
            calls.setdefault("index_klines", []).append((code, market))
            return [Bar(date=f"2026-09-{d:02d}", open=100 + d, close=100 + d, high=101 + d, low=99 + d)
                    for d in range(1, 26)]

        def tw_index_quotes(self):
            calls.setdefault("tw_index_quotes", []).append(True)
            return [
                {"symbol": "TWII", "name": "加權指數", "current_price": 47940.13, "change_pct": 0.5,
                 "change_amount": 238.5, "volume": None, "turnover": None},
                {"symbol": "TPEX", "name": "櫃買指數", "current_price": 417.07, "change_pct": -0.2,
                 "change_amount": -0.8, "volume": None, "turnover": None},
            ]

    md = _MD()
    import src.platform.marketdata.marketdata_client as mc

    monkeypatch.setattr(mc, "get_market_data", lambda: md)
    from src.platform.marketdata.collectors import capital_flow_collector as cfc

    monkeypatch.setattr(cfc, "get_market_data", lambda: md)
    cfc._FLOW_CACHE.clear()
    return calls


# ---------------------------------------------------------------- 三大法人


def test_capital_flow_collector_tw_does_not_crash_and_summarizes(fake_md):
    from src.platform.marketdata.collectors.capital_flow_collector import CapitalFlowCollector

    s = CapitalFlowCollector(MarketCode.TW).get_capital_flow_summary("2330")
    assert "error" not in s
    assert s["type"] == "three_institutions"
    assert s["foreign_net"] == 702_594 and s["trust_net"] == 761_722
    assert s["dealer_net"] == 399_899 and s["institutional_net"] == 1_864_215
    assert s["unit"] == "股" and s["trade_date"] == "2026-09-30"
    assert "買超" in s["status"] or "买超" in s["status"]


def test_capital_flow_collector_tw_sell_status(fake_md, monkeypatch):
    from src.platform.marketdata.collectors import capital_flow_collector as cfc

    md = cfc.get_market_data()
    monkeypatch.setattr(md, "capital_flow", lambda s, market="CN": _tw_flow(symbol=s, institutional_net=-50_000.0))
    s = cfc.CapitalFlowCollector(MarketCode.TW).get_capital_flow_summary("2317")
    assert "賣超" in s["status"] or "卖超" in s["status"]


def test_capital_flow_text_helper():
    from src.modules.market.capital_flow_text import format_capital_flow_line

    tw = {"type": "three_institutions", "foreign_net": 702_594, "trust_net": -12_000,
          "dealer_net": 399_899, "institutional_net": 1_090_493, "unit": "股", "status": "三大法人買超"}
    line = format_capital_flow_line(tw, "zh-TW")
    assert "外資" in line and "投信" in line and "自營" in line
    assert "+702,594" in line and "-12,000" in line
    assert "主力" not in line
    en = format_capital_flow_line(tw, "en-US")
    assert "Foreign" in en and "+702,594" in en
    cn = {"main_net_inflow": 1.5e8, "main_net_inflow_pct": 6.2, "status": "主力明显流入"}
    cn_line = format_capital_flow_line(cn, "zh-CN")
    assert "主力" in cn_line and "外資" not in cn_line


def test_agents_use_shared_flow_text_helper():
    """日报/盘前/盘中三个 Agent 不再各自用 main_net_inflow 拼字,统一走 helper(台股才会正确)。"""
    for rel in ("src/modules/automation/daily_report.py",
                "src/modules/automation/premarket_outlook.py",
                "src/modules/automation/intraday_monitor.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "format_capital_flow_line" in text, rel
        assert 'flow.get("main_net_inflow")' not in text, rel


def test_capital_flow_markets_include_tw():
    from src.platform.marketdata.models import CAPITAL_FLOW_MARKETS

    assert CAPITAL_FLOW_MARKETS == frozenset({"CN", "TW"})
    sp = (ROOT / "src/modules/research/signals/signal_pack.py").read_text(encoding="utf-8")
    assert "CAPITAL_FLOW_MARKETS" in sp
    assert not re.search(r"include_capital_flow and market == MarketCode\.CN", sp)


# ---------------------------------------------------------------- 指数


def test_index_klines_taiex_via_yahoo(monkeypatch):
    import marketdata.vendors.kline as kv
    from marketdata import MarketData, StaticConfigProvider

    urls = []

    def fake_get(url, **k):
        urls.append(url)
        q = {"open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0], "close": [1.0, 2.0], "volume": [0, 0]}
        return {"chart": {"result": [{"timestamp": [1782864000, 1782950400], "indicators": {"quote": [q]}}]}}

    monkeypatch.setattr(kv, "market_get", fake_get)
    bars = MarketData(config=StaticConfigProvider({})).index_klines("TWII", market="TW", days=30)
    assert len(bars) == 2
    assert urls and urls[0].rsplit("/", 1)[1] in ("^TWII", "%5ETWII")


def test_tw_index_quotes_from_mis(monkeypatch):
    import marketdata.vendors.twse as tv
    from marketdata import MarketData, StaticConfigProvider

    def fake_get(url, *, params=None, **k):
        assert set(params["ex_ch"].split("|")) == {"tse_t00.tw", "otc_o00.tw"}
        return {"msgArray": [
            {"c": "t00", "n": "發行量加權股價指數", "z": "47940.13", "y": "47701.63"},
            {"c": "o00", "n": "櫃買指數", "z": "-", "y": "417.07"},
        ]}

    monkeypatch.setattr(tv, "market_get", fake_get)
    rows = {r["symbol"]: r for r in MarketData(config=StaticConfigProvider({})).tw_index_quotes()}
    assert rows["TWII"]["name"] == "加權指數"
    assert rows["TWII"]["current_price"] == 47940.13
    assert abs(rows["TWII"]["change_pct"] - (47940.13 - 47701.63) / 47701.63 * 100) < 1e-9
    assert rows["TPEX"]["name"] == "櫃買指數" and rows["TPEX"]["current_price"] == 417.07


def test_context_builder_uses_taiex_for_tw():
    from src.modules.research.context_builder import ContextBuilder

    assert ContextBuilder._index_for_market(MarketCode.TW) == ("TWII", "加權指數")
    assert ContextBuilder._index_for_market("TW") == ("TWII", "加權指數")


def test_daily_report_fetches_tw_indices(fake_md):
    from src.modules.automation.daily_report import DailyReportAgent

    out = asyncio.run(DailyReportAgent()._fetch_index_for_market(MarketCode.TW))
    assert [i.symbol for i in out] == ["TWII", "TPEX"]
    assert all(i.market == MarketCode.TW for i in out)


# ---------------------------------------------------------------- 组合基准


def test_portfolio_default_benchmark_is_taiex():
    from src.modules.portfolio import portfolio_benchmark as pb

    assert pb.DEFAULT_BENCHMARK == "TWII"
    assert pb.benchmark_label("TWII") == "加權指數"
    assert pb.benchmark_label("000300") == "沪深300"  # A 股基准仍可选


def test_portfolio_api_default_benchmark_param():
    import inspect

    from src.modules.portfolio.api import accounts

    for fn in (accounts.portfolio_benchmark, accounts.portfolio_attribution):
        assert inspect.signature(fn).parameters["benchmark"].default == "TWII"


# ---------------------------------------------------------------- 文字


def test_intraday_market_label_tw():
    from src.modules.automation.intraday_monitor import market_label

    assert market_label(MarketCode.TW, "zh-TW") == "台股"
    assert market_label(MarketCode.TW, "zh-CN") == "台股"
    assert market_label(MarketCode.TW, "en-US") == "Taiwan market"
