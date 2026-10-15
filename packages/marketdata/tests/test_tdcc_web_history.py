"""集保官網「股權分散表」查詢頁：一次可回補最近 51～52 週的單檔歷史（無驗證碼）。

fixture 為 2026-10-15 真實頁面：
- tdcc_web_form.html          GET 頁，含 scaDate 週別下拉與一次性 SYNCHRONIZER_TOKEN
- tdcc_web_2330_20260924.html POST 結果頁（2330，115年09月24日，與開放資料 CSV 同值）
- tdcc_web_unknown.html       查無此資料

網路只經 `tdcc_web._http(method, url, data=None) -> str`，測試替換它。
token 是一次性的：每個回應附新 token，拿舊 token 送出只會回表單頁。
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from marketdata.vendors import tdcc_web

FX = Path(__file__).parent / "fixtures" / "tw"
FORM = (FX / "tdcc_web_form.html").read_text(encoding="utf-8")
RESULT = (FX / "tdcc_web_2330_20260924.html").read_text(encoding="utf-8")
UNKNOWN = (FX / "tdcc_web_unknown.html").read_text(encoding="utf-8")
_TOKEN = re.compile(r'(name="SYNCHRONIZER_TOKEN"[^>]*value=")[^"]*(")')


def _with_token(html: str, token: str) -> str:
    return _TOKEN.sub(lambda m: m.group(1) + token + m.group(2), html, count=1)


def _with_date(html: str, yyyymmdd: str) -> str:
    """把結果頁的「資料日期：115年09月24日」換成請求的週別，讓日期處理可測。"""
    roc = f"{int(yyyymmdd[:4]) - 1911}年{yyyymmdd[4:6]}月{yyyymmdd[6:]}日"
    return re.sub(r"\d{2,3}年\d{2}月\d{2}日", roc, html, count=1)


class FakeSite:
    """模擬集保查詢頁：一次性 token、可指定哪些代號存在。"""

    def __init__(self, known=("2330",), fail_on_post_n=None):
        self.known = set(known)
        self.valid = None
        self.posts: list[dict] = []
        self.gets = 0
        self.fail_on_post_n = fail_on_post_n

    def _fresh(self, html):
        self.valid = uuid.uuid4().hex
        return _with_token(html, self.valid)

    def __call__(self, method, url, data=None):
        if method == "GET":
            self.gets += 1
            return self._fresh(FORM)
        self.posts.append(dict(data))
        if self.fail_on_post_n is not None and len(self.posts) == self.fail_on_post_n:
            raise OSError("connection reset")
        if data.get("SYNCHRONIZER_TOKEN") != self.valid:
            return self._fresh(FORM)  # 真實站：token 不對就回空表單
        if data.get("stockNo", "").strip() not in self.known:
            return self._fresh(UNKNOWN)
        return self._fresh(_with_date(RESULT, data["scaDate"]))


@pytest.fixture
def site(monkeypatch):
    fake = FakeSite()
    monkeypatch.setattr(tdcc_web, "_http", fake)
    monkeypatch.setattr(tdcc_web.time, "sleep", lambda s: None)
    return fake


# ---------------------------------------------------------------- parse


def test_parse_dates_returns_iso_newest_first():
    dates = tdcc_web.parse_dates(FORM)
    assert len(dates) == 51
    assert dates[0] == "2026-10-08" and dates[-1] == "2025-10-17"
    assert dates == sorted(dates, reverse=True)


def test_parse_result_converts_roc_date_and_levels():
    date, levels = tdcc_web.parse_result(RESULT)
    assert date == "2026-09-24"
    assert [row["level"] for row in levels] == list(range(1, 18))
    by_level = {row["level"]: row for row in levels}
    assert by_level[1] == {"level": 1, "holders": 2_471_283, "shares": 288_915_271, "pct": 1.11}
    assert by_level[15] == {"level": 15, "holders": 1_487, "shares": 21_984_569_643, "pct": 84.77}
    assert by_level[17] == {"level": 17, "holders": 3_020_649, "shares": 25_932_370_067, "pct": 100.0}


def test_web_result_matches_open_data_csv_except_adjustment_row():
    """同一週同一檔，官網頁與開放資料 CSV 逐級相同（交叉驗證解析沒錯位）。

    唯一已知差異是第 16 級「差異數調整」：官網顯示人數空白、-1,000 股、-0.00%，
    CSV 則是 1 人、1,000 股、0.00%（官方兩邊口徑不同，且不影響任何摘要指標）。
    """
    _, levels = tdcc_web.parse_result(RESULT)
    csv_rows = [
        line.split(",") for line in (FX / "tdcc_dispersion.csv").read_text(encoding="utf-8").splitlines()
        if ",2330" in line
    ]
    assert len(csv_rows) == 17
    for row, (_, _, level, holders, shares, pct) in zip(levels, csv_rows):
        if int(level) == 16:
            continue
        assert row == {"level": int(level), "holders": int(holders), "shares": int(shares), "pct": float(pct)}


def test_adjustment_row_keeps_published_web_values_without_negative_zero():
    _, levels = tdcc_web.parse_result(RESULT)
    row = {r["level"]: r for r in levels}[16]
    assert row["holders"] == 0           # 空白 → 0
    assert row["shares"] == -1_000       # 官網原值（負數）
    assert row["pct"] == 0.0 and str(row["pct"]) == "0.0"  # "-0.00" 不可變成 -0.0


def test_parse_result_none_for_unknown_or_form_page():
    assert tdcc_web.parse_result(UNKNOWN) is None
    assert tdcc_web.parse_result(FORM) is None
    assert tdcc_web.parse_result("") is None


# ---------------------------------------------------------------- fetch_history


def test_fetch_history_walks_all_weeks_and_chains_tokens(site):
    out = tdcc_web.fetch_history("2330", weeks=52)
    assert site.gets == 1
    assert len(site.posts) == 51  # 官網只有 51 個週別，weeks 超過也不多打
    assert [p["scaDate"] for p in site.posts] == [d.replace("-", "") for d in tdcc_web.parse_dates(FORM)]
    assert len(out) == 51
    for p in site.posts:
        assert p["stockNo"] == "2330" and p["sqlMethod"] == "StockNo" and p["method"] == "submit"
        assert re.fullmatch(r"\d{8}", p["scaDate"])
    # 每個請求都用上一個回應的新 token（FakeSite 拿舊 token 只回表單頁→會少資料）
    assert [date for date, _ in out] == tdcc_web.parse_dates(FORM)  # 日期取自結果頁並轉成西元
    assert all(len(levels) == 17 for _, levels in out)


def test_fetch_history_requests_newest_dates_first_and_respects_weeks(site):
    tdcc_web.fetch_history("2330", weeks=3)
    assert [p["scaDate"] for p in site.posts] == ["20261008", "20261002", "20260924"]


def test_fetch_history_skips_dates_already_stored(site):
    out = tdcc_web.fetch_history("2330", weeks=4, skip_dates={"2026-10-08", "2026-09-24"})
    # weeks=4 取最近四週 [10-08, 10-02, 09-24, 09-18]，已存的 10-08、09-24 不再請求
    assert [p["scaDate"] for p in site.posts] == ["20261002", "20260918"]
    assert [date for date, _ in out] == ["2026-10-02", "2026-09-18"]
    assert all(date not in {"2026-10-08", "2026-09-24"} for date, _ in out)


def test_fetch_history_unknown_code_stops_after_first_post(site):
    assert tdcc_web.fetch_history("9999", weeks=52) == []
    assert len(site.posts) == 1  # 不為不存在的代號燒 51 次請求


def test_fetch_history_returns_partial_on_network_error(monkeypatch):
    fake = FakeSite(fail_on_post_n=3)
    monkeypatch.setattr(tdcc_web, "_http", fake)
    monkeypatch.setattr(tdcc_web.time, "sleep", lambda s: None)
    out = tdcc_web.fetch_history("2330", weeks=10)
    assert len(out) == 2 and len(fake.posts) == 3  # 前兩週有拿到；斷線後停手，不重試轟炸


def test_fetch_history_is_polite(monkeypatch):
    fake = FakeSite()
    sleeps = []
    monkeypatch.setattr(tdcc_web, "_http", fake)
    monkeypatch.setattr(tdcc_web.time, "sleep", lambda s: sleeps.append(s))
    tdcc_web.fetch_history("2330", weeks=5, delay=0.2)
    assert len(sleeps) >= 4 and all(s >= 0.2 for s in sleeps)


def test_fetch_history_rejects_malformed_code(site):
    assert tdcc_web.fetch_history("", weeks=3) == []
    assert tdcc_web.fetch_history("23 30;DROP", weeks=3) == []
    assert site.posts == [] and site.gets == 0


# ---------------------------------------------------------------- 16 列頁面（沒有「差異數調整」）
#
# 2026-10-15 實測：2330/0050/6488/00878/2317 每一檔的 51 個週別都混著兩種頁面——
# 17 列（含「差異數調整」）與 16 列（沒有那一列，「合 計」直接排第 16 列）。
# 第一版解析器要求湊滿 17 列，遇到第一個 16 列週就當成「沒資料」而靜默停手，
# 每檔只抓到 4 週。這一組案例專門防止這種截斷。

RESULT16 = (FX / "tdcc_web_2330_20260911_no_adjustment.html").read_text(encoding="utf-8")


def test_parse_result_accepts_16_row_page_and_inserts_empty_adjustment_level():
    date, levels = tdcc_web.parse_result(RESULT16)
    assert date == "2026-09-11"
    assert [row["level"] for row in levels] == list(range(1, 18))
    by_level = {row["level"]: row for row in levels}
    assert by_level[15] == {"level": 15, "holders": 1_485, "shares": 21_996_993_078, "pct": 84.82}
    assert by_level[16] == {"level": 16, "holders": 0, "shares": 0, "pct": 0.0}  # 該週沒有這一列
    # 「合計」依列名認，不依位置：必須落在第 17 級
    assert by_level[17] == {"level": 17, "holders": 3_019_610, "shares": 25_932_370_067, "pct": 100.0}


def test_16_row_total_is_never_mistaken_for_level_16():
    _, levels = tdcc_web.parse_result(RESULT16)
    by_level = {row["level"]: row for row in levels}
    assert by_level[16]["holders"] != by_level[17]["holders"]
    assert by_level[17]["holders"] > by_level[15]["holders"]


class MixedSite(FakeSite):
    """奇數週回 17 列頁、偶數週回 16 列頁，貼近真實站的混合狀態。"""

    def __call__(self, method, url, data=None):
        if method == "POST" and self.valid and data.get("SYNCHRONIZER_TOKEN") == self.valid \
                and data.get("stockNo", "").strip() in self.known:
            self.posts.append(dict(data))
            page = RESULT16 if len(self.posts) % 2 == 0 else RESULT
            return self._fresh(_with_date(page, data["scaDate"]))
        return super().__call__(method, url, data)


def test_fetch_history_does_not_truncate_on_mixed_page_variants(monkeypatch):
    fake = MixedSite()
    monkeypatch.setattr(tdcc_web, "_http", fake)
    monkeypatch.setattr(tdcc_web.time, "sleep", lambda s: None)
    out = tdcc_web.fetch_history("2330", weeks=52)
    assert len(out) == 51, "遇到 16 列週不可停手"
    assert [date for date, _ in out] == tdcc_web.parse_dates(FORM)
    assert all(len(levels) == 17 for _, levels in out)


def test_fetch_history_warns_when_it_stops_early(monkeypatch, caplog):
    """中途拿到無法解析的頁面（例如 token 失效回表單）時要留下警告，不能靜默少資料。"""
    fake = MixedSite()
    monkeypatch.setattr(tdcc_web, "_http", fake)
    monkeypatch.setattr(tdcc_web.time, "sleep", lambda s: None)
    original = fake.__call__

    calls = {"n": 0}

    def flaky(method, url, data=None):
        if method == "POST":
            calls["n"] += 1
            if calls["n"] == 6:
                return FORM  # 沒有結果表格、也沒有新的有效 token
        return original(method, url, data)

    monkeypatch.setattr(tdcc_web, "_http", flaky)
    with caplog.at_level("WARNING", logger=tdcc_web.logger.name):
        out = tdcc_web.fetch_history("2330", weeks=52)
    assert len(out) == 5
    assert any(rec.levelname == "WARNING" and "2330" in rec.getMessage() for rec in caplog.records)
