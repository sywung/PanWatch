"""台股(TW)代码值对象:市场枚举、自动判别、Yahoo 代码。"""

from marketdata.symbol import Market, Symbol


def test_tw_market_enum_exists():
    assert Market("TW") is Market.TW


def test_parse_four_digit_code_detects_tw():
    assert Symbol.parse("2330").market == Market.TW
    assert Symbol.parse("0050").market == Market.TW


def test_parse_etf_with_letter_suffix_detects_tw():
    # 债券 ETF(尾码 B)、主动式 ETF(尾码 A)
    assert Symbol.parse("00679B").market == Market.TW
    assert Symbol.parse("00400A").market == Market.TW


def test_existing_markets_detection_unchanged():
    assert Symbol.parse("600519").market == Market.CN
    assert Symbol.parse("00700").market == Market.HK
    assert Symbol.parse("AAPL").market == Market.US


def test_six_digit_tw_etf_needs_explicit_market():
    # 006208 与 A 股 6 位代码规则冲突:不带 market 时仍判为 CN(已知歧义),显式指定才是 TW
    assert Symbol.parse("006208").market == Market.CN
    assert Symbol.parse("006208", "TW").market == Market.TW


def test_tw_to_yfinance_defaults_to_listed_suffix():
    assert Symbol.parse("2330", "TW").to_yfinance() == "2330.TW"
