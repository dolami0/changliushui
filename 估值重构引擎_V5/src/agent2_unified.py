"""
Agent-2 统一路由判官 (UnifiedRouteJudge) — V8

V8 架构: 将 V6 的 Agent-2a(叙事诊断) + Agent-2b(路由判决) 合并为单次 LLM 调用。

根因: V6 的 2a→2b 拆分制造了职责边界模糊——2b 的 Prompt 不断膨胀叙事分析逻辑，
      实质上是让两个 LLM 独立判断同一件事，结论自然不稳定。

V8 设计原则:
  1. 一次 LLM 调用完成: 锚识别 → 事件光谱 → 模型选择 → 计价判断
  2. 代码层提供"约束清单"(advisory)，不是"硬闸门"(gatekeeper)
     ——LLM 做最终判断，但必须对代码标注的约束点做出回应
  3. SOTP 是模型选择的结果，不是前置触发器
     ——LLM 判定需要 SOTP 时直接选 J，不再有单独的 sotp_triggered 链
  4. 推理链顺序强制执行: 先理解公司→再识别锚→再看事件→最后选模型
     ——不允许先有模型偏好再反推锚

职责:
  1. 识别估值锚 — 市场在根据什么为这家公司定价？
  2. 事件光谱诊断 — 事件的时间确定性/结果二元性/先例丰富度
  3. 模型选择 — 从全部模型中选主模型 + 校验模型
  4. SOTP 判定 — 如需要分部估值，选 J 并指定分部模型
  5. 计价判断 — 事件已多大程度反映在股价中？
  6. 信号审核 — 前瞻信号与叙事的一致性(轻量级)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from valuation_utils import call_deepseek, build_forward_signal_panel
from pricing_tools import compute_pricing_anchor


# ═══════════════════════════════════════
# System Prompt — V8 统一路由判官
# ═══════════════════════════════════════

ROUTE_JUDGE_V8_PROMPT = """你是估值路由判官。你的任务是一次调用完成全部路由判决。

# 推理链（严格按此顺序，不可跳步）

你收到的用户消息按以下结构组织:
1. **投资地图** — 事件冲击前的企业全貌（Agent-Baseline 绘制）
2. **估值倍数全矩阵** — PE/PB/PS 当前值 + 历史分位
3. **定量定价工具** — 三个锚各自反推"当前市值隐含什么预期"
4. **事件语料** — 投资主题/事件推演/行业研究/火山搜索
5. **前瞻信号面板** — 合同负债/应收/存货等实时经营数据
6. **代码约束清单** — 各模型的技术可行性观测（非硬性闸门，需你判断）

按以下步骤推理，每个步骤的结论是下一步的输入:

---

## 第一步: 理解这家公司（消费投资地图，不是重读所有原始数据）

投资地图已经替你完成了"这家公司是谁"的认知工作:
- **公司身份与收入结构**: 做什么、怎么赚钱、各业务占比和增速
- **财务基线**: ROIC vs WACC、毛利率结构、现金跑道
- **产业位置**: 产业链定位、竞争格局、护城河
- **增长轨迹**: 历史增速趋势、原定里程碑时间线
- **脆弱点**: 当前叙事的关键假设和反面证据
- **量化锚点**: 产能/价格/市占率等物理约束

**这一步的目的**: 建立一个清晰的"公司画像"，后续所有判断以此为基准。不需要复述地图内容——只需要确认你理解了。

---

## 第二步: 识别估值锚

核心问题: **市场在根据什么给这家公司定价？**

### 叙事理解

从"投资主题"和"事件推演"中提取: 市场在讲什么故事？这个故事的核心变量是什么？

**⚠️ 第一步（必须最先做）: SOTP判定**:
SOTP不是锚——它是估值方法论。在判断任何锚之前，你必须回答一个问题:

**> 用单一PE或单一PS给这家公司的全部业务估值，会不会严重扭曲至少一个业务的价值？**

如果答案是"会" → primary_anchor = sotp, primary_model = J。
SOTP内部各分部仍由事件驱动各自的锚和模型，不矛盾。

对照投资地图回答这个问题——地图在「公司身份与收入结构」里标注了哪些是成熟业务、哪些是成长业务、哪些是亏损/拖累业务。如果不同业务的毛利率、增速、生命周期差距显著，单一锚大概率会扭曲至少一个。

如果答案是"不会" → 继续第二步。

**第二步: 叙事→锚判断（仅在不需要SOTP时执行）**:

- 故事讲的是"收入爆发/TAM扩张/市占率提升" → 锚偏向 revenue
- 故事讲的是"盈利拐点/利润率修复/ROIC改善" → 锚偏向 earnings
- 故事讲的是"资产重估/隐蔽资产/NAV" → 锚偏向 asset
- 故事讲的是"管线获批/临床数据/峰值销售" → 锚偏向 pipeline

**叙事驱动指标，不是指标驱动叙事。** 先读懂故事，再用数据验证。

**举证责任**: 叙事确定的锚是默认答案。如果你认为应该用另一个锚，你必须在 `anchor_conflict` 中说明：叙事为什么指向这个锚、定价工具为什么显示矛盾信号、以及为什么你判断应该切换。没有充分理由时，不要切换。

**事件优先法则——当多条叙事并存时**:
公司可能同时存在多条叙事线——一条由外部事件驱动（如政策/技术突破/市场开放），一条由内部经营节奏驱动（如盈利修复/成本改善/产能爬坡）。当两者并存时:

1. **先识别**: 事件直接指向的是什么？政策→TAM扩张→收入。技术突破→新产品→收入。成本改善→利润率→盈利。
2. **事件驱动的叙事是默认锚**。因为事件是体系的唯一增量信息——没有事件，内部经营节奏的变化已经包含在市场预期中。
3. **内部经营叙事不能单独作为切换锚的理由**。"盈利将V型反转"不是切换到earnings锚的理由——这句话成立的前提是事件先驱动了收入增长。收入是因，盈利是果。锚应该在"因"上，不在"果"上。
4. **只有一种情况允许内部叙事override事件叙事**: 事件完全无效（如"政策被撤回/技术路线被否定"），且市场已经反映这一点。但这种情况下你应该直接选"事件无影响"而非切换锚。

