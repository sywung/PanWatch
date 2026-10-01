"""浏览器验收发现的台股缺口:首页指数、市场状态排序、机会发现台股热门股、预设帐户名称。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from marketdata.vendors import tw_bulk

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "packages/marketdata/tests/fixtures/tw"


@pytest.fixture
def offline_tw(monkeypatch):
    tw_bulk.reset_cache()
    routes = {
        "exchangeReport/STOCK_DAY_ALL": "twse_stock_day_all.json",
        "tpex_mainboard_daily_close_quotes": "tpex_daily_close.json",
    }

    def fake_download(url, params=None):
        for key, name in routes.items():
            if key in url:
                return (FX / name).read_text(encoding="utf-8")
        raise AssertionError(f"未预期的请求: {url}")

    monkeypatch.setattr(tw_bulk, "_download", fake_download)
    yield
    tw_bulk.reset_cache()


# ---------------------------------------------------------------- 首页指数


def test_market_indices_list_taiwan_first():
    from src.modules.market.api.market import MARKET_INDICES

    assert [i["symbol"] for i in MARKET_INDICES[:2]] == ["TWII", "TPEX"]
    assert all(i["market"] == "TW" for i in MARKET_INDICES[:2])


def test_indices_endpoint_returns_tw_quotes(monkeypatch):
    from src.modules.market.api import market as m

    class _MD:
        def index_quotes(self, syms):
            return []

        def tw_index_quotes(self):
            return [
                {"symbol": "TWII", "name": "加權指數", "current_price": 48015.15, "change_pct": 0.16,
                 "change_amount": 75.0, "volume": 0.0, "turnover": 0.0},
                {"symbol": "TPEX", "name": "櫃買指數", "current_price": 417.07, "change_pct": -0.2,
                 "change_amount": -0.8, "volume": 0.0, "turnover": 0.0},
            ]

    m.clear_indices_cache()
    monkeypatch.setattr(m, "get_market_data", lambda: _MD(), raising=False)
    monkeypatch.setattr(m, "_spark_for", lambda idx: [])
    out = asyncio.run(m.get_market_indices())
    rows = out if isinstance(out, list) else out.get("data", out)
    by = {r["symbol"]: r for r in rows}
    assert by["TWII"]["current_price"] == 48015.15
    assert by["TPEX"]["current_price"] == 417.07
    m.clear_indices_cache()


# ---------------------------------------------------------------- 市场状态排序


def test_market_status_lists_taiwan_first():
    from src.modules.market.api.stocks import get_market_status

    res = get_market_status()
    rows = res if isinstance(res, list) else res.get("data", res)
    codes = [r.get("code") or r.get("market") for r in rows]
    assert codes[0] == "TW"
    assert codes == ["TW", "TWF", "CN", "HK", "US"]   # F5:期货排在台股之后


# ---------------------------------------------------------------- 机会发现


def test_tw_hot_stocks_by_turnover(offline_tw):
    from src.modules.market.tw_discovery import tw_hot_stocks

    rows = tw_hot_stocks(mode="turnover", limit=3)
    assert len(rows) == 3
    assert all(r["market"] == "TW" for r in rows)
    values = [r["turnover"] for r in rows]
    assert values == sorted(values, reverse=True)
    assert "730123" not in {r["symbol"] for r in tw_hot_stocks(mode="turnover", limit=50)}  # 权证排除
    keys = {"symbol", "name", "market", "price", "change_pct", "turnover", "volume"}
    assert keys <= set(rows[0])


def test_tw_hot_stocks_by_gainers(offline_tw):
    from src.modules.market.tw_discovery import tw_hot_stocks

    rows = tw_hot_stocks(mode="gainers", limit=10)
    pcts = [r["change_pct"] for r in rows]
    assert pcts == sorted(pcts, reverse=True)
    world = next(r for r in rows if r["symbol"] == "5347")
    # 世界: 收 181.00, 涨 +2.50 → 昨收 178.50
    assert abs(world["change_pct"] - 2.50 / 178.50 * 100) < 1e-6
    assert world["price"] == 181.0


def test_discovery_api_tw_hot_stocks_ok(offline_tw):
    from src.modules.market.api import discovery

    discovery._cache.clear()
    data = asyncio.run(discovery.get_hot_stocks(market="TW", mode="turnover", limit=5, db=None))
    rows = data if isinstance(data, list) else data.get("data", data)
    assert rows and all(r["market"] == "TW" for r in rows)


def test_discovery_api_tw_boards_empty_not_error(offline_tw):
    from src.modules.market.api import discovery

    discovery._cache.clear()
    data = asyncio.run(discovery.get_hot_boards(market="TW", mode="gainers", limit=12, db=None))
    rows = data if isinstance(data, list) else data.get("data", data)
    assert rows == []


# ---------------------------------------------------------------- 预设帐户


def test_default_account_name_follows_default_language():
    from src.platform.persistence import database

    assert database.default_account_name() == "預設帳戶"


def _accounts_engine(tmp_path, names):
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{tmp_path / 'accounts.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)"))
        for name in names:
            conn.execute(text("INSERT INTO accounts (name) VALUES (:n)"), {"n": name})
    return engine


def _account_names(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        return [r.name for r in conn.execute(text("SELECT name FROM accounts ORDER BY id"))]


@pytest.mark.parametrize("legacy", ["默认账户", "Default account"])
def test_legacy_default_account_name_is_migrated(tmp_path, monkeypatch, legacy):
    from src.platform.persistence import database

    backups = []
    monkeypatch.setattr(database, "_backup_db_before_migration", lambda: backups.append(1))
    engine = _accounts_engine(tmp_path, [legacy, "默认账户"])

    database._migrate_default_account_name(engine)

    # 只改第一個（內建）帳戶，第二個同名帳戶是使用者建的，不動
    assert _account_names(engine) == ["預設帳戶", "默认账户"]
    assert backups == [1]


@pytest.mark.parametrize("name", ["我的帳戶", "預設帳戶"])
def test_default_account_name_migration_leaves_others_alone(tmp_path, monkeypatch, name):
    from src.platform.persistence import database

    backups = []
    monkeypatch.setattr(database, "_backup_db_before_migration", lambda: backups.append(1))
    engine = _accounts_engine(tmp_path, [name])

    database._migrate_default_account_name(engine)

    assert _account_names(engine) == [name]
    assert backups == []
