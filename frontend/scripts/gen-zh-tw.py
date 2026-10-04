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
    # 三批繁中詞彙修正；片語放在單詞規則之前，避免改變「執行未通過」。
    ("通過 OpenAI", "透過 OpenAI"), ("程式碼", "代碼"), ("引數", "參數"), ("示例", "範例"),
    ("臺", "台"), ("賬", "帳"), ("日志", "日誌"), ("質量", "品質"), ("智慧體", "智慧代理"), ("盯盤俠", "盯盤俠"),
    # 台湾惯用直角引号
    ("“", "「"), ("”", "」"), ("‘", "『"), ("’", "』"),
    # 大陆用语 → 台湾用语(OpenCC s2twp 不处理)。整句短语放在单词规则之前。
    ("當前程序", "目前的處理程序"), ("結果未落庫", "結果尚未寫入"), ("默認同模型標識", "預設與模型 ID 相同"),
    ("通過所選", "透過所選"), ("通過通知", "透過通知"), ("在設定中配置", "在設定頁新增"),
    ("當前", "目前"), ("默認", "預設"), ("獲取", "取得"), ("渠道", "管道"), ("推送", "推播"),
    ("校驗", "驗證"), ("發送", "傳送"), ("社交平台", "社群平台"),
)
# 「配置」当「设定」用时改为设定；资金／资产配置是台湾也用的投资用语，保留。
REGEX_POSTPROCESS = (
    (re.compile(r"(?<![資金產])配置"), "設定"),
)
OVERRIDES: dict[str, str] = {
    "language.traditionalChinese": "繁體中文",
    # 语系名称以该语系自己的文字显示(与上游 en-US 显示「简体中文」一致)
    "language.simplifiedChinese": "简体中文",
    "language.quickSwitch": "简体中文",
    "normalVolatility": "正常波動",
    "loadingEarlier": "載入更早資料…",
    "bollSqueeze": "波幅收斂",
    "bollExpansion": "波動擴大",
    "dataSources.credentials.finmindLabel": "FinMind Token（選填）",
    "dataSources.credentials.finmindPlaceholder": "貼上 FinMind API Token",
    "dataSources.credentials.finmindHelp": "公開 API 可免 Token 使用；註冊免費帳號可提高請求額度。",
    "dataSources.credentials.yuantadataBaseUrlLabel": "yuantaData 服務網址",
    "dataSources.credentials.yuantadataBaseUrlPlaceholder": "http://192.168.221.194:8090",
    "dataSources.credentials.yuantadataBaseUrlHelp": "填入可連線的 yuantaData API 根網址（不含路徑）。",
    "dataSources.credentials.yuantadataLabel": "yuantaData API Token（選填）",
    "dataSources.credentials.yuantadataPlaceholder": "貼上 yuantaData Token；未設定時不傳送 Authorization",
    "dataSources.credentials.yuantadataHelp": "請自架 yuantaData FastAPI 服務，並填入服務的 base_url。",
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
    for pattern, new in REGEX_POSTPROCESS:
        text = pattern.sub(new, text)
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


LOGGER_MAP = ROOT / "src/lib/logger-map.ts"
LOGGER_MAP_TW = ROOT / "src/lib/logger-map.zh-TW.ts"


def generate_logger_map() -> None:
    # 日志视窗的模块名称表不在 locales 里,单独从 LOGGER_MAPPING_ZH 转出一份。
    source = LOGGER_MAP.read_text(encoding="utf-8")
    block = re.search(r"export const LOGGER_MAPPING_ZH[^=]*=\s*\{(?P<body>.*?)\n\}", source, re.S)
    if not block:
        raise SystemExit("logger-map.ts: LOGGER_MAPPING_ZH not found")
    body = re.sub(
        r"(?P<key>'[^']*'):\s*'(?P<label>[^']*)'",
        lambda m: f"{m.group('key')}: '{convert(m.group('label'))}'",
        block.group("body"),
    )
    header = "// 由 gen-zh-tw.py 自 logger-map.ts 的 LOGGER_MAPPING_ZH 產生；不要直接改本檔。\n"
    LOGGER_MAP_TW.write_text(
        header + "export const LOGGER_MAPPING_ZH_TW: Record<string, string> = {" + body + "\n}\n",
        encoding="utf-8",
    )


def main() -> None:
    for source in sorted(SOURCE_DIR.glob("*.ts")):
        generate(source)
    generate_logger_map()


if __name__ == "__main__":
    main()
