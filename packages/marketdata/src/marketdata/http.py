"""统一 HTTP 工具:走系统代理(trust_env=True)+ 按 host 节流 + 退避重试 + 来源标记。

默认 trust_env=True —— 遵循进程 env 的 HTTP_PROXY/NO_PROXY(宿主按 UI 的 http_proxy 设置统一注入);
没配代理时即直连。个别调用可用 proxy= 显式覆盖。
"""

from __future__ import annotations

import contextvars
import logging
import random
import threading
import time
from contextlib import contextmanager
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_FETCH_SOURCE: contextvars.ContextVar[str] = contextvars.ContextVar("fetch_source", default="")


@contextmanager
def fetch_source(name: str):
    """标注取数来源,写入失败日志便于定位触发方。"""
    token = _FETCH_SOURCE.set(name or "")
    try:
        yield
    finally:
        _FETCH_SOURCE.reset(token)


def source_suffix() -> str:
    src = _FETCH_SOURCE.get()
    return f" [src={src}]" if src else ""


# 失败原因收集:默认 None = 不收集(生产热路径零开销)。数据源"测试"按钮用 capture_errors()
# 包住取数调用,把 market_get / vendor 的真实失败原因收上来透到 UI,而不是只显示"无数据"。
_ERROR_SINK: contextvars.ContextVar[list | None] = contextvars.ContextVar("md_error_sink", default=None)


@contextmanager
def capture_errors():
    """进入后,market_get / record_error 的失败原因会被收集到 yield 出的 list。"""
    errs: list[str] = []
    token = _ERROR_SINK.set(errs)
    try:
        yield errs
    finally:
        _ERROR_SINK.reset(token)


def record_error(msg: str) -> None:
    """把一条失败原因写入当前 capture_errors 上下文(无上下文则忽略)。
    供 vendor 自己 catch 异常(如 yfinance 走库、不经 market_get)时也能上报真因。"""
    sink = _ERROR_SINK.get()
    if sink is not None and msg:
        sink.append(msg)


_THROTTLE_LOCK = threading.Lock()
_THROTTLE_HOST_LOCKS: dict[str, threading.Lock] = {}
_last_call: dict[str, float] = {}


class _CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_s: float):
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self.failures = 0
        self.open_until: float | None = None
        self.probe_in_flight = False


_CIRCUIT_LOCK = threading.Lock()
_CIRCUIT_BREAKERS: dict[str, _CircuitBreaker] = {}


def register_circuit_breaker(host_key: str, failure_threshold: int, cooldown_s: float) -> None:
    """为 host 启用连续失败熔断。重复注册会更新配置并重置该 host 状态。"""
    with _CIRCUIT_LOCK:
        _CIRCUIT_BREAKERS[host_key] = _CircuitBreaker(
            failure_threshold=max(1, int(failure_threshold)),
            cooldown_s=max(0.0, float(cooldown_s)),
        )


def circuit_breaker_config(host_key: str) -> tuple[int, float] | None:
    """返回 host 的熔断配置；未注册时返回 None。"""
    with _CIRCUIT_LOCK:
        breaker = _CIRCUIT_BREAKERS.get(host_key)
        if breaker is None:
            return None
        return breaker.failure_threshold, breaker.cooldown_s


def reset_circuit_breakers() -> None:
    """清除所有 host 的熔断状态(失败计数、开路、探测中),保留注册配置。供测试隔离使用。"""
    with _CIRCUIT_LOCK:
        for breaker in _CIRCUIT_BREAKERS.values():
            breaker.failures = 0
            breaker.open_until = None
            breaker.probe_in_flight = False


def _acquire_circuit(host_key: str) -> tuple[_CircuitBreaker | None, bool, str | None]:
    """返回 (状态, 是否为半开探测, 拒绝原因)。"""
    with _CIRCUIT_LOCK:
        breaker = _CIRCUIT_BREAKERS.get(host_key)
        if breaker is None or breaker.open_until is None:
            return breaker, False, None

        if time.monotonic() < breaker.open_until:
            return breaker, False, f"{host_key} 熔断中，冷却期尚未结束"
        if breaker.probe_in_flight:
            return breaker, False, f"{host_key} 熔断半开，探测请求进行中"

        breaker.probe_in_flight = True
        return breaker, True, None


def _finish_circuit(breaker: _CircuitBreaker | None, *, success: bool, probe: bool, host_key: str) -> None:
    if breaker is None:
        return
    with _CIRCUIT_LOCK:
        # reset/register may have replaced this state while its request was in flight.
        if _CIRCUIT_BREAKERS.get(host_key) is not breaker:
            return
        if success:
            breaker.failures = 0
            if probe:
                breaker.open_until = None
                breaker.probe_in_flight = False
                logger.info(f"{host_key} 半开探测成功,熔断解除")
            return

        if probe:
            breaker.probe_in_flight = False
            breaker.failures = breaker.failure_threshold
            breaker.open_until = time.monotonic() + breaker.cooldown_s
            logger.warning(f"{host_key} 半开探测失败,继续熔断 {breaker.cooldown_s:.0f}s")
        else:
            breaker.failures += 1
            if breaker.failures >= breaker.failure_threshold:
                was_closed = breaker.open_until is None
                breaker.failures = breaker.failure_threshold
                breaker.open_until = time.monotonic() + breaker.cooldown_s
                if was_closed:
                    logger.warning(
                        f"{host_key} 连续失败 {breaker.failure_threshold} 次,熔断 {breaker.cooldown_s:.0f}s"
                    )


