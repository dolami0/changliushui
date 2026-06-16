"""
审阅系统 · 分类常量

三级分类：子系统 → 维度 → 错误类型
"""

# ═══════════════════════════════════════
# 质量评级（跨层通用）
# ═══════════════════════════════════════

QUALITY_GRADE = {
    "A": "无发现问题，交叉验证通过，推理链自洽",
    "B": "有小问题但不影响核心判断，标记后通过",
    "C": "核心逻辑有疑点或数据缺失，下游需降置信度",
    "D": "存在事实错误或幻觉，需重跑",
    "F": "系统故障（API超时/数据源不可用），需人工介入",
}

# ═══════════════════════════════════════
# 错误分类
# ═══════════════════════════════════════

ERROR_TYPE = {
    # ── 数据层 ──
    "DATA_STALE":       "数据过期",
    "DATA_WRONG":       "数值错误",
    "DATA_MISSING":     "数据缺失但未标注",
    "DATA_CONFLICT":    "两个来源矛盾",

    # ── 幻觉层 ──
    "HALLUCINATION_FABRICATED":   "凭空捏造数字/事实",
    "HALLUCINATION_MISATTRIBUTED": "张冠李戴",
    "HALLUCINATION_GHOST_CITE":   "幽灵引用（来源不存在）",
    "HALLUCINATION_PRECISION":    "伪精度（数据精度超过来源）",

    # ── 逻辑层 ──
    "LOGIC_CONTRADICTION":  "同一份报告中自相矛盾",
    "LOGIC_CAUSAL_LEAP":    "相关当因果",
    "LOGIC_MISSING_COUNTER": "只列支持证据，不提交反面",
    "LOGIC_CIRCULAR":       "循环论证",

    # ── 覆盖层 ──
    "COVERAGE_BLIND_SPOT":  "应分析但完全遗漏",
    "COVERAGE_SHALLOW":     "提了但未深入",
    "COVERAGE_ECHO":        "多探针引用同源，回声室",
    "COVERAGE_FIELD_LEAK":  "内容放错字段",

    # ── 推理链层 ──
    "CHAIN_DROP":       "关键信息在传递中被丢弃",
    "CHAIN_DRIFT":      "叙事在传递中漂移",
    "CHAIN_MISINTERPRET": "下游误解上游结论",
}

# ═══════════════════════════════════════
# 严重级
# ═══════════════════════════════════════

SEVERITY = {
    "P0": "阻断 — 必须修复才能继续",
    "P1": "降级 — 标记后继续，下游降置信度",
    "P2": "记录 — 不阻塞，供后续模式发现",
}

# ═══════════════════════════════════════
# 审阅维度
# ═══════════════════════════════════════

AUDIT_DIMENSIONS = {
    # L1 预研层
    "individual_depth":     "单份报告的深度——有没有机器人味、一手信息、完成指定任务",
    "probe_design":         "探针设计合理性——是否冗余、是否漏了关键维度",
    "cross_consistency":    "5份预研语料之间的交叉一致性",
    "echo_detection":       "回聲检测——多探针是否引用同一来源",
    "coverage_blind_spot":  "覆盖盲区——该股票类型需要但缺失的分析维度",
    # L2 估值层
    "baseline_absorption":  "Baseline 是否正确吸收了预研语料，有无丢失负面信息",
    "anchor_chain":         "推理链自洽：Baseline锚→Agent-2锚→Agent-3变量",
    "scenario_coherence":   "三情景估值内部自洽——叙事是否有质的不同",
    "evidence_quality":     "数据/引用的来源和可信度",
}
