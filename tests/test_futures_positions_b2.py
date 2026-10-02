"""Phase 2b B2:期货持仓 API 与账户汇总。

设计见 vault projects/panwatch/phase2-plan.md「Phase 2b」与 decisions.md 2026-10-02:
- 独立表 futures_positions;契约乘数存在持仓上,未给时依商品带预设
- 列表附即时价、未实现损益、保证金占用、权益数、追缴、结算日与剩余天数
- 账户汇总:total_assets 加期货未实现损益;股票口径的市值/成本/报酬率不变
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.platform.persistence.models  # noqa: F401
from src.modules.portfolio.api import accounts
from src.modules.portfolio.api import futures_positions as api
from src.platform.marketdata import futures as futures_mod
from src.platform.marketdata import futures_margin as fm
from src.platform.marketdata.futures import FuturesProduct
from src.platform.persistence.database import Base
from src.platform.persistence.models import Account, FuturesPosition, Position, Stock
from src.platform.scheduling import trading_calendar

PRODUCTS = {
    "CDF": FuturesProduct("CDF", "台積電期貨", "stock", "CDF", "2330", False),
    "QFF": FuturesProduct("QFF", "小型台積電期貨", "stock", "QFF", "2330", True),
    "MXF": FuturesProduct("MXF", "小台指", "index", "MTX", None, False),
}
MARGINS = {
    "CDF": fm.Margin("rate", 0.135, 0.1035),
    "MXF": fm.Margin("fixed", 175250, 134500),
}
QUOTES = {"CDFJ6": 2520.0, "CDFK6": 2530.0, "MXFJ6": 48770.0}
NOW = datetime(2026, 10, 2, 10, 0)


def _third_wednesday(year: int, month: int) -> date:
    d = date(year, month, 15)
    while d.weekday() != 2:
        d = d.replace(day=d.day + 1)
    return d


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(futures_mod, "get_futures_product", lambda code: PRODUCTS.get(code))
    monkeypatch.setattr(fm, "get_margin", lambda code: MARGINS.get(code))
    monkeypatch.setattr(trading_calendar, "futures_settlement_date", _third_wednesday)
    monkeypatch.setattr(api, "_now", lambda: NOW)
    # 账户汇总会取汇率快照;测试里不连 Yahoo
    from src.platform.marketdata import fx
    fx.reset_cache()
    monkeypatch.setattr(fx, "_fetch_yahoo_rate", lambda symbol: 30.0)
    quote_calls = []

    def fake_quotes(symbols):
        quote_calls.append(sorted(symbols))
        return {s: QUOTES[s] for s in symbols if s in QUOTES}

    monkeypatch.setattr(api, "_fetch_contract_quotes", fake_quotes)
    with sessionmaker(bind=engine)() as session:
        session.quote_calls = quote_calls
        yield session
    engine.dispose()


@pytest.fixture
def account(db):
    acc = Account(name="主帳戶", available_funds=1_000_000)
    db.add(acc)
    db.commit()
    return acc


def _create(db, account, **kw):
    payload = {"account_id": account.id, "product_code": "CDF", "contract_month": "202610",
               "direction": "long", "lots": 2, "entry_price": 2500.0}
    payload.update(kw)
    return api.create_futures_position(api.FuturesPositionCreate(**payload), db=db)


def _error_code(exc_info) -> str:
    return exc_info.value.detail["code"]


# ============================================================
# 1. 新增与验证
# ============================================================

def test_create_uses_default_multiplier(db, account):
    out = _create(db, account)
    assert out["multiplier"] == 2000
    assert out["product_name"] == "台積電期貨"
    assert out["contract_symbol"] == "CDFJ6"
    assert db.query(FuturesPosition).count() == 1


def test_create_keeps_explicit_multiplier(db, account):
    """使用者指定乘数(例如调整型契约)时以使用者为准。"""
    assert _create(db, account, multiplier=1000)["multiplier"] == 1000


@pytest.mark.parametrize("kw,code", [
    ({"product_code": "ZZZ"}, "futures_product_not_found"),
    ({"direction": "buy"}, "invalid_direction"),
    ({"lots": 0}, "invalid_lots"),
    ({"entry_price": 0}, "invalid_entry_price"),
    ({"multiplier": -1}, "invalid_multiplier"),
    ({"contract_month": "2026-10"}, "invalid_contract_month"),
    ({"contract_month": "202613"}, "invalid_contract_month"),
    ({"contract_month": "202609"}, "contract_expired"),  # 9 月已于 9/16 结算
])
def test_create_validation(db, account, kw, code):
    with pytest.raises(HTTPException) as exc:
        _create(db, account, **kw)
    assert exc.value.status_code == 400
    assert _error_code(exc) == code


def test_create_unknown_account(db, account):
    with pytest.raises(HTTPException) as exc:
        _create(db, account, account_id=999)
    assert _error_code(exc) == "account_not_found"


def test_same_product_two_months_allowed(db, account):
    """转仓期间同商品可同时持有两个月份。"""
    _create(db, account, contract_month="202610")
    _create(db, account, contract_month="202611")
    assert db.query(FuturesPosition).count() == 2


# ============================================================
# 2. 列表:即时价、损益、保证金、结算
# ============================================================

def test_list_includes_metrics(db, account):
    _create(db, account)  # CDF 10 月多单 2 口 @2500
    _create(db, account, product_code="MXF", direction="short", lots=1, entry_price=48800.0)

    rows = {r["product_code"]: r for r in api.list_futures_positions(account_id=None, db=db)}

    cdf = rows["CDF"]
    assert cdf["current_price"] == 2520.0
    assert cdf["unrealized_pnl"] == 80_000            # 20 × 2000 × 2
    assert cdf["margin_used"] == pytest.approx(0.135 * 2520 * 2000 * 2)
    assert cdf["equity"] == pytest.approx(cdf["margin_used"] + 80_000)
    assert cdf["margin_call"] is False
    assert cdf["settlement_date"] == "2026-10-21"
    assert cdf["days_to_settlement"] == 19
    assert cdf["account_name"] == "主帳戶"

    mxf = rows["MXF"]
    assert mxf["unrealized_pnl"] == 1_500              # 空单 (48800−48770)×50
    assert mxf["margin_used"] == 175_250


def test_list_fetches_quotes_in_one_batch(db, account):
    _create(db, account, contract_month="202610")
    _create(db, account, contract_month="202611")
    db.quote_calls.clear()

    api.list_futures_positions(account_id=None, db=db)

    assert db.quote_calls == [["CDFJ6", "CDFK6"]]


def test_list_without_quote_or_margin(db, account):
    """没有报价(或没有保证金资料):相关栏位为 None,不报错。"""
    _create(db, account, product_code="QFF", contract_month="202612", lots=1, entry_price=2500.0)
    row = api.list_futures_positions(account_id=None, db=db)[0]
    assert row["current_price"] is None
    assert row["unrealized_pnl"] is None
    assert row["margin_used"] is None


def test_list_filters_by_account(db, account):
    other = Account(name="另一個", available_funds=0)
    db.add(other)
    db.commit()
    _create(db, account)
    _create(db, other)
    assert len(api.list_futures_positions(account_id=other.id, db=db)) == 1


# ============================================================
# 3. 修改与删除
# ============================================================

def test_update_partial_fields(db, account):
    pid = _create(db, account)["id"]
    out = api.update_futures_position(pid, api.FuturesPositionUpdate(lots=3, note="加碼"), db=db)
    assert out["lots"] == 3 and out["note"] == "加碼"
    assert out["entry_price"] == 2500.0


def test_update_validation_and_missing(db, account):
    pid = _create(db, account)["id"]
    with pytest.raises(HTTPException) as exc:
        api.update_futures_position(pid, api.FuturesPositionUpdate(lots=-1), db=db)
    assert _error_code(exc) == "invalid_lots"
    with pytest.raises(HTTPException) as exc:
        api.update_futures_position(999, api.FuturesPositionUpdate(lots=1), db=db)
    assert exc.value.status_code == 404


def test_delete(db, account):
    pid = _create(db, account)["id"]
    api.delete_futures_position(pid, db=db)
    assert db.query(FuturesPosition).count() == 0
    with pytest.raises(HTTPException) as exc:
        api.delete_futures_position(pid, db=db)
    assert exc.value.status_code == 404


# ============================================================
# 4. 新增表单选项
# ============================================================

def test_options_gives_default_multiplier_and_open_months(db):
    """10/2(10 月尚未结算):可选 10、11、12 月,依序。"""
    out = api.futures_position_options(product_code="CDF")
    assert out["multiplier"] == 2000
    assert [m["contract_month"] for m in out["months"]] == ["202610", "202611", "202612"]
    assert out["months"][0] == {"contract_month": "202610", "contract_symbol": "CDFJ6",
                                "settlement_date": "2026-10-21"}


def test_options_unknown_product(db):
    with pytest.raises(HTTPException) as exc:
        api.futures_position_options(product_code="ZZZ")
    assert exc.value.status_code == 404


# ============================================================
# 5. 账户汇总
# ============================================================

def test_portfolio_summary_adds_futures_pnl_to_assets_only(db, account, monkeypatch):
    """total_assets 加期货未实现损益;股票口径的市值/成本/损益不变。"""
    st = Stock(symbol="2330", name="台積電", market="TW")
    db.add(st)
    db.flush()
    db.add(Position(account_id=account.id, stock_id=st.id, cost_price=900.0, quantity=1000))
    db.commit()
    monkeypatch.setattr(accounts, "_fetch_quotes_for_stocks", lambda stocks: {
        "2330": {"symbol": "2330", "current_price": 1000.0, "change_pct": 1.0, "prev_close": 990.0},
    })
    _create(db, account)  # +80,000

    res = accounts.get_portfolio_summary(db=db)
    acc = res["accounts"][0]

    assert acc["total_market_value"] == 1_000_000
    assert acc["total_pnl"] == 100_000                       # 只算股票
    assert acc["futures_unrealized_pnl"] == 80_000
    assert acc["futures_margin_used"] == pytest.approx(0.135 * 2520 * 2000 * 2)
    assert acc["futures_margin_call"] is False
    assert acc["total_assets"] == 1_000_000 + 1_000_000 + 80_000
    assert res["total"]["futures_unrealized_pnl"] == 80_000
    assert res["total"]["total_assets"] == 2_080_000


def test_portfolio_summary_without_futures_unchanged(db, account, monkeypatch):
    monkeypatch.setattr(accounts, "_fetch_quotes_for_stocks", lambda stocks: {})
    res = accounts.get_portfolio_summary(db=db)
    assert res["accounts"][0]["futures_unrealized_pnl"] == 0
    assert res["total"]["total_assets"] == 1_000_000


def test_portfolio_summary_without_quotes_skips_futures(db, account, monkeypatch):
    """include_quotes=False 时不抓期货报价,期货损益记 0。"""
    _create(db, account)
    db.quote_calls.clear()
    res = accounts.get_portfolio_summary(include_quotes=False, db=db)
    assert db.quote_calls == []
    assert res["accounts"][0]["futures_unrealized_pnl"] == 0