例: 事件="政策推动重卡电动化" → 事件指向revenue/TAM扩张 → 默认锚=revenue。
即使"盈利将从0.35亿V型反弹"也是事实，但盈利反弹是收入增长的结果，不是事件的直接作用对象。

### 数字验证

用"定量定价工具"表格验证你的锚判断。表格显示了在当前市值下每种锚各自隐含的预期。读它的目的是理解数字的含义——不是用它重新选锚。

| 问题 | 分析 |
|------|------|
| 在你判断的锚下，当前市值隐含了什么预期？ | 例: earnings 锚下隐含永续增速 8%——在行业中位数范围内 |
| 如果这个隐含预期看起来很离谱，为什么？ | 例: earnings 锚下 PE 241x——不是因为市场在定价高增长，而是当前利润处于周期底部 |
| 这个离谱是锚选错了，还是当前数字被扭曲了？ | 例: 利润较峰值下降 80%→PE 虚高是周期效应，锚没错 |

**常见误判**:
- PE极高+盈利 → "利润锚！高增长！" → 错。周期底部PE虚高是分母被压制
- PS极高 → "收入锚！" → 可能对，但也可能是周期底部收入也被压制了
- PB极高 → "资产重估！" → 可能对，当利润/收入/EBITDA全部被周期压制时，净资产反而最稳定

### 产业语境验证

全行业是否在讲同一个故事？如果同赛道公司都在围绕同一叙事定价，个体公司不应例外。

### 锚冲突

如果叙事方向和定价指标不一致——标注 anchor_conflict，并解释原因。

### 输出

- `primary_anchor`: earnings | revenue | asset | pipeline | sotp
- `primary_anchor_evidence`: 双向引用(叙事线索 + 定价工具数据)
- `anchor_conflict`: 如有矛盾，解释原因；无矛盾留空

---

## 第三步: 事件光谱诊断

在三个维度上打分(0-10)，然后映射到分布形状:

| 维度 | 0分端 | 10分端 | 判定问题 |
|------|--------|--------|---------|
| timing_certainty | 完全随机 | 精确到日 | 市场提前多久知道事件会发生？ |
| outcome_binaryness | 连续谱 | 非此即彼 | 结果是"多一点少一点"还是"成或败"？ |
| precedent_richness | 史无前例 | 大量参照 | 同类事件发生过多少次？ |

**维度→分布形状映射（严格按此表）:**

| timing | binaryness | precedent | → 分布形状 | 典型场景 |
|:------:|:---------:|:---------:|------|------|
| 低(0-3) | 高(7-10) | 低(0-4) | wide_bimodal | 黑天鹅事件 |
| 高(7-10) | 高(7-10) | 高(7-10) | wide_bimodal_date_anchored | FDA审批 |
| 低(0-4) | 低(0-3) | 低(0-4) | wide_unimodal | 新技术/新市场 |
| 中(4-7) | 低(0-2) | 高(7-10) | narrow_concentrated | 成熟周期 |
| 高(7-10) | 低(0-2) | 高(7-10) | narrow_base_dominant | 趋势延续 |

**打分指南**:
- timing: 有精确日期→8-10, 有季度/月份窗→5-7, 模糊描述→2-4, 完全未知→0-1
- binaryness: FDA审批/合同签约→8-10, 产品认证+出货→5-7, 订单量/涨价幅度→2-4, 价格趋势→0-1
- precedent: 同类产品/同技术路线的具体案例→8-10, 不同品类但同行业→5-7, 全新品类逻辑清晰→2-4, 史无前例→0-1

**每个维度的打分必须引用事件语料中的具体文本作为依据。**

---

## 第四步: 模型选择

### 4a. 阅读代码约束清单

用户消息末尾有"代码约束清单"——代码已分析财务数据，标注了每个模型的技术可行性观测。

**重要: 这是观测，不是闸门。** 代码说"K不可用(NOPAT<0.5)"并不意味着LLM必须排除K——它意味着如果LLM仍选K，必须在 routing_reason 中解释为什么这个约束在当前案例中不成立。

**你必须对代码标注的每个约束点做出回应:**
- 同意代码判断 → 无需额外说明
- 不同意代码判断 → 在 `code_constraints_discussion` 中记录你的理由

### 4b. 从全部模型中选择

按以下优先级:

**优先级1: 锚匹配。** 模型必须与你第二步识别的锚一致:
- earnings 锚 → A(ROIC-RR DCF) / K(两阶段DCF) / G(PEG) / I(盈利正常化)
- revenue 锚 → B(PS+TAM)
- asset 锚 → D(PB-ROE) / H(NAV)
- resource 锚 → E(EV/EBITDA+资源)
- pipeline 锚 → F(rNPV)
- 多锚冲突且不可调和 → J(SOTP)

**优先级2: 叙事契合度。** 模型的核心逻辑是否匹配市场在赌的东西？
- 市场在赌"市场空间×渗透率" → B比K更契合，即使公司当前盈利
- 市场在赌"ROIC持续改善+永续增长" → A比G更契合
- 市场在赌"高增长→稳态过渡"且终局可见 → K比A更契合
- 市场在赌"周期底部均值回归" → I比G更契合

**优先级3: 模型-数据兼容性。** 参考代码约束清单。模型需要的输入(ROIC/NOPAT/增速终局)是否能从当前数据中合理推导？

### 4c. SOTP 判定

**SOTP不是前置触发器——它是模型J被选中时的结果。** 选J的条件:

1. 公司有两个或以上业务，且它们需要的估值锚**不同**(PE vs PS vs PB vs rNPV)
2. 混在一起用单一模型估值会产生**系统性偏差**(老业务基数大+增速低，新业务基数小+增速高 → 把老业务的低速收入也赋予新业务的高倍数)
3. 新业务有**可独立估值的锚点**(已产生收入/有订单或产能/有可比公司参照)

**注意: 不要机械套用阈值。** 老业务占比20%或40%不是硬性分界线——关键是"混在一起会不会产生系统性偏差"。如果你判断会 → 选J。

