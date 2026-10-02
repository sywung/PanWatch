"""期货持仓的损益、保证金与权益计算。"""

from __future__ import annotations

from src.platform.marketdata.futures import FuturesProduct
from src.platform.marketdata.futures_margin import Margin, margin_per_lot


def default_multiplier(product: FuturesProduct) -> float:
    if product.kind == "index":
        multipliers = {"TXF": 200, "MXF": 50, "TMF": 10, "EXF": 4000, "FXF": 1000}
        try:
            return multipliers[product.code]
        except KeyError as exc:
            raise ValueError(f"unsupported index futures product: {product.code}") from exc
    if product.kind == "stock":
        is_etf = (product.underlying_code or "").startswith("00")
        if is_etf:
            return 1000 if product.is_mini else 10000
        return 100 if product.is_mini else 2000
    raise ValueError(f"unsupported futures product kind: {product.kind}")


def unrealized_pnl(
    direction: str,
    entry_price: float,
    current_price: float | None,
    lots: int,
    multiplier: float,
) -> float | None:
    if direction not in {"long", "short"}:
        raise ValueError("direction must be 'long' or 'short'")
    if current_price is None:
        return None
    sign = 1 if direction == "long" else -1
    return sign * (current_price - entry_price) * lots * multiplier


def position_metrics(
    direction: str,
    *,
    entry_price: float,
    current_price: float | None,
    lots: int,
    multiplier: float,
    margin: Margin | None,
) -> dict:
    pnl = unrealized_pnl(direction, entry_price, current_price, lots, multiplier)
    margin_used = None
    maintenance_required = None
    equity = None
    margin_call = None

    if margin is not None and (margin.kind == "fixed" or current_price is not None):
        per_lot_initial, per_lot_maintenance = margin_per_lot(
            margin, current_price, multiplier
        )
        margin_used = per_lot_initial * lots
        maintenance_required = per_lot_maintenance * lots
        if pnl is not None:
            equity = margin_used + pnl
            margin_call = equity < maintenance_required

    return {
        "unrealized_pnl": pnl,
        "margin_used": margin_used,
        "maintenance_required": maintenance_required,
        "equity": equity,
        "margin_call": margin_call,
    }
