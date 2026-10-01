"""台股新闻、快讯与注意股资料 vendor。"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from marketdata.symbol import Symbol
from marketdata.types import DragonTigerItem, FlashNews, NewsArticle
from marketdata.vendors import tw_bulk
from marketdata.vendors.base import DragonTigerVendor, FlashNewsVendor, NewsVendor
from marketdata.vendors.tw_common import _code, _f, _rows


class TwseDragonTigerVendor(DragonTigerVendor):
    """TWSE 注意股/处置股；合并 ``announcement/notice`` 与 ``announcement/punish``。

    来源：https://openapi.twse.com.tw/v1/announcement/notice 与 /announcement/punish，
    价格单位为元；与 A 股龙虎榜同型别但不是营业部买卖明细，只有台湾公告原因。
    """

    name = "twse"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[DragonTigerItem]:
        day = (config or {}).get("date")
        if not day:
            return []
        result = []
        for suffix, prefix, reason_key, close_key in (
            ("announcement/notice", "注意股：", "TradingInfoForAttention", "ClosingPrice"),
            ("announcement/punish", "處置股：", "ReasonsOfDisposition", None),
        ):
            for row in _rows("https://openapi.twse.com.tw/v1/" + suffix):
                roc_day = (f"{int(day[:4]) - 1911:03d}{day[5:7]}{day[8:10]}"
                           if len(day) == 10 else "")
                period = str(row.get("DispositionPeriod") or "").replace("/", "")
                dates = re.findall(r"\d{7}", period)
                in_period = len(dates) == 2 and dates[0] <= roc_day <= dates[1]
                if tw_bulk.tw_date(row.get("Date")) != day and not (
                    suffix.endswith("punish") and in_period
                ):
                    continue
                code = _code(row.get("Code"))
                if tw_bulk.valid_code(code):
                    reason = prefix + str(row.get(reason_key) or "")
                    if not close_key:
                        reason += " " + str(row.get("DispositionPeriod") or "")
                    result.append(DragonTigerItem(
                        trade_date=day, symbol=code, name=str(row.get("Name") or ""),
                        reason=reason, close=_f(row.get(close_key)) if close_key else None,
                    ))
        return result


class YahooTwNewsVendor(NewsVendor):
    """Yahoo 奇摩 RSS 台股新闻；分别尝试上市 ``.TW`` 与上柜 ``.TWO`` 后合并。

    来源：https://tw.stock.yahoo.com/rss，新闻单位为元；字段与 A 股新闻同型，
    但这是台股 Yahoo 新闻流，不是公告或 A 股财经新闻源。
    """

    name = "yahoo_tw"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[NewsArticle]:
        result = []
        for symbol in symbols:
            hint = getattr(__import__("marketdata.vendors.kline", fromlist=["_TW_SUFFIX_HINT"]),
                           "_TW_SUFFIX_HINT", {})
            suffixes = (".TWO", ".TW") if symbol.code in hint else (".TW", ".TWO")
            for suffix in suffixes:
                try:
                    root = ET.fromstring(tw_bulk.get_text(
                        "https://tw.stock.yahoo.com/rss", {"s": symbol.code + suffix}
                    ))
                    items = root.findall("./channel/item")
                except Exception:
                    continue
                if items:
                    result.extend(NewsArticle(
                        source="yahoo_tw", external_id=item.findtext("link", ""),
                        title=item.findtext("title", ""),
                        content=html.unescape(re.sub(
                            r"<[^>]+>", "", item.findtext("description", "")
                        )),
                        publish_time=parsedate_to_datetime(
                            item.findtext("pubDate", "")
                        ).astimezone(timezone.utc),
                        symbols=[symbol.code], url=item.findtext("link", ""),
                    ) for item in items)
                    break
        return result


class CnyesFlashNewsVendor(FlashNewsVendor):
    """鉅亨台股快讯；不区分上市/上柜，回传同一新闻流，时间为 UTC、价格为元。

    来源：https://api.cnyes.com/media/api/v1/newslist/category/tw_stock；字段与 A 股
    FlashNews 同型，但内容是台股市场快讯，不是 A 股主力或公告数据。
    """

    name = "cnyes"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[FlashNews]:
        limit = max(1, min(int((config or {}).get("days") or 30), 100))
        data = tw_bulk.get_json(
            "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock",
            {"limit": limit},
        )
        result = []
        for row in ((data.get("items") or {}).get("data") or []):
            result.append(FlashNews(
                source="cnyes", external_id=str(row.get("newsId")),
                title=str(row.get("title") or ""),
                content=re.sub(r"<[^>]+>", "", html.unescape(
                    str(row.get("content") or row.get("summary") or "")
                )),
                publish_time=datetime.fromtimestamp(
                    int(row.get("publishAt") or 0), tz=timezone.utc
                ),
                url=f"https://news.cnyes.com/news/id/{row.get('newsId')}",
            ))
        return result
