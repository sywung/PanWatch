"""港美股搜索后备:东方财富从台湾连线常逾时/502,清单里也就没有港美股 → TSLA 搜不到(2026-10-01 实际案例)。"""

from __future__ import annotations

import pytest

from src.platform.marketdata import stock_list as sl

# Yahoo search 真实回应(2026-10-01,q=TSLA)的切片
TSLA_QUOTES = [
    {"symbol": "TSLA", "shortname": "Tesla, Inc.", "exchange": "NMS", "quoteType": "EQUITY"},
    {"symbol": "TSLL", "shortname": "Direxion Daily TSLA Bull 2X ETF", "exchange": "NGM", "quoteType": "ETF"},
    {"symbol": "TSLA.TO", "shortname": "TESLA CDR (CAD HEDGED)", "exchange": "TOR", "quoteType": "EQUITY"},
    {"symbol": "XTSLA=F", "shortname": "Micro Tesla Inc Stock Futures", "exchange": "CME", "quoteType": "FUTURE"},
    {"symbol": "0700.HK", "shortname": "TENCENT", "exchange": "HKG", "quoteType": "EQUITY"},
    {"symbol": "600519.SS", "shortname": "KWEICHOW MOUTAI", "exchange": "SHH", "quoteType": "EQUITY"},
]


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


@pytest.fixture
def net(monkeypatch):
    calls = {"yahoo": 0, "eastmoney": 0}

    def fake_get(url, *, params=None, **k):
        assert "yahoo.com/v1/finance/search" in url, url
        calls["yahoo"] += 1
        return _Resp({"quotes": TSLA_QUOTES})

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, **k):
            calls["eastmoney"] += 1
            raise TimeoutError("timed out")

    monkeypatch.setattr(sl.httpx, "get", fake_get)
    monkeypatch.setattr(sl.httpx, "Client", _Client)
    monkeypatch.setattr(sl, "_eastmoney_skip_until", 0.0)
    monkeypatch.setattr(sl, "get_stock_list", lambda: [{"symbol": "2330", "name": "台積電", "market": "TW",
                                                        "board": "TSE"}])
    return calls


def test_us_search_falls_back_to_yahoo(net):
    out = sl.search_stocks("TSLA", market="US")
    assert out[0] == {"symbol": "TSLA", "name": "Tesla, Inc.", "market": "US"}
    assert {"symbol": "TSLL", "name": "Direxion Daily TSLA Bull 2X ETF", "market": "US"} in out
    symbols = {o["symbol"] for o in out}
    assert "TSLA.TO" not in symbols and "XTSLA=F" not in symbols   # 加拿大 CDR、期货排除
    assert all(o["market"] == "US" for o in out)


def test_all_market_search_includes_yahoo_results(net):
    out = sl.search_stocks("TSLA", market="")
    assert {"symbol": "TSLA", "name": "Tesla, Inc.", "market": "US"} in out


def test_yahoo_maps_hk_and_cn_symbols():
    assert sl._yahoo_quote_to_item(TSLA_QUOTES[4]) == {"symbol": "00700", "name": "TENCENT", "market": "HK"}
    assert sl._yahoo_quote_to_item(TSLA_QUOTES[5]) == {"symbol": "600519", "name": "KWEICHOW MOUTAI",
                                                       "market": "CN"}


def test_eastmoney_failure_backs_off(net):
    sl.search_stocks("TSLA", market="US")
    sl.search_stocks("NVDA", market="US")
    assert net["eastmoney"] == 1      # 第一次逾时后,10 分钟内不再打东方财富
    assert net["yahoo"] == 2


def test_eastmoney_results_still_preferred(monkeypatch, net):
    monkeypatch.setattr(sl, "_realtime_search",
                        lambda *a, **k: [{"symbol": "TSLA", "name": "特斯拉", "market": "US"}])
    out = sl.search_stocks("TSLA", market="US")
    assert out[0]["name"] == "特斯拉"
    assert net["yahoo"] == 0
