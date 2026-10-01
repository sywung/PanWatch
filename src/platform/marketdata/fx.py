"""外部汇率来源与缓存。"""

from __future__ import annotations

import logging
import threading
import time

import httpx

from src.platform.marketdata.models import BASE_CURRENCY

logger = logging.getLogger(__name__)

CURRENCY_BY_MARKET = {"TW": "TWD", "CN": "CNY", "HK": "HKD", "US": "USD"}
FALLBACK_RATES = {"USD": 32.0, "HKD": 4.1, "CNY": 4.5}

_SUCCESS_TTL = 3600.0
_FAILURE_BACKOFF = 300.0
_cache: dict[str, dict[str, float]] = {}
_cache_lock = threading.Lock()


def market_currency(market) -> str:
    """返回市场对应的币别，未知市场使用基准币别。"""
    if market is None:
        return BASE_CURRENCY
    value = getattr(market, "value", market)
    return CURRENCY_BY_MARKET.get(str(value).upper(), BASE_CURRENCY)


def _now() -> float:
    return time.time()


def _fetch_yahoo_rate(symbol) -> float | None:
    """从 Yahoo Finance 获取汇率，失败时返回 None。"""
    try:
        response = httpx.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        response.raise_for_status()
        return float(response.json()["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception as exc:
        logger.warning("获取汇率失败 (%s): %s", symbol, exc)
        return None


def get_rate_to_base(currency) -> float:
    """获取指定币别兑基准币别的汇率。"""
    currency = str(getattr(currency, "value", currency)).upper()
    if currency == BASE_CURRENCY:
        return 1.0

    now = _now()
    with _cache_lock:
        entry = _cache.setdefault(currency, {})
        if now - entry.get("success_ts", float("-inf")) < _SUCCESS_TTL:
            return entry["rate"]
        if now - entry.get("failure_ts", float("-inf")) < _FAILURE_BACKOFF:
            return entry.get("rate", FALLBACK_RATES.get(currency, 1.0))

        try:
            rate = _fetch_yahoo_rate(f"{currency}{BASE_CURRENCY}=X")
        except Exception as exc:
            logger.warning("获取汇率失败 (%s): %s", currency, exc)
            rate = None
        if rate is not None:
            try:
                rate = float(rate)
            except (TypeError, ValueError):
                rate = None
        if rate is not None and rate > 0:
            entry["rate"] = rate
            entry["success_ts"] = now
            entry.pop("failure_ts", None)
            return rate

        entry["failure_ts"] = now
        return entry.get("rate", FALLBACK_RATES.get(currency, 1.0))


def rate_for_market(market) -> float:
    return get_rate_to_base(market_currency(market))


def exchange_rates_snapshot() -> dict:
    return {
        f"{currency}_{BASE_CURRENCY}": get_rate_to_base(currency)
        for currency in CURRENCY_BY_MARKET.values()
        if currency != BASE_CURRENCY
    }


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()
