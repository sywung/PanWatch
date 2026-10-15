"""集保官網股權分散表歷史查詢。"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from html.parser import HTMLParser

import httpx

logger = logging.getLogger(__name__)

_QUERY_URL = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_SESSION = httpx.Client(
    headers={"User-Agent": _USER_AGENT}, timeout=30, follow_redirects=True,
)
_CODE_RE = re.compile(r"^[0-9A-Za-z]{1,10}$")
_ROC_DATE_RE = re.compile(r"資料日期\s*[:：]\s*(\d{2,3})年\s*(\d{1,2})月\s*(\d{1,2})日")


def _http(method: str, url: str, data: dict | None = None) -> str:
    """唯一網路入口；共用 Client 以延續集保站 cookie。"""
    response = _SESSION.request(method.upper(), url, data=data, timeout=30)
    response.raise_for_status()
    return response.text


class _PageParser(HTMLParser):
    """收集日期下拉、hidden 欄位、表格列與可見文字。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dates: list[str] = []
        self.hidden: dict[str, str] = {}
        self.rows: list[list[str]] = []
        self.text: list[str] = []
        self._in_dates = False
        self._option_value: str | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self._in_dates = attrs.get("id") == "scaDate"
        elif tag == "option" and self._in_dates:
            self._option_value = attrs.get("value")
        elif tag == "input" and attrs.get("name"):
            if attrs.get("type", "").lower() == "hidden":
                self.hidden[attrs["name"]] = attrs.get("value", "")
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "option" and self._in_dates:
            raw = str(self._option_value or "").strip()
            if re.fullmatch(r"\d{8}", raw):
                try:
                    self.dates.append(datetime.strptime(raw, "%Y%m%d").date().isoformat())
                except ValueError:
                    pass
            self._option_value = None
        elif tag == "select":
            self._in_dates = False
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        self.text.append(data)
        if self._option_value is not None:
            return
        if self._cell is not None:
            self._cell.append(data)


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(html or "")
    parser.close()
    return parser


def parse_dates(html: str) -> list[str]:
    """解析 scaDate 選單中的週別，維持官網的新到舊排序。"""
    return _parse(html).dates


def _number(text: str, *, integer: bool) -> int | float:
    value = re.sub(r"[\s,]", "", text)
    if not value or value in {"-", "--", "—"}:
        return 0 if integer else 0.0
    if integer:
        return int(float(value))
    return float(value)


def parse_result(html: str) -> tuple[str, list[dict]] | None:
    """解析單週結果；無資料、空表或回到查詢表單時回傳 None。"""
    if not html:
        return None
    parser = _parse(html)
    page_text = "".join(parser.text)
    if "查無此資料" in page_text:
        return None

    match = _ROC_DATE_RE.search(page_text)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    try:
        date_text = datetime(year + 1911, month, day).date().isoformat()
    except ValueError:
        return None

    level_rows: list[list[str]] = []
    adjustment_row: list[str] | None = None
    total_row: list[str] | None = None
    try:
        for cells in parser.rows:
            if len(cells) < 5 or not re.fullmatch(r"\d+", cells[0]):
                continue
            label = re.sub(r"\s+", "", cells[1])
            if "差異數調整" in label:
                if adjustment_row is not None:
                    return None
                adjustment_row = cells
            elif "合" in label and "計" in label:
                if total_row is not None:
                    return None
                total_row = cells
            else:
                level_rows.append(cells)
    except (TypeError, ValueError, OverflowError):
        return None

    if len(level_rows) != 15 or total_row is None:
        return None

    def make_level(level: int, cells: list[str]) -> dict:
        return {
            "level": level,
            "holders": _number(cells[2], integer=True),
            "shares": _number(cells[3], integer=True),
            "pct": float(_number(cells[4], integer=False)) + 0.0,  # +0.0 把 "-0.00" 的 -0.0 正規化成 0.0
        }

    try:
        levels = [make_level(level, cells) for level, cells in enumerate(level_rows, start=1)]
        levels.append(
            make_level(16, adjustment_row)
            if adjustment_row is not None
            else {"level": 16, "holders": 0, "shares": 0, "pct": 0.0}
        )
        levels.append(make_level(17, total_row))
    except (TypeError, ValueError, OverflowError):
        return None
    return date_text, levels


def fetch_history(
    code: str,
    weeks: int = 52,
    skip_dates=(),
    *,
    delay: float = 0.15,
) -> list[tuple[str, list[dict]]]:
    """逐週查詢近期集保資料，遇到網路錯誤時保留已取得的部分。"""
    symbol = str(code or "").strip()
    if not _CODE_RE.fullmatch(symbol):
        return []

    try:
        form = _http("GET", _QUERY_URL)
    except Exception as exc:
        logger.warning("TDCC 官網歷史資料查詢失敗 (%s): %s", symbol, exc)
        return []

    parser = _parse(form)
    dates = parser.dates
    token = parser.hidden.get("SYNCHRONIZER_TOKEN")
    if not dates or not token:
        return []

    limit = max(0, min(int(weeks), len(dates)))
    skip = {str(value) for value in skip_dates}
    selected = [date for date in dates[:limit] if date not in skip]
    results: list[tuple[str, list[dict]]] = []
    requests_made = 0

    for date in selected:
        if requests_made:
            time.sleep(delay)
        data = {
            "SYNCHRONIZER_TOKEN": token,
            "SYNCHRONIZER_URI": "/portal/zh/smWeb/qryStock",
            "method": "submit",
            "firDate": dates[0].replace("-", ""),
            "scaDate": date.replace("-", ""),
            "sqlMethod": "StockNo",
            "stockNo": symbol,
            "stockName": "",
        }
        try:
            response_html = _http("POST", _QUERY_URL, data=data)
        except Exception as exc:
            logger.warning("TDCC 官網歷史資料查詢中斷 (%s, %s): %s", symbol, date, exc)
            break
        requests_made += 1

        response_parser = _parse(response_html)
        token = response_parser.hidden.get("SYNCHRONIZER_TOKEN", "")
        result = parse_result(response_html)
        if result is None:
            # 首週即無資料代表代號不存在或官網回了空表單；不再逐週重試。
            if not results:
                return []
            logger.warning("TDCC 官網歷史資料查詢中斷 (%s, %s): 無法解析結果頁", symbol, date)
            break
        results.append(result)
        if not token and date != selected[-1]:
            logger.warning("TDCC 官網歷史資料查詢中斷 (%s, %s): 回應未包含後續查詢 token", symbol, date)
            break

    return results
