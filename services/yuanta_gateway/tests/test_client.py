"""元大转接服务的客户端层:连线、登入、请求/回应配对、限速、资料转换。

元大 SparkAPI 的所有回应都经同一个 OnResponse(intMark, dwIndex, strIndex, objHandle, objValue) 事件回来,
strIndex 是功能名(Login / GetWatchListAll / GetKLine ...);呼叫端要等对应功能的回应。
安控限制(操作说明「四、安控限制说明」):登入失败后至少隔 4 秒;同功能报价/帐务类每秒 3 次;GetKLine 每秒 1 次;
GetWatchListAll 单次最多 600 档。
"""

from __future__ import annotations

import threading
from datetime import date

import pytest

from fakes import FakeAdapter, NetList, login_fail, login_ok, watch_row
from types import SimpleNamespace

import client as yc

CREDS = dict(account="S98875005091", password="pw", pfx_path="/config/cert.pfx", pfx_password="pfxpw")


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.t += s


def _client(adapter=None, clock=None, env="PROD"):
    adapter = adapter or FakeAdapter()
    clock = clock or Clock()
    c = yc.YuantaClient(adapter, env=env, log_dir="/tmp/ylog", clock=clock.now, sleep=clock.sleep, **CREDS)
    return c, adapter, clock


def _answer_later(adapter, mark, index, name, value, delay=0.05):
    threading.Timer(delay, adapter.respond, args=(mark, index, name, value)).start()


# ---------- 连线与登入 ----------

def test_login_uses_pfx_signature_and_reports_success():
    c, a, _ = _client()
    _answer_later(a, 1, 0, "Login", login_ok())
    st = c.connect_and_login(timeout=2)
    assert ("Open", "ENV:PROD") in a.calls
    login = next(x for x in a.calls if x[0] == "Login")
    assert login[1] == ("/config/cert.pfx", "pfxpw", "S98875005091", "pw")
    assert st["logged_in"] is True
    assert c.status()["logged_in"] is True


def test_login_failure_exposes_code_without_secrets():
    c, a, _ = _client()
    _answer_later(a, 1, 0, "Login", login_fail())
    st = c.connect_and_login(timeout=2)
    assert st["logged_in"] is False
    assert st["last_error"].startswith("0102")
    text = repr(c.status())
    assert "pw" not in text.replace("pwd", "") and "pfxpw" not in text and "/config/cert.pfx" not in text


def test_status_masks_account():
    c, a, _ = _client()
    assert c.status()["account"] == "S9887****091"


def test_login_retry_waits_at_least_4_seconds():
    """登入失败后不得频繁重试(元大安控:每 4 秒 1 次)。
    帐密错误会直接封锁不再重试(见 test_login_safety),这里用可重试的逾时情境。"""
    c, a, clock = _client()
    c.connect_and_login(timeout=0.2)
    _answer_later(a, 1, 0, "Login", login_ok())
    c.connect_and_login(timeout=2)
    assert any(s >= 4 for s in clock.slept)


def test_login_timeout_when_no_response():
    c, a, _ = _client()
    st = c.connect_and_login(timeout=0.2)
    assert st["logged_in"] is False and "timeout" in st["last_error"]


def test_system_events_update_connection_state():
    c, a, _ = _client()
    _answer_later(a, 1, 0, "Login", login_ok())
    c.connect_and_login(timeout=2)
    a.respond(0, 2, "", "Disconnect")      # intMark 0 / dwIndex 2:断线
    assert c.status()["connected"] is False
    assert c.status()["logged_in"] is False
    a.respond(0, 14, "", "停权")            # 14:停权触发
    assert "suspended" in c.status()["last_error"]


# ---------- 报价 ----------

def _logged_in_client():
    c, a, clock = _client()
    _answer_later(a, 1, 0, "Login", login_ok())
    c.connect_and_login(timeout=2)
    return c, a, clock


def test_quotes_maps_markets_and_parses_rows():
    c, a, _ = _logged_in_client()
    result = SimpleNamespace(QueryWatchList=NetList([watch_row(), watch_row("6488", "環球晶", 2, 520.0, 515.0)]))
    _answer_later(a, 1, 99, "GetWatchListAll", result)
    rows = c.quotes([("TSE", "2330"), ("OTC", "6488")], timeout=2)
    sent = next(x for x in a.calls if x[0] == "GetWatchListAll")
    assert sent[1] == "S98875005091"
    assert sent[2] == ["MKT:TWSE:2330", "MKT:TWOTC:6488"]
    assert rows[0] == {
        "market": "TSE", "code": "2330", "name": "台積電", "price": 2520.0, "prev_close": 2530.0,
        "open": 2525.0, "high": 2540.0, "low": 2510.0, "volume": 12345, "limit_up": 2780.0,
        "limit_down": 2280.0, "bid": 2515.0, "ask": 2520.0, "time": "10:05:03.120",
    }
    assert rows[1]["market"] == "OTC" and rows[1]["code"] == "6488"


