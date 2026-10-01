"""计价币别改为 TWD:汇率模块(Yahoo)与持仓汇总换算。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.platform.marketdata import fx
from src.platform.persistence.database import Base
from src.platform.persistence.models import Account, Position, Stock


@pytest.fixture(autouse=True)
def _reset_fx(monkeypatch):
    fx.reset_cache()
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(fx, "_now", lambda: clock["t"])
    yield clock
    fx.reset_cache()


def _install_fetch(monkeypatch, rates: dict):
    calls = []

    def fake(symbol):
        calls.append(symbol)
        v = rates.get(symbol)
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr(fx, "_fetch_yahoo_rate", fake)
    return calls


# ---------------------------------------------------------------- 币别对应


def test_market_currency_mapping():
    assert fx.market_currency("TW") == "TWD"
    assert fx.market_currency("CN") == "CNY"
    assert fx.market_currency("HK") == "HKD"
    assert fx.market_currency("US") == "USD"
    assert fx.market_currency("tw") == "TWD"


def test_unknown_market_falls_back_to_base_currency():
    assert fx.market_currency("XX") == "TWD"
    assert fx.market_currency(None) == "TWD"


def test_base_currency_rate_is_one_without_network(monkeypatch):
    calls = _install_fetch(monkeypatch, {})
    assert fx.get_rate_to_base("TWD") == 1.0
    assert fx.rate_for_market("TW") == 1.0
    assert calls == []


# ---------------------------------------------------------------- 取价与缓存


def test_rate_uses_yahoo_pair_symbol(monkeypatch):
    calls = _install_fetch(monkeypatch, {"USDTWD=X": 31.87, "HKDTWD=X": 4.07, "CNYTWD=X": 4.75})
    assert fx.get_rate_to_base("USD") == 31.87
    assert fx.rate_for_market("HK") == 4.07
    assert fx.rate_for_market("CN") == 4.75
    assert calls == ["USDTWD=X", "HKDTWD=X", "CNYTWD=X"]


def test_rate_cached_for_one_hour(monkeypatch, _reset_fx):
    calls = _install_fetch(monkeypatch, {"USDTWD=X": 31.87})
    fx.get_rate_to_base("USD")
    _reset_fx["t"] += 3599
    fx.get_rate_to_base("USD")
    assert len(calls) == 1
    _reset_fx["t"] += 2
    fx.get_rate_to_base("USD")
    assert len(calls) == 2


def test_failure_without_cache_uses_fallback(monkeypatch):
    _install_fetch(monkeypatch, {"USDTWD=X": None, "HKDTWD=X": RuntimeError("down"), "CNYTWD=X": None})
    assert fx.get_rate_to_base("USD") == 32.0
    assert fx.get_rate_to_base("HKD") == 4.1
    assert fx.get_rate_to_base("CNY") == 4.5


def test_failure_keeps_last_good_rate(monkeypatch, _reset_fx):
    rates = {"USDTWD=X": 31.87}
    _install_fetch(monkeypatch, rates)
    assert fx.get_rate_to_base("USD") == 31.87
    _reset_fx["t"] += 3601
    rates["USDTWD=X"] = None
    assert fx.get_rate_to_base("USD") == 31.87


def test_nonpositive_rate_treated_as_failure(monkeypatch):
    _install_fetch(monkeypatch, {"USDTWD=X": 0.0})
    assert fx.get_rate_to_base("USD") == 32.0
    fx.reset_cache()
    _install_fetch(monkeypatch, {"USDTWD=X": -5})
    assert fx.get_rate_to_base("USD") == 32.0


def test_failure_backs_off_five_minutes(monkeypatch, _reset_fx):
    calls = _install_fetch(monkeypatch, {"USDTWD=X": None})
    fx.get_rate_to_base("USD")
    fx.get_rate_to_base("USD")
    assert len(calls) == 1  # 失败后不立刻重打
    _reset_fx["t"] += 301
    fx.get_rate_to_base("USD")
    assert len(calls) == 2


def test_exchange_rates_snapshot_keys():
    snap = fx.exchange_rates_snapshot()
    assert set(snap) == {"USD_TWD", "HKD_TWD", "CNY_TWD"}


def test_exchange_rates_snapshot_values(monkeypatch):
    _install_fetch(monkeypatch, {"USDTWD=X": 31.87, "HKDTWD=X": 4.07, "CNYTWD=X": 4.75})
    assert fx.exchange_rates_snapshot() == {"USD_TWD": 31.87, "HKD_TWD": 4.07, "CNY_TWD": 4.75}


# ---------------------------------------------------------------- 持仓汇总


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def _portfolio(db, monkeypatch):
    from src.modules.portfolio.api import accounts

    acc = Account(name="main", available_funds=1000)
    db.add(acc)
    db.flush()
    rows = [("2330", "台積電", "TW", 900.0, 1000), ("AAPL", "苹果", "US", 100.0, 10),
            ("600519", "贵州茅台", "CN", 1500.0, 100)]
    for sym, name, mkt, cost, qty in rows:
        st = Stock(symbol=sym, name=name, market=mkt)
        db.add(st)
        db.flush()
        db.add(Position(account_id=acc.id, stock_id=st.id, cost_price=cost, quantity=qty))
    db.commit()

    quotes = {
        "2330": {"symbol": "2330", "current_price": 1000.0, "change_pct": 1.0, "prev_close": 990.0},
        "AAPL": {"symbol": "AAPL", "current_price": 110.0, "change_pct": 1.0, "prev_close": 100.0},
        "600519": {"symbol": "600519", "current_price": 1600.0, "change_pct": 1.0, "prev_close": 1500.0},
    }
    monkeypatch.setattr(accounts, "_fetch_quotes_for_stocks", lambda stocks: quotes)
    _install_fetch(monkeypatch, {"USDTWD=X": 30.0, "HKDTWD=X": 4.0, "CNYTWD=X": 4.5})
    return accounts


def test_summary_converts_to_twd(db, monkeypatch):
    accounts = _portfolio(db, monkeypatch)
    res = accounts.get_portfolio_summary(db=db)
    assert res["base_currency"] == "TWD"
    assert res["exchange_rates"] == {"USD_TWD": 30.0, "HKD_TWD": 4.0, "CNY_TWD": 4.5}
    pos = {p["symbol"]: p for p in res["accounts"][0]["positions"]}

    tw = pos["2330"]
    assert tw["exchange_rate"] is None            # 本币不换算
    assert tw["market_value_cny"] == 1_000_000.0  # 字段名沿用上游,值为基准币别(TWD)

    us = pos["AAPL"]
    assert us["exchange_rate"] == 30.0
    assert us["market_value_cny"] == 110.0 * 10 * 30.0

    cn = pos["600519"]
    assert cn["exchange_rate"] == 4.5            # A 股现在是外币
    assert cn["market_value_cny"] == 1600.0 * 100 * 4.5

    expected_mv = 1_000_000.0 + 33_000.0 + 720_000.0
    assert res["total"]["total_market_value"] == expected_mv
    assert res["total"]["total_assets"] == expected_mv + 1000


def test_gather_holdings_uses_twd(db, monkeypatch):
    accounts = _portfolio(db, monkeypatch)
    hs = {h["symbol"]: h for h in accounts._gather_holdings(db)}
    assert hs["2330"]["fx"] == 1.0 and hs["2330"]["market_value"] == 1_000_000.0
    assert hs["600519"]["fx"] == 4.5
    assert hs["AAPL"]["fx"] == 30.0


def test_legacy_cny_rate_helpers_removed():
    from src.modules.portfolio.api import accounts

    assert not hasattr(accounts, "get_hkd_cny_rate")
    assert not hasattr(accounts, "get_usd_cny_rate")