**当 primary_model=J 时（SOTP），各分部锚的判定规则**:

`primary_anchor` 字段填 `sotp`（表示整体方法论）。各分部锚按以下规则独立判定:

**事件驱动的分部** (`event_driven_segment`):
事件改变了这个分部的什么 → 锚就落在那个维度。
- 事件改变TAM/市占率/收入天花板 → anchor = revenue, 模型 = B
- 事件改变利润率/成本结构/盈利能力 → anchor = earnings, 模型 = A/K/G
- 事件改变资产价值/NAV → anchor = asset, 模型 = D/H
将该分部信息写入 `event_driven_segment`: {segment, anchor}

**其他分部**: 不由事件直接驱动，按其自身业务特征独立判定:
- 有利润+可比PE对标 → earnings锚
- 无利润+收入高增长 → revenue锚
- 有利润但被周期压制 → earnings锚(正常化利润)
- 重资产+可比PB → asset锚

`sotp_primary_segment_model` 填入事件驱动分部的模型（B/A/K等），作为SOTP管线LLM-1的起点提示。

### 4d. G(PEG) 的使用约束

G(PEG) 是成长股的估值范式——用增速锚定PE。它有两个隐含前提:

1. **增长驱动必须是结构性的，不是周期性的:**
   - ✅ 结构性: 新产品/新市场/市占率提升/技术突破 → 增速可持续
   - ❌ 周期性: 周期底部低基数 → 增速不可持续。当前TTM利润远低于过去3年中枢(<50%)且增速主要来自利润恢复而非新业务驱动时，G不适用 → 应选I(盈利正常化)

2. **行业估值范式匹配:**
   - 周期行业(煤炭/有色/钢铁/化工)默认范式是EV/EBITDA或盈利正常化——利润波动源于价格周期
   - 资源行业(矿业/石油)默认范式是EV/EBITDA或NAV——价值在资源储量和价格
   - 金融行业(银行/保险)默认范式是PB-ROE——盈利增速受资本约束
   - 但如果公司确有**结构性转型**(新产品/新市场改变了行业属性)，G仍然可用

### 4e. 选择校验模型

校验模型的核心目的是用另一个视角交叉验证主模型的估值区间。

**策略受事件分布形状影响:**
- wide_bimodal / wide_bimodal_date_anchored → 同类保守校验（高二元性，极端值敏感）
- wide_unimodal / narrow_concentrated / narrow_base_dominant → 跨族校验（不同视角有参照价值）

**校验模型也必须通过代码约束清单的合理性检查。** 如果所有候选都有重大约束问题，标注"同模型自校验"并降级说明。

### 4f. routing_reason 要求

≥80字，必须引用: (1)第二步的锚判断依据 (2)具体财务数据 (3)事件光谱。说明为什么这个模型最适合当前叙事方向。

---

## 第五步: 计价判断

### 5a. 量化参照

用户消息中的"定量定价工具"表格给出了当前市值在每种锚下隐含的预期。把"隐含预期"和"事件叙事指向的预期"对比:

- 隐含增速 45% vs 行业合理增速 15-20% → 市场已经充分定价甚至过度定价
- 隐含增速 8% vs 事件指向 15%+ → 事件未充分计价，还有上行空间

### 5b. 定性因子

考虑(如用户消息中有相关信息):
- 事件窗口价格走势(event_window_prices)
- 行业联动程度
- 分析师预期变化

### 5c. 综合判定

- **not_priced**: 突发事件，股价未反应
- **partially**: 部分定价，剩余取决于执行
- **fully**: 全部反映，上行空间有限
- **unknown**: 数据不足

同时填写 `priced_in_estimate`: 一个定量的百分比估计，如"约30-40%"、"约60-70%"。来自你对隐含预期(5a)与事件指向预期的差距的量化估计。

---

## 第六步: 信号审核(轻量级)

从前瞻信号面板提取关键信号，与叙事方向对比:
- 如果关键信号同向支撑叙事 → 标注支撑项
- 如果关键信号与叙事方向矛盾 → 标注矛盾项
- 给出 0-10 的匹配度评分

信号审核是轻量级的——重点是指出明显的支撑或矛盾，不需要逐条穷举。

---

## 模型目录(精简版)

| 模型 | 锚类型 | 一句话描述 | 典型场景 |
|------|--------|-----------|---------|
| **A** | earnings | ROIC-RR DCF: ROIC驱动再投资率→永续增长 | 成熟期、ROIC>WACC、稳态盈利 |
| **K** | earnings | 两阶段DCF: 高增长→终值PE | 成长型、终局可见、NOPAT可支撑DCF |
| **G** | earnings | PEG: 增速锚定PE | 结构性高增长(新产品/新市场驱动) |
| **I** | earnings | 盈利正常化: 周期中值利润替代TTM | 周期股(化工/航运/养殖) |
| **B** | revenue | PS+TAM: 收入×PS | 亏损/微利、收入高增长、TAM扩张 |
| **D** | asset | PB-ROE: ROE改善→PB扩张 | 重资产+ROE改善逻辑 |
| **H** | asset | NAV: 资产重估 | 隐蔽资产、投资性房地产 |
| **E** | resource | EV/EBITDA+资源: 储量价值 | 矿业/油气、不可复制资源 |
| **F** | pipeline | rNPV: 概率加权现金流折现 | 创新药/biotech、管线驱动 |
| **J** | sotp | SOTP: 分部独立估值后加总 | 多业务不同锚、混估产生系统性偏差 |

---

# 输出格式

