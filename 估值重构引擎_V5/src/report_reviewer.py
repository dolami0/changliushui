"""
报告审阅引擎 (Report Reviewer) — V5

工程控制论视角下的报告质量评估系统。

原则:
  1. 系统是筛选器，不是预言机 — 审阅关注"过滤质量"而非"预测精度"
  2. 信号链完整性 — 数据→路由→情景→输出，每一环的质量决定最终信噪比
  3. 校准优于准确 — 置信度应与实际结果相关，而非追求点估计精度
  4. 噪声拒绝 — 系统应敢于说"不知道"，而非给出精确的错误答案

审阅五层:
  L0 数据完整性 — 输入数字是否可靠
  L1 路由合理性 — 模型选择是否有据
  L2 情景合理性 — bear/base/bull是否在历史和逻辑边界内
  L3 案例锚定质量 — 案例是破平局工具还是先验偏置
  L4 自洽性 — 数字是否相互一致
  L5 可操作性 — 报告能否指导实际行动
"""

import json
from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════
# 审阅结果数据结构
# ═══════════════════════════════════════

@dataclass
class Flag:
    """审阅标记 — 一个问题或发现。"""
    code: str           # 如 "L0_PB_ANOMALY"
    layer: int          # 0-5
    severity: str       # critical / warning / info
    message: str        # 人类可读描述
    suggestion: str     # 改进建议


@dataclass
class ReviewResult:
    """完整审阅结果。"""
    stock_code: str
    stock_name: str
    overall_grade: str          # A/B/C/D/F
    layer_scores: dict[str, float] = field(default_factory=dict)  # L0-L5各层得分
    flags: list[Flag] = field(default_factory=list)
    key_strengths: list[str] = field(default_factory=list)
    key_weaknesses: list[str] = field(default_factory=list)
    improvement_actions: list[str] = field(default_factory=list)
    meta_note: str = ""         # 系统级反馈（工程控制论视角）


# ═══════════════════════════════════════
# L0: 数据完整性
# ═══════════════════════════════════════

