"""台股資料源(TWSE/TPEx/TDCC/Yahoo/鉅亨)，統一經 tw_bulk 取數。"""
from __future__ import annotations

import csv
import io
import re

from marketdata.symbol import Symbol
from marketdata.types import (
    CapitalFlow, DividendItem, EventItem, Fundamentals, MarginItem, ShareholderItem,
)
from marketdata.vendors import tw_bulk
from marketdata.vendors.base import (
    CapitalFlowVendor, DividendVendor, EventsVendor, FundamentalsVendor,
    MarginVendor, ShareholdersVendor,
)

from marketdata.vendors.tw_common import (
    _MOPS_URL, _T86_URL, _TDCC_URL, _TPEX, _TPEX_FOREIGN_DIFF,
    _TPEX_FOREIGN_DIFF_ALT, _TWSE, _TWSE_MATERIAL_TITLE, _code, _f,
    _merge, _rows, _tw_time,
)


class TwseFundamentalsVendor(FundamentalsVendor):
    """TWSE/TPEx 估值资料；合并上市与上柜后按代码返回。

    来源为 TWSE ``BWIBBU_ALL`` 与 TPEx ``tpex_mainboard_peratio_analysis``。
    PE、殖利率与 PB 为官方估值字段；与 A 股同名字段含义相近，但台股以交易所
    原始口径为准，不能视为 A 股的市场分类。
    """

    name = "twse"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[Fundamentals]:
        def get(kind):
            url = (_TWSE + "exchangeReport/BWIBBU_ALL" if kind == "twse"
                   else _TPEX + "tpex_mainboard_peratio_analysis")
            result = []
            for row in _rows(url):
                code = _code(row.get("Code") or row.get("SecuritiesCompanyCode"))
                if not tw_bulk.valid_code(code):
                    continue
                result.append(Fundamentals(
                    symbol=code, market="TW",
                    name=str(row.get("Name") or row.get("CompanyName") or ""),
                    pe_ttm=_f(row.get("PEratio") or row.get("PriceEarningRatio")),
                    dividend_yield=_f(row.get("DividendYield") or row.get("YieldRatio")),
                    pb=_f(row.get("PBratio") or row.get("PriceBookRatio")),
                ))
            return result
        return _merge(get, symbols)


class TwseCapitalFlowVendor(CapitalFlowVendor):
    """TWSE/TPEx 三大法人买卖超；合并上市与上柜并以股为单位。

    来源为 TWSE T86 与 TPEx ``tpex_3insti_daily_trading``。foreign/trust/dealer
    是法人买卖超股数，institutional_net 是三大法人合计股数；这些字段与 A 股
    ``main_net_inflow`` 的资金净流入语意不同，不能互相填充。
    """

    name = "twse"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[CapitalFlow]:
        chosen = None
        for day in tw_bulk.recent_dates():
            data = tw_bulk.get_json(_T86_URL, {
                "date": day, "selectType": "ALLBUT0999", "response": "json",
            })
            if data.get("stat") == "OK" and data.get("data"):
                chosen = data
                break
        if not chosen:
            return []
        fields = chosen.get("fields", [])
        indexes = {field: index for index, field in enumerate(fields)}

        def get(row, key):
            return row[indexes[key]] if key in indexes and indexes[key] < len(row) else None

        result = []
        for row in chosen["data"]:
            code = _code(get(row, "證券代號"))
            if tw_bulk.valid_code(code):
                result.append(CapitalFlow(
                    symbol=code, name=str(get(row, "證券名稱") or "").strip(),
                    foreign_net=(_f(get(row, "外陸資買賣超股數(不含外資自營商)")) or 0)
                    + (_f(get(row, "外資自營商買賣超股數")) or 0),
                    trust_net=_f(get(row, "投信買賣超股數")),
                    dealer_net=_f(get(row, "自營商買賣超股數")),
                    institutional_net=_f(get(row, "三大法人買賣超股數")),
                    unit="股", trade_date=tw_bulk.tw_date(chosen.get("date")),
                ))
        try:
            for row in _rows(_TPEX + "tpex_3insti_daily_trading"):
                code = _code(row.get("SecuritiesCompanyCode"))
                if tw_bulk.valid_code(code):
                    result.append(CapitalFlow(
                        symbol=code, name=str(row.get("CompanyName") or ""),
                        foreign_net=_f(row.get(_TPEX_FOREIGN_DIFF)
                                       or row.get(_TPEX_FOREIGN_DIFF_ALT)),
                        trust_net=_f(row.get("SecuritiesInvestmentTrustCompanies-Difference")),
                        dealer_net=_f(row.get("Dealers-Difference")),
                        institutional_net=_f(row.get("TotalDifference")),
                        unit="股", trade_date=tw_bulk.tw_date(row.get("Date")),
                    ))
        except Exception as exc:
            logger.warning("台股 TPEx 三大法人失败: %s", exc)
        wanted = {symbol.code for symbol in symbols}
        return [item for item in result if item.symbol in wanted]


class TwseMarginVendor(MarginVendor):
    """TWSE/TPEx 融资融券余额；合并上市与上柜，数量单位为张。

    来源为 TWSE ``MI_MARGN`` 与 TPEx ``tpex_mainboard_margin_balance``。字段与 A 股
    同名融资融券字段方向相近，但台股这里是交易所数量（张），不是 A 股金额（元）。
    """

    name = "twse"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[MarginItem]:
        def get(kind):
            url = (_TWSE + "exchangeReport/MI_MARGN" if kind == "twse"
                   else _TPEX + "tpex_mainboard_margin_balance")
            result = []
            for row in _rows(url):
                code = _code(row.get("股票代號") or row.get("SecuritiesCompanyCode"))
                if tw_bulk.valid_code(code):
                    result.append(MarginItem(
                        date=tw_bulk.tw_date(row.get("Date") or ""), symbol=code,
                        rz_balance=_f(row.get("融資今日餘額") or row.get("MarginPurchaseBalance")),
                        rz_buy=_f(row.get("融資買進") or row.get("MarginPurchase")),
                        rq_balance=_f(row.get("融券今日餘額") or row.get("ShortSaleBalance")),
                        rq_sell_vol=_f(row.get("融券賣出") or row.get("ShortSale")), unit="張",
                    ))
            return result
        return _merge(get, symbols)