```json
{
  "market_narrative": {
    "core_bet": "一句话: 市场在押注什么",
    "narrative_lifecycle": "导入期 | 成长期 | 成熟期 | 转型期",
    "primary_anchor": "earnings | revenue | asset | pipeline | sotp",
    "primary_anchor_evidence": "双向证据: (1)叙事线索 (2)定价工具数据。≥60字",
    "anchor_conflict": "如有矛盾解释原因; 无矛盾留空字符串",
    "narrative_summary": "完整叙事总结: 公司在讲什么故事、为什么对应这个锚、行业在讲类似故事吗。≥80字",
    "secondary_anchors": "[当存在与主锚不同的分部时填写。数组: {segment, anchor, revenue_share_pct, data_confidence}。无副锚时为空数组[]",
    "anchor_shift_potential": {
      "shift_possible": "true/false — 事件是否可能让市场换一种方式估值？",
      "shift_timing": "已发生/进行中/尚未开始",
      "from_anchor": "当前锚",
      "to_anchor": "可能切换到的锚"
    }
  },
  "event_profile": {
    "distribution_shape": "wide_unimodal | wide_bimodal | wide_bimodal_date_anchored | narrow_concentrated | narrow_base_dominant",
    "shape_rationale": "维度打分→分布形状的推导",
    "timing_certainty": 5,
    "timing_rationale": "引用事件语料依据",
    "outcome_binaryness": 2,
    "outcome_rationale": "引用事件语料依据",
    "precedent_richness": 8,
    "precedent_rationale": "引用事件语料依据"
  },
  "routing_decision": {
    "primary_model": "A-K单字母",
    "model_category": "Earnings Multiples | Revenue Multiples | Asset/Resource | rNPV | SOTP",
    "routing_reason": "引用: (1)锚判断依据 (2)具体财务数据 (3)事件光谱。≥80字",
    "validation_models": ["A"],
    "validation_rationale": "说明校验策略和校验模型的选择理由",
    "validation_strategy": "cross_family | conservative_same_family | self_validation",
    "code_constraints_discussion": ["对代码约束清单中不同意之处的回应。如全部同意，写'全部同意'"],
    "sotp_primary_segment_model": "仅当primary_model=J时填写，如B/A/K",
    "event_driven_segment": "仅当primary_model=J时填写。格式: {segment, anchor}。仅有一个分部被事件催动时填写。若事件催动所有分部则为空对象{}",
    "anchor_shift_warning": "如有范式切换风险，标注在此; 无则留空"
  },
  "pricing_assessment": {
    "overall_priced_in": "not_priced | partially | fully | unknown",
    "priced_in_rationale": "定量参照+定性因子→综合判断。≥60字",
    "priced_in_estimate": "约XX-YY% — 对已计价比例的量化估计",
    "residual_catalyst": "剩余未定价的催化因素"
  },
  "signal_audit": {
    "key_supporting_signals": ["信号1: 描述"],
    "key_conflicting_signals": ["信号1: 描述"],
    "match_score": 6,
    "score_rationale": "评分理由(1-2句)"
  }
}
```

# 核心约束

