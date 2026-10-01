"""股票标的清单的数据源适配器、项目级缓存与模糊搜索。

清单可被 API、任务调度和业务模块共同使用，因此属于市场数据平台，而不是
HTTP 层。缓存仍固定保存在项目根目录的 ``data/``，避免移动代码后悄然生成
另一份 ``src/data`` 缓存。
"""
import json
import os
import re
import time
import logging
import concurrent.futures
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_FILE = DATA_DIR / "stock_list_cache.json"
CACHE_TTL = 86400 * 7  # 7 days
# 台股来源有失败时,缓存只保留这么久就重抓
PARTIAL_RETRY_SEC = 1800

TWSE_STOCK_LIST_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_STOCK_LIST_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
TPEX_ESB_STOCK_LIST_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_R"
TW_SYMBOL_RE = re.compile(r"^(\d{4}|00\d{2,4}[A-Z]?)$")

# OpenCC 体积较大且只在台股名称搜索时需要，因此惰性初始化。
_OPENCC_CONVERTER = None
_OPENCC_INITIALIZED = False

# 东方财富 A 股（使用 push2delay 域名，避免重定向）
EASTMONEY_URL = "http://80.push2delay.eastmoney.com/api/qt/clist/get"
EASTMONEY_PARAMS = {
    "po": "1",
    "np": "1",
    "fltt": "2",
    "invt": "2",
    "fid": "f12",
    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "fields": "f12,f14",
}

# 东方财富港股参数
EASTMONEY_HK_PARAMS = {
    "po": "1",
    "np": "1",
    "fltt": "2",
    "invt": "2",
    "fid": "f12",
    "fs": "m:128+t:3,m:128+t:4,m:128+t:1,m:128+t:2",  # 港股主板、创业板等
    "fields": "f12,f14",
}

# 东方财富美股参数
EASTMONEY_US_PARAMS = {
    "po": "1",
    "np": "1",
    "fltt": "2",
    "invt": "2",
    "fid": "f12",
    "fs": "m:105,m:106,m:107",  # 美股 NYSE, NASDAQ, AMEX
    "fields": "f12,f14",
}

# 东方财富北交所参数（北证A股）
EASTMONEY_BJ_PARAMS = {
    "po": "1",
    "np": "1",
    "fltt": "2",
    "invt": "2",
    "fid": "f12",
    "fs": "m:0+t:81",  # 北交所
    "fields": "f12,f14",
}
PAGE_SIZE = 100


def _read_cache_file() -> dict | None:
    """读取缓存文件原始内容(不判断过期);不存在或损坏返回 None。"""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and isinstance(data.get("stocks"), list) else None
    except (json.JSONDecodeError, OSError):
        return None


def _load_cache() -> list[dict] | None:
    data = _read_cache_file()
    if not data:
        return None
    stocks = data["stocks"]
    age = time.time() - data.get("ts", 0)
    if age >= CACHE_TTL:
        return None
    # 台股来源有失败的缓存(或旧版未记录状态的缓存)只用 PARTIAL_RETRY_SEC,过后重抓,
    # 不能让一次失败的残缺清单沿用 7 天
    if data.get("partial", True) and age >= PARTIAL_RETRY_SEC:
        return None
    # 没有台股或板别字段的旧版本缓存需要立即升级，不能继续沿用原 TTL。
    tw_items = [item for item in stocks if isinstance(item, dict) and item.get("market") == "TW"]
    if tw_items and all(item.get("board") for item in tw_items):
        return stocks
    return None


def _save_cache(stocks: list[dict], *, partial: bool = False, failed: list[str] | None = None):
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {"ts": time.time(), "stocks": stocks, "partial": partial, "failed": failed or []}
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://quote.eastmoney.com/",
}


def _fetch_page(client: httpx.Client, page: int) -> list[dict]:
    """获取东方财富股票列表的单页"""
    params = {**EASTMONEY_PARAMS, "pn": str(page), "pz": str(PAGE_SIZE)}
    resp = client.get(EASTMONEY_URL, params=params, timeout=30, follow_redirects=True)
    data = resp.json()
    diff = data.get("data") or {}
    items = diff.get("diff") or []
    return [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "CN"} for item in items]


