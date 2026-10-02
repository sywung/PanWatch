"""Phase 2b B4:期货转仓提醒。

规则(vault projects/panwatch/phase2-plan.md「Phase 2b」):
- 结算前剩 3 个交易日那天、以及结算日当天,各推播一次
- 剩余交易日 = 今天之后(不含)到结算日(含)之间的台股交易日数;周末/假日不算
- 去重:同一持仓 × 合约月份 × 种类只推一次(持久化,重启/重跑不重复)
- 只在台股交易日执行;一次推一则,列出所有需要转仓的部位
- 排程挂在价格提醒调度器:交易日 08:45 与 12:30(后者补跑漏掉的早上)
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.platform.persistence.models  # noqa: F401
from src.modules.portfolio import futures_rollover as fr
from src.platform.marketdata import futures as futures_mod
from src.platform.marketdata.futures import FuturesProduct
from src.platform.persistence.database import Base
from src.platform.persistence.models import Account, AppSettings, FuturesPosition
from src.platform.scheduling import trading_calendar

PRODUCTS = {
    "CDF": FuturesProduct("CDF", "台積電期貨", "stock", "CDF", "2330", False),
    "MXF": FuturesProduct("MXF", "小台指", "index", "MTX", None, False),
}
HOLIDAYS = {date(2026, 10, 9), date(2026, 10, 10)}  # 国庆连假(10/9 补假、10/10 周六)


def _third_wednesday(year: int, month: int) -> date:
    d = date(year, month, 15)
    while d.weekday() != 2:
        d = d.replace(day=d.day + 1)
    return d


def _is_trading_day(market, d=None) -> bool:
    d = d.date() if isinstance(d, datetime) else d
    return d.weekday() < 5 and d not in HOLIDAYS


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(trading_calendar, "futures_settlement_date", _third_wednesday)
    monkeypatch.setattr(trading_calendar, "is_trading_day", _is_trading_day)
    monkeypatch.setattr(futures_mod, "get_futures_product", lambda code: PRODUCTS.get(code))
    with sessionmaker(bind=engine)() as session:
        acc = Account(name="主帳戶", available_funds=0)
        session.add(acc)
        session.commit()
        session.account_id = acc.id
        yield session
    engine.dispose()


def _add(db, code="CDF", month="202610", direction="long", lots=2):
    pos = FuturesPosition(account_id=db.account_id, product_code=code, contract_month=month,
                          direction=direction, lots=lots, entry_price=2500.0, multiplier=2000)
    db.add(pos)
    db.commit()
    return pos


@pytest.fixture
def sent(monkeypatch):
    out = []

    async def fake_send(db, title, content):
        out.append((title, content))
        return True

    monkeypatch.setattr(fr, "_send", fake_send)
    return out


def _run(db, when):
    return asyncio.run(fr.run_rollover_check(now=when, db=db))


# ============================================================
# 1. 剩余交易日
# ============================================================

def test_trading_days_until_counts_after_today_through_settlement():
    """10/21(三)结算:10/16(五)之后的交易日为 19、20、21 → 3。"""
    assert fr.trading_days_until(date(2026, 10, 16), date(2026, 10, 21)) == 3


def test_trading_days_until_skips_weekends_and_holidays(monkeypatch):
    monkeypatch.setattr(trading_calendar, "is_trading_day", _is_trading_day)
    # 10/7(三)之后:10/8 交易、10/9 假、10/10 六、10/11 日、10/12 交易 → 到 10/12 为 2
    assert fr.trading_days_until(date(2026, 10, 7), date(2026, 10, 12)) == 2


def test_trading_days_until_settlement_day_is_zero():
    assert fr.trading_days_until(date(2026, 10, 21), date(2026, 10, 21)) == 0


@pytest.mark.parametrize("today,kind", [
    (date(2026, 10, 16), "three_days"),
    (date(2026, 10, 21), "settlement_day"),
    (date(2026, 10, 19), None),   # 剩 2 天
    (date(2026, 10, 15), None),   # 剩 4 天
    (date(2026, 10, 22), None),   # 已过结算
])
def test_reminder_kind(today, kind, monkeypatch):
    monkeypatch.setattr(trading_calendar, "is_trading_day", _is_trading_day)
    assert fr.reminder_kind(today, date(2026, 10, 21)) == kind


# ============================================================
# 2. 执行与推播
# ============================================================

def test_three_days_before_sends_one_message_listing_positions(db, sent):
    _add(db)
    _add(db, code="MXF", direction="short", lots=1)
    out = _run(db, datetime(2026, 10, 16, 8, 45))
    assert out["sent"] == 2
    assert len(sent) == 1
    title, content = sent[0]
    assert "转仓" in title or "轉倉" in title
    assert "台積電期貨" in content and "CDFJ6" in content
    assert "小台指" in content and "MXFJ6" in content
    assert "10/21" in content


def test_settlement_day_message(db, sent):
    _add(db)
    _run(db, datetime(2026, 10, 21, 8, 45))
    assert len(sent) == 1
    assert "今日结算" in sent[0][1] or "今日結算" in sent[0][1]


def test_no_reminder_on_other_days(db, sent):
    _add(db)
    out = _run(db, datetime(2026, 10, 19, 8, 45))
    assert out["sent"] == 0 and sent == []


def test_not_run_on_non_trading_day(db, sent):
    _add(db)
    out = _run(db, datetime(2026, 10, 17, 8, 45))  # 周六
    assert out.get("skipped") == "non_trading_day"
    assert sent == []


def test_dedup_across_runs_and_persisted(db, sent):
    """同一天跑两次(08:45、12:30)只推一次;去重记录存在 app_settings。"""
    _add(db)
    _run(db, datetime(2026, 10, 16, 8, 45))
    _run(db, datetime(2026, 10, 16, 12, 30))
    assert len(sent) == 1
    assert db.query(AppSettings).filter(AppSettings.key == fr.DEDUP_KEY).count() == 1


def test_settlement_day_still_sent_after_three_day_reminder(db, sent):
    """三天前推过不影响结算日当天的提醒(种类不同)。"""
    _add(db)
    _run(db, datetime(2026, 10, 16, 8, 45))
    _run(db, datetime(2026, 10, 21, 8, 45))
    assert len(sent) == 2


def test_failed_send_is_not_marked_sent(db, monkeypatch):
    """推播失败不记去重,下一轮(12:30)会重试。"""
    _add(db)
    calls = []

    async def failing(db_, title, content):
        calls.append(1)
        return len(calls) > 1  # 第一次失败、第二次成功

    monkeypatch.setattr(fr, "_send", failing)
    _run(db, datetime(2026, 10, 16, 8, 45))
    _run(db, datetime(2026, 10, 16, 12, 30))
    assert len(calls) == 2


def test_new_month_position_gets_its_own_reminder(db, sent):
    """转仓后新月份的持仓(不同 contract_month)下个月仍会提醒。"""
    _add(db, month="202610")
    _run(db, datetime(2026, 10, 16, 8, 45))
    _add(db, month="202611")
    _run(db, datetime(2026, 11, 13, 8, 45))   # 11/18 结算,11/13(五)之后 16、17、18 → 3
    assert len(sent) == 2
    assert "CDFK6" in sent[1][1]


# ============================================================
# 3. 排程
# ============================================================

def test_scheduler_registers_rollover_jobs():
    from src.modules.market.price_alert_scheduler import PriceAlertScheduler

    s = PriceAlertScheduler(timezone="Asia/Taipei")
    s.register_jobs()
    ids = {job.id for job in s.scheduler.get_jobs()}
    assert {"futures_rollover_morning", "futures_rollover_noon"} <= ids
    morning = s.scheduler.get_job("futures_rollover_morning").trigger
    assert "hour='8'" in str(morning) and "minute='45'" in str(morning)
    assert "day_of_week='mon-fri'" in str(morning)