1. **推理链不可跳步。** 先锚→再事件→后模型。不允许先有模型偏好再反推锚。
2. **叙事驱动指标。** 锚识别从叙事出发，估值数据用于验证而非替代叙事判断。
3. **代码约束清单是观测不是闸门。** 你可以不同意代码的判断——但必须给出理由。
4. **SOTP是模型选择的结果。** 选J的条件是"混在一起会产生系统性偏差"，不是机械套用阈值。
5. **输出纯 JSON。**
"""


# ═══════════════════════════════════════
# 模型目录
# ═══════════════════════════════════════

MODELS_BY_ANCHOR = {
    "earnings":    ["A", "K", "G", "I"],
    "revenue":     ["B"],
    "asset":       ["D", "H"],
    "resource":    ["E"],
    "pipeline":    ["F"],
    "sotp":        ["J"],
}

MODEL_NAMES = {
    "A": "ROIC-RR DCF",
    "K": "两阶段DCF",
    "G": "PEG",
    "I": "盈利正常化",
    "B": "PS+TAM",
    "D": "PB-ROE",
    "H": "NAV",
    "E": "EV/EBITDA+资源",
    "F": "rNPV",
    "J": "SOTP",
}

MODEL_CATEGORIES = {
    "A": "Earnings Multiples", "K": "Earnings Multiples",
    "G": "Earnings Multiples", "I": "Earnings Multiples",
    "B": "Revenue Multiples",
    "D": "Asset/Resource", "H": "Asset/Resource",
    "E": "Asset/Resource",
    "F": "rNPV",
    "J": "SOTP",
}


# ═══════════════════════════════════════
# 代码约束清单 —— 观测，不是闸门
# ═══════════════════════════════════════

def compute_model_advisories(financials: dict) -> dict:
    """
    分析财务数据，为每个模型生成"技术可行性观测"。

    核心原则: 代码提供观测和数据事实，LLM 做最终判断。
    每个模型的输出是 "concerns" 列表——LLM 可以选择无视，但必须在
    code_constraints_discussion 中解释。

    不在代码中说"不可用"(gate)，只说"注意"(note)。
    """
    roic = financials.get("roic_pct", 0)
    np = financials.get("net_profit_ttm_yi", 0)
    nopat = financials.get("nopat_yi", 0)
    mcap = financials.get("market_cap_yi", 100)
    rev = financials.get("revenue_ttm_yi", 0)
    equity = financials.get("total_equity_yi", 1)
    assets = financials.get("total_assets_yi", 0)
    cash = financials.get("cash_yi", 0)
    debt = financials.get("interest_bearing_debt_yi", 0)
    pe = financials.get("pe_ttm", 0)
    pb = financials.get("pb", 0)
    ps = financials.get("ps_ttm", 0)
    gm = financials.get("gross_margin_pct", 0)
    industry = financials.get("industry_sw_l1", "")
    rev_growth = financials.get("revenue_growth_3y", 0)

    nopat_ratio = nopat / max(mcap, 1) if nopat > 0 else 0
    asset_ratio = assets / max(equity, 1)

    advisories = {}

    # ── A (ROIC-RR DCF) ──
    a_notes = []
    if roic < 8:
        a_notes.append(f"ROIC={roic:.1f}% < 8%。A需要ROIC>8%作为再投资率基准。"
                       f"如果事件能将ROIC推至>8%且有明确时序，A仍可考虑——请在routing_reason中说明改善路径。")
    if np <= 0:
        a_notes.append(f"净利润={np:.2f}亿 ≤ 0。A需要正利润做DCF起点。如果亏损但有明确的扭亏路径，选C或B可能更合适。")
    advisories["A"] = {"notes": a_notes}

    # ── K (两阶段DCF) ──
    k_notes = []
    if nopat <= 0:
        k_notes.append(f"NOPAT≤0，无法计算DCF起点。K在NOPAT为负时本质上退化为纯终值赌注——请谨慎。")
    elif nopat < 0.5:
        k_notes.append(f"NOPAT={nopat:.2f}亿 < 0.5亿。DCF阶段1的FCFF≈0(RR封顶0.9)，"
                       f"估值严重依赖终值——如果终局PE判断失误，误差会很大。")
    if nopat_ratio > 0 and nopat_ratio < 0.008:
        k_notes.append(f"NOPAT/市值={nopat_ratio*100:.2f}% < 0.8%。NOPAT相对市值过低，"
                       f"DCF终值占比可能>90%——注意终值折现杀穿风险。")
    advisories["K"] = {"notes": k_notes}

    # ── G (PEG) ──
    g_notes = []
    if np <= 0:
        g_notes.append("净利润≤0，PEG公式的P/E分母不存在。G不适用。")
    if rev_growth > 0 and rev_growth < 30:
        g_notes.append(f"营收增速={rev_growth:.0f}% < 30%。PEG要求高增速才有意义，"
                       f"低增速下PEG锚定的PE会很脆弱。")
    # 周期行业提示
    cyclical = ["煤炭", "有色金属", "钢铁", "化工", "石油石化", "基础化工"]
    if any(c in industry for c in cyclical):
        g_notes.append(f"行业={industry}属于周期行业。G(PEG)是成长股范式——"
                       f"如果增速来自周期底部低基数而非结构性增长(新产品/新市场)，G不适用。"
                       f"请检查: 投资主题中是否有明确的结构性转型证据(新产品线/新市场准入/技术突破)?")
    advisories["G"] = {"notes": g_notes}

    # ── I (盈利正常化) ──
    i_notes = []
    if np > 0 and roic > 15:
        i_notes.append(f"ROIC={roic:.1f}% > 15%，公司盈利能力强劲。"
                       f"I假设利润波动是周期性的——当前高ROIC可能意味着公司处于周期顶部而非需要正常化。")
    advisories["I"] = {"notes": i_notes}

    # ── B (PS+TAM) ──
    b_notes = []
    if np > 0 and roic > 8:
        b_notes.append(f"公司当前盈利(净利润={np:.2f}亿, ROIC={roic:.1f}%)。"
                       f"B(PS+TAM)通常用于亏损/微利企业。如果投资主题明确指向新业务的收入/TAM而非旧业务利润，B仍可考虑——"
                       f"但需确认: (1)投资主题是否聚焦新业务收入 (2)PS是否处于历史高位表明市场确实在定价收入。")
    if ps <= 0:
        b_notes.append("PS≤0，收入锚指标无效。")
    advisories["B"] = {"notes": b_notes}

    # ── D (PB-ROE) ──
    d_notes = []
    if asset_ratio < 1.5:
        d_notes.append(f"总资产/净资产={asset_ratio:.1f}x < 1.5x。D适用于重资产公司。"
                       f"轻资产公司用PB-ROE框架的有效性有限。")
    if pb <= 0:
        d_notes.append("PB≤0，净资产为负，PB-ROE框架不适用。")
    advisories["D"] = {"notes": d_notes}

    # ── H (NAV) ──
    h_notes = []
    if cash < equity * 0.3:
        h_notes.append(f"现金={cash:.1f}亿 / 净资产={equity:.1f}亿 = {cash/max(equity,1)*100:.0f}% < 30%。"
                       f"H(NAV)通常适用于有大量可重估资产的公司。当前现金占比不高——需确认公司是否有其他隐蔽资产"
                       f"(投资性房地产/股权/无形资产)支持NAV逻辑。")
    advisories["H"] = {"notes": h_notes}

    # ── E (EV/EBITDA+资源) ──
    e_notes = []
    resource_keywords = ["矿", "煤", "油", "气", "有色", "稀土", "锂", "钴", "镍", "铜", "金", "银", "铁", "钢"]
    if not any(kw in industry for kw in resource_keywords):
        e_notes.append(f"行业={industry}未识别为资源型行业。E(EV/EBITDA+资源)的核心前提是"
                       f"公司价值主要由不可复制的自然资源驱动。如果公司虽在资源行业但投资主题指向新产品/新技术而非资源本身，"
                       f"锚可能是revenue或earnings而非resource。")
    if gm > 0 and gm < 15:
        e_notes.append(f"毛利率={gm:.1f}%偏低。资源型公司通常有较高的资源禀赋溢价——"
                       f"低毛利率可能意味着公司是加工商而非资源拥有者。")
    advisories["E"] = {"notes": e_notes}

    # ── F (rNPV) ──
    f_notes = []
    biotech = ["医药", "生物"]
    if not any(b in industry for b in biotech):
        f_notes.append(f"行业={industry}通常不适用rNPV。F(rNPV)专用于创新药/biotech管线估值。"
                       f'注意: 科技/硬件的"产品管线"概念≠F的管线——F要求POS(成功率)×峰值销售×折现框架，'
                       f"需要临床数据/靶点/适应症等医药专业数据。")
    advisories["F"] = {"notes": f_notes}

    # ── J (SOTP) ──
    j_notes = []
    # 从 product_mix 提取分部信息
    fwd = financials.get("_forward_looking", {})
    cats = fwd.get("categories", {}) if isinstance(fwd, dict) else {}
    ea = cats.get("earnings_elasticity", {}) if isinstance(cats, dict) else {}
    product_mix = ea.get("product_mix", []) if isinstance(ea, dict) else []
    if not product_mix:
        j_notes.append("产品结构(product_mix)数据不可用——无法判断分部经济学分化程度。"
                       '在无分部数据时强行SOTP是"猜两次而非算两次"。建议先选主锚对应的单模型，'
                       "用 anchor_shift_warning 标注远期范式切换潜力。")
    elif len(product_mix) == 1:
        j_notes.append(f"只有一个产品线({product_mix[0].get('name','?')})——本质是单一业务，SOTP加总与整体估值差异<5%。"
                       f"建议用主锚单模型+参数区分档次。")
    else:
        # 有≥2个产品——分析分化程度
        segs = []
        for p in product_mix:
            segs.append({
                "name": p.get("name", "?"),
                "share": p.get("revenue_share_pct", 0),
                "gm": p.get("gross_margin_pct", 0),
                "growth": p.get("yoy_revenue_growth_pct", 0),
            })
        # 检查是否有显著分化
        if len(segs) >= 2:
            max_gm = max(s.get("gm", 0) for s in segs)
            min_gm = min(s.get("gm", 0) for s in segs)
            max_growth = max(s.get("growth", 0) for s in segs)
            min_growth = min(s.get("growth", 0) for s in segs)
            gm_gap = max_gm - min_gm
            growth_gap = max_growth - min_growth
            if gm_gap > 20 or growth_gap > 30:
                j_notes.append(f"产品间存在显著分化: 毛利率差距{gm_gap:.0f}pp, 增速差距{growth_gap:.0f}pp。"
                               f"分部详情: {json.dumps(segs, ensure_ascii=False)}。"
                               f"如果这些分部需要用不同估值锚(PE vs PS vs PB)，选J(SOTP)是合理的。"
                               f"如果都用同一锚(如都看PE)，赋不同参数即可，不需SOTP。")
            else:
                j_notes.append(f"产品间分化程度有限: 毛利率差距{gm_gap:.0f}pp, 增速差距{growth_gap:.0f}pp。"
                               f"分部详情: {json.dumps(segs, ensure_ascii=False)}。"
                               f"用单一模型+区分参数可能比SOTP更可靠——SOTP的额外拆分误差不值得。")
    advisories["J"] = {"notes": j_notes}

    return advisories


def format_advisories_for_prompt(advisories: dict) -> str:
    """将代码约束清单格式化为 LLM 可读的文本。"""
    lines = ["## 代码约束清单 — 各模型的技术可行性观测",
             "",
             "> **重要: 以下不是闸门，是观测。** 代码根据财务数据标注了每个模型的注意点。",
             "> 你可以在 routing_reason 中解释为什么某个注意点不适用——但必须回应。",
             "> 在 code_constraints_discussion 中记录你不同意代码判断的地方。",
             ""]

    for model in ["A", "K", "G", "I", "B", "D", "H", "E", "F", "J"]:
        adv = advisories.get(model, {})
        notes = adv.get("notes", [])
        name = MODEL_NAMES.get(model, model)
        if notes:
            lines.append(f"### {model} ({name})")
            for note in notes:
                lines.append(f"- ⚠ {note}")
        else:
            lines.append(f"### {model} ({name})")
            lines.append("- ✅ 财务数据未发现明显约束")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════
# 用户消息构建
# ═══════════════════════════════════════

def _build_volc_section(volc_data: dict | None) -> str:
    """构建火山搜索段落。"""
    if not volc_data:
        return ""
    text = volc_data.get("volc_text", "")
    if not text:
        return ""
    return f"""