def _fetch_from_eastmoney() -> list[dict]:
    """东方财富 A 股列表（HTTP 分页并发获取）"""
    with httpx.Client(follow_redirects=True, headers=HEADERS, timeout=30) as client:
        # 第一页: 获取总数
        params = {**EASTMONEY_PARAMS, "pn": "1", "pz": str(PAGE_SIZE)}
        resp = client.get(EASTMONEY_URL, params=params)
        data = resp.json()
        root = data.get("data") or {}
        total = root.get("total", 0)
        first_items = root.get("diff") or []

        stocks = [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "CN"} for item in first_items]

        if total <= PAGE_SIZE:
            return stocks

        # 剩余页并发获取
        pages_needed = (total + PAGE_SIZE - 1) // PAGE_SIZE
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_page, client, pn): pn for pn in range(2, pages_needed + 1)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    stocks.extend(future.result())
                except Exception as e:
                    logger.warning(f"东方财富第 {futures[future]} 页获取失败: {e}")

    return stocks


def _fetch_hk_page(client: httpx.Client, page: int) -> list[dict]:
    """获取东方财富港股列表的单页"""
    params = {**EASTMONEY_HK_PARAMS, "pn": str(page), "pz": str(PAGE_SIZE)}
    resp = client.get(EASTMONEY_URL, params=params, timeout=30, follow_redirects=True)
    data = resp.json()
    diff = data.get("data") or {}
    items = diff.get("diff") or []
    return [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "HK"} for item in items]


def _fetch_hk_from_eastmoney() -> list[dict]:
    """东方财富港股列表"""
    with httpx.Client(follow_redirects=True, headers=HEADERS, timeout=30) as client:
        params = {**EASTMONEY_HK_PARAMS, "pn": "1", "pz": str(PAGE_SIZE)}
        resp = client.get(EASTMONEY_URL, params=params)
        data = resp.json()
        root = data.get("data") or {}
        total = root.get("total", 0)
        first_items = root.get("diff") or []

        stocks = [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "HK"} for item in first_items]

        if total <= PAGE_SIZE:
            return stocks

        pages_needed = (total + PAGE_SIZE - 1) // PAGE_SIZE
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_hk_page, client, pn): pn for pn in range(2, pages_needed + 1)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    stocks.extend(future.result())
                except Exception as e:
                    logger.warning(f"东方财富港股第 {futures[future]} 页获取失败: {e}")

    return stocks


def _fetch_bj_page(client: httpx.Client, page: int) -> list[dict]:
    """获取东方财富北交所列表的单页"""
    params = {**EASTMONEY_BJ_PARAMS, "pn": str(page), "pz": str(PAGE_SIZE)}
    resp = client.get(EASTMONEY_URL, params=params, timeout=30, follow_redirects=True)
    data = resp.json()
    diff = data.get("data") or {}
    items = diff.get("diff") or []
    return [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "CN"} for item in items]


def _fetch_bj_from_eastmoney() -> list[dict]:
    """东方财富北交所列表（HTTP 分页并发获取）"""
    with httpx.Client(follow_redirects=True, headers=HEADERS, timeout=30) as client:
        # 第一页: 获取总数
        params = {**EASTMONEY_BJ_PARAMS, "pn": "1", "pz": str(PAGE_SIZE)}
        resp = client.get(EASTMONEY_URL, params=params)
        data = resp.json()
        root = data.get("data") or {}
        total = root.get("total", 0)
        first_items = root.get("diff") or []

        stocks = [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "CN"} for item in first_items]

        if total <= PAGE_SIZE:
            return stocks

        # 剩余页并发获取
        pages_needed = (total + PAGE_SIZE - 1) // PAGE_SIZE
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_bj_page, client, pn): pn for pn in range(2, pages_needed + 1)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    stocks.extend(future.result())
                except Exception as e:
                    logger.warning(f"东方财富北交所第 {futures[future]} 页获取失败: {e}")

    return stocks


def _fetch_us_page(client: httpx.Client, page: int) -> list[dict]:
    """获取东方财富美股列表的单页"""
    params = {**EASTMONEY_US_PARAMS, "pn": str(page), "pz": str(PAGE_SIZE)}
    resp = client.get(EASTMONEY_URL, params=params, timeout=30, follow_redirects=True)
    data = resp.json()
    diff = data.get("data") or {}
    items = diff.get("diff") or []
    return [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "US"} for item in items]