class TwseDividendVendor(DividendVendor):
    """TWSE 上市股利及除權息资料；来源为 TWSE，上市资料不含 TPEx 合并。

    股利金额与股票股利按元/股，除权息日期按日期返回；与 A 股 dividend_per_share
    相近，但 bonus_ratio 是台湾官方配股元/股口径，不应解读为 A 股送转比例。
    """

    name = "twse"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[DividendItem]:
        wanted = {symbol.code for symbol in symbols}
        dividends = {}
        for row in _rows(_TWSE + "opendata/t187ap45_L"):
            code = _code(row.get("公司代號"))
            if code not in wanted:
                continue
            cash = sum(_f(row.get(key)) or 0 for key in (
                "股東配發-盈餘分配之現金股利(元/股)",
                "股東配發-法定盈餘公積發放之現金(元/股)",
                "股東配發-資本公積發放之現金(元/股)",
            ))
            bonus = sum(_f(row.get(key)) or 0 for key in (
                "股東配發-盈餘轉增資配股(元/股)",
                "股東配發-法定盈餘公積轉增資配股(元/股)",
                "股東配發-資本公積轉增資配股(元/股)",
            ))
            key = str(row.get("股利年度")) + str(row.get("股利所屬年(季)度"))
            dividends[(code, key)] = DividendItem(
                ex_date="", symbol=code, dividend_per_share=cash or None,
                bonus_ratio=bonus or None,
                progress=(f"{row.get('股利年度', '')}年{row.get('股利所屬年(季)度', '')} "
                          f"{row.get('決議（擬議）進度', '')}"),
            )
        for row in _rows(_TWSE + "exchangeReport/TWT48U_ALL"):
            code = _code(row.get("Code"))
            if code in wanted:
                dividends.setdefault((code, "ex"), DividendItem(
                    ex_date=tw_bulk.tw_date(row.get("Date")), symbol=code,
                ))
        return list(dividends.values())


class TdccShareholdersVendor(ShareholdersVendor):
    """TDCC 集保股权分散资料；按代码汇总上市与上柜，数量单位为股。

    来源为 TDCC ``1-5`` CSV。持股分级比例是集保库存比例，holder_num 为人数、
    avg_shares 为平均持股股数；与 A 股同为统计指标，但分级区间与 A 股口径不同。
    """

    name = "tdcc"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[ShareholderItem]:
        wanted = {symbol.code for symbol in symbols}
        text = tw_bulk.get_text(_TDCC_URL, {"id": "1-5"}, ttl=43200)
        rows = list(csv.DictReader(io.StringIO(text)))
        for row in rows:
            if "\ufeff資料日期" in row:
                row["資料日期"] = row.pop("\ufeff資料日期")
        groups = {}
        for row in rows:
            code = _code(row.get("證券代號"))
            if code in wanted:
                groups.setdefault(code, []).append(row)
        result = []
        for code, group in groups.items():
            total = next((row for row in group if row.get("持股分級") == "17"), {})

            def ratio(levels):
                return sum(_f(row.get("占集保庫存數比例%")) or 0 for row in group
                           if row.get("持股分級") in levels)

            holder_num = int(float(total.get("人數") or 0))
            result.append(ShareholderItem(
                report_date=tw_bulk.tw_date(total.get("資料日期")), symbol=code,
                holder_num=holder_num,
                avg_shares=(_f(total.get("股數")) or 0) / int(float(total.get("人數") or 1)),
                big_holder_ratio=ratio({"12", "13", "14", "15"}),
                thousand_lot_ratio=ratio({"15"}),
            ))
        return result


class TwseEventsVendor(EventsVendor):
    """TWSE/TPEx 重大讯息；合并上市与上柜，单位为事件与 UTC 时间。

    来源为 TWSE ``t187ap04_L``、TPEx ``mopsfin_t187ap04_O``。标题与发布时间是
    MOPS 公告原值；与 A 股事件字段同型，但 material_info 是台股重大讯息类型。
    无法解析时间的资料会略过并记录 debug 日志。
    """

    name = "twse"
    supports_markets = {"TW"}

    def fetch(self, symbols: list[Symbol], config: dict) -> list[EventItem]:
        wanted = {symbol.code for symbol in symbols}
        result = []
        for kind in ("twse", "tpex"):
            url = (_TWSE + "opendata/t187ap04_L" if kind == "twse"
                   else _TPEX + "mopsfin_t187ap04_O")
            for row in _rows(url):
                code = _code(row.get("公司代號") or row.get("SecuritiesCompanyCode"))
                if code not in wanted:
                    continue
                day = row.get("發言日期") or row.get("Date")
                clock = row.get("發言時間") or "0"
                publish_time = _tw_time(day, clock)
                if publish_time is None:
                    continue
                title = row.get(_TWSE_MATERIAL_TITLE) or row.get("主旨") or ""
                result.append(EventItem(
                    source="twse_mops", external_id=f"{code}-{day}-{clock}",
                    event_type="material_info",
                    title=re.sub(r"[\\r\\n]+", "", str(title)),
                    publish_time=publish_time, symbols=[code], importance=1, url=_MOPS_URL,
                ))
        return result
