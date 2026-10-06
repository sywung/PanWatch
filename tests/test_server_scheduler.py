"""服务启动时的调度任务注册契约。"""

from types import SimpleNamespace
from unittest.mock import Mock


def test_mcp_log_cleanup_is_registered_on_wrapped_apscheduler(monkeypatch):
    import server
    from src.modules.administration.api import mcp

    prune = Mock(name="prune_mcp_logs")
    monkeypatch.setattr(mcp, "prune_mcp_logs", prune)
    scheduler = SimpleNamespace(scheduler=Mock())

    server.register_mcp_log_cleanup(scheduler)

    scheduler.scheduler.add_job.assert_called_once_with(
        prune,
        "cron",
        hour=4,
        minute=0,
        id="mcp_log_retention",
        replace_existing=True,
    )


def test_reload_scheduler_from_worker_thread_restarts_on_event_loop(monkeypatch):
    """同步端點（threadpool）呼叫 reload_scheduler 時，新排程器必須真的在主事件迴圈上啟動。

    AsyncIOScheduler.start() 需要 running loop；在 worker thread 直接呼叫會失敗，
    而舊排程器已先被關掉 → 所有 Agent 停止排程直到重啟。
    """
    import asyncio

    import server
    from src.modules.automation.agent_scheduler import AgentScheduler

    monkeypatch.setattr(server, "build_scheduler", lambda: AgentScheduler())

    async def scenario():
        monkeypatch.setattr(server, "_main_loop", asyncio.get_running_loop(), raising=False)
        old = AgentScheduler()
        old.start()
        monkeypatch.setattr(server, "scheduler", old)

        ok = await asyncio.to_thread(server.reload_scheduler)
        await asyncio.sleep(0.05)
        new = server.scheduler
        try:
            assert ok is True
            assert new is not old
            assert new.scheduler.running
            assert not old.scheduler.running
        finally:
            for s in (new, old):
                if s.scheduler.running:
                    s.scheduler.shutdown(wait=False)

    asyncio.run(scenario())
