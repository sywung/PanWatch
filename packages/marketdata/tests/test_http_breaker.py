"""按 host 熔断 + 节流不跨 host 互相阻塞（2026-10-07 首页卡顿修复的合约测试）。

背景：TWSE MIS 封锁 IP 时每次请求都“空响应断线”，每次调用还重试 3 次，
首页指数端点冷缓存一次要 12.5 秒。熔断后应立即返回 None，让报价走备援来源。
"""
import threading
import time as _real_time

_REAL_SLEEP = _real_time.sleep  # 必须在 fixture 把 time.sleep 换成桩之前取出（mh.time 与此为同一模块）

import httpx
import pytest

import marketdata.http as mh


class _Counter:
    calls = 0


class _FailClient:
    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None):
        _Counter.calls += 1
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")


class _Resp:
    text = "ok"

    def raise_for_status(self):
        pass


class _OkClient(_FailClient):
    def get(self, url, params=None):
        _Counter.calls += 1
        return _Resp()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    mh.reset_circuit_breakers()
    _Counter.calls = 0
    monkeypatch.setattr(mh.time, "sleep", lambda *_: None)
    yield
    mh.reset_circuit_breakers()


def _clock(monkeypatch, start=1000.0):
    now = {"t": start}
    monkeypatch.setattr(mh.time, "monotonic", lambda: now["t"])
    return now


def test_breaker_opens_after_threshold_and_skips_network(monkeypatch):
    _clock(monkeypatch)
    mh.register_circuit_breaker("brk-a", failure_threshold=2, cooldown_s=60)
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)

    assert mh.market_get("http://x", host_key="brk-a", retries=2) is None
    assert mh.market_get("http://x", host_key="brk-a", retries=2) is None
    assert _Counter.calls == 6  # 两次调用、各 3 次尝试，熔断前照常重试

    _Counter.calls = 0
    for _ in range(5):
        assert mh.market_get("http://x", host_key="brk-a", retries=2) is None
    assert _Counter.calls == 0  # 熔断中：完全不打网络


def test_breaker_open_reports_reason_to_capture_errors(monkeypatch):
    _clock(monkeypatch)
    mh.register_circuit_breaker("brk-b", failure_threshold=1, cooldown_s=60)
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)
    mh.market_get("http://x", host_key="brk-b", retries=0)

    with mh.capture_errors() as errs:
        assert mh.market_get("http://x", host_key="brk-b", retries=0, log_label="MIS") is None
    assert len(errs) == 1 and "熔断" in errs[0]


def test_half_open_probe_once_after_cooldown_then_reopens_on_failure(monkeypatch):
    now = _clock(monkeypatch)
    mh.register_circuit_breaker("brk-c", failure_threshold=1, cooldown_s=60)
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)
    mh.market_get("http://x", host_key="brk-c", retries=2)  # 开路

    now["t"] += 61
    _Counter.calls = 0
    assert mh.market_get("http://x", host_key="brk-c", retries=2) is None
    assert _Counter.calls == 1  # 半开探测只打一次，不重试

    _Counter.calls = 0
    now["t"] += 30  # 仍在新一轮冷却期内
    assert mh.market_get("http://x", host_key="brk-c", retries=2) is None
    assert _Counter.calls == 0


def test_success_after_cooldown_closes_breaker(monkeypatch):
    now = _clock(monkeypatch)
    mh.register_circuit_breaker("brk-d", failure_threshold=1, cooldown_s=60)
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)
    mh.market_get("http://x", host_key="brk-d", retries=0)

    now["t"] += 61
    monkeypatch.setattr(mh.httpx, "Client", _OkClient)
    assert mh.market_get("http://x", host_key="brk-d", retries=0) == "ok"
    assert mh.market_get("http://x", host_key="brk-d", retries=0) == "ok"

    # 已闭合且计数归零：再失败一次才重新开路（threshold=1），开路前这一次会真的打网络
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)
    _Counter.calls = 0
    mh.market_get("http://x", host_key="brk-d", retries=0)
    assert _Counter.calls == 1


