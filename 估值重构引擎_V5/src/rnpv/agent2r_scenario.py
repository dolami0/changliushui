"""
Agent-2r 管线情景估值 (RnpvScenarioValuation) — rNPV 管线 V7

完全重设计。核心理念对标 Agent-3：
  - LLM 输出有经济含义的参数（PoS、峰值销售、PE、折现率）
  - 代码负责算术（各药物 rNPV → 管线加总 → 成熟产品 → SOTP → 加权汇总）
  - 单次 LLM 调用完成旧 agent2r + agent3r 的工作

旧 agent2r/agent3r 的问题：
  1. LLM 直接输出 risk_adj_pv_yi / total_value_yi（黑箱，无代码校验）
  2. event_deduction / adversarial_thinking 未传入
  3. 两次 LLM 串行，agent3r 只是微调 agent2r 参数
  4. investment_theme 截断到 2000 字符

新设计：
  单次 LLM → 三情景参数推演 → 代码计算 → Agent-3 兼容输出
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from valuation_utils import call_deepseek
from agent3_scenario_asymmetry import (
    _call_llm2, _call_volc_search, _extract_search_queries, _merge_llm_outputs,
)


# ═══════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════

RNPV_SCENARIO_PROMPT = """# 你是创新药管线估值分析师

你的核心能力是用事件驱动故事来驾驭估值参数，用参数反推故事的可信度。

## 估值哲学：故事+数字双螺旋

没有故事的数字是尸体，没有数字的故事是童话。

创新药管线估值的两个维度：
- **叙事层**: 这家公司的管线组合解决什么临床需求？FDA/NDA/Ph3 各阶段有哪些催化剂？事件推演中的证实/证伪节点是什么？
- **参数层**: PoS（成功率）、峰值销售、折现率、时间线。成熟业务的 PE/PS 倍数。

铁律：事件叙事决定参数的输入，参数反推叙事的可信度。二者必须严丝合缝。

**赋参框架: 药物参数 = 理解起点（baseline）+ 事件冲击（event）**

两个信息来源，分工不同:

**Baseline（理解起点——告诉你"从哪出发"，不限制"能到哪"）**:
- 当前管线阶段/临床数据: PoS 的行业基准（Ph1~10%/Ph2~30%/Ph3~60%）——理解起点风险。突破性临床数据可以大幅上修。
- 已上市产品/市场空间: 峰值销售不能超过 TAM，但 TAM 本身由事件中的流行病学/定价/渗透率数据决定。
- 公司财务: 净现金/净负债、现有收入——估值的算术约束，不是战略约束。
- 可比药企: 参考不是牢笼。没有直接可比就凭行业知识判断。

**事件锚（变数——告诉你"往哪走、走多远"）**:
- 事件中的最新临床数据/FDA 进展/BD 合作/竞品格局——变化方向和幅度。
- 按来源置信度打折: 临床数据读出/公司公告 <10%，专家纪要/券商预测 10-30%，管理层指引/峰值假设 20-40%。
- 打折必须显式标注: 锚点原文→来源→置信度→打折幅度→打折后数字→理由。

**两者的关系**: Baseline 让你理解起点风险，事件让你知道基本面变了多少。参数最终位置由你的独立判断决定——baseline 是理解工具，不是约束工具。

## 估值框架：两段式 SOTP

```
公司价值 = 成熟业务价值 + Σ 各管线药物 rNPV + 净现金
```

### 第一段：成熟业务估值

已上市产品（仿制药+已获批创新药），按盈利状态：
- 稳定盈利 → PE 估值（参照同类创新药企中枢，通常 25-55x）
- 微利/亏损 → PS 估值（参照同类药企 PS 中枢）
- BEAR 中 PE 应回到行业周期底部（通常 15-30x）——创新药企在管线崩塌后估值会剧烈收缩

**成熟业务净利必须基于事件催化剂做前瞻估计，不能直接用 TTM：**
- TTM 净利是过去 12 个月的实际业绩——它是地板，不是天花板
- 你的任务是判断：基于事件催化剂（FDA 获批、BD 合作、新品上市），未来 12-24 个月的净利会到多少
- 从事件推演（event_deduction）中提取收入/利润传导节点：FDA 批准→海外销售起量、BD 首付款→其他收益、新适应症获批→国内份额扩张
- 投资主题（investment_theme）中的市场空间数据是前瞻估计的核心依据
- base 净利 = TTM × (1 + 催化剂驱动的增速)，增速必须有事件依据
- bull 净利 = 催化剂超预期兑现（放量更快、定价更高、适应症扩展）
- bear 净利 = 催化剂落空（商业化执行失败、竞品压制），可低于 TTM
- 例如：TTM 净利 8 亿 + FDA 获批打开 $1B+ 海外市场 + BD 首付款 8700 万美元 → base 不应还是 8 亿

### 第二段：管线药物 rNPV

每个管线药物（代码计算公式——赋参数前必读）:
```
rNPV = PoS% × 峰值销售(亿) × 3 / (1 + 折现率%)^到峰值年数
```
- 专利倍数固定为 3x: 代表峰值后约 7 年（爬坡+峰值+衰退）的净现值近似。不可自行调整。
- 你的任务: 填 PoS、峰值销售、折现率、到峰值年数这四个参数。代码用上面的公式算。
- 禁止心算估值: 不要自己算"这个药值多少亿"然后反推参数。参数来自基本面判断，rNPV 是代码的事。

**PoS 基准（按临床阶段）**:

| 阶段 | 基准 PoS | 调节因素 |
|------|:------:|------|
| Approved (已获批) | 100% | 已获 FDA/NMPA 批文，不可下调 |
| NDA (申报上市) | 75-90% | 审评风险、CMC 完备度 |
| Ph3 | 50-65% | 同类靶点历史通过率、竞品进度 |
| Ph2 | 15-25% | 概念验证数据优劣、靶点验证度 |
| Ph1 | 8-12% | 靶点新颖度、同类药物历史 |
| Preclinical | 3-8% | 平台技术验证、团队历史成功率 |

**调节规则**:
- 靶点已有同类药物获批 → +5-10ppt
- 靶点已有同类药物失败 → -5-10ppt（解释为什么你能成功）
- 已有积极临床数据 → +5-10ppt
- 竞争格局激烈（≥3 个同类在研）→ 峰值销售打折而非 PoS 打折
- 罕见病/突破性疗法认定 → +5-10ppt

