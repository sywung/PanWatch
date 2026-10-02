"""台股(含上柜/兴柜/ETF 代码)在 TradingAgents 的数据通路。

2026-10-02 生产日志:用户跑 00685L、00403A(台股 ETF)深度分析,
get_stock_data / get_news / get_fundamentals 全以原始代码「00685L」PASSTHROUGH 到 yfinance,
拿到 NO_DATA_AVAILABLE 或 30 秒逾时;只有 K 线靠 load_ohlcv 兜底。原因:
- is_tw_share 只认 4 位数字;006208(6 位)会被当 A 股、00878(5 位)当港股、00679B 当美股
- 路由没有台股分支,台股 ticker 原样交给 yfinance(要 .TW / .TWO 后缀)

策略:
1. 本次分析的标的(symbol 与 cache 里的 stock 相同)以 stock.market 为准,不靠位数猜
2. 本次分析的台股标的:走 PanWatch(collect() 已按市场收集行情/K线/重大讯息/法人资金流)
3. PanWatch 未实现的 method、或工具查询其他台股:转 yfinance 格式(上市 .TW、上柜/兴柜 .TWO)
"""

from __future__ import annotations

import pytest

from src.modules.automation.tradingagents import toolkit_adapter as ta
from src.modules.automation.tradingagents.toolkit_adapter import (
    is_panwatch_routable,
    is_tw_share,
    panwatch_data_context,
    tw_symbol_to_yfinance,
)
from src.platform.marketdata import stock_list as sl
from src.platform.marketdata.models import MarketCode


def _stock(symbol, name, market="TW"):
    return type("S", (), {"symbol": symbol, "name": name, "market": MarketCode(market)})()


KLINES = [
    {"date": "2026-09-30", "open": 12.1, "high": 12.4, "low": 12.0, "close": 12.3, "volume": 1000},
    {"date": "2026-10-01", "open": 12.3, "high": 12.5, "low": 12.2, "close": 12.4, "volume": 1200},
]


def _ctx(symbol, name, market="TW"):
    return panwatch_data_context({
        "stock": _stock(symbol, name, market),
        "quote": {"current_price": 12.4},
        "klines": KLINES,
        "events": [],
    })


@pytest.fixture
def upstream(monkeypatch):
    """记录交给上游 vendor 的参数;回一段像样的数据。"""
    calls = []

    def fake(method_name, *args, **kwargs):
        calls.append((method_name, args))
        return "Date,Open,High,Low,Close,Volume\n" + "\n".join(
            f"2026-09-{d:02d},1,1,1,1,1" for d in range(1, 20)
        )

    monkeypatch.setattr(ta, "_real_route_to_vendor", fake)
    return calls


@pytest.fixture
def tw_boards(monkeypatch):
    monkeypatch.setattr(sl, "get_stock_list", lambda *a, **k: [
        {"symbol": "2330", "name": "台積電", "market": "TW", "board": "TSE"},
        {"symbol": "6488", "name": "環球晶", "market": "TW", "board": "OTC"},
        {"symbol": "7795", "name": "長廣", "market": "TW", "board": "ESB"},
        {"symbol": "00679B", "name": "元大美債20年", "market": "TW", "board": "OTC"},
    ])


# ============================================================
# 1. 当前标的以 stock.market 为准
# ============================================================

@pytest.mark.parametrize("symbol", ["006208", "00878", "00679B", "00685L", "6488", "2330"])
def test_current_tw_stock_is_routable_regardless_of_digits(symbol):
    """当前分析的台股标的,不论 4/5/6 位或字母结尾,都由 PanWatch 处理。"""
    with _ctx(symbol, "測試"):
        assert is_panwatch_routable(symbol) is True
        assert ta._market_for_symbol(symbol) == MarketCode.TW


def test_six_digit_tw_etf_is_not_treated_as_a_share(upstream):
    """006208 是台股 ETF:不得套用 A 股专属逻辑(快照不符就拒绝/东财财报)。"""
    with _ctx("006208", "富邦台50"):
        out = ta._patched_route_to_vendor("get_stock_data", "006208", "2026-09-01", "2026-10-02")
    assert "12.4" in out           # 来自 PanWatch K 线
    assert upstream == []          # 没去上游