def _fetch_us_from_eastmoney() -> list[dict]:
    """东方财富美股列表"""
    with httpx.Client(follow_redirects=True, headers=HEADERS, timeout=30) as client:
        params = {**EASTMONEY_US_PARAMS, "pn": "1", "pz": str(PAGE_SIZE)}
        resp = client.get(EASTMONEY_URL, params=params)
        data = resp.json()
        root = data.get("data") or {}
        total = root.get("total", 0)
        first_items = root.get("diff") or []

        stocks = [{"symbol": str(item["f12"]), "name": str(item["f14"]), "market": "US"} for item in first_items]

        if total <= PAGE_SIZE:
            return stocks

        pages_needed = (total + PAGE_SIZE - 1) // PAGE_SIZE
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_fetch_us_page, client, pn): pn for pn in range(2, pages_needed + 1)}
            for future in concurrent.futures.as_completed(futures):
                try:
                    stocks.extend(future.result())
                except Exception as e:
                    logger.warning(f"东方财富美股第 {futures[future]} 页获取失败: {e}")

    return stocks


def _fetch_from_akshare() -> list[dict]:
    """akshare 数据源（备用，可能有 SSL 问题）"""
    import akshare as ak

    df = ak.stock_info_a_code_name()
    stocks = []
    for _, row in df.iterrows():
        stocks.append({
            "symbol": str(row["code"]),
            "name": str(row["name"]),
            "market": "CN",
        })
    return stocks


