"""YFinance 行情 vendor(可选,HK/US)。无状态 + 惰性 import;缺库抛 VendorError。"""

from __future__ import annotations

import logging

from marketdata.errors import VendorError
from marketdata.http import record_error
from marketdata.symbol import Market, Symbol
from marketdata.types import Quote
from marketdata.vendors.base import QuoteVendor

logger = logging.getLogger(__name__)


def _yf_ticker(sym: Symbol) -> str:
    if sym.market == Market.TW:
        return f"{sym.code}.TW"
    if sym.market == Market.HK:
        return f"{int(sym.code):04d}.HK" if sym.code.isdigit() else f"{sym.code}.HK"
    return sym.code


def _attr(info, name: str) -> float | None:
    """读 fast_info 属性;缺失/异常/非数值 → None。"""
    try:
        value = getattr(info, name)
    except Exception:
        return None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class YFinanceQuoteVendor(QuoteVendor):
    name = "yfinance"
    supports_markets = {"HK", "US", "TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Quote]:
        if not symbols:
            return []
        try:
            import yfinance as yf
        except ImportError as e:
            raise VendorError("yfinance 未安装,执行 `pip install yfinance` 后启用") from e

        out: list[Quote] = []
        for s in symbols:
            try:
                tickers = [_yf_ticker(s)]
                if s.market == Market.TW:
                    tickers.append(f"{s.code}.TWO")
                info = None
                last = None
                for ticker in tickers:
                    candidate = yf.Ticker(ticker).fast_info
                    # yfinance>=1.x 的 fast_info 键名是 camelCase,.get("last_price") 恒为 None;
                    # 用属性访问(last_price/previous_close/...)才拿得到值
                    last = _attr(candidate, "last_price")
                    if last:
                        info = candidate
                        break
                if info is None:
                    record_error(f"yfinance {_yf_ticker(s)}: 返回空(last_price 缺失,可能 Yahoo 不可达/被限流/需要代理)")
                    continue
                prev = _attr(info, "previous_close")
                chg = last - prev if prev else 0.0
                pct = (chg / prev * 100) if prev else 0.0
                out.append(Quote(
                    symbol=s.code, market=s.market.value, name="",
                    current_price=last, prev_close=prev,
                    open_price=_attr(info, "open") or 0.0,
                    high_price=_attr(info, "day_high") or 0.0,
                    low_price=_attr(info, "day_low") or 0.0,
                    change_amount=chg, change_pct=pct,
                    volume=_attr(info, "last_volume") or 0.0,
                ))
            except Exception as e:
                logger.debug(f"yfinance 拉取 {s.code} 失败: {e}")
                record_error(f"yfinance {_yf_ticker(s)}: {type(e).__name__}: {e}")
        return out
