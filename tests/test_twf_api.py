"""F5a:期货进入自选流程的后端 API —— 搜寻、新增自选、报价、市场状态、持仓防呆。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.platform.marketdata import futures as fu
from src.platform.marketdata import stock_list as sl
from src.platform.scheduling import trading_calendar as tc

FX = Path(__file__).parent / "fixtures"
_SSF = json.loads((FX / "taifex/ssf_lists.json").read_text(encoding="utf-8"))
_MARGIN = json.loads((FX / "taifex/ssf_margining.json").read_text(encoding="utf-8"))
_ETF_MARGIN = json.loads((FX / "taifex/ssf_etf_margining.json").read_text(encoding="utf-8"))
_HOLIDAYS = json.loads((FX / "twse_holidays_2026.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _futures_offline(monkeypatch, tmp_path):
    tc.reset_cache()
    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", lambda: _HOLIDAYS)
    tc.refresh_tw_blocking()
    monkeypatch.setattr(fu, "CACHE_FILE", tmp_path / "futures_list_cache.json")
    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", lambda: _SSF)
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", lambda: _MARGIN + _ETF_MARGIN)
    fu.reset_cache()
    yield
    fu.reset_cache()
    tc.reset_cache()


@pytest.fixture
def db():
    import src.platform.persistence.models  # noqa: F401
    from src.platform.persistence.database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# ---------------------------------------------------------------- 期货搜寻


def _codes(items):
    return [i["symbol"] for i in items]


def test_search_futures_by_code_name_and_underlying():
    assert _codes(fu.search_futures("TXF"))[0] == "TXF"
    assert _codes(fu.search_futures("txf"))[0] == "TXF"
    assert _codes(fu.search_futures("2330")) == ["CDF", "QFF"]       # 用股票代码找期货,标准在前
    assert _codes(fu.search_futures("台積電")) == ["CDF", "QFF"]
    assert set(_codes(fu.search_futures("台指"))) == {"TXF", "MXF", "TMF"}
    assert _codes(fu.search_futures("台指"))[0] == "TXF"              # 名称开头相符者在前
    assert fu.search_futures("") == []
    assert fu.search_futures("不存在") == []


def test_search_futures_item_shape():
    item = fu.search_futures("2330")[0]
    assert item == {"symbol": "CDF", "name": "台積電期貨", "market": "TWF", "board": "FUT", "underlying": "2330"}
    assert fu.search_futures("TXF")[0]["underlying"] is None


def test_search_futures_limit():
    assert len(fu.search_futures("期", limit=3)) == 3


def test_search_stocks_twf_only_futures(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("TWF 搜寻不该打股票来源")

    for name in ("_cached_search", "_lookup_tw_code", "_realtime_search", "_yahoo_search"):
        monkeypatch.setattr(sl, name, boom)
    assert _codes(sl.search_stocks("2330", "TWF")) == ["CDF", "QFF"]


def test_search_all_markets_lists_futures_after_tw(monkeypatch):
    tw = [{"symbol": "2330", "name": "台積電", "market": "TW", "board": "TSE"}]
    us = [{"symbol": "TSM", "name": "Taiwan Semiconductor", "market": "US"}]
    monkeypatch.setattr(sl, "_cached_search", lambda q, market, limit: tw if market == "TW" else [])
    monkeypatch.setattr(sl, "_lookup_tw_code", lambda q: [])
    monkeypatch.setattr(sl, "_realtime_search", lambda q, market, limit: us)
    monkeypatch.setattr(sl, "_yahoo_search", lambda q, market, limit: [])

    results = sl.search_stocks("2330", "")
    assert [(r["market"], r["symbol"]) for r in results] == [
        ("TW", "2330"), ("TWF", "CDF"), ("TWF", "QFF"), ("US", "TSM"),
    ]


def test_search_tw_market_does_not_include_futures(monkeypatch):
    tw = [{"symbol": "2330", "name": "台積電", "market": "TW", "board": "TSE"}]
    monkeypatch.setattr(sl, "_cached_search", lambda q, market, limit: tw)
    assert [r["market"] for r in sl.search_stocks("2330", "TW")] == ["TW"]


# ---------------------------------------------------------------- 新增自选


def test_create_futures_stock(db):
    from src.modules.market.api.stocks import StockCreate, create_stock

    res = create_stock(StockCreate(symbol="txf", name="台指期", market="twf"), db)
    assert (res["symbol"], res["market"]) == ("TXF", "TWF")       # 代码与市场正规化为大写


def test_create_unknown_futures_rejected(db):
    from fastapi import HTTPException

    from src.modules.market.api.stocks import StockCreate, create_stock

    with pytest.raises(HTTPException) as exc:
        create_stock(StockCreate(symbol="ZZZ", name="?", market="TWF"), db)
    assert exc.value.status_code == 400


def test_create_tw_stock_unchanged(db):
    from src.modules.market.api.stocks import StockCreate, create_stock

    res = create_stock(StockCreate(symbol="2330", name="台積電", market="TW"), db)
    assert (res["symbol"], res["market"]) == ("2330", "TW")


# ---------------------------------------------------------------- 报价


def test_quotes_include_futures_contract_and_session(db, monkeypatch):
    from src.modules.market.api import stocks as api
    from src.platform.persistence.models import Stock

    db.add_all([Stock(symbol="TXF", name="台指期", market="TWF"), Stock(symbol="2330", name="台積電", market="TW")])
    db.commit()

    def fake_rows(symbols, market):
        if market == "TWF":
            return [{"symbol": "TXF", "current_price": 48474.0, "change_pct": -0.46, "change_amount": -224.0,
                     "prev_close": 48698.0, "volume": 15600.0, "contract": "TXFJ6", "session": "night"}]
        return [{"symbol": "2330", "current_price": 2510.0, "change_pct": 1.2, "change_amount": 30.0,
                 "prev_close": 2480.0, "volume": 1.0}]

    monkeypatch.setattr(api, "md_quote_rows", fake_rows)
    quotes = api.get_quotes(db)

    assert quotes["TXF"]["contract"] == "TXFJ6"
    assert quotes["TXF"]["session"] == "night"
    assert quotes["TXF"]["volume"] == 15600.0
    assert quotes["TXF"]["current_price"] == 48474.0
    assert "contract" not in quotes["2330"] and "session" not in quotes["2330"]   # 股票回应格式不变


# ---------------------------------------------------------------- 市场状态


def test_market_status_lists_futures_after_tw():
    from src.modules.market.api.stocks import get_market_status

    codes = [r["code"] for r in get_market_status()]
    assert codes == ["TW", "TWF", "CN", "HK", "US"]


# ---------------------------------------------------------------- 持仓防呆(Phase 2a 不支援期货持仓)


def test_futures_position_rejected(db):
    from fastapi import HTTPException

    from src.modules.portfolio.api.accounts import PositionCreate, create_position
    from src.platform.persistence.models import Account, Stock

    acc = Account(name="預設帳戶")
    stock = Stock(symbol="TXF", name="台指期", market="TWF")
    db.add_all([acc, stock])
    db.commit()

    with pytest.raises(HTTPException) as exc:
        create_position(PositionCreate(account_id=acc.id, stock_id=stock.id, cost_price=48000, quantity=1), db)
    assert exc.value.status_code == 400
    assert "期貨" in str(exc.value.detail)


# ---------------------------------------------------------------- /quotes/batch(前端实际使用的报价端点)


def test_quotes_batch_includes_futures_contract_and_session(monkeypatch):
    import asyncio

    from src.modules.market.api import quotes as qapi

    def fake_rows(symbols, market):
        if market == "TWF":
            return [{"symbol": "RLF", "name": "元晶期貨", "current_price": 27.8, "prev_close": 28.45,
                     "volume": 85.0, "contract": "RLFL6", "session": "day"}]
        return [{"symbol": "2330", "name": "台積電", "current_price": 2510.0, "volume": 1.0}]

    monkeypatch.setattr(qapi, "md_quote_rows", fake_rows)
    payload = qapi.QuoteBatchRequest(items=[
        qapi.QuoteItem(symbol="RLF", market="TWF"),
        qapi.QuoteItem(symbol="2330", market="TW"),
        qapi.QuoteItem(symbol="TXF", market="TWF"),
    ])
    rows = {r["symbol"]: r for r in asyncio.run(qapi.get_quotes_batch(payload))}

    assert (rows["RLF"]["contract"], rows["RLF"]["session"]) == ("RLFL6", "day")
    assert "contract" not in rows["2330"] and "session" not in rows["2330"]   # 股票格式不变
    assert rows["TXF"]["current_price"] is None and "contract" not in rows["TXF"]   # 没报价时不硬塞


def test_single_quote_includes_futures_contract(monkeypatch):
    import asyncio

    from src.modules.market.api import quotes as qapi

    monkeypatch.setattr(qapi, "md_quote_rows", lambda symbols, market: [
        {"symbol": "TXF", "current_price": 48474.0, "contract": "TXFJ6", "session": "night"}
    ])
    row = asyncio.run(qapi.get_quote("TXF", "TWF"))
    assert (row["contract"], row["session"]) == ("TXFJ6", "night")