def test_letter_suffix_tw_code_recognized_without_context():
    """00679B / 00685L 这类台股债券/杠杆 ETF 代码,没有 context 也认得是台股。"""
    assert is_tw_share("00679B") is True
    assert is_tw_share("00685L") is True
    assert is_tw_share("AAPL") is False
    assert is_tw_share("BRK.B") is False


# ============================================================
# 2. 当前台股标的走 PanWatch
# ============================================================

@pytest.mark.parametrize("method,args", [
    ("get_stock_data", ("00685L", "2025-10-01", "2026-10-01")),
    ("get_news", ("00685L", "2026-10-01", "2026-10-02")),
    ("get_fundamentals", ("00685L", "2026-10-02")),
])
def test_current_tw_stock_served_from_panwatch(upstream, method, args):
    """生产日志里 PASSTHROUGH 失败的三个 method,改由 PanWatch 回应、不打上游。"""
    with _ctx("00685L", "群益臺灣加權正2"):
        out = ta._patched_route_to_vendor(method, *args)
    assert "00685L" in out
    assert upstream == []


def test_unimplemented_method_goes_upstream_with_tw_suffix(upstream, tw_boards):
    """PanWatch 没实现的 method:上游要拿 yfinance 格式代码(上市 .TW)。"""
    with _ctx("2330", "台積電"):
        ta._patched_route_to_vendor("get_some_new_tool", "2330", "2026-10-02")
    assert upstream and upstream[0][1][0] == "2330.TW"


def test_unimplemented_method_for_otc_uses_two_suffix(upstream, tw_boards):
    """上柜股票(环球晶 6488)上游用 .TWO。"""
    with _ctx("6488", "環球晶"):
        ta._patched_route_to_vendor("get_some_new_tool", "6488", "2026-10-02")
    assert upstream and upstream[0][1][0] == "6488.TWO"


# ============================================================
# 3. 工具查询其他台股(同业比较等)
# ============================================================

def test_other_tw_symbol_goes_upstream_with_suffix(upstream, tw_boards):
    """分析 2330 时工具查 6488:不能拿 2330 快照冒充,改问上游且带 .TWO。"""
    with _ctx("2330", "台積電"):
        ta._patched_route_to_vendor("get_stock_data", "6488", "2026-09-01", "2026-10-02")
    assert upstream and upstream[0][1][0] == "6488.TWO"


def test_other_tw_symbol_unknown_board_defaults_to_tw(upstream, tw_boards):
    """清单里查不到板别:默认 .TW。"""
    with _ctx("2330", "台積電"):
        ta._patched_route_to_vendor("get_stock_data", "1234", "2026-09-01", "2026-10-02")
    assert upstream[0][1][0] == "1234.TW"


# ============================================================
# 4. 代码格式转换
# ============================================================

def test_tw_symbol_to_yfinance_by_board():
    assert tw_symbol_to_yfinance("2330") == "2330.TW"
    assert tw_symbol_to_yfinance("2330", board="TSE") == "2330.TW"
    assert tw_symbol_to_yfinance("6488", board="OTC") == "6488.TWO"
    assert tw_symbol_to_yfinance("7795", board="ESB") == "7795.TWO"
    assert tw_symbol_to_yfinance("00679B", board="OTC") == "00679B.TWO"
    assert tw_symbol_to_yfinance("AAPL") == "AAPL"


# ============================================================
# 5. 其他市场不受影响
# ============================================================

def test_a_share_still_rejects_mismatched_snapshot(upstream):
    """A 股既有边界:分析 600519 时请求 000001 → 回数据不可用,不打上游、不冒充。"""
    with _ctx("600519", "贵州茅台", market="CN"):
        out = ta._patched_route_to_vendor("get_stock_data", "000001", "2026-09-01", "2026-10-02")
    assert upstream == []
    assert "600519" in out or "000001" in out


def test_us_stock_still_passthrough(upstream):
    with _ctx("AAPL", "Apple", market="US"):
        ta._patched_route_to_vendor("get_stock_data", "AAPL", "2026-09-01", "2026-10-02")
    assert upstream and upstream[0][1][0] == "AAPL"
