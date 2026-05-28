"""
Agent-2b 路由判官 (RouteJudge) — V6

V6 的核心变化: 路由判决受 Agent-2a 的叙事诊断约束。
Agent-2a 划定模型族边界，Agent-2b 在族内选具体模型。

职责:
  1. 接收 2a 的 forward_to_routing 约束
  2. 在指定模型族内，通过硬约束筛选候选模型
  3. LLM 从剩余候选中选最优主模型 + 校验模型
  4. 校验模型选择策略受事件性质影响

原则:
  - 2a 的 family_constraint 是硬约束: 2b 不可跨族选主模型
  - 2b 保留独立验证权: 如果硬约束和锚判断冲突,标注 constraint_override
  - 校验模型策略: 突发→同类保守校验, 延续→跨族校验
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from valuation_utils import call_deepseek


# ═══════════════════════════════════════
# System Prompt — 精简版（叙事诊断已由 2a 完成）
# ═══════════════════════════════════════

ROUTING_V6_PROMPT = """你是估值路由判官。叙事诊断师(Agent-2a)已完成市场叙事诊断——你需要在指定模型族内做技术选择。

# 输入解读

用户消息中包含 Agent-2a 的完整叙事诊断结论。在开始硬约束筛选之前，先理解叙事：

**1. 理解市场在赌什么 (core_bet + narrative_lifecycle)**
- 导入期/成长期公司 → 模型应更宽松(允许亏损,允许高PS),因为财务指标滞后于叙事
- 成熟期公司 → 模型应更严格(要求盈利,要求ROIC),因为财务指标应已兑现叙事
- 转型期公司 → 注意 anchor_conflict: 旧业务盈利不代表新业务锚。若 SOTP 触发,直接用 J

**2. 理解锚冲突 (anchor_conflict)**
- 若 2a 标注了锚冲突(如"PE中位但PS极端高位"),说明估值指标与叙事方向不一致
- 这种情况下,模型选择应偏向叙事方向而非财务指标方向
- 例如: ROIC>8% 但叙事是 revenue → 应考虑 B 的转型例外,而非机械选 A

**3. 理解事件性质 (3D光谱 + 分布形状 + 计价程度)**
- 高二元性(wide_bimodal): 结果可能是0或1,模型应对极端情景敏感
- 高先例丰富度(narrow_concentrated): 历史模板清晰,可用更精确的模型(如K两阶段DCF)
- 已充分计价(fully priced): 上行空间有限,校验模型应保守

# 执行流程

## Step 1: 在指定族内做硬约束筛选

你只能在 **{FAMILY_CONSTRAINT}** 族内选择。该族包含的模型:
{FAMILY_MODELS}

对族内每个模型,按准入条件逐条检查。硬约束不通过的排除。
**叙事优先原则**: 硬约束是必要条件,不是充分条件。通过硬约束≠模型合适——还需Step 2的叙事契合度判断。

## Step 2: 从剩余候选中选最优主模型

按以下优先级,综合叙事和财务数据:
- 优先级1: **叙事契合度** — 模型是否匹配 2a 判断的"市场在赌什么"?
  例: 叙事说"押注CPO供应链导入+国产替代"(→未来收入爆发),公司当前盈利但锚是revenue→B比A更契合叙事
  例: 叙事说"盈利拐点+ROIC改善"(→利润兑现期),ROIC>8%且增长曲线可预见→K比A更精准
- 优先级2: **财务数据匹配度** — 模型的参数假设是否与当前财务数据兼容?
- 优先级3: **事件光谱匹配度** — 分布形状是否支持该模型的假设?
  例: narrow_concentrated(高先例)→K两阶段DCF可预见性强; wide_unimodal→G PEG的灵活性更合适

routing_reason 必须引用: (1) 2a的叙事线索 (2) 具体财务数据。≥80字。

## Step 3: 选择校验模型

