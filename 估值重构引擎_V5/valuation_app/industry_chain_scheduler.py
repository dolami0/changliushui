"""
望气调度器 — 产业链利润流独立调度器

定时轮询 Coze 表 7479116110479048754，筛选 level>=4 的产业模式记录，
调用 IndustryChainWorkflow 分析，结果写入自建输出表。
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable


class WangqiScheduler:
    """天机 — 产业链工作流独立调度器"""

    def __init__(self, coze_client, workflow, coze_io, config: dict, progress_cb: Callable | None = None):
        self.coze = coze_client
        self.workflow = workflow
        self.coze_io = coze_io
        self.config = config
        self.progress_cb = progress_cb
        self.interval = config.get("tianji_poll_interval_sec", 3600)  # 默认1小时
        self.min_level = config.get("tianji_min_level", 4)
        self._running = False
        self._task: asyncio.Task | None = None
        self.last_poll_at: str | None = None
        self.next_poll_at: str | None = None
        self.current_poll_status: str = "idle"
        self.current_status: str = "idle"       # V5 server.py 兼容别名
        self.active_jobs: list[dict] = []
        self.completed_jobs: list[dict] = []

    def load_state(self, completed_jobs: list[dict]):
        """从 Coze 输出表恢复已完成任务列表（由 server lifespan 在 start 前调用）"""
        if completed_jobs:
            self.completed_jobs = completed_jobs

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        self.next_poll_at = (datetime.now(timezone.utc) + timedelta(seconds=self.interval)).isoformat()

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def set_interval(self, sec: int):
        self.interval = sec
        self.config["tianji_poll_interval_sec"] = sec

    async def poll_now(self) -> list[dict]:
        return await asyncio.to_thread(self._poll_sync)

    async def analyze_one(self, record_id: str) -> dict:
        """分析指定单条记录"""
        record = self.coze_io.get_record_by_id(record_id)
        if not record:
            return {"status": "error", "error": f"记录 {record_id} 未找到"}
        self.coze_io.mark_analyzing(record_id)
        result = self.workflow.run_on_record(record, progress_cb=self._on_progress)
        if result.get("status") == "done":
            try:
                self.coze_io.write_result(result)
            except Exception as e:
                result["write_error"] = str(e)[:500]
            finally:
                self.coze_io.mark_processed(record_id)
        elif result.get("status") == "skipped":
            self.coze_io.mark_processed(record_id)
        else:
            # error: analyzing=true + analyzed=false → 不重试，可识别
            self.coze_io.mark_error(record_id)
        return result

    async def _loop(self):
        while self._running:
            try:
                self.current_poll_status = "polling"
                self._emit_progress({"type": "tianji_cycle", "status": "started"})
                await asyncio.to_thread(self._poll_sync)
                self._emit_progress({"type": "tianji_cycle", "status": "completed"})
                self.current_poll_status = "idle"
            except Exception as e:
                self.current_poll_status = f"error: {e}"
                self._emit_progress({"type": "tianji_cycle", "status": "error", "error": str(e)[:200]})
            self.last_poll_at = datetime.now(timezone.utc).isoformat()
            self.next_poll_at = (datetime.now(timezone.utc) + timedelta(seconds=self.interval)).isoformat()
            await asyncio.sleep(self.interval)

    def _poll_sync(self) -> list[dict]:
        results = []
        records = self.coze_io.query_unprocessed(min_level=self.min_level)

        for record in records[:10]:
            record_id = str(record.get("id", ""))
            try:
                # 标记分析中，防止调度器重复拉取
                self.coze_io.mark_analyzing(record_id)

                self.current_poll_status = f"analyzing {record_id[:8]}"
                self._emit_progress({
                    "type": "tianji_job",
                    "record_id": record_id,
                    "status": "started",
                    "level": record.get("level"),
                })
                result = self.workflow.run_on_record(record, progress_cb=self._on_progress)

                if result.get("status") == "done":
                    try:
                        self.coze_io.write_result(result)
                    except Exception as e:
                        result["write_error"] = str(e)[:500]

                    self.coze_io.mark_processed(record_id)

                    tp = _safe_pick_name(result.get("top_pick"))
                    ru = _safe_pick_name(result.get("runner_up"))
                    self.completed_jobs.append({
                        "record_id": record_id,
                        "top_pick": tp,
                        "runner_up": ru,
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    self._emit_progress({
                        "type": "tianji_job", "record_id": record_id, "status": "done",
                        "top_pick": tp,
                        "runner_up": ru,
                    })
                elif result.get("status") == "skipped":
                    self.coze_io.mark_processed(record_id)
                    self.completed_jobs.append({
                        "record_id": record_id, "status": "skipped",
                        "error": result.get("error", ""),
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    self._emit_progress({
                        "type": "tianji_job", "record_id": record_id, "status": "skipped",
                        "error": result.get("error", "")[:200],
                    })
                else:
                    # 失败: analyzing=true + analyzed=false，不重试可识别
                    self.coze_io.mark_error(record_id)
                    self.completed_jobs.append({
                        "record_id": record_id, "status": result.get("status", "?"),
                        "error": result.get("error", ""),
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    self._emit_progress({
                        "type": "tianji_job", "record_id": record_id, "status": "error",
                        "error": result.get("error", "")[:200],
                    })

                results.append(result)

            except Exception as e:
                err = str(e)[:500]
                results.append({"status": "error", "record_id": record_id, "error": err})
                self._emit_progress({"type": "tianji_job", "record_id": record_id, "status": "error", "error": err})
                # 异常: analyzing=true + analyzed=false
                try:
                    self.coze_io.mark_error(record_id)
                except Exception:
                    pass

        return results

    def _on_progress(self, step: int, name: str):
        self._emit_progress({"type": "tianji_step", "step": step, "name": name})

    def _emit_progress(self, data: dict):
        if self.progress_cb:
            try:
                self.progress_cb(data)
            except Exception:
                pass


def _safe_pick_name(pick) -> str:
    """安全提取 top_pick/runner_up 的 stock_name，兼容字符串和 dict"""
    if isinstance(pick, dict):
        return pick.get("stock_name", "") or ""
    if isinstance(pick, str):
        return pick
    return ""
