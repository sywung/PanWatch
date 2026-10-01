"""台湾期货商品信息 API。"""

import asyncio

from fastapi import APIRouter

from src.platform.marketdata import futures
from src.platform.marketdata.futures_context import build_futures_context
from src.platform.marketdata.marketdata_client import md_quote_rows
from src.web.errors import api_error

router = APIRouter()


@router.get("/{code}")
async def get_futures_info(code: str) -> dict:
    """获取期货合约、结算日与标的现货价差。"""
    normalized = code.strip().upper()
    if futures.get_futures_product(normalized) is None:
        raise api_error(404, "futures_not_found", "期貨商品不存在")

    rows = await asyncio.to_thread(md_quote_rows, [normalized], "TWF")
    quote = next(
        (row for row in rows if str(row.get("symbol", "")).upper() == normalized),
        None,
    )
    info = build_futures_context(normalized, quote)
    if info is None:
        raise api_error(404, "futures_not_found", "期貨商品不存在")
    info["settlement_date"] = info["settlement_date"].isoformat()
    return info