校验模型策略受事件分布形状影响:
- **wide_bimodal / wide_bimodal_date_anchored** (高二元性): 选同类保守校验 — 结果可能有极端值,校验模型应与主模型同族但更保守
- **wide_unimodal** (高不确定性): 可跨族校验 — 方向确定但幅度不确定,用不同视角交叉验证
- **narrow_concentrated / narrow_base_dominant** (低不确定性): 可跨族校验 — 历史模板清晰,用另一范式做参照有参考价值

校验模型也必须通过硬约束。若所有校验候选都被硬约束排除,标注"同模型自校验"并降级。

## Step 4: 约束合规检查

- 主模型是否在 {FAMILY_CONSTRAINT} 族内 → constraint_compliance
- 若发现不得不跨族（如硬约束排除了族内所有模型），设置 constraint_override=true
  ——这是极端情况，必须在 override_rationale 中详细说明
- 若使用了B的转型例外,constraint_override=true, override_rationale 说明原因

# 模型族-模型映射

| 族 | 包含模型 |
|----|---------|
| earnings_multiples | A(ROIC-RR DCF), C(DCF+拐点), G(PEG), I(盈利正常化), K(两阶段DCF) |
| revenue_multiples | B(PS+TAM) |
| asset_multiples | D(PB-ROE), H(NAV) |
| resource | E(EV/EBITDA+资源) |
| pipeline | F(rNPV) |
| sotp | J(SOTP) |

# 模型准入条件（仅列关键硬约束）

**A (ROIC-RR DCF)**: ROIC>8%, 净利润>0
**C (DCF+拐点)**: 当前亏损/微利, 有可识别拐点时间节点
**G (PEG)**: 利润增速>30%, 盈利为正
**I (盈利正常化)**: 利润波动源于行业周期, 无硬资产资源
**B (PS+TAM)**: 叙事围绕收入/TAM。默认约束: 亏损/微利(ROIC<8%)。**转型例外**: 若2a的叙事诊断满足以下3条,允许盈利企业使用B:
  (a) 投资主题明确指向新业务的收入/TAM,非旧业务盈利增长
  (b) PS处于历史高位(>70分位)且PE正常或偏低——市场确实在定价收入而非利润
  (c) 2a的primary_anchor_evidence提供了上述判断的数据支持
  使用转型例外时 constraint_override=true,routing_reason标注"旧业务盈利不反映叙事锚"
**D (PB-ROE)**: 重资产(总资产/净资产>1.5), ROE有改善逻辑
**E (EV/EBITDA+资源)**: 拥有自然资源, 事件核心是资源量/价
**H (NAV)**: 隐蔽资产型, 事件触发资产价值再发现
**F (rNPV)**: 仅限创新药/biotech, 临床阶段管线
**K (两阶段DCF)**: 盈利企业(ROIC>8%)且预期高增长持续3-7年后回落。与A/G的区别:
  - K vs A: A假设ROIC和利润永续,K承认高增长不可持续→在第N年切换到终值PE
  - K vs G: G用PEG封顶PE,K用折现反映增长价值→K对高增长标的更友好,不会被PEG压制
  选择K的场景: 公司当前高增长(>25%)但行业终局清晰(5年后增速必然回落)
  不选K的场景: 增速已放缓到行业水平→选A;增速波动大难以预测→选G
**J (SOTP)**: 2a已验证: 估值范式冲突 + 副锚占比≥20% + 数据可支撑SOTP。若sotp_triggered=false,跳过J,按主锚选模型。
  **SOTP的本质**: 防止用主锚去估"另一类业务"时产生系统性偏差。
  **SOTP估值方法**: 分部独立估(各用正确的倍数锚),加总。行业倍数参照来自knowledge_supplement。不要求分部利润精确。
  **数据不足时**: 2a会设置sotp_triggered=false,此时以主锚为准——宁可单锚近似,也不在无数据时强行SOTP。
  **SOTP触发时必填字段**: 当主模型=J时，必须额外输出 `sotp_primary_segment_model`——为叙事主锚分部（2a的primary_anchor）选择最合适的模型。例如primary_anchor=revenue→选B(PS+TAM)；primary_anchor=earnings→选A/K(ROIC-DCF)。这个字段告诉SOTP Agent叙事分部该用什么参数体系。