## 火山联网搜索 — 券商视角（分部拆分+可比估值+产品级数据）

{text}

> 以上数据来自券商研报和公司公告。在判断锚类型和SOTP时，优先参照券商对业务线的拆分方式和可比公司使用的估值锚。
"""


def build_unified_user_message(
    data_package: dict,
    event_data: dict,
    pricing_all: dict,
    volc_data: dict | None = None,
    baseline_report: str | None = None,
) -> str:
    """
    构建 Agent-2 V8 统一用户消息。

    结构（严格按推理链顺序）:
    1. 投资地图
    2. 估值倍数全矩阵
    3. 定量定价工具
    4. 事件语料
    5. 前瞻信号面板
    6. 代码约束清单
    """
    core = data_package.get("packages", {}).get("core", {}).get("fields", {})
    stock = core.get("stock_name", data_package.get("stock_name", ""))
    code = data_package.get("stock_code", "")

    # ── 估值倍数全矩阵 ──
    pe = core.get("pe_ttm", 0)
    pe_rank = core.get("pe_historical_rank", "?")
    pb = core.get("pb", 0)
    pb_rank = core.get("pb_historical_rank", "?")
    ps = core.get("ps_ttm", 0)
    ps_rank = core.get("ps_historical_rank", "?")
    roic = core.get("roic_pct", 0)
    np = core.get("net_profit_ttm_yi", 0)
    rev = core.get("revenue_ttm_yi", 0)
    equity = core.get("total_equity_yi", 0)
    mcap = core.get("market_cap_yi", 0)
    gm = core.get("gross_margin_pct", 0)
    nm = core.get("net_margin_pct", 0)

    # ── 事件窗口价格 ──
    ew = data_package.get("event_window_prices", {}) or {}
    ew_text = ""
    if ew and ew.get("source") not in ("none", None):
        pre = ew.get("pre_event") or {}
        post = ew.get("post_event") or {}
        evd = ew.get("event_day") or {}
        cur = ew.get("current") or {}
        ew_text = f"""
## 事件窗口价格 ({ew.get('source','?')})
| 窗口 | 均价 | 区间 | 交易日数 |
|------|------|------|---------|
| 事件前 | {pre.get('avg_close','?')} | {pre.get('first_date','?')}~{pre.get('last_date','?')} | {pre.get('num_days','?')} |
| 事件日 | {evd.get('close','?')} | — | 1 |
| 事件后 | {post.get('avg_close','?')} | {post.get('first_date','?')}~{post.get('last_date','?')} | {post.get('num_days','?')} |
| 最新 | {cur.get('close','?')} ({cur.get('date','?')}) | — | — |"""

    # ── 投资地图 ──
    bs = ""
    if baseline_report and len(baseline_report) > 100:
        bs = f"""
# 一、投资地图 — 事件冲击前的企业全貌

{baseline_report}

---
"""

    # ── 代码约束清单 ──
    advisories = compute_model_advisories(core)
    advisories_text = format_advisories_for_prompt(advisories)

    msg = f"""# 路由判决: {stock}({code})

{bs}

