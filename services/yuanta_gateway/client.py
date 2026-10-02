"""元大 SparkAPI 唯讀行情用戶端。"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime
from typing import Any


MARKET_ENUM = {"TSE": "TWSE", "OTC": "TWOTC", "ESB": "TWEMERGING", "TAIFEX": "TAIFEX"}
KLINE_PERIOD = {"1m": 0, "5m": 1, "15m": 2, "30m": 3, "60m": 4, "1d": 11, "1w": 12, "1M": 13}


# 證券 S+11 碼、期貨 F+17 碼(例 FF021000P001234567);全 0 或「請填」為範例佔位字
_ACCOUNT_RE = re.compile(r"^(S\d{11}|F[0-9A-Z]{17})$")


def _credentials_look_valid(account: str, password: str, pfx_path: str, pfx_password: str) -> bool:
    if not (account and password and pfx_path and pfx_password):
        return False
    if not _ACCOUNT_RE.fullmatch(account) or set(account[1:]) == {"0"}:
        return False
    return not any("請填" in value or "请填" in value for value in (password, pfx_password))


class NotLoggedIn(Exception):
    """目前尚未登入元大 API。"""


class YuantaClient:
    def __init__(
        self,
        adapter: Any,
        *,
        account: str,
        password: str,
        pfx_path: str,
        pfx_password: str,
        env: str = "PROD",
        log_dir: str,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self._adapter = adapter
        self._account = account
        self._password = password
        self._pfx_path = pfx_path
        self._pfx_password = pfx_password
        self._env = env
        self._clock = clock
        self._sleep = sleep
        self._logger = logging.getLogger("yuanta_gateway.client")
        self._trader = adapter.create_trader(log_dir)
        adapter.subscribe(self._trader, self._on_response)

        self._state_lock = threading.RLock()
        self._connected = False
        self._logged_in = False
        self._last_error = ""
        # 帳密/憑證錯誤或停權後不再自動登入:元大有每日登入次數與黑名單機制
        self._auth_blocked = False
        self._last_login_failure: float | None = None
        self._pending: dict[str, dict[str, Any]] = {}
        self._function_locks: defaultdict[str, threading.RLock] = defaultdict(threading.RLock)
        self._last_call: dict[str, float] = {}

    def connect_and_login(self, timeout: float = 15) -> dict:
        with self._function_locks["Login"]:
            with self._state_lock:
                if self._logged_in or self._auth_blocked:
                    return self.status()
                if not _credentials_look_valid(self._account, self._password, self._pfx_path, self._pfx_password):
                    self._last_error = "missing_credentials"
                    self._auth_blocked = True
                    return self.status()
                last_failure = self._last_login_failure

            if last_failure is not None:
                remaining = 4.0 - (self._clock() - last_failure)
                if remaining > 0:
                    self._sleep(remaining)

            with self._state_lock:
                connected = self._connected
            if not connected:
                try:
                    self._trader.Open(self._adapter.env(self._env))
                except Exception as exc:
                    with self._state_lock:
                        self._connected = False
                        self._logged_in = False
                        self._last_error = f"connection error: {type(exc).__name__}"
                    return self.status()

            try:
                result = self._request(
                    "Login",
                    lambda: self._trader.Login(self._pfx_path, self._pfx_password, self._account, self._password),
                    timeout,
                )
            except TimeoutError:
                with self._state_lock:
                    self._logged_in = False
                    self._last_error = "Login timeout"
                    self._last_login_failure = self._clock()
                return self.status()
            except Exception as exc:
                with self._state_lock:
                    self._logged_in = False
                    safe_error = str(exc) if str(exc) in {"certificate error", "rate_limited", "suspended"} else ""
                    self._last_error = safe_error or f"Login error: {type(exc).__name__}"
                    self._last_login_failure = self._clock()
                    if safe_error in {"certificate error", "suspended"}:
                        self._auth_blocked = True
                return self.status()

            login_status = getattr(result, "LoginStatus", None)
            code = str(getattr(login_status, "MsgCode", ""))
            message = str(getattr(login_status, "MsgContent", "登入失敗"))
            with self._state_lock:
                if code == "0001":
                    self._connected = True
                    self._logged_in = True
                    self._last_error = ""
                else:
                    self._logged_in = False
                    self._last_error = f"{code or 'login_failed'} {message}".strip()
                    self._last_login_failure = self._clock()
                    self._auth_blocked = True
            return self.status()

    def _on_response(self, int_mark, dw_index, str_index, obj_handle, obj_value):
        del obj_handle
        mark = int(int_mark)
        index = int(dw_index)
        function = str(str_index or "")

        if mark == 0:
            if index == 1:
                with self._state_lock:
                    self._connected = True
            elif index in (2, 3):
                with self._state_lock:
                    self._connected = False
                    self._logged_in = False
                    self._last_error = "disconnected" if index == 2 else "network_error"

        error_text = {9: "certificate error", 13: "rate_limited", 14: "suspended"}.get(index)
        if error_text:
            with self._state_lock:
                self._last_error = error_text
                if index == 14:
                    self._logged_in = False
                if index in (9, 14):
                    self._auth_blocked = True

        if mark == 1 and function:
            with self._state_lock:
                waiter = self._pending.get(function)
                if waiter is not None:
                    waiter["value"] = obj_value
                    if error_text:
                        waiter["error"] = error_text
                    waiter["event"].set()

    def _request(self, function: str, invoke, timeout: float):
        with self._function_locks[function]:
            interval = 1.0 if function == "GetKLine" else 1.0 / 3.0
            previous = self._last_call.get(function)
            if previous is not None:
                remaining = interval - (self._clock() - previous)
                if remaining > 0:
                    self._sleep(remaining)

            waiter = {"event": threading.Event(), "value": None, "error": None}
            with self._state_lock:
                self._pending[function] = waiter
                self._last_call[function] = self._clock()
            try:
                invoke()
                if not waiter["event"].wait(timeout):
                    raise TimeoutError(f"{function} timeout")
                if waiter["error"]:
                    raise RuntimeError(waiter["error"])
                return waiter["value"]
            finally:
                with self._state_lock:
                    if self._pending.get(function) is waiter:
                        del self._pending[function]

    def quotes(self, items: list[tuple[str, str]], timeout: float = 10) -> list[dict]:
        if len(items) > 600:
            raise ValueError("每次最多查詢 600 筆報價")
        prepared = []
        for market, code in items:
            if market not in MARKET_ENUM:
                raise ValueError(f"未知市場: {market}")
            prepared.append((market, self._adapter.market(MARKET_ENUM[market]), str(code)))
        self._require_login()

        quote_list = self._adapter.build_quote_list([(market_enum, code) for _, market_enum, code in prepared])
        response = self._request(
            "GetWatchListAll",
            lambda: self._trader.GetWatchListAll(self._account, quote_list),
            timeout,
        )
        rows = getattr(response, "QueryWatchList", None)
        if rows is None:
            raise RuntimeError("報價回應格式錯誤")

        by_code: defaultdict[str, deque[str]] = defaultdict(deque)
        for market, _, code in prepared:
            by_code[code].append(market)
        result = []
        for index in range(int(rows.Count)):
            row = rows[index]
            code = str(getattr(row, "StkCode", ""))
            market = by_code[code].popleft() if by_code[code] else (prepared[0][0] if prepared else "")
            result.append({
                "market": market,
                "code": code,
                "name": str(getattr(row, "StkName", "")),
                "price": float(getattr(row, "DealPrice", 0) or 0),
                "prev_close": float(getattr(row, "YstPrice", 0) or 0),
                "open": float(getattr(row, "OpenPrice", 0) or 0),
                "high": float(getattr(row, "HighPrice", 0) or 0),
                "low": float(getattr(row, "LowPrice", 0) or 0),
                "volume": int(getattr(row, "TotalVol", 0) or 0),
                "limit_up": float(getattr(row, "UpStopPrice", 0) or 0),
                "limit_down": float(getattr(row, "DownStopPrice", 0) or 0),
                "bid": float(getattr(row, "BuyPrice", 0) or 0),
                "ask": float(getattr(row, "SellPrice", 0) or 0),
                "time": _quote_time(getattr(row, "Time", None)),
            })
        return result

    def kline(self, market: str, code: str, period: str, start: date, end: date, timeout: float = 15) -> list[dict]:
        if market not in MARKET_ENUM:
            raise ValueError(f"未知市場: {market}")
        if period not in KLINE_PERIOD:
            raise ValueError(f"未知 K 線週期: {period}")
        self._require_login()

        response = self._request(
            "GetKLine",
            lambda: self._trader.GetKLine(
                self._account,
                self._adapter.kline_type(KLINE_PERIOD[period]),
                self._adapter.market(MARKET_ENUM[market]),
                str(code),
                _sdk_date(start),
                _sdk_date(end),
            ),
            timeout,
        )
        rows = getattr(response, "KLineList", None)
        if rows is None:
            raise RuntimeError("K 線回應格式錯誤")
        return [
            {
                "time": _kline_time(rows[i].TimeStamp),
                "open": float(rows[i].OpenPrice),
                "high": float(rows[i].HighPrice),
                "low": float(rows[i].LowPrice),
                "close": float(rows[i].ClosePrice),
                "volume": int(rows[i].DealVol),
            }
            for i in range(int(rows.Count))
        ]

    def _require_login(self):
        with self._state_lock:
            if not self._logged_in:
                raise NotLoggedIn("尚未登入")

    def status(self) -> dict:
        with self._state_lock:
            return {
                "connected": self._connected,
                "logged_in": self._logged_in,
                "account": _mask_account(self._account),
                "last_error": self._last_error,
                "env": self._env,
                "retry_allowed": not self._auth_blocked,
            }

    def disable_login(self, reason: str):
        """設定不完整時停用登入(例如找不到憑證檔),原因顯示在 /health。"""
        with self._state_lock:
            self._last_error = reason
            self._auth_blocked = True

    def close(self):
        for method in ("Close", "Dispose"):
            try:
                getattr(self._trader, method)()
            except Exception as exc:
                self._logger.warning("關閉 SparkAPI %s 失敗 (%s)", method, type(exc).__name__)
        with self._state_lock:
            self._connected = False
            self._logged_in = False


def _mask_account(account: str) -> str:
    if len(account) <= 8:
        return "*" * len(account)
    return f"{account[:5]}****{account[-3:]}"


def _quote_time(value: Any) -> str:
    if value is None:
        return "00:00:00.000"
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, "%H:%M:%S.%f").time()
        except ValueError:
            return value
    hour = int(getattr(value, "Hour", getattr(value, "hour", 0)))
    minute = int(getattr(value, "Minute", getattr(value, "minute", 0)))
    second = int(getattr(value, "Second", getattr(value, "second", 0)))
    millis = int(getattr(value, "Millisecond", getattr(value, "microsecond", 0) // 1000))
    return f"{hour:02d}:{minute:02d}:{second:02d}.{millis:03d}"


def _sdk_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y/%m/%d")
    if isinstance(value, date):
        return value.strftime("%Y/%m/%d")
    if isinstance(value, str):
        parsed = datetime.strptime(value[:10].replace("-", "/"), "%Y/%m/%d")
        return parsed.strftime("%Y/%m/%d")
    year = int(getattr(value, "Year"))
    month = int(getattr(value, "Month"))
    day = int(getattr(value, "Day"))
    return f"{year:04d}/{month:02d}/{day:02d}"


def _kline_time(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).replace("/", "-")
        parsed = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None and all(hasattr(value, part) for part in ("Year", "Month", "Day")):
            parsed = datetime(
                int(value.Year), int(value.Month), int(value.Day),
                int(getattr(value, "Hour", 0)), int(getattr(value, "Minute", 0)),
                int(getattr(value, "Second", 0)), int(getattr(value, "Millisecond", 0)) * 1000,
            )
        if parsed is None:
            raise ValueError("無法解析 K 線時間")
    return parsed.strftime("%Y-%m-%d %H:%M:%S")
