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

用户消息最前面是 **投资地图**（Agent-Baseline 预合成的公司全貌），然后是 Agent-2a 的叙事诊断结论，最后是原始财务数据和事件素材。

**使用投资地图理解公司** — 地图已替你完成了"这家公司是谁"的认知工作:
- **生命周期与业务结构**（地图维度一+四）: 公司处于什么阶段？新旧业务如何拆分？这直接影响 SOTP 判定。
- **财务基线**（地图维度二）: ROIC vs WACC、毛利率结构、现金跑道——这些是模型硬约束的输入。
- **量化锚点**（地图维度六）: 产能、价格、市占率——这些决定增长假设的物理上限。
- **脆弱点**（地图维度五）: 当前叙事的薄弱环节——如果脆弱度高，路由应倾向于保守模型。

**然后参考 2a 判定** — 2a 已完成锚识别和事件计价:

**1. 理解市场在赌什么 (core_bet + narrative_lifecycle)**
- 导入期/成长期公司 → 模型应更宽松(允许亏损,允许高PS),因为财务指标滞后于叙事
- 成熟期公司 → 模型应更严格(要求盈利,要求ROIC),因为财务指标应已兑现叙事
- 转型期公司 → 注意 anchor_conflict: 旧业务盈利不代表新业务锚。若 SOTP 触发,直接用 J
- **交叉验证**: 地图中的生命周期判定可能比 2a 更详细——当地图标注"转型期+周期型混合"时，路由需要考虑双重属性。

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
**G (PEG)**: 利润增速>30%, 盈利为正。**PEG的本质是用增速锚定PE——这要求增速必须是结构性驱动而非均值回归。**

**G的准入条件——两个前提必须同时满足:**

1. **增长驱动必须是结构性而非周期回归**: 增速来自新产品/新市场/市占率提升/技术突破——而不是来自周期底部的低基数效应。区分方法:
   - ✅ 结构性: "KRrF光刻胶通过验证,收入从0→1.5亿,增速200%"——新产品驱动,可持续
   - ❌ 均值回归: "TTM净利13.3亿是煤价低谷,煤价回升后利润跳至30亿,增速+130%"——低基数驱动,不可持续
   - **判定标准**: 如果当前TTM利润远低于过去3年中枢（<50%），且增速预测主要来自利润恢复而非新业务驱动，则增速不是结构性的 → G不适用。

	2. **行业估值范式参照**: G(PEG)是成长股的估值范式——利润持续增长、PE随增速线性外推。不是所有行业的默认估值语言。
	   - 周期行业（煤炭/有色/钢铁/化工）的默认范式是 EV/EBITDA 或盈利正常化——利润波动源于价格周期，均值回归不是"增长"。用 PEG 给周期股估值是范式错误。
	   - 资源行业（矿业/石油）的默认范式是 EV/EBITDA 或 NAV——标的价值在资源储量和价格，不在盈利增速。
	   - 金融行业（银行/保险）的默认范式是 PB-ROE——盈利增速受资本约束。
	   - **判定**: 如果2a判定的锚类型与行业默认估值范式冲突（如周期行业判了earnings锚且准备用PEG），检查是否确有结构性转型（新产品/新市场）改变了公司的行业属性。若无，按行业默认范式选模型。

**不选G的典型场景**:
- 周期底部利润失真,增速来自低基数→选**I(盈利正常化)**。I的"正常化利润"可以包含供给侧改革的改善效果。
- 有明确资源/资产锚且周期底部流量指标全部失真→选**E(资源/EV-EBITDA)**或**H(NAV)**做底线校验。
- 增长虽高但波动剧烈、PEG难以锚定→选**I**做盈利中枢估计,比G的PEG锚定更可靠
**I (盈利正常化)**: 利润波动源于行业周期, 无硬资产资源
**B (PS+TAM)**: 叙事围绕收入/TAM。默认约束: 亏损/微利(ROIC<8%)。**转型例外**: 若2a的叙事诊断满足以下3条,允许盈利企业使用B:
  (a) 投资主题明确指向新业务的收入/TAM,非旧业务盈利增长
  (b) PS处于历史高位(>70分位)且PE正常或偏低——市场确实在定价收入而非利润
  (c) 2a的primary_anchor_evidence提供了上述判断的数据支持
  使用转型例外时 constraint_override=true,routing_reason标注"旧业务盈利不反映叙事锚"

	**转型例外的否决条件——以下情况不得使用B,应选J(SOTP):**
	B模型公式=总收入×(1+CAGR)³×PS。当传统盈利业务占比>40%时,这套公式会把旧业务的低速收入也赋予新业务的PS倍数——系统性高估。
	判定: 若2a识别出副锚(earnings锚的存量业务),且该副锚收入占比>40%,且SOTP四条件实质满足→**禁止B转型例外,必须选J**。SOTP把新旧分开估值,是解决这个结构性问题的唯一正确路径。
