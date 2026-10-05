"""商品 K 線圖畫線的持久化 API。"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from src.platform.marketdata.models import MarketCode
from src.platform.persistence.database import get_db
from src.platform.persistence.models import ChartDrawing
from src.web.errors import api_error

router = APIRouter()
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2}))?$")
_MAX_DRAWINGS = 200


def _invalid(code: str, message: str, status: int = 422):
    raise api_error(status, code, message)


def _normalize_symbol(value: Any) -> str:
    if not isinstance(value, str):
        _invalid("chart_drawing_symbol_invalid", "商品代碼必須是文字")
    symbol = value.strip().upper()
    if not symbol:
        _invalid("chart_drawing_symbol_required", "請輸入商品代碼")
    if len(symbol) > 32:
        _invalid("chart_drawing_symbol_too_long", "商品代碼不可超過 32 個字元")
    return symbol


def _normalize_market(value: Any) -> str:
    if not isinstance(value, str):
        _invalid("chart_drawing_market_invalid", "市場代碼無效")
    market = value.strip().upper()
    try:
        return MarketCode(market).value
    except ValueError:
        _invalid("chart_drawing_market_invalid", "市場代碼必須是系統支援的市場")


def _validate_price(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _invalid("chart_drawing_price_invalid", "價格必須是大於 0 的有限數值")
    try:
        price = float(value)
    except (OverflowError, ValueError):
        _invalid("chart_drawing_price_invalid", "價格必須是大於 0 的有限數值")
    if not math.isfinite(price) or price <= 0:
        _invalid("chart_drawing_price_invalid", "價格必須是大於 0 的有限數值")
    return price


def _validate_time(value: Any) -> str:
    if not isinstance(value, str):
        _invalid("chart_drawing_time_invalid", "時間格式必須是 YYYY-MM-DD 或 YYYY-MM-DD HH:MM")
    match = _DATE_RE.fullmatch(value)
    if not match:
        _invalid("chart_drawing_time_invalid", "時間格式必須是 YYYY-MM-DD 或 YYYY-MM-DD HH:MM")
    year, month, day, hour, minute = match.groups()
    try:
        date(int(year), int(month), int(day))
        if hour is not None:
            datetime(int(year), int(month), int(day), int(hour), int(minute))
    except ValueError:
        _invalid("chart_drawing_time_invalid", "時間不是有效的日期或時間")
    return value


def _validate_data(kind: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _invalid("chart_drawing_data_invalid", "畫線資料必須是物件")
    if kind == "hline":
        if set(value) != {"price"}:
            _invalid("chart_drawing_data_invalid", "水平線資料只接受 price 欄位")
        return {"price": _validate_price(value["price"])}
    if kind == "trend":
        if set(value) != {"p1", "p2"}:
            _invalid("chart_drawing_data_invalid", "趨勢線資料只接受 p1、p2 欄位")
        points: dict[str, dict[str, Any]] = {}
        for name in ("p1", "p2"):
            point = value[name]
            if not isinstance(point, dict) or set(point) != {"time", "price"}:
                _invalid("chart_drawing_data_invalid", "趨勢線端點只接受 time、price 欄位")
            points[name] = {
                "time": _validate_time(point["time"]),
                "price": _validate_price(point["price"]),
            }
        return points
    _invalid("chart_drawing_kind_invalid", "畫線類型必須是 hline 或 trend")


def _fields(payload: dict[str, Any], allowed: set[str], required: set[str]) -> None:
    if set(payload) - allowed:
        _invalid("chart_drawing_fields_invalid", "請求包含不支援的欄位")
    if not required <= set(payload):
        _invalid("chart_drawing_fields_invalid", "請求缺少必要欄位")


def _response(row: ChartDrawing) -> dict[str, Any]:
    return {
        "id": row.id,
        "symbol": row.symbol,
        "market": row.market,
        "kind": row.kind,
        "data": row.data,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("")
def list_chart_drawings(
    symbol: str = Query(...), market: str = Query(...), db: Session = Depends(get_db)
):
    normalized_symbol = _normalize_symbol(symbol)
    normalized_market = _normalize_market(market)
    rows = (
        db.query(ChartDrawing)
        .filter_by(symbol=normalized_symbol, market=normalized_market)
        .order_by(ChartDrawing.id)
        .all()
    )
    return [_response(row) for row in rows]


@router.post("")
def create_chart_drawing(payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    _fields(payload, {"symbol", "market", "kind", "data"}, {"symbol", "market", "kind", "data"})
    symbol = _normalize_symbol(payload["symbol"])
    market = _normalize_market(payload["market"])
    kind = payload["kind"]
    if not isinstance(kind, str) or kind not in {"hline", "trend"}:
        _invalid("chart_drawing_kind_invalid", "畫線類型必須是 hline 或 trend")
    data = _validate_data(kind, payload["data"])
    count = db.query(ChartDrawing.id).filter_by(symbol=symbol, market=market).count()
    if count >= _MAX_DRAWINGS:
        _invalid("chart_drawing_limit_reached", "每個商品最多只能儲存 200 條畫線", 400)
    row = ChartDrawing(symbol=symbol, market=market, kind=kind, data=data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _response(row)


@router.put("/{drawing_id}")
def update_chart_drawing(
    drawing_id: int, payload: dict[str, Any] = Body(...), db: Session = Depends(get_db)
):
    _fields(payload, {"data"}, {"data"})
    row = db.get(ChartDrawing, drawing_id)
    if row is None:
        _invalid("chart_drawing_not_found", "找不到這條畫線", 404)
    row.data = _validate_data(row.kind, payload["data"])
    db.commit()
    db.refresh(row)
    return _response(row)


@router.delete("/{drawing_id}")
def delete_chart_drawing(drawing_id: int, db: Session = Depends(get_db)):
    row = db.get(ChartDrawing, drawing_id)
    if row is None:
        _invalid("chart_drawing_not_found", "找不到這條畫線", 404)
    db.delete(row)
    db.commit()
    return {"deleted": 1}


@router.delete("")
def clear_chart_drawings(
    symbol: str = Query(...), market: str = Query(...), db: Session = Depends(get_db)
):
    normalized_symbol = _normalize_symbol(symbol)
    normalized_market = _normalize_market(market)
    deleted = (
        db.query(ChartDrawing)
        .filter_by(symbol=normalized_symbol, market=normalized_market)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}
