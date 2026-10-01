"""资金流向摘要文本格式化。"""


def _signed(value) -> str:
    try:
        return f"{float(value):+,.0f}"
    except (TypeError, ValueError):
        return "—"


def format_capital_flow_line(flow: dict, language: str) -> str:
    """将资金流摘要格式化为 Agent 可直接插入的一行文字。"""
    if not isinstance(flow, dict) or flow.get("error"):
        return ""
    if flow.get("type") == "three_institutions":
        try:
            net = f"{float(flow.get('institutional_net')):,.0f}"
        except (TypeError, ValueError):
            net = "—"
        prefix = {
            "en-US": "Institutional net buy" if (flow.get("institutional_net") or 0) >= 0 else "Institutional net sell",
        }.get(language, flow.get("status") or "三大法人买卖超")
        if language == "en-US":
            return f"{prefix} {net} {flow.get('unit') or 'shares'} (Foreign {_signed(flow.get('foreign_net'))}, Trust {_signed(flow.get('trust_net'))}, Dealers {_signed(flow.get('dealer_net'))})"
        return f"{prefix} {net} {flow.get('unit') or '股'}（外資 {_signed(flow.get('foreign_net'))}、投信 {_signed(flow.get('trust_net'))}、自營 {_signed(flow.get('dealer_net'))}）"

    inflow = flow.get("main_net_inflow")
    if inflow is None:
        return ""
    try:
        amount = float(inflow)
        pct = float(flow.get("main_net_inflow_pct") or 0)
    except (TypeError, ValueError):
        return ""
    amount_text = f"{amount / 1e8:+.2f}亿" if abs(amount) >= 1e8 else f"{amount / 1e4:+.0f}万"
    return f"{flow.get('status') or '主力资金'}，主力净流入{amount_text}（{pct:+.1f}%）"
