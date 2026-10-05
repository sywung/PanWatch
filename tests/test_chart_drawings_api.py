"""商品 K 線圖畫線 API 的 CRUD 與輸入驗證。"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.platform.persistence.models  # noqa: F401
from src.modules.market.api.chart_drawings import router
from src.platform.persistence.database import Base, get_db


def _client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router, prefix="/api/chart-drawings")

    def _db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db
    return TestClient(app), engine


def test_chart_drawing_crud_and_product_scoped_clear():
    client, engine = _client()
    created = client.post("/api/chart-drawings", json={
        "symbol": " 2330 ", "market": "tw", "kind": "hline", "data": {"price": 950},
    })
    assert created.status_code == 200
    hline = created.json()
    assert (hline["symbol"], hline["market"], hline["kind"], hline["data"]) == (
        "2330", "TW", "hline", {"price": 950.0}
    )

    trend = client.post("/api/chart-drawings", json={
        "symbol": "2330", "market": "TW", "kind": "trend",
        "data": {"p1": {"time": "2026-10-01", "price": 900},
                 "p2": {"time": "2026-10-02 09:05", "price": 920}},
    }).json()
    same_symbol_other_market = client.post("/api/chart-drawings", json={
        "symbol": "2330", "market": "TWF", "kind": "hline", "data": {"price": 1000},
    }).json()

    listed = client.get("/api/chart-drawings", params={"symbol": "2330", "market": "TW"})
    assert [row["id"] for row in listed.json()] == [hline["id"], trend["id"]]
    updated = client.put(f"/api/chart-drawings/{hline['id']}", json={"data": {"price": 960}})
    assert updated.status_code == 200
    assert updated.json()["data"] == {"price": 960.0}

    cleared = client.delete("/api/chart-drawings", params={"symbol": "2330", "market": "TW"})
    assert cleared.json() == {"deleted": 2}
    assert client.get("/api/chart-drawings", params={"symbol": "2330", "market": "TW"}).json() == []
    remaining = client.get("/api/chart-drawings", params={"symbol": "2330", "market": "TWF"})
    assert [row["id"] for row in remaining.json()] == [same_symbol_other_market["id"]]
    assert client.delete(f"/api/chart-drawings/{same_symbol_other_market['id']}").json() == {"deleted": 1}
    engine.dispose()


@pytest.mark.parametrize("payload", [
    {"symbol": " ", "market": "TW", "kind": "hline", "data": {"price": 1}},
    {"symbol": "A" * 33, "market": "TW", "kind": "hline", "data": {"price": 1}},
    {"symbol": "2330", "market": "NOPE", "kind": "hline", "data": {"price": 1}},
    {"symbol": "2330", "market": "TW", "kind": "other", "data": {"price": 1}},
    {"symbol": "2330", "market": "TW", "kind": "hline", "data": {"price": 1, "extra": 2}},
    {"symbol": "2330", "market": "TW", "kind": "hline", "data": {}},
    {"symbol": "2330", "market": "TW", "kind": "hline", "data": {"price": 0}},
    {"symbol": "2330", "market": "TW", "kind": "hline", "data": {"price": float("inf")}},
    {"symbol": "2330", "market": "TW", "kind": "hline", "data": {"price": float("nan")}},
    {"symbol": "2330", "market": "TW", "kind": "trend", "data": {"p1": {"time": "2026-02-30", "price": 1}, "p2": {"time": "2026-03-01", "price": 2}}},
    {"symbol": "2330", "market": "TW", "kind": "trend", "data": {"p1": {"time": "2026-03-01 24:00", "price": 1}, "p2": {"time": "2026-03-02", "price": 2}}},
    {"symbol": "2330", "market": "TW", "kind": "trend", "data": {"p1": {"time": "2026/03/01", "price": 1}, "p2": {"time": "2026-03-02", "price": 2}}},
    {"symbol": "2330", "market": "TW", "kind": "trend", "data": {"p1": {"time": "2026-03-01", "price": -1}, "p2": {"time": "2026-03-02", "price": 2}}},
    {"symbol": "2330", "market": "TW", "kind": "trend", "data": {"p1": {"time": "2026-03-01", "price": 1, "extra": 3}, "p2": {"time": "2026-03-02", "price": 2}}},
    {"symbol": "2330", "market": "TW", "kind": "trend", "data": {"p1": {"time": "2026-03-01", "price": 1}, "p2": {"time": "2026-03-02", "price": 2}, "extra": 0}},
    {"symbol": "2330", "market": "TW", "kind": "hline", "data": {"price": 1}, "extra": 1},
])
def test_chart_drawing_validation_rejects_invalid_inputs(payload):
    client, engine = _client()
    response = client.post(
        "/api/chart-drawings",
        content=json.dumps(payload, allow_nan=True),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text
    assert "message" in response.json()["detail"]
    engine.dispose()


def test_chart_drawing_limit_is_200_per_product():
    client, engine = _client()
    for _ in range(200):
        response = client.post("/api/chart-drawings", json={
            "symbol": "2330", "market": "TW", "kind": "hline", "data": {"price": 1},
        })
        assert response.status_code == 200
    over_limit = client.post("/api/chart-drawings", json={
        "symbol": "2330", "market": "TW", "kind": "hline", "data": {"price": 1},
    })
    assert over_limit.status_code == 400
    other_product = client.post("/api/chart-drawings", json={
        "symbol": "2330", "market": "TWF", "kind": "hline", "data": {"price": 1},
    })
    assert other_product.status_code == 200
    engine.dispose()


def test_chart_drawings_migration_is_idempotent_on_existing_database(tmp_path):
    from sqlalchemy import inspect
    from src.platform.persistence.migrations import _m9003_chart_drawings

    engine = create_engine(f"sqlite:///{tmp_path / 'existing.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE existing_records (id INTEGER PRIMARY KEY)")
        _m9003_chart_drawings(conn)
        _m9003_chart_drawings(conn)
        columns = {column["name"] for column in inspect(conn).get_columns("chart_drawings")}
        indexes = [index["name"] for index in inspect(conn).get_indexes("chart_drawings")]
    assert {"id", "symbol", "market", "kind", "data", "created_at", "updated_at"} <= columns
    assert indexes.count("ix_chart_drawings_market_symbol") == 1
    engine.dispose()
