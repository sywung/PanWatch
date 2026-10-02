"""PanWatch ↔ marketdata 接线:DB 配置端口 + 单例 + flag 门控的报价兼容层。

- DbConfigProvider:把 DataSource 表映射成 marketdata 的 SourceConfig(实现 ConfigProvider 端口)。
- get_market_data():进程级单例(无状态 vendor + 现查 DB 的配置端口)。
- md_quote_rows():新包 MarketData.quotes 转 dict,返回 list[dict](与旧 orchestrator 输出同形)。
- md_news()/md_news_by_keyword():新包 MarketData.news/news_by_keyword 转 host NewsItem。
"""

from __future__ import annotations

import logging

from marketdata import MarketData, Quote, SourceConfig

logger = logging.getLogger(__name__)


class DbConfigProvider:
    """ConfigProvider 端口实现:从 DataSource 表按 priority 读某类型的启用源。"""

    def _query_rows(self, datatype: str) -> list:
        from src.platform.persistence.database import SessionLocal
        from src.platform.persistence.models import DataSource

        db = SessionLocal()
        try:
            return (
                db.query(DataSource)
                .filter(DataSource.type == datatype, DataSource.enabled == True)  # noqa: E712
                .order_by(DataSource.priority)
                .all()
            )
        finally:
            db.close()

    def sources_for(self, datatype: str, market: str | None) -> list[SourceConfig]:
        market_code = (market or "").strip().upper()
        rows = self._query_rows(datatype)
        has_us_fallback = any(
            row.provider in {"stooq", "yahoo"} for row in rows
        )
        sources = []
        for row in rows:
            # 腾讯美股接口在当前网络出口稳定返回 501；A/HK 仍保留腾讯作为主源。
            if (
                datatype == "kline"
                and market_code == "US"
                and row.provider == "tencent"
                and has_us_fallback
            ):
                continue
            sources.append(
                SourceConfig(
                    vendor=row.provider,
                    priority=row.priority,
                    enabled=True,
                    config=row.config or {},
                    supports_batch=bool(row.supports_batch),
                )
            )
        return sources


_md: MarketData | None = None


def get_market_data() -> MarketData:
    """进程级单例。vendor 无状态、配置现查 DB,故无需失效钩子。"""
    global _md
    if _md is None:
        _md = MarketData(config=DbConfigProvider())
    return _md


def reset_market_data() -> None:
    """测试或热重载时重置单例。"""
    global _md
    _md = None


def _quote_to_row(q: Quote) -> dict:
    """marketdata.Quote → 旧 orchestrator 同形 dict。"""
    return {
        "symbol": q.symbol,
        "name": q.name,
        "market": q.market,
        "current_price": q.current_price,
        "change_pct": q.change_pct,
        "change_amount": q.change_amount,
        "prev_close": q.prev_close,
        "open_price": q.open_price,
        "high_price": q.high_price,
        "low_price": q.low_price,
        "volume": q.volume,
        "turnover": q.turnover,
        "turnover_rate": q.turnover_rate,
        "volume_ratio": q.volume_ratio,
        "pe_ratio": q.pe_ratio,
        "circulating_market_value": q.circulating_market_value,
        "total_market_value": q.total_market_value,
    }


def futures_quote_rows(md, codes: list[str], now=None) -> list[dict]:
    """将连续期货代码解析为近月合约,并把报价对应回连续代码。"""
    from datetime import datetime

    from src.platform.marketdata import futures

    current = now
    if current is None:
        from zoneinfo import ZoneInfo

        current = datetime.now(ZoneInfo("Asia/Taipei"))

    resolved = []
    seen = set()
    for raw_code in codes:
        code = str(raw_code).strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        contract = futures.resolve_contract(code, current)
        if contract is not None:
            resolved.append((code, contract.symbol, contract.product))
    if not resolved:
        return []

    quotes = md.quotes([contract for _, contract, _ in resolved], market="TWF")
    quotes_by_contract = {quote.symbol: quote for quote in quotes}
    rows = []
    for code, contract, product in resolved:
        quote = quotes_by_contract.get(contract)
        if quote is None:
            continue
        row = _quote_to_row(quote)
        row["symbol"] = code
        row["name"] = product.name
        row["contract"] = quote.contract or contract
        row["session"] = quote.session
        rows.append(row)
    return rows


