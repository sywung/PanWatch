"""F4 平台层:TWF 日 K 走 FinMind,代码对照与 F2 商品表一致,K 线收集器可用。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import marketdata.vendors.finmind as fm
from marketdata import MarketData, SourceConfig, StaticConfigProvider
from marketdata.symbol import Market, Symbol
from src.platform.marketdata import futures as fu
from src.platform.marketdata.models import MarketCode

_TX = json.loads(
    (Path(__file__).resolve().parents[1] / "packages/marketdata/tests/fixtures/taifex/finmind_futures_tx_202609.json")
    .read_text(encoding="utf-8")
)


@pytest.mark.parametrize("product", fu.INDEX_FUTURES, ids=lambda p: p.code)
def test_finmind_data_id_matches_futures_table(monkeypatch, product):
    seen = {}

    def fake_market_get(url, **kwargs):
        seen["data_id"] = kwargs["params"]["data_id"]
        return {"status": 200, "data": []}

    monkeypatch.setattr(fm, "market_get", fake_market_get)
    fm.FinMindKlineVendor().fetch([Symbol(Market.TWF, product.code)], {"days": 5})
    assert seen["data_id"] == product.openapi_code


def test_kline_collector_serves_twf(monkeypatch):
    from src.platform.marketdata.collectors import kline_collector as kc

    md = MarketData(config=StaticConfigProvider({"kline": [SourceConfig(vendor="finmind", config={}, enabled=True)]}))
    monkeypatch.setattr(kc, "get_market_data", lambda: md)
    monkeypatch.setattr(fm, "market_get", lambda url, **kw: json.loads(json.dumps(_TX)))
    kc.clear_kline_cache()

    bars = kc.KlineCollector(MarketCode.TWF).get_klines("TXF", days=5)

    assert [b.date for b in bars][-2:] == ["2026-09-21", "2026-09-22"]
    assert bars[-1].close == 48243.0
    kc.clear_kline_cache()


def test_finmind_kline_seed_serves_futures():
    import server

    rows = [s for s in server.DATA_SOURCE_SEEDS if s["provider"] == "finmind" and s["type"] == "kline"]
    assert len(rows) == 1 and rows[0]["enabled"] is True
    assert "TWF" in fm.FinMindKlineVendor.supports_markets
