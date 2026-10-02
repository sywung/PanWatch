"""Phase 2b B1:期货持仓的领域逻辑、保证金读取、资料表与迁移。

设计见 vault projects/panwatch/phase2-plan.md「Phase 2b」。要点:
- 契约乘数存在持仓上;依商品给预设值(SSFLists 没有乘数栏位)
- 损益 = (现价 − 成交价) × 乘数 × 口数,空单取负号
- 保证金:个股期为比率、ETF 期与指数期为固定金额(指数期以中文名称对应)
- 权益数 = 原始保证金占用 + 未实现损益;低于维持保证金 → 追缴
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from src.modules.portfolio import futures_positions as fp
from src.platform.marketdata import futures_margin as fm
from src.platform.marketdata.futures import FuturesProduct

FX = Path(__file__).parent / "fixtures" / "taifex"
INDEX_ROWS = json.loads((FX / "margin_index_20261001.json").read_text(encoding="utf-8"))
SSF_ROWS = json.loads((FX / "margin_ssf_20261001.json").read_text(encoding="utf-8"))
ETF_ROWS = json.loads((FX / "margin_etf_20261001.json").read_text(encoding="utf-8"))


def _product(code, name, kind="stock", underlying="2330", mini=False):
    return FuturesProduct(code, name, kind, code, underlying if kind == "stock" else None, mini)


# ============================================================
# 1. 预设契约乘数
# ============================================================

@pytest.mark.parametrize("code,expected", [
    ("TXF", 200), ("MXF", 50), ("TMF", 10), ("EXF", 4000), ("FXF", 1000),
])
def test_default_multiplier_index_futures(code, expected):
    assert fp.default_multiplier(_product(code, code, kind="index")) == expected


def test_default_multiplier_stock_futures():
    """个股期 2000 股、小型 100 股。"""
    assert fp.default_multiplier(_product("CDF", "台積電期貨")) == 2000
    assert fp.default_multiplier(_product("QFF", "小型台積電期貨", mini=True)) == 100


def test_default_multiplier_etf_futures():
    """ETF 期(标的代码 00 开头)10000 单位、小型 1000。"""
    assert fp.default_multiplier(_product("NYF", "元大台灣50ETF期貨", underlying="0050")) == 10000
    assert fp.default_multiplier(_product("SRF", "小型元大台灣50ETF期貨", underlying="0050", mini=True)) == 1000


# ============================================================
# 2. 未实现损益
# ============================================================

def test_long_pnl():
    """多单:台积电期 2500 买 2 口,现价 2520 → (20)×2000×2 = 80,000。"""
    assert fp.unrealized_pnl("long", 2500, 2520, 2, 2000) == 80_000


def test_short_pnl():
    """空单:小台 48800 卖 1 口,现价 48770 → 30×50 = 1,500。"""
    assert fp.unrealized_pnl("short", 48800, 48770, 1, 50) == 1_500


def test_pnl_without_price_is_none():
    assert fp.unrealized_pnl("long", 2500, None, 1, 2000) is None


def test_invalid_direction_rejected():
    with pytest.raises(ValueError):
        fp.unrealized_pnl("buy", 1, 2, 1, 1)


# ============================================================
# 3. 保证金解析
# ============================================================

def test_parse_index_margin_by_chinese_name():
    """指数期以中文名称对应到商品代码。"""
    margins = fm.parse_margins(INDEX_ROWS, [], [])
    assert margins["TXF"] == fm.Margin(kind="fixed", initial=701000, maintenance=538000)
    assert margins["MXF"] == fm.Margin(kind="fixed", initial=175250, maintenance=134500)
    assert margins["TMF"] == fm.Margin(kind="fixed", initial=35050, maintenance=26900)
    assert margins["EXF"].initial == 978000
    assert margins["FXF"].initial == 158000


def test_parse_stock_futures_margin_rates():
    """个股期是比率:13.50% → 0.135。"""
    margins = fm.parse_margins([], SSF_ROWS, [])
    assert margins["CDF"] == fm.Margin(kind="rate", initial=pytest.approx(0.135), maintenance=pytest.approx(0.1035))
    assert margins["QFF"].kind == "rate"


def test_parse_etf_margin_fixed_and_dedup():
    """ETF 期是固定金额;同合约重复列只取一份。"""
    margins = fm.parse_margins([], [], ETF_ROWS + ETF_ROWS[:1])
    assert margins["NYF"] == fm.Margin(kind="fixed", initial=87000, maintenance=67000)
    assert margins["SRF"] == fm.Margin(kind="fixed", initial=8700, maintenance=6700)


def test_parse_ignores_malformed_rows():
    margins = fm.parse_margins([{"Contract": "臺股期貨", "InitialMargin": "-"}, "x", None],
                               [{"Contract": "CDF", "InitialMarginRate": ""}], [{}])
    assert margins == {}


# ============================================================
# 4. 每口保证金与仓位指标
# ============================================================

def test_margin_per_lot_rate_uses_price_and_multiplier():
    """个股期:13.5% × 2520 × 2000 = 680,400;维持 10.35% → 521,640。"""
    m = fm.Margin(kind="rate", initial=0.135, maintenance=0.1035)
    initial, maintenance = fm.margin_per_lot(m, price=2520, multiplier=2000)
    assert initial == pytest.approx(680_400)
    assert maintenance == pytest.approx(521_640)


def test_margin_per_lot_fixed_ignores_price():
    m = fm.Margin(kind="fixed", initial=701000, maintenance=538000)
    assert fm.margin_per_lot(m, price=48770, multiplier=200) == (701000, 538000)


def test_position_metrics_and_margin_call():
    """权益数 = 占用 + 损益;低于维持保证金 → margin_call。"""
    m = fm.Margin(kind="fixed", initial=701000, maintenance=538000)
    ok = fp.position_metrics("long", entry_price=48000, current_price=48770, lots=1,
                             multiplier=200, margin=m)
    assert ok["unrealized_pnl"] == 154_000
    assert ok["margin_used"] == 701_000
    assert ok["maintenance_required"] == 538_000
    assert ok["equity"] == 855_000
    assert ok["margin_call"] is False

    # 跌 900 点:损益 −180,000 → 权益 521,000 < 538,000
    bad = fp.position_metrics("long", entry_price=48000, current_price=47100, lots=1,
                              multiplier=200, margin=m)
    assert bad["equity"] == 521_000
    assert bad["margin_call"] is True


def test_position_metrics_without_margin_or_price():
    """没有保证金资料或没有现价:相关栏位为 None,不报错。"""
    out = fp.position_metrics("long", entry_price=2500, current_price=None, lots=1,
                              multiplier=2000, margin=None)
    assert out["unrealized_pnl"] is None
    assert out["margin_used"] is None
    assert out["margin_call"] is None


# ============================================================
# 5. 保证金读取:每日缓存、失败沿用
# ============================================================

@pytest.fixture
def margin_env(monkeypatch, tmp_path):
    monkeypatch.setattr(fm, "CACHE_FILE", tmp_path / "futures_margin_cache.json")
    fm.reset_cache()
    calls = {"n": 0}

    def fetch_all():
        calls["n"] += 1
        return INDEX_ROWS, SSF_ROWS, ETF_ROWS

    monkeypatch.setattr(fm, "_fetch_all_raw", fetch_all)
    yield calls
    fm.reset_cache()


def test_get_margin_caches_within_ttl(margin_env):
    assert fm.get_margin("TXF").initial == 701000
    assert fm.get_margin("CDF").kind == "rate"
    assert margin_env["n"] == 1


def test_get_margin_falls_back_to_stale_cache_on_failure(margin_env, monkeypatch):
    fm.get_margin("TXF")
    fm.reset_cache(memory_only=True)
    data = json.loads(fm.CACHE_FILE.read_text(encoding="utf-8"))
    data["ts"] -= fm.CACHE_TTL + 60
    fm.CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")

    def boom():
        raise RuntimeError("openapi down")

    monkeypatch.setattr(fm, "_fetch_all_raw", boom)
    assert fm.get_margin("TXF").initial == 701000


def test_get_margin_unknown_code_is_none(margin_env):
    assert fm.get_margin("ZZZ") is None


# ============================================================
# 6. 资料表与迁移
# ============================================================

def test_futures_position_model_columns():
    import src.platform.persistence.models  # noqa: F401
    from src.platform.persistence.database import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("futures_positions")}
    assert {"id", "account_id", "product_code", "contract_month", "direction", "lots",
            "entry_price", "multiplier", "note", "created_at", "updated_at"} <= cols


def test_migration_9002_creates_table_idempotently():
    from src.platform.persistence import migrations as mig

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)"))
    step = next(m for m in mig.MIGRATIONS if m.name == "futures_positions")
    assert step.version >= 9000
    with engine.begin() as conn:
        step.runner(conn)
        step.runner(conn)  # 可重复执行
    cols = {c["name"] for c in inspect(engine).get_columns("futures_positions")}
    assert {"account_id", "product_code", "contract_month", "direction", "lots",
            "entry_price", "multiplier"} <= cols
