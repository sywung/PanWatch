"""繁体中文(zh-TW)语系:预设语言、报告语言指示、简转繁边界转换。"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.platform import language
from src.platform.persistence.database import Base
from src.platform.persistence.models import AppSettings


def _session(ui_language: str | None = None):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    if ui_language is not None:
        s.add(AppSettings(key="ui_language", value=ui_language))
        s.commit()
    return s


# ---------------------------------------------------------------- 语言解析


def test_supported_languages_include_zh_tw():
    assert language.SUPPORTED_LANGUAGES == frozenset({"zh-TW", "zh-CN", "en-US"})
    assert language.DEFAULT_LANGUAGE == "zh-TW"


def test_default_report_language_is_zh_tw():
    assert language.resolve_report_language(_session()) == "zh-TW"
    assert language.resolve_report_language(_session("xx-YY")) == "zh-TW"


def test_explicit_languages_respected():
    assert language.resolve_report_language(_session("zh-CN")) == "zh-CN"
    assert language.resolve_report_language(_session("en-US")) == "en-US"
    assert language.resolve_report_language(_session("zh-TW")) == "zh-TW"


# ---------------------------------------------------------------- 简转繁


def test_localize_text_converts_to_taiwan_traditional():
    out = language.localize_text("账户持仓数据已保存,默认显示台股", "zh-TW")
    assert out == "帳戶持倉資料已儲存,預設顯示台股"


def test_localize_text_keeps_tai_not_formal_variant():
    out = language.localize_text("台积电 新台币 台股", "zh-TW")
    assert "臺" not in out
    assert out == "台積電 新台幣 台股"


def test_localize_text_uses_taiwan_vocabulary():
    out = language.localize_text("当前持仓，默认渠道，获取失败，分享到社交平台", "zh-TW")
    assert out == "目前持倉，預設渠道，取得失敗，分享到社群平台"


def test_localize_text_keeps_allocation_wording():
    # AI 报告里的「资产配置」是台湾也用的投资用语,不能被当成「设定」改掉
    assert language.localize_text("建议调整资产配置", "zh-TW") == "建議調整資產配置"


def test_localize_text_noop_for_other_languages():
    s = "账户持仓"
    assert language.localize_text(s, "zh-CN") == s
    assert language.localize_text(s, "en-US") == s
    assert language.localize_text("", "zh-TW") == ""
    assert language.localize_text(None, "zh-TW") is None


def test_localize_text_preserves_markdown_urls_and_codes():
    s = "[2330.TW](https://tw.stock.yahoo.com/quote/2330) 收盘 **1,000** 元"
    out = language.localize_text(s, "zh-TW")
    assert "(https://tw.stock.yahoo.com/quote/2330)" in out
    assert "[2330.TW]" in out and "**1,000**" in out
    assert "收盤" in out


# ---------------------------------------------------------------- AI 报告语言


def _agent():
    from src.modules.automation.base import BaseAgent

    class _A(BaseAgent):
        name = "daily_report"
        display_name = "收盘复盘"

        async def collect(self, context):
            return {}

        def build_prompt(self, data, context):
            return "", ""

    return _A()


class _Ctx:
    def __init__(self, lang):
        self.report_language = lang


def test_apply_report_language_zh_tw_adds_traditional_instruction():
    out = _agent().apply_report_language(_Ctx("zh-TW"), "你是分析师。")
    assert out.startswith("你是分析師。")      # 2026-10-02 起提示词本体也转繁体
    assert "繁體中文" in out and "台灣" in out


def test_zh_tw_converts_prompt_examples_models_copy():
    """2026-10-02:intraday_monitor.txt 的 JSON 示例写着「减仓」「RSI超买回落」,
    模型照抄,建议池出现简中。zh-TW 时提示词整份转繁体(JSON key 不动)。"""
    from pathlib import Path

    raw = (Path(__file__).resolve().parents[1] / "prompts" / "intraday_monitor.txt").read_text(encoding="utf-8")
    out = _agent().apply_report_language(_Ctx("zh-TW"), raw)
    assert "减仓" not in out and "RSI超买" not in out
    assert '"action_label":"減倉"' in out
    assert '"action":"reduce"' in out and '"invalidations"' in out


def test_zh_tw_prompt_conversion_keeps_codes_and_numbers():
    out = _agent().apply_report_language(_Ctx("zh-TW"), "台积电(2330)涨幅 3.5%，MACD 金叉")
    assert out.startswith("台積電(2330)漲幅 3.5%，MACD 金叉")


def test_apply_report_language_zh_cn_unchanged():
    assert _agent().apply_report_language(_Ctx("zh-CN"), "你是分析师。") == "你是分析师。"


def test_agent_context_accepts_zh_tw():
    import inspect

    from src.modules.automation import base

    src = inspect.getsource(base)
    assert '{"zh-CN", "en-US"}' not in src  # 不再把 zh-TW 降级为 zh-CN


# ---------------------------------------------------------------- 通知边界


def test_notifier_localizes_for_zh_tw():
    from src.platform.notifications.notifier import NotifierManager

    n = NotifierManager(language="zh-TW")
    assert n.localize("【收盘复盘】账户") == "【收盤復盤】帳戶"


def test_notifier_default_language_does_not_convert():
    from src.platform.notifications.notifier import NotifierManager

    assert NotifierManager().localize("账户") == "账户"
    assert NotifierManager(language="zh-CN").localize("账户") == "账户"


def test_settings_api_accepts_zh_tw():
    import inspect

    from src.modules.administration.api import settings

    src = inspect.getsource(settings)
    assert '{"zh-CN", "en-US"}' not in src
    assert "zh-TW" in src


def test_server_agent_notifier_passes_report_language(monkeypatch):
    """收盘复盘等 Agent 通知走 server._build_notifier,必须带上报告语言才会转繁体。"""
    import server

    monkeypatch.setattr(server, "_get_report_language", lambda: "zh-TW")
    notifier = server._build_notifier([])
    assert notifier.language == "zh-TW"
    assert notifier.localize("账户") == "帳戶"


# ---------------------------------------------------------------- PROMPT_LANGUAGE 变数


def test_prompt_language_original_keeps_template(monkeypatch):
    """PROMPT_LANGUAGE=original:提示词维持原档(简体),但输出语言指示照介面语言附加。"""
    monkeypatch.setenv("PROMPT_LANGUAGE", "original")
    out = _agent().apply_report_language(_Ctx("zh-TW"), "你是分析师。")
    assert out.startswith("你是分析师。")
    assert "繁體中文" in out


def test_prompt_language_zh_tw_forces_conversion_even_for_zh_cn(monkeypatch):
    monkeypatch.setenv("PROMPT_LANGUAGE", "zh-TW")
    out = _agent().apply_report_language(_Ctx("zh-CN"), "你是分析师。")
    assert out == "你是分析師。"


def test_prompt_language_auto_is_default(monkeypatch):
    monkeypatch.delenv("PROMPT_LANGUAGE", raising=False)
    from src.platform.language import prompt_language_mode

    assert prompt_language_mode() == "auto"
    assert _agent().apply_report_language(_Ctx("zh-CN"), "你是分析师。") == "你是分析师。"


def test_prompt_language_invalid_value_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("PROMPT_LANGUAGE", "klingon")
    from src.platform.language import prompt_language_mode

    assert prompt_language_mode() == "auto"
