"""F3:期交所 MIS 期货报价 vendor(getQuoteDetail,POST JSON)。

vendor 只认具体合约代码(如 TXFJ6);连续代码 → 合约的解析在平台层(需要休市日历)。
规则(2026-10-01 20:12 夜盘实测,fixture 为当时的真实回应):
- 每个合约同时查 `-F`(日盘)与 `-M`(夜盘),取有成交且 (CDate, CTime) 最新的那笔;
  个股期货大多没有夜盘,只会有 -F。
- 查不到的代号回一列 SymbolID 为空字串的资料,要略过。
- 近月没挂牌(如 RLF 只有 202612):往后找下一个有挂牌的月份,回传的 Quote.symbol
  仍是请求的代码(引擎只收 symbol 与请求相同的报价),实际合约放 Quote.contract。
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest

import marketdata.vendors.taifex as tx
from marketdata.http import market_post as real_market_post
from marketdata.symbol import Market, Symbol

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/taifex/mis_quote_detail_night.json").read_text(encoding="utf-8")
)
_ROWS = {r["SymbolID"]: r for r in _FIXTURE["RtData"]["QuoteList"] if r["SymbolID"]}
_BLANK = next(r for r in _FIXTURE["RtData"]["QuoteList"] if not r["SymbolID"])


def _sym(code):
    return Symbol(Market.TWF, code)


_NO_OVERRIDE = object()


def _install(monkeypatch, rows=None, payload_override=_NO_OVERRIDE):
    rows = _ROWS if rows is None else rows
    calls = []

    def fake_market_post(url, **kwargs):
        # 绑定真实签名:漏传/传错参数在这里就炸
        inspect.signature(real_market_post).bind(url, **kwargs)
        ids = kwargs["json_body"]["SymbolID"]
        calls.append((url, kwargs))
        if payload_override is not _NO_OVERRIDE:
            return payload_override
        quote_list = [copy.deepcopy(rows.get(i, _BLANK)) for i in ids]
        return {"RtCode": "0", "RtMsg": "", "RtData": {"QuoteList": quote_list}}

    monkeypatch.setattr(tx, "market_post", fake_market_post)
    return calls


def _by_symbol(quotes):
    return {q.symbol: q for q in quotes}


def test_vendor_registration():
    assert tx.TaifexMisQuoteVendor.name == "taifex"
    assert tx.TaifexMisQuoteVendor.supports_markets == {"TWF"}


def test_night_session_quote_is_preferred_when_newer(monkeypatch):
    calls = _install(monkeypatch)
    q = _by_symbol(tx.TaifexMisQuoteVendor().fetch([_sym("TXFJ6")], {}))["TXFJ6"]
    assert q.market == "TWF"
    assert q.current_price == 48461.0
    assert q.prev_close == 48698.0                 # CRefPrice
    assert (q.open_price, q.high_price, q.low_price) == (48622.0, 48661.0, 48250.0)
    assert q.volume == 15421.0
    assert q.change_amount == pytest.approx(-237.0)
    assert q.change_pct == pytest.approx(-237.0 / 48698.0 * 100)
    assert (q.contract, q.session) == ("TXFJ6", "night")
    url, kwargs = calls[0]
    assert url == "https://mis.taifex.com.tw/futures/api/getQuoteDetail"
    assert kwargs["host_key"] == "mis.taifex.com.tw"
    assert kwargs["headers"]["User-Agent"].startswith("Mozilla/5.0")   # 预设 UA 会被挡
    assert set(kwargs["json_body"]["SymbolID"]) >= {"TXFJ6-F", "TXFJ6-M"}


def test_stock_future_without_night_session_uses_day(monkeypatch):
    _install(monkeypatch)
    q = _by_symbol(tx.TaifexMisQuoteVendor().fetch([_sym("CAFJ6")], {}))["CAFJ6"]
    assert (q.current_price, q.prev_close, q.session, q.contract) == (255.5, 258.5, "day", "CAFJ6")


def test_day_session_wins_once_it_is_newer(monkeypatch):
    rows = copy.deepcopy(_ROWS)
    rows["TXFJ6-F"].update(CDate="20261002", CTime="090101", CLastPrice="48700.00")
    rows["TXFJ6-M"].update(CDate="20261002", CTime="045959")
    _install(monkeypatch, rows)
    q = _by_symbol(tx.TaifexMisQuoteVendor().fetch([_sym("TXFJ6")], {}))["TXFJ6"]
    assert (q.current_price, q.session) == (48700.0, "day")


def test_night_row_without_trade_falls_back_to_day(monkeypatch):
    rows = copy.deepcopy(_ROWS)
    rows["CDFJ6-M"].update(CLastPrice="", CDate="20261002", CTime="150000")
    _install(monkeypatch, rows)
    q = _by_symbol(tx.TaifexMisQuoteVendor().fetch([_sym("CDFJ6")], {}))["CDFJ6"]
    assert (q.current_price, q.session) == (2530.0, "day")


def test_zero_price_is_not_a_trade(monkeypatch):
    rows = copy.deepcopy(_ROWS)
    rows["CDFJ6-M"].update(CLastPrice="0.00", CDate="20261002", CTime="150000")
    _install(monkeypatch, rows)
    q = _by_symbol(tx.TaifexMisQuoteVendor().fetch([_sym("CDFJ6")], {}))["CDFJ6"]
    assert q.session == "day" and q.current_price == 2530.0


def test_unlisted_near_month_rolls_to_next_listed_month(monkeypatch):
    calls = _install(monkeypatch)
    q = _by_symbol(tx.TaifexMisQuoteVendor().fetch([_sym("RLFJ6")], {}))["RLFJ6"]
    assert q.symbol == "RLFJ6"                    # 必须等于请求代码,否则引擎会丢掉
    assert (q.contract, q.session, q.current_price) == ("RLFL6", "day", 27.8)
    asked = [i for _, kw in calls for i in kw["json_body"]["SymbolID"]]
    assert "RLFK6-F" in asked and "RLFL6-F" in asked


def test_month_roll_crosses_year():
    assert tx.following_contracts("TXFL6", 3) == ["TXFA7", "TXFB7", "TXFC7"]


def test_contract_not_listed_anywhere_is_skipped(monkeypatch):
    _install(monkeypatch)
    quotes = tx.TaifexMisQuoteVendor().fetch([_sym("CUFJ6"), _sym("TXFJ6")], {})
    assert [q.symbol for q in quotes] == ["TXFJ6"]


@pytest.mark.parametrize("code", ["TXF", "2330", "txfj6", "TXFJ", "TXFM6", ""])
def test_invalid_codes_make_no_request(monkeypatch, code):
    calls = _install(monkeypatch)
    assert tx.TaifexMisQuoteVendor().fetch([_sym(code)], {}) == []
    assert calls == []


def test_batches_requests(monkeypatch):
    calls = _install(monkeypatch)
    codes = [f"{chr(65 + i // 26)}{chr(65 + i % 26)}FJ6" for i in range(45)]
    tx.TaifexMisQuoteVendor().fetch([_sym(c) for c in codes], {})
    first_round = [kw["json_body"]["SymbolID"] for _, kw in calls][:3]
    assert all(len(ids) <= 40 for _, kw in calls for ids in [kw["json_body"]["SymbolID"]])
    assert sum(len(ids) for ids in first_round) == 90   # 45 个合约 × 日盘/夜盘


def test_duplicate_symbols_requested_once(monkeypatch):
    calls = _install(monkeypatch)
    quotes = tx.TaifexMisQuoteVendor().fetch([_sym("TXFJ6"), _sym("TXFJ6")], {})
    assert len(quotes) == 1
    assert calls[0][1]["json_body"]["SymbolID"].count("TXFJ6-F") == 1


@pytest.mark.parametrize(
    "payload",
    [None, {"RtCode": "1", "RtMsg": "error", "RtData": None}, {"RtData": {"QuoteList": "x"}}, "garbage"],
)
def test_bad_payload_returns_empty(monkeypatch, payload):
    _install(monkeypatch, payload_override=payload)
    assert tx.TaifexMisQuoteVendor().fetch([_sym("TXFJ6")], {}) == []


# ---------------------------------------------------------------- 有挂牌但今天没成交 / 网络失败


def _untraded_row(symbol_id, name, ref):
    # 2026-10-01 实测:冷门个股期货近月有挂牌但当日无成交(318 档里 24 档),CLastPrice 为 0.00
    row = copy.deepcopy(_BLANK)
    row.update(SymbolID=symbol_id, DispCName=name, Status="TC", CLastPrice="0.00", CRefPrice=ref,
               COpenPrice="0.00", CHighPrice="0.00", CLowPrice="0.00", CTotalVolume="0",
               CDate="20261001", CTime="")
    return row


def test_listed_contract_without_trade_uses_reference_price(monkeypatch):
    rows = {**_ROWS, "DZFJ6-F": _untraded_row("DZFJ6-F", "大成期貨106", "51.90")}
    calls = _install(monkeypatch, rows)
    q = _by_symbol(tx.TaifexMisQuoteVendor().fetch([_sym("DZFJ6")], {}))["DZFJ6"]
    assert (q.current_price, q.prev_close, q.change_amount, q.change_pct) == (51.9, 51.9, 0.0, 0.0)
    assert (q.contract, q.session, q.volume) == ("DZFJ6", "day", 0.0)
    assert len(calls) == 1          # 有挂牌就不能往后找远月


def test_traded_session_beats_untraded_listing(monkeypatch):
    rows = copy.deepcopy(_ROWS)
    rows["CDFJ6-M"].update(CLastPrice="0.00", CDate="20261002", CTime="")
    _install(monkeypatch, rows)
    q = _by_symbol(tx.TaifexMisQuoteVendor().fetch([_sym("CDFJ6")], {}))["CDFJ6"]
    assert (q.current_price, q.session) == (2530.0, "day")


def test_network_failure_does_not_trigger_month_roll(monkeypatch):
    calls = _install(monkeypatch, payload_override=None)
    assert tx.TaifexMisQuoteVendor().fetch([_sym("TXFJ6"), _sym("CDFJ6")], {}) == []
    assert len(calls) == 1          # 失败时不能再发 6 个月 × 日夜盘的请求放大流量
