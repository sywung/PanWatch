"""yuantaData vendor: 離線假 HTTP 測試，涵蓋 API 狀態、時區與 failover。"""

from datetime import datetime
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pytest

import marketdata.vendors.yuantadata as yd
from marketdata.client import MarketData
from marketdata.defaults import StaticConfigProvider
from marketdata.ports import SourceConfig
from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.symbol import Symbol

BASE = "http://yuantadata:8090"
CFG = {"base_url": BASE, "token": "secret", "wait_seconds": 12, "days": 2}
TW = ZoneInfo("Asia/Taipei")


class Response:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


def _bar(ts, open_=1, high=3, low=0, close=2, volume=10):
    return {"ts": ts, "open": open_, "high": high, "low": low,
            "close": close, "volume": volume, "source": "yuanta_spark"}


def _utc_for_local(day, hour, minute=0):
    local = datetime.fromisoformat(f"{day} {hour:02d}:{minute:02d}").replace(tzinfo=TW)
    return local.astimezone(ZoneInfo("UTC")).isoformat()


@pytest.fixture(autouse=True)
def clear_market_cache():
    with yd._MARKET_CACHE_LOCK:
        yd._MARKET_CACHE.clear()


def install_http(monkeypatch, responder):
    calls = []

    def fake(url, **kwargs):
        call = {"url": url, **kwargs}
        calls.append(call)
        return responder(url, kwargs)

    monkeypatch.setattr(yd, "market_get", fake)
    return calls


def _symbols_response(*rows):
    return Response(200, {"total": len(rows), "symbols": list(rows)})


def _market_row(code="2330", market="TSE"):
    return {"symbol": code, "market": market, "name": "台積電"}


def test_daily_bars_parse_taipei_date_raw_volume_strings_and_trim(monkeypatch):
    rows = [
        _bar("2026-09-28T16:00:00+00:00", "1.1", "2.1", "0.1", "1.5", 101),
        _bar("2026-09-29T16:00:00+00:00", "2.1", "3.1", "1.1", "2.5", 102),
        _bar("2026-09-30T16:00:00+00:00", "3.1", "4.1", "2.1", "3.5", 103),
    ]

    def respond(url, kwargs):
        if url.endswith("/symbols"):
            return _symbols_response(_market_row())
        return Response(200, {"complete": True, "bars": rows})

    calls = install_http(monkeypatch, respond)
    bars = yd.YuantaDataKlineVendor().fetch([Symbol.parse("2330", "TW")], CFG)
    assert [bar.date for bar in bars] == ["2026-09-30", "2026-10-01"]
    assert bars[-1].volume == 103
    assert bars[-1].open == 3.1 and bars[-1].close == 3.5
    bars_call = next(call for call in calls if "/bars/" in call["url"])
    assert bars_call["params"]["timeframe"] == "1d"
    assert bars_call["params"]["from"].endswith("+08:00")
    assert bars_call["params"]["to"].endswith("+08:00")
    assert bars_call["params"]["fetch"] is True and bars_call["params"]["wait"] == 12
    assert bars_call["headers"] == {"Authorization": "Bearer secret"}
    assert bars_call["trust_env"] is False and bars_call["timeout"] == 22


def test_daily_incomplete_response_discards_partial_bars(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: (
        _symbols_response(_market_row()) if url.endswith("/symbols") else
        Response(200, {"complete": False, "bars": [_bar("2026-09-30T16:00:00Z")]})
    ))
    bars = yd.YuantaDataKlineVendor().fetch([Symbol.parse("2330", "TW")], CFG)
    assert bars == []
    assert sum("/bars/" in call["url"] for call in calls) == 1


def test_market_resolution_only_accepts_exact_symbol_and_caches_success(monkeypatch):
    counts = {"symbols": 0, "bars": 0}

    def respond(url, kwargs):
        if url.endswith("/symbols"):
            counts["symbols"] += 1
            assert kwargs["params"] == {"q": "2330", "limit": 20}
            return _symbols_response(_market_row("23301", "OTC"), _market_row("2330", "TSE"))
        counts["bars"] += 1
        assert kwargs["params"]["market"] == "TSE"
        return Response(200, {"complete": True, "bars": [_bar("2026-09-30T16:00:00Z")]})

    install_http(monkeypatch, respond)
    vendor = yd.YuantaDataKlineVendor()
    symbol = [Symbol.parse("2330", "TW")]
    assert len(vendor.fetch(symbol, CFG)) == 1
    assert len(vendor.fetch(symbol, CFG)) == 1
    assert counts == {"symbols": 1, "bars": 2}


