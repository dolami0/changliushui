"""
审阅与自进化系统 · Review & Self-Evolution

基于 觀瀾 Dream Loop 思路，为万业谱管线设计的质量审阅和持续改进机制。

两层审阅:
  L1 — 预研语料本身的质量（探针设计+单份报告深度+交叉一致性+回聲）
  L2 — 估值链的推理质量（吸收度+推理链自洽+情景可信度）

三层反馈:
  Step 1 — 每次管线运行后调用 Introspector.audit() 审阅
  Step 2 — DreamLoop.accumulate() 累积审计日志
  Step 3 — DreamLoop.dream() 定期触发，聚类问题，生成改进提案 → _proposed/

核心原则:
  - 不自动合入改进 → 提案必须人工审阅
  - 不重新分析公司 → 审阅师只审管线质量
  - 代码预聚合 + LLM 精分析 → 节省 token
"""

from review.taxonomy import QUALITY_GRADE, ERROR_TYPE, SEVERITY, AUDIT_DIMENSIONS
from review.introspector import Introspector, quick_audit
from review.dream_loop import DreamLoop, quick_dream

__all__ = [
    "Introspector",
    "quick_audit",
    "DreamLoop",
    "quick_dream",
    "QUALITY_GRADE",
    "ERROR_TYPE",
    "SEVERITY",
    "AUDIT_DIMENSIONS",
]
