"""TWSE mis 实时行情 vendor(台股上市+上柜)。

端点:GET https://mis.twse.com.tw/stock/api/getStockInfo.jsp
params: ex_ch="tse_2330.tw|otc_2330.tw|..."(每个代码同时送上市 tse_ 与上柜 otc_ 两个通道,
不需要上市/上柜对照表;不存在的那个通道会回 c="" 的空笔,直接跳过)。
"""

import marketdata.vendors.twse as tv
from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.symbol import Symbol
from marketdata.types import Quote


def _msg(code, ex="tse", name="台積電", z="1000.0000", y="990.0000", o="995.0000",
         h="1005.0000", l="992.0000", v="12345", b="999.0000_998.0000_"):
    return {"c": code, "ex": ex, "n": name, "z": z, "y": y, "o": o, "h": h, "l": l, "v": v, "b": b}


_EMPTY = {"c": "", "z": "-"}  # 错误前缀通道回的空笔


def _install(monkeypatch, responder):
    calls = []

    def fake_market_get(url, *, params=None, **k):
        calls.append({"url": url, "params": params, **k})
        return responder(params or {})

    monkeypatch.setattr(tv, "market_get", fake_market_get)
    return calls


def _channels(call):
    return call["params"]["ex_ch"].split("|")


def test_vendor_identity_and_registration():
    v = tv.TwseMisQuoteVendor()
    assert v.name == "twse"
    assert v.supports_markets == {"TW"}
    assert VENDOR_CLASSES_BY_TYPE["quote"]["twse"] is tv.TwseMisQuoteVendor


def test_sends_both_listed_and_otc_channels(monkeypatch):
    calls = _install(monkeypatch, lambda p: {"msgArray": [_msg("2330"), _EMPTY]})
    tv.TwseMisQuoteVendor().fetch([Symbol.parse("2330", "TW")], {})
    assert len(calls) == 1
    assert calls[0]["url"] == "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    assert set(_channels(calls[0])) == {"tse_2330.tw", "otc_2330.tw"}
    assert calls[0].get("parse") == "json"


def test_parses_quote_fields(monkeypatch):
    _install(monkeypatch, lambda p: {"msgArray": [_msg("2330"), _EMPTY]})
    out = tv.TwseMisQuoteVendor().fetch([Symbol.parse("2330", "TW")], {})
    assert len(out) == 1 and isinstance(out[0], Quote)
    q = out[0]
    assert q.symbol == "2330" and q.market == "TW" and q.name == "台積電"
    assert q.current_price == 1000.0 and q.prev_close == 990.0
    assert q.open_price == 995.0 and q.high_price == 1005.0 and q.low_price == 992.0
    assert q.volume == 12345.0
    assert abs(q.change_amount - 10.0) < 1e-9
    assert abs(q.change_pct - (10.0 / 990.0 * 100)) < 1e-9


def test_otc_stock_parsed(monkeypatch):
    _install(monkeypatch, lambda p: {"msgArray": [_EMPTY, _msg("6488", ex="otc", name="環球晶")]})
    out = tv.TwseMisQuoteVendor().fetch([Symbol.parse("6488", "TW")], {})
    assert [(q.symbol, q.name) for q in out] == [("6488", "環球晶")]


def test_no_trade_price_falls_back_to_best_bid(monkeypatch):
    _install(monkeypatch, lambda p: {"msgArray": [_msg("2330", z="-", b="1001.0000_1000.0000_")]})
    q = tv.TwseMisQuoteVendor().fetch([Symbol.parse("2330", "TW")], {})[0]
    assert q.current_price == 1001.0


def test_no_trade_and_no_bid_falls_back_to_prev_close(monkeypatch):
    _install(monkeypatch, lambda p: {"msgArray": [_msg("2330", z="-", b="-")]})
    q = tv.TwseMisQuoteVendor().fetch([Symbol.parse("2330", "TW")], {})[0]
    assert q.current_price == 990.0
    assert q.change_amount == 0.0 and q.change_pct == 0.0


def test_malformed_codes_are_dropped_before_request(monkeypatch):
    # 畸形代码会让 mis 拒绝整批(回空 body),必须送出前剔除
    calls = _install(monkeypatch, lambda p: {"msgArray": [_msg("2330")]})
    syms = [Symbol.parse("2330", "TW"), Symbol.parse("23 30", "TW"),
            Symbol.parse("", "TW"), Symbol.parse("abc", "TW")]
    out = tv.TwseMisQuoteVendor().fetch(syms, {})
    assert [q.symbol for q in out] == ["2330"]
    sent = set(_channels(calls[0]))
    assert sent == {"tse_2330.tw", "otc_2330.tw"}


def test_all_malformed_makes_no_request(monkeypatch):
    calls = _install(monkeypatch, lambda p: {"msgArray": []})
    assert tv.TwseMisQuoteVendor().fetch([Symbol.parse("abc", "TW")], {}) == []
    assert calls == []


def test_empty_input_makes_no_request(monkeypatch):
    calls = _install(monkeypatch, lambda p: {"msgArray": []})
    assert tv.TwseMisQuoteVendor().fetch([], {}) == []
    assert calls == []


def test_batches_at_most_20_channels_per_request(monkeypatch):
    codes = [f"{1101 + i}" for i in range(25)]  # 25 档 → 50 个通道 → 3 批

    def responder(params):
        chans = params["ex_ch"].split("|")
        return {"msgArray": [_msg(c.split("_")[1].split(".")[0]) for c in chans if c.startswith("tse_")]}

    calls = _install(monkeypatch, responder)
    out = tv.TwseMisQuoteVendor().fetch([Symbol.parse(c, "TW") for c in codes], {})
    assert len(calls) == 3
    assert all(len(_channels(c)) <= 20 for c in calls)
    # 同一档的 tse_/otc_ 通道必须在同一批
    for c in calls:
        chans = _channels(c)
        tse = {x[4:] for x in chans if x.startswith("tse_")}
        otc = {x[4:] for x in chans if x.startswith("otc_")}
        assert tse == otc
    assert sorted(q.symbol for q in out) == sorted(codes)


def test_one_failed_batch_does_not_drop_other_batches(monkeypatch):
    codes = [f"{1101 + i}" for i in range(25)]
    state = {"n": 0}

    def responder(params):
        state["n"] += 1
        if state["n"] == 2:
            return None  # 第二批失败(空 body / 网络错误时 market_get 回 None)
        chans = params["ex_ch"].split("|")
        return {"msgArray": [_msg(c.split("_")[1].split(".")[0]) for c in chans if c.startswith("tse_")]}

    _install(monkeypatch, responder)
    out = tv.TwseMisQuoteVendor().fetch([Symbol.parse(c, "TW") for c in codes], {})
    assert len(out) == 15  # 3 批里 2 批成功,每批 10 档 → 第 1 批 10 + 第 3 批 5


def test_response_without_msgarray_returns_empty(monkeypatch):
    _install(monkeypatch, lambda p: {"rtmessage": "Empty Query.", "rtcode": "5001"})
    assert tv.TwseMisQuoteVendor().fetch([Symbol.parse("2330", "TW")], {}) == []
