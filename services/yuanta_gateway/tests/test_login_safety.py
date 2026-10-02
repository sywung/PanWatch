"""登入安全:错误帐密/凭证不得反复重试(元大有每日登入次数与黑名单/停权机制)。"""

from __future__ import annotations

import threading

from fakes import FakeAdapter, login_fail, login_ok

import app as gateway
import client as yc


class Clock:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _client(**creds):
    a = FakeAdapter()
    clock = Clock()
    base = dict(account="S98875005091", password="pw", pfx_path="/config/cert.pfx", pfx_password="pfxpw")
    base.update(creds)
    c = yc.YuantaClient(a, env="PROD", log_dir="/tmp/ylog", clock=clock.now, sleep=clock.sleep, **base)
    return c, a


def _logins(a):
    return [x for x in a.calls if x[0] == "Login"]


def _answer_later(a, value, name="Login", mark=1, index=0):
    threading.Timer(0.05, a.respond, args=(mark, index, name, value)).start()


def test_missing_credentials_never_calls_login():
    c, a = _client(password="")
    st = c.connect_and_login(timeout=0.2)
    assert _logins(a) == []
    assert st["last_error"] == "missing_credentials"
    assert st["retry_allowed"] is False


def test_wrong_password_blocks_further_attempts():
    c, a = _client()
    _answer_later(a, login_fail("0102", "密碼凍結或未啟用"))
    c.connect_and_login(timeout=2)
    assert c.status()["retry_allowed"] is False
    c.connect_and_login(timeout=0.2)
    assert len(_logins(a)) == 1          # 第二次没有再打元大


def test_certificate_error_blocks_retry():
    c, a = _client()
    _answer_later(a, "憑證異常", name="", index=9)
    c.connect_and_login(timeout=0.3)
    assert c.status()["retry_allowed"] is False


def test_suspension_blocks_retry():
    c, a = _client()
    _answer_later(a, login_ok())
    c.connect_and_login(timeout=2)
    a.respond(0, 14, "", "停權")
    assert c.status()["logged_in"] is False
    assert c.status()["retry_allowed"] is False


def test_timeout_and_disconnect_allow_retry():
    c, a = _client()
    c.connect_and_login(timeout=0.2)                 # 无回应 → 逾时
    assert c.status()["retry_allowed"] is True
    _answer_later(a, login_ok())
    c.connect_and_login(timeout=2)
    a.respond(0, 2, "", "Disconnect")
    assert c.status()["retry_allowed"] is True


def test_default_port_is_2885(monkeypatch):
    monkeypatch.delenv("GATEWAY_PORT", raising=False)
    assert gateway.gateway_port() == 2885
    monkeypatch.setenv("GATEWAY_PORT", "9000")
    assert gateway.gateway_port() == 9000


def test_placeholder_values_are_treated_as_missing():
    """範例 env 檔沒改就啟動:不得拿佔位字去元大登入(會算一次失敗登入)。"""
    for creds in ({"password": "請填登入密碼"}, {"pfx_password": "請填憑證密碼"},
                  {"account": "S00000000000"}, {"account": "12345"}):
        c, a = _client(**creds)
        st = c.connect_and_login(timeout=0.2)
        assert _logins(a) == [], creds
        assert st["last_error"] == "missing_credentials"


def test_futures_account_format_is_accepted():
    c, a = _client(account="FF021000P001234567")
    _answer_later(a, login_ok("FF021000P001234567"))
    c.connect_and_login(timeout=2)
    assert len(_logins(a)) == 1


def test_branch_code_with_letters_is_accepted():
    """元大分公司代號可含英文字母(官方範例 S981r1691656)。"""
    c, a = _client(account="S981r1691656")
    _answer_later(a, login_ok("S981r1691656"))
    c.connect_and_login(timeout=2)
    assert len(_logins(a)) == 1


def test_login_waits_for_trade_host_connection():
    """實測:Open 後要等「交易主機 Is Connected」才能登入,太早送會被丟掉、等到逾時。"""
    c, a = _client()
    a.connect_on_open = False
    st = c.connect_and_login(timeout=0.3, connect_timeout=0.2)
    assert _logins(a) == []
    assert st["last_error"] == "connect timeout"
    assert st["retry_allowed"] is True
