"""股權分散表歷史回補：集保官網查詢頁一次可取最近 51 週，補進本機快照表。

網路只經 `svc.fetch_history_levels(symbol, skip_dates)` -> list[(iso_date, levels)]，測試替換它。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.platform.persistence.models  # noqa: F401
from marketdata.types import ShareholderItem
from src.modules.market import shareholder_dispersion as svc
from src.modules.market.api.shareholders import router
from src.platform.persistence.database import Base, get_db
from src.platform.persistence.models import ShareholderDispersion, Stock


def _levels(pct15: float, holders17: int, shares17: int = 25_000_000_000) -> list[dict]:
    rows = [{"level": n, "holders": n, "shares": n * 100, "pct": 1.0} for n in range(1, 12)]
    rows += [
        {"level": 12, "holders": 580, "shares": 1, "pct": 1.0},
        {"level": 13, "holders": 340, "shares": 1, "pct": 0.9},
        {"level": 14, "holders": 220, "shares": 1, "pct": 0.7},
        {"level": 15, "holders": 1487, "shares": 1, "pct": pct15},
        {"level": 16, "holders": 1, "shares": 1000, "pct": 0.0},
        {"level": 17, "holders": holders17, "shares": shares17, "pct": 100.0},
    ]
    return rows


WEEKS = [  # 官網順序：新→舊
    ("2026-10-08", _levels(84.77, 3_020_649)),
    ("2026-10-02", _levels(84.70, 3_021_000)),
    ("2026-09-24", _levels(84.65, 3_021_500)),
]


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
def web(monkeypatch):
    """替身：回傳 WEEKS 中不在 skip_dates 的週，並記錄呼叫。"""
    calls = []

    def fake(symbol, skip_dates=()):
        calls.append((symbol, set(skip_dates)))
        return [(d, lv) for d, lv in WEEKS if d not in set(skip_dates)]

    monkeypatch.setattr(svc, "fetch_history_levels", fake)
    fake.calls = calls
    return fake


# ---------------------------------------------------------------- backfill_symbol


def test_backfill_symbol_stores_all_weeks_with_derived_summary(db, web):
    assert svc.backfill_symbol(db, "2330") == 3
    rows = {r.data_date: r for r in db.query(ShareholderDispersion).filter_by(symbol="2330")}
    assert set(rows) == {"2026-10-08", "2026-10-02", "2026-09-24"}
    row = rows["2026-10-08"]
    assert row.market == "TW"
    assert row.holder_num == 3_020_649                          # 第 17 級人數
    assert row.avg_shares == pytest.approx(25_000_000_000 / 3_020_649)
    assert row.thousand_lot_ratio == 84.77                      # 第 15 級
    assert row.big_holder_ratio == pytest.approx(1.0 + 0.9 + 0.7 + 84.77)  # 12–15 級
    assert len(row.levels) == 17


def test_backfill_symbol_passes_already_stored_dates_and_is_idempotent(db, web):
    svc.backfill_symbol(db, "2330")
    assert svc.backfill_symbol(db, "2330") == 0
    assert web.calls[0] == ("2330", set())
    assert web.calls[1] == ("2330", {"2026-10-08", "2026-10-02", "2026-09-24"})
    assert db.query(ShareholderDispersion).count() == 3


def test_backfill_symbol_fills_only_the_gaps(db, web):
    svc.store_items(db, [ShareholderItem(
        report_date="2026-10-02", symbol="2330", holder_num=1, levels=_levels(84.70, 3_021_000),
    )])
    assert svc.backfill_symbol(db, "2330") == 2
    assert db.query(ShareholderDispersion).count() == 3


def test_backfill_symbol_swallows_failure_and_skips_incomplete_weeks(db, monkeypatch):
    def boom(symbol, skip_dates=()):
        raise RuntimeError("tdcc web down")

    monkeypatch.setattr(svc, "fetch_history_levels", boom)
    assert svc.backfill_symbol(db, "2330") == 0

    monkeypatch.setattr(svc, "fetch_history_levels", lambda s, skip_dates=(): [
        ("2026-10-08", []),                                   # 空分級
        ("2026-10-02", _levels(84.7, 1)[:10]),               # 缺第 15/17 級
        ("2026-09-24", _levels(84.65, 3_021_500)),
    ])
    assert svc.backfill_symbol(db, "2330") == 1
    assert [r.data_date for r in db.query(ShareholderDispersion)] == ["2026-09-24"]


def test_backfill_symbol_rejects_non_tw_market(db, web):
    assert svc.backfill_symbol(db, "AAPL", market="US") == 0
    assert web.calls == []


# ---------------------------------------------------------------- 排程：新股補歷史


def test_collect_watchlist_backfills_only_underfilled_symbols(db, web, monkeypatch):
    db.add_all([
        Stock(symbol="2330", name="台積電", market="TW"),
        Stock(symbol="2317", name="鴻海", market="TW"),
    ])
    db.commit()
    # 2317 已有 3 週；2330 一筆都沒有
    for d, lv in WEEKS:
        svc.store_items(db, [ShareholderItem(report_date=d, symbol="2317", holder_num=1, levels=lv)])
    monkeypatch.setattr(svc, "fetch_shareholders", lambda symbols: [])
    svc.collect_watchlist(db)
    assert [c[0] for c in web.calls] == ["2330"]
    assert db.query(ShareholderDispersion).filter_by(symbol="2330").count() == 3


# ---------------------------------------------------------------- API lazy


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/shareholders")

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_api_first_open_backfills_history(client, db, web, monkeypatch):
    monkeypatch.setattr(svc, "fetch_shareholders", lambda s: [])
    body = client.get("/api/shareholders/dispersion", params={"symbol": "2330"}).json()
    assert [h["data_date"] for h in body["history"]] == ["2026-09-24", "2026-10-02", "2026-10-08"]
    assert body["latest"]["thousand_lot_ratio_change"] == pytest.approx(0.07)


def test_api_does_not_backfill_again_once_history_exists(client, db, web, monkeypatch):
    monkeypatch.setattr(svc, "fetch_shareholders", lambda s: [])
    client.get("/api/shareholders/dispersion", params={"symbol": "2330"})
    n = len(web.calls)
    client.get("/api/shareholders/dispersion", params={"symbol": "2330"})
    assert len(web.calls) == n


def test_api_backfill_failure_still_returns_latest(client, db, monkeypatch):
    def boom(symbol, skip_dates=()):
        raise RuntimeError("tdcc web down")

    item = ShareholderItem(report_date="2026-10-08", symbol="2330", holder_num=3_020_649,
                           thousand_lot_ratio=84.77, big_holder_ratio=87.4, levels=_levels(84.77, 3_020_649))
    monkeypatch.setattr(svc, "fetch_shareholders", lambda s: [item])
    monkeypatch.setattr(svc, "fetch_history_levels", boom)
    resp = client.get("/api/shareholders/dispersion", params={"symbol": "2330"})
    assert resp.status_code == 200
    assert resp.json()["latest"]["data_date"] == "2026-10-08"
    assert len(resp.json()["history"]) == 1


def test_api_unknown_symbol_does_not_loop_backfill(client, db, monkeypatch):
    calls = []
    monkeypatch.setattr(svc, "fetch_shareholders", lambda s: [])
    monkeypatch.setattr(svc, "fetch_history_levels", lambda s, skip_dates=(): calls.append(s) or [])
    resp = client.get("/api/shareholders/dispersion", params={"symbol": "9999"})
    assert resp.json()["latest"] is None
    assert calls == ["9999"]  # 只試一次
