"""天机峰调度器 — 快讯筛选打标 + 研报处理 双管线调度器

A 管线: 快讯（东方财富+36氪）→ 快讯池 → 四步 LLM → 天机卷 (每 10 分钟)
B 管线: 研报（棱镜内参）→ 种子探测 → 火山搜索 → 守门员 → 天机卷 (每 30 分钟)

在 server.py 的 lifespan 中启动/停止。
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)
_log_file = Path(__file__).resolve().parent.parent / "tianjifeng_scheduler.log"
_handler = logging.FileHandler(str(_log_file), encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setFormatter(logging.Formatter("[TIANJIFENG %(levelname)s] %(message)s"))
logger.addHandler(_stderr_handler)


class TianjifengScheduler:
    """天机峰调度器 — 快讯 + 研报 双管线轮询。"""

    def __init__(self, coze_client, config: dict, progress_cb: Callable | None = None):
        self.coze = coze_client
        self.config = config
        self.progress_cb = progress_cb
        self.interval = config.get("tianjifeng_poll_interval_sec", 600)
        self.max_news = config.get("tianjifeng_max_news_per_cycle", 50)
        self.full_write_level = config.get("tianjifeng_full_write_level", 4)
        self.yanbao_interval = config.get("tianjifeng_yanbao_interval_sec", 1800)
        self.yanbao_max = config.get("tianjifeng_yanbao_max_per_cycle", 10)
        self.yanbao_parallel = config.get("tianjifeng_yanbao_parallel", 5)
        self._running = False
        self._task_a: asyncio.Task | None = None
        self._task_b: asyncio.Task | None = None
        self.last_poll_at: str | None = None
        self.next_poll_at: str | None = None
        self.last_yanbao_at: str | None = None
        self.next_yanbao_at: str | None = None
        self.current_status: str = "idle"
        self.active_jobs: list[dict] = []
        self.completed_jobs: list[dict] = []

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task_a = asyncio.create_task(self._loop_a())
        self._task_b = asyncio.create_task(self._loop_b())
        self.next_poll_at = (datetime.now(timezone.utc) + timedelta(seconds=self.interval)).isoformat()
        self.next_yanbao_at = (datetime.now(timezone.utc) + timedelta(seconds=self.yanbao_interval)).isoformat()
        logger.info(f"天机峰调度器已启动: A管线 {self.interval}s, B管线(研报) {self.yanbao_interval}s")

    async def stop(self):
        self._running = False
        for task in (self._task_a, self._task_b):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task_a = None
        self._task_b = None
        logger.info("天机峰调度器已停止")

    async def _loop_a(self):
        """A 管线：快讯，每 10 分钟"""
        await asyncio.sleep(5)
        while self._running:
            try:
                self.current_status = "polling_a"
                self._emit({"type": "tianjifeng_cycle", "pipeline": "A", "status": "started"})
                stats = await asyncio.to_thread(self._poll_sync_a)
                self._emit({"type": "tianjifeng_cycle", "pipeline": "A", "status": "completed", "stats": stats})
                self.current_status = "idle"
            except Exception as e:
                self.current_status = f"error: {e}"
                logger.error(f"天机峰A管线异常: {e}", exc_info=True)
                self._emit({"type": "tianjifeng_cycle", "pipeline": "A", "status": "error", "error": str(e)})
            self.last_poll_at = datetime.now(timezone.utc).isoformat()
            self.next_poll_at = (datetime.now(timezone.utc) + timedelta(seconds=self.interval)).isoformat()
            await asyncio.sleep(self.interval)

    async def _loop_b(self):
        """B 管线：研报，每 30 分钟"""
        await asyncio.sleep(15)
        while self._running:
            try:
                self.current_status = "polling_b"
                self._emit({"type": "tianjifeng_cycle", "pipeline": "B", "status": "started"})
                stats = await asyncio.to_thread(self._poll_sync_b)
                self._emit({"type": "tianjifeng_cycle", "pipeline": "B", "status": "completed", "stats": stats})
                self.current_status = "idle"
            except Exception as e:
                self.current_status = f"error: {e}"
                logger.error(f"天机峰B管线异常: {e}", exc_info=True)
                self._emit({"type": "tianjifeng_cycle", "pipeline": "B", "status": "error", "error": str(e)})
            self.last_yanbao_at = datetime.now(timezone.utc).isoformat()
            self.next_yanbao_at = (datetime.now(timezone.utc) + timedelta(seconds=self.yanbao_interval)).isoformat()
            await asyncio.sleep(self.yanbao_interval)

    def _poll_sync_a(self) -> dict:
        """A 管线：抓取入池 + 管线处理"""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from tianjifeng.pipeline import fetch_and_store, run_pipeline
        from tianjifeng.coze_io import NewsPoolCoze

        inserted = fetch_and_store(self.coze)
        self._emit({"type": "tianjifeng_fetch", "inserted": inserted})

        stats = run_pipeline(
            max_news=self.max_news,
            dry_run=False,
            full_write_level=self.full_write_level,
            coze_client=self.coze,
            progress_cb=lambda step, data: self._emit({"type": "tianjifeng_step", "pipeline": "A", "step": step, **data}),
        )

        for r in stats.get("results", []):
            if r.get("status") in ("done", "filtered", "seed_rejected"):
                self.completed_jobs.append({
                    "pipeline": "A",
                    "title": r.get("title", ""),
                    "status": r.get("status"),
                    "level": r.get("level", ""),
                    "mode": r.get("mode", ""),
                    "company": r.get("company", ""),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })

        if len(self.completed_jobs) > 100:
            self.completed_jobs = self.completed_jobs[-100:]

        logger.info(
            f"天机峰A管线: 入池{inserted} 共{stats.get('total',0)}条 "
            f"拦截{stats.get('filtered',0)} 种子拒绝{stats.get('seed_rejected',0)} "
            f"放行{stats.get('done',0)} 跳过{stats.get('skip',0)} 错误{stats.get('error',0)}"
        )

        now = datetime.now()
        if now.hour == 0 and now.minute < 15:
            try:
                pool = NewsPoolCoze(self.coze)
                old_count = pool.cleanup_old(days=7)
                if old_count > 0:
                    logger.warning(f"中间表有 {old_count} 条超过 7 天的已处理记录，建议在 Coze 后台清理")
            except Exception:
                pass

        return stats

    def _poll_sync_b(self) -> dict:
        """B 管线：研报表轮询处理"""
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from tianjifeng.pipeline import run_yanbao_pipeline

        stats = run_yanbao_pipeline(
            max_records=self.yanbao_max,
            parallel=self.yanbao_parallel,
            dry_run=False,
            full_write_level=self.full_write_level,
            coze_client=self.coze,
            progress_cb=lambda step, data: self._emit({"type": "tianjifeng_step", "pipeline": "B", "step": step, **data}),
        )

        for r in stats.get("results", []):
            if r.get("status") in ("done", "seed_rejected", "not_a_stock"):
                self.completed_jobs.append({
                    "pipeline": "B",
                    "title": r.get("title", ""),
                    "status": r.get("status"),
                    "level": r.get("level", ""),
                    "mode": r.get("mode", ""),
                    "company": r.get("company", ""),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })

        if len(self.completed_jobs) > 100:
            self.completed_jobs = self.completed_jobs[-100:]

        logger.info(
            f"天机峰B管线(研报): 共{stats.get('total',0)}条 "
            f"种子拒绝{stats.get('seed_rejected',0)} 非A股{stats.get('not_a_stock',0)} "
            f"放行{stats.get('done',0)} 跳过{stats.get('skip',0)} 错误{stats.get('error',0)}"
        )
        return stats

    def _emit(self, data: dict):
        if self.progress_cb:
            try:
                self.progress_cb(data)
            except Exception:
                pass