_UNRESOLVABLE = [[], [_market_row("23301", "TSE")],
                 [_market_row("2330", "TSE"), _market_row("2330", "OTC")]]


@pytest.mark.parametrize("rows", _UNRESOLVABLE, ids=["missing", "prefix-only", "ambiguous"])
def test_unresolved_symbol_never_requests_intraday_bars(monkeypatch, rows):
    calls = install_http(monkeypatch, lambda url, kw: (
        _symbols_response(*rows) if url.endswith("/symbols") else
        pytest.fail("must never request bars without an exact market")
    ))
    vendor = yd.YuantaDataKlineVendor()
    assert vendor.fetch_intraday("2330", "30m", CFG) == []
    assert vendor.fetch_intraday("2330", "1m", CFG) == []
    assert not any("/bars/" in call["url"] for call in calls)


@pytest.mark.parametrize("rows", _UNRESOLVABLE, ids=["missing", "prefix-only", "ambiguous"])
def test_unknown_symbol_never_requests_bars(monkeypatch, rows):
    calls = install_http(monkeypatch, lambda url, kw: (
        _symbols_response(*rows) if url.endswith("/symbols") else
        pytest.fail("must never request bars without an exact market")
    ))
    vendor = yd.YuantaDataKlineVendor()
    symbol = [Symbol.parse("2330", "TW")]
    assert vendor.fetch(symbol, CFG) == []
    assert vendor.fetch(symbol, CFG) == []
    assert sum(call["url"].endswith("/symbols") for call in calls) == 1
    assert not any("/bars/" in call["url"] for call in calls)


def test_negative_market_cache_expires_after_ten_minutes(monkeypatch):
    clock = [0.0]
    symbol_calls = []
    monkeypatch.setattr(yd, "_monotonic", lambda: clock[0])

    def respond(url, kwargs):
        symbol_calls.append(url)
        return _symbols_response()

    install_http(monkeypatch, respond)
    vendor = yd.YuantaDataKlineVendor()
    symbols = [Symbol.parse("9999", "TW")]
    assert vendor.fetch(symbols, CFG) == []
    assert vendor.fetch(symbols, CFG) == []
    assert len(symbol_calls) == 1
    clock[0] = 601.0
    assert vendor.fetch(symbols, CFG) == []
    assert len(symbol_calls) == 2


def test_ambiguous_tse_otc_symbol_never_requests_bars(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: (
        _symbols_response(_market_row("2330", "TSE"), _market_row("2330", "OTC"))
        if url.endswith("/symbols") else pytest.fail("ambiguous code must not start bars fetch")
    ))
    assert yd.YuantaDataKlineVendor().fetch([Symbol.parse("2330", "TW")], CFG) == []
    assert not any("/bars/" in call["url"] for call in calls)


@pytest.mark.parametrize(("interval", "timeframe"), [("1m", "1m"), ("5m", "5m")])
def test_intraday_1m_and_5m_keep_taipei_bar_start(interval, timeframe, monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: (
        _symbols_response(_market_row()) if url.endswith("/symbols") else
        Response(200, {"complete": True, "bars": [
            _bar("2026-10-01T01:00:00+00:00", "100.2", "101", "99", "100.5", "125000")
        ]})
    ))
    monkeypatch.setattr(yd, "_now", lambda: datetime(2026, 10, 3, 12, tzinfo=TW))
    bars = yd.YuantaDataKlineVendor().fetch_intraday("2330", interval, CFG)
    assert [bar.date for bar in bars] == ["2026-10-01 09:00"]
    assert bars[0].volume == 125000 and bars[0].open == 100.2
    request = next(call for call in calls if "/bars/" in call["url"])
    assert request["params"]["timeframe"] == timeframe
    assert request["params"]["from"].endswith("+08:00")


