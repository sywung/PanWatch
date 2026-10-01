"""台湾期货分析所需的合约、现货与价差脉络。"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from marketdata.http import market_post

from src.platform.marketdata import futures
from src.platform.scheduling import trading_calendar

_SPOT_URL = "https://mis.taifex.com.tw/futures/api/getQuoteDetail"
_TAIPEI = ZoneInfo("Asia/Taipei")
_CONTRACT_RE = re.compile(r"^([A-Z][A-Z0-9]{2})([A-L])(\d)$")
_MONTH_CODES = "ABCDEFGHIJKL"


def _quote_value(quote, key: str):
    if isinstance(quote, dict):
        return quote.get(key)
    getter = getattr(quote, "get", None)
    if callable(getter):
        value = getter(key)
        if value is not None:
            return value
    return getattr(quote, key, None)


def _number(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _local_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(_TAIPEI)
    if now.tzinfo is None:
        return now.replace(tzinfo=_TAIPEI)
    return now.astimezone(_TAIPEI)


def _contract_month(contract: str, now: datetime) -> tuple[int, int] | None:
    match = _CONTRACT_RE.fullmatch(contract.upper())
    if not match:
        return None
    month = _MONTH_CODES.index(match.group(2)) + 1
    year = now.year // 10 * 10 + int(match.group(3))
    if year < now.year - 5:
        year += 10
    elif year > now.year + 5:
        year -= 10
    return year, month


def _spot_time(value) -> str | None:
    raw = str(value or "").strip()
    if re.fullmatch(r"\d{6}", raw):
        return f"{raw[:2]}:{raw[2:4]}:{raw[4:]}"
    if re.fullmatch(r"\d{2}:\d{2}:\d{2}", raw):
        return raw
    return None


def fetch_spot_prices(codes) -> dict[str, tuple[float, str]]:
    """从期交所 MIS 批量读取标的现货价及其行情时间。"""
    try:
        requested = list(dict.fromkeys(str(code).strip().upper() for code in codes if str(code).strip()))
        if not requested:
            return {}
        ids = [f"{code}-S" for code in requested]
        payload = market_post(
            _SPOT_URL,
            host_key="mis.taifex.com.tw",
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
            json_body={"SymbolID": ids},
            parse="json",
            log_label="期交所 MIS 現貨行情",
        )
        if not isinstance(payload, dict) or payload.get("RtCode") not in (0, "0"):
            return {}
        data = payload.get("RtData")
        rows = data.get("QuoteList") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return {}

        wanted = {symbol_id: code for code, symbol_id in zip(requested, ids)}
        prices = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = wanted.get(row.get("SymbolID"))
            price = _number(row.get("CLastPrice"))
            stamp = _spot_time(row.get("CTime"))
            if code and price is not None and price > 0 and stamp:
                prices[code] = (price, stamp)
        return prices
    except Exception:
        return {}


def build_futures_context(code, quote, now: datetime | None = None) -> dict | None:
    """组合连续期货报价、实际合约、结算日与标的现货价差。"""
    normalized = str(code or "").strip().upper()
    product = futures.get_futures_product(normalized)
    if product is None:
        return None

    current = _local_now(now)
    contract_value = _quote_value(quote, "contract")
    if contract_value:
        contract = str(getattr(contract_value, "symbol", contract_value)).strip().upper()
        parsed = _contract_month(contract, current)
        if parsed is None or not contract.startswith(normalized):
            return None
        year, month = parsed
    else:
        resolved = futures.resolve_contract(normalized, current)
        if resolved is None:
            return None
        contract = resolved.symbol
        year, month = resolved.year, resolved.month

    settlement = trading_calendar.futures_settlement_date(year, month)
    spot_row = fetch_spot_prices([normalized]).get(normalized)
    spot, spot_time = spot_row if spot_row else (None, None)
    futures_price = _number(_quote_value(quote, "current_price"))
    basis = round(futures_price - spot, 2) if futures_price is not None and spot else None
    basis_pct = basis / spot * 100 if basis is not None else None

    return {
        "code": normalized,
        "name": product.name,
        "kind": product.kind,
        "underlying_code": product.underlying_code,
        "contract": contract,
        "contract_month": f"{year:04d}{month:02d}",
        "settlement_date": settlement,
        "days_to_settlement": (settlement - current.date()).days,
        "session": _quote_value(quote, "session"),
        "futures_price": futures_price,
        "spot": spot,
        "spot_time": spot_time,
        "basis": basis,
        "basis_pct": basis_pct,
    }


def format_futures_context(ctx: dict | None, language: str) -> list[str]:
    """将期货脉络格式化为提示词数据行。"""
    if not ctx:
        return []
    is_zh = language.startswith("zh")
    settlement = ctx["settlement_date"].isoformat()
    days = ctx["days_to_settlement"]
    price = ctx.get("futures_price")
    spot = ctx.get("spot")
    basis = ctx.get("basis")
    pct = ctx.get("basis_pct")
    lines = []

    if is_zh:
        lines.append(f"期貨合約：{ctx['contract']}（結算日 {settlement}，剩餘 {days} 天）")
        lines.append(f"期貨價格：{price:.2f}" if price is not None else "期貨價格：暫無")
        if spot is None:
            lines.append("標的現貨：暫無，價差資料無法計算")
        else:
            lines.append(f"標的現貨（日盤）：{spot:.2f}，行情時間 {ctx['spot_time']}")
            label = "正價差" if basis > 0 else "逆價差" if basis < 0 else "平價"
            lines.append(f"價差（期貨−現貨）：{basis:+.2f}（{label}，{pct:+.3f}%）")
        if ctx.get("session") == "night":
            lines.append("目前為夜盤；現貨為日盤收盤價，請留意行情時間差。")
    else:
        lines.append(f"Futures contract: {ctx['contract']} (settlement {settlement}, {days} days remaining)")
        lines.append(f"Futures price: {price:.2f}" if price is not None else "Futures price: unavailable")
        if spot is None:
            lines.append("Underlying spot: unavailable; basis cannot be calculated")
        else:
            lines.append(f"Underlying spot (day session): {spot:.2f} at {ctx['spot_time']}")
            label = "contango" if basis > 0 else "backwardation" if basis < 0 else "at parity"
            lines.append(f"Basis (futures − spot): {basis:+.2f} ({label}, {pct:+.3f}%)")
        if ctx.get("session") == "night":
            lines.append("Night session: spot is the day-session close; account for the timestamp difference.")
    return lines


def futures_prompt_note(watchlist, language: str) -> str:
    """为含期货标的的分析提示词补充适用的市场规则。"""
    has_futures = False
    for item in watchlist or []:
        market = item.get("market") if isinstance(item, dict) else getattr(item, "market", None)
        if getattr(market, "value", market) == "TWF":
            has_futures = True
            break
    if not has_futures:
        return ""
    if language.startswith("zh"):
        return (
            "\n期貨分析說明：標的是台灣期貨近月連續合約；價差＝期貨−現貨，正值為正價差、"
            "負值為逆價差，臨近每月第三個星期三的結算日價差會收斂。日盤 08:45–13:45，"
            "夜盤 15:00–05:00。期貨不適用三大法人買賣超、融資融券、本益比等股票指標；"
            "期貨可做空且具有槓桿，請將槓桿與風險納入分析。\n"
        )
    return (
        "\nFutures analysis: symbols are Taiwan near-month continuous futures. Basis = futures minus spot; "
        "positive basis is contango and negative basis is backwardation. Basis converges near the monthly "
        "third-Wednesday settlement. Day session: 08:45–13:45; night session: 15:00–05:00 (Taipei time). "
        "Stock indicators such as institutional flows, margin trading, short selling balances, and P/E do not "
        "apply. Futures can be shorted and are leveraged; account for leverage and risk.\n"
    )
