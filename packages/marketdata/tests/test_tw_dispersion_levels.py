"""集保股權分散：vendor 需回傳完整 17 級分級表（levels），摘要欄位維持不變。"""

from __future__ import annotations

from pathlib import Path

import pytest

from marketdata.registry import VENDOR_CLASSES_BY_TYPE
from marketdata.symbol import Symbol
from marketdata.vendors import tw_bulk

FX = Path(__file__).parent / "fixtures" / "tw"


@pytest.fixture
def tdcc(monkeypatch):
    tw_bulk.reset_cache()
    monkeypatch.setattr(
        tw_bulk, "_download",
        lambda url, params=None: (FX / "tdcc_dispersion.csv").read_text(encoding="utf-8"),
    )
    yield VENDOR_CLASSES_BY_TYPE["shareholders"]["tdcc"]()
    tw_bulk.reset_cache()


def _item(vendor, code):
    return {x.symbol: x for x in vendor.fetch([Symbol.parse(code, "TW")], {})}[code]


def test_levels_has_all_17_rows_in_order(tdcc):
    levels = _item(tdcc, "2330").levels
    assert [row["level"] for row in levels] == list(range(1, 18))


def test_levels_row_values_match_csv(tdcc):
    by_level = {row["level"]: row for row in _item(tdcc, "2330").levels}
    assert by_level[1] == {"level": 1, "holders": 2_471_283, "shares": 288_915_271, "pct": 1.11}
    assert by_level[15] == {"level": 15, "holders": 1_487, "shares": 21_984_569_643, "pct": 84.77}
    assert by_level[17] == {"level": 17, "holders": 3_020_649, "shares": 25_932_370_067, "pct": 100.0}
    for row in by_level.values():
        assert isinstance(row["level"], int)
        assert isinstance(row["holders"], int)
        assert isinstance(row["shares"], int)
        assert isinstance(row["pct"], float)


def test_summary_fields_unchanged_and_levels_consistent(tdcc):
    item = _item(tdcc, "2330")
    assert item.report_date == "2026-09-24"
    assert item.holder_num == 3_020_649
    assert item.thousand_lot_ratio == 84.77
    pct_15 = {row["level"]: row["pct"] for row in item.levels}
    assert abs(item.big_holder_ratio - sum(pct_15[n] for n in (12, 13, 14, 15))) < 1e-6


def test_other_symbol_levels_are_not_mixed(tdcc):
    item = _item(tdcc, "6488")
    assert item.symbol == "6488"
    assert all(isinstance(row["level"], int) for row in item.levels)
    assert len({row["level"] for row in item.levels}) == len(item.levels)


def test_levels_sorted_even_when_csv_rows_arrive_shuffled(monkeypatch):
    lines = (FX / "tdcc_dispersion.csv").read_text(encoding="utf-8").splitlines()
    header, rows = lines[0], lines[1:]
    shuffled = "\n".join([header, *reversed(rows)])
    tw_bulk.reset_cache()
    monkeypatch.setattr(tw_bulk, "_download", lambda url, params=None: shuffled)
    vendor = VENDOR_CLASSES_BY_TYPE["shareholders"]["tdcc"]()
    levels = _item(vendor, "2330").levels
    tw_bulk.reset_cache()
    assert [row["level"] for row in levels] == list(range(1, 18))
