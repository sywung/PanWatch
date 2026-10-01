"""台灣期貨商品、個股期貨對照與近月合約解析。"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, time as daytime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from src.platform.marketdata import stock_list
from src.platform.scheduling import trading_calendar

logger = logging.getLogger(__name__)

CACHE_FILE = stock_list.DATA_DIR / "futures_list_cache.json"
CACHE_TTL = 86400
FAILURE_RETRY_SEC = 600  # 抓取失败后的退避期,避免每次查询都重打网络
TAIPEI = ZoneInfo("Asia/Taipei")
SSF_LISTS_URL = "https://openapi.taifex.com.tw/v1/SSFLists"
SSF_MARGIN_URLS = (
    "https://openapi.taifex.com.tw/v1/SingleStockFuturesMargining",
    "https://openapi.taifex.com.tw/v1/SingleStockFuturesETFMargining",
)
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_CONTRACT_RE = re.compile(r"^[A-Z][A-Z0-9]{2}$")
_MONTH_CODES = "ABCDEFGHIJKL"
_memory_products: tuple[FuturesProduct, ...] | None = None
_memory_expires_at = 0.0


@dataclass(frozen=True)
class FuturesProduct:
    code: str
    name: str
    kind: str
    openapi_code: str
    underlying_code: str | None
    is_mini: bool


@dataclass(frozen=True)
class FuturesContract:
    product: FuturesProduct
    year: int
    month: int

    @property
    def symbol(self) -> str:
        return f"{self.product.code}{contract_month_code(self.year, self.month)}"

    @property
    def contract_month(self) -> str:
        return f"{self.year:04d}{self.month:02d}"

    def mis_id(self, night: bool = False) -> str:
        return f"{self.symbol}-{'M' if night else 'F'}"


INDEX_FUTURES = (
    FuturesProduct("TXF", "台指期", "index", "TX", None, False),
    FuturesProduct("MXF", "小台指", "index", "MTX", None, False),
    FuturesProduct("TMF", "微台指", "index", "TMF", None, False),
    FuturesProduct("EXF", "電子期", "index", "TE", None, False),
    FuturesProduct("FXF", "金融期", "index", "TF", None, False),
)


def contract_month_code(year: int, month: int) -> str:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    return f"{_MONTH_CODES[month - 1]}{year % 10}"


def near_month(now: datetime) -> tuple[int, int]:
    current = now.replace(tzinfo=TAIPEI) if now.tzinfo is None else now.astimezone(TAIPEI)
    year, month = current.year, current.month
    settlement = trading_calendar.futures_settlement_date(year, month)
    if current.date() > settlement or (
        current.date() == settlement and current.time().replace(tzinfo=None) >= daytime(13, 30)
    ):
        month += 1
        if month == 13:
            year += 1
            month = 1
    return year, month


def parse_stock_futures(ssf_rows, margin_rows) -> list[FuturesProduct]:
    names: dict[str, str] = {}
    for row in margin_rows:
        if not isinstance(row, dict):
            continue
        contract = row.get("Contract")
        name = row.get("ContractName")
        if isinstance(contract, str) and isinstance(name, str) and name:
            names.setdefault(contract, name)

    products: list[FuturesProduct] = []
    seen: set[str] = set()
    for row in ssf_rows:
        if not isinstance(row, dict):
            continue
        contract = row.get("Contract")
        stock_code = row.get("StockCode")
        if not isinstance(contract, str) or not _CONTRACT_RE.fullmatch(contract):
            continue
        if stock_code is None or not str(stock_code).strip() or contract in seen:
            continue
        seen.add(contract)
        name = names.get(contract) or f"{row.get('StockName') or ''}期貨"
        products.append(
            FuturesProduct(
                code=contract,
                name=name,
                kind="stock",
                openapi_code=contract,
                underlying_code=str(stock_code).strip(),
                is_mini=name.startswith("小型"),
            )
        )
    return products


def _fetch_json(url: str):
    with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _fetch_ssf_lists_raw():
    return _fetch_json(SSF_LISTS_URL)


def _fetch_ssf_margin_raw():
    rows = []
    for url in SSF_MARGIN_URLS:
        data = _fetch_json(url)
        if isinstance(data, list):
            rows.extend(data)
    return rows


def reset_cache() -> None:
    global _memory_products, _memory_expires_at
    _memory_products = None
    _memory_expires_at = 0.0


def _remember(products: tuple[FuturesProduct, ...], expires_at: float) -> list[FuturesProduct]:
    global _memory_products, _memory_expires_at
    _memory_products, _memory_expires_at = products, expires_at
    return _with_index(products)


def _fallback(disk_products: tuple[FuturesProduct, ...] | None, now: float) -> list[FuturesProduct]:
    # 失败时沿用过期缓存(没有就只有指数期货),退避期内不再重试
    return _remember(disk_products or (), now + FAILURE_RETRY_SEC)


def _decode_products(raw) -> tuple[FuturesProduct, ...] | None:
    if not isinstance(raw, list):
        return None
    try:
        return tuple(FuturesProduct(**item) for item in raw if isinstance(item, dict))
    except (TypeError, ValueError):
        return None


def _read_disk_cache() -> tuple[float, tuple[FuturesProduct, ...]] | None:
    try:
        payload = json.loads(Path(CACHE_FILE).read_text(encoding="utf-8"))
        timestamp = float(payload["timestamp"])
        products = _decode_products(payload["products"])
        if products is None:
            return None
        return timestamp, products
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _write_disk_cache(products: tuple[FuturesProduct, ...], timestamp: float) -> None:
    try:
        Path(CACHE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(CACHE_FILE).write_text(
            json.dumps(
                {"timestamp": timestamp, "products": [asdict(product) for product in products]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("期货商品缓存写入失败: %s", exc)


def _with_index(products: tuple[FuturesProduct, ...]) -> list[FuturesProduct]:
    return [*INDEX_FUTURES, *products]


def get_futures_products() -> list[FuturesProduct]:
    now = time.time()
    if _memory_products is not None and now < _memory_expires_at:
        return _with_index(_memory_products)

    disk = _read_disk_cache()
    if disk is not None:
        disk_timestamp, disk_products = disk
        if now - disk_timestamp < CACHE_TTL:
            return _remember(disk_products, disk_timestamp + CACHE_TTL)
    else:
        disk_timestamp, disk_products = 0.0, None

    try:
        ssf_rows = _fetch_ssf_lists_raw()
    except Exception as exc:
        logger.warning("期货 SSFLists 获取失败: %s", exc)
        return _fallback(disk_products, now)
    if not isinstance(ssf_rows, list) or not ssf_rows:
        logger.warning("期货 SSFLists 为空,沿用可用缓存")
        return _fallback(disk_products, now)

    try:
        margin_rows = _fetch_ssf_margin_raw()
    except Exception as exc:
        logger.warning("个股期货保证金表获取失败,改用标的名称: %s", exc)
        margin_rows = []
    products = tuple(parse_stock_futures(ssf_rows, margin_rows or []))
    if not products:
        logger.warning("期货 SSFLists 未包含有效商品,沿用可用缓存")
        return _fallback(disk_products, now)

    timestamp = time.time()
    _write_disk_cache(products, timestamp)
    return _remember(products, timestamp + CACHE_TTL)


def get_futures_product(code: str) -> FuturesProduct | None:
    return next((product for product in get_futures_products() if product.code == code), None)


def search_futures(query: str, limit: int = 20) -> list[dict]:
    """按代码、标的代码或名称搜索期货商品。"""
    q = query.strip()
    if not q or limit <= 0:
        return []

    folded = q.casefold()
    matches = []
    for order, product in enumerate(get_futures_products()):
        code = product.code.casefold()
        underlying = (product.underlying_code or "").casefold()
        name = product.name.casefold()
        if code == folded:
            rank = 0
        elif code.startswith(folded):
            rank = 1
        elif underlying == folded:
            rank = 2
        elif name.startswith(folded):
            rank = 3
        elif folded in name:
            rank = 4
        else:
            continue
        matches.append((rank, order, product))

    matches.sort(key=lambda item: (item[0], item[1]))
    return [
        {
            "symbol": product.code,
            "name": product.name,
            "market": "TWF",
            "board": "FUT",
            "underlying": product.underlying_code,
        }
        for _, _, product in matches[:limit]
    ]


def futures_for_stock(stock_code: str) -> list[FuturesProduct]:
    matches = [
        product
        for product in get_futures_products()
        if product.kind == "stock" and product.underlying_code == stock_code
    ]
    return sorted(matches, key=lambda product: product.is_mini)


def resolve_contract(code: str, now: datetime) -> FuturesContract | None:
    product = get_futures_product(code)
    if product is None:
        return None
    year, month = near_month(now)
    return FuturesContract(product, year, month)


def spot_mis_id(code: str) -> str:
    return f"{code}-S"
