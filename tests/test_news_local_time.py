"""新闻时间在 host 边界统一转成应用时区(naive 本地时间)。

浏览器验收(2026-10-02)看到:Yahoo 奇摩「台股开盘小涨」显示 01:23——包内 vendor 回 UTC aware,
各消费方直接 strftime,画面慢 8 小时。旧版 NewsCollector 给的是 naive 本地时间。
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from marketdata.types import NewsArticle

from src.platform.marketdata import marketdata_client


def _article(publish_time):
    return NewsArticle(source="yahoo_tw", external_id="x", title="t", content="",
                       publish_time=publish_time, symbols=["2330"])


def test_utc_news_time_converted_to_app_timezone(monkeypatch):
    """UTC 01:23 在 TZ=Asia/Taipei 下显示为 09:23(naive)。"""
    monkeypatch.setenv("TZ", "Asia/Taipei")

    item = marketdata_client._article_to_newsitem(
        _article(datetime(2026, 10, 2, 1, 23, tzinfo=timezone.utc)))

    assert item.publish_time == datetime(2026, 10, 2, 9, 23)
    assert item.publish_time.tzinfo is None


def test_beijing_news_time_same_wall_clock_in_taipei(monkeypatch):
    """东财北京时间 09:30 与台北同为 UTC+8,显示仍是 09:30。"""
    monkeypatch.setenv("TZ", "Asia/Taipei")

    item = marketdata_client._article_to_newsitem(
        _article(datetime(2026, 10, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))))

    assert item.publish_time == datetime(2026, 10, 2, 9, 30)


def test_naive_news_time_left_as_is(monkeypatch):
    """naive 时间(无时区信息)原样保留,不猜测时区。"""
    monkeypatch.setenv("TZ", "Asia/Taipei")

    item = marketdata_client._article_to_newsitem(_article(datetime(2026, 10, 2, 9, 30)))

    assert item.publish_time == datetime(2026, 10, 2, 9, 30)