def _review_l0_data(core: dict) -> tuple[float, list[Flag]]:
    """检查输入数据的完整性和合理性。"""
    score = 10.0
    flags = []

    # 检查关键字段是否存在且非零
    critical_fields = {
        "market_cap_yi": "市值",
        "revenue_ttm_yi": "营收TTM",
        "total_equity_yi": "净资产",
        "pe_ttm": "PE(TTM)",
        "pb": "PB",
        "roic_pct": "ROIC",
    }

    for field, label in critical_fields.items():
        val = core.get(field, 0)
        if val is None or (isinstance(val, (int, float)) and val <= 0 and field != "roic_pct"):
            score -= 1.5
            flags.append(Flag(
                code=f"L0_MISSING_{field.upper()}",
                layer=0, severity="critical",
                message=f"{label}缺失或为零: {val}",
                suggestion=f"检查 data_fetcher 中 {label} 的字段映射",
            ))

    # PB 合理性检查: 亏损企业PB<1正常, 高PB需要净资产>0
    pb_val = core.get("pb", 0) or 0
    equity = core.get("total_equity_yi", 0) or 1
    mcap = core.get("market_cap_yi", 0) or 1
    calc_pb = mcap / equity if equity > 0 else 0

    if pb_val > 0 and calc_pb > 0:
        ratio = pb_val / calc_pb
        if ratio < 0.5 or ratio > 2.0:
            score -= 2
            flags.append(Flag(
                code="L0_PB_MISMATCH",
                layer=0, severity="critical",
                message=f"PB值({pb_val:.1f}x)与市值/净资产({calc_pb:.1f}x)偏差{(ratio-1)*100:.0f}%",
                suggestion="检查 data_fetcher.fetch_valuation 中PB字段映射(f2290=市净率)",
            ))

    # ROIC 自洽性: ROIC ≈ NOPAT / invested_capital (代码计算，偏离>30%说明数据源异常)
    nopat = core.get("nopat_yi", 0) or 0
    ic_raw = core.get("invested_capital_yi") or core.get("total_equity_yi", 1)
    ic_val = ic_raw or 1
    roic = core.get("roic_pct", 0) or 0
    if nopat > 0 and ic_val > 0 and roic > 0:
        calc_roic = nopat / ic_val * 100
        dev = abs(roic - calc_roic) / max(abs(roic), 0.1)
        if dev > 0.3:
            score -= 2
            flags.append(Flag(
                code="L0_ROIC_MISMATCH", layer=0, severity="critical",
                message=f"ROIC({roic:.1f}%)与NOPAT/IC({calc_roic:.1f}%)偏差{dev*100:.0f}%",
                suggestion="检查 fin_der_inds→roic 字段映射和 agent1 NOPAT/IC 计算逻辑",
            ))

    # EBITDA 应 ≥ 经营利润 (EBITDA = OP + D&A，不应更小)
    ebitda = core.get("ebitda_ttm_yi", 0) or 0
    op = core.get("operating_profit_ttm_yi", 0) or 0
    if op > 0 and ebitda > 0 and ebitda < op * 0.9:
        score -= 1.5
        flags.append(Flag(
            code="L0_EBITDA_LT_OP", layer=0, severity="warning",
            message=f"EBITDA({ebitda:.2f}亿) < 经营利润({op:.2f}亿)，EBITDA应≥OP",
            suggestion="EBITDA来源为 fin_der_inds 单季数据，需×4年化；若已年化仍异常则检查API字段",
        ))

    # PS 极端偏离: mcap/revenue > 100x 或是 < 0.1x 通常意味着数据错误
    rev = core.get("revenue_ttm_yi", 0) or 0
    if rev > 0 and mcap > 0:
        ps = mcap / rev
        if ps > 100 or ps < 0.1:
            score -= 1
            flags.append(Flag(
                code="L0_PS_ANOMALY", layer=0, severity="warning",
                message=f"PS={ps:.1f}x 异常({'极高' if ps > 100 else '极低'})，可能revenue/mcap字段映射错误",
                suggestion="检查 fetch_realtime_quote→market_cap 和 fetch_income_ttm→revenue_ttm 字段",
            ))

    # PE 极端值检查
    pe = core.get("pe_ttm", 0) or 0
    if pe > 500:
        score -= 1
        flags.append(Flag(
            code="L0_PE_EXTREME", layer=0, severity="warning",
            message=f"PE={pe:.0f}x 极端高，需确认非计算错误",
            suggestion="检查PE字段映射(f2250)，确认非EV/EBITDA等误映射",
        ))

    # 历史分位一致性: 分位应有意义
    for rank_field, label in [
        ("pe_historical_rank", "PE历史分位"),
        ("pb_historical_rank", "PB历史分位"),
        ("roic_historical_rank", "ROIC历史分位"),
    ]:
        rank = core.get(rank_field)
        if rank is not None and (rank < 0 or rank > 100):
            score -= 0.5
            flags.append(Flag(
                code=f"L0_RANK_OOB_{rank_field.upper()}",
                layer=0, severity="warning",
                message=f"{label}={rank} 超出[0,100]范围",
                suggestion="检查API返回的排名字段是否有误",
            ))

    return max(0, score), flags


# ═══════════════════════════════════════
# L1: 路由合理性
# ═══════════════════════════════════════

# 每个模型的适用条件
MODEL_REQUIREMENTS = {
    "A": {"roic_min": 8, "profit_required": True, "note": "ROIC>8%+盈利稳定"},
    "B": {"roic_max": 8, "profit_required": False, "note": "亏损/微利+高增长"},
    "C": {"note": "当前亏损/微利+盈利拐点"},
    "D": {"note": "重资产+PB<2+ROE改善"},
}

