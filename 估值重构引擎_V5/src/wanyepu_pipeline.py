"""万业谱预研语料管线 — 主入口 (V2)

Coze DAG 架构的纯 Python 实现:
  N0 验证 → N1-N5 串行字段 → N6 总装 → N7 写入

V1 三层架构已废弃，保留旧代码在 agents/ 目录供参考。
"""

from .wanyepu_v2.pipeline import run_pipeline, run_pipeline_record, run_single

__all__ = ["run_pipeline", "run_pipeline_record", "run_single"]