def test_30m_aggregation_ohlcv_anchor_lunch_and_day_boundaries(monkeypatch):
    rows = []
    for minute in range(0, 60, 5):
        n = minute // 5 + 1
        rows.append(_bar(_utc_for_local("2026-10-01", 9, minute), n, n + 10, n - 10, n + 1, n * 10))
    for minute in range(0, 30, 5):
        n = 20 + minute // 5
        rows.append(_bar(_utc_for_local("2026-10-01", 13, minute), n, n + 10, n - 10, n + 1, n * 10))
    rows.append(_bar(_utc_for_local("2026-10-02", 9), 50, 55, 48, 53, 7))
    install_http(monkeypatch, lambda url, kw: (
        _symbols_response(_market_row()) if url.endswith("/symbols") else
        Response(200, {"complete": True, "bars": rows})
    ))
    monkeypatch.setattr(yd, "_now", lambda: datetime(2026, 10, 3, 12, tzinfo=TW))
    bars = yd.YuantaDataKlineVendor().fetch_intraday("2330", "30m", CFG)
    assert [bar.date for bar in bars] == [
        "2026-10-01 09:00", "2026-10-01 09:30", "2026-10-01 13:00", "2026-10-02 09:00"
    ]
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close, bars[0].volume) == (1, 16, -9, 7, 210)
    assert (bars[1].open, bars[1].close, bars[1].volume) == (7, 13, 570)
    assert bars[2].open == 20 and bars[2].close == 26 and bars[2].volume == 1350
    assert bars[3].volume == 7


def test_60m_aggregation_groups_by_hour_from_nine(monkeypatch):
    rows = [
        _bar(_utc_for_local("2026-10-03", 9, m), i + 1, i + 5, i, i + 2, 2)
        for i, m in enumerate(range(0, 60, 5))
    ]
    rows.append(_bar(_utc_for_local("2026-10-03", 10), 30, 33, 29, 32, 4))
    install_http(monkeypatch, lambda url, kw: (
        _symbols_response(_market_row()) if url.endswith("/symbols") else
        Response(200, {"complete": True, "bars": rows})
    ))
    monkeypatch.setattr(yd, "_now", lambda: datetime(2026, 10, 4, 12, tzinfo=TW))
    bars = yd.YuantaDataKlineVendor().fetch_intraday("2330", "60m", CFG)
    assert [bar.date for bar in bars] == ["2026-10-03 09:00", "2026-10-03 10:00"]
    assert (bars[0].open, bars[0].high, bars[0].low, bars[0].close, bars[0].volume) == (1, 16, 0, 13, 24)


def test_intraday_incomplete_response_returns_empty(monkeypatch):
    install_http(monkeypatch, lambda url, kw: (
        _symbols_response(_market_row()) if url.endswith("/symbols") else
        Response(200, {"complete": False, "bars": [_bar("2026-10-05T01:00:00Z")]})
    ))
    monkeypatch.setattr(yd, "_now", lambda: datetime(2026, 10, 5, 10, tzinfo=TW))
    assert yd.YuantaDataKlineVendor().fetch_intraday("2330", "5m", CFG) == []


@pytest.mark.parametrize("now", [
    datetime(2026, 10, 5, 10, tzinfo=TW),  # Monday in session
])
def test_weekday_session_without_today_bar_returns_empty(now, monkeypatch):
    install_http(monkeypatch, lambda url, kw: (
        _symbols_response(_market_row()) if url.endswith("/symbols") else
        Response(200, {"complete": True, "bars": [_bar("2026-10-02T01:00:00Z")]})
    ))
    monkeypatch.setattr(yd, "_now", lambda: now)
    assert yd.YuantaDataKlineVendor().fetch_intraday("2330", "5m", CFG) == []


@pytest.mark.parametrize(("now", "previous_day"), [
    (datetime(2026, 10, 10, 10, tzinfo=TW), "2026-10-09"),  # Saturday
    (datetime(2026, 10, 5, 8, 30, tzinfo=TW), "2026-10-02"),  # before session
])
def test_weekend_or_preopen_can_return_previous_bars(now, previous_day, monkeypatch):
    install_http(monkeypatch, lambda url, kw: (
        _symbols_response(_market_row()) if url.endswith("/symbols") else
        Response(200, {"complete": True, "bars": [_bar(f"{previous_day}T01:00:00Z")]})
    ))
    monkeypatch.setattr(yd, "_now", lambda: now)
    bars = yd.YuantaDataKlineVendor().fetch_intraday("2330", "5m", CFG)
    assert [bar.date for bar in bars] == [f"{previous_day} 09:00"]