# 二、估值倍数全矩阵
| 倍数 | 当前值 | 历史分位(0=最高,100=最低) | 含义 |
|------|--------|--------------------------|------|
| PE(TTM) | {pe:.1f}x | {pe_rank} | {'PE无意义(亏损)' if np <= 0 else '市场对利润的定价'} |
| PB | {pb:.1f}x | {pb_rank} | 市场对净资产的定价 |
| PS(TTM) | {ps:.1f}x | {ps_rank} | 市场对收入的定价 |
| EV/EBITDA | {core.get('ev_ebitda', '?')} | — | 市场对经营利润的定价 |

- 市值: {mcap:.0f}亿 | 营收TTM: {rev:.1f}亿 | 净利润: {np:.1f}亿
- ROIC: {roic:.1f}% | 毛利率: {gm:.1f}% | 净利率: {nm:.1f}%
- 净资产: {equity:.0f}亿 | 总资产: {core.get('total_assets_yi',0):.0f}亿
- 有息负债: {core.get('interest_bearing_debt_yi',0):.1f}亿 | 现金: {core.get('cash_yi',0):.1f}亿
- 行业: {core.get('industry_sw_l1','?')} / {core.get('industry_sw_l2','?')}
- 异常标记: {json.dumps(core.get('caution_flags',[]), ensure_ascii=False)}

## 历史分位解读
0=历史最高位(从未更贵), 50=中位, 100=历史最低位(从未更便宜)
- PE分位={pe_rank}: {'PE处于历史高位' if isinstance(pe_rank, (int,float)) and pe_rank < 20 else 'PE处于历史中低位'}
- PB分位={pb_rank}: {'PB处于历史高位' if isinstance(pb_rank, (int,float)) and pb_rank < 20 else 'PB处于历史中低位'}
- PS分位={ps_rank}: {'PS处于历史高位,收入锚显著' if isinstance(ps_rank, (int,float)) and ps_rank < 20 else 'PS处于历史中低位'}

{ew_text}

# 三、定量定价工具 — 三个锚各自反推: 当前市值在定价什么？

**用途**: 这是锚判断最关键的定量证据。对比三个锚的隐含预期——哪个锚下市场隐含的最离谱，哪个就是市场在用的锚。

| 锚 | 工具 | 适用 | 当前市值隐含什么？ |
|----|------|:--:|------|
| **earnings** | {pricing_all.get('earnings',{}).get('method','?')} | {pricing_all.get('earnings',{}).get('applicable',False)} | {pricing_all.get('earnings',{}).get('implied_metric','?')} = **{pricing_all.get('earnings',{}).get('implied_value','?')}** |
| **revenue** | {pricing_all.get('revenue',{}).get('method','?')} | {pricing_all.get('revenue',{}).get('applicable',False)} | {pricing_all.get('revenue',{}).get('implied_metric','?')} = **{pricing_all.get('revenue',{}).get('implied_value','?')}** |
| **asset** | {pricing_all.get('asset',{}).get('method','?')} | {pricing_all.get('asset',{}).get('applicable',False)} | {pricing_all.get('asset',{}).get('implied_metric','?')} = **{pricing_all.get('asset',{}).get('implied_value','?')}** |

**解读指南**:
- 三个都离谱 → 公司在周期极端位置，利润/收入/资产指标都失真
- earnings离谱但revenue合理 → 市场在定价收入，不是利润
- asset离谱但earnings合理 → 市场在定价资产重估
- 哪个最离谱 ≠ 哪个错误 —— 它指向市场在交易的方向

# 四、事件语料 — 事件对公司的增量影响

## 原始事件
{event_data.get('raw_event_text','')}

## 事件推演 (传导链→关键发现→脆弱性与证伪→市场共识对照→瓶颈节点)
{event_data.get('event_deduction','')}

## 逆向推演 (各假设存活强度+降级条件+击穿信号组合)
{event_data.get('adversarial_thinking','')}

## 催化日历 (P0/P1/P2优先级+证实/证伪条件+日历风险提示)
{event_data.get('future','')}

## 预研推理
响应等级: L{event_data.get('response_level','?')}
{event_data.get('preliminary_reasoning','')}

{_build_volc_section(volc_data)}

# 五、前瞻信号面板

{build_forward_signal_panel(core)}

# 六、{advisories_text}

---
请严格按推理链顺序执行: 第一步理解公司→第二步识别估值锚→第三步事件光谱→第四步模型选择→第五步计价判断→第六步信号审核。
先读投资地图和事件语料理解公司，再读定价工具表格判断锚，再分析事件光谱，最后选模型。
输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# Agent-2 V8 主类
# ═══════════════════════════════════════

