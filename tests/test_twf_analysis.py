"""F6a:分析层接期货 —— 期货脉络(合约、结算日、现货、价差)、提示词说明、夜盘不跑 AI 盘中监测、期货资讯 API。

规则:
- 现货价取期交所 mis `{code}-S`(指数期货=加权/电子/金融指数,个股期货=标的股票)。
  夜盘时现货停在日盘收盘(实测 TXF-S 停在 13:33:15),价差要注明现货时间,避免 AI 当成同时点比较。
- 价差 = 期货 − 现货;> 0 正价差、< 0 逆价差。
- 决策(2026-10-01):夜盘只推使用者自设的价格提醒,AI 盘中监测只在日盘跑。
"""

from __future__ import annotations

import copy
import inspect
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from marketdata.http import market_post as real_market_post
from src.platform.marketdata import futures as fu
from src.platform.scheduling import trading_calendar as tc

TPE = ZoneInfo("Asia/Taipei")
FX = Path(__file__).parent / "fixtures"
_SSF = json.loads((FX / "taifex/ssf_lists.json").read_text(encoding="utf-8"))
_MARGIN = json.loads((FX / "taifex/ssf_margining.json").read_text(encoding="utf-8"))
_HOLIDAYS = json.loads((FX / "twse_holidays_2026.json").read_text(encoding="utf-8"))
_SPOT = json.loads((FX / "taifex/mis_spot.json").read_text(encoding="utf-8"))
_SPOT_ROWS = {r["SymbolID"]: r for r in _SPOT["RtData"]["QuoteList"] if r["SymbolID"]}
_BLANK = next(r for r in _SPOT["RtData"]["QuoteList"] if not r["SymbolID"])
NIGHT = datetime(2026, 10, 1, 20, 0, tzinfo=TPE)
DAY = datetime(2026, 10, 1, 10, 0, tzinfo=TPE)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    tc.reset_cache()
    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", lambda: _HOLIDAYS)
    tc.refresh_tw_blocking()
    monkeypatch.setattr(fu, "CACHE_FILE", tmp_path / "futures_list_cache.json")
    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", lambda: _SSF)
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", lambda: _MARGIN)
    fu.reset_cache()
    yield
    fu.reset_cache()
    tc.reset_cache()


@pytest.fixture
def spot(monkeypatch):
    from src.platform.marketdata import futures_context as fc

    calls = []

    def fake_post(url, **kwargs):
        inspect.signature(real_market_post).bind(url, **kwargs)
        ids = kwargs["json_body"]["SymbolID"]
        calls.append(ids)
        rows = [copy.deepcopy(_SPOT_ROWS.get(i, _BLANK)) for i in ids]
        return {"RtCode": "0", "RtMsg": "", "RtData": {"QuoteList": rows}}

    monkeypatch.setattr(fc, "market_post", fake_post)
    return calls


# ---------------------------------------------------------------- 现货与期货脉络


def test_fetch_spot_prices(spot):
    from src.platform.marketdata import futures_context as fc

    prices = fc.fetch_spot_prices(["TXF", "CDF", "ZZZ"])
    assert prices["TXF"] == (48353.49, "13:33:15")
    assert prices["CDF"] == (2510.0, "13:30:00")
    assert "ZZZ" not in prices
    assert spot == [["TXF-S", "CDF-S", "ZZZ-S"]]


def test_fetch_spot_prices_network_failure_returns_empty(monkeypatch):
    from src.platform.marketdata import futures_context as fc

    monkeypatch.setattr(fc, "market_post", lambda url, **kw: None)
    assert fc.fetch_spot_prices(["TXF"]) == {}


def test_build_futures_context_index(spot):
    from src.platform.marketdata import futures_context as fc

    quote = {"current_price": 48461.0, "contract": "TXFJ6", "session": "night"}
    ctx = fc.build_futures_context("TXF", quote, now=NIGHT)

    assert ctx["code"] == "TXF" and ctx["name"] == "台指期" and ctx["kind"] == "index"
    assert ctx["contract"] == "TXFJ6" and ctx["contract_month"] == "202610"
    assert ctx["settlement_date"] == date(2026, 10, 21)
    assert ctx["days_to_settlement"] == 20
    assert ctx["session"] == "night"
    assert ctx["spot"] == 48353.49 and ctx["spot_time"] == "13:33:15"
    assert ctx["basis"] == pytest.approx(107.51)
    assert ctx["basis_pct"] == pytest.approx(107.51 / 48353.49 * 100)
    assert ctx["underlying_code"] is None


