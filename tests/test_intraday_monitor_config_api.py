"""盤中監測參數（止盈/止損/異動門檻）可由 API 修改：驗證欄位、儲存後重載排程。

2026-10-06 使用者問「浮盈達標」的 10% 門檻能不能在設定頁改——原本只有 DB 能改，
而且排程器只在啟動時讀一次 config，存了也不會生效。
"""

from __future__ import annotations

import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.platform.persistence.models  # noqa: F401
from src.modules.automation.api import agents as agents_api
from src.modules.automation.api.agents import router
from src.modules.automation.intraday_monitor import IntradayMonitorAgent
from src.platform.persistence.database import Base, get_db
from src.platform.persistence.models import AgentConfig

ORIGINAL = {
    "event_only": True,
    "price_alert_threshold": 3.0,
    "volume_alert_ratio": 2.0,
    "stop_loss_warning": -5.0,
    "take_profit_warning": 10.0,
    "throttle_minutes": 30,
}

VALID = {
    "event_only": False,
    "price_alert_threshold": 4.5,
    "volume_alert_ratio": 2.5,
    "stop_loss_warning": -8.0,
    "take_profit_warning": 25.0,
    "throttle_minutes": 45,
}


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as s:
        s.add(AgentConfig(
            name="intraday_monitor", display_name="盘中监测", kind="workflow",
            enabled=True, schedule="*/5 9-13 * * 1-5", execution_mode="single",
            config=dict(ORIGINAL),
        ))
        s.add(AgentConfig(
            name="daily_report", display_name="收盘复盘", kind="workflow",
            enabled=True, schedule="0 14 * * 1-5", config={},
        ))
        s.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/agents")

    def _db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db

    reloads: list[int] = []
    fake_server = types.ModuleType("server")

    def reload_scheduler():
        reloads.append(1)
        return True

    fake_server.reload_scheduler = reload_scheduler
    monkeypatch.setitem(sys.modules, "server", fake_server)

    def stored(name="intraday_monitor", field="config"):
        with Session() as s:
            row = s.query(AgentConfig).filter(AgentConfig.name == name).one()
            return getattr(row, field)

    return TestClient(app), stored, reloads, fake_server


def test_valid_full_config_is_saved_and_usable_by_agent(env):
    client, stored, reloads, _ = env
    resp = client.put("/api/agents/intraday_monitor", json={"config": VALID})
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"] == VALID
    assert stored() == VALID

    agent = IntradayMonitorAgent(**stored())
    assert agent.take_profit_warning == 25.0
    assert agent.stop_loss_warning == -8.0
    assert agent.throttle_minutes == 45
    assert agent.event_only is False


def test_integer_numbers_are_accepted_for_float_fields(env):
    client, stored, _, _ = env
    cfg = {**VALID, "take_profit_warning": 20, "stop_loss_warning": -6}
    resp = client.put("/api/agents/intraday_monitor", json={"config": cfg})
    assert resp.status_code == 200, resp.text
    assert stored()["take_profit_warning"] == 20
    assert stored()["stop_loss_warning"] == -6


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("take_profit_warning", 0),
        ("take_profit_warning", -1),
        ("take_profit_warning", 1001),
        ("take_profit_warning", "20"),
        ("take_profit_warning", True),
        ("take_profit_warning", None),
        ("stop_loss_warning", 0),
        ("stop_loss_warning", 5),
        ("stop_loss_warning", -101),
        ("price_alert_threshold", 0),
        ("price_alert_threshold", 51),
        ("volume_alert_ratio", 0),
        ("volume_alert_ratio", 51),
        ("throttle_minutes", -1),
        ("throttle_minutes", 1441),
        ("throttle_minutes", 1.5),
        ("throttle_minutes", True),
        ("event_only", "yes"),
        ("event_only", 1),
    ],
)
def test_invalid_value_is_rejected_and_nothing_changes(env, field, value):
    client, stored, reloads, _ = env
    resp = client.put(
        "/api/agents/intraday_monitor", json={"config": {**VALID, field: value}}
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_agent_config"
    assert field in detail["message"]
    assert stored() == ORIGINAL
    assert reloads == []


def test_unknown_key_is_rejected(env):
    client, stored, _, _ = env
    resp = client.put(
        "/api/agents/intraday_monitor", json={"config": {**VALID, "take_profit": 20}}
    )
    assert resp.status_code == 422, resp.text
    assert "take_profit" in resp.json()["detail"]["message"]
    assert stored() == ORIGINAL


def test_rejected_config_does_not_apply_other_fields_in_same_request(env):
    client, stored, reloads, _ = env
    resp = client.put(
        "/api/agents/intraday_monitor",
        json={"enabled": False, "config": {**VALID, "take_profit_warning": -3}},
    )
    assert resp.status_code == 422
    assert stored(field="enabled") is True
    assert stored() == ORIGINAL
    assert reloads == []


def test_partial_config_with_valid_keys_is_accepted(env):
    client, stored, _, _ = env
    resp = client.put(
        "/api/agents/intraday_monitor", json={"config": {"take_profit_warning": 30}}
    )
    assert resp.status_code == 200, resp.text
    assert stored() == {"take_profit_warning": 30}


def test_other_agents_config_is_not_validated(env):
    client, stored, _, _ = env
    resp = client.put(
        "/api/agents/daily_report", json={"config": {"anything": "goes", "n": -1}}
    )
    assert resp.status_code == 200, resp.text
    assert stored("daily_report") == {"anything": "goes", "n": -1}


@pytest.mark.parametrize(
    "body",
    [
        {"config": VALID},
        {"schedule": "*/10 9-13 * * 1-5"},
        {"enabled": False},
    ],
)
def test_scheduler_reloads_after_runtime_relevant_change(env, body):
    client, _, reloads, _ = env
    resp = client.put("/api/agents/intraday_monitor", json=body)
    assert resp.status_code == 200, resp.text
    assert reloads == [1]


@pytest.mark.parametrize(
    "body",
    [
        {"notify_channel_ids": []},
        {"visible": True},
    ],
)
def test_scheduler_not_reloaded_for_display_only_change(env, body):
    client, _, reloads, _ = env
    resp = client.put("/api/agents/intraday_monitor", json=body)
    assert resp.status_code == 200, resp.text
    assert reloads == []


def test_reload_failure_does_not_fail_the_save(env):
    client, stored, _, fake_server = env

    def boom():
        raise RuntimeError("scheduler down")

    fake_server.reload_scheduler = boom
    resp = client.put("/api/agents/intraday_monitor", json={"config": VALID})
    assert resp.status_code == 200, resp.text
    assert stored() == VALID

