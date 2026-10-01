"""Fugle 富果即時行情 vendor。"""

from __future__ import annotations

from marketdata.http import market_get
from marketdata.symbol import Symbol
from marketdata.types import Quote
from marketdata.vendors.base import QuoteVendor


def _number(value) -> float | None:
    try:
        if value is None or str(value).strip() in {"", "-"}:
            return None
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


class FugleQuoteVendor(QuoteVendor):
    """Fugle 股票即時行情 vendor。"""

    name = "fugle"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Quote]:
        api_key = str(config.get("api_key") or "").strip()
        if not api_key:
            return []

        out = []
        for symbol in symbols:
            code = symbol.code.strip().upper()
            payload = market_get(
                f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{code}",
                host_key="api.fugle.tw",
                headers={"X-API-KEY": api_key},
                parse="json",
                log_label="Fugle行情",
            )
            if not isinstance(payload, dict):
                continue
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            current = _number(data.get("lastPrice"))
            if current is None:
                current = _number(data.get("closePrice"))
            if current is None:
                continue
            trade = data.get("total") if isinstance(data.get("total"), dict) else {}
            reference = _number(data.get("referencePrice"))
            if reference is None:
                reference = _number(data.get("previousClose"))
            out.append(Quote(
                symbol=code,
                market="TW",
                name=str(data.get("name") or ""),
                current_price=current,
                prev_close=reference,
                open_price=_number(data.get("openPrice")),
                high_price=_number(data.get("highPrice")),
                low_price=_number(data.get("lowPrice")),
                change_amount=_number(data.get("change")),
                change_pct=_number(data.get("changePercent")),
                volume=_number(trade.get("tradeVolume")),
            ))
        return out
