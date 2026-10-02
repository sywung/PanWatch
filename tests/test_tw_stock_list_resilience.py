"""台股清单的韧性:来源失败时不能把残缺清单存 7 天;本地查不到的代码要向证交所 mis 验证。

2026-10-01 实际案例:使用者那台的清单缓存只有上市 1327 档、上柜一档都没有
(建立当下 TPEx 请求失败),于是上柜 ETF 00887 搜不到,而且会持续 7 天。
"""

from __future__ import annotations

import json
import time

import pytest

from src.platform.marketdata import stock_list as sl

TWSE = [{"Code": "2330", "Name": "台積電"}]
TPEX = [{"SecuritiesCompanyCode": "00887", "CompanyName": "永豐中國科技50大"},
        {"SecuritiesCompanyCode": "6488", "CompanyName": "環球晶"}]
ESB = [{"SecuritiesCompanyCode": "1260", "CompanyAbbreviation": "富味鄉"}]


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(sl, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sl, "CACHE_FILE", tmp_path / "stock_list_cache.json")
    for name in ("_fetch_from_eastmoney", "_fetch_hk_from_eastmoney", "_fetch_us_from_eastmoney",
                 "_fetch_bj_from_eastmoney"):
        monkeypatch.setattr(sl, name, lambda: [])
    monkeypatch.setattr(sl, "_fetch_twse_raw", lambda: TWSE)
    monkeypatch.setattr(sl, "_fetch_tpex_raw", lambda: TPEX)
    monkeypatch.setattr(sl, "_fetch_esb_raw", lambda: ESB)
    return tmp_path / "stock_list_cache.json"


def _boom():
    raise RuntimeError("tpex timeout")


def _cache(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_complete_refresh_is_not_partial(env):
    sl.refresh_stock_list()
    data = _cache(env)
    assert data["partial"] is False and data["failed"] == []


def test_failed_board_marks_cache_partial(env, monkeypatch):
    monkeypatch.setattr(sl, "_fetch_tpex_raw", _boom)
    sl.refresh_stock_list()
    data = _cache(env)
    assert data["partial"] is True and data["failed"] == ["OTC"]


def test_empty_board_counts_as_failure(env, monkeypatch):
    monkeypatch.setattr(sl, "_fetch_tpex_raw", lambda: [])
    sl.refresh_stock_list()
    assert _cache(env)["failed"] == ["OTC"]


def test_partial_cache_expires_after_retry_window(env, monkeypatch):
    monkeypatch.setattr(sl, "_fetch_tpex_raw", _boom)
    sl.refresh_stock_list()
    assert sl._load_cache() is not None                     # 刚建立:先用
    data = _cache(env)
    data["ts"] = time.time() - sl.PARTIAL_RETRY_SEC - 1
    env.write_text(json.dumps(data), encoding="utf-8")
    assert sl._load_cache() is None                         # 过了重试窗口:重抓


def test_complete_cache_lasts_full_ttl(env):
    sl.refresh_stock_list()
    data = _cache(env)
    data["ts"] = time.time() - sl.PARTIAL_RETRY_SEC - 1
    env.write_text(json.dumps(data), encoding="utf-8")
    assert sl._load_cache() is not None


def test_legacy_cache_without_status_is_treated_as_partial(env):
    env.write_text(json.dumps({"ts": time.time() - sl.PARTIAL_RETRY_SEC - 1, "stocks": [
        {"symbol": "2330", "name": "台積電", "market": "TW", "board": "TSE"}]}), encoding="utf-8")
    assert sl._load_cache() is None


def test_failed_board_carries_over_previous_cache(env, monkeypatch):
    sl.refresh_stock_list()                                  # 第一次完整
    monkeypatch.setattr(sl, "_fetch_tpex_raw", _boom)        # 第二次上柜失败
    stocks = sl.refresh_stock_list()
    codes = {s["symbol"]: s["board"] for s in stocks if s["market"] == "TW"}
    assert codes.get("00887") == "OTC" and codes.get("6488") == "OTC"
    assert codes.get("2330") == "TSE" and codes.get("1260") == "ESB"
    assert _cache(env)["partial"] is True                   # 沿用的资料仍算不完整,稍后重试


# ---------------------------------------------------------------- mis 验证


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


@pytest.fixture
def mis(monkeypatch):
    calls = []

    def fake_get(url, *, params=None, **k):
        calls.append(params)
        if "00887" in params["ex_ch"]:
            return _Resp({"msgArray": [{"c": "", "z": "-"},
                                       {"c": "00887", "ex": "otc", "n": "永豐中國科技50大"}]})
        return _Resp({"msgArray": [{"c": "", "z": "-"}, {"c": "", "z": "-"}]})

    monkeypatch.setattr(sl.httpx, "get", fake_get)
    monkeypatch.setattr(sl, "get_stock_list", lambda *a, **k: [{"symbol": "2330", "name": "台積電",
                                                        "market": "TW", "board": "TSE"}])
    monkeypatch.setattr(sl, "_realtime_search", lambda *a, **k: [])
    return calls


def test_code_missing_from_list_is_verified_with_mis(mis):
    out = sl.search_stocks("00887", market="TW")
    assert out == [{"symbol": "00887", "name": "永豐中國科技50大", "market": "TW", "board": "OTC"}]
    assert mis[0]["ex_ch"] == "tse_00887.tw|otc_00887.tw"


def test_all_market_search_also_verifies_code(mis):
    out = sl.search_stocks("00887", market="")
    assert out and out[0]["symbol"] == "00887" and out[0]["market"] == "TW"


def test_unknown_code_returns_empty(mis):
    assert sl.search_stocks("9999", market="TW") == []


def test_name_query_does_not_hit_network(mis):
    assert sl.search_stocks("不存在的公司", market="TW") == []
    assert mis == []


def test_code_in_list_does_not_hit_network(mis):
    assert sl.search_stocks("2330", market="TW")[0]["name"] == "台積電"
    assert mis == []
