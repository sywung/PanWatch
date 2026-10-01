"""台股全市场开放资料的共用下载与进程内缓存。"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import date, timedelta
from typing import Any

import httpx

_cache: dict[tuple, tuple[float, str]] = {}
_lock = threading.RLock()
_CODE_RE = re.compile(r"^(\d{4}|00\d{2,4}[A-Z]?)$")


def _download(url: str, params: dict[str, Any] | None = None) -> str:
    """下载台股官方开放资料；所有网络访问集中在此处，方便测试替换。"""
    response = httpx.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text.removeprefix("\ufeff")


def _key(url: str, params: dict[str, Any] | None) -> tuple:
    return url, tuple(sorted((params or {}).items()))


def get_text(
    url: str, params: dict[str, Any] | None = None, ttl: float = 1800
) -> str:
    key = _key(url, params)
    now = time.monotonic()
    with _lock:
        item = _cache.get(key)
        if item and now - item[0] < ttl:
            return item[1]
    text = _download(url, params)
    with _lock:
        _cache[key] = (time.monotonic(), text)
    return text


def get_json(url: str, params: dict[str, Any] | None = None, ttl: float = 1800):
    return json.loads(get_text(url, params, ttl))


def reset_cache() -> None:
    with _lock:
        _cache.clear()


def tw_date(value: str) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.isdigit():
        return f"{int(text[:3]) + 1911:04d}-{text[3:5]}-{text[5:]}"
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def number(value) -> float | None:
    if value is None or str(value).strip() in {"", "-"}:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def valid_code(value: str) -> bool:
    return bool(_CODE_RE.fullmatch(str(value or "").strip().upper()))


def recent_dates(days: int = 7) -> list[str]:
    today = date.today()
    return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]