def _review_l1_routing(core: dict, routing: dict) -> tuple[float, list[Flag]]:
    """检查路由选择是否有数据支撑。"""
    score = 10.0
    flags = []

    primary = (routing.get("primary_model", "") or "")[0] if routing.get("primary_model") else ""
    reason = routing.get("routing_reason", "")

    # 检查路由理由是否引用具体数字
    has_numbers = any(c.isdigit() for c in reason[:200])
    if not has_numbers:
        score -= 3
        flags.append(Flag(
            code="L1_REASON_NO_DATA",
            layer=1, severity="warning",
            message="路由理由未引用具体财务数据——可能是模板化输出",
            suggestion="在 Agent-2 提示词中强化'必须引用具体数字'约束",
        ))

    # 检查路由理由长度（过短=退化fallback）
    if len(reason) < 100:
        score -= 2
        flags.append(Flag(
            code="L1_REASON_TOO_SHORT",
            layer=1, severity="warning",
            message=f"路由理由仅{len(reason)}字，疑似fallback或LLM退化",
            suggestion="检查 Agent-2 是否正常调用LLM",
        ))

    # 模型-财务一致性检查
    roic = core.get("roic_pct", 0) or 0
    is_loss = core.get("is_loss_making", False)

    if primary == "A" and roic < 5:
        score -= 2
        flags.append(Flag(
            code="L1_MODEL_A_LOW_ROIC",
            layer=1, severity="warning",
            message=f"模型A(ROIC-RR DCF)要求ROIC>8%，实际ROIC={roic:.1f}%",
            suggestion="考虑路由到 I(盈利正常化) 或 E(EV/EBITDA)",
        ))

    if primary == "B" and roic > 10 and not is_loss:
        score -= 1
        flags.append(Flag(
            code="L1_MODEL_B_HIGH_ROIC",
            layer=1, severity="info",
            message=f"模型B(PS+TAM)适合亏损/微利企业，但ROIC={roic:.1f}%且盈利",
            suggestion="检查是否应路由到盈利乘数族(A/C/G)",
        ))

    # 模型I触发条件检查（周期底部识别）
    if primary == "I":
        pe = core.get("pe_ttm", 0) or 0
        pb = core.get("pb", 0) or 0
        if pe < 80 or pb > 3:
            score -= 1
            flags.append(Flag(
                code="L1_MODEL_I_WEAK_SIGNAL",
                layer=1, severity="info",
                message=f"模型I(盈利正常化)触发条件PE>80x+PB<3x，实际PE={pe:.1f}x PB={pb:.1f}x——信号偏弱",
                suggestion="检查是否为真正的周期底部",
            ))

    return max(0, score), flags


# ═══════════════════════════════════════
# L2: 情景合理性
# ═══════════════════════════════════════

