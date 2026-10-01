"""台股数据源(TWSE/TPEx/TDCC/Yahoo 奇摩/钜亨)。fixture 为 2026-09-30 真实响应切片。

所有台股 vendor 统一经 `marketdata.vendors.tw_bulk` 取数:
- `tw_bulk._download(url, params=None) -> str` 是唯一碰网络的函数(测试替换它)
- `tw_bulk.get_json(url, params=None)` / `tw_bulk.get_text(url, params=None)` 带进程内 TTL 缓存
  (同一 url+params 在 TTL 内只下载一次;全市场整包数据按代码取值)
- `tw_bulk.reset_cache()` 清缓存
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.symbol import Symbol
from marketdata.types import CapitalFlow, MarginItem, ShareholderItem
from marketdata.vendors import tw_bulk

FX = Path(__file__).parent / "fixtures" / "tw"

ROUTES = {
    "exchangeReport/BWIBBU_ALL": "twse_bwibbu.json",
    "tpex_mainboard_peratio_analysis": "tpex_peratio.json",
    "fund/T86": "twse_t86.json",
    "tpex_3insti_daily_trading": "tpex_3insti.json",
    "exchangeReport/MI_MARGN": "twse_margin.json",
    "tpex_mainboard_margin_balance": "tpex_margin.json",
    "opendata/t187ap45_L": "twse_dividend.json",
    "exchangeReport/TWT48U_ALL": "twse_exdividend.json",
    "getOD.ashx": "tdcc_dispersion.csv",
    "opendata/t187ap04_L": "twse_material_info.json",
    "mopsfin_t187ap04_O": "tpex_material_info.json",
    "announcement/notice": "twse_notice.json",
    "announcement/punish": "twse_punish.json",
    "tw.stock.yahoo.com/rss": "yahoo_rss_2330.xml",
    "newslist/category/tw_stock": "cnyes_tw_stock.json",
}


@pytest.fixture
def calls(monkeypatch):
    tw_bulk.reset_cache()
    log: list[tuple[str, dict | None]] = []

    def fake_download(url, params=None):
        log.append((url, params))
        for key, name in ROUTES.items():
            if key in url:
                return (FX / name).read_text(encoding="utf-8")
        raise AssertionError(f"未预期的请求: {url}")

    monkeypatch.setattr(tw_bulk, "_download", fake_download)
    yield log
    tw_bulk.reset_cache()


def _vendor(dtype, name):
    cls = VENDOR_CLASSES_BY_TYPE[dtype][name]
    assert "TW" in cls.supports_markets, f"{dtype}/{name} 未声明支持 TW"
    return cls()


def S(code):
    return Symbol.parse(code, "TW")


# ---------------------------------------------------------------- 注册


def test_registry_has_tw_vendors():
    expect = {
        "fundamentals": "twse", "capital_flow": "twse", "margin": "twse", "dividend": "twse",
        "events": "twse", "dragon_tiger": "twse", "shareholders": "tdcc",
        "news": "yahoo_tw", "flash_news": "cnyes",
    }
    for dtype, name in expect.items():
        assert name in VENDOR_CLASSES_BY_TYPE[dtype], f"{dtype} 缺 {name}"
        assert VENDOR_CLASSES_BY_TYPE[dtype][name].supports_markets == {"TW"}


def test_yfinance_quote_backs_up_tw():
    assert "TW" in VENDOR_CLASSES_BY_TYPE["quote"]["yfinance"].supports_markets


# ---------------------------------------------------------------- bulk 缓存


def test_bulk_cache_downloads_once(calls):
    v = _vendor("fundamentals", "twse")
    v.fetch([S("2330")], {})
    v.fetch([S("2330"), S("6488")], {})
    urls = [u for u, _ in calls if "BWIBBU_ALL" in u]
    assert len(urls) == 1


# ---------------------------------------------------------------- 基本面


def test_fundamentals_listed_and_otc(calls):
    out = {f.symbol: f for f in _vendor("fundamentals", "twse").fetch([S("2330"), S("6488")], {})}
    assert out["2330"].market == "TW"
    assert out["6488"].pe_ttm == 50.24
    assert out["6488"].dividend_yield == 0.74
    assert out["6488"].pb == 5.12
    tsmc = json.loads((FX / "twse_bwibbu.json").read_text(encoding="utf-8"))[0]
    assert out["2330"].pb == float(tsmc["PBratio"])
    assert out["2330"].dividend_yield == float(tsmc["DividendYield"])


def test_fundamentals_blank_pe_is_none_not_zero(calls, monkeypatch):
    rows = [{"Date": "1150930", "Code": "1101", "Name": "台泥", "PEratio": "", "DividendYield": "3.04", "PBratio": "0.85"}]
    monkeypatch.setitem(ROUTES, "exchangeReport/BWIBBU_ALL", "_blank.json")
    (FX / "_blank.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    try:
        f = _vendor("fundamentals", "twse").fetch([S("1101")], {})[0]
        assert f.pe_ttm is None and f.pb == 0.85
    finally:
        (FX / "_blank.json").unlink()


# ---------------------------------------------------------------- 三大法人


def test_capital_flow_listed_three_institutions(calls):
    cf = _vendor("capital_flow", "twse").fetch([S("2330")], {})[0]
    assert isinstance(cf, CapitalFlow)
    assert cf.symbol == "2330" and cf.name == "台積電"
    assert cf.foreign_net == 702_594
    assert cf.trust_net == 761_722
    assert cf.dealer_net == 399_899
    assert cf.institutional_net == 1_864_215
    assert cf.unit == "股"
    assert cf.trade_date == "2026-09-30"
    # 三大法人买卖超不是 A 股"主力资金净流入",不得混填
    assert cf.main_net_inflow is None


def test_capital_flow_otc(calls):
    cf = _vendor("capital_flow", "twse").fetch([S("6488")], {})[0]
    assert cf.foreign_net == 3_775_551
    assert cf.trust_net == -112_200
    assert cf.dealer_net == 89_552
    assert cf.institutional_net == 3_752_903


def test_t86_walks_back_to_last_trading_day(calls, monkeypatch):
    """当日盘后资料未出(或休市)时,T86 回「很抱歉」,要往前一天找,最多 7 天。"""
    real = tw_bulk._download
    tried = []

    def flaky(url, params=None):
        if "fund/T86" in url:
            tried.append(params["date"])
            if len(tried) < 3:
                return json.dumps({"stat": "很抱歉，沒有符合條件的資料!"})
        return real(url, params)

    monkeypatch.setattr(tw_bulk, "_download", flaky)
    out = _vendor("capital_flow", "twse").fetch([S("2330")], {})
    assert out and out[0].institutional_net == 1_864_215
    assert len(tried) == 3 and len(set(tried)) == 3
    assert all(len(d) == 8 and d.isdigit() for d in tried)


# ---------------------------------------------------------------- 融资融券


def test_margin_listed_in_lots(calls):
    m = {x.symbol: x for x in _vendor("margin", "twse").fetch([S("0050"), S("00679B")], {})}
    assert isinstance(m["0050"], MarginItem)
    assert m["0050"].rz_balance == 47977 and m["0050"].rq_balance == 653
    assert m["0050"].rz_buy == 500 and m["0050"].rq_sell_vol == 24
    assert m["0050"].unit == "張"
    assert m["00679B"].rz_balance == 4550 and m["00679B"].rq_balance == 4


# ---------------------------------------------------------------- 股利


def test_dividend_cash_and_stock(calls):
    items = [d for d in _vendor("dividend", "twse").fetch([S("2330")], {}) if d.symbol == "2330"]
    assert items
    q2 = [d for d in items if "第2季" in d.progress]
    assert q2 and q2[0].dividend_per_share == 7.0
    assert q2[0].bonus_ratio in (None, 0.0)
    assert "董事會決議" in q2[0].progress


def test_dividend_ex_date_from_preannouncement(calls):
    rows = json.loads((FX / "twse_exdividend.json").read_text(encoding="utf-8"))
    code = rows[0]["Code"]
    items = _vendor("dividend", "twse").fetch([S(code)], {})
    assert any(d.ex_date == "2026-10-08" for d in items)


# ---------------------------------------------------------------- 集保股权分散


def test_shareholders_from_tdcc(calls):
    sh = {x.symbol: x for x in _vendor("shareholders", "tdcc").fetch([S("2330")], {})}["2330"]
    assert isinstance(sh, ShareholderItem)
    assert sh.report_date == "2026-09-24"
    assert sh.holder_num == 3_020_649                          # 分级 17 合计
    assert abs(sh.big_holder_ratio - (1.09 + 0.92 + 0.75 + 84.77)) < 1e-6  # 分级 12–15(>400 张)
    assert sh.thousand_lot_ratio == 84.77                      # 分级 15(>1000 张)
    assert abs(sh.avg_shares - 25_932_370_067 / 3_020_649) < 1e-3


# ---------------------------------------------------------------- 重大讯息


def test_events_material_info(calls):
    evs = _vendor("events", "twse").fetch([S("6177"), S("4530")], {})
    by = {e.symbols[0]: e for e in evs}
    e = by["6177"]
    assert e.event_type == "material_info"
    assert e.title.startswith("代海外子公司")
    # 发言日期 1150930 发言时间 60706 = 台北 06:07:06 → UTC 前一日 22:07:06
    assert e.publish_time == datetime(2026, 9, 29, 22, 7, 6, tzinfo=timezone.utc)
    assert e.external_id and e.source
    assert "4530" in by  # 上柜重大讯息


def test_events_filters_by_symbols(calls):
    evs = _vendor("events", "twse").fetch([S("2330")], {})
    assert all("2330" in e.symbols for e in evs)


# ---------------------------------------------------------------- 注意股 / 处置股


def test_dragon_tiger_attention_and_disposition(calls):
    items = _vendor("dragon_tiger", "twse").fetch([], {"date": "2026-09-30"})
    codes = {i.symbol: i for i in items}
    assert "2330" in codes and "注意" in codes["2330"].reason
    assert codes["2330"].close == 2480.0
    assert "2455" in codes and "處置" in codes["2455"].reason
    # 权证(6 位非 00 开头)排除
    assert "086845" not in codes


def test_dragon_tiger_without_date_returns_empty(calls):
    assert _vendor("dragon_tiger", "twse").fetch([], {}) == []


# ---------------------------------------------------------------- 新闻 / 快讯


def test_news_yahoo_rss_per_stock(calls):
    arts = _vendor("news", "yahoo_tw").fetch([S("2330")], {})
    assert len(arts) >= 5
    a = arts[0]
    assert a.title and a.url.startswith("https://tw.stock.yahoo.com/")
    assert a.publish_time.tzinfo is not None
    assert a.symbols == ["2330"]
    url, params = next((u, p) for u, p in calls if "yahoo" in u)
    assert (params or {}).get("s") == "2330.TW" or "s=2330.TW" in url


def test_flash_news_cnyes(calls):
    items = _vendor("flash_news", "cnyes").fetch([], {})
    assert len(items) == 3
    it = items[0]
    assert it.title and it.url.startswith("https://news.cnyes.com/news/id/")
    assert it.publish_time.tzinfo is not None
    assert "&lt;" not in it.content and "<p>" not in it.content  # HTML 已清理
