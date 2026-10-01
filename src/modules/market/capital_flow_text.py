"""资金流向摘要文本格式化(日报 / 盘前 / 盘中三个 Agent 共用)。

两种资金面口径:
- A 股:主力资金净流入(金额,元)
- 台股:三大法人买卖超(股数),外资 / 投信 / 自营商分列

中文先以简体组字(与既有代码一致),zh-TW 再整句转为台湾繁体用语。
"""

from __future__ import annotations

from src.platform.language import localize_text


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _signed(value) -> str:
    n = _num(value)
    return "—" if n is None else f"{n:+,.0f}"


def _three_institutions_line(flow: dict, language: str) -> str:
    net = _num(flow.get("institutional_net"))
    amount = "—" if net is None else f"{abs(net):,.0f}"
    foreign = _signed(flow.get("foreign_net"))
    trust = _signed(flow.get("trust_net"))
    dealer = _signed(flow.get("dealer_net"))

    if language == "en-US":
        if net is None or net == 0:
            head = "Institutional investors flat"
        else:
            head = "Institutional net buy" if net > 0 else "Institutional net sell"
        return f"{head} {amount} shares (Foreign {foreign}, Trust {trust}, Dealers {dealer})"

    if net is None or net == 0:
        head = "三大法人持平"
    else:
        head = "三大法人买超" if net > 0 else "三大法人卖超"
    text = f"{head} {amount} 股（外资 {foreign}、投信 {trust}、自营 {dealer}）"
    return localize_text(text, language) or text


def _main_force_line(flow: dict, language: str) -> str:
    amount = _num(flow.get("main_net_inflow"))
    if amount is None:
        return ""
    pct = _num(flow.get("main_net_inflow_pct")) or 0.0
    amount_text = f"{amount / 1e8:+.2f}亿" if abs(amount) >= 1e8 else f"{amount / 1e4:+.0f}万"
    text = f"{flow.get('status') or '主力资金'}，主力净流入{amount_text}（{pct:+.1f}%）"
    return localize_text(text, language) or text


def format_capital_flow_line(flow: dict, language: str) -> str:
    """将资金流摘要格式化为一行文字;无数据或有 error 时返回空字符串。"""
    if not isinstance(flow, dict) or flow.get("error"):
        return ""
    if flow.get("type") == "three_institutions":
        return _three_institutions_line(flow, language)
    return _main_force_line(flow, language)