# 输出格式

```json
{
  "routing_decision": {
    "primary_model": "K",
    "model_category": "Earnings Multiples",
    "routing_reason": "引用叙事线索+财务数据,≥80字。必须说明为什么这个模型最适合2a判断的叙事方向",
    "validation_models": ["A"],
    "validation_rationale": "延续事件→跨族校验: 用A(DCF)验证K(两阶段DCF)的估值区间",
    "validation_strategy": "cross_family | conservative_same_family | self_validation",
    "constraint_compliance": {
      "family_constraint_applied": "revenue_multiples",
      "constraint_override": false,
      "override_rationale": ""
    },
    "anchor_shift_warning": "如果存在锚切换风险,标注在此",
    "sotp_primary_segment_model": "仅当primary_model=J时填写,如B/A/K。为叙事主锚分部选模型"
  }
}
```

# 核心约束
1. 不可跨族选主模型（除非族内全部被硬约束排除）
2. routing_reason 必须引用: (1) 2a的叙事线索 (2) 具体财务数据
3. 叙事理解优先于硬约束——先读懂市场在赌什么,再做技术筛选
4. 输出纯 JSON
"""


# ═══════════════════════════════════════
# 模型族映射
# ═══════════════════════════════════════

FAMILY_MODELS = {
    "earnings_multiples": "A(ROIC-RR DCF), C(DCF+拐点), G(PEG), I(盈利正常化), K(两阶段DCF)",
    "revenue_multiples": "B(PS+TAM)",
    "asset_multiples": "D(PB-ROE), H(NAV)",
    "resource": "E(EV/EBITDA+资源)",
    "pipeline": "F(rNPV)",
    "sotp": "J(SOTP)",
}

MODEL_FAMILY_MAP = {
    "A": "earnings_multiples", "C": "earnings_multiples",
    "G": "earnings_multiples", "I": "earnings_multiples",
    "B": "revenue_multiples",
    "D": "asset_multiples", "H": "asset_multiples",
    "E": "resource",
    "F": "pipeline",
    "J": "sotp",
}


# ═══════════════════════════════════════
# 用户消息构建
# ═══════════════════════════════════════

def _build_routing_user_message(
    data_package: dict,
    agent2a_output: dict,
    event_data: dict,
) -> str:
    """构建 Agent-2b 用户消息：注入数据+约束。"""
    core = data_package.get("packages", {}).get("core", {}).get("fields", {})
    stock = core.get("stock_name", data_package.get("stock_name", ""))
    code = data_package.get("stock_code", "")
    fwd = agent2a_output.get("forward_to_routing", {})
    mn = agent2a_output.get("market_narrative", {})
    ep = agent2a_output.get("event_pricing", {})
    epr = ep.get("event_profile", {})
    pa = ep.get("pricing_assessment", {})

    roic = core.get("roic_pct", 0)
    mcap = core.get("market_cap_yi", 0)
    rev = core.get("revenue_ttm_yi", 0)
    np = core.get("net_profit_ttm_yi", 0)
    pe = core.get("pe_ttm", 0)
    pb = core.get("pb", 0)
    ps = core.get("ps_ttm", 0)
    equity = core.get("total_equity_yi", 0)
    assets = core.get("total_assets_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    cash = core.get("cash_yi", 0)
    gm = core.get("gross_margin_pct", 0)
    nm = core.get("net_margin_pct", 0)

    family = fwd.get("model_family_constraint", "earnings_multiples")
    family_models = FAMILY_MODELS.get(family, "A/C/G/I")
    sas = mn.get("secondary_anchors", [])

    msg = f"""# 路由任务: {stock}({code})

## 叙事诊断 (Agent-2a 完整结论)

**市场在赌什么**: {mn.get('core_bet','?')}
**叙事生命周期**: {mn.get('narrative_lifecycle','?')}

**估值锚**: {mn.get('primary_anchor','?')}
**锚判断依据**: {mn.get('primary_anchor_evidence','?')[:300]}

