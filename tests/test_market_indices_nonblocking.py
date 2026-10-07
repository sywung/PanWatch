"""首页指数端点不得阻塞 event loop（2026-10-07：冷缓存时同步取 MIS 卡住整台服务 12.5 秒）。"""
import asyncio
import time

import src.modules.market.api.market as mkt


class _SlowMD:
    def tw_index_quotes(self):
        time.sleep(0.5)
        return []

    def index_quotes(self, tencent_symbols):
        time.sleep(0.5)
        return []


async def _run_with_ticker():
    ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal ticks
        while not done.is_set():
            await asyncio.sleep(0.02)
            ticks += 1

    t = asyncio.create_task(ticker())
    started = time.perf_counter()
    out = await mkt.get_market_indices()
    elapsed = time.perf_counter() - started
    done.set()
    await t
    return out, ticks, elapsed


def test_indices_fetch_does_not_block_event_loop(monkeypatch):
    mkt.clear_indices_cache()
    monkeypatch.setattr(mkt, "get_market_data", lambda: _SlowMD())
    monkeypatch.setattr(mkt, "get_index_klines", lambda *a, **k: [])

    out, ticks, elapsed = asyncio.run(_run_with_ticker())

    assert isinstance(out, list)
    # 同步实现会把 loop 卡满 ~1s，ticker 只能跑 0~1 次
    assert ticks >= 10, f"event loop blocked: only {ticks} ticks in {elapsed:.2f}s"


def test_tw_and_other_index_quotes_fetched_concurrently(monkeypatch):
    mkt.clear_indices_cache()
    monkeypatch.setattr(mkt, "get_market_data", lambda: _SlowMD())
    monkeypatch.setattr(mkt, "get_index_klines", lambda *a, **k: [])

    _, _, elapsed = asyncio.run(_run_with_ticker())
    assert elapsed < 0.9, f"tw + tencent should run in parallel, took {elapsed:.2f}s"