def md_quote_rows(symbols: list[str], market: str) -> list[dict]:
    """批量报价,返回 list[dict](与旧 orchestrator 输出同形)。

    同步函数;async 调用方用 `await asyncio.to_thread(md_quote_rows, ...)`。
    """
    syms = list(symbols)
    if not syms:
        return []
    md = get_market_data()
    if market == "TWF":
        return futures_quote_rows(md, syms)
    quotes = md.quotes(syms, market=market)
    return [_quote_to_row(q) for q in quotes]


def _article_to_newsitem(a):
    """marketdata.NewsArticle → host NewsItem(同名字段直拷)。

    lazy import 避免与 news_collector 的模块级循环引用(news_collector 会
    在模块级 import 本模块的 md_news)。
    """
    from src.platform.marketdata.collectors.news_collector import NewsItem

    return NewsItem(
        source=a.source,
        external_id=a.external_id,
        title=a.title,
        content=a.content,
        publish_time=a.publish_time,
        symbols=a.symbols,
        importance=a.importance,
        url=a.url,
    )


def md_news(
    symbols: list[str], since_hours: int = 2, names: dict[str, str] | None = None,
    markets: dict[str, str] | None = None,
) -> list:
    """聚合新闻(个股新闻 + 公告),返回 list[NewsItem](与旧 NewsCollector.fetch_all 同形)。

    host 侧可以用 datetime.now() 做 since 过滤(包内不允许偷偷调 datetime.now(),
    必须由调用方显式传 now)。

    同步函数;async 调用方用 `await asyncio.to_thread(md_news, ...)`。
    """
    from datetime import datetime, timezone

    # 包内 news vendor 的 publish_time 是 aware(UTC);这里的 now 也必须 aware,
    # 否则 since 过滤会 "can't compare offset-naive and offset-aware datetimes"。
    md = get_market_data()
    symbol_list = list(symbols or [])
    now = datetime.now(timezone.utc)
    if markets is None:
        arts = md.news(
            symbol_list, since_hours=since_hours, names=names, now=now,
        )
        return [_article_to_newsitem(a) for a in arts]

    # 查不到市场的代码归入 None 组:不传 market,沿用包内默认(与旧调用方一致)
    symbols_by_market: dict[str | None, list[str]] = {}
    for symbol in symbol_list:
        symbols_by_market.setdefault(markets.get(symbol) or None, []).append(symbol)

    articles = []
    for market, market_symbols in symbols_by_market.items():
        market_names = {
            symbol: names[symbol]
            for symbol in market_symbols
            if names and symbol in names
        }
        market_kwargs = {"market": market} if market else {}
        articles.extend(md.news(
            market_symbols,
            since_hours=since_hours,
            names=market_names or None,
            now=now,
            **market_kwargs,
        ))

    seen = set()
    unique_articles = []
    for article in articles:
        if article.external_id in seen:
            continue
        seen.add(article.external_id)
        unique_articles.append(article)
    unique_articles.sort(key=lambda article: article.publish_time, reverse=True)
    return [_article_to_newsitem(a) for a in unique_articles]


def md_news_by_keyword(keyword: str) -> list:
    """按关键词(行业/主题词)搜中文新闻,返回 list[NewsItem]。同步。"""
    arts = get_market_data().news_by_keyword(keyword)
    return [_article_to_newsitem(a) for a in arts]


def md_stock_data(symbols: list[str], market: str) -> list:
    """返回 list[StockData](旧 AkshareCollector.get_stock_data 同形)。同步。"""
    from src.platform.marketdata.models import MarketCode, StockData

    syms = list(symbols)
    if not syms:
        return []
    quotes = get_market_data().quotes(syms, market=market)
    return [StockData(
        symbol=q.symbol, name=q.name or "", market=MarketCode(q.market),
        current_price=q.current_price or 0.0, change_pct=q.change_pct or 0.0,
        change_amount=q.change_amount or 0.0, volume=q.volume or 0.0,
        turnover=q.turnover or 0.0, open_price=q.open_price or 0.0,
        high_price=q.high_price or 0.0, low_price=q.low_price or 0.0,
        prev_close=q.prev_close or 0.0, contract=q.contract, session=q.session)
        for q in quotes]
