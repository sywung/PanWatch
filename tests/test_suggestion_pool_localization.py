"""建议池文字依介面语言转繁体。

2026-10-02 使用者回报:详情页「近期补充建议」出现简中(「减仓 · RSI超买+突破上轨+浮盈达标」)。
盘中监测的 AI 有时回简体、有时回繁体,save_suggestion 原样落库;读出时也没转换。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.platform.persistence.models  # noqa: F401
from src.modules.automation import suggestion_pool as sp
from src.platform.persistence.database import Base
from src.platform.persistence.models import AppSettings, StockSuggestion


@pytest.fixture
def db_factory(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(sp, "SessionLocal", factory)
    yield factory
    engine.dispose()


def _set_language(factory, language):
    with factory() as db:
        db.add(AppSettings(key="ui_language", value=language))
        db.commit()


def _save(**kw):
    payload = dict(stock_symbol="00403A", stock_name="主動統一升級50", action="reduce",
                   action_label="减仓", agent_name="intraday_monitor",
                   signal="RSI超买+突破上轨+浮盈达标", reason="止盈减仓", stock_market="TW")
    payload.update(kw)
    assert sp.save_suggestion(**payload)


def _stored(factory):
    with factory() as db:
        row = db.query(StockSuggestion).order_by(StockSuggestion.id.desc()).first()
        return row.action_label, row.signal, row.reason


def test_save_converts_to_traditional_when_ui_is_zh_tw(db_factory):
    _set_language(db_factory, "zh-TW")
    _save()
    label, signal, reason = _stored(db_factory)
    assert label == "減倉"
    assert signal == "RSI超買+突破上軌+浮盈達標"
    assert reason == "止盈減倉"


def test_save_keeps_simplified_when_ui_is_zh_cn(db_factory):
    _set_language(db_factory, "zh-CN")
    _save()
    assert _stored(db_factory)[0] == "减仓"


def test_dedupe_matches_across_scripts(db_factory):
    """先存简体、再存同义繁体:应视为同一条建议(去重),不新增一列。"""
    _set_language(db_factory, "zh-TW")
    _save()
    _save(action_label="減倉", signal="RSI超買+突破上軌+浮盈達標")
    with db_factory() as db:
        assert db.query(StockSuggestion).count() == 1


def test_read_localizes_legacy_simplified_rows(db_factory):
    """已落库的简体旧资料,读出时依介面语言转繁体(不改资料库)。"""
    with db_factory() as db:
        db.add(StockSuggestion(stock_symbol="3661", stock_market="TW", stock_name="世芯-KY",
                               action="reduce", action_label="减仓", signal="浮盈达标且法人卖超",
                               reason="", agent_name="intraday_monitor", agent_label="盘中监测"))
        db.commit()
    _set_language(db_factory, "zh-TW")

    rows = sp.get_suggestions_for_stock("3661", stock_market="TW", include_expired=True)
    assert rows[0]["action_label"] == "減倉"
    assert rows[0]["signal"] == "浮盈達標且法人賣超"
    assert rows[0]["agent_label"] == "盤中監測"

    latest = sp.get_latest_suggestions(include_expired=True)
    assert latest and next(iter(latest.values()))["signal"] == "浮盈達標且法人賣超"

    with db_factory() as db:
        assert db.query(StockSuggestion).first().signal == "浮盈达标且法人卖超"


def test_read_unchanged_for_zh_cn(db_factory):
    with db_factory() as db:
        db.add(StockSuggestion(stock_symbol="3661", stock_market="TW", stock_name="世芯-KY",
                               action="reduce", action_label="减仓", signal="浮盈达标",
                               agent_name="intraday_monitor"))
        db.commit()
    _set_language(db_factory, "zh-CN")
    rows = sp.get_suggestions_for_stock("3661", stock_market="TW", include_expired=True)
    assert rows[0]["action_label"] == "减仓"


def test_identical_suggestion_is_deduped_on_sqlite(db_factory):
    """SQLite 读回的 expires_at 不带时区;与带时区的新值比较曾抛 TypeError 被吞掉,
    导致去重从未生效、盘中监测每 5 分钟新增一列几乎相同的建议。"""
    _set_language(db_factory, "zh-CN")
    _save(signal="abc")
    _save(signal="abc")
    with db_factory() as db:
        assert db.query(StockSuggestion).count() == 1


def test_less_severe_action_within_window_keeps_previous(db_factory):
    """稳定性规则:窗口内降级(减仓→持有)不新增,保留较严重的那条。"""
    _set_language(db_factory, "zh-CN")
    _save(action="reduce", action_label="减仓", signal="a")
    _save(action="hold", action_label="持有", signal="b")
    with db_factory() as db:
        rows = db.query(StockSuggestion).all()
        assert [r.action for r in rows] == ["reduce"]