def _review_l2_scenarios(scenario_details: dict, core: dict) -> tuple[float, list[Flag]]:
    """检查三情景参数是否在历史和逻辑边界内。"""
    score = 10.0
    flags = []

    if not scenario_details:
        score = 0
        flags.append(Flag(code="L2_NO_SCENARIOS", layer=2, severity="critical",
                          message="情景推演为空", suggestion="检查 Agent-3 输出解析"))
        return score, flags

    bear = scenario_details.get("bear", {})
    base = scenario_details.get("base", {})
    bull = scenario_details.get("bull", {})

    bear_up = bear.get("upside_pct", 0) or 0
    base_up = base.get("upside_pct", 0) or 0
    bull_up = bull.get("upside_pct", 0) or 0

    # 单调性
    if not (bear_up < base_up < bull_up):
        score -= 3
        flags.append(Flag(
            code="L2_MONOTONICITY", layer=2, severity="critical",
            message=f"upside违反单调性: bear={bear_up:.1f} base={base_up:.1f} bull={bull_up:.1f}",
            suggestion="检查 Agent-3 输出的情景排序",
        ))

    # Bear底线: 破产价不应低于净现金
    cash = core.get("cash_yi", 0) or 0
    debt = core.get("interest_bearing_debt_yi", 0) or 0
    net_cash = cash - debt
    mcap = core.get("market_cap_yi", 0) or 1
    bear_mcap = bear.get("target_mcap_yi", mcap)

    if bear_mcap and net_cash > mcap * 0.3 and bear_mcap < net_cash * 0.5:
        score -= 2
        flags.append(Flag(
            code="L2_BEAR_BELOW_CASH", layer=2, severity="warning",
            message=f"Bear市值({bear_mcap:.0f}亿)远低于净现金({net_cash:.0f}亿)——隐含破产定价",
            suggestion="Bear应有资产托底，除非公司确实在消耗现金",
        ))

    # Bull上限: 对比历史先例
    pe = core.get("pe_ttm", 0) or 0
    if bull_up > 500:
        score -= 2
        flags.append(Flag(
            code="L2_BULL_EXTREME", layer=2, severity="warning",
            message=f"Bull涨幅={bull_up:.0f}%，远超10倍股定义(+900%)，需强有力的范式切换论证",
            suggestion="检查bull是否被案例锚定约束",
        ))

    # 概率分布: 避免均匀分布(33/33/33)或过度集中(90/5/5)
    probs = [bear.get("probability", 0) or 0, base.get("probability", 0) or 0, bull.get("probability", 0) or 0]
    prob_sum = sum(probs)
    if abs(prob_sum - 1.0) > 0.05:
        score -= 2
        flags.append(Flag(
            code="L2_PROB_SUM", layer=2, severity="critical",
            message=f"概率和={prob_sum:.2f}≠1.0",
            suggestion="强制 Σprob=1.0",
        ))

    if max(probs) > 0.75:
        score -= 1.5
        flags.append(Flag(
            code="L2_PROB_OVERCONFIDENT", layer=2, severity="warning",
            message=f"概率过度集中: max={max(probs):.0%}，缺乏不确定性表达",
            suggestion="鼓励更宽的概率分布以反映真实不确定性",
        ))

    if abs(probs[0] - probs[1]) < 0.03 and abs(probs[1] - probs[2]) < 0.03:
        score -= 1
        flags.append(Flag(
            code="L2_PROB_UNIFORM", layer=2, severity="info",
            message="三情景概率接近均匀分布——可能缺乏判断力",
            suggestion="基于事件验证度、证伪风险、超预期空间做差异化概率分配",
        ))

    return max(0, score), flags


# ═══════════════════════════════════════
# L3: 案例锚定质量
# ═══════════════════════════════════════

def _review_l3_cases(case_comparison: dict, scenario_details: dict) -> tuple[float, list[Flag]]:
    """检查案例使用是否合理：破平局 vs 先验。"""
    score = 10.0
    flags = []

    cases = case_comparison.get("compared_cases", [])
    if not cases:
        # 无案例不一定是问题——有些行业/模型族确实缺案例
        return 8.0, [Flag(
            code="L3_NO_CASES", layer=3, severity="info",
            message="无案例锚定——可能因无同族案例或案例匹配失败",
            suggestion="检查 case_loader 匹配分是否过低，或该模型族案例库是否空白",
        )]

    # 检查6维度判断是否有模板化倾向
    all_superior = 0
    all_inferior = 0
    total_dims = 0
    for c in cases:
        dims = c.get("six_dimension_judgment", {})
        superior_count = sum(1 for v in dims.values() if v == "优于")
        inferior_count = sum(1 for v in dims.values() if v == "劣于")
        if superior_count >= 5:
            all_superior += 1
        if inferior_count >= 5:
            all_inferior += 1
        total_dims += len(dims)

    if all_superior >= len(cases) * 0.8:
        score -= 3
        flags.append(Flag(
            code="L3_ALL_SUPERIOR", layer=3, severity="warning",
            message=f"{all_superior}/{len(cases)}个案例全维度'优于'——高度怀疑模板化",
            suggestion="强化提示词: 6维度判断必须附案例原文证据，禁止全'优于'",
        ))

    if all_inferior >= len(cases) * 0.8:
        score -= 3
        flags.append(Flag(
            code="L3_ALL_INFERIOR", layer=3, severity="warning",
            message=f"{all_inferior}/{len(cases)}个案例全维度'劣于'——可能过度悲观",
            suggestion="检查是否因为PB数据修正导致过度修正",
        ))

    # 检查折扣是否落实
    pi = case_comparison.get("parameter_impact", {})
    discount = pi.get("target_param_discount_pct", 0) or 0
    if discount > 0:
        # 检查bull是否真的被打了折
        bull_mcap = scenario_details.get("bull", {}).get("target_mcap_yi", 0)
        if bull_mcap and discount > 15:
            score -= 2
            flags.append(Flag(
                code="L3_DISCOUNT_NOT_APPLIED",
                layer=3, severity="warning",
                message=f"声称施加{discount}%折扣，需验证bull市值是否已反映——当前bull={bull_mcap:.0f}亿",
                suggestion="强化约束: target_param_discount_pct必须与实际数字一致",
            ))

    return max(0, score), flags


