"""台股数据源在宿主侧:种子、数据源「测试」按钮能真正测到台股 vendor。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.vendors import tw_bulk

FX = Path(__file__).resolve().parents[1] / "packages/marketdata/tests/fixtures/tw"
ROUTES = {
    "exchangeReport/BWIBBU_ALL": "twse_bwibbu.json",
    "tpex_mainboard_peratio_analysis": "tpex_peratio.json",
    "fund/T86": "twse_t86.json",
    "tpex_3insti_daily_trading": "tpex_3insti.json",
    "exchangeReport/MI_MARGN": "twse_margin.json",
    "tpex_mainboard_margin_balance": "tpex_margin.json",
    "opendata/t187ap45_L": "twse_dividend.json",
    "exchangeReport/TWT48U_ALL": "twse_exdividend.json",
    "getOD.ashx": "tdcc_dispersion.csv",
    "opendata/t187ap04_L": "twse_material_info.json",
    "mopsfin_t187ap04_O": "tpex_material_info.json",
    "announcement/notice": "twse_notice.json",
    "announcement/punish": "twse_punish.json",
    "tw.stock.yahoo.com/rss": "yahoo_rss_2330.xml",
    "newslist/category/tw_stock": "cnyes_tw_stock.json",
}

TW_SEEDS = [
    ("fundamentals", "twse"), ("capital_flow", "twse"), ("margin", "twse"), ("dividend", "twse"),
    ("events", "twse"), ("dragon_tiger", "twse"), ("shareholders", "tdcc"),
    ("news", "yahoo_tw"), ("flash_news", "cnyes"),
]


@pytest.fixture
def offline_tw(monkeypatch):
    tw_bulk.reset_cache()

    def fake_download(url, params=None):
        for key, name in ROUTES.items():
            if key in url:
                return (FX / name).read_text(encoding="utf-8")
        raise AssertionError(f"未预期的请求: {url}")

    monkeypatch.setattr(tw_bulk, "_download", fake_download)
    yield
    tw_bulk.reset_cache()


def _seed(dtype, provider):
    import server

    rows = [s for s in server.DATA_SOURCE_SEEDS if s["type"] == dtype and s["provider"] == provider]
    assert len(rows) == 1, f"缺少种子 {dtype}/{provider}"
    return rows[0]


@pytest.mark.parametrize("dtype,provider", TW_SEEDS)
def test_tw_seed_exists_and_enabled(dtype, provider):
    row = _seed(dtype, provider)
    assert row["enabled"] is True
    assert row["name"]
    assert VENDOR_CLASSES_BY_TYPE[dtype][provider].supports_markets == {"TW"}


def test_yahoo_quote_backup_seed_enabled_for_tw():
    # YFinance 行情种子启用,作为 TWSE 之后的台股备援
    assert _seed("quote", "yfinance")["enabled"] is True


@pytest.mark.parametrize("dtype,provider", TW_SEEDS)
def test_tw_source_test_button_succeeds(offline_tw, dtype, provider):
    """数据源页「测试」:用种子的 test_symbols(台股)实际走到台股 vendor 并成功。"""
    from src.modules.market.data_collector import DataCollectorManager

    row = _seed(dtype, provider)
    cfg = dict(row.get("config") or {})
    if dtype == "dragon_tiger":
        cfg["test_date"] = "2026-09-30"
    symbols = list(row["test_symbols"] or [])
    if dtype == "events":
        symbols = ["6177", "4530"]  # fixture 当日有重大讯息的上市/上柜公司
    source = SimpleNamespace(
        name=row["name"], type=dtype, provider=provider, config=cfg,
        test_symbols=symbols,
    )
    result = asyncio.run(DataCollectorManager().test_source(source))
    assert result.success, f"{dtype}/{provider}: {result.error}"
    assert result.count > 0
