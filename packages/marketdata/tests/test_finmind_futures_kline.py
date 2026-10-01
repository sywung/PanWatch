"""F4:FinMind TaiwanFuturesDaily → 期货连续近月日 K(TWF)。

规则(2026-10-01 决策,见 vault projects/panwatch/decisions.md):
- 只用一般时段(trading_session == "position"),与期交所官方日线一致;盘后(after_market)不并入。
- 每个交易日取「最近的单月合约」(contract_date 为 6 位数字的最小值);价差组合
  (202609/202610)排除。结算日当天仍是到期月,隔天换下月 —— 不需要休市日历。
- 不做价格调整:换月日会有真实的价差跳空(9/16 → 9/17 由 9 月合约换 10 月)。
- FinMind 的 data_id 是 openapi 代码:TXF→TX、MXF→MTX、EXF→TE、FXF→TF,其余(TMF、个股期货)相同。
fixture 是 2026-10-01 抓的真实回应。
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest

import marketdata.vendors.finmind as fm
from marketdata.http import market_get as real_market_get
from marketdata.symbol import Market, Symbol

FX = Path(__file__).parent / "fixtures/taifex"
_TX = json.loads((FX / "finmind_futures_tx_202609.json").read_text(encoding="utf-8"))
_CDF = json.loads((FX / "finmind_futures_cdf_202609.json").read_text(encoding="utf-8"))


def _install(monkeypatch, payload):
    calls = []

    def fake_market_get(url, **kwargs):
        inspect.signature(real_market_get).bind(url, **kwargs)
        calls.append(kwargs)
        return copy.deepcopy(payload)

    monkeypatch.setattr(fm, "market_get", fake_market_get)
    return calls


def _fetch(code, days=60, config=None):
    return fm.FinMindKlineVendor().fetch([Symbol(Market.TWF, code)], {"days": days, **(config or {})})


def test_finmind_supports_tw_and_twf():
    assert fm.FinMindKlineVendor.supports_markets == {"TW", "TWF"}


def test_continuous_near_month_rolls_after_settlement_day(monkeypatch):
    calls = _install(monkeypatch, _TX)
    bars = {b.date: b for b in _fetch("TXF")}

    params = calls[0]["params"]
    assert params["dataset"] == "TaiwanFuturesDaily" and params["data_id"] == "TX"
    assert list(bars) == sorted(bars)
    assert bars["2026-09-15"].close == 45607.0     # 9 月合约
    assert bars["2026-09-16"].close == 45759.0     # 结算日当天仍是到期的 9 月合约
    assert bars["2026-09-17"].close == 46445.0     # 隔天换 10 月合约
    b = bars["2026-09-16"]
    assert (b.open, b.high, b.low, b.volume) == (45534.0, 46093.0, 45518.0, 28491.0)


def test_after_market_and_spread_rows_are_excluded(monkeypatch):
    _install(monkeypatch, _TX)
    bars = _fetch("TXF")
    # 9/10 ~ 9/22 共 9 个交易日,每天恰好一根(一般时段、单月合约)
    assert [b.date for b in bars] == [
        "2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16",
        "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22",
    ]
    position_closes = {
        r["close"] for r in _TX["data"]
        if r["trading_session"] == "position" and r["contract_date"] in ("202609", "202610")
    }
    assert all(b.close in position_closes for b in bars)


@pytest.mark.parametrize("code, data_id", [("TXF", "TX"), ("MXF", "MTX"), ("TMF", "TMF"),
                                           ("EXF", "TE"), ("FXF", "TF"), ("CDF", "CDF")])
def test_data_id_mapping(monkeypatch, code, data_id):
    calls = _install(monkeypatch, {"status": 200, "data": []})
    _fetch(code)
    assert calls[0]["params"]["data_id"] == data_id


def test_stock_future(monkeypatch):
    _install(monkeypatch, _CDF)
    bars = {b.date: b for b in _fetch("CDF")}
    near = {}
    for r in _CDF["data"]:
        if r["trading_session"] == "position" and len(r["contract_date"]) == 6:
            near.setdefault(r["date"], min(
                (x for x in _CDF["data"] if x["date"] == r["date"] and x["trading_session"] == "position"
                 and len(x["contract_date"]) == 6),
                key=lambda x: x["contract_date"],
            ))
    assert set(bars) == set(near)
    assert all(bars[d].close == near[d]["close"] for d in bars)


def test_trims_to_requested_days(monkeypatch):
    _install(monkeypatch, _TX)
    assert [b.date for b in _fetch("TXF", days=3)] == ["2026-09-18", "2026-09-21", "2026-09-22"]


def test_skips_non_positive_prices(monkeypatch):
    payload = copy.deepcopy(_TX)
    for r in payload["data"]:
        if r["date"] == "2026-09-22" and r["contract_date"] == "202610" and r["trading_session"] == "position":
            r["open"] = 0.0
    _install(monkeypatch, payload)
    bars = {b.date: b for b in _fetch("TXF")}
    # 近月那根价格不合理就整天略过,不能拿远月顶替(远月价格不同,会制造假走势)
    assert "2026-09-22" not in bars


def test_token_sent_as_bearer(monkeypatch):
    calls = _install(monkeypatch, {"status": 200, "data": []})
    _fetch("TXF", config={"token": " abc "})
    assert calls[0]["headers"]["Authorization"] == "Bearer abc"


@pytest.mark.parametrize("code", ["TX", "2330", "txf", "TXFJ6", ""])
def test_invalid_futures_codes_make_no_request(monkeypatch, code):
    calls = _install(monkeypatch, _TX)
    assert _fetch(code) == []
    assert calls == []


def test_api_error_raises(monkeypatch):
    _install(monkeypatch, {"status": 402, "msg": "Requests reach the upper limit."})
    with pytest.raises(RuntimeError, match="upper limit"):
        _fetch("TXF")


def test_tw_stock_path_unchanged(monkeypatch):
    calls = _install(monkeypatch, {"status": 200, "data": []})
    fm.FinMindKlineVendor().fetch([Symbol(Market.TW, "2330")], {"days": 5})
    assert calls[0]["params"]["dataset"] == "TaiwanStockPrice"


def test_spread_contract_never_used_when_near_month_row_missing(monkeypatch):
    # 价差组合 202609/202610 的「价格」是两个月份的价差(约一两百点);某天单月近月列缺失时,
    # 若没排除价差组合,字串最小值会挑到它,K 线会从四万多点掉到一百多点
    payload = copy.deepcopy(_TX)
    payload["data"] = [
        r for r in payload["data"]
        if not (r["date"] == "2026-09-15" and r["contract_date"] == "202609")
    ]
    assert any(r["date"] == "2026-09-15" and "/" in r["contract_date"] for r in payload["data"])
    _install(monkeypatch, payload)
    bar = {b.date: b for b in _fetch("TXF")}["2026-09-15"]
    assert bar.close == 45740.0          # 当天剩下最近的单月合约(10 月)
