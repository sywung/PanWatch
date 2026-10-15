"""PanWatch 的股權分散服務改走 MarketData.shareholders_history（yuantaData 優先、集保直連備援）。"""

from __future__ import annotations

import server
from src.modules.market import shareholder_dispersion as svc


def test_fetch_history_levels_delegates_to_marketdata_with_skip_dates(monkeypatch):
    seen = []

    class FakeMD:
        def shareholders_history(self, symbol, *, skip_dates=(), market=None):
            seen.append((symbol, set(skip_dates), market))
            return [("2026-10-08", [{"level": 1}])]

    monkeypatch.setattr("src.platform.marketdata.collectors.kline_collector.get_market_data", lambda: FakeMD())
    out = svc.fetch_history_levels("2330", skip_dates={"2026-10-02"})
    assert out == [("2026-10-08", [{"level": 1}])]
    assert seen == [("2330", {"2026-10-02"}, "TW")]


def test_service_no_longer_imports_tdcc_web_directly():
    import inspect

    assert "tdcc_web" not in inspect.getsource(svc)


def test_default_data_sources_include_disabled_yuantadata_shareholders_before_tdcc():
    rows = [s for s in server.DATA_SOURCE_SEEDS if s["type"] == "shareholders"]
    yd = [s for s in rows if s["provider"] == "yuantadata"]
    tdcc = [s for s in rows if s["provider"] == "tdcc"]
    assert len(yd) == 1 and len(tdcc) == 1
    assert yd[0]["enabled"] is False                      # 沒填 base_url 前不啟用
    assert yd[0]["config"]["base_url"] == "" and "token" in yd[0]["config"]
    assert yd[0]["priority"] <= tdcc[0]["priority"]      # 啟用後優先；Engine 以 priority 小者先
    assert yd[0]["supports_batch"] is True
    assert isinstance(yd[0]["test_symbols"], list) and "2330" in yd[0]["test_symbols"]
