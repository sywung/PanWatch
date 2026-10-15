"""集保股權分散表：儲存、API、排程、AI 文字。

資料來源只有最新一週，所以趨勢靠每週快照累積；所有網路來源在此以
`fetch_shareholders` 替身取代，測試不碰外網。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.platform.persistence.models  # noqa: F401
from marketdata.types import ShareholderItem
from src.modules.market import shareholder_dispersion as svc
from src.modules.market.api.shareholders import router
from src.platform.persistence.database import Base, get_db
from src.platform.persistence.models import ShareholderDispersion, Stock

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- helpers


def _levels(big_pct: float = 84.77, total_holders: int = 3_020_649) -> list[dict]:
    rows = [{"level": n, "holders": 10 * n, "shares": 1000 * n, "pct": 0.5} for n in range(1, 15)]
    rows.append({"level": 15, "holders": 1487, "shares": 21_984_569_643, "pct": big_pct})
    rows.append({"level": 16, "holders": 1, "shares": 1000, "pct": 0.0})
    rows.append({"level": 17, "holders": total_holders, "shares": 25_932_370_067, "pct": 100.0})
    return rows


def _item(symbol="2330", date="2026-10-01", *, thousand=84.77, holders=3_020_649, big=87.53):
    return ShareholderItem(
        report_date=date, symbol=symbol, holder_num=holders,
        avg_shares=25_932_370_067 / holders,
        big_holder_ratio=big, thousand_lot_ratio=thousand,
        levels=_levels(thousand, holders),
    )


@pytest.fixture(autouse=True)
def _no_web_history(monkeypatch):
    """回補歷史會打集保官網；本檔的案例都不該碰外網。回補專屬案例在 test_shareholder_backfill.py。"""
    monkeypatch.setattr(svc, "fetch_history_levels", lambda symbol, skip_dates=(): [])


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/shareholders")

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


# ---------------------------------------------------------------- vendor item


def test_shareholder_item_levels_defaults_to_none():
    item = ShareholderItem(report_date="2026-10-01", symbol="2330")
    assert item.levels is None


# ---------------------------------------------------------------- 遷移 / 模型


def test_migration_9004_creates_table_and_is_registered():
    from src.platform.persistence.migrations import MIGRATIONS

    versions = {m.version: m.name for m in MIGRATIONS}
    assert versions[9004] == "shareholder_dispersion"
    assert [m.version for m in MIGRATIONS] == sorted(m.version for m in MIGRATIONS)


def test_migration_creates_unique_constraint_on_real_sqlite(tmp_path):
    from src.platform.persistence.migrations import MIGRATIONS

    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    migration = next(m for m in MIGRATIONS if m.version == 9004)
    fn = migration.runner
    with engine.begin() as conn:
        fn(conn)
        fn(conn)  # 冪等
    assert "shareholder_dispersion" in inspect(engine).get_table_names()
    with engine.begin() as conn:
        insert = text(
            "INSERT INTO shareholder_dispersion(symbol, market, data_date, levels) "
            "VALUES ('2330','TW','2026-10-01','[]')"
        )
        conn.execute(insert)
        with pytest.raises(Exception):
            conn.execute(insert)


# ---------------------------------------------------------------- store_items


def test_store_items_inserts_and_is_idempotent(db):
    assert svc.store_items(db, [_item("2330"), _item("6488", holders=100_000)]) == 2
    assert svc.store_items(db, [_item("2330")]) == 0  # 同代號同日期不重複
    assert db.query(ShareholderDispersion).count() == 2
    row = db.query(ShareholderDispersion).filter_by(symbol="2330").one()
    assert row.market == "TW" and row.data_date == "2026-10-01"
    assert row.holder_num == 3_020_649
    assert row.thousand_lot_ratio == 84.77
    assert len(row.levels) == 17 and row.levels[14]["pct"] == 84.77


def test_store_items_skips_items_without_date_or_levels(db):
    bad = [
        ShareholderItem(report_date="", symbol="2330", levels=_levels()),
        ShareholderItem(report_date="2026-10-01", symbol="2330", levels=None),
        ShareholderItem(report_date="2026-10-01", symbol="2330", levels=[]),
    ]
    assert svc.store_items(db, bad) == 0
    assert db.query(ShareholderDispersion).count() == 0


def test_store_items_keeps_each_week(db):
    assert svc.store_items(db, [_item(date="2026-09-24"), _item(date="2026-10-01")]) == 2
    assert svc.store_items(db, [_item(date="2026-10-01")]) == 0
    assert svc.store_items(db, [_item(date="2026-10-08")]) == 1


# ---------------------------------------------------------------- get_history / serialize


def _seed_three_weeks(db):
    svc.store_items(db, [
        _item(date="2026-09-24", thousand=84.60, holders=3_021_883),
        _item(date="2026-10-01", thousand=84.65, holders=3_021_000),
        _item(date="2026-10-08", thousand=84.77, holders=3_020_649),
    ])


def test_get_history_is_ascending_and_limited_to_last_weeks(db):
    _seed_three_weeks(db)
    rows = svc.get_history(db, "2330", "TW", weeks=2)
    assert [r.data_date for r in rows] == ["2026-10-01", "2026-10-08"]
    assert svc.get_history(db, "9999", "TW", weeks=26) == []


def test_serialize_latest_has_levels_and_week_over_week_changes(db):
    _seed_three_weeks(db)
    out = svc.serialize(svc.get_history(db, "2330", "TW", weeks=26))
    latest = out["latest"]
    assert latest["data_date"] == "2026-10-08"
    assert latest["holder_num"] == 3_020_649
    assert len(latest["levels"]) == 17
    assert latest["holder_num_change"] == 3_020_649 - 3_021_000
    assert latest["thousand_lot_ratio_change"] == pytest.approx(0.12)
    assert [h["data_date"] for h in out["history"]] == ["2026-09-24", "2026-10-01", "2026-10-08"]
    assert set(out["history"][0]) == {
        "data_date", "holder_num", "avg_shares", "big_holder_ratio", "thousand_lot_ratio",
    }


def test_serialize_single_week_has_none_changes_and_empty_is_none(db):
    svc.store_items(db, [_item()])
    latest = svc.serialize(svc.get_history(db, "2330", "TW", weeks=26))["latest"]
    assert latest["holder_num_change"] is None
    assert latest["thousand_lot_ratio_change"] is None
    assert latest["big_holder_ratio_change"] is None
    assert svc.serialize([]) == {"latest": None, "history": []}


# ---------------------------------------------------------------- fetch_and_store / watchlist


def test_fetch_and_store_uses_fetch_shareholders(db, monkeypatch):
    calls = []

    def fake(symbols):
        calls.append(list(symbols))
        return [_item(s) for s in symbols]

    monkeypatch.setattr(svc, "fetch_shareholders", fake)
    assert svc.fetch_and_store(db, ["2330", "6488"]) == 2
    assert calls == [["2330", "6488"]]
    assert svc.fetch_and_store(db, []) == 0
    assert calls == [["2330", "6488"]]  # 空清單不打來源


def test_fetch_and_store_swallows_source_failure(db, monkeypatch):
    def boom(symbols):
        raise RuntimeError("tdcc down")

    monkeypatch.setattr(svc, "fetch_shareholders", boom)
    assert svc.fetch_and_store(db, ["2330"]) == 0  # 失敗回 0，不拋


def test_collect_watchlist_only_tw_and_deduplicated(db, monkeypatch):
    db.add_all([
        Stock(symbol="2330", name="台積電", market="TW"),
        Stock(symbol="2330", name="台積電", market="TW"),
        Stock(symbol="AAPL", name="Apple", market="US"),
        Stock(symbol="00878", name="國泰永續高股息", market="TW"),
    ])
    db.commit()
    seen = []
    monkeypatch.setattr(svc, "fetch_shareholders", lambda s: seen.append(sorted(s)) or [_item(x) for x in s])
    assert svc.collect_watchlist(db) == 2
    assert seen == [["00878", "2330"]]


# ---------------------------------------------------------------- API


def test_api_returns_latest_levels_and_history(client, db):
    _seed_three_weeks(db)
    body = client.get("/api/shareholders/dispersion", params={"symbol": "2330", "market": "TW"}).json()
    assert body["symbol"] == "2330" and body["market"] == "TW"
    assert body["latest"]["data_date"] == "2026-10-08"
    assert len(body["latest"]["levels"]) == 17
    assert len(body["history"]) == 3


def test_api_normalizes_symbol_and_respects_weeks(client, db):
    _seed_three_weeks(db)
    body = client.get("/api/shareholders/dispersion", params={"symbol": " 2330 ", "weeks": 1}).json()
    assert body["symbol"] == "2330"
    assert [h["data_date"] for h in body["history"]] == ["2026-10-08"]


def test_api_lazy_fetches_when_nothing_stored(client, db, monkeypatch):
    monkeypatch.setattr(svc, "fetch_shareholders", lambda s: [_item(x) for x in s])
    body = client.get("/api/shareholders/dispersion", params={"symbol": "2330"}).json()
    assert body["latest"]["data_date"] == "2026-10-01"
    assert db.query(ShareholderDispersion).count() == 1


def test_api_unknown_symbol_is_200_with_empty_payload(client, monkeypatch):
    monkeypatch.setattr(svc, "fetch_shareholders", lambda s: [])
    resp = client.get("/api/shareholders/dispersion", params={"symbol": "9999"})
    assert resp.status_code == 200
    assert resp.json() == {"symbol": "9999", "market": "TW", "latest": None, "history": []}


def test_api_source_failure_is_200_empty_not_500(client, monkeypatch):
    def boom(symbols):
        raise RuntimeError("tdcc down")

    monkeypatch.setattr(svc, "fetch_shareholders", boom)
    resp = client.get("/api/shareholders/dispersion", params={"symbol": "2330"})
    assert resp.status_code == 200 and resp.json()["latest"] is None


def test_api_rejects_non_tw_market_and_bad_params(client):
    resp = client.get("/api/shareholders/dispersion", params={"symbol": "AAPL", "market": "US"})
    assert resp.status_code == 400
    assert "shareholder_dispersion_market_unsupported" in resp.text
    assert client.get("/api/shareholders/dispersion", params={"symbol": "  "}).status_code == 422
    assert client.get("/api/shareholders/dispersion").status_code == 422
    assert client.get("/api/shareholders/dispersion", params={"symbol": "2330", "weeks": 0}).status_code == 422
    assert client.get("/api/shareholders/dispersion", params={"symbol": "2330", "weeks": 105}).status_code == 422


def test_router_is_mounted_in_application():
    source = (ROOT / "src" / "bootstrap" / "application.py").read_text(encoding="utf-8")
    assert "shareholders.router" in source and "/api/shareholders" in source


# ---------------------------------------------------------------- 排程


def test_scheduler_registers_daily_dispersion_job():
    from src.modules.market.price_alert_scheduler import PriceAlertScheduler

    s = PriceAlertScheduler(timezone="Asia/Taipei")
    s.register_jobs()
    job = s.scheduler.get_job("shareholder_dispersion_daily")
    assert job is not None
    trigger = str(job.trigger)
    assert "hour='6'" in trigger and "minute='30'" in trigger
    assert job.trigger.timezone.key == "Asia/Taipei"
    assert "day_of_week" not in trigger  # 每天跑；冪等，免得猜集保哪天公布
    # 原有工作沒被擠掉
    assert s.scheduler.get_job("price_alert_scan") is not None
    assert s.scheduler.get_job("futures_rollover_morning") is not None


# ---------------------------------------------------------------- AI 文字


def test_dispersion_line_zh_with_week_over_week(db):
    _seed_three_weeks(db)
    line = svc.dispersion_line_for(db, "2330", "TW", "zh-CN")
    assert "2026-10-08" in line
    assert "84.77" in line and "+0.12" in line
    assert "3,020,649" in line and "-351" in line


def test_dispersion_line_zh_tw_is_localized(db):
    _seed_three_weeks(db)
    line = svc.dispersion_line_for(db, "2330", "TW", "zh-TW")
    assert "集保" in line and "84.77" in line  # 繁體「集保」
    assert "週 +0.12" in line and "週 -351" in line and "周" not in line  # 台灣用字「週」


def test_dispersion_line_en(db):
    _seed_three_weeks(db)
    line = svc.dispersion_line_for(db, "2330", "TW", "en-US")
    assert "TDCC" in line and "84.77" in line and "+0.12" in line and "-351" in line


def test_dispersion_line_single_week_has_no_change_text(db):
    svc.store_items(db, [_item()])
    line = svc.dispersion_line_for(db, "2330", "TW", "en-US")
    assert "84.77" in line and "WoW" not in line


def test_dispersion_line_empty_for_non_tw_or_no_data(db):
    assert svc.dispersion_line_for(db, "2330", "TW", "zh-TW") == ""
    _seed_three_weeks(db)
    assert svc.dispersion_line_for(db, "2330", "US", "zh-TW") == ""
    assert svc.dispersion_line_for(db, "AAPL", "US", "en-US") == ""


def test_dispersion_line_never_fetches_network(db, monkeypatch):
    # 用呼叫紀錄而非丟例外：fetch_and_store 會吞掉來源例外，丟 AssertionError 會被誤吞
    fetched, backfilled = [], []
    monkeypatch.setattr(svc, "fetch_shareholders", lambda s: fetched.append(list(s)) or [])
    monkeypatch.setattr(svc, "fetch_history_levels", lambda s, skip_dates=(): backfilled.append(s) or [])
    assert svc.dispersion_line_for(db, "2330", "TW", "zh-TW") == ""
    _seed_three_weeks(db)
    assert svc.dispersion_line_for(db, "2330", "TW", "zh-TW") != ""
    assert fetched == [] and backfilled == []


@pytest.mark.parametrize("module", ["daily_report", "premarket_outlook", "intraday_monitor"])
def test_agents_include_dispersion_line(module):
    source = (ROOT / "src" / "modules" / "automation" / f"{module}.py").read_text(encoding="utf-8")
    assert "dispersion_line_for" in source