**锚冲突**: {mn.get('anchor_conflict','') or '无'}
**SOTP触发**: {mn.get('sotp_triggered',False)}
**SOTP理由**: {mn.get('sotp_rationale','') or '—'}

**事件分布**: {epr.get('distribution_shape','?')} — {epr.get('shape_rationale','?')[:150]}
**3D光谱**: 时点确定性{epr.get('timing_certainty','?')}/10 | 结果二元性{epr.get('outcome_binaryness','?')}/10 | 先例丰富度{epr.get('precedent_richness','?')}/10
**事件计价**: {pa.get('overall_priced_in','?')} ({pa.get('priced_in_estimate','?')}) | 剩余催化: {pa.get('residual_catalyst','?')[:150]}

**路由约束**:
- 模型族: **{family}** → 可选模型: {family_models}
- 排除族: {fwd.get('excluded_families',[])}
- 定价偏向: {fwd.get('pricing_bias','?')}
- 路由风险: {fwd.get('key_risk_for_routing','') or '无'}
{chr(10).join(f'- 副锚: {sa.get("segment")} → {sa.get("anchor")} ({sa.get("revenue_share_pct")}%收入)' for sa in sas) if sas else ''}

## 核心财务数据
| 指标 | 数值 |
|------|------|
| 市值 | {mcap:.0f}亿 |
| TTM营收 | {rev:.1f}亿 |
| TTM净利润 | {np:.1f}亿 |
| ROIC | {roic:.1f}% |
| 毛利率/净利率 | {gm:.1f}% / {nm:.1f}% |
| PE/PB/PS | {pe:.1f}x / {pb:.1f}x / {ps:.1f}x |
| 净资产 | {equity:.0f}亿 |
| 总资产 | {assets:.0f}亿 |
| 有息负债/现金 | {debt:.1f}亿 / {cash:.1f}亿 |
| 异常标记 | {json.dumps(core.get('caution_flags',[]), ensure_ascii=False)} |

## 事件背景
{event_data.get('investment_theme','')[:500]}
{event_data.get('event_deduction','')[:500]}

请在指定模型族内完成路由判决。输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# Agent2b 主类
# ═══════════════════════════════════════

# 保留 V5 的 fallback 路由逻辑（纯代码，DeepSeek 不可用时）
# 但适配 V6 的家族约束

FALLBACK_HARD_CONSTRAINTS = {
    "A": lambda c: c.get("roic_pct", 0) > 8 and c.get("net_profit_ttm_yi", 0) > 0,
    "B": lambda c: c.get("roic_pct", 0) < 8 or c.get("net_profit_ttm_yi", 0) <= 0,
    "C": lambda c: c.get("net_profit_ttm_yi", 0) <= 0,
    "D": lambda c: (c.get("total_assets_yi", 0) / max(c.get("total_equity_yi", 1), 1)) > 1.5,
    "E": lambda c: "矿" in str(c.get("industry_sw_l1", "")) or "有色" in str(c.get("industry_sw_l1", "")),
    "G": lambda c: c.get("roic_pct", 0) > 15,
    "H": lambda c: c.get("cash_yi", 0) > c.get("total_equity_yi", 0) * 0.5,
    "I": lambda c: c.get("pe_ttm", 0) > 80,
}

FAMILY_TO_MODELS = {
    "earnings_multiples": ["A", "C", "G", "I", "K"],
    "revenue_multiples": ["B"],
    "asset_multiples": ["D", "H"],
    "resource": ["E"],
    "pipeline": ["F"],
    "sotp": ["J"],
}