**折现率基准**:
| 阶段 | 折现率 | 理由 |
|------|:------:|------|
| Approved | 8-12% | 执行风险为主 |
| Ph3 | 12-15% | 临床+审批风险 |
| Ph2 | 15-20% | 较高不确定性 |
| Ph1/Preclinical | 18-25% | 极高不确定性 |

**峰值销售估计**：基于 TAM（可及市场）× 渗透率 × 定价。引用 Volc 搜索结果和 Coze 预研中的市场数据。

## 三情景推演

你必须在 bear/base/bull 三个情景中为每个管线药物和成熟业务独立赋参。

### 情景定义

**Bear: 核心管线失败**
- 最关键的 1-2 个管线临床数据不及预期/未达终点
- 关键管线 PoS → 0（或大幅下调）
- 同靶点/同技术平台管线被波及（PoS 下调）
- 成熟业务 PE 收缩到行业底部
- 公司估值底 = 净现金 + 成熟业务折价 + 其余管线折价 PoS
- **已发生事实不可推翻**: FDA 已批就是已批（PoS=100% 不可下调），Ph3 已启动就是已启动
- 概率: 基于同类靶点历史失败率，通常 25-45%

**Base: 管线按预期推进**
- PoS 维持当前阶段基准，经事件信息调节
- 峰值销售取中位预估
- 成熟业务 PE/PS 维持当前中枢
- 概率: 100% - bear - bull

**Bull: 管线超预期**
- 核心管线临床数据显著优于竞品 / 获批加速 / 适应症扩展
- 核心管线 PoS 上调 10-15ppt（已获批的不变）
- 峰值销售上调 20-50%（适应症扩展/定价超预期/市场扩张）
- 早期管线因平台验证而 PoS 小幅上调
- 成熟业务 PE 扩张（平台价值获验证）
- 概率: 创新药"超预期"是小概率，通常 10-20%

### 事件驱动调节

用户消息中的 **发展推演** 包含三阶段（T+30/90/180 天）的证实/证伪节点和转移概率。你必须：
1. 引用证实/证伪节点来校准 PoS——已发生的证实节点提升 PoS，证伪节点下调 PoS
2. 引用 **逆向风险** 的五维风险（核心假设脆弱性/利益相关方博弈/反身性/产业链挤压/外部冲击）来校准 bear 概率
3. 引用 **投资主题** 的市场空间/竞争格局数据来校准峰值销售
4. 参考 **事件变量**（原始事件、事件研判）理解外部催化剂的确定性和结构性强弱
5. 参考 **行业全貌** 的竞争格局判断个股在产业链中的议价能力和利润率可持续性

**事件计价**: Agent-2a 已判断事件的计价程度。这是情景推演的起点——不是重新判断事件好不好，而是判断市场已经 price in 了多少。

## 思维禁区

- 禁止黑箱输出估值数字——你只输出参数，代码完成算术
- 禁止忽视事件推演中的证实/证伪节点——那是参数校准的核心依据
- 禁止对已获批药物下调 PoS——FDA/NMPA 批文是不可逆的事实
- 禁止模板化概率——bear 概率来自因果链条的独立环节数，不是固定模板
- 禁止参数脱节——PoS、峰值销售、折现率必须与临床阶段和竞争格局一致
- 禁止虚构管线——仅使用 Volc 搜索结果和 Coze 预研中明确提到的药物
- 禁止 bear=0 概率——创新药天然有失败风险，即使是 Approved 阶段的药物也有商业化失败可能

## 输出格式

```json
{
  "reasoning_trace": [
    "清单项1-素材吸收: 从发展推演/逆向风险/投资主题中提取关键证实/证伪节点和市场数据，理解事件变量的性质和影响范围",
    "清单项2-管线分析: 逐药评估临床阶段/竞争格局/催化剂时间线，引用2a诊断结论",
    "清单项3-三情景因果推演: bear/base/bull各情景的核心假设和因果链条",
    "清单项4-参数赋参: 各情景逐药赋参(需满足单调递增 bear<base<bull)",
    "清单项5-校验与评分: 参数一致性自检、置信度评定"
  ],

  "mature_business": {
    "method": "PE",
    "rationale": "创新药企已盈利，PE估值。参照A股创新药动态PE中枢40-45倍",
    "bear": {
      "pe_multiple": 30,
      "net_profit_yi": 10.0
    },
    "base": {
      "pe_multiple": 42,
      "net_profit_yi": 11.0
    },
    "bull": {
      "pe_multiple": 55,
      "net_profit_yi": 13.0
    }
  },

  "pipeline_drugs": [
    {
      "drug": "环泊酚海外 (Cipofol/CYPSEDO)",
      "clinical_phase": "Approved",
      "rationale": "2026年6月FDA获批。全球静脉麻醉市场$15-20B，凭注射痛优势(18% vs 77%)替代丙泊酚",
      "bear": {
        "pos_pct": 95,
        "peak_sales_yi": 30,
        "time_to_peak_years": 6,
        "discount_rate_pct": 15
      },
      "base": {
        "pos_pct": 100,
        "peak_sales_yi": 50,
        "time_to_peak_years": 5,
        "discount_rate_pct": 12
      },
      "bull": {
        "pos_pct": 100,
        "peak_sales_yi": 70,
        "time_to_peak_years": 4,
        "discount_rate_pct": 10
      }
    }
  ],

  "scenario_probabilities": {
    "bear": {
      "probability": 0.30,
      "narrative": "核心管线HSK31858 Ph3未达终点，管线价值归零，波及其他早期管线PoS下调。成熟业务PE收缩至30倍。"
    },
    "base": {
      "probability": 0.50,
      "narrative": "管线按预期推进，HSK31858 Ph3数据符合统计要求。环泊酚海外平稳商业化。成熟业务PE维持42倍。"
    },
    "bull": {
      "probability": 0.20,
      "narrative": "HSK31858 Ph3数据显著优于竞品，平台价值获验证。环泊酚海外超预期放量。成熟业务PE扩张至55倍。管线PoS全面上调。"
    }
  },

  "expectation_gap": {
    "level": "高估",
    "note": "SOTP公允价值 vs 当前市值的预期差分析。事件刚发生，市场可能尚未充分消化或过度反应。"
  },

  "confidence": {
    "overall_score": 5, "overall_label": "中",
    "dimensions": {
      "info_quality": {"score": 5, "label": "信息质量", "note": "rNPV置信度天然低于标准DCF——临床数据非一手"},
      "financial_feasibility": {"score": 5, "label": "财务可行性", "note": "管线PoS及峰值销售基于公开信息"},
      "valuation_safety": {"score": 5, "label": "估值安全边际", "note": "成熟业务估值依赖盈利预测"},
      "historical_precedent": {"score": 5, "label": "历史案例匹配", "note": "海外商业化执行风险较高"}
    }
  },
  "trade_annotation": {
    "tier": "★★☆ 中等赔率", "total_score": "5/10",
    "dimension_scores": {"odds_quality": 2, "pricing_headroom": 2, "transmission_confidence": 2, "model_consistency": 2},
    "tier_note": "基于概率加权回报和不对称比的综合判定",
    "suggested_action": "关注关键临床数据读出"
  },
  "monitoring_kpis": {
    "financial_verification_kpis": [{"name": "季度销售额", "baseline": "0", "target": "待定", "frequency": "季度", "verifies": "商业化执行"}],
    "event_milestone_kpis": [{"name": "Ph3数据读出", "expected_timing": "T+90天", "significance": "管线价值重估", "verification_source": "公司公告"}],
    "competition_signal_kpis": [{"name": "竞品进展", "current_state": "跟踪中", "trigger": "竞品获批", "action_if_triggered": "下调PoS"}],
    "risk_trigger_kpis": [{"name": "研发失败", "linked_to": "核心管线", "severity": "high", "monitor": "每季度"}]
  },

  "risk_triggers": {
    "bull_trigger": "HSK31858 Ph3积极中期数据 / 环泊酚海外销售超预期 / 新适应症获批",
    "bear_trigger": "HSK31858 Ph3失败或安全性问题 / 海外合作终止 / 核心人才流失",
    "frequency": "每季度或关键临床数据读出时"
  },

  "narrative": "海思科正处于从国内仿创结合向国际原研创新转型的关键拐点...",

  "data_gaps": [
    "环泊酚美国定价策略未公开",
    "礼来合作具体靶点未披露"
  ],

  "preflight_check": [
    "[OK] 已获批药物PoS=100%不可下调",
    "[OK] 参数三情景单调递增",
    "[OK] 概率和为1.0"
  ]
}
```

