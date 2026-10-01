"""台股盘后热门股票，数据来自 TWSE/TPEx 官方开放资料。"""

from marketdata.vendors import tw_bulk


_TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
_TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"


def _change_pct(close, change) -> float:
    price = tw_bulk.number(close)
    delta = tw_bulk.number(change) or 0.0
    if price is None or price == delta:
        return 0.0
    return delta / (price - delta) * 100


def _row(symbol, name, close, change, turnover, volume) -> dict | None:
    code = str(symbol or "").strip().upper()
    price = tw_bulk.number(close)
    if not tw_bulk.valid_code(code) or price is None:
        return None
    return {
        "symbol": code,
        "name": str(name or code).strip(),
        "market": "TW",
        "price": price,
        "change_pct": _change_pct(close, change),
        "turnover": tw_bulk.number(turnover) or 0.0,
        "volume": tw_bulk.number(volume) or 0.0,
    }


def tw_hot_stocks(mode: str, limit: int) -> list[dict]:
    """取得台股收盘后热门榜；mode 支持 turnover/gainers。"""
    if mode not in ("turnover", "gainers"):
        raise ValueError(f"不支持的 mode: {mode}")
    rows: list[dict] = []
    for raw in tw_bulk.get_json(_TWSE_URL):
        item = _row(
            raw.get("Code"), raw.get("Name"), raw.get("ClosingPrice"),
            raw.get("Change"), raw.get("TradeValue"), raw.get("TradeVolume"),
        )
        if item:
            rows.append(item)
    for raw in tw_bulk.get_json(_TPEX_URL):
        item = _row(
            raw.get("SecuritiesCompanyCode"), raw.get("CompanyName"), raw.get("Close"),
            raw.get("Change"), raw.get("TransactionAmount"), raw.get("TradingShares"),
        )
        if item:
            rows.append(item)
    key = "turnover" if mode == "turnover" else "change_pct"
    rows.sort(key=lambda item: item[key], reverse=True)
    return rows[: max(1, min(int(limit), 100))]
