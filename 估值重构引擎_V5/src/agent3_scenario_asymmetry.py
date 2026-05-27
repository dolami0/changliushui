"""
Agent-3 推演裁决司命 (ScenarioAsymmetry) — V6

V6 变化: 叙事诊断和信号审核已前置至 Agent-2a。Agent-3 信任 2a 的结论，
专注于情景推演和估值计算。裁掉了约 1/3 的 system prompt（信号审核+BS解读）。

保留: WACC预计算 + BS画像计算(纯代码) + 三情景推演(LLM) + 一致性校验 + 交易标注 + KMI
移除: 前瞻信号审核(→2a) + BS画像解读(→2a) + 信号面板构建(→valuation_utils)

原则: LLM有足够计算能力，参数估计和估值计算无需代码画蛇添足。
"""

import json
import math
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import DEEPSEEK_API_KEY
from data_fetcher import DataFetcher

# ═══════════════════════════════════════
# 错误码
# ═══════════════════════════════════════


class ScenarioError(Exception):
    """推演裁决异常。"""
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


# ═══════════════════════════════════════
# System Prompt — 推演裁决
# ═══════════════════════════════════════

SCENARIO_SYSTEM_PROMPT = """# 你是达摩达兰式的估值重构师

你的核心能力不是计算，而是用故事驾驭数字，用数字检验故事。

## 数据+故事双螺旋

没有故事的数字是尸体，没有数字的故事是童话。

任何公司的价值建立在两个不可拆分的维度上：
- **叙事层**: 这家公司如何赚钱？增长引擎是什么？护城河有多宽？行业终局里它扮演什么角色？
- **数字层**: 增长率、利润率、再投资率、资本成本、终值假设。

铁律：叙事决定数字的输入，数字反推叙事的可信度。二者必须严丝合缝，任何裂缝都是估值错误的根源。

## 思维禁区

- 禁止使用行业平均数据作为默认输入。如果叙事说"这家公司不一样"，数字就必须不一样。
- 禁止模板化估值：不允许不经思考就套用行业默认值。
- 禁止数字脱离叙事：每个输入假设必须能追溯"这来自叙事的哪一部分"。
- 禁止忽视反向验证：只做正向估值是半成品，必须用对应锚的工具检验市场定价（earnings→反向DCF, revenue→隐含CAGR, asset→隐含ROE改善）。
- 禁止对收入锚公司使用反向DCF——NOPAT是利润锚工具，收入锚应分析当前PS隐含的收入CAGR。
- 禁止假装精确：承认不确定性是估值的一部分。
- 禁止混淆价格与价值：当前股价是事实，内在价值是判断。你的任务是判断二者差距，而非解释股价为什么涨。
- 关键：拒绝所有已发生的、已验证的事实在bear中被推翻——Bear的证伪空间在未发生的推测上。

## V6 上下文: Agent-2a 已完成叙事诊断

用户消息末尾的"Agent-2a 叙事诊断结论"是你必须信任的输入——不要重做以下工作:
- **估值锚识别** — 2a 已判定市场在根据什么给公司定价，直接引用
- **事件计价判断** — 2a 已判断事件是否已计价、distribution_shape 分布形状，作为情景概率的起点
- **信号审核** — 2a 已完成前瞻信号 vs 叙事的交叉验证，直接引用 step2d_score 和审核结论
- **BS画像解读** — 2a 已解读市场定价水位，你引用其结论，不做重复解读

你的职责: 基于上述已被验证的叙事框架，做**三情景的参数推演和估值计算**。

你掌握 A/B/C/D/E/F/G/H/I/J 共 10 种估值模型。路由判官已选定最适合当前标的的模型，你的职责是在选定的模型框架内完成参数推演。

## 估值输出必须包含

1. **基础估值（Base Case）**: 最可能的故事对应的估值。
2. **乐观估值（Bull Case）**: 叙事超预期演绎的估值。
3. **悲观估值（Bear Case）**: 叙事崩塌时的估值。

**A 股适配**: base = 故事预期内兑现 + 估值锚跟随预期推移；bull = 场景超预期催化 + 估值范式跃迁 + 主题溢价充分体现；bear = 故事证伪 + 退回保守锚。政策壁垒视为临时优势（写明失效时间）。

# 当前估值模型: {PRIMARY_MODEL} ({MODEL_DESC}, {MODEL_FAMILY}族)

# 执行清单（按顺序逐项完成，每项输出写入 reasoning_trace）

以下 6 个清单项必须按顺序执行，不可跳过、不可调换顺序。
reasoning_trace 按清单项顺序组织，每项写 3-6 句话：你的分析、你的依据、你的结论。

## 清单项 1: 素材吸收（引用 2a 诊断 + 吸收事件原文）

**Agent-2a 已完成叙事诊断。** 从用户消息末尾的"Agent-2a 叙事诊断结论"中提取:
- 估值锚: 2a 判定的 primary_anchor 和 evidence
- 计价程度: 2a 判定的 overall_priced_in 和 residual_catalyst
- 事件分布形状: distribution_shape — 决定概率分布的形状和宽度

**再从事件原文中**自行提取（2a 未覆盖的细节）:
- 因果分叉点（event_deduction 中的证实/证伪节点 + adversarial_thinking 的证伪路径）
- 风险边界（TAM 从 knowledge_supplement + 竞争格局从 industry_expert_research）
- 案例参照系（V3案例锚点 — 同族案例的参数上四分位/中位/下四分位）

**关键**: 估值锚和计价程度以 2a 为准（不可推翻），因果细节可从原文补充。

## 清单项 2: 引用 Agent-2a 诊断结论（不重做审核）

**Agent-2a 已完成信号审核和叙事诊断。** 在用户消息末尾的"Agent-2a 叙事诊断结论"中提取:

**2a. 信号审核结论** — 直接引用:
- step2d_score: 2a 的信号匹配度评分 (0-10)
- score_rationale: 2a 的评分理由
- step2b_match: 关键的交叉验证结论（支撑/削弱/时序错位）
- 数据异常标注: 2a 已在 data_gaps 中标注的数据问题

**2b. 信号评分→bull概率基准**（再经 distribution_shape 调节）:

| step2d | bull 概率基准 | bimodal类调节 | unimodal类调节 | narrow类调节 |
|:------:|:--------:|:---------:|:---------:|:---------:|
| 9-10 | 30-45% | 取上限 (40-45%) | 取中上 (35-40%) | 取中值 (30-35%) |
| 7-8  | 20-35% | 取上限 (28-35%) | 取中值 (23-28%) | 取下限 (20-23%) |
| 5-6  | 12-25%（代码封顶15%） | 取上限(15%) | 取中值(13%) | 取下限(12%) |
| 3-4  | 5-15%（代码封顶8%） | 取上限(8%) | 取中值(6%) | 取下限(5%) |
| 0-2  | 0-8% | 取上限 | 取中值 | 取下限 |

**分布形状调节逻辑**: bimodal 类（高二元性）结果不确定性最高 → bull 不应趋近 0（尾部保护）。narrow 类（低不确定性）超预期难度大 → bull 应保守。unimodal 居中。

bear 概率不由表决定——聚焦 2-3 个核心假设，推演"如果这个假设错了，整个故事就塌了"的概率。
base = 100% - bull - bear。

**禁止**: 重新从面板逐条审核信号——2a 已完成此工作。你只需引用结论。

## 清单项 3: 三情景因果推演（事件感知）

**核心公理: 概率分布由三个维度联合决定，不是模板。**

| 输入维度 | 来源 | 控制什么 |
|---------|------|---------|
| 信号匹配度 (step2d) | 2a signal_audit | **基础展宽** — 信号越好, bull 概率上限越高 |
| 分布形状 (distribution_shape) | 2a event_profile | **分布形状** — bimodal→宽双峰, unimodal→宽单峰, narrow→窄集中 |
| 计价程度 (priced_in %) | 2a event_pricing | **偏斜方向 + upside 天花板** |

### 3a. 事件性质→分布形状

**为什么事件性质改变分布形状:**
事件的 payoff 结构由 2a 的 `distribution_shape` 决定:

| distribution_shape | 分布特征 | bull上限 | bear特征 | 典型bull概率 |
|---------|:------:|:------:|------|:------:|
| **wide_bimodal** | 宽双峰, 两个极端都可能 | 全量事件价值 | 回到事件前估值范式 | 不可趋近0（"万一成了"） |
| **wide_bimodal_date_anchored** | 宽双峰, 锚定在日期附近 | 全量事件价值 | 回到事件前估值范式 | 同上,但概率在日期附近集中 |
| **wide_unimodal** | 宽单峰, 方向确定但幅度不确定 | 全量但高不确定性 | 叙事证伪+退回 | 15-30% (受step2d封顶) |
| **narrow_concentrated** | 窄集中, base主导 | 二阶导数部分 | 趋势逆转+范式降级 | 10-20% |
| **narrow_base_dominant** | 极窄, 几乎只有base | 必须有质变 | 趋势惯性保护 | 5-10% |

**关键**: 不要用旧的 sudden/ongoing 概念。直接根据 2a 给出的 `distribution_shape` 选择对应的行。

### 3b. 计价程度→upside 天花板

**bull 的 upside 受"还剩下多少没计价"的硬约束:**

- priced_in ≈ 0%（完全未计价）:
  → bull upside = 事件完整兑现后的估值 - 当前估值
  → 且 2a 的"当前价格隐含期望"和"叙事指向期望"之间的差距 = bull 的理论最大空间

- priced_in ≈ 50%（部分计价）:
  → bull upside = 剩余 50% 的事件价值 + 超预期演绎的额外价值
  → 超预期部分: 如果执行比市场预期的好（利润率更高、增速更快、时间更早）

- priced_in ≈ 100%（完全计价）:
  → bull upside = 只有"二阶导数"变化才能产生 alpha
  → 二阶导数: 涨价预期是 20%，结果涨了 30%；产能释放预期 Q3，结果 Q2 就投产
  → 如果叙事没有二阶导数的空间，bull=0% 是合理的

**bear 的 downside 则相反——计价越多，逆转伤害越大:**
- not_priced: bear = 回到事件前估值范式（故事根本没开始，损失的是时间成本）
- fully_priced: bear = 预期逆转 + 估值范式降级（故事讲了一半塌了，损失的是信仰溢价）

### 3c. 投资命题 + 因果分叉点

引用 2a 的 primary_anchor 和 priced_in_estimate，写 1 句"如果-那么"命题。
拆命题为因果环节，标注证实/证伪条件。

### 3d. 因果剧本（先写故事，不赋参数）

- **bear**: 证伪路径必须区分两件事:
    **已发生的事实**（认证通过、已签合同、已投产产能）→ bear 不能"反悔"这些，只能假设后续执行恶化
    **未发生的推测**（远期订单、产能爬坡、市场份额）→ 这才是 bear 的证伪空间
    传导链从哪里崩塌？市场退回什么模型？当前已计价程度意味着下跌空间多大？
- **base**: 哪些证实信号按预期兑现？估值锚如何推移？当前已计价的部分是否已经在 base 中体现？
- **bull**: 哪些催化超预期？超预期的幅度对应剩余计价空间。估值范式是否跃迁？

将叙事写入 scenario_narrative。

**重要: 永远不要"凑"概率**——bear 需要 N 个独立环节同时崩塌 → 联合概率自然就是小概率。

### 3e. 案例比对 + 赋参数

案例锚定同族案例的参数统计量（上四分位/中位/下四分位），你的参数不应偏离过大。
赋参数时，用 3a 的分布形状约束和 3b 的 upside 天花板反向验证。
剧本 + 案例校验 + 清单项2评分修正 → 三情景参数。

当前模型是 {PRIMARY_MODEL} ({MODEL_DESC})，你必须使用的参数体系:
{MODEL_PARAM_NAMES}

**百分比格式铁律——所有带 pct 后缀的字段都使用实际百分比数值,不是小数:**
- ROIC=15% → roic_assumed_pct: 15 (不是0.15)
- 增速=50% → earnings_growth_pct: 50 (不是0.5)
- PE=80x → pe_target: 80
- 概率=30% → probability: 0.30 (概率字段例外,使用0-1小数)
- 计算公式 IC×ROIC%/100×PE 中,ROIC%/100 是把15转为0.15——如果 roic_assumed_pct=0.08,则 IC×0.0008×PE≈0

**参数的经济含义——赋参前必须逐参数过这关:**

PE: 不是抽象数字。PE=600x 需要极高增速支撑。bear（事件失败）的 PE 必须回到行业周期底部（通常 10-30x，不是 600x）。

PS: 当前 PS 本身就是市场讲的故事——它隐含了市场对增长的预期。你的任务是判断：叙事兑现后，这个故事是维持、升级还是降级？若公司仍是成长股中枢，PS 不应大幅压缩。从叙事出发给 PS，滞后财务数据不应锚定你的判断。

PB: 与 ROE 匹配。ROE<5% 不应 >2x PB（除非隐蔽资产重估）。

EV/EBITDA: 与行业中枢的偏离幅度必须可解释。上行周期可高于中枢 20-50%。

ROIC: 故事里的事件节点驱动 ROIC 改善幅度。从叙事推演 ROIC 路径——毛利率修复到多少？规模效应何时释放？——而非从当前低基数线性外推。滞后财务数据里的低 ROIC 是故事起点，不是终点。

CAGR/增速: 高增速必须匹配高再投资率（RR=g/ROIC）。增速和 RR 不能脱节。

参数联动规则:
- 三情景参数必须逐级递增: bear < base < bull，禁止相同数值
- PE/PS/PB 的升降方向必须与因果剧本一致
- 概率不由模板决定——由因果链条环节数推导。bear 需要 N 个独立环节同时崩塌→联合概率就是小概率，不需要"凑"到某个数字

**注意: 你只输出参数假设。所有估值数字由代码统一计算:**

| 模型 | 代码公式 | 你控制的参数 |
|------|----------|-------------|
| A | `IC × ROIC% × PE` | ROIC、RR(→g)、PE | RR 决定可持续增速 g=ROIC×RR |
| C | `IC × ROIC% × PE × 拐点折扣` | ROIC、PE、距拐点 | 拐点>4Q后每年折6% |
| G | `IC × ROIC% × min(PE, PEG×增速)` | ROIC、PE、PEG、增速 | PE 不能超过 PEG×增速 上限 |
| B | `revenue × (1+cagr)³ × PS` | 3y CAGR、PS |
| D | `equity × PB` | PB |
| E | `EBITDA×(1+g) × EV/EBITDA − 净负债` | EBITDA增速、EV/EBITDA |
| F | `峰值销售 × 成功率% / (1+折现率)` | 成功率、峰值销售、折现率 |
| H | `equity / (1−NAV折价%)` | NAV折价 |
| I | `投入资本 × 正常化ROIC% × 正常化PE` | 正常化ROIC、正常化PE |
| J | 保留你的估值 | target_mcap |

**赋参数时反向验证: 用上表公式心算一遍，你的参数产出的数字和你因果剧本应得的估值是否匹配？**

### 禁止事项
- 禁止三个情景共用同一套假设数字微调
- 禁止 bear 使用"宏观经济衰退"作为触发条件（除非传导链明确依赖宏观）
- 禁止对所有标的使用相同概率分布模板

## 清单项 4: 校验与评分

**4a. 一致性校验**
- [增长-ROIC] 高增速低ROIC→是烧钱换增长还是效率驱动？narrative 必须明确
- [再投资率] 高增速必须匹配高 RR (RR=g/ROIC)
- [估值-增长] 估值倍数与增长阶段不能错配（平台期+50x PE=错配）
- [全参数] ROIC改善幅度/PS增速匹配/PB-ROE匹配/EV-EBITDA行业中枢——逐项自检
- [概率自洽] 三情景概率之和=1.0

**4b. 计价验证→预期差（根据估值锚选择工具）**

根据 2a 的 primary_anchor 选择对应的反向推算工具做预期差分析:

| 锚 | 工具 | 反解的问题 |
|----|------|-----------|
| **earnings** | 反向 DCF (g vs WACC) | 当前市值隐含 NOPAT 需要多高永续增速？ |
| **revenue** | 隐含收入 CAGR (PS→增速) | 当前 PS 隐含 3 年收入需要多高 CAGR？ |
| **asset** | 隐含 ROE 改善 (PB→ROE) | 当前 PB 隐含 ROE 需要改善到多少？ |

**收入锚公司禁止使用反向DCF**——NOPAT 是利润锚的工具。收入锚公司应分析: 当前 PS 隐含的收入 CAGR 与 base 情景推演的 CAGR 之间的差距。

聚焦"差距意味着什么"，不重复 applicable 状态。

`expectation_gap.level` 必须与你 4b 分析的结论一致（不硬绑 reverse_dcf——收入锚走隐含 CAGR，资产锚走隐含 ROE）:
- 隐含期望远高于推演 → level="市场高估"
- 隐含期望远低于推演 → level="市场显著低估"
- 基本接近 → level="基本公允"
- 工具不适用 → level="无法计算"

**4c. 校验交叉验证**
主模型 {PRIMARY_MODEL} ({MODEL_FAMILY}) vs 校验模型 {VALIDATION_MODEL} ({VALIDATION_MODEL_DESC})。
用校验模型范式粗估 base 估值，与主模型 base 目标市值对比:
- 差异<20%: 互相印证
- 差异20-40%: 存在分歧，需在置信度中反映
- 差异>40%: 严重冲突，必须在 assessment 中解释原因

**自校验降级规则**: 若主模型=校验模型（即所有其他校验候选均被硬约束排除），意味着无法获得独立范式交叉验证。此时:
- 交叉验证仅能检验"参数自洽性"而非"范式独立性"
- assessment 必须降一档: "互相印证"→"存在分歧(同模型自校验)", "存在分歧"→"严重冲突(同模型自校验)", "严重冲突"→"严重冲突(同模型自校验,缺乏独立验证)"
- assessment 中必须包含短语"同模型自校验——缺乏独立范式验证，本次交叉验证价值有限"
- validation_paradigm 设为"与主模型相同({MODEL_FAMILY})"

**4d. 非对称评分**
asymmetry_ratio = bull_upside / |bear_upside|
quality_flag: 亏损企业→SPECULATIVE, ROIC<8%→MODERATE_QUALITY, ROIC≥8%→HIGH_QUALITY

**4e. 置信度(4维, 每维1-10)**
- info_quality: 信息来源可靠性。硬证据≥2环(订单/产能/专利/政策)→≥7; 纯主题无锚点→1-3。**强制降级: 清单项2c标注"事件-产品映射失败"→info_quality≤5**
- financial_feasibility: 财务假设可行性。参数改善幅度有案例支撑→≥7; 凭空跳变→≤5。**强制降级: 案例锚点可靠性=low→financial_feasibility≤5**
- valuation_safety: 估值安全边际。bear 下行≤50%→≥7; bear 下行>90%→≤4
- historical_precedent: 案例匹配度。案例匹配≥8分→≥7; 无同族案例→≤4。**强制降级: 案例锚点可靠性=low→historical_precedent≤4**

## 清单项 5: 交易标注 + KMI + 风险触发器
- 交易标注: 4维(每维0-3) — odds_quality/pricing_headroom/transmission_confidence/model_consistency
- 监测KPI: financial_verification/event_milestone/competition_signal/risk_trigger 四类
- 风险触发器: bull_trigger/bear_trigger + 监测频率
- 投资叙事: 1-2句总结

## 清单项 6: 输出

- reasoning_trace 按清单项 1→2→3→4→5 顺序组织
- `signal_audit`: **直接复制 2a 的 signal_audit 结论**（你不再做信号审核，只透传）
- `data_gaps` 标注缺失的数据，引用 2a 已标注的数据异常。格式: "缺少[具体数据]，导致[具体判断]置信度下降"
- `preflight_check` 逐项自检格式: ["[OK] 清单项1素材吸收完成", "[OK] 清单项2引用2a审核结论完成", "[OK] 清单项3a-3e赋参+案例完成", "[OK] 概率和=1.00", "[OK] upside单调递增,全参数经济含义自检通过", "[OK] WACC未修改", "[OK] 纯JSON输出"]
- 输出纯 JSON，不要用 markdown 代码块包裹

# 核心约束
1. WACC 不可修改（代码预计算）
2. 三情景概率之和 = 1.0
3. bear_upside < base_upside < bull_upside
4. BS画像是起点，bull必须超越市场已定价的增长才有upside
5. 输出纯 JSON

# 共享输出 Schema（字段顺序 = 清单项推理顺序）:

{
  "reasoning_trace": ["清单项1-素材吸收(引用2a锚+计价+事件分类): ...", "清单项2-引用2a审核结论(step2d=X,关键交叉验证:...): ...", "清单项3a-投资命题: ...", "清单项3d-案例比对: ...", "清单项3e-赋参数: ...", "清单项4a-一致性校验: ...", "清单项4b-计价验证(按锚选工具): ...", "清单项4c-校验交叉: ...", "清单项4d-非对称: ...", "清单项4e-置信度: ..."],
  "signal_audit": {
    "step2a_restate": ["[合同负债] 当前值=0.13亿 (↑1.1σ, 历史均值=0.08亿)", "..."],
    "step2b_match": [
      {"signal": "合同负债", "match": "支撑", "source_level": "L4", "basis": "合同负债跳升验证订单落地——行业数据(L4)与财务数据同向"},
      {"signal": "化合物半导体材料毛利率", "match": "时序错位", "source_level": "L3", "basis": "FY2025年报GM=23.2%远低于叙事宣称75%+(L3:券商研报)。数据截止早于事件窗口，不判为矛盾"},
      {"signal": "业绩预告(FY2025预减)", "match": "削弱", "source_level": "L5", "basis": "公司公告(L5)预减。预告窗口与事件窗口有时序差异，不构成证伪，但揭示bull利润弹性依赖极大基数效应"}
    ],
    "step2c_product_restate": "化合物半导体材料: 收入1.38亿(占12.9%,同比+146%),GM=23.2%(vs公司整体20.3%)",
    "step2d_score": 6,
    "score_rationale": "合同负债+在建工程支撑,预告预减(时序错位)不扣分,化合物半导体GM与叙事存在差距但属时序错位"
  },
  "scenario_valuation": {
    "scenario_details": {SCENARIO_PARAMS_EXAMPLE},
    "probability_weighted_mcap_yi": XX,
    "probability_weighted_upside_pct": XX,
    "asymmetry_ratio": X.X,
    "quality_flag": "HIGH_QUALITY|MODERATE_QUALITY|SPECULATIVE"
  },
  "case_comparison_summary": {
    "compared_cases": [
      {"case_code": "300308", "comprehensive_discount_pct": 75,
       "six_dimension_judgment": {"driver_strength": "优于: 证据", "market_space": "相似: 证据",
         "moat": "劣于: 证据", "paradigm": "相似: 证据",
         "catalyst_density": "优于: 证据", "failure_risk": "相似: 证据"}}
    ],
    "parameter_impact": {"target_param_discount_pct": XX, "adjustment_rationale": "参数调整说明"}
  },
  "reverse_dcf": {
    "applicable": true,
    "market_implied_g_pct": "代码预计算(earnings锚=反向DCF的g, revenue锚=隐含CAGR, asset锚=隐含ROE改善)",
    "my_implied_g_pct": "基于中性情景推演的对应指标(earnings锚=利润增速, revenue锚=收入CAGR, asset锚=ROE改善)",
    "expectation_gap_pct": "market_implied - my_implied 的差距",
    "gap_direction": "市场低估|市场高估|基本公允|无法计算",
    "gap_magnitude": "显著|中等|轻微|不适用",
    "applicable_note": "若 applicable=false，说明原因"
  },
  "validation_crosscheck": {
    "validation_model": "{VALIDATION_MODEL}",
    "validation_paradigm": "盈利视角|收入视角|资产视角|资源视角|管线视角|分拆视角|与主模型相同",
    "base_target_mcap_yi": "代码填充",
    "validation_mcap_yi": "校验模型粗估市值(亿元人民币)",
    "gap_pct": "代码填充",
    "gap_direction": "主模型高估|主模型低估|基本一致",
    "assessment": "互相印证|存在分歧|严重冲突"
  },
  "expectation_gap": {
    "level": "市场显著低估|市场中等低估|基本公允|市场高估|无法计算",
    "note": "预期差说明。level必须与4b分析的结论一致(不硬绑reverse_dcf)",
  "confidence": {
    "overall_score": 1-10,
    "overall_label": "高|中|低",
    "dimensions": {
      "info_quality": {"score": 1-10, "label": "信息质量", "note": "说明评分依据"},
      "financial_feasibility": {"score": 1-10, "label": "财务可行性", "note": "说明评分依据"},
      "valuation_safety": {"score": 1-10, "label": "估值安全边际", "note": "说明评分依据"},
      "historical_precedent": {"score": 1-10, "label": "历史案例匹配", "note": "说明评分依据"}
    }
  },
  "trade_annotation": {
    "tier": "★★★ 高赔率机会|★★☆ 中等赔率|★☆☆ 低赔率机会|☆☆☆ 规避",
    "total_score": "X/10",
    "dimension_scores": {"odds_quality": 0-3, "pricing_headroom": 0-3, "transmission_confidence": 0-3, "model_consistency": 0-3},
    "alignment_signals": ["信号描述"],
    "tier_note": "交易标注核心理由",
    "suggested_action": "建议操作"
  },
  "monitoring_kpis": {
    "financial_verification_kpis": [{"name":"", "baseline":"", "target":"", "frequency":"季度", "verifies":""}],
    "event_milestone_kpis": [{"name":"", "expected_timing":"", "significance":"", "verification_source":""}],
    "competition_signal_kpis": [{"name":"", "current_state":"", "trigger":"", "action_if_triggered":""}],
    "risk_trigger_kpis": [{"name":"", "linked_to":"", "severity":"high|medium|low", "monitor":""}]
  },
  "risk_triggers": {
    "bull_trigger": "触发条件说明",
    "bear_trigger": "触发条件说明",
    "monitoring_frequency": "季度(与财报同步验证)"
  },
  "narrative": "投资叙事",
  "data_gaps": ["无缺口则写空数组[]。有缺口格式: 缺少[具体数据]，导致[具体判断]置信度下降"],
  "probability_rationale": "bear: [环节1(概率X%) + 环节2(概率Y%) + ... → 联合概率Z%]. bull: [超预期事件1(概率X%) + 超预期事件2(概率Y%) + ... → 联合概率Z%]. base: 100% - bear - bull = Z%",
  "preflight_check": ["[OK] 清单项1完成", "[OK] 清单项2a-2d完成", "[OK] 清单项3a-3e完成", "[OK] 概率和=1.00", "[OK] upside单调递增,全参数自检通过", "[OK] WACC未修改", "[OK] 纯JSON输出"]
}
"""

