"""台股标的清单与搜索(TWSE 上市 + TPEx 上柜)。"""

from __future__ import annotations

import json
import time

import pytest

from src.platform.marketdata import stock_list as sl

_TWSE_ROWS = [  # openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL 的真实字段
    {"Code": "2330", "Name": "台積電", "ClosingPrice": "1000"},
    {"Code": "0050", "Name": "元大台灣50", "ClosingPrice": "112"},
    {"Code": "006208", "Name": "富邦台50", "ClosingPrice": "256"},
    {"Code": "00400A", "Name": "主動國泰動能高息", "ClosingPrice": "15"},
    {"Code": "", "Name": "空代码", "ClosingPrice": "1"},
]
_TPEX_ROWS = [  # tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes
    {"SecuritiesCompanyCode": "6488", "CompanyName": "環球晶"},
    {"SecuritiesCompanyCode": "00679B", "CompanyName": "元大美債20年"},
    {"SecuritiesCompanyCode": "730123", "CompanyName": "某某權證購01"},  # 权证,应排除
    {"SecuritiesCompanyCode": "6488", "CompanyName": "環球晶"},  # 重复
]


@pytest.fixture(autouse=True)
def _no_esb_network(monkeypatch):
    """兴柜清单默认给空,避免测试真的连到 tpex.org.tw(慢线时会拖住整个测试集)。"""
    monkeypatch.setattr(sl, "_fetch_esb_raw", lambda: [])


@pytest.fixture
def fake_sources(monkeypatch):
    monkeypatch.setattr(sl, "_fetch_twse_raw", lambda: _TWSE_ROWS)
    monkeypatch.setattr(sl, "_fetch_tpex_raw", lambda: _TPEX_ROWS)


def test_fetch_tw_list_merges_listed_and_otc(fake_sources):
    out = sl._fetch_tw_stock_list()
    pairs = {(s["symbol"], s["name"], s["market"]) for s in out}
    assert ("2330", "台積電", "TW") in pairs
    assert ("6488", "環球晶", "TW") in pairs
    assert ("00679B", "元大美債20年", "TW") in pairs
    assert ("006208", "富邦台50", "TW") in pairs
    assert ("00400A", "主動國泰動能高息", "TW") in pairs


def test_fetch_tw_list_excludes_warrants_blanks_and_duplicates(fake_sources):
    out = sl._fetch_tw_stock_list()
    codes = [s["symbol"] for s in out]
    assert "730123" not in codes
    assert "" not in codes
    assert codes.count("6488") == 1


def test_fetch_tw_list_survives_one_source_failure(monkeypatch):
    def boom():
        raise RuntimeError("tpex down")

    monkeypatch.setattr(sl, "_fetch_twse_raw", lambda: _TWSE_ROWS)
    monkeypatch.setattr(sl, "_fetch_tpex_raw", boom)
    codes = {s["symbol"] for s in sl._fetch_tw_stock_list()}
    assert "2330" in codes and "6488" not in codes


def _no_other_markets(monkeypatch):
    for name in ("_fetch_from_eastmoney", "_fetch_hk_from_eastmoney", "_fetch_us_from_eastmoney", "_fetch_bj_from_eastmoney"):
        monkeypatch.setattr(sl, name, lambda: [])


def test_refresh_includes_tw(monkeypatch, tmp_path, fake_sources):
    _no_other_markets(monkeypatch)
    monkeypatch.setattr(sl, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sl, "CACHE_FILE", tmp_path / "stock_list_cache.json")
    stocks = sl.refresh_stock_list()
    assert any(s["market"] == "TW" and s["symbol"] == "2330" for s in stocks)


def test_cache_without_tw_is_treated_as_stale(monkeypatch, tmp_path, fake_sources):
    """升级前留下的缓存(7 天内、但没有台股)不能继续用,否则台股要等一周才搜得到。"""
    _no_other_markets(monkeypatch)
    cache = tmp_path / "stock_list_cache.json"
    cache.write_text(json.dumps({"ts": time.time(), "stocks": [
        {"symbol": "600519", "name": "贵州茅台", "market": "CN"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(sl, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sl, "CACHE_FILE", cache)
    stocks = sl.get_stock_list()
    assert any(s["market"] == "TW" for s in stocks)


def test_fresh_cache_with_tw_is_used_without_refetch(monkeypatch, tmp_path):
    cache = tmp_path / "stock_list_cache.json"
    cache.write_text(json.dumps({"ts": time.time(), "stocks": [
        {"symbol": "2330", "name": "台積電", "market": "TW", "board": "TSE"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(sl, "CACHE_FILE", cache)

    def forbidden():
        raise AssertionError("不应重新拉取")

    monkeypatch.setattr(sl, "_fetch_twse_raw", forbidden)
    assert sl.get_stock_list() == [{"symbol": "2330", "name": "台積電", "market": "TW", "board": "TSE"}]


@pytest.fixture
def tw_cache(monkeypatch):
    stocks = [
        {"symbol": "2330", "name": "台積電", "market": "TW"},
        {"symbol": "6488", "name": "環球晶", "market": "TW"},
        {"symbol": "600519", "name": "贵州茅台", "market": "CN"},
    ]
    monkeypatch.setattr(sl, "get_stock_list", lambda: stocks)
    return stocks


def test_search_tw_skips_eastmoney_realtime(monkeypatch, tw_cache):
    def forbidden(*a, **k):
        raise AssertionError("TW 搜索不应打东财实时搜索")

    monkeypatch.setattr(sl, "_realtime_search", forbidden)
    out = sl.search_stocks("2330", market="TW")
    assert out == [{"symbol": "2330", "name": "台積電", "market": "TW"}]


def test_search_tw_by_traditional_name(monkeypatch, tw_cache):
    monkeypatch.setattr(sl, "_realtime_search", lambda *a, **k: [])
    out = sl.search_stocks("環球", market="TW")
    assert [s["symbol"] for s in out] == ["6488"]


def test_search_tw_by_simplified_name(monkeypatch, tw_cache):
    """用户输入简体「台积电」也要找得到台積電。"""
    monkeypatch.setattr(sl, "_realtime_search", lambda *a, **k: [])
    out = sl.search_stocks("台积电", market="TW")
    assert [s["symbol"] for s in out] == ["2330"]


def test_all_market_search_lists_tw_first(monkeypatch, tw_cache):
    monkeypatch.setattr(
        sl, "_realtime_search",
        lambda *a, **k: [{"symbol": "02330", "name": "某港股", "market": "HK"}],
    )
    out = sl.search_stocks("2330", market="")
    assert out[0] == {"symbol": "2330", "name": "台積電", "market": "TW"}
    assert {"symbol": "02330", "name": "某港股", "market": "HK"} in out
