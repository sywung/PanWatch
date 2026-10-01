"""FinMind 台股歷史日 K vendor。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from marketdata.http import market_get
from marketdata.symbol import Symbol
from marketdata.types import Bar
from marketdata.vendors.base import KlineVendor

_API_URL = "https://api.finmindtrade.com/api/v4/data"
_TAIPEI = ZoneInfo("Asia/Taipei")
_FUTURES_CODE = re.compile(r"[A-Z][A-Z0-9]{2}")
_FUTURES_DATA_IDS = {"TXF": "TX", "MXF": "MTX", "EXF": "TE", "FXF": "TF"}


def _requested_days(config: dict) -> int:
    try:
        return min(max(int(config.get("days") or 60), 1), 20000)
    except (TypeError, ValueError):
        return 60


def _date_range(days: int) -> tuple[str, str]:
    end = datetime.now(_TAIPEI).date()
    # API 按日历日期查询；多抓周末/休市日后再按交易日数裁切。
    start = end - timedelta(days=max(days * 2, days + 14))
    return start.isoformat(), end.isoformat()


def _headers(config: dict) -> dict[str, str]:
    token = str(config.get("token") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _request_payload(
    symbol: Symbol,
    config: dict,
    *,
    dataset: str,
    data_id: str,
    log_label: str,
) -> tuple[object, int]:
    days = _requested_days(config)
    start_date, end_date = _date_range(days)
    payload = market_get(
        _API_URL,
        host_key="api.finmindtrade.com",
        params={
            "dataset": dataset,
            "data_id": data_id,
            "start_date": start_date,
            "end_date": end_date,
        },
        headers=_headers(config),
        min_interval_s=0.2,
        timeout=15,
        retries=1,
        parse="json",
        log_label=log_label,
        symbol=symbol.code,
    )
    if isinstance(payload, dict) and payload.get("status") != 200:
        raise RuntimeError(f"FinMind API: {payload.get('msg') or payload.get('status')}")
    return payload, days


class FinMindKlineVendor(KlineVendor):
    """FinMind 台股與期貨歷史日 K；支援免 token 公開額度與 Bearer token。"""

    name = "finmind"
    supports_markets = {"TW", "TWF"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Bar]:
        if not symbols:
            return []
        symbol = symbols[0]
        code = symbol.code.strip()
        if symbol.market == "TW":
            if not code:
                return []
            payload, days = _request_payload(
                symbol,
                config,
                dataset="TaiwanStockPrice",
                data_id=code,
                log_label="FinMind 台股日 K",
            )
            return _parse_stock_bars(payload, days)
        if symbol.market != "TWF" or not _FUTURES_CODE.fullmatch(code):
            return []

        payload, days = _request_payload(
            symbol,
            config,
            dataset="TaiwanFuturesDaily",
            data_id=_FUTURES_DATA_IDS.get(code, code),
            log_label="FinMind 期貨日 K",
        )
        return _parse_futures_bars(payload, days)


def _parse_stock_bars(payload: object, days: int) -> list[Bar]:
    if not isinstance(payload, dict):
        return []
    bars = []
    for row in payload.get("data") or []:
        if not isinstance(row, dict):
            continue
        try:
            bar_date = str(row.get("date") or "")[:10]
            values = [float(row[key]) for key in ("open", "close", "max", "min")]
            if len(bar_date) != 10 or min(values) <= 0:
                continue
            bars.append(Bar(
                date=bar_date,
                open=values[0],
                close=values[1],
                high=values[2],
                low=values[3],
                volume=float(row.get("Trading_Volume") or 0),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda bar: bar.date)
    return bars[-days:]


def _parse_futures_bars(payload: object, days: int) -> list[Bar]:
    if not isinstance(payload, dict):
        return []
    nearest = {}
    for row in payload.get("data") or []:
        if not isinstance(row, dict) or row.get("trading_session") != "position":
            continue
        contract_date = row.get("contract_date")
        if not isinstance(contract_date, str) or not re.fullmatch(r"\d{6}", contract_date):
            continue
        bar_date = str(row.get("date") or "")[:10]
        if len(bar_date) != 10:
            continue
        current = nearest.get(bar_date)
        if current is None or contract_date < current[0]:
            nearest[bar_date] = (contract_date, row)

    bars = []
    for bar_date, (_, row) in nearest.items():
        try:
            values = [float(row[key]) for key in ("open", "close", "max", "min")]
            if not all(value > 0 for value in values):
                continue
            bars.append(Bar(
                date=bar_date,
                open=values[0],
                close=values[1],
                high=values[2],
                low=values[3],
                volume=float(row.get("volume") or 0),
            ))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    bars.sort(key=lambda bar: bar.date)
    return bars[-days:]
