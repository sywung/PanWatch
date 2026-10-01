"""期交所 MIS 期货实时行情 vendor。"""

from __future__ import annotations

import math
import re

from marketdata.http import market_post
from marketdata.symbol import Symbol
from marketdata.types import Quote
from marketdata.vendors.base import QuoteVendor

_URL = "https://mis.taifex.com.tw/futures/api/getQuoteDetail"
_CONTRACT_RE = re.compile(r"^[A-Z][A-Z0-9]{2}[A-L]\d$")
_MONTH_CODES = "ABCDEFGHIJKL"


def following_contracts(contract_code: str, n: int) -> list[str]:
    """返回指定合约之后 n 个月的代码,并处理跨年。"""
    if not _CONTRACT_RE.fullmatch(contract_code) or n <= 0:
        return []
    product = contract_code[:3]
    month_index = _MONTH_CODES.index(contract_code[3])
    year_digit = int(contract_code[4])
    contracts = []
    for offset in range(1, n + 1):
        absolute_month = month_index + offset
        month = absolute_month % 12
        year = (year_digit + absolute_month // 12) % 10
        contracts.append(f"{product}{_MONTH_CODES[month]}{year}")
    return contracts


def _number(value) -> float | None:
    try:
        text = str(value if value is not None else "").strip()
        if not text or text == "-":
            return None
        number = float(text)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _contract_hits(contracts: list[str]) -> tuple[dict[str, dict], dict[str, dict], set[str]]:
    """按合约查询日夜盘。

    返回 (各合约最新一笔有效成交, 有挂牌但未成交的合约行, 请求成功的合约)。
    查不到的代号 mis 会回空行,所以「有回应但没有该合约」才代表没挂牌。
    """
    requested = {
        f"{contract}-{session_code}": (contract, session)
        for contract in contracts
        for session_code, session in (("F", "day"), ("M", "night"))
    }
    hits: dict[str, tuple[str, str, dict]] = {}
    listed: dict[str, dict] = {}
    answered: set[str] = set()
    symbol_ids = list(requested)
    for start in range(0, len(symbol_ids), 40):
        batch = symbol_ids[start:start + 40]
        payload = market_post(
            _URL,
            host_key="mis.taifex.com.tw",
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
            json_body={"SymbolID": batch},
            parse="json",
            log_label="期交所 MIS 期貨行情",
        )
        if not isinstance(payload, dict) or payload.get("RtCode") not in (0, "0"):
            continue
        data = payload.get("RtData")
        rows = data.get("QuoteList") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            continue
        answered.update(requested[symbol_id][0] for symbol_id in batch)
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol_id = row.get("SymbolID")
            if not isinstance(symbol_id, str) or not symbol_id.strip() or symbol_id not in requested:
                continue
            contract, session = requested[symbol_id]
            price = _number(row.get("CLastPrice"))
            if price is None or price <= 0:
                if session == "day" or contract not in listed:
                    listed[contract] = {**row, "_session": session}
                continue
            stamp = (str(row.get("CDate") or ""), str(row.get("CTime") or ""))
            previous = hits.get(contract)
            if previous is None or stamp > (previous[0], previous[1]):
                hits[contract] = (stamp[0], stamp[1], {**row, "_session": session})
    traded = {contract: row for contract, (_, _, row) in hits.items()}
    return traded, listed, answered


def _to_quote(symbol: str, contract: str, row: dict, *, traded: bool = True) -> Quote:
    """将 MIS 行转换为标准 Quote;当日未成交时以参考价当现价、涨跌为 0。"""
    previous = _number(row.get("CRefPrice"))
    price = _number(row.get("CLastPrice")) if traded else previous
    valid_previous = previous is not None and previous > 0
    change = price - previous if price is not None and valid_previous else None
    change_pct = change / previous * 100 if change is not None else None
    return Quote(
        symbol=symbol,
        market="TWF",
        name=str(row.get("DispCName") or ""),
        current_price=price if price is not None else 0.0,
        prev_close=previous,
        open_price=_number(row.get("COpenPrice")),
        high_price=_number(row.get("CHighPrice")),
        low_price=_number(row.get("CLowPrice")),
        volume=_number(row.get("CTotalVolume")) if traded else 0.0,
        change_amount=change,
        change_pct=change_pct,
        contract=contract,
        session=row.get("_session"),
    )


def _quote_from(code: str, contract: str, traded: dict, listed: dict) -> Quote | None:
    if contract in traded:
        return _to_quote(code, contract, traded[contract])
    if contract in listed and _number(listed[contract].get("CRefPrice")):
        return _to_quote(code, contract, listed[contract], traded=False)
    return None


class TaifexMisQuoteVendor(QuoteVendor):
    name = "taifex"
    supports_markets = {"TWF"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Quote]:
        """查询近月合约,无成交时依次搜索后续六个月份。"""
        codes = []
        for symbol in symbols:
            code = symbol.code
            if _CONTRACT_RE.fullmatch(code) and code not in codes:
                codes.append(code)
        if not codes:
            return []

        quotes_by_code: dict[str, Quote] = {}
        traded, listed, answered = _contract_hits(codes)
        for code in codes:
            quote = _quote_from(code, code, traded, listed)
            if quote is not None:
                quotes_by_code[code] = quote

        # 只有「请求成功但没有该合约」才往后找月份;网络失败时不放大请求
        unlisted = [code for code in codes if code not in quotes_by_code and code in answered]
        following = {code: following_contracts(code, 6) for code in unlisted}
        candidates = list(dict.fromkeys(contract for months in following.values() for contract in months))
        if candidates:
            later_traded, later_listed, _ = _contract_hits(candidates)
            for code in unlisted:
                for contract in following[code]:
                    quote = _quote_from(code, contract, later_traded, later_listed)
                    if quote is not None:
                        quotes_by_code[code] = quote
                        break

        return [quotes_by_code[code] for code in codes if code in quotes_by_code]