# ═══════════════════════════════════════
# L4: 自洽性
# ═══════════════════════════════════════

def _review_l4_consistency(
    scenario_details: dict, vs: dict, confidence: dict,
    narrative: str,
) -> tuple[float, list[Flag]]:
    """检查报告内部自洽性。"""
    score = 10.0
    flags = []

    # 算术一致性
    bear = scenario_details.get("bear", {})
    base = scenario_details.get("base", {})
    bull = scenario_details.get("bull", {})
    probs = [bear.get("probability", 0) or 0, base.get("probability", 0) or 0, bull.get("probability", 0) or 0]
    upsides = [bear.get("upside_pct", 0) or 0, base.get("upside_pct", 0) or 0, bull.get("upside_pct", 0) or 0]

    calc_asym = abs(upsides[2] / upsides[0]) if upsides[0] != 0 else 0
    reported_asym = vs.get("asymmetry_ratio", 0) or 0
    if abs(calc_asym - reported_asym) > 0.2:
        score -= 3
        flags.append(Flag(
            code="L4_ASYM_MISMATCH", layer=4, severity="critical",
            message=f"不对称比: 计算={calc_asym:.1f} 报告={reported_asym:.1f}",
            suggestion="代码已覆盖asymmetry_ratio，此flag不应触发——检查_compute_from_assumptions",
        ))

    weighted_up = sum(p * u for p, u in zip(probs, upsides))

    # 叙事与数字一致性
    has_upside_text = any(w in (narrative or "").lower() for w in ["上涨", "增长", "upside", "bull", "翻倍"])
    has_bear_text = any(w in (narrative or "").lower() for w in ["下跌", "风险", "亏损", "bear", "泡沫"])
    if weighted_up > 20 and not has_upside_text:
        score -= 0.5
        flags.append(Flag(
            code="L4_NARRATIVE_MISMATCH", layer=4, severity="info",
            message="正加权涨幅但叙事未提及上行潜力",
            suggestion="叙事应与数值方向一致",
        ))

    return max(0, score), flags


# ═══════════════════════════════════════
# L5: 可操作性
# ═══════════════════════════════════════

