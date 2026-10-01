"""默认市场改为 TW:禁止在业务代码里再写死 "CN" 默认值或三市场清单。

例外:`src/platform/persistence/migrations.py`(历史数据迁移,旧资料确实是 CN 语义)。
"""

from __future__ import annotations

import re
from pathlib import Path

from src.platform.marketdata import models

ROOT = Path(__file__).resolve().parents[1]
ALLOW = {"src/platform/persistence/migrations.py"}

# 写死 "CN" 当默认/兜底的形态
_DEFAULT_PATTERNS = [
    re.compile(r"""default\s*=\s*["']CN["']"""),                 # ORM / Field default
    re.compile(r""":\s*str\s*=\s*["']CN["']"""),                 # 参数默认值
    re.compile(r"""\bor\s+["']CN["']"""),                        # x or "CN"
    re.compile(r"""\.get\(\s*["'][a-z_]*market["']\s*,\s*["']CN["']\s*\)"""),  # d.get("market", "CN")
    re.compile(r"""\belse\s+["']CN["']"""),                      # ... if ... else "CN"
    re.compile(r"""\belse\s+MarketCode\.CN\b"""),                # ... if ... else MarketCode.CN
    re.compile(r"""market\s*=\s*["']CN["']\s*[,)]"""),           # 调用时 market="CN"
]

# 写死三市场清单(应改用 models.ALL_MARKETS)
_LIST_PATTERN = re.compile(r"""["']CN["']\s*,\s*["']HK["']\s*,\s*["']US["']""")


def _py_files():
    files = [ROOT / "server.py", *sorted((ROOT / "src").rglob("*.py"))]
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if rel not in ALLOW:
            yield rel, f.read_text(encoding="utf-8")


def _hits(pattern_list):
    out = []
    for rel, text in _py_files():
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if any(p.search(line) for p in pattern_list):
                out.append(f"{rel}:{i}: {line.strip()}")
    return out


def test_all_markets_constant():
    assert models.ALL_MARKETS == ("TW", "CN", "HK", "US")
    assert models.DEFAULT_MARKET.value == "TW"


def test_no_hardcoded_cn_defaults():
    hits = _hits(_DEFAULT_PATTERNS)
    assert hits == [], "仍有写死 CN 的默认值:\n" + "\n".join(hits)


def test_no_hardcoded_three_market_lists():
    hits = _hits([_LIST_PATTERN])
    assert hits == [], "仍有写死的三市场清单(改用 ALL_MARKETS):\n" + "\n".join(hits)


def test_scan_patterns_actually_match():
    """陰性对照:确认扫描规则本身抓得到违规写法(避免规则写错而永远通过)。"""
    samples = [
        'market = Column(String, nullable=False, default="CN")',
        'def f(market: str = "CN"):',
        'm = (x or "CN").upper()',
        'm = p.get("market", "CN")',
        'm = p.get("stock_market", "CN")',
        'return m if m in ok else "CN"',
        'code = MarketCode(m) if ok else MarketCode.CN',
        'foo(symbol, market="CN")',
    ]
    for s in samples:
        assert any(p.search(s) for p in _DEFAULT_PATTERNS), s
    assert _LIST_PATTERN.search('MARKETS = ("CN", "HK", "US")')
    assert _LIST_PATTERN.search('"enum": ["CN", "HK", "US"],')
    # 合法写法不应误报
    assert not any(p.search('if market == "CN":') for p in _DEFAULT_PATTERNS)
    assert not any(p.search('market: str = DEFAULT_MARKET.value') for p in _DEFAULT_PATTERNS)


# ---------------------------------------------------------------- 行为:TW 不再落入 CN 分支


def test_stock_link_for_tw_uses_yahoo_tw():
    from src.modules.administration.stock_link import stock_url

    assert stock_url("2330", "TW", platform="xueqiu") == "https://tw.stock.yahoo.com/quote/2330"
    assert stock_url("6488", "tw", platform="xueqiu") == "https://tw.stock.yahoo.com/quote/6488"
    # 其他市场不变
    assert stock_url("AAPL", "US", platform="xueqiu") == "https://xueqiu.com/S/AAPL"


def test_tradingagents_market_resolution():
    from src.modules.automation.tradingagents.operations import _resolve_market
    from src.platform.marketdata.models import MarketCode

    assert _resolve_market("TW") is MarketCode.TW
    assert _resolve_market("") is MarketCode.TW
    assert _resolve_market(None) is MarketCode.TW
    assert _resolve_market("cn") is MarketCode.CN
    assert _resolve_market("HK") is MarketCode.HK


def test_market_scan_seed_has_tw():
    from src.modules.strategy.entry_candidates import MARKET_SCAN_SEED_SYMBOLS

    assert set(MARKET_SCAN_SEED_SYMBOLS) >= {"TW", "CN", "HK", "US"}
    tw = MARKET_SCAN_SEED_SYMBOLS["TW"]
    assert "2330" in tw and len(tw) >= 10
    assert all(re.fullmatch(r"\d{4,6}[A-Z]?", s) for s in tw)


def test_factor_weights_markets_include_tw():
    from src.modules.strategy import factor_weights

    assert "TW" in factor_weights.MARKETS


def test_paper_trading_markets_include_tw():
    from src.modules.paper_trading.paper_trading_engine import ALL_MARKETS

    assert "TW" in ALL_MARKETS


def test_assistant_tool_schemas_offer_tw():
    """助手工具 JSON schema 里的 market enum 必须包含 TW,否则 LLM 无法指定台股。"""
    text = (ROOT / "src/modules/assistant/tools.py").read_text(encoding="utf-8")
    assert '"enum": ["CN", "HK", "US"]' not in text


def test_no_hardcoded_fx_rates_outside_fx_module():
    """汇率只能来自 src/platform/marketdata/fx.py。"""
    pat = re.compile(r"""\bfx\s*=\s*(0\.92|7\.25)\b|HKD_CNY|USD_CNY|hkd_cny|usd_cny""")
    hits = [h for h in _hits([pat]) if not h.startswith("src/platform/marketdata/fx.py")]
    assert hits == [], "\n".join(hits)
