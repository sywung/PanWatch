"""yfinance>=1.x 的 fast_info:属性名 snake_case 可用,但 .get("last_price") 恒为 None。"""

import sys
import types

from marketdata.symbol import Symbol
from marketdata.vendors.yfinance import YFinanceQuoteVendor


class _FastInfo(dict):
    """模拟真实 FastInfo:dict 键是 camelCase,snake_case 只能用属性取。"""

    def __init__(self, last, prev):
        super().__init__(lastPrice=last, previousClose=prev)
        self.last_price = last
        self.previous_close = prev
        self.open = prev
        self.day_high = last
        self.day_low = prev
        self.last_volume = 1000


def _install(monkeypatch, prices: dict):
    calls = []

    class _Ticker:
        def __init__(self, ticker):
            calls.append(ticker)
            last = prices.get(ticker)
            self.fast_info = _FastInfo(last, 100.0 if last else None)

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_Ticker))
    return calls


def test_reads_fast_info_attributes(monkeypatch):
    _install(monkeypatch, {"AAPL": 110.0})
    q = YFinanceQuoteVendor().fetch([Symbol.parse("AAPL", "US")], {})[0]
    assert q.current_price == 110.0 and q.prev_close == 100.0
    assert abs(q.change_pct - 10.0) < 1e-9


def test_tw_listed(monkeypatch):
    calls = _install(monkeypatch, {"2330.TW": 2495.0})
    q = YFinanceQuoteVendor().fetch([Symbol.parse("2330", "TW")], {})[0]
    assert q.symbol == "2330" and q.market == "TW" and q.current_price == 2495.0
    assert calls == ["2330.TW"]


def test_tw_otc_falls_back_to_two(monkeypatch):
    calls = _install(monkeypatch, {"6488.TWO": 1125.0})
    q = YFinanceQuoteVendor().fetch([Symbol.parse("6488", "TW")], {})[0]
    assert q.current_price == 1125.0
    assert calls == ["6488.TW", "6488.TWO"]