def test_build_futures_context_stock_future_and_rolled_contract(spot):
    from src.platform.marketdata import futures_context as fc

    # 报价用的是远月(近月没挂牌)时,合约/结算日以实际合约为准
    ctx = fc.build_futures_context("CDF", {"current_price": 2520.0, "contract": "CDFL6", "session": "day"}, now=DAY)
    assert ctx["kind"] == "stock" and ctx["underlying_code"] == "2330"
    assert ctx["contract"] == "CDFL6" and ctx["contract_month"] == "202612"
    assert ctx["settlement_date"] == date(2026, 12, 16)
    assert ctx["basis"] == pytest.approx(10.0)


def test_build_futures_context_without_spot(monkeypatch):
    from src.platform.marketdata import futures_context as fc

    monkeypatch.setattr(fc, "market_post", lambda url, **kw: None)
    ctx = fc.build_futures_context("TXF", {"current_price": 48461.0, "contract": "TXFJ6"}, now=DAY)
    assert ctx["spot"] is None and ctx["basis"] is None and ctx["basis_pct"] is None
    assert ctx["contract"] == "TXFJ6"


def test_build_futures_context_unknown_code_is_none(spot):
    from src.platform.marketdata import futures_context as fc

    assert fc.build_futures_context("ZZZ", {"current_price": 1.0}, now=DAY) is None


def test_format_futures_context_zh(spot):
    from src.platform.marketdata import futures_context as fc

    ctx = fc.build_futures_context("TXF", {"current_price": 48461.0, "contract": "TXFJ6", "session": "night"}, now=NIGHT)
    text = "\n".join(fc.format_futures_context(ctx, "zh-TW"))
    assert "TXFJ6" in text and "2026-10-21" in text and "20" in text
    assert "正價差" in text and "107.51" in text
    assert "夜盤" in text and "13:33" in text          # 夜盘要注明现货是日盘收盘时间


def test_format_futures_context_backwardation_and_en(spot):
    from src.platform.marketdata import futures_context as fc

    ctx = fc.build_futures_context("TXF", {"current_price": 48300.0, "contract": "TXFJ6", "session": "day"}, now=DAY)
    assert "逆價差" in "\n".join(fc.format_futures_context(ctx, "zh-TW"))
    en = "\n".join(fc.format_futures_context(ctx, "en-US"))
    assert "backwardation" in en.lower() and "TXFJ6" in en


def test_futures_prompt_note():
    from src.platform.marketdata import futures_context as fc

    tw = SimpleNamespace(market="TW")
    twf = SimpleNamespace(market="TWF")
    assert fc.futures_prompt_note([tw], "zh-TW") == ""
    note = fc.futures_prompt_note([tw, twf], "zh-TW")
    assert "期貨" in note and "價差" in note and "結算" in note and "三大法人" in note
    assert "futures" in fc.futures_prompt_note([twf], "en-US").lower()


def test_agents_use_shared_futures_note():
    root = Path(__file__).resolve().parents[1] / "src/modules/automation"
    for name in ("intraday_monitor.py", "daily_report.py", "premarket_outlook.py"):
        assert "futures_prompt_note" in (root / name).read_text(encoding="utf-8"), name


# ---------------------------------------------------------------- 日盘 / 夜盘


@pytest.mark.parametrize(
    "market, when, expected",
    [
        ("TWF", DAY, True),
        ("TWF", NIGHT, False),                                         # 夜盘不跑 AI 盘中监测
        ("TWF", datetime(2026, 10, 3, 3, 0, tzinfo=TPE), False),      # 周六凌晨(周五夜盘)
        ("TWF", datetime(2026, 10, 1, 8, 50, tzinfo=TPE), True),
        ("TW", DAY, True),
        ("TW", NIGHT, False),
    ],
)
def test_intraday_monitor_trading_gate(market, when, expected):
    from src.modules.automation.intraday_monitor import is_market_trading
    from src.platform.marketdata.models import MarketCode

    assert is_market_trading(MarketCode(market), now=when) is expected


def test_day_session_helper():
    from src.platform.marketdata.models import MARKETS, MarketCode

    twf = MARKETS[MarketCode.TWF]
    assert twf.is_day_session_time(DAY) is True
    assert twf.is_day_session_time(NIGHT) is False
    assert twf.is_trading_time(NIGHT) is True                         # 价格提醒仍视夜盘为交易中
    assert MARKETS[MarketCode.TW].is_day_session_time(DAY) is True


