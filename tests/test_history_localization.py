"""分析纪录读出时依介面语言转繁中(资料库原样保留)。

旧版与研究图都把简体存进 analysis_history(标题、内文、research_report、建议),
繁中介面读出时必须一律转换;简中介面原样回传。
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.modules.automation.api.agents import get_tradingagents_latest
from src.modules.portfolio.api.dashboard import get_brief
from src.modules.portfolio.api.history import get_history_detail, list_history
from src.platform.persistence.database import Base
from src.platform.persistence.models import AnalysisHistory, AppSettings


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed(db, language):
    now = datetime.now(timezone.utc)
    if language:
        db.add(AppSettings(key="ui_language", value=language))
    legacy = AnalysisHistory(agent_name="premarket_outlook", stock_symbol="*", analysis_date="2026-10-20",
        title="【盘前分析】无股票", content="## 1. 隔夜影响\n美股科技股情绪回暖", raw_data={},
        created_at=now, updated_at=now)
    graph = AnalysisHistory(agent_name="daily_report", stock_symbol="*", analysis_date="2026-10-27",
        title="【收盘复盘】台积电", content="## 投研结论\n维持观望",
        raw_data={"engine": "langgraph", "research_report": {
            "version": 3, "content": "## 投研结论\n维持观望", "action_summary": "建议减持",
            "sections": [{"title": "风险", "items": ["汇率波动"]}]},
            "suggestions": {"TW:2330": {"action_label": "减持", "reason": "资金流出"}}},
        created_at=now, updated_at=now)
    deep = AnalysisHistory(agent_name="tradingagents", stock_symbol="2330", analysis_date="2026-10-07",
        title="【深度】台积电(2330):卖出", content="**卖出** (评级:卖出)",
        raw_data={"suggestion": {"action_label": "卖出"}}, created_at=now, updated_at=now)
    db.add_all([legacy, graph, deep]); db.commit()
    return legacy, graph, deep


def test_zh_tw_history_list_and_detail_are_traditional(db):
    legacy, graph, _ = _seed(db, "zh-TW")
    listing = {item.id: item for item in list_history(kind="all", limit=30, db=db)}

    assert listing[legacy.id].title == "【盤前分析】無股票"
    assert "情緒回暖" in listing[legacy.id].content
    item = listing[graph.id]
    assert item.title == "【收盤復盤】台積電"
    assert "投研結論" in item.content and "維持觀望" in item.content
    assert item.research_report["action_summary"] == "建議減持"
    assert item.research_report["sections"][0]["items"] == ["匯率波動"]
    assert item.suggestions["TW:2330"]["reason"] == "資金流出"
    assert "TW:2330" in item.suggestions, "只转换值,键(股票代码)不能变"

    detail = get_history_detail(graph.id, db)
    assert detail.title == item.title and detail.content == item.content
    assert detail.research_report == item.research_report


def test_zh_tw_dashboard_brief_and_deep_analysis_are_traditional(db):
    _seed(db, "zh-TW")
    brief = get_brief(type="premarket", db=db)
    assert brief["title"] == "【盤前分析】無股票" and brief["agent_label"] == "盤前分析"
    assert "情緒" in brief["content"]

    deep = get_tradingagents_latest(stock_symbol="2330", db=db)
    assert deep["title"] == "【深度】台積電(2330):賣出"
    assert "賣出" in deep["content"] and deep["raw_data"]["suggestion"]["action_label"] == "賣出"


def test_zh_cn_history_is_returned_unchanged(db):
    legacy, graph, _ = _seed(db, "zh-CN")
    listing = {item.id: item for item in list_history(kind="all", limit=30, db=db)}
    assert listing[legacy.id].title == "【盘前分析】无股票"
    assert listing[graph.id].research_report["action_summary"] == "建议减持"


def test_reading_never_rewrites_stored_history(db):
    legacy, graph, _ = _seed(db, "zh-TW")
    list_history(kind="all", limit=30, db=db)
    get_history_detail(graph.id, db)
    db.expire_all()
    assert db.get(AnalysisHistory, legacy.id).title == "【盘前分析】无股票"
    assert db.get(AnalysisHistory, graph.id).raw_data["research_report"]["action_summary"] == "建议减持"