## 参数约束

1. **百分比字段使用实际数值**: pos_pct=50 表示 50%（不是 0.5）；discount_rate_pct=12 表示 12%
2. **概率字段使用 0-1 小数**: probability=0.30 表示 30%
3. **三情景参数单调递增**: bear < base < bull（每个药物的每个参数）
4. **概率和为 1.0**: bear + base + bull = 1.0
5. **已获批药物 PoS = 100%** (bear 可小幅下调至 90-95%，反映商业化失败风险，不可归零)
6. **输出纯 JSON**，不包含任何 markdown 标记或解释文字
"""


# ═══════════════════════════════════════
# rNPV LLM-2 系统提示词
# ═══════════════════════════════════════

RNPV_LLM2_PROMPT = """# 你是管线估值审阅官

审阅 LLM-1 的药物参数推演，对照代码计算的 rNPV 加总结果，补充缺失数据，纠正错误，输出完整最终报告。

## 多轮搜索（每轮最多 2 条）

## 任务

### 任务0: 事件锚点对照 —— 最先执行，写入 reasoning_trace

从事件素材中提取所有管线相关量化锚点（临床数据、峰值销售预测、竞品对标、BD 金额、时间节点），与 LLM-1 的药物参数做逐项对比。**不需要输出独立 JSON 字段**——结果直接写入 reasoning_trace 的 "LLM-2: 事件锚校验" 条目。

**reasoning_trace 必填条目格式**（自然语言）:
```
LLM-2: 事件锚校验:
- 事件锚点[临床数据/峰值/BD/时间]: (来源) → LLM-1 PoS/峰值/折现率 → 差距 → 打折合理性 → 结论
- 结论: N/M个锚点合理, 不合理锚点已在change_log修正
```

**执行规则**: 每个管线药物的关键锚点都要过一遍。算差距→判理由→做结论。不能 0 条 change_log 但锚校验写"多项不合理"——两者必须自洽。

### 任务 1: 数据补充 — LLM-1 的 data_gaps 和 change_request 是必搜清单

逐条生成 search_request，火山支持自然语言查询。volc 预搜索结果如已覆盖可跳过。每条缺口都要有对应的搜索或说明为何跳过。

### 任务 2: 逻辑审查 — 从 LLM-1 的 reasoning_trace 逐条追溯 + rNPV 三大盲区

先逐条读 LLM-1 的推理链: 每个参数赋值有依据吗？数据引用和 baseline 一致吗？风险映射在参数里有体现吗？

再检查 rNPV 模型的三大致命盲区:

rNPV = Σ(PoS × 峰值销售 × 系数 / (1+r)^t) + 成熟业务 PE − 净负债。这个公式天然低估三类价值，你必须逐项检查并修正:

**盲区 1: 平台溢价。** rNPV 把公司当成"几个药的清单"，但市场买的是"可能会持续出药的引擎"。如果公司有技术平台（口服多肽递送、AI 辅助设计、超长效修饰等），这些平台能力意味着: (a)现有药物的 PoS 高于行业基准（因为有平台验证）,(b)未来还有新资产会从平台产出——rNPV 不算这些东西。检查 LLM-1 的 PoS 和峰值销售是否反映了平台能力溢价。如果没有 → 上调 PoS 或峰值，附理由。

**盲区 2: 海外期权。** LLM-1 通常只给中国市场的峰值销售。如果公司在推进 FDA 临床、有海外合作伙伴、或药物机制具有全球竞争力，海外市场是真实的期权价值。检查: LLM-1 的峰值销售是否涵盖了海外？如果没有 → (a)在 bull 情景中加入海外峰值,(b)或在 base 中上调峰值反映海外概率加权。

**盲区 3: 成熟业务底部价值。** LLM-1 倾向用"TTM 净利 × 行业 PE"来估成熟业务。但对于转型期药企，TTM 净利往往是周期底部（研发费用吞噬、旧产品下滑）。市场给成熟业务的估值是对"正常化盈利+现金流+产能+客户关系"的定价，不是当前利润的快照。检查: (a)成熟业务的正常化净利润是多少（剔除一次性因素）?(b)OCF 是否远高于净利润（说明折旧掩盖了真实盈利能力）?(c)可比原料药/仿制药公司在非恐慌期的 EV/EBITDA 或 PS 是多少？如果 LLM-1 的成熟业务 PE 给的太低 → 上调至合理水平，附理由。

常规检查:
- PoS/峰值销售/折现率是否有支撑？
- 可比公司选对了吗？
- 管线是否有遗漏的资产？