def test_intraday_rejects_unsupported_intervals_without_http(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: pytest.fail("unexpected HTTP call"))
    assert yd.YuantaDataKlineVendor().fetch_intraday("2330", "2h", CFG) == []
    assert calls == []


def test_quotes_parse_zero_fields_lots_and_skip_nonpositive_price(monkeypatch):
    rows = [
        {"symbol": "2330", "name": "台積電", "price": "100.5", "prev_close": 0,
         "open": 0, "high": "102", "low": 0, "volume_lots": "1234", "bid": 0, "ask": 0},
        {"symbol": "6488", "name": "環球晶", "price": 0, "prev_close": 90, "volume_lots": 20},
    ]
    calls = install_http(monkeypatch, lambda url, kw: Response(200, {"data": rows}))
    quotes = yd.YuantaDataQuoteVendor().fetch(
        [Symbol.parse("2330", "TW"), Symbol.parse("6488", "TW")], CFG
    )
    assert len(calls) == 1 and calls[0]["params"] == {"symbols": "2330,6488"}
    assert len(quotes) == 1
    quote = quotes[0]
    assert quote.current_price == 100.5 and quote.prev_close is None
    assert quote.open_price is None and quote.high_price == 102 and quote.low_price is None
    assert quote.volume == 1234 and quote.change_amount is None and quote.change_pct is None


def test_quotes_deduplicate_and_batch_120_symbols_into_50_50_20(monkeypatch):
    calls = install_http(monkeypatch, lambda url, kw: Response(200, {"data": []}))
    symbols = [Symbol.parse(f"{1000 + i}", "TW") for i in range(120)]
    symbols += [Symbol.parse("1000", "TW")]
    assert yd.YuantaDataQuoteVendor().fetch(symbols, CFG) == []
    assert [len(call["params"]["symbols"].split(",")) for call in calls] == [50, 50, 20]


def test_quotes_503_raises_for_engine_failover(monkeypatch):
    install_http(monkeypatch, lambda url, kw: Response(503, {"detail": "gateway down"}))
    with pytest.raises(RuntimeError, match="503"):
        yd.YuantaDataQuoteVendor().fetch([Symbol.parse("2330", "TW")], CFG)


def test_quote_http_400_retries_codes_individually_and_keeps_valid_quotes(monkeypatch):
    calls = []

    def respond(url, kwargs):
        codes = kwargs["params"]["symbols"].split(",")
        calls.append(codes)
        if len(codes) > 1 or codes == ["6488"]:
            return Response(400, {"detail": "invalid or ambiguous"})
        return Response(200, {"data": [{"symbol": codes[0], "price": 10,
                                         "prev_close": 9, "volume_lots": 3}]})

    install_http(monkeypatch, respond)
    quotes = yd.YuantaDataQuoteVendor().fetch(
        [Symbol.parse(code, "TW") for code in ("2330", "6488", "8069")], CFG
    )
    assert calls == [["2330", "6488", "8069"], ["2330"], ["6488"], ["8069"]]
    assert [quote.symbol for quote in quotes] == ["2330", "8069"]


def _md(sources):
    return MarketData(config=StaticConfigProvider({"kline": sources}))


def test_intraday_client_uses_enabled_yuantadata_and_skips_yahoo(monkeypatch):
    calls = []
    expected = [yd.Bar(date="2026-10-02 09:00", open=1, high=2, low=1, close=2, volume=5)]
    monkeypatch.setattr(yd.YuantaDataKlineVendor, "fetch_intraday",
                        lambda self, code, interval, config: calls.append((code, interval)) or expected)
    import marketdata.vendors.kline as kv
    monkeypatch.setattr(kv, "market_get", lambda *a, **kw: pytest.fail("Yahoo should not run"))
    result = _md([SourceConfig(vendor="yuantadata", priority=22,
                               config={"intraday": True, "base_url": BASE})]).intraday_klines(
                                   "2330", market="TW", interval="30m")
    assert result == expected and calls == [("2330", "30m")]


