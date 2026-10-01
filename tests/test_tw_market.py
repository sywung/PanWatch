"""台股(TW)市场定义、交易日历、默认市场/计价币别常量、数据源种子。"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from src.platform.marketdata import models as market_models
from src.platform.marketdata.models import MARKETS, MarketCode
from src.platform.scheduling import trading_calendar as tc

TPE = ZoneInfo("Asia/Taipei")

# TWSE openapi holidaySchedule 的真实 2026 切片(民国年日期)。
# 注意「开始交易日」「最后交易日」也在清单里,但那两天是开市的。
_RAW_TW_HOLIDAYS = [
    {"Name": "中華民國開國紀念日", "Date": "1150101", "Weekday": "四", "Description": "依規定放假1日。"},
    {"Name": "國曆新年開始交易日", "Date": "1150102", "Weekday": "五", "Description": "國曆新年開始交易。"},
    {"Name": "農曆春節前最後交易日", "Date": "1150211", "Weekday": "三", "Description": "農曆春節前最後交易。<br>"},
    {"Name": "市場無交易，僅辦理結算交割作業", "Date": "1150212", "Weekday": "四", "Description": ""},
    {"Name": "農曆除夕及春節", "Date": "1150216", "Weekday": "一", "Description": "依規定於2月15日至2月19日放假5日。"},
    {"Name": "農曆春節後開始交易日", "Date": "1150223", "Weekday": "一", "Description": "農曆春節後開始交易。"},
    {"Name": "和平紀念日", "Date": "1150227", "Weekday": "五", "Description": "於2月27日（星期五）補假。"},
    {"Name": "中秋節", "Date": "1150925", "Weekday": "五", "Description": "依規定放假1日。"},
    {"Name": "國慶日", "Date": "1151009", "Weekday": "五", "Description": "於10月9日（星期五）補假。"},
    {"Name": "行憲紀念日", "Date": "1151225", "Weekday": "五", "Description": "依規定放假1日。"},
]


@pytest.fixture(autouse=True)
def _reset_calendar():
    tc.reset_cache()
    yield
    tc.reset_cache()


@pytest.fixture
def tw_calendar(monkeypatch):
    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", lambda: _RAW_TW_HOLIDAYS)
    assert tc.refresh_tw_blocking() is True


# ---------------------------------------------------------------- 市场定义


def test_tw_market_definition():
    md = MARKETS[MarketCode.TW]
    assert MarketCode("TW") is MarketCode.TW
    assert md.timezone == "Asia/Taipei"
    assert [(s.start, s.end) for s in md.sessions] == [(time(9, 0), time(13, 30))]


def test_default_market_and_base_currency_constants():
    assert market_models.DEFAULT_MARKET is MarketCode.TW
    assert market_models.BASE_CURRENCY == "TWD"


def test_tw_trading_time(tw_calendar):
    md = MARKETS[MarketCode.TW]
    assert md.is_trading_time(datetime(2026, 9, 30, 10, 0, tzinfo=TPE)) is True
    assert md.is_trading_time(datetime(2026, 9, 30, 13, 30, tzinfo=TPE)) is True
    assert md.is_trading_time(datetime(2026, 9, 30, 8, 59, tzinfo=TPE)) is False
    assert md.is_trading_time(datetime(2026, 9, 30, 14, 0, tzinfo=TPE)) is False
    assert md.is_trading_time(datetime(2026, 9, 25, 10, 0, tzinfo=TPE)) is False  # 中秋


# ---------------------------------------------------------------- 日历解析


def test_parse_tw_holidays_converts_roc_dates_and_skips_trading_markers():
    closed = tc._parse_tw_holidays(_RAW_TW_HOLIDAYS)
    assert date(2026, 1, 1) in closed
    assert date(2026, 2, 12) in closed      # 市场无交易
    assert date(2026, 9, 25) in closed
    assert date(2026, 1, 2) not in closed   # 开始交易日
    assert date(2026, 2, 11) not in closed  # 最后交易日
    assert date(2026, 2, 23) not in closed


def test_parse_tw_holidays_ignores_malformed_rows():
    closed = tc._parse_tw_holidays([{"Name": "x", "Date": "abc"}, {"Name": "y"}, {"Name": "中秋節", "Date": "1150925"}])
    assert closed == frozenset({date(2026, 9, 25)})


# ---------------------------------------------------------------- 交易日判断


def test_tw_weekday_holiday_is_closed(tw_calendar):
    assert tc.is_trading_day(MarketCode.TW, date(2026, 9, 25)) is False
    assert tc.is_trading_day("TW", date(2026, 10, 9)) is False
    assert tc.is_trading_day("TW", date(2026, 2, 12)) is False


def test_tw_trading_markers_are_open(tw_calendar):
    assert tc.is_trading_day("TW", date(2026, 2, 11)) is True
    assert tc.is_trading_day("TW", date(2026, 1, 2)) is True
    assert tc.is_trading_day("TW", date(2026, 9, 30)) is True


def test_tw_weekend_closed_without_calendar():
    assert tc.is_trading_day("TW", date(2026, 10, 3)) is False  # 周六


def test_tw_without_calendar_degrades_to_weekend_only():
    assert tc.is_trading_day("TW", date(2026, 9, 25)) is True


def test_tw_outside_covered_years_degrades_to_weekend_only(tw_calendar):
    # 清单只覆盖 2026 年;2027-01-01(周五)不在覆盖范围 → 只判周末
    assert tc.is_trading_day("TW", date(2027, 1, 1)) is True


def test_tw_calendar_not_applied_to_other_markets(tw_calendar):
    assert tc.is_trading_day("US", date(2026, 9, 25)) is True
    assert tc.is_trading_day("HK", date(2026, 10, 9)) is True


def test_tw_refresh_failure_keeps_degraded(monkeypatch):
    def _boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", _boom)
    assert tc.refresh_tw_blocking() is False
    assert tc.is_trading_day("TW", date(2026, 9, 25)) is True


def test_tw_refresh_empty_result_is_failure(monkeypatch):
    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", lambda: [])
    assert tc.refresh_tw_blocking() is False


def test_tw_async_refresh(monkeypatch):
    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", lambda: _RAW_TW_HOLIDAYS)
    assert asyncio.run(tc.refresh_tw()) is True
    assert tc.is_trading_day("TW", date(2026, 9, 25)) is False


def test_reset_cache_clears_tw(tw_calendar):
    tc.reset_cache()
    assert tc.is_trading_day("TW", date(2026, 9, 25)) is True


def test_any_market_trading_day_includes_tw(monkeypatch, tw_calendar):
    # 只有 TW 开市的情境:把其他三个市场都视为休市
    real = tc.is_trading_day
    monkeypatch.setattr(
        tc, "is_trading_day",
        lambda m, d=None: real(m, d) if str(getattr(m, "value", m)) == "TW" else False,
    )
    assert tc.any_market_trading_day(date(2026, 9, 30)) is True
    assert tc.any_market_trading_day(date(2026, 9, 25)) is False


def test_cn_refresh_does_not_touch_tw_network(monkeypatch):
    """A 股 refresh_blocking() 语义不变:不得顺带拉 TW(避免既有测试打网络)。"""
    def _forbidden():
        raise AssertionError("refresh_blocking() 不应拉取 TW 日历")

    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", _forbidden)
    monkeypatch.setattr(tc, "_fetch_cn_trading_dates", lambda: frozenset({date(2026, 9, 30)}))
    assert tc.refresh_blocking() is True


# ---------------------------------------------------------------- 数据源种子


def _seed(provider, dtype):
    import server

    rows = [s for s in server.DATA_SOURCE_SEEDS if s["provider"] == provider and s["type"] == dtype]
    assert len(rows) == 1, f"缺少种子 {dtype}/{provider}"
    return rows[0]


def test_twse_quote_seed_enabled_first():
    row = _seed("twse", "quote")
    assert row["enabled"] is True
    assert row["priority"] == 0


def test_yahoo_kline_seed_enabled_for_tw():
    assert _seed("yahoo", "kline")["enabled"] is True