class RouteJudgeV6:
    """路由判官 — V6 Agent-2b。"""

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key

    def run(
        self,
        data_package: dict,
        agent2a_output: dict,
        event_data: dict | None = None,
    ) -> dict:
        """
        执行路由判决。

        data_package: Agent-1 输出
        agent2a_output: Agent-2a 输出（含 forward_to_routing 约束）
        event_data: Coze Agent0 事件数据

        返回: {routing_decision, ...}
        """
        event_data = event_data or {}
        fwd = agent2a_output.get("forward_to_routing", {})
        family = fwd.get("model_family_constraint", "earnings_multiples")
        dist_shape = fwd.get("distribution_shape", "wide_unimodal")

        # ── 构建 prompt ──
        mn = agent2a_output.get("market_narrative", {})
        prompt = ROUTING_V6_PROMPT.replace(
            "{PRIMARY_ANCHOR}", mn.get("primary_anchor", "?")
        ).replace(
            "{FAMILY_CONSTRAINT}", family
        ).replace(
            "{FAMILY_MODELS}", FAMILY_MODELS.get(family, "?")
        ).replace(
            "{EXCLUDED_FAMILIES}", str(fwd.get("excluded_families", []))
        ).replace(
            "{DISTRIBUTION_SHAPE}", dist_shape
        ).replace(
            "{PRICING_BIAS}", fwd.get("pricing_bias", "uncertain")
        )

        user_msg = _build_routing_user_message(data_package, agent2a_output, event_data)

        # ── LLM 调用 ──
        result = call_deepseek(
            prompt, user_msg,
            max_tokens=8192, temperature=0,
            api_key=self.api_key,
        )

        if "_parse_error" in result:
            result = call_deepseek(
                prompt, user_msg,
                max_tokens=8192, temperature=0,
                api_key=self.api_key,
            )

        if "_parse_error" in result:
            return {
                "routing_decision": self._fallback_routing(data_package, agent2a_output),
                "_fallback": True,
            }

        routing = result.get("routing_decision", result)
        if not routing or not routing.get("primary_model"):
            return {
                "routing_decision": self._fallback_routing(data_package, agent2a_output),
                "_fallback": True,
            }

        return {"routing_decision": routing}

    def _fallback_routing(self, data_package: dict,
                          agent2a_output: dict) -> dict:
        """纯代码 fallback，遵守 2a 的族约束。"""
        core = data_package.get("packages", {}).get("core", {}).get("fields", {})
        fwd = agent2a_output.get("forward_to_routing", {})
        family = fwd.get("model_family_constraint", "earnings_multiples")
        candidates = FAMILY_TO_MODELS.get(family, ["A"])

        # 在族内按硬约束筛选
        valid = [m for m in candidates
                 if m in FALLBACK_HARD_CONSTRAINTS
                 and FALLBACK_HARD_CONSTRAINTS[m](core)]

        primary = valid[0] if valid else (candidates[0] if candidates else "A")

        # 校验模型策略
        dist_shape = fwd.get("distribution_shape", "wide_unimodal")
        # 分布形状→校验策略: 高二元性→同类保守, 其他→跨族
        if dist_shape in ("wide_bimodal", "wide_bimodal_date_anchored"):
            validation = [m for m in candidates if m != primary][:1]
        else:
            all_models = ["A", "B", "D", "E"]
            validation = [m for m in all_models
                         if m != primary
                         and m in FALLBACK_HARD_CONSTRAINTS
                         and FALLBACK_HARD_CONSTRAINTS[m](core)][:1]

        return {
            "primary_model": primary,
            "model_category": (
                "Earnings Multiples" if family == "earnings_multiples"
                else "Revenue Multiples" if family == "revenue_multiples"
                else "Asset/Resource"
            ),
            "routing_reason": f"Fallback路由(LLM不可用)。族={family}, 候选={candidates}, 选定={primary}",
            "validation_models": validation,
            "validation_rationale": "Fallback: LLM不可用,代码规则选校验模型",
            "validation_strategy": (
                "conservative_same_family" if dist_shape in ("wide_bimodal", "wide_bimodal_date_anchored")
                else "cross_family"
            ),
            "constraint_compliance": {
                "family_constraint_applied": family,
                "constraint_override": False,
                "override_rationale": "",
            },
            "anchor_shift_warning": "",
        }


# ── 便捷函数 ──

def route_judge_v6(
    data_package: dict,
    agent2a_output: dict,
    event_data: dict | None = None,
) -> dict:
    """便捷入口：运行 V6 路由判决。"""
    judge = RouteJudgeV6()
    return judge.run(data_package, agent2a_output, event_data)
