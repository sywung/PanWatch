"""资金流向采集器 - 经 marketdata 包统一接入"""
from dataclasses import dataclass

from src.platform.marketdata.collectors.market_http import TTLCache
from src.platform.marketdata.models import MarketCode

# 资金流为日级数据、变动慢:中等 TTL 缓存,避免每轮重复拉。
_FLOW_CACHE = TTLCache(default_ttl_sec=600.0)


@dataclass
class CapitalFlow:
    """资金流向数据"""
    symbol: str
    name: str

    # 今日资金流（单位：元）
    main_net_inflow: float | None = None      # 主力净流入
    main_net_inflow_pct: float | None = None  # 主力净流入占比
    super_net_inflow: float | None = None     # 超大单净流入
    big_net_inflow: float | None = None       # 大单净流入
    mid_net_inflow: float | None = None       # 中单净流入
    small_net_inflow: float | None = None     # 小单净流入

    # 5日资金流
    main_net_5d: float | None = None  # 5日主力净流入
    foreign_net: float | None = None
    trust_net: float | None = None
    dealer_net: float | None = None
    institutional_net: float | None = None
    unit: str = ""
    trade_date: str = ""


def get_market_data():
    """惰性导入,避免模块加载时的循环依赖(便于测试 monkeypatch)。"""
    from src.platform.marketdata.marketdata_client import get_market_data as _g
    return _g()


class CapitalFlowCollector:
    """资金流向采集器"""

    def __init__(self, market: MarketCode):
        self.market = market

    def get_capital_flow(self, symbol: str) -> CapitalFlow | None:
        """获取单只股票的资金流向(经 marketdata 包统一接入 + TTL缓存)。"""
        cache_key = f"{self.market.value}:{symbol}"
        cached = _FLOW_CACHE.get(cache_key)
        if cached is not None:
            return cached

        md_cf = get_market_data().capital_flow(symbol, market=self.market.value)
        if md_cf is None:
            return None
        capital_flow = CapitalFlow(
            symbol=md_cf.symbol,
            name=md_cf.name,
            main_net_inflow=md_cf.main_net_inflow,
            main_net_inflow_pct=md_cf.main_net_inflow_pct,
            super_net_inflow=md_cf.super_net_inflow,
            big_net_inflow=md_cf.big_net_inflow,
            mid_net_inflow=md_cf.mid_net_inflow,
            small_net_inflow=md_cf.small_net_inflow,
            main_net_5d=md_cf.main_net_5d,
            foreign_net=md_cf.foreign_net,
            trust_net=md_cf.trust_net,
            dealer_net=md_cf.dealer_net,
            institutional_net=md_cf.institutional_net,
            unit=md_cf.unit,
            trade_date=md_cf.trade_date,
        )
        _FLOW_CACHE.set(cache_key, capital_flow)
        return capital_flow

    def get_capital_flow_summary(self, symbol: str) -> dict:
        """获取资金流向摘要（用于 prompt）"""
        flow = self.get_capital_flow(symbol)

        if not flow:
            return {"error": "无资金流向数据"}

        if not flow:
            return {"error": "无资金流向数据"}

        if flow.institutional_net is not None:
            net = flow.institutional_net
            status = "三大法人买超" if net > 0 else "三大法人卖超" if net < 0 else "三大法人持平"
            return {
                "type": "three_institutions",
                "foreign_net": flow.foreign_net,
                "trust_net": flow.trust_net,
                "dealer_net": flow.dealer_net,
                "institutional_net": net,
                "unit": flow.unit,
                "trade_date": flow.trade_date,
                "status": status,
            }

        # 判断资金状态；字段可能为空，缺失时返回可用的空摘要。
        if flow.main_net_inflow is None:
            return {
                "type": "main_force",
                "status": "主力资金数据缺失",
                "main_net_inflow": None,
                "main_net_inflow_pct": None,
                "super_net_inflow": flow.super_net_inflow,
                "big_net_inflow": flow.big_net_inflow,
                "mid_net_inflow": flow.mid_net_inflow,
                "small_net_inflow": flow.small_net_inflow,
                "trend_5d": "无数据",
            }
        pct = flow.main_net_inflow_pct or 0
        if flow.main_net_inflow > 0:
            if pct > 10:
                status = "主力大幅流入"
            elif pct > 5:
                status = "主力明显流入"
            else:
                status = "主力小幅流入"
        elif flow.main_net_inflow < 0:
            if pct < -10:
                status = "主力大幅流出"
            elif pct < -5:
                status = "主力明显流出"
            else:
                status = "主力小幅流出"
        else:
            status = "主力资金平衡"

        # 5日趋势
        trend_5d = "无数据"
        if flow.main_net_5d is not None:
            if flow.main_net_5d > 0:
                trend_5d = f"5日净流入{flow.main_net_5d/1e8:.2f}亿"
            else:
                trend_5d = f"5日净流出{abs(flow.main_net_5d)/1e8:.2f}亿"

        return {
            "type": "main_force",
            "status": status,
            "main_net_inflow": flow.main_net_inflow,
            "main_net_inflow_pct": flow.main_net_inflow_pct,
            "super_net_inflow": flow.super_net_inflow,
            "big_net_inflow": flow.big_net_inflow,
            "mid_net_inflow": flow.mid_net_inflow,
            "small_net_inflow": flow.small_net_inflow,
            "trend_5d": trend_5d,
        }
