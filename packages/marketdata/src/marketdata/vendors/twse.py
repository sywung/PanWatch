"""台湾证交所 MIS 实时行情 vendor。"""

from __future__ import annotations

import re

from marketdata.http import market_get
from marketdata.symbol import Symbol
from marketdata.types import Quote
from marketdata.vendors.base import QuoteVendor

_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
_CODE_RE = re.compile(r"^\d{4,6}[A-Z]?$")


def _number(value) -> float | None:
    try:
        text = str(value or "").strip()
        if not text or text == "-":
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


class TwseMisQuoteVendor(QuoteVendor):
    name = "twse"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Quote]:
        codes = []
        for sym in symbols:
            code = sym.code.strip().upper()
            if _CODE_RE.fullmatch(code) and code not in codes:
                codes.append(code)
        if not codes:
            return []

        out: list[Quote] = []
        for start in range(0, len(codes), 10):
            batch = codes[start:start + 10]
            channels = [f"{ex}_{code}.tw" for code in batch for ex in ("tse", "otc")]
            payload = market_get(
                _URL,
                host_key="mis.twse.com.tw",
                params={"ex_ch": "|".join(channels), "json": "1", "delay": "0"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
                parse="json",
                log_label="TWSE MIS行情",
            )
            rows = payload.get("msgArray") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or not str(row.get("c") or "").strip():
                    continue
                code = str(row.get("c")).strip()
                prev = _number(row.get("y"))
                price = _number(row.get("z"))
                if price is None:
                    for bid in str(row.get("b") or "").split("_"):
                        candidate = _number(bid)
                        if candidate is not None and candidate > 0:
                            price = candidate
                            break
                if price is None:
                    if prev is None:
                        continue  # 无成交、无委买、无昨收:没有可用价格
                    price = prev
                change = price - prev if prev is not None else 0.0
                change_pct = change / prev * 100 if prev else 0.0
                out.append(Quote(
                    symbol=code, market="TW", name=str(row.get("n") or ""),
                    current_price=price, prev_close=prev,
                    open_price=_number(row.get("o")), high_price=_number(row.get("h")),
                    low_price=_number(row.get("l")), volume=_number(row.get("v")),
                    change_amount=change, change_pct=change_pct,
                ))
        return out
