"""台股 vendor 共用的字段、日期与资料取得工具。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from marketdata.vendors import tw_bulk

logger = logging.getLogger(__name__)

_TWSE = "https://openapi.twse.com.tw/v1/"
_TPEX = "https://www.tpex.org.tw/openapi/v1/"
_T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86"
_TDCC_URL = "https://opendata.tdcc.com.tw/getOD.ashx"
_MOPS_URL = "https://mops.twse.com.tw/mops/web/t05st01"

# 欄位名照官方回應原樣，含空白。
_TWSE_MATERIAL_TITLE = "主旨 "
_TPEX_FOREIGN_DIFF = "ForeignInvestorsInclude MainlandAreaInvestors-Difference"
_TPEX_FOREIGN_DIFF_ALT = "ForeignInvestorsIncludeMainlandAreaInvestors-Difference"


def _f(value):
    return tw_bulk.number(value)


def _code(value):
    return str(value or "").strip().upper()


def _tw_time(day, value):
    date_text = tw_bulk.tw_date(day)
    time_text = str(value or "0").strip().zfill(6)
    try:
        local_time = datetime.strptime(
            f"{date_text} {time_text}", "%Y-%m-%d %H%M%S"
        ).replace(tzinfo=timezone(timedelta(hours=8)))
    except ValueError:
        logger.debug("跳过时间格式无效的台股资料: date=%r time=%r", day, value)
        return None
    return local_time.astimezone(timezone.utc)


def _rows(url, *, params=None, ttl=1800):
    data = tw_bulk.get_json(url, params, ttl)
    return data if isinstance(data, list) else []


def _merge(fetch, symbols):
    wanted = {_code(symbol.code) for symbol in symbols}
    rows = []
    try:
        rows.extend(fetch("twse"))
    except Exception as exc:
        logger.warning("台股 TWSE 请求失败: %s", exc)
    try:
        rows.extend(fetch("tpex"))
    except Exception as exc:
        logger.warning("台股 TPEx 请求失败: %s", exc)
    return [row for row in rows if row.symbol in wanted]