def _fetch_twse_raw() -> list[dict]:
    """获取 TWSE 上市股票和 ETF 原始列表"""
    resp = httpx.get(TWSE_STOCK_LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _fetch_tpex_raw() -> list[dict]:
    """获取 TPEx 上柜股票和 ETF 原始列表"""
    resp = httpx.get(TPEX_STOCK_LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _fetch_esb_raw() -> list[dict]:
    """获取 TPEx 興櫃股票原始列表"""
    resp = httpx.get(TPEX_ESB_STOCK_LIST_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


_TW_BOARD_SOURCES = (
    ("TSE", "_fetch_twse_raw", "Code", "Name"),
    ("OTC", "_fetch_tpex_raw", "SecuritiesCompanyCode", "CompanyName"),
    ("ESB", "_fetch_esb_raw", "SecuritiesCompanyCode", "CompanyAbbreviation"),
)


def _fetch_tw_stock_list_with_status() -> tuple[list[dict], list[str]]:
    """合并上市/上柜/兴柜清单;返回 (清单, 失败或回空的板别)。"""
    stocks: list[dict] = []
    failed: list[str] = []
    seen: set[str] = set()
    for board, fetcher_name, code_key, name_key in _TW_BOARD_SOURCES:
        try:
            raw = globals()[fetcher_name]()
        except Exception as e:
            logger.warning(f"台股 {board} 列表获取失败: {e}")
            failed.append(board)
            continue
        count = 0
        for row in raw or []:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get(code_key) or "").strip().upper()
            name = str(row.get(name_key) or "").strip()
            if not symbol or not name or not TW_SYMBOL_RE.fullmatch(symbol) or symbol in seen:
                continue
            seen.add(symbol)
            stocks.append({"symbol": symbol, "name": name, "market": "TW", "board": board})
            count += 1
        if count == 0:
            logger.warning(f"台股 {board} 列表为空")
            failed.append(board)
    return stocks, failed


def _fetch_tw_stock_list() -> list[dict]:
    """合并 TWSE 和 TPEx 列表，并过滤非股票类代码"""
    return _fetch_tw_stock_list_with_status()[0]


def _carry_over_tw_boards(stocks: list[dict], failed: list[str]) -> list[dict]:
    """失败的板别沿用上一份缓存(即使已过期)的资料,避免整板消失。"""
    old = _read_cache_file()
    if not old or not failed:
        return stocks
    have = {s["symbol"] for s in stocks}
    kept = [
        item for item in old["stocks"]
        if isinstance(item, dict) and item.get("market") == "TW"
        and item.get("board") in failed and item.get("symbol") not in have
    ]
    if kept:
        logger.info(f"台股 {','.join(failed)} 沿用上一份缓存 {len(kept)} 只")
    return stocks + kept


def refresh_stock_list() -> list[dict]:
    """拉取台股、A 股和港股等列表并缓存"""
    stocks = []

    # 台股: TWSE 上市 + TPEx 上柜 + 兴柜，放在清单最前面
    tw_stocks, tw_failed = _fetch_tw_stock_list_with_status()
    tw_stocks = _carry_over_tw_boards(tw_stocks, tw_failed)
    stocks.extend(tw_stocks)
    logger.info(f"获取台股列表: {len(tw_stocks)} 只" + (f"(失败板别 {tw_failed})" if tw_failed else ""))

    # A 股: 东方财富优先，akshare 备用
    try:
        cn_stocks = _fetch_from_eastmoney()
        stocks.extend(cn_stocks)
        logger.info(f"东方财富获取 A 股列表成功: {len(cn_stocks)} 只")
    except Exception as e:
        logger.warning(f"东方财富获取 A 股失败: {e}")
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(_fetch_from_akshare)
                cn_stocks = future.result(timeout=15)
                stocks.extend(cn_stocks)
            logger.info(f"akshare 获取 A 股列表成功: {len(cn_stocks)} 只")
        except concurrent.futures.TimeoutError:
            logger.error("akshare 获取超时（15s）")
        except Exception as e2:
            logger.error(f"A 股数据源获取失败: {e2}")

    # 港股: 东方财富
    try:
        hk_stocks = _fetch_hk_from_eastmoney()
        stocks.extend(hk_stocks)
        logger.info(f"东方财富获取港股列表成功: {len(hk_stocks)} 只")
    except Exception as e:
        logger.warning(f"东方财富获取港股失败: {e}")

    # 美股: 东方财富
    try:
        us_stocks = _fetch_us_from_eastmoney()
        stocks.extend(us_stocks)
        logger.info(f"东方财富获取美股列表成功: {len(us_stocks)} 只")
    except Exception as e:
        logger.warning(f"东方财富获取美股失败: {e}")

    # 北交所: 东方财富
    try:
        bj_stocks = _fetch_bj_from_eastmoney()
        stocks.extend(bj_stocks)
        logger.info(f"东方财富获取北交所列表成功: {len(bj_stocks)} 只")
    except Exception as e:
        logger.warning(f"东方财富获取北交所失败: {e}")

    if stocks:
        _save_cache(stocks, partial=bool(tw_failed), failed=tw_failed)
    return stocks


def get_stock_list() -> list[dict]:
    """获取股票列表(优先缓存)"""
    cached = _load_cache()
    if cached:
        return cached
    return refresh_stock_list()


def _realtime_search(query: str, market: str = "", limit: int = 20) -> list[dict]:
    """东方财富实时搜索 API"""
    import urllib.parse
    # 提高 count 以覆盖更多候选项（包含北交所）
    url = f"https://searchapi.eastmoney.com/api/suggest/get?input={urllib.parse.quote(query)}&type=14&count={limit * 5}"

    try:
        with httpx.Client(timeout=5) as client:
            resp = client.get(url, headers=HEADERS)
            data = resp.json()
    except Exception as e:
        logger.warning(f"实时搜索失败: {e}")
        return []

    items = data.get("QuotationCodeTable", {}).get("Data", [])
    if not items:
        return []

    def _normalize_symbol(code: str, mkt: str) -> str:
        c = (code or "").strip().upper()
        # 去掉可能的市场前缀/后缀，如 SH000001 / SZ000001 / BJ830799 / 00700.HK / 836239.BJ
        for p in ("SH", "SZ", "BJ", "US", "HK"):
            if c.startswith(p):
                c = c[len(p):]
                break
        if "." in c:
            # 形如 00700.HK / 836239.BJ
            c = c.split(".")[0]
        if mkt == "HK":
            # 保证为 5 位代码
            c = c.zfill(5)
        return c

    results = []
    for item in items:
        classify = (item.get("Classify") or "").strip()
        security_type = (item.get("SecurityTypeName") or "").strip()
        code_raw = (item.get("Code") or "").strip().upper()

        # 判断市场
        if (
            classify in ("AStock", "BJStock")
            or any(ch in security_type for ch in ("沪", "深", "北"))
            or code_raw.endswith(".BJ")
            or code_raw.startswith("BJ")
        ):
            stock_market = "CN"
        elif classify == "HKStock" or "港" in security_type:
            stock_market = "HK"
        elif classify == "UsStock" or "美" in security_type:
            stock_market = "US"
        else:
            continue  # 跳过其他类型（债券、基金等）

        # 市场筛选
        if market and stock_market != market:
            continue

        # 只保留股票（排除债券等）
        type_us = item.get("TypeUS", "")
        if stock_market == "US" and type_us and type_us not in ("1", "2", "3"):  # 1=普通股, 3=ADR/ADS 等；5=ETF 等
            continue

        code = item.get("Code", "")
        symbol = _normalize_symbol(code, stock_market)

        results.append({
            "symbol": symbol,
            "name": item.get("Name", ""),
            "market": stock_market,
        })

        if len(results) >= limit:
            break

    return results


MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"


def _lookup_tw_code(query: str) -> list[dict]:
    """本地清单查不到时,拿代码直接问证交所 mis 验证(上市/上柜)。

    清单刷新失败或新上市股票尚未进清单时,仍能用代码搜到。非代码格式的查询不打网络。
    """
    code = query.strip().upper()
    if not TW_SYMBOL_RE.fullmatch(code):
        return []
    try:
        resp = httpx.get(
            MIS_URL,
            params={"ex_ch": f"tse_{code}.tw|otc_{code}.tw", "json": "1", "delay": "0"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
        )
        rows = (resp.json() or {}).get("msgArray") or []
    except Exception as e:
        logger.warning(f"证交所验证台股代码失败 {code}: {e}")
        return []
    for row in rows:
        if str(row.get("c") or "").strip().upper() == code and row.get("n"):
            board = "OTC" if row.get("ex") == "otc" else "TSE"
            return [{"symbol": code, "name": str(row["n"]).strip(), "market": "TW", "board": board}]
    return []


def search_stocks(query: str, market: str = "", limit: int = 20) -> list[dict]:
    """搜索股票；台股使用缓存，全市场搜索时台股结果优先"""
    q = query.strip()
    if not q:
        return []

    if market == "TW":
        return _cached_search(q, market, limit) or _lookup_tw_code(q)

    if market == "":
        tw_results = _cached_search(q, "TW", limit) or _lookup_tw_code(q)
        realtime_results = _realtime_search(q, market, limit)
        cached_results = _cached_search(q, market, limit)
        results = []
        seen = set()
        for item in (*tw_results, *realtime_results):
            key = (item.get("market"), item.get("symbol"))
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
            if len(results) >= limit:
                break
        if len(results) < limit:
            for item in cached_results:
                if item.get("market") == "TW":
                    continue
                key = (item.get("market"), item.get("symbol"))
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    # 尝试实时搜索
    results = _realtime_search(q, market, limit)
    if len(results) >= limit:
        return results[:limit]

    # 实时搜索结果不足时，用缓存补全（便于聚合多市场搜索结果）
    cached = _cached_search(q, market, limit)
    if not results:
        if cached:
            logger.info("实时搜索无结果，使用缓存搜索")
        return cached

    seen = {(r.get("market"), r.get("symbol")) for r in results}
    for r in cached:
        key = (r.get("market"), r.get("symbol"))
        if key in seen:
            continue
        results.append(r)
        seen.add(key)
        if len(results) >= limit:
            break
    return results


def _cached_search(query: str, market: str = "", limit: int = 20) -> list[dict]:
    """从缓存中模糊搜索股票"""
    stocks = get_stock_list()
    if not stocks:
        return []

    q = query.strip().upper()
    if not q:
        return []

    query_variants = {q}
    if market == "TW":
        converter = _get_opencc_converter()
        if converter is not None:
            try:
                query_variants.add(converter.convert(query.strip()).upper())
            except Exception as e:
                logger.warning(f"OpenCC 转换失败: {e}")

    results = []
    for s in stocks:
        if market and s["market"] != market:
            continue
        code = s["symbol"].upper()
        name = s["name"].upper()
        names = {name}
        if market == "TW" and len(query_variants) > 1:
            converter = _get_opencc_converter()
            if converter is not None:
                try:
                    names.add(converter.convert(s["name"]).upper())
                except Exception as e:
                    logger.warning(f"OpenCC 转换失败: {e}")
        # 代码前缀匹配优先
        if code.startswith(q):
            results.append((0, s))
        elif any(variant in candidate for variant in query_variants for candidate in names):
            results.append((1, s))
        elif q in code:
            results.append((2, s))

        if len(results) >= limit * 2:
            break

    results.sort(key=lambda x: x[0])
    return [r[1] for r in results[:limit]]


def _get_opencc_converter():
    """惰性创建 OpenCC 转换器，未安装时跳过繁简转换"""
    global _OPENCC_CONVERTER, _OPENCC_INITIALIZED
    if _OPENCC_INITIALIZED:
        return _OPENCC_CONVERTER
    _OPENCC_INITIALIZED = True
    try:
        from opencc import OpenCC

        _OPENCC_CONVERTER = OpenCC("s2t")
    except ImportError:
        logger.debug("未安装 OpenCC，跳过台股繁简转换")
    return _OPENCC_CONVERTER