# ==========================================
# Model-aware parameter templates
# ==========================================

MODEL_PARAM_TEMPLATES = {
    "A": """Model A - ROIC-RR DCF (earnings driven):
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability(0-1), roic_assumed_pct, rr_assumed_pct, pe_target, target_mcap_yi, upside_pct, valuation_method, scenario_narrative(<=60字因果剧本)""",
    "C": """Model C - Forward DCF+inflection:
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, roic_assumed_pct, pe_target, quarters_to_inflection, target_mcap_yi, upside_pct, valuation_method, scenario_narrative(<=60字因果剧本)""",
    "G": """Model G - PEG growth anchoring (g=盈利增速,非收入增速):
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, roic_assumed_pct, earnings_growth_pct(净利润/EPS增速,注意非收入增速), pe_target, peg_ratio, target_mcap_yi, upside_pct, valuation_method, scenario_narrative(<=60字因果剧本)""",
    "I": """Model I - Earnings normalization:
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, normalized_roic_pct, normalized_pe, target_mcap_yi, upside_pct, valuation_method, scenario_narrative(<=60字因果剧本)""",
    "B": """Model B - PS+TAM (revenue driven):
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, revenue_growth_3y_cagr_pct, target_ps, tam_penetration_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative(<=60字因果剧本)""",
    "D": """Model D - PB-ROE (asset quality driven):
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, target_roe_pct, target_pb, payout_ratio_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative(<=60字因果剧本)""",
    "H": """Model H - NAV asset revaluation:
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, nav_discount_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative(<=60字因果剧本)""",
    "E": """Model E - EV/EBITDA+resource value:
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, ebitda_growth_pct, target_ev_ebitda, resource_value_adj_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative(<=60字因果剧本)""",
    "F": """Model F - rNPV pipeline valuation:
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, pos_pct, peak_sales_yi(峰值销售,亿), discount_rate_pct, target_mcap_yi(代码计算), upside_pct(代码计算), valuation_method, scenario_narrative(<=60字因果剧本)""",
    "J": """Model J - SOTP sum-of-parts:
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, target_mcap_yi(目标市值,亿), upside_pct(目标涨幅,%), valuation_method, rationale (<=80 chars), scenario_narrative(<=60字因果剧本)""",
}