**D (PB-ROE)**: 重资产(总资产/净资产>1.5), ROE有改善逻辑
**E (EV/EBITDA+资源)**: 拥有自然资源, 事件核心是资源量/价
**H (NAV)**: 隐蔽资产型, 事件触发资产价值再发现
**F (rNPV)**: 创新药/biotech — 覆盖从临床前到商业化的全生命周期。rNPV 的核心能力是**概率加权现金流折现**，可以统一处理:
  - 已上市产品: PoS=100%, 峰值销售×折现率 → 就是 rNPV 的特例
  - 在研管线: PoS×峰值销售×折现率
  - BD/授权/里程碑收入: 概率加权的各期里程碑付款折现
  rNPV 的优势: 不需要拆分部、不需要切换估值锚——管线、BD、上市产品都用同一套 PoS×现金流的逻辑框架，天然避免了锚冲突。
  **触发条件**: 2a 识别出公司价值主要由产品管线驱动（不论当前是否有收入），且管线数据可获取（火山搜索中的靶点/适应症/临床进度/峰值销售预测）。如果 2a 的 primary_anchor 不是 pipeline 但公司的核心增长驱动力是管线——你仍然可以选择 F——因为 rNPV 能统一覆盖已上市和未上市产品。
  **与 SOTP 的区分**: 当公司同时有上市产品和管线时，SOTP 会拆成两个分部用不同锚——但 rNPV 更优，因为它用 PoS 统一处理了所有产品的不确定性。只有当公司有一块业务**完全不是管线驱动**（如 CRO/CDMO 服务、原料药代工）时，才应选 SOTP。
**K (两阶段DCF)**: **仅限earnings_multiples族内选择**。适用于当前盈利、高增长(>25%)、行业终局清晰(5年后增速必然回落)、且**NOPAT起点可支撑DCF**的标的。与A/G/I的区别:
  - K vs A: A假设ROIC和利润永续→适合稳态盈利公司; K承认高增长不可持续→在第N年切换到终值PE→适合"成长→成熟"过渡期
  - K vs G: G用PEG封顶PE→适合增速波动大但PEG可锚定的标的; K用两阶段折现→适合增长路径可预见的标的
  - K vs I: I假设利润波动是周期性的(均值回归)→适合周期股; K假设增长是结构性的(增速回落≠消失)→适合成长股
  **选择K的充分条件**(缺一不可):
    (a) NOPAT_TTM > 0.5亿 且 NOPAT/市值 > 0.8% — DCF需要NOPAT起点,否则退化为终值PE赌注
    (b) 当前高增长(>25%)且可持续3-7年 — 有行业/产能/订单锚点约束增速上限
    (c) 行业终局清晰 — 5-7年后增速回落到什么水平、稳态PE多少,可以基于行业历史判断
  **不选K的场景**:
    - NOPAT起点过低→选A(若ROIC>8%)或G(若增速可见)
    - 增速已回落到行业水平→选A(永续DCF)
    - 增速波动大、难以预测→选I(盈利正常化),比G的PEG锚定更可靠（若增速来自周期底部均值回归而非结构性增长,G不适用——参见G的准入条件）
    - primary_anchor=revenue→此标的属于revenue_multiples族,应选B; K仅限earnings_multiples族内使用
  **注意**: K是earnings_multiples族内最"进取"的模型——它比A更友好(承认增长会回落),但比G更严格(要求终局可见)。不要因为K"看起来更精确"就选它——如果NOPAT起点或终局可见性不满足条件,K的DCF退化为终值PE赌注,不如坦诚用A、I或G。