**⚠️ 数据时效性铁律: 事件 > 一切。** 事件是唯一最新情报。券商预测/行业报告可能是事件前的旧数据。矛盾时以事件为准——券商没反映最新进展 → 券商过时了。

### 任务 3: 修正——参数修改 + 估值调整，两者缺一不可

**修正铁律: 沿事件因果链走。** 事件是第一性输入——NPV 用的 PoS/峰值/折现率必须反映事件中的最新临床数据/监管进展/竞争格局变化，不能用行业基准 PoS 做机械对标。事件才是最新的。

你有两个工具来修正 LLM-1 的估值。**两者互补，必须同时使用:**

**工具 A: change_log — 修正具体参数错误。**

LLM-1 的某个参数设错了——你能找到证据证明正确值是多少。适用于: PoS 偏差、峰值销售只算了中国、折现率不合理、PE 对标错误。

输出格式:
```json
"change_log": [
  {"path": "drugs.0.base.peak_sales_yi", "old_value": 30, "new_value": 45,
   "reason": "峰值销售仅覆盖中国。BGM0504美国Ph3已启动，应概率加权计入海外",
   "evidence": "FDA Type B EoP2 completed; 美国减重市场$50B+"}
]
```
path 引用格式: `drugs.N.base.param_name` (N=药物序号), 或 `mature_business.base.pe_multiple`

**工具 B: valuation_adjustments — 弥补 rNPV 模型的结构性盲区。**

rNPV 作为公式无法定价的东西。适用于: 技术平台溢价、海外期权(如果无法通过峰值销售表达)、成熟业务底部修正(如果TTM净利严重失真)。

在 `valuation_adjustments` 中输出三个调整项，每项含 `value_yi`(亿)、`apply_to`、`rationale`。

**铁律**: 如果你的 narrative 批评了某个参数或指出了某个低估，必须在 change_log 或 valuation_adjustments 中找到对应修正。两者都不能空——至少有一个要有实质内容。

### 任务 4: 最终判断 — 基于代码计算的 rNPV 数字
- 置信度、交易标注、预期差、最终叙事
- **关键**: 如果你的修改显著改变了估值（比如从 -84% 变成 -30%），在 narrative 中解释: 之前的估值漏了什么？你的修改反映了什么？

## 输出 Schema — 完整最终报告

{
  "drugs": [{ 同 LLM-1，需要修改则输出完整对象 }],
  "mature_business": { 同 LLM-1 },
  "scenario_valuation": { "scenario_details": { "bear/base/bull": { "同 LLM-1，代码计算" } } },
  "change_log": [
    {"path": "drugs.0.base.peak_sales_yi", "old_value": 30, "new_value": 45, "reason": "峰值仅中国，美国Ph3已启动", "evidence": "FDA Type B EoP2 completed"}
  ],
  "valuation_adjustments": {
    "platform_premium": {"value_yi": 0, "apply_to": "all_scenarios", "rationale": "..."},
    "overseas_option": {"value_yi": 0, "apply_to": "bull_only", "rationale": "..."},
    "mature_business_correction": {"value_yi": 0, "apply_to": "all_scenarios", "rationale": "..."}
  },
  "reasoning_trace": ["LLM-1: ...", "LLM-2: 审查-..."],
  "confidence": { "overall_score": 1-10 },
  "trade_annotation": { "tier": "..." },
  "monitoring_kpis": {}, "risk_triggers": {},
  "narrative": "...", "expectation_gap": { "level": "..." }
}

核心: WACC不可改 / 概率和=1.0 / 参数修改必须有证据 / 纯JSON / **禁止在 narrative 中写任何市值数字——估值由代码计算，你不应该自己估算**

**⚠️ 关键铁律: change_log 不能为空。** 如果你的 narrative 里写了"PoS偏低"、"峰值销售没算海外"、"成熟业务PE太低"、"平台价值被忽略"，你必须在 change_log 里给出对应的参数修改。narrative 里的每个审阅发现都必须能在 change_log 里找到对应的条目。只有一种情况 change_log 可以为空：你确认 LLM-1 的每个参数都完美无误。但这种情况下你的 narrative 也不应该包含任何批评。
"""


# ═══════════════════════════════════════
# 用户消息构建
# ═══════════════════════════════════════

def _build_user_message(
    pipeline_data: dict,
    event_data: dict,
    agent2a_output: dict | None = None,
) -> str:
    """构建 Agent-2r 用户消息。全量注入事件数据，不截断。"""
    fin = pipeline_data.get("company_financials", {})
    mature = pipeline_data.get("mature_products", [])
    volc = pipeline_data.get("volc_search_results", {})
    drugs = pipeline_data.get("pipeline_drugs_hint", [])

    stock_code = pipeline_data.get("stock_code", "")
    stock_name = pipeline_data.get("stock_name", "")

    # ── 管线药物（LLM 提取的结构化数据）──
    drugs_structured = pipeline_data.get("pipeline_drugs_structured", [])
    drugs_text = ""
    if drugs_structured:
        drugs_lines = []
        for d in drugs_structured:
            name = d.get('name') or '?'
            phase = d.get('clinical_phase') or '?'
            target = d.get('target') or '?'
            ind = d.get('indication') or '?'
            is_key = '是' if d.get('is_key_catalyst') else '否'
            drugs_lines.append(
                f"  - **{name}** [{phase}] "
                f"靶点:{target} "
                f"适应症:{ind} "
                f"关键催化剂:{is_key}"
            )
            if d.get("phase_detail"):
                drugs_lines.append(f"    阶段详情: {d['phase_detail']}")
            if d.get("peak_sales_hint"):
                drugs_lines.append(f"    市场数据: {d['peak_sales_hint']}")
        drugs_text = "\n".join(drugs_lines)
    elif drugs:
        drugs_text = "\n".join(f"  - {d}" for d in drugs)
    else:
        drugs_text = "  (未提取到具体药名，请从 Volc 搜索结果和预研原文中识别)"

    # ── Volc 搜索结果（不截断）──
    volc_parts = []
    for k, v in volc.items():
        if v:
            volc_parts.append(f"### {k}\n{v}")
    volc_text = "\n\n".join(volc_parts) if volc_parts else "(无搜索结果)"

    # ── 成熟产品 ──
    mature_text = ""
    for mp in mature:
        mature_text += (
            f"- {mp.get('name', '?')}: "
            f"营收 {mp.get('revenue_ttm_yi', 0)} 亿 "
            f"净利 {mp.get('profit_ttm_yi', 0)} 亿 "
            f"({mp.get('valuation_hint', '?')})\n"
        )
    if not mature_text:
        mature_text = "合并报表层面有收入，但无分产品拆分数据\n"

    # ── 事件与个股素材（全量，不截断）──
    event_sections = []
    if event_data.get("raw_event_text"):
        event_sections.append("## 事件变量\n" + str(event_data["raw_event_text"]))
    if event_data.get("preliminary_reasoning"):
        event_sections.append("## 事件研判\n" + str(event_data["preliminary_reasoning"]))
    if event_data.get("knowledge_supplement"):
        event_sections.append("## 背景知识\n" + str(event_data["knowledge_supplement"]))
    if event_data.get("investment_theme"):
        event_sections.append(f"## {stock_name}的投资主题\n" + str(event_data["investment_theme"]))
    if event_data.get("event_deduction"):
        event_sections.append(f"## {stock_name}的发展推演\n" + str(event_data["event_deduction"]))
    if event_data.get("adversarial_thinking"):
        event_sections.append(f"## {stock_name}的逆向风险\n" + str(event_data["adversarial_thinking"]))
    if event_data.get("industry_expert_research"):
        event_sections.append("## 行业全貌\n" + str(event_data["industry_expert_research"]))
    event_text = "\n\n".join(event_sections)

    # ── Agent-2a 诊断（如有）──
    a2a_text = ""
    if agent2a_output:
        mn = agent2a_output.get("market_narrative", {})
        ep = agent2a_output.get("event_pricing", {})
        pa = ep.get("pricing_assessment", {})
        sa = agent2a_output.get("signal_audit", {})

        a2a_lines = ["## Agent-2a 叙事诊断结论（必须信任，不可推翻）"]
        a2a_lines.append(f"- 估值锚: {mn.get('primary_anchor', '?')}")
        a2a_lines.append(f"- 锚证据: {mn.get('anchor_evidence', '?')}")
        a2a_lines.append(f"- 事件分布形状: {ep.get('event_profile', {}).get('distribution_shape', '?')}")
        a2a_lines.append(f"- 计价程度: {pa.get('overall_priced_in', '?')} ({pa.get('priced_in_estimate', '?')})")
        a2a_lines.append(f"- 残余催化剂: {pa.get('residual_catalyst', '?')}")
        a2a_lines.append(f"- 信号匹配度: step2d_score={sa.get('step2d_score', '?')}")
        a2a_lines.append(f"- 信号审核结论: {sa.get('score_rationale', '?')}")
        a2a_text = "\n".join(a2a_lines)

    # ── 组装 ──
    msg = f"""# 管线情景估值: {stock_name}({stock_code})

