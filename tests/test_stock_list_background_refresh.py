"""股票清单过期/缺失时搜索不能卡住:旧清单先用、背景重抓、同一时间只抓一份。

2026-10-01 浏览器验收:新容器第一次「全部」搜索 181 秒(同步重抓整份清单,A/港/美股来源逾时);
之后每 10 分钟有一次搜索要等东方财富实时搜索逾时 5 秒(从台湾连不上 searchapi.eastmoney.com)。
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from src.platform.marketdata import stock_list as sl

TW_2330 = {"symbol": "2330", "name": "台積電", "market": "TW", "board": "TSE"}


@pytest.fixture
def cache_file(monkeypatch, tmp_path):
    path = tmp_path / "stock_list_cache.json"
    monkeypatch.setattr(sl, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sl, "CACHE_FILE", path)
    monkeypatch.setattr(sl, "_realtime_search", lambda *a, **k: [])
    monkeypatch.setattr(sl, "_yahoo_search", lambda *a, **k: [])
    # 「全部」搜索也查期货商品清单;没有缓存时会连期交所
    from src.platform.marketdata import futures
    monkeypatch.setattr(futures, "search_futures", lambda *a, **k: [])
    return path


def _write_cache(path, stocks, age_sec):
    path.write_text(json.dumps({"ts": time.time() - age_sec, "stocks": stocks,
                                "partial": False, "failed": []}), encoding="utf-8")


def _forbid_sync_refresh(monkeypatch):
    def forbidden():
        raise AssertionError("搜索路径不得同步重抓整份清单")

    monkeypatch.setattr(sl, "refresh_stock_list", forbidden)


def _record_background(monkeypatch):
    calls = []
    monkeypatch.setattr(sl, "refresh_in_background", lambda: calls.append(1))
    return calls


# ---------- 搜索路径不阻塞 ----------

def test_stale_cache_is_served_and_refreshed_in_background(monkeypatch, cache_file):
    """清单过期(超过 TTL):搜索直接用旧清单,同时触发背景重抓。"""
    _write_cache(cache_file, [TW_2330], sl.CACHE_TTL + 60)
    _forbid_sync_refresh(monkeypatch)
    bg = _record_background(monkeypatch)

    out = sl.search_stocks("台積", "TW")

    assert [s["symbol"] for s in out] == ["2330"]
    assert bg == [1]


def test_missing_cache_does_not_block_search(monkeypatch, cache_file):
    """完全没有清单(新容器):搜索不等清单,改走证交所 mis 验证代码,并触发背景重抓。"""
    _forbid_sync_refresh(monkeypatch)
    bg = _record_background(monkeypatch)
    monkeypatch.setattr(sl, "_lookup_tw_code", lambda q: [dict(TW_2330)])

    out = sl.search_stocks("2330", "TW")

    assert [s["symbol"] for s in out] == ["2330"]
    assert bg == [1]


def test_all_market_search_does_not_block_on_missing_cache(monkeypatch, cache_file):
    """「全部」市场搜索同样不阻塞。"""
    _forbid_sync_refresh(monkeypatch)
    bg = _record_background(monkeypatch)
    monkeypatch.setattr(sl, "_lookup_tw_code", lambda q: [])

    assert isinstance(sl.search_stocks("台積", ""), list)  # 结果可为空,重点是不同步重抓
    assert bg  # 至少触发一次背景重抓


def test_fresh_cache_does_not_trigger_background(monkeypatch, cache_file):
    """清单新鲜时不触发任何重抓。"""
    _write_cache(cache_file, [TW_2330], 60)
    _forbid_sync_refresh(monkeypatch)
    bg = _record_background(monkeypatch)

    sl.search_stocks("台積", "TW")

    assert bg == []


def test_blocking_get_stock_list_still_refreshes_when_missing(monkeypatch, cache_file):
    """非搜索的调用方(启动预热等)用默认的 get_stock_list():没有清单时仍同步抓取。"""
    monkeypatch.setattr(sl, "refresh_stock_list", lambda: [TW_2330])

    assert sl.get_stock_list() == [TW_2330]


# ---------- 背景重抓 single-flight ----------

def _blocking_fetch(monkeypatch):
    """台股抓取卡在 event 上,记录被调用几次;其他市场给空。"""
    gate = threading.Event()
    entered = threading.Event()
    calls = []

    def fetch():
        calls.append(1)
        entered.set()
        assert gate.wait(5), "测试卡住"
        return [dict(TW_2330)], []

    monkeypatch.setattr(sl, "_fetch_tw_stock_list_with_status", fetch)
    for name in ("_fetch_from_eastmoney", "_fetch_hk_from_eastmoney",
                 "_fetch_us_from_eastmoney", "_fetch_bj_from_eastmoney"):
        monkeypatch.setattr(sl, name, lambda: [])
    return gate, entered, calls


def test_background_refresh_is_single_flight(monkeypatch, cache_file):
    """重抓进行中再次触发背景重抓:不另开一份,回 None。"""
    gate, entered, calls = _blocking_fetch(monkeypatch)

    first = sl.refresh_in_background()
    assert first is not None
    assert entered.wait(5)
    second = sl.refresh_in_background()
    gate.set()
    first.join(5)

    assert second is None
    assert calls == [1]
    assert json.loads(cache_file.read_text(encoding="utf-8"))["stocks"] == [TW_2330]


def test_sync_refresh_waits_for_running_background(monkeypatch, cache_file):
    """背景重抓进行中,同步 refresh_stock_list() 等它完成并沿用结果,不再抓第二份。"""
    gate, entered, calls = _blocking_fetch(monkeypatch)

    bg = sl.refresh_in_background()
    assert entered.wait(5)
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("stocks", sl.refresh_stock_list()))
    t.start()
    time.sleep(0.2)
    gate.set()
    bg.join(5)
    t.join(5)

    assert calls == [1]
    assert result["stocks"] == [TW_2330]


def test_background_refresh_can_run_again_after_finishing(monkeypatch, cache_file):
    """上一轮结束后可以再触发下一轮(没有永久锁死)。"""
    gate, entered, calls = _blocking_fetch(monkeypatch)
    gate.set()

    sl.refresh_in_background().join(5)
    sl.refresh_in_background().join(5)

    assert calls == [1, 1]


def test_background_refresh_failure_is_logged_not_raised(monkeypatch, cache_file, caplog):
    """背景重抓抛错:记日志,不影响下一次触发。"""
    def boom():
        raise RuntimeError("source down")

    monkeypatch.setattr(sl, "_fetch_tw_stock_list_with_status", boom)

    sl.refresh_in_background().join(5)

    assert "source down" in caplog.text
    assert sl.refresh_in_background() is not None


# ---------- 东方财富实时搜索 ----------

class _TimeoutClient:
    timeouts: list = []

    def __init__(self, *a, timeout=None, **k):
        _TimeoutClient.timeouts.append(timeout)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, **k):
        raise TimeoutError("timed out")


@pytest.fixture
def em_down(monkeypatch):
    _TimeoutClient.timeouts = []
    monkeypatch.setattr(sl.httpx, "Client", _TimeoutClient)
    monkeypatch.setattr(sl, "_eastmoney_skip_until", 0.0)
    monkeypatch.setattr(sl, "_eastmoney_failures", 0, raising=False)
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(sl.time, "time", lambda: now["t"])
    return now


def _connect_timeout(timeout) -> float:
    return timeout.connect if hasattr(timeout, "connect") else float(timeout)


def test_eastmoney_connect_timeout_is_short(em_down):
    """从台湾连不上东方财富时是连线逾时;连线逾时不超过 2 秒(原本 5 秒)。"""
    sl._realtime_search("TSLA")

    assert _TimeoutClient.timeouts and _connect_timeout(_TimeoutClient.timeouts[0]) <= 2


def test_eastmoney_backoff_grows_on_repeated_failures(em_down):
    """连续失败时退避时间加倍(600→1200→2400…),上限 6 小时。"""
    windows = []
    for _ in range(8):
        sl._realtime_search("TSLA")
        windows.append(sl._eastmoney_skip_until - em_down["t"])
        em_down["t"] = sl._eastmoney_skip_until + 1  # 退避结束后再试

    assert windows[:3] == [600, 1200, 2400]
    assert max(windows) == 6 * 3600


def test_eastmoney_success_resets_backoff(monkeypatch, em_down):
    """成功一次后,下一次失败重新从 600 秒起算。"""
    sl._realtime_search("TSLA")
    em_down["t"] = sl._eastmoney_skip_until + 1
    sl._realtime_search("TSLA")  # 第二次失败 → 1200

    class _OkClient(_TimeoutClient):
        def get(self, url, **k):
            return type("R", (), {"json": lambda self: {"QuotationCodeTable": {"Data": []}}})()

    em_down["t"] = sl._eastmoney_skip_until + 1
    monkeypatch.setattr(sl.httpx, "Client", _OkClient)
    sl._realtime_search("TSLA")
    monkeypatch.setattr(sl.httpx, "Client", _TimeoutClient)
    sl._realtime_search("TSLA")

    assert sl._eastmoney_skip_until - em_down["t"] == 600


# ---------- 来源失败不能清空其他市场 ----------
# 2026-10-02 实测:从台湾连东方财富 A/港/美股清单全失败(akshare 也逾时),
# 重抓后缓存只剩台股 2692 只,原本 3 万多只 A/港/美股被覆盖掉。

def _old_full_cache(path):
    _write_cache(path, [
        TW_2330,
        {"symbol": "600519", "name": "贵州茅台", "market": "CN"},
        {"symbol": "00700", "name": "腾讯控股", "market": "HK"},
        {"symbol": "AAPL", "name": "苹果", "market": "US"},
    ], sl.CACHE_TTL + 60)


def _sources(monkeypatch, *, cn=None, hk=None, us=None, bj=None):
    def make(value):
        if isinstance(value, Exception):
            def boom():
                raise value
            return boom
        return lambda: list(value or [])

    monkeypatch.setattr(sl, "_fetch_tw_stock_list_with_status",
                        lambda: ([dict(TW_2330), {"symbol": "2317", "name": "鴻海", "market": "TW",
                                                  "board": "TSE"}], []))
    monkeypatch.setattr(sl, "_fetch_from_eastmoney", make(cn))
    monkeypatch.setattr(sl, "_fetch_from_akshare", make(RuntimeError("akshare down")))
    monkeypatch.setattr(sl, "_fetch_hk_from_eastmoney", make(hk))
    monkeypatch.setattr(sl, "_fetch_us_from_eastmoney", make(us))
    monkeypatch.setattr(sl, "_fetch_bj_from_eastmoney", make(bj))


def _markets(stocks):
    return sorted({s["market"] for s in stocks})


def test_failed_markets_carry_over_previous_cache(monkeypatch, cache_file):
    """A/港/美股来源全失败:沿用上一份缓存的这些市场,台股照常更新。"""
    _old_full_cache(cache_file)
    err = ValueError("Expecting value: line 1 column 1 (char 0)")
    _sources(monkeypatch, cn=err, hk=err, us=err, bj=err)

    stocks = sl.refresh_stock_list()

    assert _markets(stocks) == ["CN", "HK", "TW", "US"]
    assert {s["symbol"] for s in stocks if s["market"] == "TW"} == {"2330", "2317"}
    saved = json.loads(cache_file.read_text(encoding="utf-8"))["stocks"]
    assert _markets(saved) == ["CN", "HK", "TW", "US"]


def test_empty_market_result_also_carries_over(monkeypatch, cache_file):
    """来源回空清单视同失败,同样沿用旧资料。"""
    _old_full_cache(cache_file)
    _sources(monkeypatch, cn=[], hk=[], us=[], bj=[])

    stocks = sl.refresh_stock_list()

    assert {s["symbol"] for s in stocks if s["market"] == "HK"} == {"00700"}


def test_successful_market_replaces_previous(monkeypatch, cache_file):
    """来源成功时用新资料,不混入旧的同市场资料。"""
    _old_full_cache(cache_file)
    _sources(monkeypatch, cn=[], hk=[], bj=[],
             us=[{"symbol": "TSLA", "name": "特斯拉", "market": "US"}])

    stocks = sl.refresh_stock_list()

    assert {s["symbol"] for s in stocks if s["market"] == "US"} == {"TSLA"}


def test_non_tw_failure_does_not_mark_cache_partial(monkeypatch, cache_file):
    """非台股来源失败不标 partial(否则从台湾每 30 分钟就重抓一次必失败的来源)。"""
    _old_full_cache(cache_file)
    _sources(monkeypatch, cn=[], hk=[], us=[], bj=[])

    sl.refresh_stock_list()

    assert json.loads(cache_file.read_text(encoding="utf-8"))["partial"] is False