def test_intraday_market_label_futures():
    from src.modules.automation.intraday_monitor import market_label
    from src.platform.marketdata.models import MarketCode

    assert market_label(MarketCode.TWF) == "期貨"
    assert market_label(MarketCode.TWF, "en-US") == "Taiwan futures"


# ---------------------------------------------------------------- 盘中监测提示词


def _intraday_prompt(futures_ctx, market="TWF", symbol="TXF"):
    from src.modules.automation.intraday_monitor import IntradayMonitorAgent
    from src.platform.marketdata.models import MarketCode, StockData

    stock = StockData(
        symbol=symbol, name="台指期", market=MarketCode(market), current_price=48461.0,
        change_pct=-0.49, change_amount=-237.0, open_price=48622.0, high_price=48661.0,
        low_price=48250.0, prev_close=48698.0, volume=15421, turnover=0,
    )

    class _Portfolio:
        total_available_funds = 0.0
        accounts: list = []

        def get_positions_for_stock(self, symbol):
            return []

    class _Ctx:
        portfolio = _Portfolio()
        watchlist = [SimpleNamespace(market=MarketCode(market), symbol=symbol)]
        report_language = "zh-TW"

    data = {"stock_data": stock, "kline_summary": {"trend": "多头排列"}, "symbol_context": {},
            "futures_context": futures_ctx}
    return IntradayMonitorAgent(price_alert_threshold=3.0).build_prompt(data, _Ctx())


def test_intraday_prompt_includes_futures_context(spot):
    from src.platform.marketdata import futures_context as fc

    ctx = fc.build_futures_context("TXF", {"current_price": 48461.0, "contract": "TXFJ6", "session": "night"}, now=NIGHT)
    system, user = _intraday_prompt(ctx)
    assert "期貨" in system and "價差" in system
    assert "台股说明" not in system                                   # 不能套用台股(三大法人、融资融券)说明
    assert "TXFJ6" in user and "正價差" in user


def test_intraday_collect_attaches_futures_context(monkeypatch):
    import asyncio

    from src.modules.automation import intraday_monitor as im
    from src.platform.marketdata.models import MarketCode, StockData

    stock = StockData(symbol="TXF", name="台指期", market=MarketCode.TWF, current_price=48461.0,
                      change_pct=-0.49, change_amount=-237.0, open_price=0, high_price=0, low_price=0,
                      prev_close=48698.0, volume=0, turnover=0)

    class FakePackBuilder:
        async def build_for_symbols(self, **kwargs):
            return {"TXF": SimpleNamespace(quote=stock, technical={})}

    class FakeContextBuilder:
        async def build_symbol_contexts(self, **kwargs):
            return {}

    seen = {}

    def fake_build(code, quote, now=None):
        seen["code"] = code
        return {"marker": True}

    monkeypatch.setattr(im, "SignalPackBuilder", FakePackBuilder)
    monkeypatch.setattr(im, "ContextBuilder", FakeContextBuilder)
    monkeypatch.setattr(im, "get_latest_analysis", lambda **kw: None)
    monkeypatch.setattr(im, "get_analysis", lambda **kw: None)
    monkeypatch.setattr(im, "build_futures_context", fake_build)

    agent = im.IntradayMonitorAgent(price_alert_threshold=3.0)
    agent.bypass_market_hours = True
    ctx = SimpleNamespace(watchlist=[SimpleNamespace(symbol="TXF", market=MarketCode.TWF, name="台指期")],
                          portfolio=None, report_language="zh-TW")
    data = asyncio.run(agent.collect(ctx))
    assert seen["code"] == "TXF" and data["futures_context"] == {"marker": True}


# ---------------------------------------------------------------- 期货资讯 API(给前端详情页)


def test_futures_info_endpoint(spot, monkeypatch):
    import asyncio

    from src.modules.market.api import futures as api

    monkeypatch.setattr(api, "md_quote_rows", lambda symbols, market: [
        {"symbol": "CDF", "current_price": 2520.0, "contract": "CDFJ6", "session": "night"}
    ])
    info = asyncio.run(api.get_futures_info("cdf"))
    assert info["code"] == "CDF" and info["underlying_code"] == "2330"
    assert info["contract"] == "CDFJ6" and info["settlement_date"] == "2026-10-21"
    assert info["basis"] == pytest.approx(10.0)


def test_futures_info_unknown_code_404():
    import asyncio

    from fastapi import HTTPException

    from src.modules.market.api import futures as api

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.get_futures_info("ZZZ"))
    assert exc.value.status_code == 404