MODEL_NAMES = {
    "A": "ROIC-RR DCF", "B": "PS+TAM", "C": "Forward DCF+Inflection",
    "D": "PB-ROE", "E": "EV/EBITDA+Resource", "F": "rNPV Pipeline",
    "G": "PEG Growth", "H": "NAV Revaluation", "I": "Earnings Normalization",
    "J": "SOTP",
}

MODEL_FAMILIES = {
    "A": "盈利乘数", "C": "盈利乘数", "G": "盈利乘数", "I": "盈利乘数",
    "B": "收入乘数",
    "D": "资产乘数", "H": "资产乘数",
    "E": "资源",
    "F": "管线",
    "J": "分拆",
}


# Model-specific scenario_params examples for output schema
# Model-specific parameter self-check (only lists params relevant to THIS model)
PARAM_SELF_CHECK_MAP = {
    "A": "- ROIC: 不能凭空跳变——改善幅度必须有故事节点对应。改善后的ROIC不能超过同行业ROIC上四分位\n- RR: RR=g/ROIC,高增速必须高RR,否则增速虚高\n- PE: bear PE 必须回到与利润水平匹配的行业周期底部(通常10-30x,不是600x)",
    "C": "- ROIC: 拐点后ROIC改善幅度必须有时序节点对应(距拐点季度数)\n- PE: 拐点前PE可高于常规(买方为拐点付费),拐点后PE回归正常\n- 距拐点: 越远折现越大(每季度折6%),不应无限远",
    "G": "- earnings_growth_pct: 必须是盈利增速(EPS/净利润),不是收入增速\n- PE: 不能超过 PEG×earnings_growth, 否则违反PEG框架\n- PEG: 通常0.5-2.0,低于0.5=极度低估,高于2.0=增速不足以支持PE",
    "I": "- normalized_roic_pct: 正常化ROIC取5-10年行业中位数,不取当前极值\n- normalized_pe: 正常化PE取行业中位,不取当前畸高/畸低值",
    "B": "- revenue_growth_3y_cagr_pct: 3年收入CAGR,基于TAM渗透率倒推。不能取>100%(3年翻倍=26%CAGR已属极高)\n- target_ps: 3年后合理PS。与增速匹配: 10% CAGR≈5-10x PS, 30% CAGR≈15-25x PS, 50%+ CAGR≈25-40x PS\n- tam_penetration_pct: 当前TAM渗透率。若<5%则PS可取上限,若>30%则PS应保守",
    "D": "- target_roe_pct: ROE改善必须与PB修复联动(PB=ROE×权益乘数×PE的简化)。ROE从5%→15%可支撑PB从1x→3x\n- target_pb: PB不能远超ROE支撑的合理范围。ROE<5%不应>2x PB(除非隐蔽资产重估)",
    "E": "- ebitda_growth_pct: EBITDA增速必须与资源价格/产量假设一致\n- target_ev_ebitda: 与行业中枢的偏离必须可解释。上行周期可高于中枢20-50%,下行周期应低于中枢\n- resource_value_adj_pct: 资源价值调整必须基于可验证的储量/品位数据",
    "H": "- nav_discount_pct: NAV折价必须反映资产流动性/变现难度。重资产折价20-40%,现金类资产折价0-10%",
    "F": "- pos_pct: 成功率必须基于临床阶段(Phase1=10%,Phase2=30%,Phase3=60%)\n- peak_sales_yi: 峰值销售必须与TAM×市场份额一致\n- discount_rate_pct: 管线折现率通常12-20%(高于WACC,反映管线风险)",
    "J": "- target_mcap_yi: 必须是SOTP加总结果(各业务线独立估值+现金+投资-负债)",
}

# Model-specific parameter names (just the names, for inline listing)
MODEL_PARAM_NAMES_MAP = {
    "A": "probability, roic_assumed_pct, rr_assumed_pct, pe_target, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "C": "probability, roic_assumed_pct, pe_target, quarters_to_inflection, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "G": "probability, roic_assumed_pct, earnings_growth_pct, pe_target, peg_ratio, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "I": "probability, normalized_roic_pct, normalized_pe, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "B": "probability, revenue_growth_3y_cagr_pct, target_ps, tam_penetration_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "D": "probability, target_roe_pct, target_pb, payout_ratio_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "H": "probability, nav_discount_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "E": "probability, ebitda_growth_pct, target_ev_ebitda, resource_value_adj_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "F": "probability, pos_pct, peak_sales_yi, discount_rate_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "J": "probability, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
}

