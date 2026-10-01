"""F1:台湾期货(TWF)市场定义、跨午夜夜盘、期货日历与结算日、市场状态。

规则来源(2026-10-01 实测,见 vault projects/panwatch/phase2-plan.md):
- 期货交易日 = 证交所交易日(FinMind TaiwanFuturesDaily 2026 全年逐日比对一致,
  唯一例外 7/10 是台风临时停市,股票也停)。
- 一般时段 08:45–13:45;盘后(夜盘)15:00–次日 05:00。
- 交易日 D 的晚上一定开夜盘(含连假前最后一个交易日,如 2026-02-11、2026-09-24),
  跨过午夜那段属于 D;D 不是交易日就没有夜盘。
- 月契约结算日 = 当月第三个星期三,遇休市顺延到下一个交易日(2026-02 → 2/23)。
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from marketdata.symbol import Market, Symbol
from src.platform.marketdata import models as market_models
from src.platform.marketdata.models import ALL_MARKETS, MARKETS, MarketCode, TradingSession
from src.platform.scheduling import trading_calendar as tc

TPE = ZoneInfo("Asia/Taipei")
# 证交所 openapi holidaySchedule 的真实 2026 全年清单(2026-10-01 抓取)
_RAW_2026 = json.loads(
    (Path(__file__).parent / "fixtures/twse_holidays_2026.json").read_text(encoding="utf-8")
)


@pytest.fixture(autouse=True)
def _reset_calendar():
    tc.reset_cache()
    yield
    tc.reset_cache()


@pytest.fixture
def tw_calendar(monkeypatch):
    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", lambda: _RAW_2026)
    assert tc.refresh_tw_blocking() is True


def _tpe(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TPE)


# ---------------------------------------------------------------- 市场定义


def test_twf_market_definition():
    assert MarketCode("TWF") is MarketCode.TWF
    md = MARKETS[MarketCode.TWF]
    assert md.timezone == "Asia/Taipei"
    assert md.name == "期貨"
    assert [(s.start, s.end) for s in md.sessions] == [
        (time(8, 45), time(13, 45)),
        (time(15, 0), time(5, 0)),
    ]


def test_session_crosses_midnight_flag():
    assert TradingSession(time(15, 0), time(5, 0)).crosses_midnight is True
    assert TradingSession(time(8, 45), time(13, 45)).crosses_midnight is False


def test_twf_is_not_a_stock_market():
    # ALL_MARKETS 的语意是「股票市场」(模拟盘资金配置、策略、选股都在用),期货不能混进去
    assert "TWF" not in ALL_MARKETS
    assert market_models.FUTURES_MARKETS == frozenset({"TWF"})


@pytest.mark.parametrize("code", ["TXF", "MXF", "TMF", "CDF", "QFF", "CM1", "DC1"])
def test_twf_symbol_pattern_accepts_continuous_codes(code):
    import re

    assert re.match(MARKETS[MarketCode.TWF].symbol_pattern, code)


@pytest.mark.parametrize("code", ["2330", "txf", "TX", "TXFJ6", "00679B", ""])
def test_twf_symbol_pattern_rejects_non_futures(code):
    import re

    assert not re.match(MARKETS[MarketCode.TWF].symbol_pattern, code)


def test_symbol_twf_only_when_explicit():
    assert Market("TWF") is Market.TWF
    assert Symbol.parse("TXF", "TWF").market is Market.TWF
    # 不带 market 时不能自动判成期货(TXF 形似美股代码,维持原判断)
    assert Symbol.parse("TXF").market is not Market.TWF
    assert Symbol.parse("2330").market is Market.TW


# ---------------------------------------------------------------- 交易日


@pytest.mark.parametrize(
    "d",
    ["2026-02-11", "2026-02-12", "2026-02-13", "2026-02-23", "2026-09-25", "2026-09-28",
     "2026-09-29", "2026-10-09", "2026-10-03", "2026-10-01"],
)
def test_twf_trading_days_follow_tw_calendar(tw_calendar, d):
    target = date.fromisoformat(d)
    assert tc.is_trading_day("TWF", target) == tc.is_trading_day("TW", target)
    assert tc.is_trading_day(MarketCode.TWF, target) == tc.is_trading_day(MarketCode.TW, target)


# ---------------------------------------------------------------- 交易时段(含夜盘)


@pytest.mark.parametrize(
    "when, expected",
    [
        # 一般交易日(2026-09-30 周三)日盘边界,含端点
        (_tpe(2026, 9, 30, 8, 44), False),
        (_tpe(2026, 9, 30, 8, 45), True),
        (_tpe(2026, 9, 30, 13, 45), True),
        (_tpe(2026, 9, 30, 13, 46), False),
        (_tpe(2026, 9, 30, 14, 59), False),
        # 夜盘:当晚 15:00 起,跨午夜到次日 05:00
        (_tpe(2026, 9, 30, 15, 0), True),
        (_tpe(2026, 9, 30, 23, 59), True),
        (_tpe(2026, 10, 1, 0, 0), True),
        (_tpe(2026, 10, 1, 5, 0), True),
        (_tpe(2026, 10, 1, 5, 1), False),
        # 周五夜盘延续到周六凌晨;周六白天、周日凌晨都不交易
        (_tpe(2026, 10, 3, 3, 0), True),
        (_tpe(2026, 10, 3, 6, 0), False),
        (_tpe(2026, 10, 3, 16, 0), False),
        (_tpe(2026, 10, 4, 3, 0), False),
        # 中秋(9/25 周五休市):前一晚 9/24 照开夜盘,延续到 9/25 凌晨
        (_tpe(2026, 9, 24, 16, 0), True),
        (_tpe(2026, 9, 25, 3, 0), True),
        (_tpe(2026, 9, 25, 10, 0), False),
        (_tpe(2026, 9, 25, 16, 0), False),
        (_tpe(2026, 9, 26, 3, 0), False),
        # 9/28(孔子诞辰,周一休市):周五 9/25 休市所以周六凌晨没有夜盘;9/29 凌晨也没有
        (_tpe(2026, 9, 29, 3, 0), False),
        (_tpe(2026, 9, 29, 8, 45), True),
        # 春节前最后交易日 2/11 晚上开夜盘(实测成交约 5.5 万口),2/12 凌晨仍在交易
        (_tpe(2026, 2, 11, 20, 0), True),
        (_tpe(2026, 2, 12, 3, 0), True),
        (_tpe(2026, 2, 12, 10, 0), False),
        (_tpe(2026, 2, 12, 20, 0), False),
        (_tpe(2026, 2, 13, 3, 0), False),
    ],
)
def test_twf_is_trading_time(tw_calendar, when, expected):
    assert MARKETS[MarketCode.TWF].is_trading_time(when) is expected


def test_twf_is_trading_time_converts_timezone(tw_calendar):
    # UTC 2026-10-02 19:00 = 台北 10/3(周六)03:00,属于周五夜盘
    assert MARKETS[MarketCode.TWF].is_trading_time(datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)) is True


@pytest.mark.parametrize(
    "when, expected",
    [
        (_tpe(2026, 9, 30, 9, 0), True),
        (_tpe(2026, 9, 30, 13, 30), True),
        (_tpe(2026, 9, 30, 13, 31), False),
        (_tpe(2026, 9, 30, 20, 0), False),
        (_tpe(2026, 10, 3, 3, 0), False),
    ],
)
def test_tw_stock_sessions_unchanged(tw_calendar, when, expected):
    assert MARKETS[MarketCode.TW].is_trading_time(when) is expected


def test_twf_without_calendar_degrades_to_weekend_rule():
    # 日历拉不到:与 TW 相同,只判周末;夜盘跨午夜规则仍成立
    md = MARKETS[MarketCode.TWF]
    assert md.is_trading_time(_tpe(2026, 9, 25, 10, 0)) is True  # 不知道是中秋
    assert md.is_trading_time(_tpe(2026, 10, 3, 3, 0)) is True
    assert md.is_trading_time(_tpe(2026, 10, 4, 3, 0)) is False


# ---------------------------------------------------------------- 结算日


@pytest.mark.parametrize(
    "year, month, expected",
    [
        (2026, 1, date(2026, 1, 21)),
        (2026, 2, date(2026, 2, 23)),  # 第三个周三 2/18 在春节内,顺延到下一个交易日
        (2026, 6, date(2026, 6, 17)),
        (2026, 9, date(2026, 9, 16)),
        (2026, 10, date(2026, 10, 21)),
    ],
)
def test_futures_settlement_date(tw_calendar, year, month, expected):
    assert tc.futures_settlement_date(year, month) == expected


def test_futures_settlement_date_without_calendar_is_third_wednesday():
    assert tc.futures_settlement_date(2026, 2) == date(2026, 2, 18)


# ---------------------------------------------------------------- 市场状态


def _status(code, now):
    from src.modules.market.api.stocks import build_market_status

    return build_market_status(MARKETS[code], now)


@pytest.mark.parametrize(
    "code, when, status",
    [
        (MarketCode.TWF, _tpe(2026, 10, 3, 3, 0), "trading"),      # 周六凌晨夜盘
        (MarketCode.TWF, _tpe(2026, 10, 3, 6, 0), "closed"),       # 周六白天
        (MarketCode.TWF, _tpe(2026, 9, 30, 14, 0), "break"),       # 日盘与夜盘之间
        (MarketCode.TWF, _tpe(2026, 9, 30, 7, 0), "pre_market"),
        (MarketCode.TWF, _tpe(2026, 9, 25, 3, 0), "trading"),      # 休市日凌晨仍是前一晚夜盘
        (MarketCode.TWF, _tpe(2026, 9, 25, 10, 0), "closed"),      # 中秋休市
        (MarketCode.TW, _tpe(2026, 9, 25, 10, 0), "closed"),       # 台股休市日不能显示「盘中休息」
        (MarketCode.TW, _tpe(2026, 9, 30, 8, 0), "pre_market"),
        (MarketCode.TW, _tpe(2026, 9, 30, 10, 0), "trading"),
        (MarketCode.TW, _tpe(2026, 9, 30, 14, 0), "after_hours"),
        (MarketCode.TW, _tpe(2026, 10, 3, 10, 0), "closed"),
    ],
)
def test_build_market_status(tw_calendar, code, when, status):
    result = _status(code, when)
    assert result["status"] == status
    assert result["is_trading"] is (status == "trading")
    assert result["code"] == code.value
    assert result["local_time"] == when.astimezone(TPE).strftime("%H:%M")


def test_market_status_lists_twf_sessions(tw_calendar):
    result = _status(MarketCode.TWF, _tpe(2026, 9, 30, 10, 0))
    assert result["sessions"] == ["08:45-13:45", "15:00-05:00"]
