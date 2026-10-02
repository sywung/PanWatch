"""台湾期货转仓提醒。"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from src.platform.marketdata import futures as futures_mod
from src.platform.marketdata.models import MarketCode
from src.platform.notifications.notifier import NotifierManager
from src.platform.persistence.database import SessionLocal
from src.platform.persistence.models import AppSettings, FuturesPosition, NotifyChannel
from src.platform.scheduling import trading_calendar
from src.platform.language import resolve_report_language

logger = logging.getLogger(__name__)

DEDUP_KEY = "futures_rollover_notified"
_TAIPEI = ZoneInfo("Asia/Taipei")
_CONTRACT_MONTH_RE = re.compile(r"^\d{6}$")


def trading_days_until(today: date, settlement: date) -> int:
    """统计今天之后(不含)到结算日(含)的台股交易日数。"""
    if settlement <= today:
        return 0
    days = 0
    current = today + timedelta(days=1)
    while current <= settlement:
        if trading_calendar.is_trading_day(MarketCode.TW, current):
            days += 1
        current += timedelta(days=1)
    return days


def reminder_kind(today: date, settlement: date) -> str | None:
    """返回结算前三个交易日或结算日的提醒种类。"""
    if today == settlement:
        return "settlement_day"
    if today < settlement and trading_days_until(today, settlement) == 3:
        return "three_days"
    return None


def _read_dedup_records(db: Session) -> tuple[AppSettings | None, dict[str, str]]:
    setting = db.query(AppSettings).filter(AppSettings.key == DEDUP_KEY).first()
    if setting is None or not setting.value:
        return setting, {}
    try:
        records = json.loads(setting.value)
    except (TypeError, ValueError):
        logger.warning("期货转仓提醒去重记录格式无效，将重新建立")
        return setting, {}
    if not isinstance(records, dict):
        logger.warning("期货转仓提醒去重记录格式无效，将重新建立")
        return setting, {}
    return setting, {str(key): str(value) for key, value in records.items()}


def _valid_contract_month(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str) or not _CONTRACT_MONTH_RE.fullmatch(value):
        return None
    year, month = int(value[:4]), int(value[4:])
    if year < 1 or not 1 <= month <= 12:
        return None
    return year, month


async def _send(db: Session, title: str, content: str) -> bool:
    """向所有启用的默认通知渠道发送一条提醒。"""
    try:
        channels = (
            db.query(NotifyChannel)
            .filter(NotifyChannel.enabled == True, NotifyChannel.is_default == True)
            .all()
        )
        if not channels:
            logger.warning("期货转仓提醒未发送：没有启用中的默认通知渠道")
            return False

        try:
            notifier = NotifierManager(language=resolve_report_language(db))
        except TypeError:
            notifier = NotifierManager()
        for channel in channels:
            notifier.add_channel(channel.type, channel.config or {})

        result = await notifier.notify_with_result(title, content)
        if isinstance(result, dict) and result.get("success"):
            return True
        reason = "notify_failed"
        if isinstance(result, dict):
            reason = str(result.get("error") or result.get("skipped") or reason)
        logger.warning("期货转仓提醒发送失败：%s", reason)
        return False
    except Exception as exc:
        logger.warning("期货转仓提醒发送失败：%s", exc)
        return False


async def run_rollover_check(
    *, now: datetime | None = None, db: Session | None = None
) -> dict:
    """检查持仓并将本轮所有需要的转仓提醒合并为一则通知。"""
    owns_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        if now is None:
            current_time = datetime.now(_TAIPEI)
        elif now.tzinfo is None:
            current_time = now.replace(tzinfo=_TAIPEI)
        else:
            current_time = now.astimezone(_TAIPEI)
        today = current_time.date()

        if not trading_calendar.is_trading_day(MarketCode.TW, today):
            return {"sent": 0, "skipped": "non_trading_day"}

        positions = db.query(FuturesPosition).all()
        setting, dedup_records = _read_dedup_records(db)
        english = resolve_report_language(db) == "en-US"
        reminder_lines: list[str] = []
        pending_keys: list[str] = []

        for position in positions:
            parsed_month = _valid_contract_month(position.contract_month)
            if parsed_month is None:
                logger.warning("跳过无效期货合约月份：position_id=%s", position.id)
                continue
            year, month = parsed_month
            try:
                settlement = trading_calendar.futures_settlement_date(year, month)
                kind = reminder_kind(today, settlement)
            except Exception as exc:
                logger.warning("跳过无法解析的期货持仓 position_id=%s：%s", position.id, exc)
                continue
            if kind is None:
                continue

            dedup_key = f"{position.id}:{position.contract_month}:{kind}"
            if dedup_key in dedup_records:
                continue
            try:
                product = futures_mod.get_futures_product(position.product_code)
                contract_code = (
                    f"{position.product_code}{futures_mod.contract_month_code(year, month)}"
                )
            except Exception as exc:
                logger.warning("跳过无法解析的期货商品 position_id=%s：%s", position.id, exc)
                continue
            if product is None:
                logger.warning("跳过未知期货商品：position_id=%s", position.id)
                continue

            settlement_label = settlement.strftime("%m/%d")
            if english:
                direction = "Long" if position.direction == "long" else "Short"
                if kind == "three_days":
                    reminder = (
                        f"Settlement in 3 trading days ({settlement_label}); "
                        "please consider rolling over"
                    )
                else:
                    reminder = (
                        f"Settlement today ({settlement_label}); open positions "
                        "will be settled at the final settlement price"
                    )
                account_name = position.account.name if position.account else "Unknown account"
                reminder_lines.append(
                    f"{product.name} {contract_code} {direction} {position.lots} lots; "
                    f"{reminder}; {account_name}"
                )
            else:
                direction = "多" if position.direction == "long" else "空"
                if kind == "three_days":
                    reminder = f"3 个交易日后（{settlement_label}）结算，请留意转仓"
                else:
                    reminder = (
                        f"今日结算（{settlement_label}），未平仓将以最后结算价结算"
                    )
                account_name = position.account.name if position.account else "未知账户"
                reminder_lines.append(
                    f"{product.name} {contract_code} {direction} {position.lots} 口；"
                    f"{reminder}；{account_name}"
                )
            pending_keys.append(dedup_key)

        if not reminder_lines:
            return {"sent": 0, "positions": len(positions)}

        if english:
            title = "[Futures rollover]"
        else:
            title = "【期货转仓提醒】"
        content = "\n".join(reminder_lines)

        if not await _send(db, title, content):
            return {"sent": 0, "positions": len(positions)}

        cutoff = today - timedelta(days=60)
        cleaned_records: dict[str, str] = {}
        for key, sent_date in dedup_records.items():
            try:
                parsed_date = date.fromisoformat(sent_date)
            except (TypeError, ValueError):
                continue
            if parsed_date >= cutoff:
                cleaned_records[key] = parsed_date.isoformat()
        for key in pending_keys:
            cleaned_records[key] = today.isoformat()

        if setting is None:
            setting = AppSettings(
                key=DEDUP_KEY,
                value=json.dumps(cleaned_records, ensure_ascii=False),
                description="期货转仓提醒去重记录",
            )
            db.add(setting)
        else:
            setting.value = json.dumps(cleaned_records, ensure_ascii=False)
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("期货转仓提醒去重记录写入失败：%s", exc)
            return {"sent": 0, "positions": len(positions)}
        return {"sent": len(pending_keys), "positions": len(positions)}
    finally:
        if owns_db:
            db.close()
