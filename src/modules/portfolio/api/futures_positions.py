"""台湾期货持仓 API。"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.modules.portfolio.futures_positions import default_multiplier, position_metrics
from src.platform.marketdata import futures as futures_mod
from src.platform.marketdata import futures_margin as fm
from src.platform.marketdata.marketdata_client import get_market_data
from src.platform.persistence.database import get_db
from src.platform.persistence.models import Account, FuturesPosition
from src.platform.scheduling import trading_calendar
from src.web.errors import api_error

logger = logging.getLogger(__name__)
router = APIRouter()
_TAIPEI = ZoneInfo("Asia/Taipei")
_CONTRACT_MONTH_RE = re.compile(r"^\d{6}$")


class FuturesPositionCreate(BaseModel):
    account_id: int
    product_code: str
    contract_month: str
    direction: str
    lots: int
    entry_price: float
    multiplier: float | None = None
    note: str | None = None


class FuturesPositionUpdate(BaseModel):
    contract_month: str | None = None
    direction: str | None = None
    lots: int | None = None
    entry_price: float | None = None
    multiplier: float | None = None
    note: str | None = None


def _now() -> datetime:
    """返回台北时区的 naive 当前时间。"""
    return datetime.now(_TAIPEI).replace(tzinfo=None)


def _fetch_contract_quotes(symbols: list[str]) -> dict[str, float]:
    """批量获取指定月份合约报价。"""
    if not symbols:
        return {}
    try:
        quotes = get_market_data().quotes(symbols, market="TWF")
        result = {}
        for quote in quotes:
            if isinstance(quote, dict):
                symbol = quote.get("symbol")
                price = quote.get("current_price")
            else:
                symbol = getattr(quote, "symbol", None)
                price = getattr(quote, "current_price", None)
            try:
                price = float(price)
            except (TypeError, ValueError):
                continue
            if symbol in symbols and price > 0:
                result[symbol] = price
        return result
    except Exception as exc:
        logger.warning("获取期货合约报价失败: %s", exc)
        return {}


def _lookup_product(product_code: str):
    product = futures_mod.get_futures_product(product_code)
    if product is None:
        raise api_error(400, "futures_product_not_found", "期货商品不存在")
    return product


def _parse_contract_month(value: str) -> tuple[int, int]:
    if not isinstance(value, str) or not _CONTRACT_MONTH_RE.fullmatch(value):
        raise api_error(400, "invalid_contract_month", "合约月份必须为 YYYYMM 格式")
    year, month = int(value[:4]), int(value[4:])
    if year < 1 or not 1 <= month <= 12:
        raise api_error(400, "invalid_contract_month", "合约月份必须在 01 到 12 之间")
    return year, month


def _validate_contract_month(value: str) -> tuple[int, int]:
    year, month = _parse_contract_month(value)
    settlement = trading_calendar.futures_settlement_date(year, month)
    if settlement < _now().date():
        raise api_error(400, "contract_expired", "合约月份已过结算日")
    return year, month


def _validate_values(*, direction=None, lots=None, entry_price=None, multiplier=None):
    if direction is not None and direction not in {"long", "short"}:
        raise api_error(400, "invalid_direction", "方向必须为 long 或 short")
    if lots is not None and lots <= 0:
        raise api_error(400, "invalid_lots", "口数必须大于零")
    if entry_price is not None and entry_price <= 0:
        raise api_error(400, "invalid_entry_price", "开仓价格必须大于零")
    if multiplier is not None and multiplier <= 0:
        raise api_error(400, "invalid_multiplier", "契约乘数必须大于零")


def _account_or_error(db: Session, account_id: int) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if account is None:
        raise api_error(400, "account_not_found", "账户不存在")
    return account


def _contract_symbol(product_code: str, year: int, month: int) -> str:
    return f"{product_code}{futures_mod.contract_month_code(year, month)}"


def _build_position_rows(
    positions: list[FuturesPosition],
    *,
    fetch_quotes: bool = True,
    quotes: dict[str, float] | None = None,
) -> list[dict]:
    """为持仓批量补齐行情、损益、保证金和结算指标。"""
    contracts: list[tuple[FuturesPosition, object, int, int, str]] = []
    for position in positions:
        try:
            year, month = _parse_contract_month(position.contract_month)
        except HTTPException:
            # 历史脏数据仍可展示；结算日不可计算时使用空值。
            year = month = 0
        product = futures_mod.get_futures_product(position.product_code)
        symbol = (
            _contract_symbol(position.product_code, year, month)
            if year and month
            else position.product_code
        )
        contracts.append((position, product, year, month, symbol))

    if quotes is None:
        symbols = sorted({item[4] for item in contracts})
        quotes = _fetch_contract_quotes(symbols) if fetch_quotes else {}

    rows = []
    today = _now().date()
    margin_cache = {}
    for position, product, year, month, symbol in contracts:
        current_price = quotes.get(symbol)
        margin = margin_cache.get(position.product_code)
        if position.product_code not in margin_cache:
            margin = fm.get_margin(position.product_code)
            margin_cache[position.product_code] = margin
        metrics = position_metrics(
            position.direction,
            entry_price=position.entry_price,
            current_price=current_price,
            lots=position.lots,
            multiplier=position.multiplier,
            margin=margin,
        )
        settlement = (
            trading_calendar.futures_settlement_date(year, month)
            if year and month
            else None
        )
        account = position.account
        rows.append(
            {
                "id": position.id,
                "account_id": position.account_id,
                "account_name": account.name if account else None,
                "product_code": position.product_code,
                "product_name": product.name if product else position.product_code,
                "contract_month": position.contract_month,
                "contract_symbol": symbol,
                "direction": position.direction,
                "lots": position.lots,
                "entry_price": position.entry_price,
                "multiplier": position.multiplier,
                "note": position.note,
                "current_price": current_price,
                **metrics,
                "settlement_date": settlement.isoformat() if settlement else None,
                "days_to_settlement": (settlement - today).days if settlement else None,
            }
        )
    return rows


@router.post("")
def create_futures_position(data: FuturesPositionCreate, db: Session = Depends(get_db)):
    _account_or_error(db, data.account_id)
    product = _lookup_product(data.product_code)
    _validate_values(
        direction=data.direction,
        lots=data.lots,
        entry_price=data.entry_price,
        multiplier=data.multiplier,
    )
    _validate_contract_month(data.contract_month)
    multiplier = data.multiplier if data.multiplier is not None else default_multiplier(product)
    position = FuturesPosition(
        account_id=data.account_id,
        product_code=data.product_code,
        contract_month=data.contract_month,
        direction=data.direction,
        lots=data.lots,
        entry_price=data.entry_price,
        multiplier=multiplier,
        note=data.note,
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return _build_position_rows([position])[0]


@router.put("/{position_id}")
def update_futures_position(
    position_id: int, data: FuturesPositionUpdate, db: Session = Depends(get_db)
):
    position = db.query(FuturesPosition).filter(FuturesPosition.id == position_id).first()
    if position is None:
        raise api_error(404, "futures_position_not_found", "期货持仓不存在")
    product = _lookup_product(position.product_code)
    values = data.model_dump(exclude_unset=True)
    if values.get("contract_month") is not None:
        _validate_contract_month(values["contract_month"])
    _validate_values(
        direction=values.get("direction"),
        lots=values.get("lots"),
        entry_price=values.get("entry_price"),
        multiplier=values.get("multiplier"),
    )
    for field, value in values.items():
        if value is not None or field == "note":
            setattr(position, field, value)
    # 兼容旧记录中为空的乘数，同时让显式更新为 None 时恢复商品默认值。
    if position.multiplier is None:
        position.multiplier = default_multiplier(product)
    db.commit()
    db.refresh(position)
    return _build_position_rows([position])[0]


@router.delete("/{position_id}")
def delete_futures_position(position_id: int, db: Session = Depends(get_db)):
    position = db.query(FuturesPosition).filter(FuturesPosition.id == position_id).first()
    if position is None:
        raise api_error(404, "futures_position_not_found", "期货持仓不存在")
    db.delete(position)
    db.commit()
    return {"success": True}


@router.get("")
def list_futures_positions(account_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(FuturesPosition)
    if account_id is not None:
        query = query.filter(FuturesPosition.account_id == account_id)
    positions = query.order_by(
        FuturesPosition.account_id.asc(), FuturesPosition.id.asc()
    ).all()
    return _build_position_rows(positions)


@router.get("/options")
def futures_position_options(product_code: str):
    product = futures_mod.get_futures_product(product_code)
    if product is None:
        raise api_error(404, "futures_product_not_found", "期货商品不存在")
    months = []
    year, month = futures_mod.near_month(_now())
    for _ in range(3):
        settlement = trading_calendar.futures_settlement_date(year, month)
        months.append(
            {
                "contract_month": f"{year:04d}{month:02d}",
                "contract_symbol": _contract_symbol(product_code, year, month),
                "settlement_date": settlement.isoformat(),
            }
        )
        month += 1
        if month == 13:
            year += 1
            month = 1
    return {
        "product_code": product.code,
        "product_name": product.name,
        "multiplier": default_multiplier(product),
        "months": months,
    }