def _review_l5_actionability(
    trade_annotation: dict, monitoring_kpis: dict,
    risk_triggers: dict, confidence: dict,
) -> tuple[float, list[Flag]]:
    """检查报告是否能指导实际行动。"""
    score = 10.0
    flags = []

    # 交易标注完整性
    ta_keys = trade_annotation.keys() if trade_annotation else []
    if len(ta_keys) < 3:
        score -= 2
        flags.append(Flag(
            code="L5_TRADE_INCOMPLETE", layer=5, severity="warning",
            message=f"交易标注不完整: 仅有{len(ta_keys)}个字段",
            suggestion="确保 trade_annotation 包含 tier/total_score/dimension_scores",
        ))

    # KPI可验证性
    fin_kpis = monitoring_kpis.get("financial_verification_kpis", []) if monitoring_kpis else []
    if len(fin_kpis) < 1:
        score -= 2
        flags.append(Flag(
            code="L5_NO_KPI", layer=5, severity="warning",
            message="缺少财务验证KPI——无法在后续季度验证投资逻辑",
            suggestion="Agent-3 需生成至少1个可量化的财务KPI",
        ))

    # Bull/Bear触发条件是否具体
    bull_trigger = risk_triggers.get("bull_trigger", "") if risk_triggers else ""
    bear_trigger = risk_triggers.get("bear_trigger", "") if risk_triggers else ""
    for trigger, label in [(bull_trigger, "Bull"), (bear_trigger, "Bear")]:
        if not trigger or len(trigger) < 10:
            score -= 1.5
            flags.append(Flag(
                code=f"L5_{label}_TRIGGER_VAGUE",
                layer=5, severity="warning",
                message=f"{label}触发条件不具体或缺失: {trigger[:50]}",
                suggestion="触发条件应包含可量化的阈值(如'毛利率>35%'而非'毛利率提升')",
            ))

    # 置信度与操作建议一致性
    conf_score = confidence.get("overall_score", 5) if confidence else 5
    tier = trade_annotation.get("tier", "") if trade_annotation else ""
    if conf_score >= 7 and "规避" in str(tier):
        score -= 1.5
        flags.append(Flag(
            code="L5_CONF_TIER_CLASH", layer=5, severity="warning",
            message=f"置信度={conf_score}但交易建议为'规避'——高置信度不应伴随规避建议",
            suggestion="对齐 confidence 和 trade_annotation 的逻辑",
        ))

    return max(0, score), flags


# ═══════════════════════════════════════
# 主审阅函数
# ═══════════════════════════════════════

