"""元大转接服务的 HTTP 介面(FastAPI)。只绑本机/内部网路;可选 bearer token。"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

import app as gateway
import client as yc


class FakeClient:
    def __init__(self, logged_in=True):
        self.logged_in = logged_in
        self.calls = []

    def status(self):
        return {"connected": self.logged_in, "logged_in": self.logged_in, "account": "S9887****091",
                "last_error": "", "env": "PROD"}

    def quotes(self, items, timeout=10):
        self.calls.append(("quotes", items))
        if not self.logged_in:
            raise yc.NotLoggedIn()
        return [{"market": m, "code": c, "price": 1.0} for m, c in items]

    def kline(self, market, code, period, start, end, timeout=15):
        self.calls.append(("kline", market, code, period, start, end))
        return [{"time": "2026-10-01 00:00:00", "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}]


@pytest.fixture
def api(monkeypatch):
    fake = FakeClient()
    monkeypatch.delenv("GATEWAY_TOKEN", raising=False)
    return TestClient(gateway.create_app(fake)), fake


def test_health(api):
    c, _ = api
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["logged_in"] is True
    assert "password" not in r.text.lower()


def test_quotes_endpoint(api):
    c, fake = api
    r = c.post("/quotes", json={"items": [{"market": "TSE", "code": "2330"}]})
    assert r.status_code == 200
    assert r.json()["data"][0]["code"] == "2330"
    assert fake.calls == [("quotes", [("TSE", "2330")])]


def test_quotes_not_logged_in_returns_503(monkeypatch):
    c = TestClient(gateway.create_app(FakeClient(logged_in=False)))
    r = c.post("/quotes", json={"items": [{"market": "TSE", "code": "2330"}]})
    assert r.status_code == 503


def test_kline_endpoint(api):
    c, fake = api
    r = c.get("/kline", params={"market": "TSE", "code": "2330", "period": "1d",
                                "start": "2026-10-01", "end": "2026-10-02"})
    assert r.status_code == 200 and len(r.json()["data"]) == 1
    assert fake.calls[-1] == ("kline", "TSE", "2330", "1d", date(2026, 10, 1), date(2026, 10, 2))


def test_bad_input_returns_400(api, monkeypatch):
    c, fake = api

    def bad(*a, **k):
        raise ValueError("unknown market")

    monkeypatch.setattr(fake, "quotes", bad)
    r = c.post("/quotes", json={"items": [{"market": "X", "code": "1"}]})
    assert r.status_code == 400


def test_token_required_when_configured(monkeypatch):
    monkeypatch.setenv("GATEWAY_TOKEN", "s3cret")
    c = TestClient(gateway.create_app(FakeClient()))
    assert c.get("/health").status_code == 200          # 健康检查免 token
    assert c.post("/quotes", json={"items": []}).status_code == 401
    ok = c.post("/quotes", json={"items": []}, headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_no_order_routes(api):
    c, _ = api
    paths = [r.path for r in c.app.routes]
    assert not [p for p in paths if "order" in p.lower()]