class UnifiedRouteJudge:
    """统一路由判官 — V8。"""

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key

    def run(
        self,
        data_package: dict,
        event_data: dict | None = None,
        wacc_params: dict | None = None,
        volc_data: dict | None = None,
        baseline_report: str | None = None,
    ) -> dict:
        """
        执行统一路由判决。

        data_package: Agent-1 输出
        event_data: Coze Agent0 事件数据
        wacc_params: WACC 预计算参数
        volc_data: 火山联网搜索数据
        baseline_report: Agent-Baseline 投资地图报告

        返回: 包含 market_narrative, event_profile, routing_decision,
              pricing_assessment, signal_audit 的完整 dict
        """
        event_data = event_data or {}
        core = data_package.get("packages", {}).get("core", {}).get("fields", {})

        # ── 预计算: 定价工具(三个锚) ──
        pricing_all = {}
        for a in ("earnings", "revenue", "asset"):
            pricing_all[a] = compute_pricing_anchor(a, core, wacc_params)

        # ── 预计算: 代码约束清单 ──
        advisories = compute_model_advisories(core)

        # ── 构建用户消息 ──
        user_msg = build_unified_user_message(
            data_package, event_data, pricing_all,
            volc_data=volc_data,
            baseline_report=baseline_report,
        )

        # ── LLM 调用 ──
        result = call_deepseek(
            ROUTE_JUDGE_V8_PROMPT, user_msg,
            temperature=0,
            api_key=self.api_key,
        )

        if "_parse_error" in result:
            # 重试一次
            result = call_deepseek(
                ROUTE_JUDGE_V8_PROMPT, user_msg,
                temperature=0,
                api_key=self.api_key,
            )

        if "_parse_error" in result:
            return self._fallback(core, pricing_all, advisories)

        # ── 注入代码计算值(LLM不能修改) ──
        result["_pricing_tool"] = pricing_all
        result["_model_advisories"] = advisories

        # ── 代码层后验证 ──
        result = self._post_validate(result, core)

        return result

    def _post_validate(self, result: dict, core: dict) -> dict:
        """
        代码层后验证——不是闸门，是安全网。

        只在 LLM 输出存在明显数学不可行时做修正（如 K 选为 NOPAT=0 的标的）。
        正常情况下不做改动。
        """
        rd = result.get("routing_decision", {})
        primary = rd.get("primary_model", "")

        # K 模型的 NOPAT 基础检查
        if primary == "K":
            nopat = core.get("nopat_yi", 0)
            mcap = core.get("market_cap_yi", 100)
            nopat_ratio = nopat / max(mcap, 1)

            if nopat < 0.5 and nopat_ratio < 0.008:
                # NOPAT 起点过低且 LLM 未在 code_constraints_discussion 中解释
                discussed = False
                for d in rd.get("code_constraints_discussion", []):
                    if "K" in str(d) and ("NOPAT" in str(d) or "nopat" in str(d)):
                        discussed = True
                        break

                if not discussed:
                    # LLM 未回应 K 的 NOPAT 约束——降级到 A 或 B
                    anchor = result.get("market_narrative", {}).get("primary_anchor", "earnings")
                    fallback = "B" if anchor == "revenue" else "A"
                    rd["_k_auto_downgraded"] = True
                    rd["_k_downgrade_reason"] = (
                        f"代码层安全网: NOPAT={nopat:.2f}亿/市值={mcap:.0f}亿="
                        f"{nopat_ratio*100:.2f}% < 0.8%，LLM未在code_constraints_discussion中"
                        f"回应此约束。自动降级至{fallback}。"
                    )
                    rd["primary_model"] = fallback
                    rd["model_category"] = (
                        "Revenue Multiples" if fallback == "B" else "Earnings Multiples"
                    )
                    rd["routing_reason"] = (
                        rd.get("routing_reason", "") +
                        f" [自动修正: K的NOPAT={nopat:.2f}亿过低且LLM未回应→回退{fallback}]"
                    )
                    result["routing_decision"] = rd

        return result

    @staticmethod
    def _fallback(core: dict, pricing_all: dict | None = None,
                  advisories: dict | None = None) -> dict:
        """LLM 不可用时的纯代码 fallback。"""
        np = core.get("net_profit_ttm_yi", 0)
        roic = core.get("roic_pct", 0)
        ps = core.get("ps_ttm", 0)
        nopat = core.get("nopat_yi", 0)
        mcap = core.get("market_cap_yi", 100)

        # 锚推断
        if np > 0 and roic > 8:
            anchor = "earnings"
            # earnings 锚内选模型
            if nopat > 0.5 and nopat / max(mcap, 1) > 0.008:
                primary = "K"
            elif roic > 15:
                primary = "G"
            else:
                primary = "A"
            category = "Earnings Multiples"
        elif ps > 3:
            anchor = "revenue"
            primary = "B"
            category = "Revenue Multiples"
        else:
            anchor = "asset"
            primary = "A"  # fallback to most generic
            category = "Asset/Resource"

        return {
            "market_narrative": {
                "core_bet": f"Fallback: LLM不可用,基于财务数据推断锚={anchor}",
                "narrative_lifecycle": "无法判断(LLM不可用)",
                "primary_anchor": anchor,
                "primary_anchor_evidence": f"Fallback: np={np:.1f}亿 roic={roic:.1f}% ps={ps:.1f}x",
                "anchor_conflict": "",
                "narrative_summary": f"LLM不可用,代码机械推断主锚={anchor}。叙事诊断+产业语境分析跳过。",
                "secondary_anchors": [],
                "anchor_shift_potential": {"shift_possible": False, "shift_timing": "", "from_anchor": "", "to_anchor": ""},
            },
            "event_profile": {
                "distribution_shape": "wide_unimodal",
                "shape_rationale": "LLM不可用,fallback使用默认中等分布",
                "timing_certainty": 5, "timing_rationale": "Fallback默认值",
                "outcome_binaryness": 5, "outcome_rationale": "Fallback默认值",
                "precedent_richness": 5, "precedent_rationale": "Fallback默认值",
            },
            "routing_decision": {
                "primary_model": primary,
                "model_category": category,
                "routing_reason": f"Fallback路由(LLM不可用)。锚={anchor}, 候选模型由代码规则筛选, 选定={primary}",
                "validation_models": ["A"] if primary != "A" else ["B"],
                "validation_rationale": "Fallback: LLM不可用,代码选通用校验模型",
                "validation_strategy": "cross_family",
                "code_constraints_discussion": ["LLM不可用,跳过约束讨论"],
                "sotp_primary_segment_model": "",
                "anchor_shift_warning": "",
            },
            "pricing_assessment": {
                "overall_priced_in": "unknown",
                "priced_in_rationale": "LLM不可用,无法判断计价程度",
                "priced_in_estimate": "无法判断(LLM不可用)",
                "residual_catalyst": "",
            },
            "signal_audit": {
                "key_supporting_signals": [],
                "key_conflicting_signals": [],
                "match_score": 0,
                "score_rationale": "LLM不可用,跳过信号审核",
            },
            "_pricing_tool": pricing_all,
            "_model_advisories": advisories,
            "_fallback": True,
        }


# ── 便捷函数 ──

def route_judge_v8(
    data_package: dict,
    event_data: dict | None = None,
    wacc_params: dict | None = None,
    volc_data: dict | None = None,
    baseline_report: str | None = None,
) -> dict:
    """便捷入口: 运行 V8 统一路由判决。"""
    judge = UnifiedRouteJudge()
    return judge.run(data_package, event_data, wacc_params, volc_data, baseline_report)
