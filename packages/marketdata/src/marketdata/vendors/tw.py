"""台股資料源(TWSE/TPEx/TDCC/Yahoo/鉅亨)，統一經 tw_bulk 取數。"""
from __future__ import annotations

import csv
import html
import io
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from marketdata.symbol import Symbol
from marketdata.types import (CapitalFlow, DividendItem, DragonTigerItem, EventItem,
                              FlashNews, Fundamentals, MarginItem, NewsArticle,
                              ShareholderItem)
from marketdata.vendors.base import (CapitalFlowVendor, DividendVendor, DragonTigerVendor,
    EventsVendor, FlashNewsVendor, FundamentalsVendor, MarginVendor, NewsVendor,
    ShareholdersVendor)
from marketdata.vendors import tw_bulk

logger = logging.getLogger(__name__)
_TWSE = "https://openapi.twse.com.tw/v1/"
_TPEX = "https://www.tpex.org.tw/openapi/v1/"

def _f(v): return tw_bulk.number(v)
def _code(v): return str(v or "").strip().upper()
def _tw_time(d, t):
    ds = tw_bulk.tw_date(d); ts = str(t or "0").strip().zfill(6)
    try: return datetime.strptime(f"{ds} {ts}", "%Y-%m-%d %H%M%S").replace(tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc)
    except ValueError: return datetime(1970, 1, 1, tzinfo=timezone.utc)
def _rows(url, *, params=None, ttl=1800):
    data = tw_bulk.get_json(url, params, ttl)
    return data if isinstance(data, list) else []
def _merge(fetch, symbols):
    wanted = {_code(s.code) for s in symbols}
    out = []
    try: out.extend(fetch("twse"))
    except Exception as e: logger.warning("台股 TWSE 请求失败: %s", e)
    try: out.extend(fetch("tpex"))
    except Exception as e: logger.warning("台股 TPEx 请求失败: %s", e)
    return [x for x in out if x.symbol in wanted]

class TwseFundamentalsVendor(FundamentalsVendor):
    name="twse"; supports_markets={"TW"}
    def fetch(self, symbols, config):
        def get(kind):
            rows = _rows(_TWSE+"exchangeReport/BWIBBU_ALL") if kind=="twse" else _rows(_TPEX+"tpex_mainboard_peratio_analysis")
            out=[]
            for r in rows:
                c=_code(r.get("Code") or r.get("SecuritiesCompanyCode"));
                if not tw_bulk.valid_code(c): continue
                out.append(Fundamentals(symbol=c, market="TW", name=str(r.get("Name") or r.get("CompanyName") or ""), pe_ttm=_f(r.get("PEratio") or r.get("PriceEarningRatio")), dividend_yield=_f(r.get("DividendYield") or r.get("YieldRatio")), pb=_f(r.get("PBratio") or r.get("PriceBookRatio"))))
            return out
        return _merge(get, symbols)

class TwseCapitalFlowVendor(CapitalFlowVendor):
    name="twse"; supports_markets={"TW"}
    def fetch(self, symbols, config):
        chosen=None
        for d in tw_bulk.recent_dates():
            data=tw_bulk.get_json("https://www.twse.com.tw/rwd/zh/fund/T86", {"date":d,"selectType":"ALLBUT0999","response":"json"})
            if data.get("stat")=="OK" and data.get("data"): chosen=data; break
        if not chosen: return []
        fields=chosen.get("fields",[]); idx={x:i for i,x in enumerate(fields)}
        def get(r,k): return r[idx[k]] if k in idx and idx[k]<len(r) else None
        tw=[]
        for r in chosen["data"]:
            c=_code(get(r,"證券代號"));
            if tw_bulk.valid_code(c): tw.append(CapitalFlow(symbol=c,name=str(get(r,"證券名稱") or "").strip(),foreign_net=(_f(get(r,"外陸資買賣超股數(不含外資自營商)")) or 0)+(_f(get(r,"外資自營商買賣超股數")) or 0),trust_net=_f(get(r,"投信買賣超股數")),dealer_net=_f(get(r,"自營商買賣超股數")),institutional_net=_f(get(r,"三大法人買賣超股數")),unit="股",trade_date=tw_bulk.tw_date(chosen.get("date"))))
        try:
            for r in _rows(_TPEX+"tpex_3insti_daily_trading"):
                c=_code(r.get("SecuritiesCompanyCode"));
                if tw_bulk.valid_code(c): tw.append(CapitalFlow(symbol=c,name=str(r.get("CompanyName") or ""),foreign_net=_f(r.get("ForeignInvestorsInclude MainlandAreaInvestors-Difference") or r.get("ForeignInvestorsIncludeMainlandAreaInvestors-Difference")),trust_net=_f(r.get("SecuritiesInvestmentTrustCompanies-Difference")),dealer_net=_f(r.get("Dealers-Difference")),institutional_net=_f(r.get("TotalDifference")),unit="股",trade_date=tw_bulk.tw_date(r.get("Date"))))
        except Exception as e: logger.warning("台股 TPEx 三大法人失败: %s", e)
        wanted={s.code for s in symbols}; return [x for x in tw if x.symbol in wanted]

