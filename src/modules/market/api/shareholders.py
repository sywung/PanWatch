"""台股集保股權分散表 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.modules.market import shareholder_dispersion as service
from src.platform.persistence.database import get_db
from src.web.errors import api_error

router = APIRouter()


@router.get("/dispersion")
def get_shareholder_dispersion(
    symbol: str = Query(...),
    market: str = Query("TW"),
    weeks: int = Query(26, ge=1, le=104),
    db: Session = Depends(get_db),
) -> dict:
    """回傳指定台股的最新快照與本機歷史。"""
    normalized_symbol = symbol.strip()
    if not normalized_symbol:
        raise api_error(422, "shareholder_dispersion_symbol_required", "請輸入商品代碼")
    normalized_market = market.strip().upper()
    if normalized_market != "TW":
        raise api_error(
            400,
            "shareholder_dispersion_market_unsupported",
            "集保股權分散表僅支援台股",
        )
    stored_rows = service.get_history(db, normalized_symbol, normalized_market, weeks=2)
    if len(stored_rows) < 2:
        service.fetch_and_store(db, [normalized_symbol])
        service.backfill_symbol(db, normalized_symbol, market=normalized_market)
    rows = service.get_history(db, normalized_symbol, normalized_market, weeks)
    return {
        "symbol": normalized_symbol,
        "market": normalized_market,
        **service.serialize(rows),
    }
