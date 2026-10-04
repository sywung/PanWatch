"""Yahoo 日 K 請求參數：5 年內用 range；更長改用 period1/period2（range=max 會被降成月 K）。"""

from marketdata.vendors.kline import _yahoo_daily_params

NOW = 1_791_158_400  # 2026-10-05 00:00 UTC


def test_up_to_five_years_uses_range_enum():
    assert _yahoo_daily_params(500, now=NOW) == {"interval": "1d", "range": "2y"}
    assert _yahoo_daily_params(1300, now=NOW) == {"interval": "1d", "range": "5y"}


def test_longer_spans_use_explicit_period_never_max():
    params = _yahoo_daily_params(5200, now=NOW)
    assert "range" not in params
    assert params["interval"] == "1d"
    assert params["period2"] == NOW + 86400
    assert params["period1"] == NOW - int(5200 * 1.5 * 86400)
    assert _yahoo_daily_params(1301, now=NOW).get("range") is None
