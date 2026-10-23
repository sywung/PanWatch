"""台股／台指期专属证据:缠论、期货脉络、三大法人、集保分散与市场规则。

研究图按 domain 分派证据给各角色,这些内容要放进对应 domain 才看得到。
文字沿用介面语言格式化(研究图本身以简体/英文产出,繁中在呈现时转换)。
"""
from __future__ import annotations

import logging

from src.modules.market.capital_flow_text import format_capital_flow_line
from src.modules.market.chan_analysis import format_chan_summary
from src.platform.marketdata.futures_context import futures_prompt_note

logger = logging.getLogger(__name__)

CHAN_NOTE = "缠论结构(笔、线段、中枢、买卖点、区间套)仅作参考,需与其他指标综合判断。"
CHAN_NOTE_EN = ("Chan-theory structure (strokes, segments, pivots, buy/sell points, nesting) "
                "is a reference only and must be weighed with other indicators.")
TW_STOCK_RULES = "台股说明:资金面使用三大法人买卖超(单位:股),融资融券单位为张,涨跌幅限制±10%,可当冲。"
TW_STOCK_RULES_EN = ("Taiwan stocks: capital flow is the three major institutional investors' net "
                     "buy/sell in shares; margin balances are in lots (1,000 shares); daily price "
                     "limit is ±10%; day trading is allowed.")


def read_dispersion_line(symbol: str, market: str, language: str) -> str:
    """只读本机集保快照;绝不触发来源抓取。"""
    if market != "TW":
        return ""
    from src.modules.market.shareholder_dispersion import dispersion_line_for
    from src.platform.persistence.database import SessionLocal

    with SessionLocal() as db:
        return dispersion_line_for(db, symbol, market, language)


def technical_extras(market: str, symbol: str, pack, data: dict, language: str) -> dict:
    extras: dict = {}
    chan_text = format_chan_summary((getattr(pack, "technical", None) or {}).get("chan"), language)
    if chan_text:
        extras["chan_summary"] = chan_text
        extras["chan_note"] = CHAN_NOTE_EN if language == "en-US" else CHAN_NOTE
    if market == "TWF":
        futures_ctx = (data.get("futures_contexts") or {}).get(symbol) or data.get("futures_context")
        if futures_ctx:
            extras["futures_context"] = futures_ctx
    return extras


def flow_extras(market: str, symbol: str, pack, language: str, dispersion_line: str) -> dict:
    extras: dict = {}
    if market != "TW":
        return extras
    flow_text = format_capital_flow_line(getattr(pack, "capital_flow", None), language)
    if flow_text:
        extras["capital_flow_summary"] = flow_text
    if dispersion_line:
        extras["shareholder_dispersion"] = dispersion_line
    return extras


def market_rules(market: str, language: str) -> str:
    if market == "TW":
        return TW_STOCK_RULES_EN if language == "en-US" else TW_STOCK_RULES
    if market == "TWF":
        return futures_prompt_note([{"market": "TWF"}], language).strip()
    return ""


async def dispersion_line(market: str, symbol: str, language: str) -> str:
    """集保摘要读取失败只记日志,不影响研究流程。"""
    if market != "TW":
        return ""
    import asyncio

    try:
        return await asyncio.to_thread(read_dispersion_line, symbol, market, language) or ""
    except Exception as exc:
        logger.warning("读取集保摘要失败 %s: %s", symbol, exc)
        return ""