**J (SOTP)**: 2a已验证: 估值范式冲突 + 副锚占比≥20% + 数据可支撑SOTP。若sotp_triggered=false,跳过J,按主锚选模型。
  **重要优先规则**: 如果公司属于创新药/biotech且核心价值由管线驱动 → **F(rNPV)优先于J**。rNPV 用 PoS×现金流统一覆盖上市产品+在研管线+BD授权，不需要拆分部。只有当存在非管线驱动的业务（如CRO/CDMO/原料药代工）且占比≥20%时，才考虑J。
  **SOTP的本质**: 防止用主锚去估"另一类业务"时产生系统性偏差。
  **SOTP估值方法**: 分部独立估(各用正确的倍数锚),加总。行业倍数参照来自knowledge_supplement。不要求分部利润精确。
  **数据不足时**: 2a会设置sotp_triggered=false,此时以主锚为准——宁可单锚近似,也不在无数据时强行SOTP。
  **SOTP触发时必填字段**: 当主模型=J时，必须额外输出 `sotp_primary_segment_model`——为叙事主锚分部（2a的primary_anchor）选择最合适的模型。规则与标准管线一致：
    - primary_anchor=revenue → **仅B(PS+TAM)**。即使产品数据可获取,也不选K——K是earnings模型,不跨界到revenue
    - primary_anchor=earnings → A(ROIC-RR DCF)/K(两阶段DCF)/G(PEG)。选K必须满足:NOPAT>0.5亿、NOPAT/市值>0.8%、增速>25%、终局可见——不满足则选A或G
    - primary_anchor=asset → D(PB-ROE)/H(NAV)
    - 这个字段告诉SOTP Agent叙事分部该用什么参数体系

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
    "sotp_primary_segment_model": "仅当primary_model=J时填写,如B/A/K。为叙事主锚分部选模型",
    "event_driven_segment": "透传自2a的forward_to_routing.event_driven_segment。{segment, anchor}或空对象{}"
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
    "K": "earnings_multiples",
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
    volc_data: dict | None = None,
    baseline_report: str | None = None,
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

    # ── V7: 投资地图 ──
    baseline_section = ""
    if baseline_report and len(baseline_report) > 100:
        baseline_section = f"""
## 投资地图 — Agent-Baseline 合成（事件冲击前的企业全貌）

{baseline_report}

---
"""

    msg = f"""# 路由任务: {stock}({code})
{baseline_section}

## 叙事诊断 (Agent-2a 完整结论)

**市场在赌什么**: {mn.get('core_bet','?')}
**叙事生命周期**: {mn.get('narrative_lifecycle','?')}

**估值锚**: {mn.get('primary_anchor','?')}
**锚判断依据**: {mn.get('primary_anchor_evidence','?')[:300]}

**锚冲突**: {mn.get('anchor_conflict','') or '无'}
**SOTP触发**: {mn.get('sotp_triggered',False)}
**SOTP理由**: {mn.get('sotp_rationale','') or '—'}
**事件驱动分部** (2a-1j): {json.dumps(fwd.get('event_driven_segment', {}), ensure_ascii=False) if fwd.get('event_driven_segment') and isinstance(fwd.get('event_driven_segment'), dict) and fwd.get('event_driven_segment') else '事件催动所有分部/非SOTP路由'}

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
{event_data.get('investment_theme','')}
{event_data.get('event_deduction','')}

## 火山联网搜索 — 市场量化预期（产能/订单/券商预测/可比估值）
{volc_data.get('volc_text', '') if volc_data else '（未触发火山搜索）'}

请在指定模型族内完成路由判决。注意: K(两阶段DCF)仅限earnings_multiples族内使用——revenue_multiples族应选B。输出纯 JSON。
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
    "K": lambda c: (c.get("nopat_yi", 0) or (c.get("net_profit_ttm_yi", 0) * 0.8)) > 0.5
         and (c.get("nopat_yi", 0) or (c.get("net_profit_ttm_yi", 0) * 0.8)) / max(c.get("market_cap_yi", 1), 1) > 0.008,
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
        volc_data: dict | None = None,
        baseline_report: str | None = None,
    ) -> dict:
        """
        执行路由判决。

        data_package: Agent-1 输出
        agent2a_output: Agent-2a 输出（含 forward_to_routing 约束）
        event_data: Coze Agent0 事件数据
        volc_data: V6.4 — 火山联网搜索补充（产能/订单/券商预测，用于K/B判定）
        baseline_report: V7 Agent-Baseline 投资地图报告

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

        user_msg = _build_routing_user_message(data_package, agent2a_output, event_data, volc_data,
                                                baseline_report=baseline_report)

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

        # ── 代码层硬校验: K模型经济可行性 ──
        # K(DCF)对NOPAT起点过低的标的会退化为"终值PE赌注"
        # ——阶段1 FCFF≈0(RR封顶0.9), 终值被WACC折现杀穿
        if routing.get("primary_model") == "K":
            core_k = data_package.get("packages", {}).get("core", {}).get("fields", {})
            nopat_k = core_k.get("nopat_yi", 0)
            mcap_k = core_k.get("market_cap_yi", 100)
            nopat_ratio = nopat_k / max(mcap_k, 1)
            if nopat_k < 0.5 or nopat_ratio < 0.008:
                # NOPAT起点过低, DCF不可行 → 回退到A或B（尊重Agent-2a锚选择）
                anchor = (agent2a_output or {}).get("market_narrative", {}).get("primary_anchor", "earnings")
                fallback = "B" if anchor == "revenue" else "A"
                print(f"  [RouteJudge] K blocked: NOPAT={nopat_k:.2f}yi NOPAT/mcap={nopat_ratio*100:.2f}% < 0.8% → override to {fallback}", flush=True)
                routing["primary_model"] = fallback
                routing["model_category"] = "Revenue Multiples" if fallback == "B" else "Earnings Multiples"
                routing["routing_reason"] = (
                    routing.get("routing_reason", "") +
                    f" [K不适用:NOPAT={nopat_k:.2f}亿/市值={nopat_ratio*100:.2f}%<0.8%,DCF退化为终值PE赌注→回退{fallback}]"
                )
                routing["_k_blocked_by_code"] = True

        # ── 代码层硬校验: A模型要求正向盈利 ──
        # A(ROIC-RR DCF): mcap = IC × ROIC% × PE。当ROIC<0时NOPAT为负，PE失去经济含义。
        # 此时应强制走B(PS/revenue)，不依赖盈利假设。
        if routing.get("primary_model") == "A":
            core_a = data_package.get("packages", {}).get("core", {}).get("fields", {})
            roic_a = core_a.get("roic_pct", 0)
            nm_a = core_a.get("net_margin_pct", 0)
            if roic_a < 0 and nm_a < 0:
                anchor = (agent2a_output or {}).get("market_narrative", {}).get("primary_anchor", "earnings")
                # 深度亏损公司→PE模型不适用，强制revenue锚
                print(f"  [RouteJudge] A blocked: ROIC={roic_a}%<0 净利率={nm_a}%<0 → PE无经济含义, override to B", flush=True)
                routing["primary_model"] = "B"
                routing["model_category"] = "Revenue Multiples"
                routing["routing_reason"] = (
                    routing.get("routing_reason", "") +
                    f" [A不适用:ROIC={roic_a}%<0净利率={nm_a}%<0,PE无经济含义→回退B]"
                )
                routing["_a_blocked_by_code"] = True

        # ── 注入事件驱动分部(代码层透传,不为LLM输出的兜底) ──
        ed = (agent2a_output.get("forward_to_routing", {}) or {}).get("event_driven_segment")
        if ed and isinstance(ed, dict) and ed:
            routing["event_driven_segment"] = ed

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
            "event_driven_segment": (agent2a_output.get("forward_to_routing", {}) or {}).get("event_driven_segment", {}),
        }

def route_judge_v6(
    data_package: dict,
    agent2a_output: dict,
    event_data: dict | None = None,
) -> dict:
    """便捷入口：运行 V6 路由判决。"""
    judge = RouteJudgeV6()
    return judge.run(data_package, agent2a_output, event_data)
