"""缠论分析(M11a):vendored chan.py + 日线/30 分线 + 区间套 + 摘要/AI/API 接入。

fixture 为 2330 真实 K 线(2025-10-01 ~ 2026-10-01 日线、近 60 天 30 分线),
期望值是 chan.py(commit 429d6ed,CChanConfig 预设值 + trigger_step)在这份资料上的输出。
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests/fixtures/chan"
DAY = json.loads((FX / "2330_day.json").read_text())
M30 = json.loads((FX / "2330_30m.json").read_text())


# ---------------------------------------------------------------- vendored 库


def test_vendored_chan_py_has_license_and_provenance():
    base = ROOT / "packages/chan_py"
    assert (base / "LICENSE").read_text().startswith("MIT License")
    vendor = (base / "VENDOR.md").read_text(encoding="utf-8")
    assert "Vespa314/chan.py" in vendor and "429d6ed" in vendor
    for unwanted in ("DataAPI", "Plot", "Debug", "Script", "App", "ChanModel"):
        assert not (base / unwanted).exists(), f"不该带入 {unwanted}"


def test_analysis_does_not_pull_heavy_deps():
    from src.modules.market.chan_analysis import analyze_level

    analyze_level(DAY, "day")
    for mod in ("matplotlib", "akshare", "baostock", "xgboost", "ccxt"):
        assert mod not in sys.modules, mod


# ---------------------------------------------------------------- 单级别


def test_day_level_structure():
    from src.modules.market.chan_analysis import analyze_level

    r = analyze_level(DAY, "day")
    assert r["level"] == "day"
    assert len(r["bi"]) == 15 and len(r["seg"]) == 3 and len(r["zs"]) == 1
    zs = r["zs"][-1]
    assert (zs["begin_time"], zs["end_time"], zs["zd"], zs["zg"]) == ("2026-05-07", "2026-06-11", 2210.0, 2345.0)
    last = r["bi"][-1]
    assert last == {"begin_time": "2026-08-19", "begin_val": 2335.0, "end_time": "2026-09-30",
                    "end_val": 2510.0, "dir": "up", "sure": False}
    assert [(p["time"], p["is_buy"], p["type"], p["sure"]) for p in r["bsp"]] == [
        ("2026-06-23", False, "1", True),
        ("2026-08-13", False, "2", True),
        ("2026-09-30", False, "2s", False),
    ]
    assert r["bsp"][-1]["price"] == 2480.0
    assert r["last_close"] == 2500.0
    assert r["position"] == "above"   # 2500 > ZG 2345


def test_30m_level_structure():
    from src.modules.market.chan_analysis import analyze_level

    r = analyze_level(M30, "30m")
    assert len(r["bi"]) == 15 and len(r["zs"]) == 2 and len(r["bsp"]) == 6
    assert (r["zs"][-1]["zd"], r["zs"][-1]["zg"]) == (2335.0, 2425.0)
    assert r["zs"][-1]["begin_time"] == "2026-07-31 13:00"
    last = r["bsp"][-1]
    assert (last["time"], last["is_buy"], last["type"], last["sure"], last["price"]) == (
        "2026-09-30 10:00", False, "1", True, 2505.0)
    assert r["bi"][-1]["dir"] == "up" and r["bi"][-1]["sure"] is True


def test_seg_entries_have_direction():
    from src.modules.market.chan_analysis import analyze_level

    r = analyze_level(DAY, "day")
    assert all(s["dir"] in ("up", "down") for s in r["seg"])
    assert set(r["seg"][0]) >= {"begin_time", "begin_val", "end_time", "end_val", "dir", "sure"}


def test_too_few_bars_returns_none():
    from src.modules.market.chan_analysis import analyze_level

    assert analyze_level(DAY[:5], "day") is None
    assert analyze_level([], "30m") is None


def test_accepts_kline_objects():
    from src.modules.market.chan_analysis import analyze_level
    from src.platform.marketdata.collectors.kline_collector import KlineData

    objs = [KlineData(date=r["date"], open=r["open"], close=r["close"], high=r["high"],
                      low=r["low"], volume=r["volume"]) for r in DAY]
    assert len(analyze_level(objs, "day")["bi"]) == 15


def test_position_inside_and_below():
    from src.modules.market.chan_analysis import position_vs_zs

    zs = [{"zd": 100.0, "zg": 110.0}]
    assert position_vs_zs(105.0, zs) == "inside"
    assert position_vs_zs(99.0, zs) == "below"
    assert position_vs_zs(111.0, zs) == "above"
    assert position_vs_zs(105.0, []) == "none"


# ---------------------------------------------------------------- 区间套


def _bsp(time, is_buy, sure=True, typ="1"):
    return {"time": time, "is_buy": is_buy, "type": typ, "sure": sure, "price": 1.0}


def test_interval_nesting_confirms_same_direction_after_day_bsp():
    from src.modules.market.chan_analysis import interval_nesting

    day = {"bsp": [_bsp("2026-09-30", False, sure=False, typ="2s")]}
    m30 = {"bsp": [_bsp("2026-09-29 13:00", True), _bsp("2026-09-30 10:00", False)]}
    n = interval_nesting(day, m30, since_date="2026-09-17")
    assert n["confirmed"] is True and n["direction"] == "sell"
    assert n["day_bsp"]["time"] == "2026-09-30" and n["m30_bsp"]["time"] == "2026-09-30 10:00"


def test_interval_nesting_requires_same_direction():
    from src.modules.market.chan_analysis import interval_nesting

    day = {"bsp": [_bsp("2026-09-30", True)]}
    m30 = {"bsp": [_bsp("2026-09-30 10:00", False)]}
    assert interval_nesting(day, m30, since_date="2026-09-17")["confirmed"] is False


def test_interval_nesting_requires_recent_day_bsp():
    from src.modules.market.chan_analysis import interval_nesting

    day = {"bsp": [_bsp("2026-08-13", False)]}
    m30 = {"bsp": [_bsp("2026-09-30 10:00", False)]}
    assert interval_nesting(day, m30, since_date="2026-09-17")["confirmed"] is False


def test_interval_nesting_requires_unsure_m30_excluded():
    from src.modules.market.chan_analysis import interval_nesting

    day = {"bsp": [_bsp("2026-09-30", False)]}
    m30 = {"bsp": [_bsp("2026-09-30 10:00", False, sure=False)]}
    assert interval_nesting(day, m30, since_date="2026-09-17")["confirmed"] is False


def test_interval_nesting_without_m30():
    from src.modules.market.chan_analysis import interval_nesting

    assert interval_nesting({"bsp": []}, None, since_date="2026-09-17")["confirmed"] is False


def test_analyze_chan_end_to_end_on_2330():
    from src.modules.market.chan_analysis import analyze_chan

    r = analyze_chan(DAY, M30)
    assert r["day"]["position"] == "above"
    assert r["m30"]["zs"][-1]["zg"] == 2425.0
    assert r["nesting"]["confirmed"] is True and r["nesting"]["direction"] == "sell"


def test_analyze_chan_without_intraday():
    from src.modules.market.chan_analysis import analyze_chan

    r = analyze_chan(DAY, [])
    assert r["m30"] is None and r["nesting"]["confirmed"] is False
    assert r["day"] is not None


# ---------------------------------------------------------------- 文字


def test_format_summary_zh_tw():
    from src.modules.market.chan_analysis import analyze_chan, format_chan_summary

    text = format_chan_summary(analyze_chan(DAY, M30), "zh-TW")
    assert "纏論" in text and "中樞" in text and "2210" in text and "2345" in text
    assert "區間套" in text
    assert "缠" not in text and "枢" not in text


def test_format_summary_en():
    from src.modules.market.chan_analysis import analyze_chan, format_chan_summary

    text = format_chan_summary(analyze_chan(DAY, M30), "en-US")
    assert "Chan" in text and "pivot" in text.lower()
    assert not any("一" <= ch <= "鿿" for ch in text)


def test_format_summary_handles_none():
    from src.modules.market.chan_analysis import format_chan_summary

    assert format_chan_summary(None, "zh-TW") == ""
    assert format_chan_summary({"day": None, "m30": None, "nesting": {"confirmed": False}}, "zh-TW") == ""


# ---------------------------------------------------------------- 30 分 K 来源


def test_intraday_klines_from_yahoo(monkeypatch):
    import marketdata.vendors.kline as kv
    from marketdata import MarketData, StaticConfigProvider

    kv._TW_SUFFIX_HINT.clear()
    seen = []

    real_sig = inspect.signature(kv.market_get)

    def fake_get(url, **kwargs):
        # 呼叫必须符合真实 market_get 的签名(曾漏传必填的 host_key 而测试照过)
        real_sig.bind(url, **kwargs)
        params = kwargs.get("params")
        seen.append((url.rsplit("/", 1)[1], params))
        if url.endswith("/6488.TW"):
            return None
        q = {"open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0], "close": [1.5, 2.5], "volume": [10, 20]}
        # 2026-09-30 01:00Z / 01:30Z = 台北 09:00 / 09:30
        return {"chart": {"result": [{"timestamp": [1790730000, 1790731800], "indicators": {"quote": [q]}}]}}

    monkeypatch.setattr(kv, "market_get", fake_get)
    bars = MarketData(config=StaticConfigProvider({})).intraday_klines("6488", market="TW", interval="30m")
    assert [b.date for b in bars] == ["2026-09-30 09:00", "2026-09-30 09:30"]
    assert bars[-1].close == 2.5
    assert [s for s, _ in seen] == ["6488.TW", "6488.TWO"]
    assert seen[-1][1]["interval"] == "30m" and seen[-1][1]["range"] == "60d"
    kv._TW_SUFFIX_HINT.clear()


# ---------------------------------------------------------------- 接入:摘要 / API / Agent


@pytest.fixture
def chan_inputs(monkeypatch):
    from marketdata import Bar
    from src.platform.marketdata.collectors import kline_collector as kc

    day_objs = [kc.KlineData(date=r["date"], open=r["open"], close=r["close"], high=r["high"],
                             low=r["low"], volume=r["volume"]) for r in DAY]
    monkeypatch.setattr(kc.KlineCollector, "get_klines", lambda self, symbol, days=60: day_objs[-days:])

    class _MD:
        def intraday_klines(self, symbol, *, market, interval="30m"):
            return [Bar(date=r["date"], open=r["open"], close=r["close"], high=r["high"],
                        low=r["low"], volume=r["volume"]) for r in M30]

    monkeypatch.setattr(kc, "get_market_data", lambda: _MD())
    return kc


def test_kline_summary_includes_chan(chan_inputs):
    from src.platform.marketdata.models import MarketCode

    s = chan_inputs.KlineCollector(MarketCode.TW).get_kline_summary("2330")
    assert s["chan"]["day"]["zs"][-1]["zg"] == 2345.0
    assert s["chan"]["nesting"]["direction"] == "sell"


def test_kline_summary_chan_failure_is_soft(chan_inputs, monkeypatch):
    from src.modules.market import chan_analysis
    from src.platform.marketdata.models import MarketCode

    def boom(*a, **k):
        raise RuntimeError("chan broke")

    monkeypatch.setattr(chan_analysis, "analyze_chan", boom)
    s = chan_inputs.KlineCollector(MarketCode.TW).get_kline_summary("2330")
    assert s.get("chan") is None
    assert "ma" in str(s).lower() or s  # 其他技术指标照常


def test_chan_api_endpoint(chan_inputs):
    from src.modules.market.api import klines

    out = klines.get_kline_chan("2330", market="TW", level="day")
    data = out.get("data", out) if isinstance(out, dict) and "data" in out else out
    assert data["level"] == "day" and len(data["bi"]) == 15
    out30 = klines.get_kline_chan("2330", market="TW", level="30m")
    data30 = out30.get("data", out30) if isinstance(out30, dict) and "data" in out30 else out30
    assert data30["level"] == "30m" and len(data30["zs"]) == 2


def test_agents_put_chan_into_prompt_context():
    for rel in ("src/modules/automation/daily_report.py",
                "src/modules/automation/premarket_outlook.py",
                "src/modules/automation/intraday_monitor.py"):
        assert "format_chan_summary" in (ROOT / rel).read_text(encoding="utf-8"), rel
    for rel in ("prompts/daily_report.txt", "prompts/premarket_outlook.txt", "prompts/intraday_monitor.txt"):
        assert "缠论" in (ROOT / rel).read_text(encoding="utf-8"), rel


# ---------------------------------------------------------------- 真实资料踩到的坑


def test_yahoo_adjclose_scales_ohlc_consistently(monkeypatch):
    """Yahoo 还原权息只给 adjclose;只换收盘会出现 收盘 < 最低(2330 实际 1308.9 < 1325)。"""
    import marketdata.vendors.kline as kv
    from marketdata.symbol import Symbol

    kv._TW_SUFFIX_HINT.clear()
    q = {"open": [1325.0], "high": [1350.0], "low": [1325.0], "close": [1335.0], "volume": [1]}
    payload = {"chart": {"result": [{"timestamp": [1790730000], "indicators": {
        "quote": [q], "adjclose": [{"adjclose": [1308.9478759765625]}]}}]}}
    monkeypatch.setattr(kv, "market_get", lambda url, **k: payload)
    bar = kv.YahooKlineVendor().fetch([Symbol.parse("2330", "TW")], {"days": 10})[0]
    assert abs(bar.close - 1308.9478759765625) < 1e-9
    assert bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high
    assert abs(bar.low / bar.close - 1325.0 / 1335.0) < 1e-9
    kv._TW_SUFFIX_HINT.clear()


def test_analyze_level_tolerates_inconsistent_bars():
    from src.modules.market.chan_analysis import analyze_level

    bad = [dict(r) for r in DAY]
    bad[0]["close"] = bad[0]["low"] - 15  # 收盘低于最低
    assert analyze_level(bad, "day") is not None


def test_summary_position_is_localized():
    from src.modules.market.chan_analysis import analyze_chan, format_chan_summary

    r = analyze_chan(DAY, M30)
    zh = format_chan_summary(r, "zh-TW")
    assert "中樞上方" in zh and "above" not in zh and "日線" in zh
    en = format_chan_summary(r, "en-US")
    assert "price above pivot" in en