class TwseMarginVendor(MarginVendor):
    name="twse"; supports_markets={"TW"}
    def fetch(self,symbols,config):
        def get(kind):
            rows=_rows(_TWSE+"exchangeReport/MI_MARGN") if kind=="twse" else _rows(_TPEX+"tpex_mainboard_margin_balance"); out=[]
            for r in rows:
                c=_code(r.get("股票代號") or r.get("SecuritiesCompanyCode"));
                if tw_bulk.valid_code(c): out.append(MarginItem(date=tw_bulk.tw_date(r.get("Date") or ""),symbol=c,rz_balance=_f(r.get("融資今日餘額") or r.get("MarginPurchaseBalance")),rz_buy=_f(r.get("融資買進") or r.get("MarginPurchase")),rq_balance=_f(r.get("融券今日餘額") or r.get("ShortSaleBalance")),rq_sell_vol=_f(r.get("融券賣出") or r.get("ShortSale")),unit="張"))
            return out
        return _merge(get,symbols)

class TwseDividendVendor(DividendVendor):
    name="twse"; supports_markets={"TW"}
    def fetch(self,symbols,config):
        wanted={s.code for s in symbols}; div={}
        for r in _rows(_TWSE+"opendata/t187ap45_L"):
            c=_code(r.get("公司代號"));
            if c in wanted:
                cash = sum(_f(r.get(k)) or 0 for k in (
                    "股東配發-盈餘分配之現金股利(元/股)",
                    "股東配發-法定盈餘公積發放之現金(元/股)",
                    "股東配發-資本公積發放之現金(元/股)",
                ))
                bonus = sum(_f(r.get(k)) or 0 for k in (
                    "股東配發-盈餘轉增資配股(元/股)",
                    "股東配發-法定盈餘公積轉增資配股(元/股)",
                    "股東配發-資本公積轉增資配股(元/股)",
                ))
                div[(c, str(r.get("股利年度")) + str(r.get("股利所屬年(季)度")))] = DividendItem(
                    ex_date="", symbol=c, dividend_per_share=cash or None,
                    bonus_ratio=bonus or None,
                    progress=f"{r.get('股利年度', '')}年{r.get('股利所屬年(季)度', '')} {r.get('決議（擬議）進度', '')}",
                )
        for r in _rows(_TWSE+"exchangeReport/TWT48U_ALL"):
            c=_code(r.get("Code"));
            if c in wanted: div.setdefault((c,"ex"),DividendItem(ex_date=tw_bulk.tw_date(r.get("Date")),symbol=c))
        return list(div.values())

class TdccShareholdersVendor(ShareholdersVendor):
    name="tdcc"; supports_markets={"TW"}
    def fetch(self,symbols,config):
        wanted={s.code for s in symbols}; rows=list(csv.DictReader(io.StringIO(tw_bulk.get_text("https://opendata.tdcc.com.tw/getOD.ashx",{"id":"1-5"},ttl=43200))))
        for r in rows:
            if "\ufeff資料日期" in r:
                r["資料日期"] = r.pop("\ufeff資料日期")
        groups={}
        for r in rows:
            c=_code(r.get("證券代號"));
            if c in wanted: groups.setdefault(c,[]).append(r)
        out=[]
        for c,rs in groups.items():
            total=next((r for r in rs if r.get("持股分級")=="17"),{}); ratio=lambda level: sum(_f(r.get("占集保庫存數比例%")) or 0 for r in rs if r.get("持股分級") in level)
            out.append(ShareholderItem(report_date=tw_bulk.tw_date(total.get("資料日期")),symbol=c,holder_num=int(float(total.get("人數") or 0)),avg_shares=(_f(total.get("股數")) or 0)/(int(float(total.get("人數") or 1))),big_holder_ratio=ratio({"12","13","14","15"}),thousand_lot_ratio=ratio({"15"})))
        return out

