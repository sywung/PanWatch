"""元大 SparkAPI 本地转接服务的台股报价与 K 线 vendor。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from marketdata.http import market_get, market_post
from marketdata.symbol import Symbol
from marketdata.types import Bar, Quote
from marketdata.vendors.base import KlineVendor, QuoteVendor

_DEFAULT_BASE_URL = "http://host.containers.internal:2885"
_TAIPEI = ZoneInfo("Asia/Taipei")
_MARKETS = ("TSE", "OTC", "ESB")
_QUOTE_BATCH_SIZE = 600
_INTRADAY_INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}


def _today() -> date:
    return datetime.now(_TAIPEI).date()


def _base_url(config: dict) -> str:
    return str(config.get("base_url") or _DEFAULT_BASE_URL).rstrip("/")


def _headers(config: dict) -> dict[str, str]:
    token = str(config.get("token") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _days(config: dict) -> int:
    try:
        return max(1, int(config.get("days") or 120))
    except (TypeError, ValueError):
        return 120


def _number(value) -> float | None:
    try:
        if value is None or str(value).strip() in {"", "-"}:
            return None
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _quotes_rows(payload) -> list[dict]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _bars_rows(payload) -> list[dict]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _parse_bar(row: dict, *, intraday_minutes: int | None = None) -> Bar | None:
    raw_time = str(row.get("time") or "")
    if len(raw_time) < 10:
        return None
    values = [_number(row.get(key)) for key in ("open", "high", "low", "close")]
    if any(value is None for value in values):
        return None
    try:
        volume = (_number(row.get("volume")) or 0.0) * 1000
        if intraday_minutes is None:
            bar_date = raw_time[:10]
        else:
            stamp_text = raw_time.replace("Z", "+00:00")
            stamp = datetime.fromisoformat(stamp_text)
            if stamp.tzinfo is not None:
                stamp = stamp.astimezone(_TAIPEI).replace(tzinfo=None)
            stamp -= timedelta(minutes=intraday_minutes)
            bar_date = stamp.strftime("%Y-%m-%d %H:%M")
        return Bar(date=bar_date, open=values[0], high=values[1], low=values[2],
                   close=values[3], volume=volume)
    except (TypeError, ValueError, OverflowError):
        return None


class YuantaQuoteVendor(QuoteVendor):
    """经由本机 SparkAPI 转接服务取得台股即时报价。"""

    name = "yuanta"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Quote]:
        codes = list(dict.fromkeys(
            sym.code.strip().upper() for sym in symbols
            if sym.market == "TW" and sym.code.strip()
        ))
        if not codes:
            return []

        url = f"{_base_url(config)}/quotes"
        headers = _headers(config)
        found: dict[str, Quote] = {}
        unresolved = codes
        for market in _MARKETS:
            next_unresolved: list[str] = []
            for start in range(0, len(unresolved), _QUOTE_BATCH_SIZE):
                batch = unresolved[start:start + _QUOTE_BATCH_SIZE]
                payload = market_post(
                    url,
                    host_key="yuanta_gateway",
                    json_body={"items": [{"market": market, "code": code} for code in batch]},
                    headers=headers,
                    timeout=10,
                    retries=0,
                    parse="json",
                    log_label="元大 SparkAPI 行情",
                    symbol=",".join(batch),
                    trust_env=False,
                )
                if payload is None:
                    raise RuntimeError("元大 SparkAPI 转接服务请求失败")
                remaining = set(batch)
                for row in _quotes_rows(payload):
                    code = str(row.get("code") or "").strip().upper()
                    if code not in remaining:
                        continue
                    price = _number(row.get("price"))
                    if price is None or price <= 0:
                        continue
                    prev_close = _number(row.get("prev_close"))
                    change_amount = price - prev_close if prev_close is not None else None
                    change_pct = (
                        change_amount / prev_close * 100
                        if change_amount is not None and prev_close
                        else None
                    )
                    found[code] = Quote(
                        symbol=code,
                        market="TW",
                        name=str(row.get("name") or ""),
                        current_price=price,
                        prev_close=prev_close,
                        open_price=_number(row.get("open")),
                        high_price=_number(row.get("high")),
                        low_price=_number(row.get("low")),
                        volume=_number(row.get("volume")),
                        change_amount=change_amount,
                        change_pct=change_pct,
                    )
                    remaining.remove(code)
                next_unresolved.extend(code for code in batch if code in remaining)
            unresolved = next_unresolved
            if not unresolved:
                break
        return [found[code] for code in codes if code in found]


class YuantaKlineVendor(KlineVendor):
    """经由本机 SparkAPI 转接服务取得台股日 K 与分 K。"""

    name = "yuanta"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Bar]:
        days = _days(config)
        end = _today()
        start = end - timedelta(days=max(days * 2, days + 14))
        base = _base_url(config)
        headers = _headers(config)
        out: list[Bar] = []
        for symbol in symbols:
            if symbol.market != "TW" or not symbol.code.strip():
                continue
            bars: list[Bar] = []
            for market in _MARKETS:
                payload = market_get(
                    f"{base}/kline",
                    host_key="yuanta_gateway",
                    params={"market": market, "code": symbol.code.strip(), "period": "1d",
                            "start": start.isoformat(), "end": end.isoformat()},
                    headers=headers,
                    timeout=20,
                    retries=0,
                    parse="json",
                    log_label="元大 SparkAPI 日K",
                    symbol=symbol.code,
                    trust_env=False,
                )
                if payload is None:
                    raise RuntimeError("元大 SparkAPI 转接服务请求失败")
                bars = [bar for row in _bars_rows(payload) if (bar := _parse_bar(row)) is not None]
                if bars:
                    break
            bars.sort(key=lambda bar: bar.date)
            out.extend(bars[-days:])
        return out

    def fetch_intraday(self, code: str, interval: str, config: dict) -> list[Bar]:
        minutes = _INTRADAY_INTERVALS.get(interval)
        if minutes is None:
            return []
        end = _today()
        start = end - timedelta(days=60)
        base = _base_url(config)
        headers = _headers(config)
        for market in _MARKETS:
            payload = market_get(
                f"{base}/kline",
                host_key="yuanta_gateway",
                params={"market": market, "code": str(code).strip(), "period": interval,
                        "start": start.isoformat(), "end": end.isoformat()},
                headers=headers,
                timeout=20,
                retries=0,
                parse="json",
                log_label="元大 SparkAPI 分钟K",
                symbol=str(code),
                trust_env=False,
            )
            if payload is None:
                raise RuntimeError("元大 SparkAPI 转接服务请求失败")
            bars = [bar for row in _bars_rows(payload)
                    if (bar := _parse_bar(row, intraday_minutes=minutes)) is not None]
            if bars:
                return bars
        return []
