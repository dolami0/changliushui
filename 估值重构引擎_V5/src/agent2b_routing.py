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

ROUTING_V6_PROMPT = """你是估值路由判官。叙事诊断师已经确定了市场在为什么定价——你只需要在指定模型族内做技术选择。

# 输入约束

叙事诊断师的结论:
- 估值锚 = {PRIMARY_ANCHOR}
- 模型族约束 = {FAMILY_CONSTRAINT}（不可跨族）
- 排除族 = {EXCLUDED_FAMILIES}
- 分布形状 = {DISTRIBUTION_SHAPE}
- 定价偏向 = {PRICING_BIAS}

# 执行流程

## Step 1: 在指定族内做硬约束筛选

你只能在 **{FAMILY_CONSTRAINT}** 族内选择。该族包含的模型:
{FAMILY_MODELS}

对族内每个模型,按准入条件逐条检查。硬约束不通过的排除。

## Step 2: 从剩余候选中选最优主模型

按以下优先级:
- 优先级1: 估值锚匹配度 — 模型的锚是否与叙事诊断一致
- 优先级2: 事件-模型契合度 — 模型是否适合事件驱动的估值场景
- 优先级3: 案例支持度 — 同族案例的模型选择是否一致

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

# 模型族-模型映射

| 族 | 包含模型 |
|----|---------|
| earnings_multiples | A(ROIC-RR DCF), C(DCF+拐点), G(PEG), I(盈利正常化) |
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
**J (SOTP)**: **仅当2a的 sotp_triggered=true 时使用。** 2a已验证: 估值范式冲突 + 副锚占比≥20% + 数据可支撑SOTP。若sotp_triggered=false,跳过J,按主锚选模型。
  **SOTP的本质**: 防止用主锚去估"另一类业务"时产生系统性偏差。
  **SOTP估值方法**: 分部独立估(各用正确的倍数锚),加总。行业倍数参照来自knowledge_supplement。不要求分部利润精确。
  **数据不足时**: 2a会设置sotp_triggered=false,此时以主锚为准——宁可单锚近似,也不在无数据时强行SOTP。

# 输出格式

```json
{
  "routing_decision": {
    "primary_model": "B",
    "model_category": "Revenue Multiples",
    "routing_reason": "引用财务数据+叙事诊断结论,≥80字",
    "validation_models": ["A"],
    "validation_rationale": "延续事件→跨族校验: 用A(DCF)验证B(PS+TAM)的估值区间",
    "validation_strategy": "cross_family | conservative_same_family | self_validation",
    "constraint_compliance": {
      "family_constraint_applied": "revenue_multiples",
      "constraint_override": false,
      "override_rationale": ""
    },
    "anchor_shift_warning": "如果存在锚切换风险,标注在此"
  }
}
```

# 核心约束
1. 不可跨族选主模型（除非族内全部被硬约束排除）
2. routing_reason 必须引用具体财务数据
3. 输出纯 JSON
"""


# ═══════════════════════════════════════
# 模型族映射
# ═══════════════════════════════════════

FAMILY_MODELS = {
    "earnings_multiples": "A(ROIC-RR DCF), C(DCF+拐点), G(PEG), I(盈利正常化)",
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

    msg = f"""# 路由任务: {stock}({code})

## 叙事诊断约束 (Agent-2a 结论)
- 主锚: {agent2a_output.get('market_narrative',{}).get('primary_anchor','?')}
- 模型族约束: **{family}** → 可选: {family_models}
- 排除族: {fwd.get('excluded_families',[])}
- 事件性质: {fwd.get('distribution_shape','?')}
- 定价偏向: {fwd.get('pricing_bias','?')}
- 路由风险: {fwd.get('key_risk_for_routing','')}
- SOTP触发: {agent2a_output.get('market_narrative',{}).get('sotp_triggered',False)}

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
{event_data.get('investment_theme','')}
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
    "earnings_multiples": ["A", "C", "G", "I"],
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