def review_report(agent3_output: dict, agent2_output: dict, agent1_output: dict) -> ReviewResult:
    """
    对单份报告执行五层审阅。

    输入: orchestrator 产出的 agent1/agent2/agent3 字典
    返回: ReviewResult 包含评级、标记、改进建议
    """
    core = agent1_output.get("packages", {}).get("core", {}).get("fields", {})
    routing = agent2_output.get("routing_decision", {})
    sv = agent3_output.get("scenario_valuation", {})
    vs = agent3_output.get("valuation_summary", {})
    conf = agent3_output.get("confidence", {})
    ta = agent3_output.get("trade_annotation", {})
    kpi = agent3_output.get("monitoring_kpis", {})
    triggers = agent3_output.get("risk_triggers", {})
    ccs = agent3_output.get("case_comparison_summary", {})
    narrative = agent3_output.get("narrative", "")
    scenarios = sv.get("scenario_details", {})

    stock_code = agent1_output.get("stock_code", "?")
    stock_name = core.get("stock_name", "?")

    result = ReviewResult(
        stock_code=stock_code,
        stock_name=stock_name,
        overall_grade="C",
        layer_scores={},
        flags=[],
    )

    # ── L0: 数据完整性 ──
    l0_score, l0_flags = _review_l0_data(core)
    result.layer_scores["L0_数据完整性"] = round(l0_score, 1)
    result.flags.extend(l0_flags)

    # ── L1: 路由合理性 ──
    l1_score, l1_flags = _review_l1_routing(core, routing)
    result.layer_scores["L1_路由合理性"] = round(l1_score, 1)
    result.flags.extend(l1_flags)

    # ── L2: 情景合理性 ──
    l2_score, l2_flags = _review_l2_scenarios(scenarios, core)
    result.layer_scores["L2_情景合理性"] = round(l2_score, 1)
    result.flags.extend(l2_flags)

    # ── L3: 案例锚定质量 ──
    l3_score, l3_flags = _review_l3_cases(ccs, scenarios)
    result.layer_scores["L3_案例锚定"] = round(l3_score, 1)
    result.flags.extend(l3_flags)

    # ── L4: 自洽性 ──
    l4_score, l4_flags = _review_l4_consistency(scenarios, vs, conf, narrative)
    result.layer_scores["L4_自洽性"] = round(l4_score, 1)
    result.flags.extend(l4_flags)

    # ── L5: 可操作性 ──
    l5_score, l5_flags = _review_l5_actionability(ta, kpi, triggers, conf)
    result.layer_scores["L5_可操作性"] = round(l5_score, 1)
    result.flags.extend(l5_flags)

    # ── 综合评级 ──
    weights = {"L0_数据完整性": 0.30, "L1_路由合理性": 0.20, "L2_情景合理性": 0.20,
               "L3_案例锚定": 0.10, "L4_自洽性": 0.10, "L5_可操作性": 0.10}
    overall = sum(result.layer_scores.get(k, 0) * v for k, v in weights.items())
    critical_count = sum(1 for f in result.flags if f.severity == "critical")
    warning_count = sum(1 for f in result.flags if f.severity == "warning")

    if overall >= 8.5 and critical_count == 0:
        result.overall_grade = "A"
    elif overall >= 7.0 and critical_count <= 1:
        result.overall_grade = "B"
    elif overall >= 5.0 and critical_count <= 2:
        result.overall_grade = "C"
    elif overall >= 3.0:
        result.overall_grade = "D"
    else:
        result.overall_grade = "F"

    # ── 关键强弱项 ──
    strengths = []
    weaknesses = []
    actions = []

    if l0_score >= 9:
        strengths.append("L0: 数据链完整，关键字段无缺失")
    if l1_score >= 8:
        strengths.append("L1: 路由逻辑清晰，模型选择有数据支撑")
    if l2_score >= 8:
        strengths.append("L2: 情景参数在合理边界内，概率分配有区分度")
    if l3_score >= 8:
        strengths.append("L3: 案例使用合理，非模板化判断")
    if l4_score >= 9:
        strengths.append("L4: 报告内部自洽，无算术矛盾")
    if l5_score >= 8:
        strengths.append("L5: KPI可执行，触发条件具体")

    for f in result.flags:
        if f.severity == "critical":
            weaknesses.append(f"[{f.code}] {f.message}")
            actions.append(f"[{f.code}] {f.suggestion}")
        elif f.severity == "warning":
            if len(weaknesses) < 5:
                weaknesses.append(f"[{f.code}] {f.message}")

    result.key_strengths = strengths
    result.key_weaknesses = weaknesses[:5]
    result.improvement_actions = actions[:5]

    # ── 工程控制论元注释 ──
    meta_parts = []
    if l0_score < 7:
        meta_parts.append("数据层有缺陷→下游所有推理不可靠。优先修复数据映射，再调prompt。")
    if result.overall_grade in ("D", "F"):
        meta_parts.append("系统级故障→不应将此报告呈现给用户。检查管线完整性。")
    if critical_count == 0 and warning_count <= 2:
        meta_parts.append("信号链完整→报告可作为投资决策参考。关注后续实际回报与预测的校准。")
    if result.overall_grade == "A" and l4_score < 9:
        meta_parts.append("报告整体优秀但自洽性有瑕疵→代码计算覆盖应已消除此问题，检查_compute_from_assumptions是否正确注入。")

    result.meta_note = " | ".join(meta_parts) if meta_parts else "报告质量可接受，建议定期校准验证。"

    return result


# ═══════════════════════════════════════
# 批量审阅 + 趋势分析
# ═══════════════════════════════════════

def review_batch(results: list[dict]) -> dict:
    """批量审阅多份报告，输出系统级趋势。"""
    reviews = []
    for r in results:
        rev = review_report(
            r.get("agent3", {}),
            r.get("agent2", {}),
            r.get("agent1", {}),
        )
        reviews.append(rev)

    grades = [r.overall_grade for r in reviews]
    grade_dist = {g: grades.count(g) for g in "ABCDF" if grades.count(g) > 0}

    # 高频flag
    all_codes = []
    for r in reviews:
        for f in r.flags:
            all_codes.append(f.code)
    from collections import Counter
    top_flags = Counter(all_codes).most_common(5)

    # 各层平均分
    layer_avgs = {}
    for layer_name in ["L0_数据完整性", "L1_路由合理性", "L2_情景合理性",
                        "L3_案例锚定", "L4_自洽性", "L5_可操作性"]:
        scores = [r.layer_scores.get(layer_name, 0) for r in reviews]
        layer_avgs[layer_name] = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "total_reports": len(reviews),
        "grade_distribution": grade_dist,
        "layer_averages": layer_avgs,
        "top_systemic_flags": [
            {"code": code, "count": count, "action": _suggest_action(code)}
            for code, count in top_flags
        ],
        "overall_health": "良好" if sum(1 for g in grades if g in "AB") / len(grades) > 0.6 else (
            "需关注" if sum(1 for g in grades if g in "DE") / len(grades) < 0.3 else "需改进"
        ),
    }