def test_success_resets_consecutive_failure_count(monkeypatch):
    _clock(monkeypatch)
    mh.register_circuit_breaker("brk-e", failure_threshold=2, cooldown_s=60)
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)
    mh.market_get("http://x", host_key="brk-e", retries=0)
    monkeypatch.setattr(mh.httpx, "Client", _OkClient)
    mh.market_get("http://x", host_key="brk-e", retries=0)
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)
    mh.market_get("http://x", host_key="brk-e", retries=0)  # 连续失败只有 1 次

    _Counter.calls = 0
    mh.market_get("http://x", host_key="brk-e", retries=0)
    assert _Counter.calls == 1  # 未开路


def test_unregistered_host_never_breaks(monkeypatch):
    _clock(monkeypatch)
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)
    for _ in range(10):
        mh.market_get("http://x", host_key="brk-none", retries=0)
    assert _Counter.calls == 10


def test_twse_mis_host_has_breaker_registered():
    import marketdata.vendors.twse  # noqa: F401  导入即注册

    cfg = mh.circuit_breaker_config("mis.twse.com.tw")
    assert cfg is not None
    threshold, cooldown = cfg
    assert 1 <= threshold <= 5
    assert 60 <= cooldown <= 900


def test_throttle_does_not_block_other_hosts(monkeypatch):
    """节流等待只能挡同一 host；原实现在全局锁里 sleep，会让所有 host 一起排队。"""
    monkeypatch.setattr(mh.time, "sleep", _REAL_SLEEP)
    mh.throttle("thr-a", 0.6)
    t = threading.Thread(target=mh.throttle, args=("thr-a", 0.6))  # 需等 ~0.6s
    t.start()
    _REAL_SLEEP(0.05)
    started = _real_time.perf_counter()
    mh.throttle("thr-b", 0.6)  # 另一个 host 首次调用，应立即返回
    elapsed = _real_time.perf_counter() - started
    t.join()
    assert elapsed < 0.15, f"other host waited {elapsed:.2f}s"


def test_throttle_still_serializes_same_host(monkeypatch):
    monkeypatch.setattr(mh.time, "sleep", _REAL_SLEEP)
    mh.throttle("thr-c", 0.3)
    started = _real_time.perf_counter()
    mh.throttle("thr-c", 0.3)
    assert _real_time.perf_counter() - started >= 0.25


def test_breaker_logs_once_when_opening(monkeypatch, caplog):
    _clock(monkeypatch)
    mh.register_circuit_breaker("brk-log", failure_threshold=1, cooldown_s=60)
    monkeypatch.setattr(mh.httpx, "Client", _FailClient)
    with caplog.at_level("WARNING", logger=mh.logger.name):
        for _ in range(5):
            mh.market_get("http://x", host_key="brk-log", retries=0)
    assert sum("熔断" in r.getMessage() for r in caplog.records) == 1


def _capture_market_get(monkeypatch, module):
    calls = []

    def fake(url, **kw):
        calls.append(kw)
        return None

    monkeypatch.setattr(module, "market_get", fake)
    return calls


def test_twse_quote_vendor_fails_fast_without_retry(monkeypatch):
    """MIS 正常几百毫秒内回应；超时 10s 加上递增重试，会让熔断前的首次请求卡 20 秒以上（2026-10-07 实测 23s）。"""
    import marketdata.vendors.twse as tv
    from marketdata.symbol import Symbol

    calls = _capture_market_get(monkeypatch, tv)
    tv.TwseMisQuoteVendor().fetch([Symbol.parse("2330", "TW")], {})
    assert calls and all(c.get("timeout", 10) <= 3 and c.get("retries") == 0 for c in calls)


def test_tw_index_quotes_fails_fast_without_retry(monkeypatch):
    import marketdata.client as client_mod
    import marketdata.vendors.twse as tv

    calls = _capture_market_get(monkeypatch, tv)  # tw_index_quotes 经由 twse.market_get 取数
    client_mod.MarketData.tw_index_quotes(object.__new__(client_mod.MarketData))
    assert calls and all(c.get("timeout", 10) <= 3 and c.get("retries") == 0 for c in calls)