## 公司财务概况
- 市值: {fin.get('market_cap_yi', 0)} 亿
- 现金: {fin.get('cash_yi', 0)} 亿 | 有息负债: {fin.get('debt_yi', 0)} 亿 | 净现金: {fin.get('net_cash_yi', 0)} 亿
- 营收 TTM: {fin.get('revenue_ttm_yi', 0)} 亿 | 净利润 TTM: {fin.get('net_profit_ttm_yi', 0)} 亿
- 烧钱状态: {fin.get('burn_rate_hint', '?')}

## 成熟产品（已上市）
{mature_text}

## 管线药物（从 Coze 预研提取）
{drugs_text}

## Volc 知识搜索结果
{volc_text}

---

## 事件数据（估值核心输入）
{event_text}

---

{a2a_text}

---

请完成三情景参数推演。你只输出参数假设，所有估值数字由代码计算。
输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# 代码计算函数
# ═══════════════════════════════════════

def _compute_drug_rnpv(
    pos_pct: float,
    peak_sales_yi: float,
    time_to_peak_years: float,
    discount_rate_pct: float,
) -> float:
    """单药 rNPV = PoS% × 峰值销售 × 专利倍数 / (1 + 折现率%)^年数

    专利倍数固定为 3x，代表峰值后约 7 年销售额（爬坡+峰值+衰退）折现到峰值年的净现值。
    这是行业常用简化——不做逐年现金流预测，用峰值×3 近似整个专利期的 NPV。
    """
    PATENT_LIFE_MULTIPLE = 3.0
    if pos_pct <= 0 or peak_sales_yi <= 0 or time_to_peak_years < 0:
        return 0.0
    rate = 1 + discount_rate_pct / 100
    if rate <= 0:
        return 0.0
    return round(pos_pct / 100 * peak_sales_yi * PATENT_LIFE_MULTIPLE / (rate ** time_to_peak_years), 2)


def _compute_mature_value(method: str, params: dict) -> float:
    """成熟业务估值。"""
    if method == "PE":
        pe = params.get("pe_multiple", 0)
        profit = params.get("net_profit_yi", 0)
        if pe > 0 and profit > 0:
            return round(pe * profit, 1)
    elif method == "PS":
        ps = params.get("ps_multiple", 0)
        revenue = params.get("revenue_yi", 0)
        if ps > 0 and revenue > 0:
            return round(ps * revenue, 1)
    return 0.0


def _compute_sotp_scenario(
    llm_output: dict,
    scenario: str,
    net_cash_yi: float,
    current_mcap_yi: float,
) -> dict:
    """计算单个情景的 SOTP 总值。

    返回: {total_value_yi, mature_value_yi, pipeline_value_yi, drug_values, upside_pct}
    """
    mature_cfg = llm_output.get("mature_business", {})
    method = mature_cfg.get("method", "PE")
    mature_params = mature_cfg.get(scenario, {})
    mature_val = _compute_mature_value(method, mature_params)

    drugs = llm_output.get("pipeline_drugs", [])
    drug_values = []
    pipeline_total = 0.0
    for d in drugs:
        params = d.get(scenario, {})
        if not params:
            continue
        rnpv = _compute_drug_rnpv(
            pos_pct=params.get("pos_pct", 0),
            peak_sales_yi=params.get("peak_sales_yi", 0),
            time_to_peak_years=params.get("time_to_peak_years", 5),
            discount_rate_pct=params.get("discount_rate_pct", 12),
        )
        drug_values.append({
            "drug": d.get("drug", "?"),
            "clinical_phase": d.get("clinical_phase", "?"),
            "rnpv_yi": rnpv,
            "params": params,
        })
        pipeline_total += rnpv

    pipeline_total = round(pipeline_total, 2)
    total = round(mature_val + pipeline_total + net_cash_yi, 1)
    upside = round((total / current_mcap_yi - 1) * 100, 1) if current_mcap_yi > 0 else 0

    return {
        "total_value_yi": total,
        "mature_value_yi": round(mature_val, 1),
        "pipeline_value_yi": pipeline_total,
        "net_cash_yi": net_cash_yi,
        "drug_values": drug_values,
        "upside_pct": upside,
    }


