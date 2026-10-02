"""pythonnet 與元大 SparkAPI .NET 元件的薄轉接層。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable


def load_runtime(sdk_dir: str | os.PathLike[str]):
    sdk_path = str(Path(sdk_dir).resolve())
    os.chdir(sdk_path)
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)

    from pythonnet import load

    dotnet_root = os.environ.get("DOTNET_ROOT")
    if dotnet_root:
        load("coreclr", dotnet_root=dotnet_root)
    else:
        load("coreclr")

    import clr

    clr.AddReference("YuantaSparkAPI")
    from System.Collections.Generic import List
    from YuantaOneAPI import (
        KLineType,
        OnResponseEventHandler,
        Quote,
        YuantaSparkAPITrader,
        enumEnvironmentMode,
        enumMarketType,
    )

    return DotnetAdapter(
        YuantaSparkAPITrader,
        enumEnvironmentMode,
        enumMarketType,
        KLineType,
        Quote,
        OnResponseEventHandler,
        List,
    )


class DotnetAdapter:
    def __init__(
        self,
        trader_type: Any,
        environment_type: Any,
        market_type: Any,
        kline_type: Any,
        quote_type: Any,
        response_handler_type: Any,
        list_type: Any,
    ):
        self._trader_type = trader_type
        self._environment_type = environment_type
        self._market_type = market_type
        self._kline_type = kline_type
        self._quote_type = quote_type
        self._response_handler_type = response_handler_type
        self._list_type = list_type

    def create_trader(self, log_dir: str):
        return self._trader_type(log_dir)

    def subscribe(self, trader: Any, fn: Callable):
        trader.OnResponse += self._response_handler_type(fn)

    def env(self, name: str):
        return getattr(self._environment_type, name)

    def market(self, enum_name: str):
        return getattr(self._market_type, enum_name)

    def kline_type(self, value: int):
        return self._kline_type(value)

    def build_quote_list(self, items: list[tuple[Any, str]]):
        quotes = self._list_type[self._quote_type]()
        for market, code in items:
            quote = self._quote_type()
            quote.MarketType = market
            quote.StockCode = code
            quotes.Add(quote)
        return quotes
