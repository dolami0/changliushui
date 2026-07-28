"""万业谱预研管线调度器 — 两条独立管线轮询

管线 A (天机卷): 每 30 分钟轮询
管线 B (产业链): 每 45 分钟轮询（错开 15 分钟）

在 server.py 的 lifespan 中启动/停止。
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
_log_file = Path(__file__).resolve().parent.parent / "wanyepu_scheduler.log"
_handler = logging.FileHandler(str(_log_file), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(logging.Formatter("[WANYEPU %(levelname)s] %(message)s"))
logger.addHandler(_stderr_handler)


class WanyepuScheduler:
    """万业谱预研管线调度器 — 两条独立管线轮询。"""

    def __init__(self, config: dict):
        self.interval_a = config.get("wanyepu_tianji_interval_sec", 1800)   # 30 分钟
        self.interval_b = config.get("wanyepu_industry_interval_sec", 2700)  # 45 分钟
        self._running = False
        self._task_a: asyncio.Task | None = None
        self._task_b: asyncio.Task | None = None
        self.last_poll_a: str | None = None
        self.last_poll_b: str | None = None
        self.next_poll_a: str | None = None
        self.next_poll_b: str | None = None
        self.active_jobs: list[dict] = []
        self.completed_jobs: list[dict] = []

    async def start(self):
        """启动两条管线轮询。"""
        self._running = True
        self._task_a = asyncio.create_task(self._loop_a())
        self._task_b = asyncio.create_task(self._loop_b())
        logger.info(f"万业谱调度器已启动: 管线A {self.interval_a}s, 管线B {self.interval_b}s")

    async def stop(self):
        """停止两条管线轮询。"""
        self._running = False
        for task in (self._task_a, self._task_b):
            if task and not task.done():
                task.cancel()
        logger.info("万业谱调度器已停止")

    @staticmethod
    def _wait_until_minute(minute: int) -> float:
        """计算到下一个整点第 minute 分的等待秒数。"""
        now = datetime.now()
        target = now.replace(minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(hours=1)
        return (target - now).total_seconds()

    async def _loop_a(self):
        """管线 A (天机卷): 每个整点的第 30 分触发。"""
        await asyncio.sleep(5)  # 启动延迟，让 server 先起来
        while self._running:
            wait_sec = self._wait_until_minute(30)
            next_time = datetime.now(timezone.utc) + timedelta(seconds=wait_sec)
            self.next_poll_a = next_time.isoformat()
            logger.info(f"管线A下次轮询: {next_time.isoformat()} (等待 {wait_sec:.0f}s)")
            await asyncio.sleep(wait_sec)
            if not self._running:
                break
            try:
                await self._poll_tianji()
            except Exception as e:
                logger.error(f"管线A轮询异常: {e}")

    async def _loop_b(self):
        """管线 B (产业链): 每个整点的第 45 分触发。"""
        await asyncio.sleep(5)  # 启动延迟
        while self._running:
            wait_sec = self._wait_until_minute(45)
            next_time = datetime.now(timezone.utc) + timedelta(seconds=wait_sec)
            self.next_poll_b = next_time.isoformat()
            logger.info(f"管线B下次轮询: {next_time.isoformat()} (等待 {wait_sec:.0f}s)")
            await asyncio.sleep(wait_sec)
            if not self._running:
                break
            try:
                await self._poll_industry()
            except Exception as e:
                logger.error(f"管线B轮询异常: {e}")

    async def _poll_tianji(self):
        """管线 A: 天机卷轮询。"""
        self.last_poll_a = datetime.now(timezone.utc).isoformat()
        logger.info("管线A开始轮询...")

        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
            from wanyepu_v2.pipeline import run_tianji_pipeline

            results = await asyncio.to_thread(run_tianji_pipeline, limit=3, verbose=False)

            if results:
                logger.info(f"管线A完成: {len(results)} 条记录")
                for r in results:
                    self.completed_jobs.append({
                        "pipeline": "tianji",
                        "stock_code": r.get("stock_code", ""),
                        "stock_name": r.get("stock_name", ""),
                        "elapsed_s": r.get("elapsed", 0),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    })
            else:
                logger.info("管线A: 无待处理记录")
        except Exception as e:
            logger.error(f"管线A处理异常: {e}")

    async def _poll_industry(self):
        """管线 B: 产业链轮询。"""
        self.last_poll_b = datetime.now(timezone.utc).isoformat()
        logger.info("管线B开始轮询...")

        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
            from wanyepu_v2.pipeline import run_industry_pipeline

            results = await asyncio.to_thread(run_industry_pipeline, limit=3, verbose=False)

            if results:
                logger.info(f"管线B完成: {len(results)} 条记录")
                for r in results:
                    self.completed_jobs.append({
                        "pipeline": "industry",
                        "stock_code": r.get("stock_code", ""),
                        "stock_name": r.get("stock_name", ""),
                        "elapsed_s": r.get("elapsed", 0),
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    })
            else:
                logger.info("管线B: 无待处理记录")
        except Exception as e:
            logger.error(f"管线B处理异常: {e}")

    async def poll_now_a(self) -> list[dict]:
        """手动触发管线 A。"""
        await self._poll_tianji()
        return self.completed_jobs

    async def poll_now_b(self) -> list[dict]:
        """手动触发管线 B。"""
        await self._poll_industry()
        return self.completed_jobs