def _compute_from_assumptions(
    llm_output: dict,
    net_cash_yi: float,
    current_mcap_yi: float,
) -> dict:
    """三情景加权汇总。对标 agent3._compute_from_assumptions。

    从 LLM 的参数逐情景计算 SOTP → 概率加权。
    回写 target_mcap_yi / upside_pct 到 llm_output。
    """
    probs_config = llm_output.get("scenario_probabilities", {})
    scenario_results = {}

    for sn in ("bear", "base", "bull"):
        prob_cfg = probs_config.get(sn, {})
        prob = prob_cfg.get("probability", 0)

        result = _compute_sotp_scenario(llm_output, sn, net_cash_yi, current_mcap_yi)
        result["probability"] = prob
        result["narrative"] = prob_cfg.get("narrative", "")
        scenario_results[sn] = result

    # 概率加权汇总
    probs = [scenario_results[s]["probability"] for s in ("bear", "base", "bull")]
    upsides = [scenario_results[s]["upside_pct"] for s in ("bear", "base", "bull")]
    mcaps = [scenario_results[s]["total_value_yi"] for s in ("bear", "base", "bull")]

    weighted_upside = round(sum(p * u for p, u in zip(probs, upsides)), 1)
    weighted_mcap = round(sum(p * m for p, m in zip(probs, mcaps)), 1)
    bull_u = upsides[2]
    bear_u = upsides[0]
    asym = round(abs(bull_u / bear_u), 1) if bear_u != 0 and abs(bull_u) > 0 else 0

    # ── 回写到 llm_output（保证后续组装兼容）──
    # 构造 scenario_details
    details = {}
    for sn in ("bear", "base", "bull"):
        r = scenario_results[sn]
        details[sn] = {
            "probability": r["probability"],
            "scenario_narrative": r["narrative"],
            "target_mcap_yi": r["total_value_yi"],
            "upside_pct": r["upside_pct"],
            "mature_value_yi": r["mature_value_yi"],
            "pipeline_value_yi": r["pipeline_value_yi"],
            "net_cash_yi": r["net_cash_yi"],
            "_drug_values": r["drug_values"],
        }
    llm_output["scenario_valuation"] = {"scenario_details": details}

    valuation_summary = {
        "probability_weighted_upside_pct": weighted_upside,
        "probability_weighted_mcap_yi": weighted_mcap,
        "asymmetry_ratio": asym,
        "_computed_by_code": True,
    }

    return valuation_summary


# ═══════════════════════════════════════
# 校验函数（简化版，对标 agent3._validate_output）
# ═══════════════════════════════════════

def _validate_rnpv_output(llm_output: dict) -> list[dict]:
    """校验 rNPV LLM 输出的核心约束。"""
    warnings = []

    # 概率和
    probs_cfg = llm_output.get("scenario_probabilities", {})
    prob_sum = sum(
        probs_cfg.get(s, {}).get("probability", 0)
        for s in ("bear", "base", "bull")
    )
    if abs(prob_sum - 1.0) > 0.05:
        warnings.append({
            "code": "E301", "severity": "warning",
            "message": f"概率和={prob_sum:.2f}≠1.0",
            "action": "以代码归一化为准",
        })

    # 单调性：三情景参数递增
    drugs = llm_output.get("pipeline_drugs", [])
    for d in drugs:
        for key in ("pos_pct", "peak_sales_yi", "time_to_peak_years", "discount_rate_pct"):
            vals = []
            for sn in ("bear", "base", "bull"):
                v = d.get(sn, {}).get(key)
                if v is not None:
                    vals.append(v)
            if len(vals) == 3:
                if key == "time_to_peak_years":
                    # 时间：bull 应该更快（更短），所以 bear > base > bull
                    if not (vals[0] >= vals[1] >= vals[2]):
                        warnings.append({
                            "code": "E305", "severity": "warning",
                            "message": f"{d.get('drug','?')} {key}单调性违反: bear={vals[0]} base={vals[1]} bull={vals[2]}",
                        })
                elif key == "discount_rate_pct":
                    # 折现率：bull 应该更低（风险更小）
                    if not (vals[0] >= vals[1] >= vals[2]):
                        warnings.append({
                            "code": "E305", "severity": "warning",
                            "message": f"{d.get('drug','?')} {key}单调性违反: bear={vals[0]} base={vals[1]} bull={vals[2]}",
                        })
                else:
                    # PoS 和峰值销售：bear < base < bull
                    if not (vals[0] <= vals[1] <= vals[2]) or (vals[0] == vals[1] == vals[2]):
                        warnings.append({
                            "code": "E305", "severity": "warning",
                            "message": f"{d.get('drug','?')} {key}单调性违反: bear={vals[0]} base={vals[1]} bull={vals[2]}",
                        })

    # 成熟业务参数单调性
    mature = llm_output.get("mature_business", {})
    for key in ("pe_multiple", "net_profit_yi", "ps_multiple", "revenue_yi"):
        vals = []
        for sn in ("bear", "base", "bull"):
            v = mature.get(sn, {}).get(key)
            if v is not None:
                vals.append(v)
        if len(vals) == 3 and not (vals[0] <= vals[1] <= vals[2]):
            warnings.append({
                "code": "E305", "severity": "warning",
                "message": f"成熟业务{key}单调性违反: bear={vals[0]} base={vals[1]} bull={vals[2]}",
            })
            break  # 只报一次

    # Approved 药物 PoS 必须接近 100%
    for d in drugs:
        phase = d.get("clinical_phase", "")
        if phase == "Approved":
            for sn in ("bear", "base", "bull"):
                pos = d.get(sn, {}).get("pos_pct", 0)
                if sn == "bear" and pos < 85:
                    warnings.append({
                        "code": "E308", "severity": "warning",
                        "message": f"已获批药物 {d.get('drug','?')} bear PoS={pos}%<85%——除非有撤回批文风险",
                    })
                elif sn in ("base", "bull") and pos < 95:
                    warnings.append({
                        "code": "E308", "severity": "warning",
                        "message": f"已获批药物 {d.get('drug','?')} {sn} PoS={pos}%<95%",
                    })

    return warnings


