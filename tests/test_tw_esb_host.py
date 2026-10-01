"""兴柜在宿主侧:资料源种子、Fugle 凭证栏位、标的清单含兴柜。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marketdata.vendors import tw_bulk

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "packages/marketdata/tests/fixtures/tw"


def _seed(provider):
    import server

    rows = [s for s in server.DATA_SOURCE_SEEDS if s["type"] == "quote" and s["provider"] == provider]
    assert len(rows) == 1, f"缺少 quote/{provider} 种子"
    return rows[0]


def test_quote_seed_order_mis_fugle_esb():
    twse, fugle, esb = _seed("twse"), _seed("fugle"), _seed("tpex_esb")
    assert twse["priority"] < fugle["priority"] < esb["priority"]
    assert fugle["enabled"] is True and esb["enabled"] is True
    # 没 key 时 Fugle vendor 直接跳过,不会打网络;key 由使用者在资料源页填写
    assert fugle["config"].get("api_key", "") == ""


def test_fugle_key_never_hardcoded():
    for p in [ROOT / "server.py", *sorted((ROOT / "packages/marketdata/src").rglob("*.py")),
              *sorted((ROOT / "src").rglob("*.py"))]:
        text = p.read_text(encoding="utf-8")
        assert "X-API-KEY\": \"" not in text, p


def test_datasource_page_has_fugle_secret_field():
    text = (ROOT / "frontend/src/pages/DataSources.tsx").read_text(encoding="utf-8")
    i = text.index("PROVIDER_CREDENTIAL_FIELDS")
    block = text[i:i + 1500]
    assert "fugle:" in block
    seg = block[block.index("fugle:"):]
    seg = seg[:seg.index("]")]
    assert "key: 'api_key'" in seg and "secret: true" in seg


@pytest.fixture
def offline_lists(monkeypatch):
    from src.platform.marketdata import stock_list as sl

    tw_bulk.reset_cache()
    monkeypatch.setattr(sl, "_fetch_twse_raw", lambda: [{"Code": "2330", "Name": "台積電"}])
    monkeypatch.setattr(sl, "_fetch_tpex_raw", lambda: [{"SecuritiesCompanyCode": "6488", "CompanyName": "環球晶"}])
    monkeypatch.setattr(
        sl, "_fetch_esb_raw",
        lambda: json.loads((FX / "tpex_esb_companies.json").read_text(encoding="utf-8")),
    )
    return sl


def test_tw_stock_list_includes_esb_with_board(offline_lists):
    rows = {s["symbol"]: s for s in offline_lists._fetch_tw_stock_list()}
    assert rows["1260"]["name"] == "富味鄉" and rows["1260"]["market"] == "TW"
    assert rows["1260"]["board"] == "ESB"
    assert rows["2330"].get("board") == "TSE"
    assert rows["6488"].get("board") == "OTC"


def test_esb_list_failure_keeps_listed(offline_lists, monkeypatch):
    def boom():
        raise RuntimeError("tpex down")

    monkeypatch.setattr(offline_lists, "_fetch_esb_raw", boom)
    codes = {s["symbol"] for s in offline_lists._fetch_tw_stock_list()}
    assert {"2330", "6488"} <= codes
