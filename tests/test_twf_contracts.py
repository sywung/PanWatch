"""F2:期货商品清单、个股期货↔股票代码对照、连续代码 → 近月合约。

资料来源(2026-10-01 实测):
- 指数期货(静态表):mis 代码 TXF/MXF/TMF/EXF/FXF 对 openapi/FinMind 代码 TX/MTX/TMF/TE/TF。
- 个股期货:openapi `SSFLists`(Contract↔StockCode,约 320 档)+ 保证金表
  `SingleStockFuturesMargining`/`SingleStockFuturesETFMargining` 的 ContractName(含「小型」)。
  调整型契约(CM1、DC1…)不在 SSFLists,自然排除。
- 合约月份码:A–L = 1–12 月 + 年尾数(2026-10 → J6);mis 代号 `{code}{月码}-F` 日盘、`-M` 夜盘、`{code}-S` 现货。
- 近月:当月结算日(futures_settlement_date)13:30 到期合约最后交易,之后(含当晚夜盘)换下月。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.platform.marketdata import futures as fu
from src.platform.scheduling import trading_calendar as tc

TPE = ZoneInfo("Asia/Taipei")
FX = Path(__file__).parent / "fixtures"
_SSF = json.loads((FX / "taifex/ssf_lists.json").read_text(encoding="utf-8"))
_MARGIN = json.loads((FX / "taifex/ssf_margining.json").read_text(encoding="utf-8"))
_ETF_MARGIN = json.loads((FX / "taifex/ssf_etf_margining.json").read_text(encoding="utf-8"))
_HOLIDAYS = json.loads((FX / "twse_holidays_2026.json").read_text(encoding="utf-8"))


def _tpe(y, m, d, hh=10, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TPE)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    tc.reset_cache()
    monkeypatch.setattr(tc, "_fetch_tw_holidays_raw", lambda: _HOLIDAYS)
    assert tc.refresh_tw_blocking() is True
    monkeypatch.setattr(fu, "CACHE_FILE", tmp_path / "futures_list_cache.json")
    fu.reset_cache()
    yield
    fu.reset_cache()
    tc.reset_cache()


@pytest.fixture
def online(monkeypatch):
    calls = {"n": 0}

    def ssf():
        calls["n"] += 1
        return _SSF

    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", ssf)
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", lambda: _MARGIN + _ETF_MARGIN)
    return calls


@pytest.fixture
def offline(monkeypatch):
    def boom():
        raise OSError("network down")

    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", boom)
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", boom)


# ---------------------------------------------------------------- 月份码


@pytest.mark.parametrize(
    "year, month, code",
    [(2026, 10, "J6"), (2026, 1, "A6"), (2026, 12, "L6"), (2027, 1, "A7"), (2030, 3, "C0")],
)
def test_contract_month_code(year, month, code):
    assert fu.contract_month_code(year, month) == code


# ---------------------------------------------------------------- 近月


@pytest.mark.parametrize(
    "now, expected",
    [
        (_tpe(2026, 10, 1), (2026, 10)),
        (_tpe(2026, 10, 3, 3, 0), (2026, 10)),          # 周六凌晨(周五夜盘)
        (_tpe(2026, 10, 21, 13, 29), (2026, 10)),       # 结算日 13:30 前仍是到期月
        (_tpe(2026, 10, 21, 13, 30), (2026, 11)),
        (_tpe(2026, 10, 21, 20, 0), (2026, 11)),        # 结算日当晚夜盘交易的是下月
        (_tpe(2026, 10, 22, 3, 0), (2026, 11)),
        (_tpe(2026, 2, 18), (2026, 2)),                 # 第三个周三在春节,结算顺延到 2/23
        (_tpe(2026, 2, 23, 13, 29), (2026, 2)),
        (_tpe(2026, 2, 23, 13, 30), (2026, 3)),
        (_tpe(2026, 12, 16, 14, 0), (2027, 1)),         # 跨年
        (datetime(2026, 10, 21, 5, 30, tzinfo=timezone.utc), (2026, 11)),  # = 台北 13:30
    ],
)
def test_near_month(now, expected):
    assert fu.near_month(now) == expected


# ---------------------------------------------------------------- 商品清单


def test_index_futures_are_static_and_mapped():
    by = {p.code: p for p in fu.INDEX_FUTURES}
    assert list(by) == ["TXF", "MXF", "TMF", "EXF", "FXF"]
    assert {c: p.openapi_code for c, p in by.items()} == {
        "TXF": "TX", "MXF": "MTX", "TMF": "TMF", "EXF": "TE", "FXF": "TF",
    }
    assert by["TXF"].name == "台指期" and by["MXF"].name == "小台指" and by["TMF"].name == "微台指"
    assert all(p.kind == "index" and p.underlying_code is None and not p.is_mini for p in by.values())


def test_parse_stock_futures_from_real_rows():
    products = {p.code: p for p in fu.parse_stock_futures(_SSF, _MARGIN + _ETF_MARGIN)}
    assert set(products) == {"CDF", "QFF", "NYF", "SRF", "CAF", "RZF", "MYF"}
    cdf, qff = products["CDF"], products["QFF"]
    assert (cdf.name, cdf.underlying_code, cdf.is_mini, cdf.kind) == ("台積電期貨", "2330", False, "stock")
    assert (qff.name, qff.underlying_code, qff.is_mini) == ("小型台積電期貨", "2330", True)
    assert products["SRF"].is_mini and products["SRF"].underlying_code == "0050"
    assert products["RZF"].underlying_code == "00679B"
    assert products["MYF"].underlying_code == "1565"     # 上柜标的
    assert all(p.openapi_code == p.code for p in products.values())


def test_parse_stock_futures_name_fallback_and_bad_rows():
    rows = _SSF + [
        {"Contract": "bad code", "StockCode": "9999", "StockName": "壞資料", "Type": ""},
        {"Contract": "ZZF", "StockCode": "", "StockName": "缺代碼", "Type": ""},
        "garbage",
    ]
    products = {p.code: p for p in fu.parse_stock_futures(rows, [])}  # 保证金表抓不到
    assert products["CDF"].name == "台積電期貨"                      # StockName + 期貨
    assert set(products) == {"CDF", "QFF", "NYF", "SRF", "CAF", "RZF", "MYF"}


def test_get_futures_products_combines_index_and_stock(online):
    codes = [p.code for p in fu.get_futures_products()]
    assert codes[:5] == ["TXF", "MXF", "TMF", "EXF", "FXF"]
    assert {"CDF", "QFF", "MYF"} <= set(codes)
    assert len(codes) == len(set(codes))


def test_product_lookup(online):
    assert fu.get_futures_product("CDF").underlying_code == "2330"
    assert fu.get_futures_product("TXF").openapi_code == "TX"
    assert fu.get_futures_product("cdf") is None          # 代码区分大小写,由调用端正规化
    assert fu.get_futures_product("ZZZ") is None


def test_futures_for_stock_standard_first(online):
    assert [p.code for p in fu.futures_for_stock("2330")] == ["CDF", "QFF"]
    assert [p.code for p in fu.futures_for_stock("0050")] == ["NYF", "SRF"]
    assert fu.futures_for_stock("2454") == []


# ---------------------------------------------------------------- 缓存与离线


def test_list_is_cached_in_memory_and_on_disk(online):
    fu.get_futures_products()
    fu.get_futures_products()
    assert online["n"] == 1
    assert fu.CACHE_FILE.exists()


def test_disk_cache_survives_restart_when_offline(online, monkeypatch):
    fu.get_futures_products()
    fu.reset_cache()  # 模拟重启:内存清空,磁盘缓存还在

    def boom():
        raise OSError("network down")

    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", boom)
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", boom)
    assert fu.get_futures_product("CDF").underlying_code == "2330"


def test_stale_cache_is_used_when_refresh_fails(online, monkeypatch):
    fu.get_futures_products()
    fu.reset_cache()
    data = json.loads(fu.CACHE_FILE.read_text(encoding="utf-8"))
    data["timestamp"] -= fu.CACHE_TTL + 60
    fu.CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def boom():
        raise OSError("network down")

    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", boom)
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", boom)
    assert fu.get_futures_product("CDF") is not None   # 过期但能用,胜过没有


def test_offline_without_cache_still_has_index_futures(offline):
    codes = [p.code for p in fu.get_futures_products()]
    assert codes == ["TXF", "MXF", "TMF", "EXF", "FXF"]
    assert not fu.CACHE_FILE.exists()   # 残缺清单不能写进磁盘缓存


def test_margin_failure_still_lists_stock_futures(online, monkeypatch):
    def boom():
        raise OSError("margin endpoint down")

    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", boom)
    assert fu.get_futures_product("QFF").name == "台積電期貨"   # 没有保证金表就用 StockName 回退


def test_empty_ssf_list_is_not_cached(monkeypatch):
    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", lambda: [])
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", lambda: [])
    assert [p.code for p in fu.get_futures_products()] == ["TXF", "MXF", "TMF", "EXF", "FXF"]
    assert not fu.CACHE_FILE.exists()


# ---------------------------------------------------------------- 连续代码 → 合约


def test_resolve_index_contract(online):
    c = fu.resolve_contract("TXF", _tpe(2026, 10, 1))
    assert (c.product.code, c.year, c.month) == ("TXF", 2026, 10)
    assert c.symbol == "TXFJ6"
    assert c.contract_month == "202610"          # openapi / FinMind 的 contract_date 格式
    assert c.mis_id() == "TXFJ6-F"
    assert c.mis_id(night=True) == "TXFJ6-M"


def test_resolve_rolls_after_settlement(online):
    assert fu.resolve_contract("MXF", _tpe(2026, 10, 21, 15, 0)).symbol == "MXFK6"
    assert fu.resolve_contract("CDF", _tpe(2026, 12, 16, 14, 0)).symbol == "CDFA7"


def test_resolve_stock_contract(online):
    c = fu.resolve_contract("QFF", _tpe(2026, 10, 1))
    assert c.symbol == "QFFJ6" and c.product.underlying_code == "2330"


def test_resolve_unknown_returns_none(online):
    assert fu.resolve_contract("ZZZ", _tpe(2026, 10, 1)) is None


def test_spot_mis_id():
    assert fu.spot_mis_id("TXF") == "TXF-S"
    assert fu.spot_mis_id("CDF") == "CDF-S"


# ---------------------------------------------------------------- 失败退避


def test_failed_refresh_backs_off(monkeypatch):
    # 抓不到时不能每次查询都重打网络(每次可能卡 30 秒);退避期内沿用上次结果
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise OSError("network down")

    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", boom)
    monkeypatch.setattr(fu, "_fetch_ssf_margin_raw", boom)
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(fu.time, "time", lambda: clock["t"])

    for _ in range(3):
        assert fu.get_futures_product("TXF") is not None
        assert fu.get_futures_product("CDF") is None
    assert calls["n"] == 1

    clock["t"] += fu.FAILURE_RETRY_SEC + 1
    fu.get_futures_products()
    assert calls["n"] == 2


def test_backoff_keeps_stale_disk_cache(online, monkeypatch):
    fu.get_futures_products()
    fu.reset_cache()
    data = json.loads(fu.CACHE_FILE.read_text(encoding="utf-8"))
    data["timestamp"] -= fu.CACHE_TTL + 60
    fu.CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise OSError("network down")

    monkeypatch.setattr(fu, "_fetch_ssf_lists_raw", boom)
    for _ in range(3):
        assert fu.get_futures_product("CDF") is not None
    assert calls["n"] == 1
