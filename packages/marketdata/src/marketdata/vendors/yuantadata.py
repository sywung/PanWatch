"""台股行情與 K 線 vendor，透過 LAN 上的 yuantaData API 取數。"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from marketdata.http import market_get
from marketdata.symbol import Symbol
from marketdata.types import Bar, Quote
from marketdata.vendors.base import KlineVendor, QuoteVendor

_TAIPEI = ZoneInfo("Asia/Taipei")
_UTC = timezone.utc
_MARKET_CACHE: dict[tuple[str, str], tuple[str | None, float | None]] = {}
_MARKET_CACHE_LOCK = threading.Lock()
_NEGATIVE_CACHE_SECONDS = 600.0
_QUOTE_BATCH_SIZE = 50
# 指数报价代码(2026-10-07 实测):不在商品清单,必须指定 market。
_INDEX_CODES = {"TWII": ("IX0001", "TSE", "加權指數"), "TPEX": ("IX0043", "OTC", "櫃買指數")}
_INTRADAY_INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}


def _now() -> datetime:
    """本地時鐘入口，方便測試固定台北時間。"""
    return datetime.now(_TAIPEI)


def _monotonic() -> float:
    return time.monotonic()


def _base_url(config: dict) -> str:
    base = str(config.get("base_url") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("yuantaData base_url 未設定")
    return base


def _headers(config: dict) -> dict[str, str]:
    token = str(config.get("token") or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _wait_seconds(config: dict) -> int:
    """預設 0＝只排入回補、不等待：資料未齊時立刻交給下一個來源，避免圖表與批次收集卡住。"""
    try:
        return max(0, int(config.get("wait_seconds", 0)))
    except (TypeError, ValueError):
        return 0


def _days(config: dict) -> int:
    try:
        return max(1, int(config.get("days", 120)))
    except (TypeError, ValueError):
        return 120


def _timeout(config: dict) -> int:
    return _wait_seconds(config) + 10


def _number(value) -> float | None:
    try:
        if value is None or str(value).strip() in {"", "-"}:
            return None
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError, OverflowError):
        return None


def _zero_none(value) -> float | None:
    number = _number(value)
    return None if number == 0 else number


def _response_status(response) -> int:
    try:
        return int(response.status_code)
    except (AttributeError, TypeError, ValueError):
        return 200


def _response_json(response):
    if isinstance(response, dict):  # makes small fake transports convenient
        return response
    try:
        return response.json()
    except Exception:
        return None


def _request(url: str, config: dict, *, params: dict, symbol: str = ""):
    return market_get(
        url,
        host_key="yuantadata",
        params=params,
        headers=_headers(config),
        timeout=_timeout(config),
        retries=0,
        parse="response",
        raise_for_status=False,
        log_label="yuantaData",
        symbol=symbol,
        trust_env=False,
    )


def _market_for(code: str, config: dict) -> str | None:
    """精確解析 TSE/OTC；成功常駐快取，未命中或模糊結果快取十分鐘。"""
    base = _base_url(config)
    key = (base, code)
    now_mono = _monotonic()
    with _MARKET_CACHE_LOCK:
        cached = _MARKET_CACHE.get(key)
        if cached is not None:
            market, expires = cached
            if expires is None or expires > now_mono:
                return market
            _MARKET_CACHE.pop(key, None)

    response = _request(
        f"{base}/api/v1/market/symbols", config,
        params={"q": code, "limit": 20}, symbol=code,
    )
    if response is None or _response_status(response) != 200:
        return None
    payload = _response_json(response)
    symbols = payload.get("symbols") if isinstance(payload, dict) else None
    exact_markets = {
        str(row.get("market") or "").upper()
        for row in symbols or []
        if isinstance(row, dict) and str(row.get("symbol") or "").strip() == code
    }
    market = next(iter(exact_markets)) if len(exact_markets) == 1 else None
    if market not in {"TSE", "OTC"}:
        market = None
    expiry = None if market else now_mono + _NEGATIVE_CACHE_SECONDS
    with _MARKET_CACHE_LOCK:
        _MARKET_CACHE[key] = (market, expiry)
    return market


def _parse_ts(value) -> datetime | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=_UTC)
        return stamp.astimezone(_TAIPEI)
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_bar(row: dict, *, intraday: bool) -> Bar | None:
    stamp = _parse_ts(row.get("ts"))
    if stamp is None:
        return None
    values = [_number(row.get(key)) for key in ("open", "high", "low", "close")]
    if any(value is None for value in values):
        return None
    volume = _number(row.get("volume")) or 0.0  # API 已是股，不作單位換算
    date_text = stamp.strftime("%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d")
    return Bar(date=date_text, open=values[0], high=values[1], low=values[2],
               close=values[3], volume=volume)


def _bars_response(code: str, market: str, timeframe: str, start: datetime,
                   end: datetime, config: dict):
    base = _base_url(config)
    wait = _wait_seconds(config)
    path_code = quote(code, safe="")
    response = _request(
        f"{base}/api/v1/market/bars/{path_code}", config,
        params={"market": market, "timeframe": timeframe,
                "from": start.isoformat(), "to": end.isoformat(),
                "fetch": True, "wait": wait},
        symbol=code,
    )
    if response is None:
        raise RuntimeError("yuantaData K 線請求失敗")
    status = _response_status(response)
    if status >= 500:
        raise RuntimeError(f"yuantaData K 線 HTTP {status}")
    if status != 200:
        return None
    payload = _response_json(response)
    if not isinstance(payload, dict):
        return None
    return payload


def _bar_rows(payload, *, intraday: bool) -> list[Bar]:
    rows = payload.get("bars") if isinstance(payload, dict) else None
    return [bar for row in rows or []
            if isinstance(row, dict) and (bar := _parse_bar(row, intraday=intraday)) is not None]


def _local_range(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start_date, dt_time.min, tzinfo=_TAIPEI),
        datetime.combine(end_date, dt_time.min, tzinfo=_TAIPEI),
    )


def _aggregate(bars: list[Bar], minutes: int) -> list[Bar]:
    groups: dict[datetime, list[Bar]] = {}
    for bar in sorted(bars, key=lambda item: item.date):
        stamp = datetime.strptime(bar.date, "%Y-%m-%d %H:%M")
        anchor = datetime.combine(stamp.date(), dt_time(9, 0))
        bucket = anchor + timedelta(minutes=((stamp - anchor).total_seconds() // (minutes * 60)) * minutes)
        groups.setdefault(bucket, []).append(bar)
    result = []
    for bucket, items in sorted(groups.items()):
        result.append(Bar(
            date=bucket.strftime("%Y-%m-%d %H:%M"),
            open=items[0].open,
            high=max(item.high for item in items),
            low=min(item.low for item in items),
            close=items[-1].close,
            volume=sum(item.volume for item in items),
        ))
    return result


def _missing_today_during_session(bars: list[Bar]) -> bool:
    now = _now().astimezone(_TAIPEI)
    return (
        now.weekday() < 5
        and now.time() >= dt_time(9, 0)
        and not any(bar.date[:10] == now.date().isoformat() for bar in bars)
    )


def fetch_tw_index_quotes(config: dict, wanted: set[str]) -> list[dict]:
    """取加权(TWII)/柜买(TPEX)指数报价,格式同 MarketData.tw_index_quotes 的 MIS 结果。"""
    base = _base_url(config)
    out: list[dict] = []
    for symbol, (code, market, name) in _INDEX_CODES.items():
        if symbol not in wanted:
            continue
        response = _request(
            f"{base}/api/v1/market/quotes", config,
            params={"symbols": code, "market": market}, symbol=code,
        )
        if response is None or _response_status(response) != 200:
            continue
        payload = _response_json(response)
        rows = payload.get("data") if isinstance(payload, dict) else None
        for row in rows or []:
            if not isinstance(row, dict) or str(row.get("symbol") or "").strip().upper() != code:
                continue
            price = _number(row.get("price"))
            if price is None or price <= 0:
                continue
            prev_close = _zero_none(row.get("prev_close"))
            change = price - prev_close if prev_close is not None else 0.0
            out.append({"symbol": symbol, "name": name, "current_price": price,
                        "prev_close": prev_close, "change_amount": change,
                        "change_pct": change / prev_close * 100 if prev_close else 0.0,
                        "volume": 0.0, "turnover": 0.0})
            break
    return out


class YuantaDataQuoteVendor(QuoteVendor):
    """從 yuantaData 的即時報價轉發 API 取得台股報價。"""

    name = "yuantadata"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Quote]:
        base = _base_url(config)
        codes = list(dict.fromkeys(
            symbol.code.strip().upper() for symbol in symbols
            if symbol.market == "TW" and symbol.code.strip()
        ))
        if not codes:
            return []
        found: dict[str, Quote] = {}

        def request_batch(batch: list[str]) -> tuple[int, list[dict]]:
            response = _request(
                f"{base}/api/v1/market/quotes", config,
                params={"symbols": ",".join(batch)}, symbol=",".join(batch),
            )
            if response is None:
                raise RuntimeError("yuantaData 報價服務連線失敗")
            status = _response_status(response)
            if status not in {200, 400}:
                raise RuntimeError(f"yuantaData 報價 HTTP {status}")
            payload = _response_json(response)
            rows = payload.get("data") if isinstance(payload, dict) else None
            return status, [row for row in rows or [] if isinstance(row, dict)]

        def add_rows(batch: list[str], rows: list[dict]) -> None:
            allowed = set(batch)
            for row in rows:
                code = str(row.get("symbol") or "").strip().upper()
                if code not in allowed:
                    continue
                price = _number(row.get("price"))
                if price is None or price <= 0:
                    continue
                prev_close = _zero_none(row.get("prev_close"))
                change = price - prev_close if prev_close is not None else None
                change_pct = change / prev_close * 100 if change is not None and prev_close else None
                found[code] = Quote(
                    symbol=code,
                    market="TW",
                    name=str(row.get("name") or ""),
                    current_price=price,
                    prev_close=prev_close,
                    open_price=_zero_none(row.get("open")),
                    high_price=_zero_none(row.get("high")),
                    low_price=_zero_none(row.get("low")),
                    volume=_number(row.get("volume_lots")),
                    change_amount=change,
                    change_pct=change_pct,
                )

        for start in range(0, len(codes), _QUOTE_BATCH_SIZE):
            batch = codes[start:start + _QUOTE_BATCH_SIZE]
            status, rows = request_batch(batch)
            if status == 400:
                # Ambiguous/invalid code rejects the whole batch; isolate each code.
                for code in batch:
                    single_status, single_rows = request_batch([code])
                    if single_status == 200:
                        add_rows([code], single_rows)
            else:
                add_rows(batch, rows)
        return [found[code] for code in codes if code in found]


class YuantaDataKlineVendor(KlineVendor):
    """從 yuantaData 取得日 K 與分 K；15/30/60 分由 5 分 K 本地合成。"""

    name = "yuantadata"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Bar]:
        days = _days(config)
        today = _now().astimezone(_TAIPEI).date()
        start, end = _local_range(today - timedelta(days=max(days * 2, days + 14)),
                                  today + timedelta(days=1))
        out: list[Bar] = []
        for symbol in symbols:
            if symbol.market != "TW" or not symbol.code.strip():
                continue
            code = symbol.code.strip().upper()
            market = _market_for(code, config)
            if market is None:
                continue
            payload = _bars_response(code, market, "1d", start, end, config)
            if not isinstance(payload, dict) or payload.get("complete") is not True:
                continue
            bars = sorted(_bar_rows(payload, intraday=False), key=lambda bar: bar.date)
            out.extend(bars[-days:])
        return out

    def fetch_intraday(self, code: str, interval: str, config: dict) -> list[Bar]:
        target_minutes = _INTRADAY_INTERVALS.get(interval)
        if target_minutes is None:
            return []
        code = str(code).strip().upper()
        if not code:
            return []
        market = _market_for(code, config)
        if market is None:
            return []
        now = _now().astimezone(_TAIPEI)
        lookback_days = 7 if interval == "1m" else 60
        start, end = _local_range(now.date() - timedelta(days=lookback_days),
                                  now.date() + timedelta(days=1))
        timeframe = "1m" if interval == "1m" else "5m"
        payload = _bars_response(code, market, timeframe, start, end, config)
        if not isinstance(payload, dict) or payload.get("complete") is not True:
            return []
        bars = sorted(_bar_rows(payload, intraday=True), key=lambda bar: bar.date)
        if not bars:
            return []
        if target_minutes > 5:
            bars = _aggregate(bars, target_minutes)
        if _missing_today_during_session(bars):
            return []
        return bars
