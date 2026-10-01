"""每个 AI 模型可设定额外请求参数(extra_params),以 OpenAI SDK 的 extra_body 送出。

动机(2026-10-01 实测 oMLX 本机模型):Qwen3.x 会把思考过程直接写进 content(没有独立的
reasoning 栏位),400 token 用完仍未作答;请求带 `chat_template_kwargs: {"enable_thinking": false}`
后 36 token 干净作答。`/no_think` 无效。PanWatch 原本无法对单一模型附加参数。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.platform.ai.ai_client import AIClient

NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}


# ---------------------------------------------------------------- AIClient


class _Recorder:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        msg = SimpleNamespace(content="OK", tool_calls=None, role="assistant")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")], usage=usage, model="m")


def _client(extra=None):
    client = AIClient(base_url="http://localhost:9/v1", api_key="k", model="m", extra_body=extra)
    rec = _Recorder()
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=rec))
    return client, rec


def test_chat_sends_extra_body():
    client, rec = _client(NO_THINK)
    asyncio.run(client.chat(system_prompt="s", user_content="u"))
    assert rec.calls[0]["extra_body"] == NO_THINK


def test_chat_multi_and_tools_send_extra_body():
    client, rec = _client(NO_THINK)
    asyncio.run(client.chat_multi(messages=[{"role": "user", "content": "u"}]))
    asyncio.run(client.chat_with_tools(messages=[{"role": "user", "content": "u"}], tools=[]))
    assert all(c["extra_body"] == NO_THINK for c in rec.calls)


def test_no_extra_body_when_not_configured():
    # 其他服务商(Azure 等)完全不受影响:不能多送空的 extra_body
    for extra in (None, {}):
        client, rec = _client(extra)
        asyncio.run(client.chat(system_prompt="s", user_content="u"))
        assert "extra_body" not in rec.calls[0]


def test_extra_body_is_copied_not_shared():
    params = {"chat_template_kwargs": {"enable_thinking": False}}
    client, rec = _client(params)
    params["chat_template_kwargs"]["enable_thinking"] = True
    asyncio.run(client.chat(system_prompt="s", user_content="u"))
    assert rec.calls[0]["extra_body"] == NO_THINK


# ---------------------------------------------------------------- 数据库栏位与迁移


@pytest.fixture
def db():
    import src.platform.persistence.models  # noqa: F401
    from src.platform.persistence.database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_model_extra_params_defaults_to_empty_dict(db):
    from src.platform.persistence.models import AIModel, AIService

    svc = AIService(name="oMLX", base_url="http://host.containers.internal:9999/v1", api_key="k")
    db.add(svc)
    db.commit()
    m = AIModel(name="gemma", service_id=svc.id, model="gemma-4")
    db.add(m)
    db.commit()
    db.refresh(m)
    assert m.extra_params == {}


def test_migration_adds_column_to_existing_database():
    from src.platform.persistence import migrations as mig

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE ai_models (id INTEGER PRIMARY KEY, name TEXT, service_id INTEGER, model TEXT, is_default BOOLEAN)"
        ))
        conn.execute(text("INSERT INTO ai_models (name, service_id, model, is_default) VALUES ('x', 1, 'x', 0)"))
    step = next(m for m in mig.MIGRATIONS if m.name == "ai_model_extra_params")
    assert step.version >= 9000          # 分支专属迁移用 9000+,避免与上游流水号撞号
    with engine.begin() as conn:
        step.runner(conn)
        step.runner(conn)                 # 可重复执行
    cols = {c["name"] for c in inspect(engine).get_columns("ai_models")}
    assert "extra_params" in cols
    with engine.begin() as conn:
        assert conn.execute(text("SELECT extra_params FROM ai_models")).scalar() == "{}"


# ---------------------------------------------------------------- 模型 API


def _service(db):
    from src.platform.persistence.models import AIService

    svc = AIService(name="oMLX", base_url="http://host.containers.internal:9999/v1", api_key="k")
    db.add(svc)
    db.commit()
    return svc


def test_create_and_update_model_with_extra_params(db):
    from src.modules.administration.api import providers as api

    svc = _service(db)
    created = api.create_model(api.ModelCreate(service_id=svc.id, model="Qwen3.6", extra_params=NO_THINK), db)
    assert created.extra_params == NO_THINK
    updated = api.update_model(created.id, api.ModelUpdate(extra_params={}), db)
    assert updated.extra_params == {}
    untouched = api.update_model(created.id, api.ModelUpdate(name="Qwen"), db)
    assert untouched.extra_params == {}          # 没传 extra_params 时不覆盖


@pytest.mark.parametrize("bad", [["x"], "enable_thinking", 1])
def test_extra_params_must_be_an_object(bad):
    from pydantic import ValidationError

    from src.modules.administration.api import providers as api

    with pytest.raises(ValidationError):
        api.ModelCreate(service_id=1, model="m", extra_params=bad)


@pytest.mark.parametrize("reserved", ["model", "messages", "stream", "tools"])
def test_extra_params_cannot_override_core_fields(reserved):
    # extra_body 会并进请求 JSON,若允许 model/messages 会悄悄改掉真正的请求
    from pydantic import ValidationError

    from src.modules.administration.api import providers as api

    with pytest.raises(ValidationError):
        api.ModelCreate(service_id=1, model="m", extra_params={reserved: "x"})


def test_model_test_endpoint_uses_extra_params(db, monkeypatch):
    from src.modules.administration.api import providers as api

    svc = _service(db)
    created = api.create_model(api.ModelCreate(service_id=svc.id, model="Qwen3.6", extra_params=NO_THINK), db)
    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        async def chat(self, **kwargs):
            return "OK"

    monkeypatch.setattr(api, "AIClient", FakeClient)
    asyncio.run(api.test_model(created.id, db))
    assert seen["extra_body"] == NO_THINK


# ---------------------------------------------------------------- failover 链


def test_failover_chain_carries_each_models_extra_params(monkeypatch):
    from src.platform.ai import ai_failover as fo

    made = []

    def fake_make_client(base_url, api_key, model, proxy, extra_body=None):
        made.append((model, extra_body))
        return SimpleNamespace(model=model)

    monkeypatch.setattr(fo, "_make_client", fake_make_client)
    primary_svc = SimpleNamespace(id=1, name="oMLX", base_url="u", api_key="k")
    primary = SimpleNamespace(id=1, name="qwen", model="Qwen3.6", service_id=1, extra_params=NO_THINK)
    fo.build_failover_client(primary, primary_svc, max_fallbacks=0)
    assert made[0] == ("Qwen3.6", NO_THINK)


def test_failover_fallback_models_carry_their_own_extra_params(db, monkeypatch):
    # 主模型(Azure)失败时切到本机 Qwen,备援请求也必须带 Qwen 自己的参数,主模型的不能串过去
    from src.platform.ai import ai_failover as fo
    from src.platform.persistence.models import AIModel, AIService

    azure = AIService(name="Azure", base_url="https://azure/v1", api_key="a")
    omlx = AIService(name="oMLX", base_url="http://host.containers.internal:9999/v1", api_key="k")
    db.add_all([azure, omlx])
    db.commit()
    gpt = AIModel(name="gpt", service_id=azure.id, model="gpt-6", is_default=True)
    qwen = AIModel(name="qwen", service_id=omlx.id, model="Qwen3.6", extra_params=NO_THINK)
    gemma = AIModel(name="gemma", service_id=omlx.id, model="gemma-4")
    db.add_all([gpt, qwen, gemma])
    db.commit()

    made = []

    def fake_make_client(base_url, api_key, model, proxy, extra_body=None):
        made.append((model, extra_body))
        return SimpleNamespace(model=model)

    monkeypatch.setattr(fo, "_make_client", fake_make_client)
    fo.build_failover_client(gpt, azure, db=db, max_fallbacks=2)
    by_model = dict(made)
    assert by_model["gpt-6"] in (None, {})
    assert by_model["Qwen3.6"] == NO_THINK
    assert by_model["gemma-4"] in (None, {})
