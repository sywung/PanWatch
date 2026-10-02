"""读取与缓存期交所期货保证金资料。"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from src.platform.marketdata import stock_list

logger = logging.getLogger(__name__)

CACHE_FILE = stock_list.DATA_DIR / "futures_margin_cache.json"
CACHE_TTL = 86400
FAILURE_RETRY_SEC = 600

INDEX_MARGIN_URL = "https://openapi.taifex.com.tw/v1/IndexFuturesAndOptionsMargining"
SSF_MARGIN_URL = "https://openapi.taifex.com.tw/v1/SingleStockFuturesMargining"
ETF_MARGIN_URL = "https://openapi.taifex.com.tw/v1/SingleStockFuturesETFMargining"
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_INDEX_NAME_TO_CODE = {
    "臺股期貨": "TXF",
    "小型臺指": "MXF",
    "微型臺指期貨": "TMF",
    "電子期貨": "EXF",
    "金融期貨": "FXF",
}


@dataclass(frozen=True)
class Margin:
    kind: str
    initial: float
    maintenance: float


_memory_margins: dict[str, Margin] | None = None
_memory_expires_at = 0.0


def _positive_number(value, *, percent: bool = False) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        has_percent = isinstance(value, str) and value.strip().endswith("%")
        raw = value.strip().removesuffix("%").replace(",", "") if isinstance(value, str) else value
        number = float(raw)
        if percent and has_percent:
            number /= 100
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _parse_pair(row: dict, initial_key: str, maintenance_key: str, *, percent: bool = False):
    initial = _positive_number(row.get(initial_key), percent=percent)
    maintenance = _positive_number(row.get(maintenance_key), percent=percent)
    if initial is None or maintenance is None:
        return None
    return initial, maintenance


def parse_margins(index_rows, ssf_rows, etf_rows) -> dict[str, Margin]:
    """解析指数期、个股期与 ETF 期保证金资料。"""
    margins: dict[str, Margin] = {}

    for row in index_rows if isinstance(index_rows, list) else ():
        if not isinstance(row, dict):
            continue
        contract_name = row.get("Contract")
        if not isinstance(contract_name, str):
            continue
        code = _INDEX_NAME_TO_CODE.get(contract_name)
        pair = _parse_pair(row, "InitialMargin", "MaintenanceMargin")
        if code is not None and pair is not None:
            margins[code] = Margin("fixed", *pair)

    for row in ssf_rows if isinstance(ssf_rows, list) else ():
        if not isinstance(row, dict):
            continue
        code = row.get("Contract")
        pair = _parse_pair(
            row, "InitialMarginRate", "MaintenanceMarginRate", percent=True
        )
        if isinstance(code, str) and code.strip() and pair is not None:
            margins.setdefault(code.strip(), Margin("rate", *pair))

    seen_etf: set[str] = set()
    for row in etf_rows if isinstance(etf_rows, list) else ():
        if not isinstance(row, dict):
            continue
        code = row.get("Contract")
        if not isinstance(code, str) or not code.strip():
            continue
        code = code.strip()
        if code in seen_etf:
            continue
        pair = _parse_pair(row, "InitialMargin", "MaintenanceMargin")
        if pair is not None:
            seen_etf.add(code)
            margins.setdefault(code, Margin("fixed", *pair))

    return margins


def margin_per_lot(
    margin: Margin, price: float | None, multiplier: float
) -> tuple[float, float]:
    if margin.kind == "fixed":
        return margin.initial, margin.maintenance
    if margin.kind == "rate":
        if price is None:
            raise ValueError("rate margin requires a current price")
        base = price * multiplier
        return margin.initial * base, margin.maintenance * base
    raise ValueError(f"unsupported margin kind: {margin.kind}")


def _fetch_json(url: str):
    with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _fetch_all_raw():
    return (
        _fetch_json(INDEX_MARGIN_URL),
        _fetch_json(SSF_MARGIN_URL),
        _fetch_json(ETF_MARGIN_URL),
    )


def _decode_margins(raw) -> dict[str, Margin] | None:
    if not isinstance(raw, dict):
        return None
    margins = {}
    for code, value in raw.items():
        if not isinstance(code, str) or not isinstance(value, dict):
            continue
        kind = value.get("kind")
        initial = _positive_number(value.get("initial"))
        maintenance = _positive_number(value.get("maintenance"))
        if (
            isinstance(kind, str)
            and kind in {"fixed", "rate"}
            and initial is not None
            and maintenance is not None
        ):
            margins[code] = Margin(kind, initial, maintenance)
    return margins


def _read_disk_cache() -> tuple[float, dict[str, Margin]] | None:
    try:
        payload = json.loads(Path(CACHE_FILE).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        timestamp = float(payload["ts"])
        margins = _decode_margins(payload.get("margins"))
        if margins is None:
            return None
        return timestamp, margins
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _write_disk_cache(margins: dict[str, Margin], timestamp: float) -> None:
    try:
        path = Path(CACHE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"ts": timestamp, "margins": {code: asdict(value) for code, value in margins.items()}},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("期货保证金缓存写入失败: %s", exc)


def _remember(margins: dict[str, Margin], expires_at: float) -> None:
    global _memory_margins, _memory_expires_at
    _memory_margins = margins
    _memory_expires_at = expires_at


def get_margin(code: str) -> Margin | None:
    now = time.time()
    if _memory_margins is not None and now < _memory_expires_at:
        return _memory_margins.get(code)
    stale_memory = _memory_margins

    disk = _read_disk_cache()
    if disk is not None:
        disk_timestamp, disk_margins = disk
        if now - disk_timestamp < CACHE_TTL:
            _remember(disk_margins, disk_timestamp + CACHE_TTL)
            return disk_margins.get(code)
    else:
        disk_timestamp, disk_margins = 0.0, None

    try:
        index_rows, ssf_rows, etf_rows = _fetch_all_raw()
        margins = parse_margins(index_rows, ssf_rows, etf_rows)
        if not margins:
            raise ValueError("期货保证金资料为空或格式无效")
    except Exception as exc:
        logger.warning("期货保证金资料获取失败: %s", exc)
        fallback = disk_margins or stale_memory
        if fallback:
            _remember(fallback, now + FAILURE_RETRY_SEC)
            return fallback.get(code)
        _remember({}, now + FAILURE_RETRY_SEC)
        return None

    timestamp = time.time()
    _write_disk_cache(margins, timestamp)
    _remember(margins, timestamp + CACHE_TTL)
    return margins.get(code)


def reset_cache(memory_only: bool = False) -> None:
    global _memory_margins, _memory_expires_at
    _memory_margins = None
    _memory_expires_at = 0.0
    if not memory_only:
        try:
            Path(CACHE_FILE).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("期货保证金缓存删除失败: %s", exc)
