"""
管线编排器 (V5) — Web 层进度通知包装器。

使用 src/orchestrator.py 编排 4-Agent 管线，
将 Orchestrator 的回调映射为 ProgressEvent 供 Web UI (SSE) 使用。

与 V4 兼容: run_single() 返回 dict 格式保持一致。
"""

import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# 添加 src/ 到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orchestrator import Orchestrator


# ═══════════════════════════════════════
# ProgressEvent — Web UI 兼容
# ═══════════════════════════════════════

@dataclass
class ProgressEvent:
    stock_code: str
    stock_name: str
    stage: str           # agent0 | agent1 | agent2 | agent3 | report
    step: int
    total_steps: int
    step_name: str
    status: str          # running | done | error
    elapsed_s: float = 0.0
    error_msg: str | None = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════
# 子步骤定义 (V5 4-Agent)
# ═══════════════════════════════════════

AGENT0_STEPS = ["预路由(行业+事件标签→数据清单)"]
AGENT1_STEPS = ["分层数据拉取(core/specialized/validation/optional)"]
AGENT2_STEPS = ["联网搜索", "V3案例匹配", "LLM路由判决", "迁移路径预判", "增量补取检查", "路由完成"]
AGENT3_STEPS = ["WACC/BS预计算", "LLM推演裁决", "一致性校验", "组装输出", "推演裁决完成"]
REPORT_STEPS = ["写入Coze输出表", "构建HTML报告"]


# ═══════════════════════════════════════
# PipelineRunner — V5
# ═══════════════════════════════════════

class PipelineRunner:
    """管线编排器。持有进度回调，将 Agent0 记录送入 4-Agent 管线。"""

    def __init__(self, progress_callback: Callable[[ProgressEvent], None]):
        self.on_progress = progress_callback

    def _emit(self, stock_code: str, stock_name: str, stage: str,
              step: int, total: int, step_name: str, status: str,
              elapsed: float = 0.0, error_msg: str | None = None):
        self.on_progress(ProgressEvent(
            stock_code=stock_code, stock_name=stock_name,
            stage=stage, step=step, total_steps=total,
            step_name=step_name, status=status,
            elapsed_s=elapsed, error_msg=error_msg,
        ))

    def run_single(self, record: dict, deepseek_key: str,
                   eval_mode: bool = False) -> dict:
        """
        处理单条 Agent0 记录 → 返回管线结果 dict。

        record 字段: stock_code, stock_name, raw_event_text, event_deduction,
                     investment_theme, adversarial_thinking, knowledge_supplement,
                     preliminary_reasoning, response_level 等 Coze Agent0 输出。

        返回: {agent0, agent1, agent2, agent3, status: "done"|"error"}
        """
        stock_code = record.get("stock_code", "")
        stock_name = record.get("stock_name", "")

        try:
            # ── 创建 Orchestrator ──
            orch = Orchestrator(deepseek_key=deepseek_key)

            if eval_mode:
                # 评测模式: 从 record 的 frozen_agent1 注入
                orch.enable_eval_mode(record)

            # ── 进度回调映射 ──
            def progress_cb(stage, step, total, status, message):
                # 直接用 orchestrator 传的 message 作为 step_name，保持前后端一致
                self._emit(stock_code, stock_name, stage,
                          step, total, message, status,
                          elapsed=0.0,
                          error_msg=message if status == "error" else None)

            # ── 构建事件数据 ──
            event_data = {
                "raw_event_text": record.get("raw_event_text", ""),
                "event_deduction": record.get("event_deduction", ""),
                "investment_theme": record.get("investment_theme", ""),
                "response_level": record.get("response_level", ""),
                "preliminary_reasoning": record.get("preliminary_reasoning", ""),
                "adversarial_thinking": record.get("adversarial_thinking", ""),
                "knowledge_supplement": record.get("knowledge_supplement", ""),
                "industry_expert_research": record.get("industry_expert_research", ""),
                "future": record.get("future", ""),
                "event_date": record.get("event_date", ""),
                "event_source": record.get("event_source", ""),
                "stock_name": stock_name,
            }

            # ── 运行管线 ──
            result = orch.run(stock_code, event_data, progress_cb=progress_cb)

            # 确保 agent0 字段（兼容 scheduler）
            if "agent0" not in result or not result["agent0"]:
                result["agent0"] = record

            return result

        except Exception as e:
            return {
                "agent0": record,
                "agent1": {},
                "agent2": {},
                "agent3": {},
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    def run_batch(self, records: list[dict], deepseek_key: str) -> list[dict]:
        """串行批处理，单只失败不阻塞后续。"""
        results = []
        for i, rec in enumerate(records):
            try:
                result = self.run_single(rec, deepseek_key)
                results.append(result)
            except Exception as e:
                results.append({
                    "agent0": rec,
                    "agent1": {}, "agent2": {}, "agent3": {},
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                })
        return results