@pytest.mark.parametrize("market,enum", [("TSE", "TWSE"), ("OTC", "TWOTC"), ("ESB", "TWEMERGING"), ("TAIFEX", "TAIFEX")])
def test_market_name_mapping(market, enum):
    assert yc.MARKET_ENUM[market] == enum


def test_quotes_rejects_more_than_600_and_unknown_market():
    c, a, _ = _logged_in_client()
    with pytest.raises(ValueError):
        c.quotes([("TSE", str(i)) for i in range(601)])
    with pytest.raises(ValueError):
        c.quotes([("NASDAQ", "AAPL")])


def test_quotes_requires_login():
    c, a, _ = _client()
    with pytest.raises(yc.NotLoggedIn):
        c.quotes([("TSE", "2330")])


def test_quotes_timeout_raises():
    c, a, _ = _logged_in_client()
    with pytest.raises(TimeoutError):
        c.quotes([("TSE", "2330")], timeout=0.2)


def test_same_function_calls_are_spaced_for_rate_limit():
    """同功能报价类每秒最多 3 次 → 两次呼叫至少间隔 1/3 秒。"""
    c, a, clock = _logged_in_client()
    result = SimpleNamespace(QueryWatchList=NetList([watch_row()]))
    for _ in range(2):
        _answer_later(a, 1, 99, "GetWatchListAll", result)
        c.quotes([("TSE", "2330")], timeout=2)
    assert any(s >= 0.33 for s in clock.slept)


# ---------- K 线 ----------

def _kbar(ts, o, h, l, c, v):
    return SimpleNamespace(TimeStamp=ts, OpenPrice=o, HighPrice=h, LowPrice=l, ClosePrice=c, DealVol=v)


def test_kline_daily_request_and_parse():
    c, a, _ = _logged_in_client()
    result = SimpleNamespace(MarketNo=1, StockCode="2330", KLineList=NetList([
        _kbar("2026/10/01 00:00:00", 2500, 2530, 2490, 2520, 30000),
        _kbar("2026/10/02 00:00:00", 2520, 2540, 2505, 2510, 28000),
    ]))
    _answer_later(a, 1, 99, "GetKLine", result)
    bars = c.kline("TSE", "2330", "1d", date(2026, 10, 1), date(2026, 10, 2), timeout=2)
    sent = next(x for x in a.calls if x[0] == "GetKLine")
    # 實測元大的開始日期不含當天(查 9/01 起第一筆是 9/02),所以往前送一天
    assert sent[1][:6] == ("S98875005091", "KT:11", "MKT:TWSE", "2330", "2026/09/30", "2026/10/02")
    assert bars[0] == {"time": "2026-10-01 00:00:00", "open": 2500.0, "high": 2530.0,
                       "low": 2490.0, "close": 2520.0, "volume": 30000}


@pytest.mark.parametrize("period,value", [("1m", 0), ("5m", 1), ("15m", 2), ("30m", 3), ("60m", 4),
                                          ("1d", 11), ("1w", 12), ("1M", 13)])
def test_kline_period_mapping(period, value):
    assert yc.KLINE_PERIOD[period] == value


def test_kline_rate_limit_one_per_second():
    c, a, clock = _logged_in_client()
    result = SimpleNamespace(MarketNo=1, StockCode="2330", KLineList=NetList([]))
    for _ in range(2):
        _answer_later(a, 1, 99, "GetKLine", result)
        c.kline("TSE", "2330", "1d", date(2026, 10, 1), date(2026, 10, 2), timeout=2)
    assert any(s >= 1.0 for s in clock.slept)


def test_unknown_period_rejected():
    c, a, _ = _logged_in_client()
    with pytest.raises(ValueError):
        c.kline("TSE", "2330", "2h", date(2026, 10, 1), date(2026, 10, 2))


# ---------- 安全 ----------

def test_client_exposes_no_order_methods():
    """转接服务第一版只读:不得包装任何下单/委托/圈存/预缴功能。"""
    forbidden = ("order", "Order", "earmark", "Earmark", "prefund", "Prefund", "strategy", "Strategy")
    names = [n for n in dir(yc.YuantaClient) if not n.startswith("_")]
    assert not [n for n in names if any(f in n for f in forbidden)]


def test_kline_drops_bars_before_requested_start():
    """往前多送一天後,回應中早於開始日的資料要篩掉。"""
    c, a, _ = _logged_in_client()
    result = SimpleNamespace(MarketNo=1, StockCode="2330", KLineList=NetList([
        _kbar("2026/09/30 00:00:00", 1, 1, 1, 1, 1),
        _kbar("2026/10/01 00:00:00", 2, 2, 2, 2, 2),
        _kbar("2026/10/01 13:25:00", 3, 3, 3, 3, 3),
    ]))
    _answer_later(a, 1, 99, "GetKLine", result)
    bars = c.kline("TSE", "2330", "5m", date(2026, 10, 1), date(2026, 10, 1), timeout=2)
    assert [b["time"] for b in bars] == ["2026-10-01 00:00:00", "2026-10-01 13:25:00"]
