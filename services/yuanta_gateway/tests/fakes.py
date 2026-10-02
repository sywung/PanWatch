"""模拟元大 .NET 物件:有 Count 属性、可用索引取值的清单,以及带属性的结果物件。"""

from __future__ import annotations

from types import SimpleNamespace


class NetList:
    def __init__(self, items):
        self._items = list(items)

    @property
    def Count(self):
        return len(self._items)

    def __getitem__(self, i):
        return self._items[i]


def ytime(h, m, s, ms=0):
    return SimpleNamespace(Hour=h, Minute=m, Second=s, Millisecond=ms)


def watch_row(code="2330", name="台積電", market=1, deal=2520.0, yst=2530.0):
    return SimpleNamespace(
        MarketNo=market, StkCode=code, StkName=name, YstPrice=yst, OpenPrice=2525.0,
        HighPrice=2540.0, LowPrice=2510.0, DealPrice=deal, TotalVol=12345, UpStopPrice=2780.0,
        DownStopPrice=2280.0, BuyPrice=2515.0, SellPrice=2520.0, Time=ytime(10, 5, 3, 120),
    )


def login_ok(account="S98875005091"):
    return SimpleNamespace(
        LoginStatus=SimpleNamespace(MsgCode="0001", MsgContent="登入成功", Count=1),
        LoginList=NetList([SimpleNamespace(Account=account, Name="王小明", InvestorID="A1", SellerNo=1)]),
    )


def login_fail(code="0102", msg="密碼凍結或未啟用"):
    return SimpleNamespace(
        LoginStatus=SimpleNamespace(MsgCode=code, MsgContent=msg, Count=0),
        LoginList=NetList([]),
    )


class FakeAdapter:
    """client 只透过 adapter 碰 .NET;测试里由 FakeAdapter 记录呼叫、由测试手动触发 OnResponse。"""

    def __init__(self):
        self.calls = []
        self.handler = None
        self.trader = SimpleNamespace(
            Open=lambda env: self.calls.append(("Open", env)),
            Login=lambda *a: self.calls.append(("Login", a)) or True,
            GetWatchListAll=lambda account, quotes: self.calls.append(("GetWatchListAll", account, quotes)) or True,
            GetKLine=lambda *a: self.calls.append(("GetKLine", a)) or True,
            Close=lambda: self.calls.append(("Close",)),
            Dispose=lambda: self.calls.append(("Dispose",)),
        )

    def create_trader(self, log_dir):
        return self.trader

    def subscribe(self, trader, fn):
        self.handler = fn

    def env(self, name):
        return f"ENV:{name}"

    def market(self, name):
        return f"MKT:{name}"

    def kline_type(self, value):
        return f"KT:{value}"

    def build_quote_list(self, items):
        return [f"{m}:{c}" for m, c in items]

    # 测试辅助:模拟服务端回应
    def respond(self, mark, index, name, value):
        self.handler(mark, index, name, None, value)
