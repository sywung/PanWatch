"""本機集保股權分散快照與趨勢。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from marketdata.types import ShareholderItem
from src.platform.persistence.models import ShareholderDispersion, Stock

logger = logging.getLogger(__name__)


def fetch_shareholders(symbols: list[str]) -> list[ShareholderItem]:
    """從 marketdata 取得台股最新集保資料。"""
    from src.platform.marketdata.collectors.kline_collector import get_market_data

    return get_market_data().shareholders(symbols, market="TW")


def fetch_history_levels(symbol: str, skip_dates=()) -> list[tuple[str, list[dict]]]:
    """從 MarketData 來源鏈取得歷史週分級。"""
    from src.platform.marketdata.collectors.kline_collector import get_market_data

    return get_market_data().shareholders_history(symbol, skip_dates=skip_dates, market="TW")


def store_items(db: Session, items: list[ShareholderItem], market: str = "TW") -> int:
    """保存尚未存在且帶有分級資料的集保週快照。"""
    added = 0
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not item.report_date or not item.levels:
            continue
        key = (market, item.symbol, item.report_date)
        if key in seen:
            continue
        seen.add(key)
        exists = db.query(ShareholderDispersion.id).filter_by(
            market=market, symbol=item.symbol, data_date=item.report_date
        ).first()
        if exists:
            continue
        db.add(ShareholderDispersion(
            market=market, symbol=item.symbol, data_date=item.report_date,
            holder_num=item.holder_num, avg_shares=item.avg_shares,
            big_holder_ratio=item.big_holder_ratio,
            thousand_lot_ratio=item.thousand_lot_ratio, levels=item.levels,
        ))
        added += 1
    db.commit()
    return added


def get_history(
    db: Session, symbol: str, market: str = "TW", weeks: int = 26
) -> list[ShareholderDispersion]:
    """讀取最近週快照並依日期遞增回傳。"""
    rows = (
        db.query(ShareholderDispersion)
        .filter_by(symbol=symbol, market=market)
        .order_by(ShareholderDispersion.data_date.desc())
        .limit(weeks)
        .all()
    )
    return list(reversed(rows))


def _change(current, previous, *, ratio: bool = False):
    if current is None or previous is None:
        return None
    difference = current - previous
    return round(difference, 2) if ratio else difference


def serialize(rows: list[ShareholderDispersion]) -> dict:
    """轉換快照為 API 用的最新值與歷史序列。"""
    history = [{
        "data_date": row.data_date, "holder_num": row.holder_num,
        "avg_shares": row.avg_shares, "big_holder_ratio": row.big_holder_ratio,
        "thousand_lot_ratio": row.thousand_lot_ratio,
    } for row in rows]
    if not rows:
        return {"latest": None, "history": []}
    latest_row = rows[-1]
    previous = rows[-2] if len(rows) > 1 else None
    latest = {
        **history[-1], "levels": latest_row.levels,
        "holder_num_change": _change(
            latest_row.holder_num, previous.holder_num if previous else None
        ),
        "big_holder_ratio_change": _change(
            latest_row.big_holder_ratio,
            previous.big_holder_ratio if previous else None, ratio=True,
        ),
        "thousand_lot_ratio_change": _change(
            latest_row.thousand_lot_ratio,
            previous.thousand_lot_ratio if previous else None, ratio=True,
        ),
    }
    return {"latest": latest, "history": history}


def fetch_and_store(db: Session, symbols: list[str]) -> int:
    """抓取並保存最新快照；來源失敗記錄警告並回傳零。"""
    if not symbols:
        return 0
    try:
        items = fetch_shareholders(symbols)
    except Exception as exc:
        logger.warning("TDCC 股權分散資料抓取失敗: %s", exc, exc_info=True)
        return 0
    return store_items(db, items)


def backfill_symbol(db: Session, symbol: str, market: str = "TW") -> int:
    """補齊單一台股歷史週資料，並沿用快照表的去重與提交路徑。"""
    if market != "TW":
        return 0
    skip_dates = {
        row[0] for row in db.query(ShareholderDispersion.data_date).filter_by(
            symbol=symbol, market=market
        ).all()
    }
    try:
        history = fetch_history_levels(symbol, skip_dates=skip_dates)
    except Exception as exc:
        logger.warning("TDCC 股權分散歷史回補失敗 (%s): %s", symbol, exc, exc_info=True)
        return 0

    items = []
    for data_date, levels in history:
        if not levels:
            continue
        by_level = {
            row.get("level"): row for row in levels
            if isinstance(row, dict) and row.get("level") is not None
        }
        level_15 = by_level.get(15)
        level_17 = by_level.get(17)
        if level_15 is None or level_17 is None:
            continue
        holders = int(level_17.get("holders") or 0)
        if holders <= 0:
            continue
        big_holder_ratio = sum(
            float(by_level[level].get("pct") or 0)
            for level in (12, 13, 14, 15) if level in by_level
        )
        items.append(ShareholderItem(
            report_date=data_date,
            symbol=symbol,
            holder_num=holders,
            avg_shares=int(level_17.get("shares") or 0) / holders,
            big_holder_ratio=big_holder_ratio,
            thousand_lot_ratio=float(level_15.get("pct") or 0),
            levels=levels,
        ))
    return store_items(db, items, market=market)


def collect_watchlist(db: Session) -> int:
    """收集資料庫中所有不同的台股自選標的。"""
    symbols = [row[0] for row in db.query(Stock.symbol).filter(
        Stock.market == "TW"
    ).distinct().order_by(Stock.symbol).all()]
    added = fetch_and_store(db, symbols)
    for symbol in symbols:
        count = db.query(ShareholderDispersion.id).filter_by(
            symbol=symbol, market="TW"
        ).count()
        if count < 2:
            added += backfill_symbol(db, symbol, market="TW")
    return added


def dispersion_line_for(
    db: Session, symbol: str, market: str, language: str
) -> str:
    """只從本機快照格式化集保摘要，絕不觸發來源抓取。"""
    if market != "TW":
        return ""
    rows = get_history(db, symbol, market, weeks=2)
    payload = serialize(rows)["latest"]
    if payload is None:
        return ""
    return _format_dispersion_line(payload, language)


def _format_dispersion_line(latest: dict, language: str) -> str:
    ratio = latest["thousand_lot_ratio"]
    ratio_text = "—" if ratio is None else f"{ratio:.2f}%"
    holders = latest["holder_num"]
    holder_text = "—" if holders is None else f"{holders:,}"
    ratio_change = latest["thousand_lot_ratio_change"]
    holder_change = latest["holder_num_change"]
    if language == "en-US":
        return _english_line(latest, ratio_text, holders, holder_text, ratio_change, holder_change)
    text = _chinese_line(latest, ratio_text, holder_text, ratio_change, holder_change)
    from src.platform.language import localize_text

    localized = localize_text(text, language) or text
    # OpenCC 不會把「周」轉成「週」；台灣用字是「週」
    return localized.replace("（周 ", "（週 ") if language == "zh-TW" else localized


def _english_line(latest, ratio_text, holders, holder_text, ratio_change, holder_change):
    ratio_delta = f" (WoW {ratio_change:+.2f}pp)" if ratio_change is not None else ""
    holder_delta = f" (WoW {holder_change:+,})" if holders is not None and holder_change is not None else ""
    return (
        f"TDCC holder distribution ({latest['data_date']}): >1000-lot holders "
        f"{ratio_text}{ratio_delta}, total holders {holder_text}{holder_delta}"
    )


def _chinese_line(latest, ratio_text, holder_text, ratio_change, holder_change):
    ratio_delta = f"（周 {ratio_change:+.2f}pp）" if ratio_change is not None else ""
    holder_delta = f"（周 {holder_change:+,}）" if holder_change is not None else ""
    return (
        f"集保股权分散（{latest['data_date']}）：千张大户 {ratio_text}{ratio_delta}，"
        f"总人数 {holder_text}{holder_delta}"
    )