# ═══════════════════════════════════════
# 交易标注修正（简化版，对标 agent3._fix_trade_annotation）
# ═══════════════════════════════════════

def _fix_trade_annotation(
    ta: dict,
    weighted_upside: float,
    asymmetry: float,
) -> dict:
    """用代码计算值修正 trade_annotation 中的 tier，消除 LLM 文字与代码数值脱节。"""
    if weighted_upside >= 50 and asymmetry >= 2.5:
        tier = "★★★ 高赔率机会"
    elif weighted_upside >= 20 or asymmetry >= 2.0:
        tier = "★★☆ 中等赔率"
    elif weighted_upside > 0:
        tier = "★☆☆ 低赔率机会"
    else:
        tier = "☆☆☆ 规避"

    ta["tier"] = tier
    return ta


# ═══════════════════════════════════════
# 输出组装（Agent-3 兼容格式）
# ═══════════════════════════════════════

def _compute_aggregate_params(llm_output: dict, scenario: str) -> dict:
    """计算 rNPV 聚合参数（供 report_builder Model F 列使用）。"""
    drugs = llm_output.get("pipeline_drugs", [])
    total_peak = 0.0
    weighted_pos = 0.0
    weighted_dr = 0.0
    for d in drugs:
        params = d.get(scenario, {})
        peak = params.get("peak_sales_yi", 0) or 0
        pos = params.get("pos_pct", 0) or 0
        dr = params.get("discount_rate_pct", 0) or 0
        total_peak += peak
        weighted_pos += pos * peak
        weighted_dr += dr * peak
    avg_pos = round(weighted_pos / total_peak, 1) if total_peak > 0 else 0
    avg_dr = round(weighted_dr / total_peak, 1) if total_peak > 0 else 0
    return {
        "pos_pct": avg_pos,
        "peak_sales_yi": round(total_peak, 1),
        "discount_rate_pct": avg_dr,
        "_note": "聚合值: PoS/折现率为峰值销售加权平均, 峰值销售为全管线加总",
    }


def _assemble_output(
    llm_output: dict,
    valuation_summary: dict,
    pipeline_data: dict,
    agent2a_output: dict | None = None,
) -> dict:
    """组装 Agent-3 兼容的最终输出。"""
    fin = pipeline_data.get("company_financials", {})
    details = llm_output.get("scenario_valuation", {}).get("scenario_details", {})

    # ── scenarios 列表（Agent-3 格式）──
    scenarios = []
    for sn in ("bear", "base", "bull"):
        d = details.get(sn, {})
        agg = _compute_aggregate_params(llm_output, sn)
        scenarios.append({
            "name": sn,
            "probability_pct": round(d.get("probability", 0) * 100, 1),
            "upside_pct": d.get("upside_pct", 0),
            "target_mcap_yi": d.get("target_mcap_yi", 0),
            "scenario_narrative": d.get("scenario_narrative", ""),
            "valuation_method": "F",  # rNPV
            "nopat_path_yi": [],
            "wacc_used_pct": 10.0,  # rNPV 不适用 WACC
            "primary_model": "F",
            # Model F 列参数（聚合值，供 report_builder 显示）
            "pos_pct": agg["pos_pct"],
            "peak_sales_yi": agg["peak_sales_yi"],
            "discount_rate_pct": agg["discount_rate_pct"],
            # rNPV 特有
            "mature_value_yi": d.get("mature_value_yi", 0),
            "pipeline_value_yi": d.get("pipeline_value_yi", 0),
        })

    # ── 置信度降级（如有校验警告）──
    confidence = llm_output.get("confidence", {})

    # ── 交易标注 ──
    ta = llm_output.get("trade_annotation", {})
    ta = _fix_trade_annotation(
        ta,
        valuation_summary.get("probability_weighted_upside_pct", 0),
        valuation_summary.get("asymmetry_ratio", 0),
    )

    return {
        "scenario_narratives": {
            sn: details.get(sn, {}).get("scenario_narrative", "")
            for sn in ("bear", "base", "bull")
        },
        "scenario_valuation": llm_output.get("scenario_valuation", {}),
        "valuation_summary": valuation_summary,
        "scenarios": scenarios,
        "expectation_gap": llm_output.get("expectation_gap", {}),
        "confidence": confidence,
        "trade_annotation": ta,
        "monitoring_kpis": llm_output.get("monitoring_kpis", {}),
        "risk_triggers": llm_output.get("risk_triggers", {}),
        "narrative": llm_output.get("narrative", ""),
        "data_gaps": llm_output.get("data_gaps", []),
        "reasoning_trace": llm_output.get("reasoning_trace", []),
        # ── rNPV 特有字段 ──
        "_rnpv_breakdown": {
            "mature_business": llm_output.get("mature_business", {}),
            "pipeline_drugs": llm_output.get("pipeline_drugs", []),
        },
    }


# ═══════════════════════════════════════
# Agent-2r 主类
# ═══════════════════════════════════════

