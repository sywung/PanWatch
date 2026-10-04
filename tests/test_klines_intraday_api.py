import pytest

from marketdata.types import Bar
from src.modules.market.api import klines
from src.platform.marketdata.collectors.kline_collector import KlineData
from src.platform.marketdata.models import MARKETS, MarketCode


@pytest.mark.parametrize("interval", ["5m", "15m", "30m", "60m"])
def test_intraday_intervals_use_marketdata(interval, monkeypatch):
    klines._INTRADAY_CACHE.clear()
    calls = []

    class FakeMarketData:
        def intraday_klines(self, symbol, *, market, interval):
            calls.append((symbol, market, interval))
            return [Bar(date="2026-10-01 09:00", open=1, close=2, high=3, low=0.5, volume=10)]

    monkeypatch.setattr(klines, "get_market_data", lambda: FakeMarketData())

    result = klines.get_klines("2330", market="TW", days=1, interval=interval)

    assert calls == [("2330", "TW", interval)]
    assert result["interval"] == interval
    assert result["klines"] == [
        {"date": "2026-10-01 09:00", "open": 1, "close": 2, "high": 3, "low": 0.5, "volume": 10}
    ]


def test_one_minute_interval_remains_monthly_aggregation(monkeypatch):
    klines._INTRADAY_CACHE.clear()
    calls = []

    def daily_bars(self, symbol, days):
        calls.append((symbol, days))
        return [
            KlineData(date="2026-10-01", open=1, close=2, high=3, low=0.5, volume=10),
            KlineData(date="2026-10-02", open=2, close=4, high=5, low=1, volume=20),
        ]

    monkeypatch.setattr(klines.KlineCollector, "get_klines", daily_bars)
    monkeypatch.setattr(klines, "get_market_data", lambda: pytest.fail("1m must not request intraday data"))

    result = klines.get_klines("2330", market="TW", days=250, interval="1m")

    assert calls == [("2330", 250)]
    assert result["klines"] == [
        {"date": "2026-10-02", "open": 1, "close": 4, "high": 5, "low": 0.5, "volume": 30}
    ]


def test_daily_interval_keeps_collector_path(monkeypatch):
    calls = []

    def daily_bars(self, symbol, days):
        calls.append((symbol, days))
        return [KlineData(date="2026-10-01", open=1, close=2, high=3, low=0.5, volume=10)]

    monkeypatch.setattr(klines.KlineCollector, "get_klines", daily_bars)
    monkeypatch.setattr(klines, "get_market_data", lambda: pytest.fail("daily bars use KlineCollector"))

    result = klines.get_klines("2330", market="TW", days=500, interval="1d")

    assert calls == [("2330", 500)]
    assert result["klines"][0]["date"] == "2026-10-01"


def test_intraday_cache_uses_trading_ttl_and_expires(monkeypatch):
    klines._INTRADAY_CACHE.clear()
    calls = []
    clock = [1000.0]

    class FakeMarketData:
        def intraday_klines(self, symbol, *, market, interval):
            calls.append(symbol)
            return [Bar(date=f"2026-10-01 09:{len(calls):02d}", open=1, close=2, high=3, low=0.5, volume=10)]

    monkeypatch.setattr(klines, "get_market_data", lambda: FakeMarketData())
    monkeypatch.setattr(klines.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(MARKETS[MarketCode.TW], "is_trading_time", lambda: True)

    first = klines.get_klines("2330", market="TW", interval="30m")
    second = klines.get_klines("2330", market="TW", interval="30m")
    assert calls == ["2330"]
    assert first["klines"] == second["klines"]

    clock[0] += klines._INTRADAY_TTL_TRADING_S + 1
    third = klines.get_klines("2330", market="TW", interval="30m")
    assert calls == ["2330", "2330"]
    assert third["klines"][0]["date"].endswith("02")


def test_intraday_cache_uses_closed_market_ttl(monkeypatch):
    klines._INTRADAY_CACHE.clear()
    monkeypatch.setattr(MARKETS[MarketCode.TW], "is_trading_time", lambda: False)
    monkeypatch.setattr(klines.time, "monotonic", lambda: 1000.0)

    class FakeMarketData:
        def intraday_klines(self, symbol, *, market, interval):
            return [Bar(date="2026-10-01 09:00", open=1, close=2, high=3, low=0.5, volume=10)]

    monkeypatch.setattr(klines, "get_market_data", lambda: FakeMarketData())
    klines.get_klines("2330", market="TW", interval="5m")

    expiry, _ = klines._INTRADAY_CACHE["TW:2330:5m"]
    assert expiry == 1000.0 + klines._INTRADAY_TTL_CLOSED_S


def test_intraday_cache_does_not_cache_failures(monkeypatch):
    klines._INTRADAY_CACHE.clear()
    calls = []

    class FailingMarketData:
        def intraday_klines(self, symbol, *, market, interval):
            calls.append(symbol)
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(klines, "get_market_data", lambda: FailingMarketData())
    for _ in range(2):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            klines.get_klines("2330", market="TW", interval="15m")

    assert calls == ["2330", "2330"]
    assert "TW:2330:15m" not in klines._INTRADAY_CACHE


def test_batch_endpoint_uses_shared_intraday_path(monkeypatch):
    klines._INTRADAY_CACHE.clear()
    calls = []

    class FakeMarketData:
        def intraday_klines(self, symbol, *, market, interval):
            calls.append((symbol, market, interval))
            return [Bar(date="2026-10-01 09:00", open=1, close=2, high=3, low=0.5, volume=10)]

    monkeypatch.setattr(klines, "get_market_data", lambda: FakeMarketData())
    payload = klines.KlineBatchRequest(items=[
        klines.KlineItem(symbol="2330", market="TW", days=1, interval="30m")
    ])

    result = klines.get_klines_batch(payload)

    assert calls == [("2330", "TW", "30m")]
    assert result[0]["interval"] == "30m"
    assert result[0]["klines"][0]["date"] == "2026-10-01 09:00"


def test_empty_intraday_result_is_not_cached(monkeypatch):
    klines._INTRADAY_CACHE.clear()
    responses = [[], [Bar(date="2026-10-01 09:00", open=1, close=2, high=3, low=0.5, volume=10)]]
    calls = []

    class FakeMarketData:
        def intraday_klines(self, symbol, *, market, interval):
            calls.append(symbol)
            return responses[len(calls) - 1]

    monkeypatch.setattr(klines, "get_market_data", lambda: FakeMarketData())
    monkeypatch.setattr(klines.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(MARKETS[MarketCode.TW], "is_trading_time", lambda: False)

    assert klines.get_klines("2330", market="TW", interval="30m")["klines"] == []
    retry = klines.get_klines("2330", market="TW", interval="30m")
    assert calls == ["2330", "2330"]
    assert len(retry["klines"]) == 1