def test_intraday_client_falls_back_to_yahoo_when_yuantadata_is_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(yd.YuantaDataKlineVendor, "fetch_intraday",
                        lambda *args: calls.append("yuantadata") or [])
    import marketdata.vendors.kline as kv
    yahoo_calls = []
    monkeypatch.setattr(kv, "market_get", lambda url, **kwargs: yahoo_calls.append(url) or {
        "chart": {"result": [{"timestamp": [1790902800], "indicators": {"quote": [{
            "open": [1], "close": [2], "high": [3], "low": [0], "volume": [4]
        }]}}]}
    })
    result = _md([SourceConfig(vendor="yuantadata", priority=22,
                               config={"intraday": True, "base_url": BASE})]).intraday_klines(
                                   "2330", market="TW", interval="5m")
    assert calls == ["yuantadata"] and yahoo_calls
    assert len(result) == 1 and result[0].open == 1 and result[0].volume == 4


def test_intraday_client_does_not_call_vendor_when_flag_disabled(monkeypatch):
    monkeypatch.setattr(yd.YuantaDataKlineVendor, "fetch_intraday",
                        lambda *args: pytest.fail("intraday=false must skip yuantaData"))
    import marketdata.vendors.kline as kv
    monkeypatch.setattr(kv, "market_get", lambda *a, **kw: None)
    _md([SourceConfig(vendor="yuantadata", priority=22,
                      config={"intraday": False, "base_url": BASE})]).intraday_klines(
                          "2330", market="TW", interval="5m")


def test_intraday_client_tries_yuantadata_then_yuanta_in_source_order(monkeypatch):
    import marketdata.vendors.yuanta as legacy

    calls = []
    expected = [yd.Bar(date="2026-10-02 09:00", open=1, high=2, low=1, close=2, volume=5)]
    monkeypatch.setattr(yd.YuantaDataKlineVendor, "fetch_intraday",
                        lambda *args: calls.append("yuantadata") or [])
    monkeypatch.setattr(legacy.YuantaKlineVendor, "fetch_intraday",
                        lambda *args: calls.append("yuanta") or expected)
    import marketdata.vendors.kline as kv
    monkeypatch.setattr(kv, "market_get", lambda *a, **kw: pytest.fail("Yahoo should not run"))
    md = _md([
        SourceConfig(vendor="yuantadata", priority=22, config={"intraday": True, "base_url": BASE}),
        SourceConfig(vendor="yuanta", priority=23, config={"intraday": True, "base_url": BASE}),
    ])
    assert md.intraday_klines("2330", market="TW", interval="30m") == expected
    assert calls == ["yuantadata", "yuanta"]


def test_sources_include_disabled_seeds_priorities_and_registry_entries():
    repo_root = str(Path(__file__).resolve().parents[3])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    import server

    seeds = {(row["type"], row["provider"]): row for row in server.DATA_SOURCE_SEEDS}
    kline = seeds[("kline", "yuantadata")]
    quote = seeds[("quote", "yuantadata")]
    assert kline["enabled"] is False and kline["priority"] == 22
    assert kline["config"]["wait_seconds"] == 0 and kline["config"]["intraday"] is True
    assert kline["test_symbols"] == list(server.DEFAULT_TEST_SYMBOLS_BY_MARKET["TW"])
    assert quote["enabled"] is False and quote["priority"] > next(
        row["priority"] for row in server.DATA_SOURCE_SEEDS
        if row["type"] == "quote" and row["provider"] == "twse"
    )
    assert quote["supports_batch"] is True and quote["test_symbols"] == ["2330", "6488"]
    assert next(row["priority"] for row in server.DATA_SOURCE_SEEDS
                if row["type"] == "kline" and row["provider"] == "yahoo") < kline["priority"]
    assert kline["priority"] < next(row["priority"] for row in server.DATA_SOURCE_SEEDS
                                     if row["type"] == "kline" and row["provider"] == "finmind")
    assert VENDOR_CLASSES_BY_TYPE["quote"]["yuantadata"] is yd.YuantaDataQuoteVendor
    assert VENDOR_CLASSES_BY_TYPE["kline"]["yuantadata"] is yd.YuantaDataKlineVendor


def test_wait_defaults_to_zero_so_callers_never_block():
    assert yd._wait_seconds({}) == 0
    assert yd._timeout({}) == 10
