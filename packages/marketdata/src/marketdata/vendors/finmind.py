"""FinMind 台股歷史日 K vendor。"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from marketdata.http import market_get
from marketdata.symbol import Symbol
from marketdata.types import Bar
from marketdata.vendors.base import KlineVendor

_API_URL = "https://api.finmindtrade.com/api/v4/data"
_TAIPEI = ZoneInfo("Asia/Taipei")


class FinMindKlineVendor(KlineVendor):
    """FinMind TaiwanStockPrice 歷史日 K；支援免 token 公開額度與 Bearer token。"""

    name = "finmind"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Bar]:
        if not symbols:
            return []
        symbol = symbols[0]
        if symbol.market != "TW" or not symbol.code.strip():
            return []

        try:
            days = min(max(int(config.get("days") or 60), 1), 20000)
        except (TypeError, ValueError):
            days = 60
        end = datetime.now(_TAIPEI).date()
        # API 按日曆日期查詢；多抓週末/休市日後再按交易日數裁切。
        start = end - timedelta(days=max(days * 2, days + 14))
        headers = {}
        token = str(config.get("token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = market_get(
            _API_URL,
            host_key="api.finmindtrade.com",
            params={
                "dataset": "TaiwanStockPrice",
                "data_id": symbol.code.strip(),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            headers=headers,
            min_interval_s=0.2,
            timeout=15,
            retries=1,
            parse="json",
            log_label="FinMind 台股日 K",
            symbol=symbol.code,
        )
        if not isinstance(payload, dict):
            return []
        if payload.get("status") != 200:
            raise RuntimeError(f"FinMind API: {payload.get('msg') or payload.get('status')}")

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
