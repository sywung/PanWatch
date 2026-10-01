"""zh-TW 前端字串:由 gen-zh-tw.py 产生,不得残留大陆用语;日志视窗模块名称也要有繁中版。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
TW_FILES = sorted((FRONTEND / "src/i18n/locales/zh-TW").glob("*.ts")) + [
    FRONTEND / "src/lib/logger-map.zh-TW.ts"
]

MAINLAND_TERMS = ["當前", "默認", "獲取", "渠道", "推送", "校驗", "發送", "社交平台", "落庫"]


@pytest.mark.parametrize("term", MAINLAND_TERMS)
def test_no_mainland_terms_in_zh_tw_ui(term):
    hits = [f.name for f in TW_FILES if term in f.read_text(encoding="utf-8")]
    assert hits == [], f"{term} 仍出现在 {hits}"


def test_config_only_kept_for_allocation():
    # 「配置」当设定用要改为「设定」;只允许「资金配置／资产配置」
    for f in TW_FILES:
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"(?<![資金產])配置", text), f.name


def test_no_duplicated_setting_wording():
    for f in TW_FILES:
        text = f.read_text(encoding="utf-8")
        assert "設定中設定" not in text and "設定設定" not in text, f.name


def _logger_keys(text: str, const: str) -> list[str]:
    block = re.search(rf"{const}[^=]*=\s*\{{(.*?)\n\}}", text, re.S).group(1)
    return re.findall(r"'([^']+)':", block)


def test_logger_map_zh_tw_covers_same_modules():
    zh = (FRONTEND / "src/lib/logger-map.ts").read_text(encoding="utf-8")
    tw = (FRONTEND / "src/lib/logger-map.zh-TW.ts").read_text(encoding="utf-8")
    assert _logger_keys(tw, "LOGGER_MAPPING_ZH_TW") == _logger_keys(zh, "LOGGER_MAPPING_ZH")
    assert "盘中监测" not in tw and "盤中監測" in tw


def test_generator_output_is_up_to_date(tmp_path, monkeypatch):
    # 生成档不得手改:重新产生一次必须与 repo 中的内容完全相同
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_zh_tw", FRONTEND / "scripts/gen-zh-tw.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    monkeypatch.setattr(gen, "TARGET_DIR", tmp_path / "locales")
    monkeypatch.setattr(gen, "LOGGER_MAP_TW", tmp_path / "logger-map.zh-TW.ts")
    gen.main()
    for f in sorted((tmp_path / "locales").glob("*.ts")):
        committed = FRONTEND / "src/i18n/locales/zh-TW" / f.name
        assert f.read_text(encoding="utf-8") == committed.read_text(encoding="utf-8"), f.name
    assert (tmp_path / "logger-map.zh-TW.ts").read_text(encoding="utf-8") == (
        FRONTEND / "src/lib/logger-map.zh-TW.ts"
    ).read_text(encoding="utf-8")
