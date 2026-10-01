"""F3 平台层:连续代码(TXF、CDF…)→ 近月合约 → 报价 → 对应回连续代码。

vendor(packages/marketdata/vendors/taifex.py)只认具体合约;这一层负责用休市日历
解析近月(futures.resolve_contract),并把结果对应回自选股里存的连续代码。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from marketdata import Quote
from src.platform.marketdata import futures as fu
from src.platform.marketdata import marketdata_client as mc
from src.platform.scheduling import trading_calendar as tc

TPE = ZoneInfo("Asia/Taipei")
FX = Path(__file__).parent / "fixtures"
_HOLIDAYS = json.loads((FX / "twse_holidays_2026.json").read_text(encoding="utf-8"))
_SSF = json.loads((FX / "taifex/ssf_lists.json").read_text(encoding="utf-8"))
_MARGIN = json.loads((FX / "taifex/ssf_margining.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 10, 1, 20, 0, tzinfo=TPE)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    tc.reset_cache()
    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", lambda: _HOLIDAYS)
    assert tc.refresh_tw_blocking() is True
    monkeypatch.setattr(fu, "CACHE_FILE", tmp_path / "futures_list_cache.json")
    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", lambda: _SSF)
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", lambda: _MARGIN)
    fu.reset_cache()
    yield
    fu.reset_cache()
    tc.reset_cache()


class FakeMD:
    def __init__(self, quotes):
        self._quotes = quotes
        self.calls = []

    def quotes(self, symbols, *, market=None):
        self.calls.append((list(symbols), market))
        return [q for q in self._quotes if q.symbol in symbols]


def _q(symbol, price, **kw):
    return Quote(symbol=symbol, market="TWF", current_price=price, name="臺指期106", **kw)


def test_futures_quote_rows_resolve_and_map_back():
    md = FakeMD([
        _q("TXFJ6", 48461.0, prev_close=48698.0, change_pct=-0.49, contract="TXFJ6", session="night"),
        _q("CDFJ6", 2530.0, prev_close=2500.0, contract="CDFJ6", session="day"),
    ])
    rows = mc.futures_quote_rows(md, ["TXF", "cdf", "ZZZ", "TXF"], now=NOW)

    assert md.calls == [(["TXFJ6", "CDFJ6"], "TWF")]      # 未知代码丢弃、正规化大写、去重
    by = {r["symbol"]: r for r in rows}
    assert set(by) == {"TXF", "CDF"}
    txf = by["TXF"]
    assert txf["market"] == "TWF"
    assert txf["name"] == "台指期"                          # 用商品名,不用 mis 的「臺指期106」
    assert txf["current_price"] == 48461.0
    assert txf["prev_close"] == 48698.0
    assert (txf["contract"], txf["session"]) == ("TXFJ6", "night")
    assert by["CDF"]["name"] == "台積電期貨"


def test_futures_quote_rows_keeps_rolled_contract():
    md = FakeMD([_q("MYFJ6", 50.0, contract="MYFL6", session="day")])
    rows = mc.futures_quote_rows(md, ["MYF"], now=NOW)
    assert rows[0]["symbol"] == "MYF" and rows[0]["contract"] == "MYFL6"


def test_futures_quote_rows_rolls_after_settlement():
    md = FakeMD([])
    mc.futures_quote_rows(md, ["TXF"], now=datetime(2026, 10, 21, 13, 30, tzinfo=TPE))
    assert md.calls == [(["TXFK6"], "TWF")]


def test_futures_quote_rows_no_known_codes_makes_no_call():
    md = FakeMD([])
    assert mc.futures_quote_rows(md, ["ZZZ", "2330"], now=NOW) == []
    assert md.calls == []


def test_md_quote_rows_routes_twf(monkeypatch):
    md = FakeMD([_q("TXFJ6", 48461.0, contract="TXFJ6", session="night")])
    monkeypatch.setattr(mc, "get_market_data", lambda: md)
    rows = mc.md_quote_rows(["TXF"], "TWF")
    assert rows and rows[0]["symbol"] == "TXF"
    assert md.calls[0][1] == "TWF" and md.calls[0][0][0].startswith("TXF") and len(md.calls[0][0][0]) == 5


def test_md_quote_rows_other_markets_unchanged(monkeypatch):
    md = FakeMD([Quote(symbol="2330", market="TW", current_price=2510.0, name="台積電")])
    monkeypatch.setattr(mc, "get_market_data", lambda: md)
    rows = mc.md_quote_rows(["2330"], "TW")
    assert md.calls == [(["2330"], "TW")]
    assert "contract" not in rows[0] and "session" not in rows[0]


# ---------------------------------------------------------------- 数据源种子与测试按钮


def test_taifex_quote_seed():
    import server

    rows = [s for s in server.DATA_SOURCE_SEEDS if s["provider"] == "taifex" and s["type"] == "quote"]
    assert len(rows) == 1
    seed = rows[0]
    assert seed["enabled"] is True
    assert seed["test_symbols"] and all(fu.get_futures_product(c) for c in seed["test_symbols"])


def test_datasource_test_button_resolves_futures_codes():
    from src.modules.market.data_collector import DataCollectorManager

    seen = {}

    def fake_quotes(self, symbols, *, market=None):
        seen["args"] = (list(symbols), market)
        return [
            Quote(symbol=s, market="TWF", current_price=48461.0, name="x", change_pct=-0.5,
                  contract=s, session="night")
            for s in symbols
        ]

    source = SimpleNamespace(name="期交所", type="quote", provider="taifex", config={}, test_symbols=["TXF"])
    with mock.patch("marketdata.MarketData.quotes", fake_quotes):
        result = asyncio.run(DataCollectorManager()._test_quote_source(source, source.test_symbols))

    assert result.success, result.error
    assert seen["args"][1] == "TWF"
    assert seen["args"][0][0].startswith("TXF") and len(seen["args"][0][0]) == 5
    assert result.data[0]["symbol"] == "TXF"
    assert result.data[0]["price"] == 48461.0