def throttle(host_key: str, min_interval_s: float) -> None:
    """保证对同一 host 的请求间隔 ≥ min_interval_s。"""
    if min_interval_s <= 0:
        return
    with _THROTTLE_LOCK:
        host_lock = _THROTTLE_HOST_LOCKS.setdefault(host_key, threading.Lock())
    with host_lock:
        wait = min_interval_s - (time.time() - _last_call.get(host_key, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_call[host_key] = time.time()


def market_get(
    url: str,
    *,
    host_key: str,
    params: dict | None = None,
    headers: dict | None = None,
    min_interval_s: float = 0.0,
    timeout: float = 10.0,
    retries: int = 2,
    backoff: float = 0.4,
    jitter: float = 0.25,
    parse: str = "text",   # "text" | "json" | "content" | "response"
    encoding: str | None = None,
    symbol: str = "",
    log_label: str = "",
    raise_for_status: bool = True,
    trust_env: bool = True,
    follow_redirects: bool = True,
    verify: bool = True,
    proxy: str | None = None,
) -> Any | None:
    """走系统代理(env)+ 按 host 节流 + 退避重试。成功返回解析结果,失败返回 None 并打带来源日志。

    parse="response" 会返回原始 HTTP response,供需要区分状态码的业务调用方使用。

    proxy: 显式代理,仅在给了值时传给 httpx.Client 覆盖 env 代理;不传则遵循 trust_env(env)。
    """
    return _market_request(
        "GET", url, host_key=host_key, params=params, headers=headers,
        min_interval_s=min_interval_s, timeout=timeout, retries=retries,
        backoff=backoff, jitter=jitter, parse=parse, encoding=encoding,
        symbol=symbol, log_label=log_label, raise_for_status=raise_for_status,
        trust_env=trust_env, follow_redirects=follow_redirects, verify=verify,
        proxy=proxy,
    )


def market_post(
    url: str,
    *,
    host_key: str,
    json_body: Any,
    params: dict | None = None,
    headers: dict | None = None,
    min_interval_s: float = 0.0,
    timeout: float = 10.0,
    retries: int = 2,
    backoff: float = 0.4,
    jitter: float = 0.25,
    parse: str = "text",
    encoding: str | None = None,
    symbol: str = "",
    log_label: str = "",
    raise_for_status: bool = True,
    trust_env: bool = True,
    follow_redirects: bool = True,
    verify: bool = True,
    proxy: str | None = None,
) -> Any | None:
    """以 JSON body 发送 POST,沿用 market_get 的节流、重试与错误记录。"""
    return _market_request(
        "POST", url, host_key=host_key, params=params, json_body=json_body,
        headers=headers, min_interval_s=min_interval_s, timeout=timeout,
        retries=retries, backoff=backoff, jitter=jitter, parse=parse,
        encoding=encoding, symbol=symbol, log_label=log_label,
        raise_for_status=raise_for_status, trust_env=trust_env,
        follow_redirects=follow_redirects, verify=verify, proxy=proxy,
    )


def _market_request(
    method: str,
    url: str,
    *,
    host_key: str,
    params: dict | None = None,
    json_body: Any = None,
    headers: dict | None = None,
    min_interval_s: float = 0.0,
    timeout: float = 10.0,
    retries: int = 2,
    backoff: float = 0.4,
    jitter: float = 0.25,
    parse: str = "text",
    encoding: str | None = None,
    symbol: str = "",
    log_label: str = "",
    raise_for_status: bool = True,
    trust_env: bool = True,
    follow_redirects: bool = True,
    verify: bool = True,
    proxy: str | None = None,
) -> Any | None:
    """共用 HTTP 请求、解析及失败处理。"""
    effective_proxy = proxy
    last_err: Any = None
    breaker, probe, rejected_reason = _acquire_circuit(host_key)
    if rejected_reason is not None:
        label = log_label or host_key
        record_error(f"{label}: {rejected_reason}")
        return None

    attempts = 1 if probe else max(1, retries + 1)
    for attempt in range(attempts):
        throttle(host_key, min_interval_s)
        try:
            with httpx.Client(
                follow_redirects=follow_redirects,
                timeout=timeout + attempt * 4,
                headers=headers,
                trust_env=trust_env,
                verify=verify,
                **({"proxy": effective_proxy} if effective_proxy else {}),
            ) as client:
                if method == "POST":
                    resp = client.post(url, params=params, json=json_body)
                else:
                    resp = client.get(url, params=params)
                if raise_for_status:
                    resp.raise_for_status()
                if parse == "response":
                    result = resp
                elif parse == "json":
                    result = resp.json()
                elif parse == "content":
                    result = resp.content
                elif encoding:
                    result = resp.content.decode(encoding, errors="ignore")
                else:
                    result = resp.text
                _finish_circuit(breaker, success=True, probe=probe, host_key=host_key)
                return result
        except Exception as e:
            last_err = e
        if attempt + 1 < attempts:
            time.sleep(backoff * (attempt + 1) + random.uniform(0, jitter))

    if last_err is not None:
        label = log_label or host_key
        sym = f" symbol={symbol}" if symbol else ""
        logger.warning(f"{label} 获取失败{sym}: {last_err}{source_suffix()}")
        record_error(f"{label}{sym}: {type(last_err).__name__}: {last_err}")
    _finish_circuit(breaker, success=False, probe=probe, host_key=host_key)
    return None
