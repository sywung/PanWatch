"""价格提醒调度器：独立于 Agent 调度。"""

from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.modules.market.price_alert_engine import ENGINE
from src.modules.market.alert_delivery import AlertDeliveryWorker

logger = logging.getLogger(__name__)


class PriceAlertScheduler:
    def __init__(self, timezone: str = "UTC", interval_seconds: int = 60):
        self.scheduler = AsyncIOScheduler(timezone=timezone)
        self.interval_seconds = max(15, int(interval_seconds))
        self._running = False
        self._delivering = False
        self.delivery_worker = AlertDeliveryWorker()

    async def _delivery_job(self):
        if self._delivering:
            return
        self._delivering = True
        try:
            await self.delivery_worker.drain()
        except Exception:
            logger.exception("[价格提醒] 投递队列处理失败")
        finally:
            self._delivering = False

    async def _scan_job(self):
        if self._running:
            logger.debug("[价格提醒] 上轮扫描仍在执行，跳过本轮")
            return
        self._running = True
        try:
            result = await ENGINE.scan_once()
            triggered = result.get("triggered", 0)
            # 实际触发了告警才是业务事件,否则只是心跳。
            level = logging.INFO if triggered else logging.DEBUG
            logger.log(
                level,
                "[价格提醒] 扫描完成: rules=%s triggered=%s skipped=%s",
                result.get("total_rules", 0),
                triggered,
                result.get("skipped", 0),
            )
        except Exception as e:
            logger.exception(f"[价格提醒] 扫描异常: {e}")
        finally:
            self._running = False

    async def _rollover_job(self):
        try:
            from src.modules.portfolio.futures_rollover import run_rollover_check

            result = await run_rollover_check()
            logger.info("[期货转仓提醒] 扫描完成: %s", result)
        except Exception as e:
            logger.exception(f"[期货转仓提醒] 扫描异常: {e}")

    async def _shareholder_dispersion_job(self):
        try:
            from src.modules.market.shareholder_dispersion import collect_watchlist
            from src.platform.persistence.database import SessionLocal

            def collect():
                with SessionLocal() as db:
                    return collect_watchlist(db)

            count = await asyncio.to_thread(collect)
            logger.info("[集保股權分散] 每日收集完成: 新增=%s", count)
        except Exception as exc:
            logger.exception("[集保股權分散] 每日收集异常: %s", exc)

    async def trigger_once(self, *, dry_run: bool = False, rule_id: int | None = None) -> dict:
        return await ENGINE.scan_once(
            dry_run=dry_run, only_rule_id=rule_id, bypass_market_hours=True
        )

    def register_jobs(self):
        self.scheduler.add_job(
            self._delivery_job, "interval", seconds=10,
            id="price_alert_delivery", replace_existing=True,
            coalesce=True, max_instances=1,
        )
        self.scheduler.add_job(
            self._scan_job,
            "interval",
            seconds=self.interval_seconds,
            jitter=20,  # 抖动错峰,避免与模拟盘扫描每 60s 同刻并发写 SQLite
            id="price_alert_scan",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        taipei = ZoneInfo("Asia/Taipei")
        self.scheduler.add_job(
            self._rollover_job,
            CronTrigger(day_of_week="mon-fri", hour=8, minute=45, timezone=taipei),
            id="futures_rollover_morning",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._rollover_job,
            CronTrigger(day_of_week="mon-fri", hour=12, minute=30, timezone=taipei),
            id="futures_rollover_noon",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self.scheduler.add_job(
            self._shareholder_dispersion_job,
            CronTrigger(hour=6, minute=30, timezone=taipei),
            id="shareholder_dispersion_daily",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    def start(self):
        self.register_jobs()
        self.scheduler.start()
        from src.platform.scheduling.scheduler_registry import register
        register("price_alert", self.scheduler)
        logger.info(f"价格提醒调度器已启动，扫描间隔 {self.interval_seconds}s")

    def shutdown(self):
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass
        logger.info("价格提醒调度器已关闭")