class TwseEventsVendor(EventsVendor):
    name="twse"; supports_markets={"TW"}
    def fetch(self,symbols,config):
        wanted={s.code for s in symbols}; out=[]
        for kind in ("twse","tpex"):
            rows=_rows(_TWSE+"opendata/t187ap04_L") if kind=="twse" else _rows(_TPEX+"mopsfin_t187ap04_O")
            for r in rows:
                c=_code(r.get("公司代號") or r.get("SecuritiesCompanyCode"));
                if c in wanted:
                    d=r.get("發言日期") or r.get("Date"); t=r.get("發言時間") or "0"; out.append(EventItem(source="twse_mops",external_id=f"{c}-{d}-{t}",event_type="material_info",title=re.sub(r"[\\r\\n]+","",str(r.get("主旨 ") or r.get("主旨") or "")),publish_time=_tw_time(d,t),symbols=[c],importance=1,url="https://mops.twse.com.tw/mops/web/t05st01"))
        return out

class TwseDragonTigerVendor(DragonTigerVendor):
    name="twse"; supports_markets={"TW"}
    def fetch(self,symbols,config):
        d=(config or {}).get("date");
        if not d:return []
        out=[]
        for url,prefix,reason,close in (("announcement/notice","注意股：","TradingInfoForAttention","ClosingPrice"),("announcement/punish","處置股：","ReasonsOfDisposition",None)):
            for r in _rows(_TWSE+url):
                roc_day = f"{int(d[:4]) - 1911:03d}{d[5:7]}{d[8:10]}" if len(d) == 10 else ""
                period = str(r.get("DispositionPeriod") or "").replace("/", "")
                dates = re.findall(r"\d{7}", period)
                in_period = len(dates) == 2 and dates[0] <= roc_day <= dates[1]
                if tw_bulk.tw_date(r.get("Date"))!=d and not (url.endswith("punish") and in_period):continue
                c=_code(r.get("Code"));
                if tw_bulk.valid_code(c): out.append(DragonTigerItem(trade_date=d,symbol=c,name=str(r.get("Name") or ""),reason=prefix+str(r.get(reason) or "")+((" "+str(r.get("DispositionPeriod") or "")) if not close else ""),close=_f(r.get(close)) if close else None))
        return out

class YahooTwNewsVendor(NewsVendor):
    name="yahoo_tw"; supports_markets={"TW"}
    def fetch(self,symbols,config):
        out=[]
        for s in symbols:
            for suffix in ((".TWO", ".TW") if s.code in getattr(__import__('marketdata.vendors.kline',fromlist=['_TW_SUFFIX_HINT']),'_TW_SUFFIX_HINT',{}) else (".TW", ".TWO")):
                try: root=ET.fromstring(tw_bulk.get_text("https://tw.stock.yahoo.com/rss",{"s":s.code+suffix})); items=root.findall("./channel/item")
                except Exception: continue
                if items:
                    out += [NewsArticle(source="yahoo_tw",external_id=i.findtext("link","") ,title=i.findtext("title","") ,content=html.unescape(re.sub(r"<[^>]+>","",i.findtext("description","") )),publish_time=parsedate_to_datetime(i.findtext("pubDate","")).astimezone(timezone.utc),symbols=[s.code],url=i.findtext("link","") ) for i in items]; break
        return out

class CnyesFlashNewsVendor(FlashNewsVendor):
    name="cnyes"; supports_markets={"TW"}
    def fetch(self,symbols,config):
        limit=max(1,min(int((config or {}).get("days") or 30),100)); data=tw_bulk.get_json("https://api.cnyes.com/media/api/v1/newslist/category/tw_stock",{"limit":limit}); out=[]
        for r in ((data.get("items") or {}).get("data") or []):
            out.append(FlashNews(source="cnyes",external_id=str(r.get("newsId")),title=str(r.get("title") or ""),content=re.sub(r"<[^>]+>","",html.unescape(str(r.get("content") or r.get("summary") or ""))),publish_time=datetime.fromtimestamp(int(r.get("publishAt") or 0),tz=timezone.utc),url=f"https://news.cnyes.com/news/id/{r.get('newsId')}"))
        return out