def _suggest_action(flag_code: str) -> str:
    """根据flag代码给出系统级改进建议。"""
    actions = {
        "L0_PB_MISMATCH": "修复 data_fetcher PB字段映射 (f2290=市净率)",
        "L0_MISSING_PB": "检查 valuation API 是否正常返回 f2290",
        "L0_PE_EXTREME": "检查 PE 字段映射 (f2250)，确认非 EV/EBITDA 误映射",
        "L0_RANK_OOB": "检查 profit_ability API 返回的排名字段范围",
        "L1_REASON_NO_DATA": "强化 Agent-2 提示词: routing_reason 必须引用具体数字",
        "L1_REASON_TOO_SHORT": "Agent-2 可能走了 fallback 路由——检查 DeepSeek API 是否正常",
        "L1_MODEL_A_LOW_ROIC": "模型A需要ROIC>8%，低ROIC应考虑 I(正常化) 或 E(EV/EBITDA)",
        "L1_MODEL_B_HIGH_ROIC": "盈利企业用PS模型不合理，应路由到盈利乘数族",
        "L1_MODEL_I_WEAK_SIGNAL": "模型I需要PE>80x+PB<3x的周期底部信号，当前信号偏弱",
        "L2_PROB_SUM": "启用代码强制归一化概率和",
        "L2_MONOTONICITY": "Agent-3 输出校验: bear<base<bull",
        "L2_BEAR_BELOW_CASH": "Bear情景应参照净资产或净现金设定底线",
        "L2_BULL_EXTREME": "Bull>500%需强有力的范式切换论证，检查案例锚定是否生效",
        "L2_PROB_OVERCONFIDENT": "概率过度集中(>75%)——鼓励更宽分布以反映不确定性",
        "L2_PROB_UNIFORM": "三情景概率均匀——基于事件验证度做差异化分配",
        "L3_NO_CASES": "补充该模型族的V3案例，或检查 case_loader 匹配逻辑",
        "L3_ALL_SUPERIOR": "案例比对提示词强化: 禁止全'优于'，必须附案例原文证据",
        "L3_ALL_INFERIOR": "检查是否因PB数据修正导致过度悲观，或确实缺乏可比案例",
        "L3_DISCOUNT_NOT_APPLIED": "强化折扣执行: target_param_discount_pct必须反映在bull数字上",
        "L4_ASYM_MISMATCH": "代码已覆盖asymmetry计算——检查 _compute_from_assumptions 是否调用",
        "L4_QUALITY_UPSIDE_CLASH": "修改质量标签定义: 反映'当前价格的投资质量'而非'业务质量'",
        "L4_NARRATIVE_MISMATCH": "叙事方向应与加权涨幅一致",
        "L5_NO_KPI": "Agent-3 提示词强化: 至少生成1个可量化财务KPI",
        "L5_TRADE_INCOMPLETE": "确保 trade_annotation 包含完整字段",
        "L5_BULL_TRIGGER_VAGUE": "触发条件必须包含可量化阈值(如'毛利率>35%'而非'毛利率提升')",
        "L5_BEAR_TRIGGER_VAGUE": "触发条件必须包含可量化阈值",
        "L5_CONF_TIER_CLASH": "对齐 confidence 和 trade_annotation 的逻辑",
    }
    return actions.get(flag_code, f"检查 {flag_code} 对应的代码/提示词逻辑")


# ── 便捷入口 ──

def review_from_orchestrator_result(result: dict) -> ReviewResult:
    """从 orchestrator.run() 的返回结果直接审阅。"""
    return review_report(
        result.get("agent3", {}),
        result.get("agent2", {}),
        result.get("agent1", {}),
    )