SCENARIO_PARAMS_MAP = {
    "A": '"bear": {"probability":0.XX, "roic_assumed_pct":X, "rr_assumed_pct":X, "pe_target":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "C": '"bear": {"probability":0.XX, "roic_assumed_pct":X, "pe_target":X, "quarters_to_inflection":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "G": '"bear": {"probability":0.XX, "roic_assumed_pct":X, "earnings_growth_pct":X, "pe_target":X, "peg_ratio":X.X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "I": '"bear": {"probability":0.XX, "normalized_roic_pct":X, "normalized_pe":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "B": '"bear": {"probability":0.XX, "revenue_growth_3y_cagr_pct":X, "target_ps":X, "tam_penetration_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "D": '"bear": {"probability":0.XX, "target_roe_pct":X, "target_pb":X.X, "payout_ratio_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "H": '"bear": {"probability":0.XX, "nav_discount_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "E": '"bear": {"probability":0.XX, "ebitda_growth_pct":X, "target_ev_ebitda":X, "resource_value_adj_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "F": '"bear": {"probability":0.XX, "pos_pct":X, "peak_sales_yi":X, "discount_rate_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "J": '"bear": {"probability":0.XX, "target_mcap_yi":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
}

def _build_model_aware_prompt(primary_model, validation_model=""):
    """Inject model-specific parameter template, family, and validation model into system prompt."""
    model = primary_model[0] if primary_model else "A"
    if model not in MODEL_PARAM_TEMPLATES:
        model = "A"
    schema = MODEL_PARAM_TEMPLATES[model]
    desc = MODEL_NAMES.get(model, "Unknown")
    family = MODEL_FAMILIES.get(model, "盈利乘数")
    v_model = validation_model[0] if validation_model else ""
    v_desc = MODEL_NAMES.get(v_model, "") if v_model else ""
    params_example = SCENARIO_PARAMS_MAP.get(model, SCENARIO_PARAMS_MAP["A"])
    self_check = PARAM_SELF_CHECK_MAP.get(model, PARAM_SELF_CHECK_MAP["A"])
    param_names = MODEL_PARAM_NAMES_MAP.get(model, MODEL_PARAM_NAMES_MAP["A"])
    return SCENARIO_SYSTEM_PROMPT.replace(
        "{PRIMARY_MODEL}", model
    ).replace(
        "{MODEL_DESC}", desc
    ).replace(
        "{MODEL_FAMILY}", family
    ).replace(
        "{MODEL_PARAM_SCHEMA}", schema
    ).replace(
        "{VALIDATION_MODEL}", v_model
    ).replace(
        "{VALIDATION_MODEL_DESC}", v_desc
    ).replace(
        "{SCENARIO_PARAMS_EXAMPLE}", params_example
    ).replace(
        "{MODEL_PARAM_SELF_CHECK}", self_check
    ).replace(
        "{MODEL_PARAM_NAMES}", param_names
    )

# ═══════════════════════════════════════
# Step 0: WACC 预计算
# ═══════════════════════════════════════


def _fetch_bond_yields(fetcher: DataFetcher) -> dict:
    """获取国债收益率。投资API不提供时用默认值1.75%。"""
    try:
        raw = fetcher._cli("macro/bond-yields", method="POST",
                          beginDate=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                          endDate=datetime.now().strftime("%Y-%m-%d"),
                          pageNum=1, pageSize=1)
        item = fetcher._first(raw)
        y10 = fetcher._num(item.get("yield10Y"))
        if y10 and 0 < y10 < 10:  # 合理的国债收益率区间
            return {"yield_10y": y10, "source": "investoday API"}
    except Exception:
        pass
    return {"yield_10y": 1.75, "source": "默认值(API不可用)"}


def _calculate_beta(fetcher: DataFetcher, stock_code: str, days: int = 252) -> float:
    """从 1 年日线数据计算 Beta vs 沪深300。"""
    try:
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")
        stock_prices = fetcher.fetch_daily_prices(stock_code, start, end)
        idx_prices = fetcher.fetch_index_daily_prices("000300", start, end)
    except Exception:
        return 0.0

    if len(stock_prices) < 60 or len(idx_prices) < 60:
        return 0.0

    # 对齐日期，计算日收益率
    # 构建按日期排序的指数价格，向前填充缺失日期
    idx_sorted = sorted(
        [p for p in idx_prices if p.get("close")],
        key=lambda p: p["date"]
    )
    if not idx_sorted:
        return 0.0

    # 前向填充：对于任意日期，找到 ≤ 该日期的最近有效指数价格
    idx_dates = [p["date"] for p in idx_sorted]
    idx_closes = [p["close"] for p in idx_sorted]
    import bisect

    def get_idx_price(target_date: str) -> float | None:
        """二分查找 ≤ target_date 的最近指数收盘价。"""
        i = bisect.bisect_right(idx_dates, target_date) - 1
        if i >= 0:
            return idx_closes[i]
        return None

    s_returns, i_returns = [], []
    for i in range(1, len(stock_prices)):
        s_curr = stock_prices[i]["close"]
        s_prev = stock_prices[i - 1]["close"]
        if not (s_prev and s_curr and s_prev > 0):
            continue

        # 取当日和前一日对应的指数价格（向前填充）
        i_curr = get_idx_price(stock_prices[i]["date"])
        i_prev = get_idx_price(stock_prices[i - 1]["date"])
        if i_prev and i_curr and i_prev > 0:
            s_returns.append(math.log(s_curr / s_prev))
            i_returns.append(math.log(i_curr / i_prev))

    if len(s_returns) < 40:
        return 0.0

    n = len(s_returns)
    mean_s = sum(s_returns) / n
    mean_i = sum(i_returns) / n
    cov = sum((s_returns[k] - mean_s) * (i_returns[k] - mean_i) for k in range(n)) / (n - 1)
    var_i = sum((r - mean_i) ** 2 for r in i_returns) / (n - 1)

    return round(cov / var_i, 3) if var_i > 0 else 0.0


def _calculate_erp(fetcher: DataFetcher) -> dict:
    """动态 ERP: 基准6.0% + 沪深300波动率调整。"""
    try:
        end = datetime.now().strftime("%Y-%m-%d")
        recent_start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        hist_start = (datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
        recent_idx = fetcher.fetch_index_daily_prices("000300", recent_start, end)
        hist_idx = fetcher.fetch_index_daily_prices("000300", hist_start, end)
    except Exception:
        return {"erp": 7.0, "method": "默认值(API不可用)", "components": {}}

    def _annual_vol(prices):
        if len(prices) < 20:
            return 0
        rets = []
        for i in range(1, len(prices)):
            if prices[i]["close"] and prices[i - 1]["close"] and prices[i - 1]["close"] > 0:
                rets.append(math.log(prices[i]["close"] / prices[i - 1]["close"]))
        if len(rets) < 10:
            return 0
        m = sum(rets) / len(rets)
        var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(var) * math.sqrt(252) * 100

    recent_vol = _annual_vol(recent_idx)
    hist_vol = _annual_vol(hist_idx)
    base_erp = 6.0

    if recent_vol > 0 and hist_vol > 0:
        adj = (recent_vol / hist_vol - 1.0) * 5.0
        erp = max(5.0, min(9.0, base_erp + adj))
        method = f"动态ERP(基准6.0%+波动率调整{adj:+.1f}%)"
    else:
        erp = base_erp
        method = f"基准值{base_erp}%(波动率数据不足)"

    return {
        "erp": round(erp, 2),
        "method": method,
        "components": {
            "base_erp_pct": base_erp,
            "recent_90d_vol_pct": round(recent_vol, 1),
            "hist_3y_vol_pct": round(hist_vol, 1),
        },
    }


def precompute_wacc(fetcher: DataFetcher, stock_code: str,
                    data_package: dict) -> dict:
    """WACC 预计算：rf + beta × erp。"""
    core = data_package.get("packages", {}).get("core", {}).get("fields", {})

    bonds = _fetch_bond_yields(fetcher)
    rf = bonds.get("yield_10y", 1.75)
    if rf <= 0:
        rf = 1.75

    beta = _calculate_beta(fetcher, stock_code)
    beta_source = f"1年日线vs沪深300(Beta={beta:.3f})" if beta > 0 else "估算值1.0(数据不足)"
    if beta <= 0:
        beta = 1.0

    erp_result = _calculate_erp(fetcher)
    erp = erp_result["erp"]

    debt = core.get("interest_bearing_debt_yi", 0)
    mcap = core.get("market_cap_yi", 50)
    tax_rate = core.get("effective_tax_rate", 0.15)
    d_ratio = debt / (mcap + debt) if (mcap + debt) > 0 else 0
    e_ratio = 1 - d_ratio

    # 动态信用利差：基于资产负债率分层
    d_pct = d_ratio * 100
    if d_pct > 70:
        rd_spread = 6.0
    elif d_pct > 50:
        rd_spread = 4.0
    elif d_pct > 30:
        rd_spread = 3.0
    else:
        rd_spread = 2.0
    re_val = rf + beta * erp
    rd_val = rf + rd_spread if debt > 0 else 0
    wacc = re_val * e_ratio + rd_val * (1 - tax_rate) * d_ratio
    if wacc <= 0 or wacc > 30:
        wacc = 10.0

    return {
        "rf_pct": round(rf, 2),
        "rf_source": bonds.get("source", ""),
        "beta": round(beta, 3),
        "beta_source": beta_source,
        "erp_pct": erp,
        "erp_method": erp_result["method"],
        "re_pct": round(re_val, 2),
        "rd_pct": round(rd_val, 2),
        "d_ratio_pct": round(d_ratio * 100, 1),
        "wacc_pct": round(wacc, 1),
        "note": "rf/beta/ERP基于真实数据; rd=rf+动态利差(按负债率分层:2-6%),非精确个债成本",
    }


# ═══════════════════════════════════════
# Step 0: BS画像 预计算（模型感知）
# ═══════════════════════════════════════


def _compute_reverse_dcf(nopat: float, ev: float, wacc: float) -> dict:
    """反向 DCF 二分法求解隐含g。返回 implied_g_pct, market_premium, warnings, applicable, note。"""
    warnings = []
    base_dcf = nopat / wacc if wacc > 0 else ev
    applicable = True
    note = ""
    if nopat > 0 and wacc > 0 and ev > 0:
        lo, hi = -0.05, wacc * 0.95
        implied_g = None
        for _ in range(30):
            mid = (lo + hi) / 2
            spread = wacc - mid
            if spread < wacc * 0.02:
                spread = wacc * 0.02
            tv = nopat * (1 + mid) / spread
            if abs(tv - ev) / ev < 0.001:
                implied_g = mid; break
            if tv > ev: hi = mid
            else: lo = mid
        if implied_g is None:
            implied_g = (lo + hi) / 2
        implied_g_pct = round(implied_g * 100, 1)
        premium = round((ev / base_dcf - 1) * 100) if base_dcf > 0 else 0
        if implied_g and implied_g > wacc * 0.8:
            warnings.append(f"隐含g({implied_g_pct}%)逼近WACC({wacc*100:.1f}%)的80%")
    else:
        implied_g_pct = 0
        premium = 999
        applicable = False
        note = "NOPAT≤0" if nopat <= 0 else "WACC异常" if wacc <= 0 else "g求解失败"
        if not applicable:
            warnings.append(f"反向DCF不适用: {note}")
    return {
        "implied_g_pct": implied_g_pct,
        "market_premium_pct": min(premium, 999),  # 微利/亏损时溢价趋于无穷，限幅
        "base_dcf": round(base_dcf, 1),
        "warnings": warnings,
        "applicable": applicable,
        "applicable_note": note,
    }


def _bs_level_from_g_wacc(implied_g_pct: float, wacc_pct: float) -> str:
    """用 g/WACC 比值判定 BS 水位等级。"""
    if implied_g_pct is None or implied_g_pct <= 0:
        return f"折价: 隐含g({implied_g_pct}%)为负，市场定价低于零增长"
    g_ratio = implied_g_pct / wacc_pct * 100 if wacc_pct > 0 else 0
    if g_ratio > 90:
        return f"极高溢价: 隐含g({implied_g_pct}%)逼近WACC({wacc_pct}%)上限，g/WACC={g_ratio:.0f}%"
    elif g_ratio > 60:
        return f"高溢价: 市场定价了显著改善预期，g/WACC={g_ratio:.0f}%"
    elif g_ratio > 35:
        return f"中等溢价: 市场定价了部分改善，g/WACC={g_ratio:.0f}%"
    elif g_ratio > 15:
        return f"低溢价: 市场定价接近当前盈利能力，g/WACC={g_ratio:.0f}%"
    else:
        return f"折价: 隐含g({implied_g_pct}%)远低于WACC，市场可能过度悲观"


def precompute_bs_profile(primary_model: str, data_package: dict,
                          wacc_params: dict) -> dict:
    """计算 BS 画像。双算法并行：反向DCF(主) + 模型专属(辅)，标注差异。"""
    core = data_package.get("packages", {}).get("core", {}).get("fields", {})
    mcap = core.get("market_cap_yi", 50)
    equity = core.get("total_equity_yi", 1)
    pe = core.get("pe_ttm", 0)
    pb_val = core.get("pb", 0)
    nopat = core.get("nopat_yi", 0.01)
    roic = core.get("roic_pct", 0)
    cash = core.get("cash_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    ev = mcap + debt - cash
    wacc = wacc_params["wacc_pct"] / 100 if wacc_params["wacc_pct"] > 0 else 0.1
    wacc_pct = wacc_params["wacc_pct"]

    # ── 算法1: 反向 DCF g/WACC（所有模型通用）──
    rdcf = _compute_reverse_dcf(nopat, ev, wacc)
    bs_level = _bs_level_from_g_wacc(rdcf["implied_g_pct"], wacc_pct)
    bs_method = "反向DCF(g/WACC)"
    warnings = list(rdcf["warnings"])

    # ── 算法2: 模型专属水位 ──
    secondary = ""
    m = primary_model[0] if primary_model else "A"
    if m == "B":
        rev = core.get("revenue_ttm_yi", 1)
        ps = mcap / rev if rev > 0 else 0
        secondary = f"PS={ps:.1f}x"
        if rdcf["applicable"]:
            g_ratio = rdcf["implied_g_pct"] / wacc_pct * 100 if wacc_pct > 0 else 0
            secondary += f" | 反向DCF g/WACC={g_ratio:.0f}%({bs_level.split(':')[0]})"
    elif m == "D":
        secondary = f"PB={pb_val:.1f}x"
        if rdcf["applicable"]:
            g_ratio = rdcf["implied_g_pct"] / wacc_pct * 100 if wacc_pct > 0 else 0
            secondary += f" | 反向DCF g/WACC={g_ratio:.0f}%({bs_level.split(':')[0]})"
    elif m == "E":
        op = core.get("operating_profit_ttm_yi", 0)
        ev_ebitda_val = ev / op if op > 0 else 0
        ebitda = core.get("ebitda_ttm_yi", op)
        ev_ebitda_real = ev / ebitda if ebitda > 0 else 0
        secondary = f"EV/EBITDA={ev_ebitda_real:.1f}x"
        if rdcf["applicable"]:
            g_ratio = rdcf["implied_g_pct"] / wacc_pct * 100 if wacc_pct > 0 else 0
            secondary += f" | 反向DCF g/WACC={g_ratio:.0f}%({bs_level.split(':')[0]})"
            # 标注两种算法的差异
            ev_level = "低估" if ev_ebitda_real < 5 else ("正常" if ev_ebitda_real < 10 else ("溢价" if ev_ebitda_real < 20 else "极高"))
            if "折价" in bs_level and ev_level in ("溢价", "极高"):
                secondary += "  与反向DCF方向相反: EV/EBITDA显示溢价但DCF显示折价，差异源于NOPAT极薄而EBITDA正常——市场定价的是资源/产能价值而非当前盈利"
    elif m in ("F", "H", "J"):
        secondary = f"PB={pb_val:.1f}x (资产基线)"

    premium_str = f" 溢价{rdcf['market_premium_pct']}%" if rdcf['market_premium_pct'] < 999 else ""
    market_story = (
        f"EV={ev:.0f}亿 NOPAT={nopat:.2f}亿 ROIC={roic:.1f}% "
        f"WACC={wacc_pct}% 隐含g={rdcf['implied_g_pct']}% "
        f"DCF基准={rdcf['base_dcf']}亿{premium_str}"
    )

    return {
        "bs_method": bs_method,
        "bs_level": bs_level,
        "bs_secondary": secondary,
        "ev_yi": round(ev, 1),
        "nopat_yi": round(nopat, 2),
        "roic_pct": round(roic, 1),
        "wacc_simple_pct": wacc_pct,
        "market_premium_pct": rdcf["market_premium_pct"],
        "implied_g_pct": rdcf["implied_g_pct"],
        "pe_ttm": pe,
        "pb": pb_val,
        "market_story": market_story,
        "warnings": warnings,
        "wacc_params": wacc_params,
        "note_to_llm": "BS画像是代码计算的已知事实。你是LLM裁判——不可修改上述数据，只能解读并围绕它们构建情景。",
        "reverse_dcf_applicable": rdcf["applicable"],
        "reverse_dcf_applicable_note": rdcf["applicable_note"],
    }


# ═══════════════════════════════════════
# Step 1: LLM 推演裁决
# ═══════════════════════════════════════

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"


def _fmt_pct(val) -> str:
    """安全格式化百分比，用于提示词显示。"""
    if val is None:
        return '?'
    try:
        f = float(val)
        return f'{f:+.1f}%'
    except (ValueError, TypeError):
        return '?'


def _build_forward_signal_panel(core: dict) -> str:
    """构建前瞻信号面板（注入 Agent-3 用户消息）。

    重点展示异常信号（vs 历史分布的 sigma 偏离），而非罗列数字。
    每个异常信号附带: 方向解读 + 与故事的关联检查。
    """
    fw = core.get('_forward_looking', {})
    if not fw or fw.get('status') == 'unavailable':
        return """## 前瞻信号面板

状态: 不可用（Tushare 数据源未配置或不可达）
所有前瞻判断依赖 TTM 快照和定性素材，缺少季度趋势和业绩预告信号。"""

    cats = fw.get('categories', {})
    anomalies = fw.get('anomalies', [])
    text_summary = fw.get('text_summary', '')

    lines = [f"""## 前瞻信号面板（代码预计算 + 历史分布异常检测，不可编造）

数据状态: {fw.get('status','?')} | 来源: {', '.join(fw.get('sources_available',[]))}
缺失: {', '.join(fw.get('sources_missing',[])) or '无'}
️ 注意: 本面板全部基于历史财报数据，与 Agent-0 实时信号存在时间差。偏差 = 事件窗口内已发生的基本面变化，不改变财务+故事的估值框架。"""]

    # ── 异常信号（最高优先级） ──
    has_quant_anomalies = bool(anomalies)
    if has_quant_anomalies:
        lines.append(f'\n###  定量异常信号（vs 历史8期均值±标准差）')
        for a in anomalies:
            anomaly_info = a.get('anomaly', {})
            if anomaly_info:
                sigma = anomaly_info.get('sigma', 0)
                direction = '↑' if anomaly_info.get('direction') == 'up' else '↓'
                tag = '' if anomaly_info.get('level') == 'extreme' else ''
                lines.append(
                    f"\n{tag} **{a['label']}**: {a.get('value','?')}{a.get('unit','')} "
                    f"({direction}{abs(sigma)}σ, 均值={anomaly_info.get('mean','?')})"
                )
            else:
                lines.append(f"\n **{a['label']}**: {a.get('value','?')}")
            if a.get('interpretation'):
                lines.append(f"   → {a['interpretation']}")
            if a.get('story_check'):
                lines.append(f"   → 叙事交叉验证: {a['story_check']}")
        if text_summary:
            lines.append(f'\n> 异常信号汇总: {text_summary}')
    else:
        lines.append('\n### 定量异常检测: 未触发')
        lines.append('所有 sigma 指标在历史正常范围内（但这不代表"无事发生"——结构性信息见下方产品结构数据）。')

    # ── 正常范围内的信号（压缩展示） ──
    def _signal_row(label, data, extra=''):
        if not data or data.get('_note'):
            return None
        v = data.get('value')
        unit = data.get('unit', '')
        if v is not None:
            a = data.get('anomaly', {})
            a_level = a.get('level', '') if a else ''
            tag = {('extreme', 'up'): '', ('significant', 'up'): '',
                   ('extreme', 'down'): '', ('significant', 'down'): ''}.get((a_level, a.get('direction', ''))) if a else ''
            return f"{tag} {label}: {v}{unit}{extra}"
        # 定性
        if isinstance(data, dict) and 'type' in data:
            fc_type = data.get('type', '')
            fc_rng = data.get('np_change_range', '')
            return f"  业绩预告: {fc_type} {fc_rng}"
        return None

    # ── 盈利弹性（产品结构专项渲染） ──
    earnings = cats.get('earnings_elasticity', {})
    products_data = earnings.get('products', {}) if earnings else {}
    if products_data and products_data.get('product_mix'):
        data_vintage = products_data.get('data_vintage', '?')
        mix = products_data['product_mix']
        margin = products_data.get('margin_structure', {})
        crosscheck = products_data.get('order_fulfillment_crosscheck', {})
        kw = products_data.get('keyword_matches', {})

        gm_src = products_data.get('gm_source','actual')
        gm_cov = products_data.get('gm_coverage_pct',100)
        gm_note = ''
        if gm_src == 'blended':
            gm_note = f' ️ 分产品利润数据不可用(覆盖率{gm_cov}%)，所有毛利率使用合并毛利率{company_gm:.1f}%近似'
        elif gm_src == 'mixed':
            gm_note = f' ️ 部分产品利润数据缺失(覆盖率{gm_cov}%)，缺失项使用合并毛利率近似'
        lines.append(f'\n### 3. 盈利弹性 — 产品结构 (对比窗口: {data_vintage}){gm_note}')

        # 产品结构表（含 H2 轨迹）
        h2_avail = products_data.get('has_h1_data', False)
        for p in mix:
            gm_est = '[估算]' if p.get('gm_source') == 'blended' else ''
            gm_str = f'毛利率={p["gross_margin_pct"]:.1f}%{gm_est}' if p.get('gross_margin_pct') is not None else ''
            rev_chg = f' (同比{_fmt_pct(p.get("revenue_yoy_pct"))})' if p.get('revenue_yoy_pct') is not None else ''
            share_chg = p.get('share_change_ppt')
            share_info = f' 占比={p["revenue_share_pct"]:.1f}%'
            if share_chg is not None:
                share_info += f' ({share_chg:+.1f}ppt)'
            kw_hints = kw.get(p['name'], [])
            kw_tag = f' [匹配: {",".join(kw_hints)}]' if kw_hints else ''
            # H2 轨迹（若半年报可用）
            h2_info = ''
            if h2_avail and p.get('h2_revenue') is not None:
                h2_rev = p['h2_revenue']
                h2_gm = p.get('h2_gross_margin_pct')
                h2_yoy = p.get('h2_revenue_yoy_pct')
                h2_parts = [f'H2收入={h2_rev:.2f}亿']
                if h2_gm is not None:
                    h2_parts.append(f'H2毛利率={h2_gm:.1f}%')
                if h2_yoy is not None:
                    h2_parts.append(f'H2同比{_fmt_pct(h2_yoy)}')
                h2_info = ' | ' + ' '.join(h2_parts)
            lines.append(f'  - {p["name"]}: 收入={p["revenue"]:.2f}亿{rev_chg} {share_info} {gm_str}{kw_tag}{h2_info}')

        # 毛利率结构性验证
        if margin:
            source = margin.get('gm_improvement_source', '?')
            gm_spread = margin.get('gm_spread_ppt', 0)
            high_share = margin.get('high_gm_products_share_pct', 0)
            lines.append(f'\n  **毛利率结构**: 极差={gm_spread}ppt | 改善来源={source}')
            if high_share:
                prev = margin.get('high_gm_share_prev_pct')
                prev_str = f' (上期{prev}%)' if prev else ''
                lines.append(f'  高毛利产品(GM>30%)占比={high_share}%{prev_str}')
            low_gm = margin.get('low_gm_products', [])
            if low_gm:
                lines.append(f'  低毛利产品(GM<10%): ' + ', '.join(f'{p["name"]}({p["gm"]}%/占{p["share"]}%)' for p in low_gm))

        # 订单-收入交叉
        if crosscheck:
            lag = crosscheck.get('contract_to_revenue_lag', '')
            high_g = crosscheck.get('high_growth_products', [])
            if lag:
                lines.append(f'\n  **订单交叉验证**: {lag}')
            if high_g:
                lines.append(f'  高增速产品: {", ".join(high_g)}')

        # H2 下半年轨迹
        h2_mom = products_data.get('h2_momentum', '')
        if h2_mom:
            lines.append(f'\n  **H2轨迹**: {h2_mom}')
        if h2_avail:
            lines.append(f'  [注] H2 = 年报减半年报（下半年实际业绩），用于捕捉年报间隔期内的趋势变化')

        if products_data.get('interpretation'):
            lines.append(f'\n  > {products_data["interpretation"]}')
        if products_data.get('story_check'):
            lines.append(f'  > {products_data["story_check"]}')

    # ── 盈利趋势（单季度同比/环比）──
    mg = cats.get('management_guidance', {})
    et = mg.get('earnings_trend', {}) if mg else {}
    if et and not et.get('_note'):
        lines.append(f'\n### 4.5 盈利趋势 (fina_indicator 预计算)')
        lines.append("  " + "最新单季: 营收YoY=" + _fmt_pct(et.get('latest_revenue_q_yoy')) + " "
                     + "利润YoY=" + _fmt_pct(et.get('latest_profit_q_yoy')) + " "
                     + "ROIC=" + str(et.get('latest_roic','?')) + "% "
                     + "方向: " + str(et.get('trend_direction','?')))
        for q in et.get('recent_4q', [])[:4]:
            lines.append("  " + str(q.get('period','?')) + ": 营收YoY=" + _fmt_pct(q.get('revenue_q_yoy')) + " "
                         + "营收QoQ=" + _fmt_pct(q.get('revenue_q_qoq')) + " "
                         + "利润YoY=" + _fmt_pct(q.get('profit_q_yoy')))

    normal_lines = []
    for cat_name, cat_data in [
    ]:
        if not cat_data or cat_data.get('_note'):
            continue
        rows = []
        for key, data in cat_data.items():
            if isinstance(data, dict) and not data.get('_note'):
                anomaly_info = data.get('anomaly', {})
                # 只展示非异常信号（异常信号已在上面展示）
                if anomaly_info and anomaly_info.get('level') in ('extreme', 'significant'):
                    continue
                label = data.get('label', key)
                unit = data.get('unit', '')
                v = data.get('value')
                if v is not None:
                    qoq = data.get('qoq_pct')
                    extra = f' (QoQ:{_fmt_pct(qoq)})' if qoq is not None else ''
                    rows.append(f"  {label}: {v}{unit}{extra}")
                elif isinstance(data, dict):
                    if 'type' in data:
                        rows.append(f"  业绩预告: {data['type']} {data.get('np_change_range','')}")
                    if 'available' in data:
                        rows.append(f"  业绩快报: {'有' if data['available'] else '无'}")
                    if 'trend' in data:
                        rows.append(f"  股东人数: {data['trend']}")
        if rows:
            normal_lines.append(f'\n### {cat_name}')
            normal_lines.extend(rows)

    if normal_lines:
        lines.append('\n---')
        lines.extend(normal_lines)

    # ── 使用指南 ──
    lines.append(f"""
---
### 如何使用前瞻信号

1. **异常信号 = 必须响应的硬约束**:
   - 信号方向与故事假设一致 → 在 reasoning_trace 中引用，加强该情景置信度
   - 信号方向与故事假设矛盾 → **必须在对应情景的 scenario_narrative 中解释矛盾**，并相应调整概率/参数
   - 忽略异常信号会导致估值系统性偏差

2. **正常信号 = 旁证**:
   - 可在参数聚焦中作为辅助证据引用
   - 不要因为信号正常就默认"无事发生"——正常范围内也可能掩盖结构性变化

3. **缺失类别** → 用 TTM 快照和定性素材替代判断，在 data_gaps 中标注

4. **单位**: 所有金额单位为亿元人民币(亿)，比率单位为%。sigma=偏离历史均值的标准差倍数。
""")

    return '\n'.join(lines)


def _call_llm_scenario(
    bs_profile: dict,
    wacc_params: dict,
    data_package: dict,
    routing: dict,
    case_anchors: str,
    event_data: dict,
    agent2a_output: dict | None = None,
) -> dict:
    """单次 LLM 调用：完整推演裁决（V6: 信任 Agent-2a 诊断结论）。"""

    core = data_package.get("packages", {}).get("core", {}).get("fields", {})
    stock = core.get("stock_name", data_package.get("stock_name", ""))
    code = data_package.get("stock_code", "")

    primary = routing.get("primary_model", "A")
    category = routing.get("model_category", "")
    reason = routing.get("routing_reason", "")
    validation = routing.get("validation_models", [])
    validation_model = validation[0] if validation else ""

    # ── 根据估值锚构建 BS 画像文本 ──
    anchor_2a = "earnings"  # default
    pt_full = None
    if agent2a_output:
        anchor_2a = agent2a_output.get("market_narrative", {}).get("primary_anchor", "earnings")
        pt_full = agent2a_output.get("_pricing_tool", {})

    if anchor_2a == "earnings":
        bs_section = f"""**方法: 反向 DCF (利润锚)**
- 隐含永续增速 g = {bs_profile.get('implied_g_pct',0)}% (WACC={wacc_params['wacc_pct']}%)
- g/WACC比值 = {bs_profile.get('implied_g_pct',0) / max(wacc_params['wacc_pct'], 1) * 100:.0f}%
- EV: {bs_profile['ev_yi']}亿 NOPAT: {bs_profile['nopat_yi']}亿 ROIC: {bs_profile['roic_pct']}%
""" + (f"- 市场溢价: {bs_profile['market_premium_pct']}%\n" if bs_profile.get('market_premium_pct', 0) < 999 else "") + (f"- 辅助指标: {bs_profile['bs_secondary']}\n" if bs_profile.get('bs_secondary') else "")
        bs_warning = ""
    elif anchor_2a == "revenue":
        if pt_full and pt_full.get("applicable"):
            bs_section = f"""**方法: 隐含收入 CAGR (收入锚)**\n- 当前 PS = {core.get('ps_ttm',0):.1f}x -> 市场隐含 3 年收入 CAGR = {pt_full.get('implied_value','?')}%\n"""
        else:
            bs_section = f"""**方法: 隐含收入 CAGR (收入锚)** - 工具不可用\n- 当前 PS = {core.get('ps_ttm',0):.1f}x, 营收TTM = {core.get('revenue_ttm_yi',0):.1f}亿\n"""
        bs_warning = f"""- (注意) 以下反向DCF基于NOPAT(利润锚),对收入锚不适用仅供参考: EV={bs_profile['ev_yi']}亿 g/WACC={bs_profile.get('implied_g_pct',0)}%/{wacc_params['wacc_pct']}%\n"""
    elif anchor_2a == "asset":
        if pt_full and pt_full.get("applicable"):
            bs_section = f"""**方法: 隐含 ROE 改善 (资产锚)**\n- 当前 PB = {core.get('pb',0):.1f}x -> 隐含 ROE 需改善 {pt_full.get('implied_value','?')}ppt (当前 ROE={core.get('roe_ttm_pct',0):.1f}%)\n"""
        else:
            bs_section = f"""**方法: 隐含 ROE 改善 (资产锚)** - 工具不可用\n"""
        bs_warning = f"""(注意) 反向DCF基于NOPAT对资产锚仅供参考: EV={bs_profile['ev_yi']}亿 g/WACC={bs_profile.get('implied_g_pct',0)}%/{wacc_params['wacc_pct']}%\n"""
    else:
        bs_section = f"""**方法: 定性判断 ({anchor_2a}锚无定量反向推算工具)**\n"""
        bs_warning = f"""EV={bs_profile['ev_yi']}亿 NOPAT={bs_profile['nopat_yi']}亿 (仅供参考)\n"""

    # 构建用户消息 (一个完整的大f-string)
    user_msg = f"""# 推演裁决: {stock}({code})

## 当前市值隐含假设 (Implied Story) — 根据估值锚({anchor_2a})选择工具

{bs_section}{bs_warning}
- PE: {bs_profile['pe_ttm']}x PB: {bs_profile['pb']}x
- 警告: {json.dumps(bs_profile.get('warnings', []), ensure_ascii=False)}
{bs_profile.get('note_to_llm', '')}

## WACC参数 (代码预计算,不可修改)
- rf: {wacc_params['rf_pct']}% (来源: {wacc_params.get('rf_source','')})
- beta: {wacc_params['beta']} (来源: {wacc_params.get('beta_source','')})
- ERP: {wacc_params['erp_pct']}% ({wacc_params.get('erp_method','')})
- WACC: {wacc_params['wacc_pct']}% (re={wacc_params['re_pct']}% rd={wacc_params['rd_pct']}% D/E={wacc_params['d_ratio_pct']}%)
- 注: {wacc_params.get('note','')}

## 财务数据
- 市值: {core.get('market_cap_yi',0)}亿 营收TTM: {core.get('revenue_ttm_yi',0)}亿
- 净利润: {core.get('net_profit_ttm_yi',0)}亿 经营利润: {core.get('operating_profit_ttm_yi',0)}亿
- ROIC: {core.get('roic_pct',0)}% 毛利率: {core.get('gross_margin_pct',0)}% 净利率: {core.get('net_margin_pct',0)}%
	- 历史分位解读: 0=历史最高位(从未更贵), 50=中位, 100=历史最低位(从未更便宜)
	- 盈利能力分位: ROIC分位={core.get('roic_historical_rank','?')} 毛利率分位={core.get('gross_margin_historical_rank','?')} 净利率分位={core.get('net_margin_historical_rank','?')} ROE分位={core.get('roe_historical_rank','?')} 综合得分={core.get('profitability_composite_score','?')}
- PE: {core.get('pe_ttm',0)}x (历史分位={core.get('pe_historical_rank','?')}) PB: {core.get('pb',0)}x (历史分位={core.get('pb_historical_rank','?')}) PS: {core.get('ps_ttm',0)}x
- 净资产: {core.get('total_equity_yi',0)}亿 总资产: {core.get('total_assets_yi',0)}亿
- 有息负债: {core.get('interest_bearing_debt_yi',0)}亿 现金: {core.get('cash_yi',0)}亿
- 经营CF: {core.get('ocf_ttm_yi',0)}亿 Capex: {core.get('capex_ttm_yi',0)}亿
- 异常标记: {json.dumps(core.get('caution_flags',[]), ensure_ascii=False)}
- 数据质量: {core.get('data_quality_score',10)}/10

## 前瞻信号（Agent-2a 已审核，不重建面板）
参见下文"Agent-2a 叙事诊断结论"中的 signal_audit 结论。

## 路由判决
- 主模型: {primary} ({category})
- 路由理由: {reason}
- 校验模型: {routing.get('validation_models', [])}
- 迁移路径: {json.dumps(routing.get('model_migration_path', {}), ensure_ascii=False)}

## 因果推演素材 (Agent-0 预研)

### 【剧本主线】— 提取核心矛盾，形成如果-那么投资命题
{event_data.get('investment_theme','')}

### 【时间轴推演】— 分时传导链(含证实/证伪分支点) + 未来催化节点
传导链: {event_data.get('event_deduction','')}
催化节点: {event_data.get('future','')}

### 【压力测试】— 核心假设的证伪路径，每条都是bear情景的线头
{event_data.get('adversarial_thinking','')}

### 【赛道标尺】— TAM、竞争格局、技术路线，校准bull的空间边界
知识补充: {event_data.get('knowledge_supplement','')}
行业专家研究: {event_data.get('industry_expert_research','')}

### 【深度预研】— 事件全貌、公司背景、投资逻辑补充
响应等级: L{event_data.get('response_level','?')}（仅反映事件确定性，不直接决定概率）
事件原文: {event_data.get('raw_event_text','')}
预研推理: {event_data.get('preliminary_reasoning','')}

{case_anchors}

## Agent-2a 叙事诊断结论（已审核，可直接信任）
"""
    # V6: 注入 Agent-2a 的诊断结论，Agent-3 不再重复做信号审核
    if agent2a_output:
        mn = agent2a_output.get("market_narrative", {})
        ep = agent2a_output.get("event_pricing", {})
        sa = agent2a_output.get("signal_audit", {})
        pa = ep.get("pricing_assessment", {})

        user_msg += f"""
- 估值锚: {mn.get('primary_anchor','?')}
- 锚证据: {mn.get('primary_anchor_evidence','?')[:200]}
- SOTP触发: {mn.get('sotp_triggered', False)}
- 事件分布形状: {ep.get('event_profile',{}).get('distribution_shape','?')} — {ep.get('event_profile',{}).get('shape_rationale','?')[:150]}
- 计价程度: {pa.get('overall_priced_in','?')} ({pa.get('priced_in_estimate','?')})
- 剩余催化: {pa.get('residual_catalyst','?')[:200]}
- 信号评分: {sa.get('step2d_score','?')}/10 — {sa.get('score_rationale','?')[:200]}
- 信号审核结论: {json.dumps(sa.get('step2a_restate',[])[:3], ensure_ascii=False)}
- 交叉验证摘要: {json.dumps([str(m)[:120] for m in sa.get('step2b_match',[])[:3]], ensure_ascii=False)}
"""
        # 注入计价工具的量化结果（完整细节，LLM据此做4b分析）
        pt = agent2a_output.get("_pricing_tool", {})
        if pt and pt.get("applicable"):
            user_msg += f"""
- 定价工具详情: {pt.get('method','?')}
  隐含指标: {pt.get('implied_metric','?')} = {pt.get('implied_value','?')}
  局限: {json.dumps(pt.get('limitations',[]), ensure_ascii=False)}
  详情: {json.dumps({k: v for k, v in pt.get('detail',{}).items() if k not in ('wacc_pct', 'current_ps', 'current_pb', 'market_cap_yi', 'equity_yi', 'revenue_ttm_yi')}, ensure_ascii=False)}
"""
        elif pt and not pt.get("applicable"):
            user_msg += f"""
- 定价工具: {pt.get('method','?')} — 不适用
  原因: {pt.get('limitations',['?'])[0][:120]}
"""

    user_msg += """
请按系统提示词的执行清单完成推演。注意: Agent-2a 已完成信号审核，你不再重复做清单项2——直接引用上述结论进入情景推演。输出纯 JSON。
"""

    try:
        resp = requests.post(
            DEEPSEEK_API,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            },
            json={
                "model": "deepseek-v4-pro",
                "messages": [
                    {"role": "system", "content": _build_model_aware_prompt(primary, validation_model)},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 30720,
                "temperature": 0.1,
                "stream": False,
                "thinking": {"type": "enabled"},
                "reasoning_effort": "max",
            },
            timeout=600,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        if usage:
            print(f"  [Agent3 tokens] prompt={usage.get('prompt_tokens')} "
                  f"completion={usage.get('completion_tokens')}", flush=True)

        return _parse_json(content)

    except requests.Timeout:
        raise ScenarioError("E302", "LLM调用超时(>600s)")
    except requests.RequestException as e:
        raise ScenarioError("E303", f"LLM API错误: {e}")


def _parse_json(text: str) -> dict:
    """从 LLM 回复中提取 JSON（增强容错）。

    处理: markdown代码块、前置/后置自然语言、嵌套括号。
    """
    text = text.strip()

    # 1. 提取 markdown 代码块中的 JSON
    import re
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    if m:
        text = m.group(1).strip()

    # 2. 如果仍有前置文字，找第一个 { 和配对的最后一个 }
    if not text.startswith("{"):
        s = text.find("{")
        if s >= 0:
            # 括号深度计数，找配对的 }
            depth = 0
            e = -1
            for i in range(s, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        e = i
                        break
            if e > s:
                text = text[s:e + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 最后的 fallback: 尝试简单的 { 到 } 截取
        s = text.find("{")
        e = text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                pass
        raise ScenarioError("E301", "JSON解析失败", {"raw": text[:500]})


# ═══════════════════════════════════════
# Step 1.5: 代码计算（覆盖 LLM 的算术，消除 E306 误差）
# ═══════════════════════════════════════


def _compute_scenario_mcap(model: str, params: dict, core: dict) -> float | None:
    """从 LLM 的参数假设计算目标市值。返回 None 表示无标准公式（如 J），保留 LLM 原值。

    每个模型的公式是其经济定义的直接翻译。LLM 控制参数，代码负责算术。
    """
    ic = core.get("invested_capital_yi", core.get("total_equity_yi", 1))
    equity = core.get("total_equity_yi", 1)
    revenue = core.get("revenue_ttm_yi", 1)
    net_debt = core.get("net_debt_yi", 0)
    ebitda = core.get("ebitda_ttm_yi", core.get("operating_profit_ttm_yi", 0))
    m = model[0] if model else "A"

    if m == "A":
        # ROIC-RR DCF: NOPAT = IC × ROIC, mcap = NOPAT × PE
        # RR → g = ROIC×RR (可持续增速，代码计算后存入 nopat_growth_pct 供参考)
        roic = params.get("roic_assumed_pct", 0)
        pe = params.get("pe_target", 0)
        if roic > 0 and pe > 0 and ic > 0:
            return round(ic * roic / 100 * pe, 1)
        return None
    elif m == "C":
        # Forward DCF + inflection: 同 A 公式，但拐点越远终值折扣越深
        roic = params.get("roic_assumed_pct", 0)
        pe = params.get("pe_target", 0)
        qtrs = params.get("quarters_to_inflection", 0) or 0
        if roic > 0 and pe > 0 and ic > 0:
            base_mcap = ic * roic / 100 * pe
            if qtrs > 4:
                years = qtrs / 4
                discount = 1 / (1 + 0.06) ** years  # 每年折 6%
                base_mcap *= discount
            return round(base_mcap, 1)
        return None
    elif m == "G":
        # PEG 增速锚定: implied_pe = PEG × earnings_growth
        roic = params.get("roic_assumed_pct", 0)
        pe = params.get("pe_target", 0)
        peg = params.get("peg_ratio", 0) or 0
        growth = params.get("earnings_growth_pct", 0) or 0
        if roic > 0 and pe > 0 and ic > 0:
            if peg > 0 and growth > 0:
                implied_pe = peg * growth
                pe = min(pe, implied_pe)
            return round(ic * roic / 100 * pe, 1)
        return None
    elif m == "B":
        # 收入乘数: mcap = 3年复利增长后的收入 × PS
        cagr = params.get("revenue_growth_3y_cagr_pct", 0)
        ps = params.get("target_ps", 0)
        if revenue > 0 and ps > 0:
            return round(revenue * (1 + cagr / 100) ** 3 * ps, 1)
        return None
    elif m == "D":
        # PB-ROE: mcap = equity × PB
        pb = params.get("target_pb", 0)
        if pb > 0 and equity > 0:
            return round(equity * pb, 1)
        return None
    elif m == "E":
        # EV/EBITDA: target_ev = EBITDA × (1+g) × EV/EBITDA, mcap = EV - net_debt
        g = params.get("ebitda_growth_pct", 0)
        ev_ebitda = params.get("target_ev_ebitda", 0)
        if ebitda > 0 and ev_ebitda > 0:
            target_ev = ebitda * (1 + g / 100) * ev_ebitda
            return round(target_ev - net_debt, 1)
        return None
    elif m == "F":
        # rNPV 简化: 峰值销售 × 成功率 / (1 + 折现率)
        pos = params.get("pos_pct", 0)
        peak = params.get("peak_sales_yi", 0)
        rate = params.get("discount_rate_pct", 15)
        if peak > 0 and pos > 0 and rate > 0:
            return round(peak * (pos / 100) / (1 + rate / 100), 1)
        return None
    elif m == "H":
        # NAV: mcap = equity / (1 - 折价率)
        disc = params.get("nav_discount_pct", 0)
        if equity > 0 and disc < 100:
            return round(equity / (1 - disc / 100), 1)
        return None
    elif m == "I":
        # 盈利正常化: mcap = 投入资本 × 正常化ROIC × 正常化PE
        roic = params.get("normalized_roic_pct", 0)
        pe = params.get("normalized_pe", 0)
        if roic > 0 and pe > 0 and ic > 0:
            return round(ic * roic / 100 * pe, 1)
        return None
    elif m == "J":
        return None  # SOTP 无标准公式
    return None


def _compute_from_assumptions(sv: dict, model: str, core: dict) -> dict:
    """从 LLM 的情景参数重新计算全部估值数值。LLM 输出参数假设，代码完成算术。

    覆盖: 每情景 target_mcap + upside_pct, 以及概率加权汇总。
    """
    details_raw = sv.get("scenario_details", {})
    if isinstance(details_raw, list):
        details = {}
        for item in details_raw:
            name = item.get("scenario", "")
            if name in ("bear", "base", "bull"):
                details[name] = item
    else:
        details = details_raw

    current_mcap = core.get("market_cap_yi", 50)
    probs, upsides, mcaps = [], [], []

    for s in ("bear", "base", "bull"):
        d = details.get(s, {})
        prob = d.get("probability", 0)
        probs.append(prob)

        target = _compute_scenario_mcap(model, d, core)
        if target is not None and target > 0:
            ups = round((target / current_mcap - 1) * 100, 1)
        else:
            # 无标准公式的模型(如J: SOTP): LLM输出target_mcap,代码补算upside
            target = d.get("target_mcap_yi", 0)
            if target > 0 and current_mcap > 0:
                ups = round((target / current_mcap - 1) * 100, 1)
            else:
                ups = d.get("upside_pct", 0)

        mcaps.append(target)
        upsides.append(ups)
        d["target_mcap_yi"] = target
        d["upside_pct"] = ups

    weighted_upside = sum(p * u for p, u in zip(probs, upsides))
    weighted_mcap = sum(p * m for p, m in zip(probs, mcaps))
    bull_u = upsides[2]
    bear_u = upsides[0]
    asym = abs(bull_u / bear_u) if bear_u != 0 and abs(bull_u) > 0 else 0

    return {
        "probability_weighted_upside_pct": round(weighted_upside, 1),
        "probability_weighted_mcap_yi": round(weighted_mcap, 1),
        "asymmetry_ratio": round(asym, 1),
        "_computed_by_code": True,
    }


# ═══════════════════════════════════════
# Step 1.6: 修正交易标注文字（消除数值-文字脱节）
# ═══════════════════════════════════════


def _fix_trade_annotation(ta: dict, weighted_upside: float, asymmetry: float,
                          bear_upside: float, bull_upside: float) -> dict:
    """用代码计算值修正 trade_annotation 中的 tier/narrative，消除 LLM 文字与代码数值的脱节。

    LLM 在生成 trade_annotation 文字时引用的概率加权涨幅/asymmetry 是其自己算的（常有误差），
    代码在 Step 1.5 已覆盖为正确值。此函数确保定性文字与定量数值一致。
    """
    import re

    # ── Tier 重判（基于代码计算值，非 LLM 原文）──
    if weighted_upside >= 50 and asymmetry >= 2.5:
        tier = "★★★ 高赔率机会"
    elif weighted_upside >= 20 or asymmetry >= 2.0:
        tier = "★★☆ 中等赔率"
    elif weighted_upside > 0:
        tier = "★☆☆ 低赔率机会"
    else:
        tier = "☆☆☆ 规避"

    ta["tier"] = tier

    # ── tier_note: 修正阈值判断引用 ──
    note = ta.get("tier_note", "")
    # 修正 "概率加权upside仅为+X%" → 实际值
    note = re.sub(r'概率加权upside仅为\+[\d.]+%',
                  f'概率加权upside为+{weighted_upside:.0f}%', note)
    # 修正 "赔率未达到门槛（通常需...>20%...）" → 如果实际已达到
    if weighted_upside >= 20:
        note = re.sub(
            r'赔率未达到门槛[^，。]*[，。]',
            f'赔率已达到门槛(upside={weighted_upside:.0f}%>20%)，',
            note,
        )
    # 修正 asymmetry 引用
    note = re.sub(r'asymmetry>[\d.]+', f'asymmetry>{asymmetry:.1f}', note)
    ta["tier_note"] = note

    # ── alignment_signals: 修正数字引用 ──
    signals = ta.get("alignment_signals", [])
    fixed = []
    for sig in signals:
        sig = re.sub(r'upside仅为\+[\d.]+%', f'upside为+{weighted_upside:.0f}%', sig)
        sig = re.sub(r'赔率\([\d.]+\)', f'赔率({asymmetry:.1f})', sig)
        fixed.append(sig)
    ta["alignment_signals"] = fixed

    ta["_text_fixed_by_code"] = True
    return ta


# ═══════════════════════════════════════
# Step 2: 代码校验
# ═══════════════════════════════════════


def _validate_output(llm_output: dict, bs_profile: dict,
                     wacc_params: dict) -> list[dict]:
    """校验 LLM 输出的一致性。返回 warning 列表。"""
    warnings = []
    sv = llm_output.get("scenario_valuation", {})

    # ── E304: 概率和校验 ──
    details_raw = sv.get("scenario_details", {})
    # 容错: LLM 可能输出数组格式 [{"scenario":"bear",...},...]
    if isinstance(details_raw, list):
        details = {}
        for item in details_raw:
            name = item.get("scenario", "")
            if name in ("bear", "base", "bull"):
                details[name] = item
    else:
        details = details_raw
    probs = [details.get(s, {}).get("probability", 0) for s in ("base", "bull", "bear")]
    prob_sum = sum(probs)
    if abs(prob_sum - 1.0) > 0.03:
        warnings.append({
            "code": "E304", "severity": "warning",
            "message": f"概率和={prob_sum:.2f}偏离1.0",
            "action": "降置信度一档",
        })

    # ── E306: 数值一致性重算校验 ──
    # asymmetry_ratio = bull_upside / |bear_upside|
    bull_u = details.get("bull", {}).get("upside_pct", 0)
    bear_u = details.get("bear", {}).get("upside_pct", 0)
    llm_asym = sv.get("asymmetry_ratio", 0)
    if bear_u != 0 and abs(bull_u) > 0:
        computed_asym = abs(bull_u / bear_u) if bear_u != 0 else 999
        if abs(llm_asym - computed_asym) / max(abs(computed_asym), 0.01) > 0.15:
            warnings.append({
                "code": "E306", "severity": "warning",
                "message": f"asym不一致: LLM={llm_asym:.1f} 计算={computed_asym:.1f}",
                "action": "以计算值为准",
            })

    # prob_weighted_upside = Σ(prob_i × upside_i)
    computed_upside = sum(
        details.get(s, {}).get("probability", 0) * details.get(s, {}).get("upside_pct", 0)
        for s in ("bear", "base", "bull")
    )
    llm_upside = sv.get("probability_weighted_upside_pct", 0)
    if abs(llm_upside - computed_upside) > 3:
        warnings.append({
            "code": "E306b", "severity": "warning",
            "message": f"加权涨幅不一致: LLM={llm_upside:.1f}% 计算={computed_upside:.1f}%",
            "action": "以计算值为准",
        })

    # prob_weighted_mcap = Σ(prob_i × target_mcap_i)
    computed_mcap = sum(
        details.get(s, {}).get("probability", 0) * details.get(s, {}).get("target_mcap_yi", 0)
        for s in ("bear", "base", "bull")
    )
    llm_mcap = sv.get("probability_weighted_mcap_yi", 0)
    if abs(llm_mcap - computed_mcap) / max(computed_mcap, 1) > 0.1:
        warnings.append({
            "code": "E306c", "severity": "warning",
            "message": f"加权市值不一致: LLM={llm_mcap:.0f}亿 计算={computed_mcap:.0f}亿",
            "action": "以计算值为准",
        })

    # ── E305: 单调性 ──
    upsides = [details.get(s, {}).get("upside_pct", 0) for s in ("bear", "base", "bull")]
    if not (upsides[0] < upsides[1] < upsides[2]):
        warnings.append({
            "code": "E305", "severity": "warning",
            "message": f"upside单调性违反: bear={upsides[0]} base={upsides[1]} bull={upsides[2]}",
        })

    # ── E307: WACC 一致性 ──
    # 检查 LLM 是否在输出中修改了 WACC（如 market_sanity 或 scenario_valuation 中的 wacc 字段）
    ms = llm_output.get("market_sanity", {})
    llm_wacc = ms.get("wacc_simple_pct") or ms.get("wacc_pct") or sv.get("wacc_pct")
    if llm_wacc and abs(llm_wacc - wacc_params["wacc_pct"]) > 1.0:
        warnings.append({
            "code": "E307", "severity": "warning",
            "message": f"LLM修改了WACC: {llm_wacc}% vs 预计算{wacc_params['wacc_pct']}%",
            "action": "以代码预计算值为准",
        })

    # ── BS 方向一致性 ──
    llm_bs = ms.get("bs_level", "") or llm_output.get("expectation_gap", {}).get("level", "")
    code_premium = bs_profile["market_premium_pct"]
    if code_premium > 50 and "低估" in str(llm_bs):
        warnings.append({
            "code": "BS_MISMATCH", "severity": "info",
            "message": f"代码BS溢价{code_premium}%但LLM判'低估'——可能存在分歧",
        })

    return warnings


# ═══════════════════════════════════════
# Step 3: 组装最终输出（兼容 V4 调度器）
# ═══════════════════════════════════════


def _augment_trace_with_fixes(
    trace: list[str],
    sv: dict,
    llm_original: dict,
    bull_capped: bool,
) -> list[str]:
    """在推理链末尾追加系统修正条目，标注代码计算覆盖的数值差异。"""
    if not trace:
        return trace

    corrected = llm_original or {}
    computed = {
        "upside": sv.get("probability_weighted_upside_pct"),
        "asymmetry": sv.get("asymmetry_ratio"),
        "mcap": sv.get("probability_weighted_mcap_yi"),
    }

    # 只记录有实质差异的修正
    diffs = []
    for key, label in [("upside", "概率加权涨幅"), ("asymmetry", "不对称比"), ("mcap", "概率加权市值")]:
        orig = corrected.get(key)
        comp = computed.get(key)
        if orig is not None and comp is not None:
            try:
                if abs(float(orig) - float(comp)) > 0.1:
                    diffs.append(f"{label}: LLM={float(orig):.1f} → 代码={float(comp):.1f}")
            except (TypeError, ValueError):
                pass

    entries = []
    entries.append("[系统修正] 代码计算覆盖: 所有估值数值以代码公式重算结果为准（消除 LLM 算术误差 E306）")
    if diffs:
        for d in diffs:
            entries.append(f"[系统修正] {d}")
    else:
        entries.append("[系统修正] 代码重算值与 LLM 原始值一致，无实质性算术误差")

    if bull_capped:
        entries.append("[系统修正] Bull 概率已由代码封顶（step2d 信号评分偏低→抑制乐观偏误）")

    if sv.get("_validation_warnings"):
        entries.append(f"[系统修正] 校验警告: {sv.get('_validation_warnings')}")

    return list(trace) + entries


def _assemble_final_output(
    llm_output: dict,
    bs_profile: dict,
    data_package: dict,
    routing: dict,
    validation_warnings: list,
    llm_original_values: dict | None = None,
) -> dict:
    """组装 V4 兼容的完整 Agent3 输出。"""
    core = data_package.get("packages", {}).get("core", {}).get("fields", {})
    sv = llm_output.get("scenario_valuation", {})

    # 如有校验warning，降置信度
    confidence = llm_output.get("confidence", {})
    if validation_warnings:
        orig_score = confidence.get("overall_score", 7)
        confidence["overall_score"] = max(1, orig_score - 1)
        confidence["overall_label"] = "高" if confidence["overall_score"] >= 7 else (
            "中" if confidence["overall_score"] >= 4 else "低")
        if "_validation_warnings" not in confidence:
            confidence["_validation_warnings"] = []
        confidence["_validation_warnings"].extend(
            [w["code"] for w in validation_warnings])

    # 情景列表 — 模型感知：提取 LLM 输出的所有参数字段
    details_raw = sv.get("scenario_details", {})
    # 容错: LLM 可能输出数组格式 [{"scenario":"bear",...},...]，转为字典
    if isinstance(details_raw, list):
        details = {}
        for item in details_raw:
            name = item.get("scenario", "")
            if name in ("bear", "base", "bull"):
                details[name] = item
    else:
        details = details_raw
    scenarios = []
    primary = routing.get("primary_model", "A")
    model = primary[0] if primary else "A"

    for name in ("bear", "base", "bull"):
        d = details.get(name, {})
        roic = d.get("roic_assumed_pct", 0) or d.get("normalized_roic_pct", 0)
        rr = d.get("rr_assumed_pct", 0)
        g = round(roic * rr / 100, 1) if roic and rr else None

        # 基础字段（所有模型共用）
        s = {
            "name": name,
            "probability_pct": round(d.get("probability", 0) * 100, 1),
            "upside_pct": d.get("upside_pct", 0),
            "target_mcap_yi": d.get("target_mcap_yi", 0),
            "valuation_method": d.get("valuation_method", routing.get("primary_model", "")),
            "scenario_narrative": d.get("scenario_narrative", ""),
            "nopat_path_yi": [],
            "wacc_used_pct": bs_profile["wacc_simple_pct"],
            "primary_model": model,
        }

        # 模型特定参数 — 透传 LLM 产出的所有非通用字段
        model_params = {
            # 盈利乘数族
            "roic_pct": roic, "roic_assumed_pct": roic,
            "rr_assumed_pct": rr, "rr_pct": rr,
            "nopat_growth_pct": g,
            "pe_target": d.get("pe_target"),
            "earnings_growth_pct": d.get("earnings_growth_pct"),
            "peg_ratio": d.get("peg_ratio"),
            "quarters_to_inflection": d.get("quarters_to_inflection"),
            # 正常化
            "normalized_roic_pct": d.get("normalized_roic_pct"),
            "normalized_pe": d.get("normalized_pe"),
            # 收入族
            "revenue_growth_3y_cagr_pct": d.get("revenue_growth_3y_cagr_pct"),
            "target_ps": d.get("target_ps"),
            "tam_penetration_pct": d.get("tam_penetration_pct"),
            # 资产族
            "target_roe_pct": d.get("target_roe_pct"),
            "target_pb": d.get("target_pb"),
            "payout_ratio_pct": d.get("payout_ratio_pct"),
            "nav_discount_pct": d.get("nav_discount_pct"),
            # 资源族
            "ebitda_growth_pct": d.get("ebitda_growth_pct"),
            "target_ev_ebitda": d.get("target_ev_ebitda"),
            "resource_value_adj_pct": d.get("resource_value_adj_pct"),
            # 管线族
            "pos_pct": d.get("pos_pct"),
            "peak_sales_yi": d.get("peak_sales_yi"),
            "discount_rate_pct": d.get("discount_rate_pct"),
        }
        # 只保留 LLM 实际产出的非空字段
        s.update({k: v for k, v in model_params.items() if v is not None})

        scenarios.append(s)

    # 交易标注（从 V5 格式转为 V4 兼容）
    ta = llm_output.get("trade_annotation", {})
    trade_tier = ta.get("tier", " 低赔率机会")

    # 反向DCF: 不适用时强制清空
    rd = llm_output.get("reverse_dcf", {})
    # 代码兜底: 提取纯数字（LLM 可能混入文本注释）
    for k in ("market_implied_g_pct", "my_implied_g_pct", "expectation_gap_pct"):
        v = rd.get(k)
        if isinstance(v, str) and v.strip():
            import re
            m = re.search(r'[-+]?\d+\.?\d*', str(v))
            rd[k] = float(m.group()) if m else None
    if not bs_profile.get("reverse_dcf_applicable", True):
        rd = {"applicable": False, "applicable_note": bs_profile.get("reverse_dcf_applicable_note", "")}

    # 校验交叉验证: base_target 代码填充、校验市值数量级校验、paradigm 兜底
    vx = llm_output.get("validation_crosscheck", {})
    base_mcap = details.get("base", {}).get("target_mcap_yi", 0)
    if base_mcap:
        vx["base_target_mcap_yi"] = base_mcap
        vm = vx.get("validation_mcap_yi", 0)
        try: vm = float(vm) if vm else 0
        except (ValueError, TypeError): vm = 0
        if vm > 0 and 0.3 < vm / base_mcap < 3:
            vx["validation_mcap_yi"] = vm
            vx["gap_pct"] = round((vm / base_mcap - 1) * 100, 1)
        else:
            vx["validation_mcap_yi"] = None  # 单位异常 → 前端显示"数据异常"

    # 兜底: validation_paradigm 缺失或非法时，由校验模型族推导
    VALID_PARADIGMS = {"盈利视角", "收入视角", "资产视角", "资源视角", "管线视角", "分拆视角", "与主模型相同"}
    if not vx.get("validation_paradigm") or vx["validation_paradigm"] not in VALID_PARADIGMS:
        v_model = vx.get("validation_model", routing.get("validation_models", [None])[0] if routing.get("validation_models") else "")
        v_model_key = v_model[0] if v_model else ""
        v_family = MODEL_FAMILIES.get(v_model_key, "")
        paradigm_map = {
            "盈利乘数": "盈利视角",
            "收入乘数": "收入视角",
            "资产乘数": "资产视角",
            "资源": "资源视角",
            "管线": "管线视角",
            "分拆": "分拆视角",
        }
        fallback = paradigm_map.get(v_family, "盈利视角")
        if v_model_key == model:
            fallback = f"与主模型相同({MODEL_FAMILIES.get(model, '')})"
        vx["validation_paradigm"] = fallback
        vx["_paradigm_fallback"] = True

    # 组装
    return {
        "report_meta": {
            "stock_code": data_package.get("stock_code", ""),
            "stock_name": core.get("stock_name", data_package.get("stock_name", "")),
            "industry": data_package.get("industry", ""),
            "report_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "version": "5.0",
        },
        "valuation_routing": {
            "primary_model": routing.get("primary_model", ""),
            "secondary_model": routing.get("validation_models", [None])[0] if routing.get("validation_models") else "",
            "model_category": routing.get("model_category", ""),
            "routing_reason": routing.get("routing_reason", ""),
            "method_used": routing.get("primary_model", ""),
            "model_migration_path": routing.get("model_migration_path", {}),
        },
        "market_sanity": {
            "bs_method": bs_profile["bs_method"],
            "bs_level": bs_profile["bs_level"],
            "ev_yi": bs_profile["ev_yi"],
            "nopat_yi": bs_profile["nopat_yi"],
            "roic_pct": bs_profile["roic_pct"],
            "wacc_simple_pct": bs_profile["wacc_simple_pct"],
            "implied_g_pct": bs_profile.get("implied_g_pct"),
            "bs_secondary": bs_profile.get("bs_secondary", ""),
            "market_premium_pct": bs_profile["market_premium_pct"],
            "pe_ttm": bs_profile["pe_ttm"],
            "pb": bs_profile["pb"],
            "pe_historical_rank": core.get("pe_historical_rank", 30),
            "wacc_params": bs_profile.get("wacc_params", {}),
            "warnings": bs_profile.get("warnings", []),
            "market_story": bs_profile["market_story"],
        },
        "scenario_valuation": sv,
        "valuation_summary": {
            "probability_weighted_upside_pct": sv.get("probability_weighted_upside_pct", 0),
            "probability_weighted_mcap_yi": sv.get("probability_weighted_mcap_yi", 0),
            "asymmetry_ratio": sv.get("asymmetry_ratio", 0),
            "quality_flag": sv.get("quality_flag", "MODERATE_QUALITY"),
        },
        "reverse_dcf": rd,
        "validation_crosscheck": vx,
        "expectation_gap": llm_output.get("expectation_gap", {}),
        "confidence": confidence,
        "trade_annotation": ta,
        "monitoring_kpis": llm_output.get("monitoring_kpis", {}),
        "reasoning_trace": _augment_trace_with_fixes(
            llm_output.get("reasoning_trace", []),
            sv,
            llm_original_values or {},
            sv.get("_bull_capped_by_code", False),
        ),
        "preflight_check": llm_output.get("preflight_check", []),
        "probability_rationale": llm_output.get("probability_rationale", ""),
        "risk_triggers": llm_output.get("risk_triggers", {}),
        "narrative": llm_output.get("narrative", ""),
        "data_gaps": llm_output.get("data_gaps", []),
        "signal_audit": llm_output.get("signal_audit", {}),
        "scenarios": scenarios,
        "case_comparison_summary": llm_output.get("case_comparison_summary", {}),
        "_validation_warnings": validation_warnings,
    }


# ═══════════════════════════════════════
# ScenarioAsymmetry 主类
# ═══════════════════════════════════════


class ScenarioAsymmetry:
    """推演裁决司命 — V6 Agent-3。

    V6 变化: 接收 agent2a_output（叙事诊断结论），信任其信号审核和 BS 解读，
    专注于情景推演 + 估值计算。
    """

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key or DEEPSEEK_API_KEY
        self.fetcher = DataFetcher()

    def run(
        self,
        data_package: dict,
        routing_decision: dict,
        event_data: dict | None = None,
        case_anchors: str = "",
        progress_cb: Callable[[int, str], None] | None = None,
        agent2a_output: dict | None = None,
    ) -> dict:
        """
        执行完整推演裁决。

        data_package: Agent-1 DataForge 输出
        routing_decision: Agent-2b routing_decision 部分
        event_data: Coze Agent0 输入
        case_anchors: Agent-2a 案例锚点文本（向后兼容）
        agent2a_output: V6 新增 — Agent-2a 叙事诊断输出（信号审核 + 计价判断）
        """
        cb = progress_cb or (lambda s, n: None)
        event_data = event_data or {}
        stock_code = data_package.get("stock_code", "")

        # ── Step 0: WACC + BS 预计算 ──
        cb(1, "WACC/BS预计算")
        wacc_params = precompute_wacc(self.fetcher, stock_code, data_package)
        primary = routing_decision.get("primary_model", "A")
        bs_profile = precompute_bs_profile(primary, data_package, wacc_params)

        # ── Step 1: LLM 推演裁决 ──
        cb(2, "LLM推演裁决")
        try:
            llm_output = _call_llm_scenario(
                bs_profile, wacc_params, data_package,
                routing_decision, case_anchors, event_data,
                agent2a_output=agent2a_output,
            )
        except ScenarioError as e:
            cb(3, f"LLM故障: {e.code}")
            if e.code in ("E302", "E303"):
                try:
                    llm_output = _call_llm_scenario(
                        bs_profile, wacc_params, data_package,
                        routing_decision, case_anchors, event_data,
                        agent2a_output=agent2a_output,
                    )
                except ScenarioError:
                    raise
            else:
                raise

        # ── Step 1.5: 代码计算（LLM出参数，代码出数字）──
        cb(3, "代码重算")
        # 快照 LLM 原始值（用于 trace 修正条目）
        sv_pre = llm_output.get("scenario_valuation", {})
        _llm_orig = {
            "upside": sv_pre.get("probability_weighted_upside_pct", None),
            "asymmetry": sv_pre.get("asymmetry_ratio", None),
            "mcap": sv_pre.get("probability_weighted_mcap_yi", None),
        }
        core_fields = data_package.get("packages", {}).get("core", {}).get("fields", {})
        computed = _compute_from_assumptions(
            llm_output.get("scenario_valuation", {}), primary, core_fields,
        )
        sv = llm_output.get("scenario_valuation", {})
        sv["probability_weighted_upside_pct"] = computed["probability_weighted_upside_pct"]
        sv["probability_weighted_mcap_yi"] = computed["probability_weighted_mcap_yi"]
        sv["asymmetry_ratio"] = computed["asymmetry_ratio"]
        sv["_computed_by_code"] = True

        # ── Step 1.55: Bull 概率硬封顶（低信号评分时抑制乐观偏误）──
        # V6: 优先使用 Agent-2a 的信号评分（信源更可靠，审核更完整）
        a2a_signal = (agent2a_output or {}).get("signal_audit", {})
        signal_audit = llm_output.get("signal_audit", a2a_signal)
        step2d = a2a_signal.get("step2d_score") or signal_audit.get("step2d_score", 10)
        details_raw = sv.get("scenario_details", {})
        if isinstance(details_raw, list):
            details = {item.get("scenario", ""): item for item in details_raw}
        else:
            details = details_raw

        bull_prob = details.get("bull", {}).get("probability", 0)
        cap_applied = False

        if step2d is not None and step2d <= 6:
            # 信号评分≤6: bull概率上限15%（防止在信号混杂时过度押注上行）
            # 评分≤4: bull概率上限8%
            cap = 0.15 if step2d >= 5 else 0.08
            if bull_prob > cap:
                excess = bull_prob - cap
                details["bull"]["probability"] = cap
                # 超出部分转移给base（bear概率不受影响——bear由证伪逻辑独立决定）
                details["base"]["probability"] = details.get("base", {}).get("probability", 0) + excess
                cap_applied = True
                print(f"  [Agent3 bull cap] step2d={step2d}≤6, bull {bull_prob:.0%}→{cap:.0%} "
                      f"(excess {excess:.0%}→base)", flush=True)

        # 如果封顶后概率和可能≠1（浮点），归一化
        if cap_applied:
            probs = {s: details.get(s, {}).get("probability", 0) for s in ("bear", "base", "bull")}
            total = sum(probs.values())
            if abs(total - 1.0) > 0.001:
                for s in probs:
                    details[s]["probability"] = round(probs[s] / total, 4)
            # 封顶后重新计算加权值
            computed = _compute_from_assumptions(sv, primary, core_fields)
            sv["probability_weighted_upside_pct"] = computed["probability_weighted_upside_pct"]
            sv["probability_weighted_mcap_yi"] = computed["probability_weighted_mcap_yi"]
            sv["asymmetry_ratio"] = computed["asymmetry_ratio"]
            sv["_bull_capped_by_code"] = True
            sv["_bull_cap_step2d"] = step2d

        # ── Step 1.6: 修正交易标注文字（消除数值-文字脱节）──
        cb(3.5, "修正交易标注")
        ta = llm_output.get("trade_annotation", {})
        details_raw = sv.get("scenario_details", {})
        if isinstance(details_raw, list):
            details = {item.get("scenario", ""): item for item in details_raw}
        else:
            details = details_raw
        bear_u = details.get("bear", {}).get("upside_pct", 0)
        bull_u = details.get("bull", {}).get("upside_pct", 0)
        llm_output["trade_annotation"] = _fix_trade_annotation(
            ta, computed["probability_weighted_upside_pct"],
            computed["asymmetry_ratio"], bear_u, bull_u,
        )

        # ── Step 2: 代码校验 ──
        cb(4, "一致性校验")
        validation_warnings = _validate_output(llm_output, bs_profile, wacc_params)
        validation_warnings = [w for w in validation_warnings if not w.get("code", "").startswith("E306")]
        if validation_warnings:
            codes = [w["code"] for w in validation_warnings]
            print(f"  [Agent3 validation] warnings: {codes}", flush=True)

        # ── Step 3: 组装输出 ──
        cb(5, "组装输出")
        output = _assemble_final_output(
            llm_output, bs_profile, data_package, routing_decision, validation_warnings,
            llm_original_values=_llm_orig,
        )

        cb(6, "推演裁决完成")
        return output


# ── 便捷函数 ──

def run_scenario_asymmetry(
    data_package: dict,
    routing_decision: dict,
    event_data: dict | None = None,
    case_anchors: str = "",
) -> dict:
    """便捷入口。"""
    agent = ScenarioAsymmetry()
    return agent.run(data_package, routing_decision,
                     event_data=event_data,
                     case_anchors=case_anchors)
