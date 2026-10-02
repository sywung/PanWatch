"""元大 SparkAPI 資料來源種子:預設停用、預設轉接服務網址、報價為備援、K 線排在 Yahoo 之前。"""

from marketdata.registry import VENDOR_CLASSES_BY_TYPE


def _seed(dtype):
    import server

    rows = [s for s in server.DATA_SOURCE_SEEDS if s["type"] == dtype and s["provider"] == "yuanta"]
    assert len(rows) == 1, f"缺少元大 {dtype} 種子"
    return rows[0]


def test_yuanta_seeds_disabled_by_default():
    for dtype in ("quote", "kline"):
        row = _seed(dtype)
        assert row["enabled"] is False                     # 需自行架設轉接服務與帳密
        assert row["config"]["base_url"] == "http://host.containers.internal:2885"
        assert "token" in row["config"]
        assert row["test_symbols"] and all(s.isdigit() for s in row["test_symbols"])
        assert VENDOR_CLASSES_BY_TYPE[dtype]["yuanta"]


def test_yuanta_kline_priority_before_yahoo_quote_after_twse():
    import server

    def prio(dtype, provider):
        return next(s["priority"] for s in server.DATA_SOURCE_SEEDS
                    if s["type"] == dtype and s["provider"] == provider)

    assert prio("kline", "yuanta") < prio("kline", "yahoo")      # 啟用後台股日 K 以元大為主
    assert prio("quote", "yuanta") > prio("quote", "twse")       # 報價以證交所 mis 為主、元大備援