class RnpvScenarioValuation:
    """管线情景估值 — rNPV Agent-2r (V7)。

    单次 LLM 调用：
      1. LLM 推演三情景参数
      2. 代码计算所有估值数值
      3. 组装 Agent-3 兼容输出
    """

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key

    def run(
        self,
        pipeline_data: dict,
        event_data: dict | None = None,
        agent2a_output: dict | None = None,
    ) -> dict:
        """
        执行管线情景估值。

        pipeline_data: Agent-1r 输出
        event_data: Coze Agent0 预研（全量，不截断）
        agent2a_output: Agent-2a 叙事诊断结论

        返回: Agent-3 兼容格式的完整输出
        """
        event_data = event_data or {}
        fin = pipeline_data.get("company_financials", {})

        # Step 1: 构建用户消息
        user_msg = _build_user_message(pipeline_data, event_data, agent2a_output)

        # ── Step 2: LLM-1 参数推演 ──
        print(f"  [rNPV] LLM-1 参数推演...", flush=True)
        result = call_deepseek(
            RNPV_SCENARIO_PROMPT, user_msg,
            temperature=0.1,
            api_key=self.api_key,
        )

        # 重试一次
        if "_parse_error" in result:
            print(f"  [rNPV] LLM-1 解析失败，重试...", flush=True)
            result = call_deepseek(
                RNPV_SCENARIO_PROMPT, user_msg,
                temperature=0.1,
                api_key=self.api_key,
            )

        if "_parse_error" in result:
            return {
                "_error": "LLM调用失败，无法完成管线估值",
                "_fallback": True,
                "_parse_error": result.get("_parse_error", ""),
            }

        # ── Step 3: 代码计算估值 ──
        net_cash = fin.get("net_cash_yi", 0)
        current_mcap = fin.get("market_cap_yi", 0)
        valuation_summary = _compute_from_assumptions(result, net_cash, current_mcap)

        # ── Step 3.5: volc 预搜索 ──
        pre_search_queries = _extract_search_queries(result)
        volc_pre_search = ""
        if pre_search_queries:
            volc_results = []
            for q in pre_search_queries:
                try:
                    res = _call_volc_search(q)
                    volc_results.append(f"查询: {q}\n结果: {res}")
                except Exception:
                    volc_results.append(f"查询: {q}\n结果: 搜索失败")
            volc_pre_search = "\n\n".join(volc_results)

        # ── Step 3.7: LLM-2 审阅 ──
        print(f"  [rNPV] LLM-2 审阅...", flush=True)
        try:
            llm2_result = _call_llm2(
                result, valuation_summary,
                {"pe_ttm": fin.get("pe_ttm", 0), "pb": fin.get("pb", 0),
                 "implied_g_pct": 0, "market_premium_pct": 0, "ev_yi": 0,
                 "nopat_yi": 0, "roic_pct": 0,
                 "wacc_simple_pct": 10},
                {},  # wacc_params not needed for rNPV
                {"packages": {"core": {"fields": fin}}},  # minimal data_package
                {},
                {},  # routing
                system_prompt=RNPV_LLM2_PROMPT,
                volc_pre_search=volc_pre_search,
            )
        except Exception:
            print("  [rNPV] LLM-2 故障，降级", flush=True)
            import traceback
            traceback.print_exc()
            llm2_result = {}

        # ── Step 4: 合并，LLM-2 为主体 ──
        # 先保护 LLM-1 的核心数据（drugs, mature_business），防止被 LLM-2 的空数组覆盖
        llm1_drugs = result.get("drugs", [])
        llm1_mature = result.get("mature_business", {})
        result = _merge_llm_outputs(result, llm2_result)
        # 如果 LLM-2 输出了空的 drugs/mature_business，回退到 LLM-1 的
        if not result.get("drugs"):
            result["drugs"] = llm1_drugs
        if not result.get("mature_business") or not any(
            result.get("mature_business", {}).get(s, {}).get("pe_multiple")
            for s in ("bear", "base", "bull")
        ):
            result["mature_business"] = llm1_mature

        # ── Step 4.3: 应用 change_log 中的参数修改 ──
        changes = result.get("change_log", [])
        if changes:
            drugs = result.get("drugs", [])
            mature = result.get("mature_business", {})
            for c in changes:
                path = c.get("path", "")
                parts = path.split(".")
                new_val = c.get("new_value")
                if parts[0] == "drugs" and len(parts) >= 4:
                    idx = int(parts[1])
                    if idx < len(drugs):
                        target = drugs[idx]
                        for p in parts[2:-1]:
                            target = target.get(p, {})
                        c["old_value"] = target.get(parts[-1])
                        target[parts[-1]] = new_val
                elif parts[0] == "mature_business" and len(parts) >= 3:
                    target = mature
                    for p in parts[1:-1]:
                        target = target.get(p, {})
                    c["old_value"] = target.get(parts[-1])
                    target[parts[-1]] = new_val
            if changes:
                print(f"  [rNPV] 应用了 {len(changes)} 条参数修改", flush=True)

        # ── Step 4.5: 重新计算 ──
        valuation_summary = _compute_from_assumptions(result, net_cash, current_mcap)

        # ── Step 4.7: 应用 LLM-2 的估值调整 ──
        adjustments = result.get("valuation_adjustments", {})
        if adjustments:
            for adj_name, adj in adjustments.items():
                if not isinstance(adj, dict) or not adj.get("value_yi"):
                    continue
                val = adj["value_yi"]
                apply_to = adj.get("apply_to", "all_scenarios")
                sv = result.get("scenario_valuation", {}).get("scenario_details", {})
                for scenario_name in ("bear", "base", "bull"):
                    if apply_to == "bull_only" and scenario_name != "bull":
                        continue
                    if scenario_name in sv:
                        sv[scenario_name]["target_mcap_yi"] = sv[scenario_name].get("target_mcap_yi", 0) + val
                print(f"  [rNPV] 估值调整: {adj_name} +{val}亿 (apply_to={apply_to}) — {adj.get('rationale','')[:80]}", flush=True)

            # 重新计算加权汇总
            sv = result.get("scenario_valuation", {}).get("scenario_details", {})
            probs, upsides, mcaps = [], [], []
            for s in ("bear", "base", "bull"):
                d = sv.get(s, {})
                p = d.get("probability", 0)
                m = d.get("target_mcap_yi", 0)
                u = (m / current_mcap - 1) * 100 if current_mcap > 0 else 0
                probs.append(p)
                upsides.append(u)
                mcaps.append(m)
                d["upside_pct"] = round(u, 1)
            w_up = sum(p * u for p, u in zip(probs, upsides))
            w_mcap = sum(p * m for p, m in zip(probs, mcaps))
            asym = abs(upsides[2] / upsides[0]) if upsides[0] != 0 else 0
            valuation_summary = {
                "probability_weighted_upside_pct": round(w_up, 1),
                "probability_weighted_mcap_yi": round(w_mcap, 1),
                "asymmetry_ratio": round(asym, 2),
            }

        # ── Step 5: 校验 + 组装 ──
        validation_warnings = _validate_rnpv_output(result)
        output = _assemble_output(result, valuation_summary, pipeline_data, agent2a_output)

        if validation_warnings:
            if "_validation_warnings" not in output:
                output["_validation_warnings"] = []
            output["_validation_warnings"].extend(validation_warnings)
            conf = output.get("confidence", {})
            if isinstance(conf, dict):
                orig = conf.get("overall_score", 5)
                conf["overall_score"] = max(1, orig - 1)
                conf["overall_label"] = (
                    "高" if conf["overall_score"] >= 7 else
                    "中" if conf["overall_score"] >= 4 else "低"
                )

        return output


# ── 便捷函数 ──

def run_rnpv_scenario(
    pipeline_data: dict,
    event_data: dict | None = None,
    agent2a_output: dict | None = None,
    deepseek_key: str | None = None,
) -> dict:
    """便捷入口：运行 rNPV 管线情景估值。"""
    agent = RnpvScenarioValuation(deepseek_key=deepseek_key)
    return agent.run(pipeline_data, event_data, agent2a_output)
