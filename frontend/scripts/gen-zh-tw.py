#!/usr/bin/env python3
"""Generate Taiwan Traditional Chinese locale files from zh-CN locale files."""

from __future__ import annotations

import re
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "src/i18n/locales/zh-CN"
TARGET_DIR = ROOT / "src/i18n/locales/zh-TW"

# Keep manual vocabulary decisions in one place so regeneration is reproducible.
POSTPROCESS = (
    ("臺", "台"), ("賬", "帳"), ("日志", "日誌"), ("質量", "品質"), ("智慧體", "智慧代理"), ("盯盤俠", "盯盤俠"),
    # 台湾惯用直角引号
    ("“", "「"), ("”", "」"), ("‘", "『"), ("’", "』"),
)
OVERRIDES: dict[str, str] = {
    "language.traditionalChinese": "繁體中文",
    # 语系名称以该语系自己的文字显示(与上游 en-US 显示「简体中文」一致)
    "language.simplifiedChinese": "简体中文",
    "language.quickSwitch": "简体中文",
    "normalVolatility": "正常波動",
    "bollSqueeze": "波幅收斂",
    "bollExpansion": "波動擴大",
    "dataSources.credentials.finmindLabel": "FinMind Token（選填）",
    "dataSources.credentials.finmindPlaceholder": "貼上 FinMind API Token",
    "dataSources.credentials.finmindHelp": "公開 API 可免 Token 使用；註冊免費帳號可提高請求額度。",
}

_STRING = re.compile(r"(?P<quote>['\"])(?P<body>(?:\\.|(?!\1).)*)(?P=quote)")
_cc: OpenCC | None = None


def convert(text: str) -> str:
    global _cc
    if _cc is None:
        _cc = OpenCC("s2twp")
    text = _cc.convert(text)
    for old, new in POSTPROCESS:
        text = text.replace(old, new)
    return text


def key_for(source: str, start: int) -> str | None:
    # Locale files are object literals; derive the dotted key path from the
    # preceding property declarations, ignoring imports and code expressions.
    lines = source[:start].splitlines()
    stack: list[str] = []
    for line in lines:
        stripped = line.strip()
        match = re.match(r"([A-Za-z_$][\w$]*):\s*\{\s*$", stripped)
        if match:
            stack.append(match.group(1))
        elif re.match(r"\},?\s*$", stripped) and stack:
            stack.pop()
    current = lines[-1] if lines else ""
    prop = re.search(r"([A-Za-z_$][\w$]*):\s*$", current)
    if not prop:
        return None
    return ".".join((*stack, prop.group(1)))


def generate(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    out: list[str] = []
    last = 0
    for match in _STRING.finditer(source):
        # Only translate values immediately following a property colon. This
        # leaves keys, imports, placeholders, and executable code untouched.
        before = source[last:match.start()]
        if re.search(r":\s*$", before):
            key = key_for(source, match.start())
            raw = match.group("body")
            value = OVERRIDES.get(key, OVERRIDES.get(key.rsplit(".", 1)[-1], convert(raw)) if key else convert(raw))
            out.append(source[last:match.start()])
            out.append(match.group("quote") + value + match.group("quote"))
            last = match.end()
    out.append(source[last:])
    header = "// 由 gen-zh-tw.py 自 zh-CN 產生；手動修正請寫進腳本的 OVERRIDES，不要直接改本檔。\n"
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    (TARGET_DIR / path.name).write_text(header + "".join(out), encoding="utf-8")


def main() -> None:
    for source in sorted(SOURCE_DIR.glob("*.ts")):
        generate(source)


if __name__ == "__main__":
    main()
