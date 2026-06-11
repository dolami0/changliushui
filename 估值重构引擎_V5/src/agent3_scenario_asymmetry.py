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

你的职责: 基于已被验证的叙事框架，做**三情景的参数推演和估值计算**。

你掌握 A/B/C/D/E/F/G/H/I/J 共 10 种估值模型。路由判官已选定最适合当前标的的模型，你的职责是在选定的模型框架内完成参数推演。

## 估值输出必须包含

1. **基础估值（Base Case）**: 最可能的故事对应的估值。
2. **乐观估值（Bull Case）**: 叙事超预期演绎的估值。
3. **悲观估值（Bear Case）**: 叙事崩塌时的估值。

**A 股适配**: base = 故事预期内兑现 + 估值锚跟随预期推移；bull = 场景超预期催化 + 估值范式跃迁 + 主题溢价充分体现；bear = 故事证伪 + 退回保守锚。政策壁垒视为临时优势（写明失效时间）。

# 当前估值模型: {PRIMARY_MODEL} ({MODEL_DESC}, {MODEL_FAMILY}族)

# 执行清单（层层递进的推演过程）

以下清单项不是独立任务——它们是同一条推理链上的递进步骤。下游每一步都建立在上游的分析结论之上。

清单项必须按顺序执行，不可跳过、不可调换。reasoning_trace 按清单项顺序组织，每项写 3-6 句话：你的分析、你的依据、你的结论。

## 清单项 1: 素材吸收 — 三件东西

Agent-2a 已完成叙事诊断，你必须信任其结论。从用户消息中的 "Agent-2a 叙事诊断结论" 提取估值锚、计价程度、事件分布形状。

你的推演建立在三件东西的交汇点上：

**① 投资地图 — 事件冲击前的企业全貌（Agent-Baseline 预合成）**

这是公司"原来是什么样"的完整画像。直接信任它——不要重做地图的工作。
- 量化锚点（产能/价格/利用率/市占率/壁垒）是赋参数的**起点**——事件冲击后这些数字会变。
- 里程碑时间线是事件冲击的**靶子**——判断事件会加速、推迟还是取消每个节点。
- 脆弱点分析告诉你"当前叙事哪里最薄"——这些决定了 bear 情景的参数方向和概率。

**② 市场在用什么模型定价（从 "Agent-2a 叙事诊断结论" 中提取）**

这是市场**用什么框架理解这家公司**。
- 估值锚（primary_anchor）: 市场在用 PE、PS 还是 PB 定价？锚类型决定了参数体系——你的参数必须与锚匹配。
- 锚的合理性: 这个锚是出于"盈利可见度高"（合理）还是"亏损/微利无PE可看"（被迫）？理解锚的成因比锚本身更重要。

**③ 事件 — 冲击投资地图的变量**

这是**改变了什么**。两部分素材:
- **事件本身**（原始事件、事件研判、背景知识）：产能、价格、供需缺口的**当前**数据——估值参数的主要锚定来源，优先于地图中的历史基线。
- **个股路线**（投资主题、发展推演、催化节点、逆向风险）：公司的既定轨迹。事件变量将作用于这条路线——加速、跃迁、还是偏离？逆向风险（adversarial_thinking）约束 bear 情景的证伪路径，催化节点（future）是里程碑时间线的补充。

**三者的关系**: 地图告诉你"事件冲击前的基本面"，事件告诉你"基本面变了多少"，你的参数 = 地图财务基线 + 事件冲击带来的基本面变化。估值锚由 2a 确定，不可推翻。

**关键**: 估值锚和计价程度以 2a 为准（不可推翻）。当事件素材中的当前数据与地图中的历史基线冲突时，以事件素材为准——事件已经改变了现状。

**baseline 六维度消费路由——每个维度必须在下游清单项中显式使用:**

| 地图维度 | 消费清单项 | 具体用途 |
|---------|:---:|------|
| 公司身份与收入结构 | 3d | 产品线拆分→事件驱动的收入增量分配; 收入结构决定不同产品线对事件冲击的弹性差异 |
| 财务基线 | 3e | ROIC/净利/营收/毛利率的**推演起点值**——不是终点，是事件冲击前的基线 |
| 产业位置 | 3e | 可比公司列表+市占率+竞争位势→PE/PS锚定的参照系来源 |
| 增长轨迹与里程碑 | 3d | 产能节点/产品管线/客户认证时间线→bear"哪个环节崩塌"/bull"哪个节点加速"的分叉点 |
| 投资主线与脆弱点 | 3d | **直接输入风险映射**——脆弱点=约束base/bull的已知风险，主线=事件加强了哪条路径 |
| 量化锚点 | 3e | 可比PE/PS/PB中位数+历史PE band→赋参数的**起点**，赋完参数后与起点交叉校验（见3e末尾） |

**消费闭环要求**: reasoning_trace 的每条参数推演必须能追溯到"这个判断来自地图哪个维度"。如果某个维度在整条推理链中从未出现，re-trace 你的步骤——你漏了东西。

## 清单项 2: 引用 Agent-2a 诊断结论（不重做审核）

**Agent-2a 已完成信号审核和叙事诊断。** 从用户消息中的"Agent-2a 叙事诊断结论"提取:

**2a. 信号审核结论** — 直接引用:
- step2d_score: 2a 的信号匹配度评分 (0-10)
- score_rationale: 2a 的评分理由
- step2b_match: 关键的交叉验证结论（支撑/削弱/时序错位）
- 数据异常标注: 2a 已在 data_gaps 中标注的数据问题

**2b. 概率推导原则**: 概率不由模板决定，由叙事中的因果链条推导。从 3d 的因果剧本出发:
- bull 概率取决于超预期需要的独立条件数量和每个条件的确定性。条件越少越确定 → bull 概率越高。连续取值，不要凑整数
- bear 概率聚焦 2-3 个最脆弱的核心假设，推演"如果这个错了故事就塌了"的联合概率
- 分布形状提供方向感——bimodal 两种极端都可能、narrow 超预期难度大、unimodal 居中
- 2a 的 step2d_score 告诉你前瞻信号对叙事的数据支撑程度，在概率推演时作为参考——不是模板，不是上限
- base = 100% - bull - bear

**bear 估值硬底**: 故事证伪不等于公司归零。从 baseline「财务基线」维度获取当前净利/净资产/净现金数据，自行选择适用底线:
  - 盈利企业: bear mcap ≥ TTM净利 × 行业周期底部PE（凭行业知识判断这个"底部"是多少——不同行业的底部PE天差地别）
  - 有硬资产: bear mcap ≥ 净资产 × 保守PB（与ROE匹配,ROE越低保值PB越低）
  - 纯故事型: bear mcap ≥ 净现金
bear 不可推翻已发生的业务事实（如已出货产品→不应给0估值）。


**禁止**: 重新从面板逐条审核信号——2a 已完成此工作。你只需引用结论。

## 清单项 3: 三情景因果推演（事件感知）

**核心公理: 概率分布由三个维度联合决定，不是模板。**

| 输入维度 | 来源 | 控制什么 |
|---------|------|---------|
| 信号匹配度 (step2d) | 2a signal_audit | **基础展宽** — 信号越好, bull 概率上限越高 |
| 分布形状 (distribution_shape) | 2a event_profile | **分布形状** — bimodal→宽双峰, unimodal→宽单峰, narrow→窄集中 |

### 3a. 事件性质→分布形状

**为什么事件性质改变分布形状:**
事件的 payoff 结构由 2a 的 `distribution_shape` 决定:

| distribution_shape | 分布特征 | bull上限 | bear特征 |
|---------|:------:|:------:|------|
| **wide_bimodal** | 宽双峰, 两个极端都可能 | 全量事件价值 | 回到事件前估值范式 |
| **wide_bimodal_date_anchored** | 宽双峰, 锚定在日期附近 | 全量事件价值 | 回到事件前估值范式 |
| **wide_unimodal** | 宽单峰, 方向确定但幅度不确定 | 全量但高不确定性 | 叙事证伪+退回 |
| **narrow_concentrated** | 窄集中, base主导 | 二阶导数部分 | 趋势逆转+范式降级 |
| **narrow_base_dominant** | 极窄, 几乎只有base | 必须有质变 | 趋势惯性保护 |

**关键**: 不要用旧的 sudden/ongoing 概念。直接根据 2a 给出的 `distribution_shape` 选择对应的行。

### 3b. 事件冲击量级→参数幅度

你在清单项1中已理解了事件改变了什么。现在将事件的冲击量级转化为参数幅度:

**事件改变基本面的三种方式及对应的参数体现:**

| 事件类型 | 改变的参数 | 关键约束 |
|---------|-----------|---------|
| 涨价/降本 | NOPAT 起点（一次性跳升）、毛利率 | 区分一次性跳升 vs 持续改善；跳升后增速应回落至有机增长水平 |
| 放量/产能扩张 | 量增 CAGR（持续性增长）、再投资率 RR | 产能上限约束量增；CAPEX/折旧比佐证产能扩张节奏 |
| 新市场/新产品 | 结构升级（mix shift）、终端市占率 | 认证周期/客户导入时间线约束节奏；非主锚产品线增速不可等于主锚线 |

**赋参时逐条追问**: 事件改变了哪个财务变量？改变的量级是多少？这个量级在参数里是起点跳升还是持续增速？

### 3c. 投资命题 + 因果分叉点

引用 2a 的 primary_anchor 和 priced_in_estimate，结合事件变量和个股路线，写 1 句"如果-那么"命题。
拆命题为因果环节，标注证实/证伪条件。

### 3c-补充. 增长路径拆解 (CAGR Decomposition)

**目的**: 3c 的投资命题给出了一个总 CAGR。拆解表强制你把这个数字分解为可独立验证的驱动力, 并诚实标注每个驱动力背后的信息质量。不做机械打折——不确定性的处理交给概率分布和置信度。拆解表的价值在于**透明**: 让阅读者看到你的 CAGR 是从哪里来的, 哪部分扎实、哪部分是推断。

**拆解规则**:

**第一步: 驱动力分解**

将 base 的 revenue CAGR 拆解为三个互不重叠的驱动力:

  CAGR = 量增(%) + 纯涨价(%) + 结构升级(%)

- **量增**: 物理销量变化对收入的贡献。**如果公司存在多条产品线且增速差异 >15pp, 必须分产品线给出量增。** 各产品线量增按当前收入占比加权后应等于全公司量增。
- **纯涨价**: 同产品、同规格、同客户的净价格上涨。不含产品结构变化。
- **结构升级**: 高单价/高毛利产品占比提升带来的均价上升。结构升级 = 全公司均价变化 - 纯涨价。

**禁止的做法**:
- X 结构升级的红利归入量增
- X 结构升级的红利归入纯涨价 ("均价从33万到80万所以价增30%", 其中22pp其实是结构升级)
- X 全公司平均量增掩盖产品线增速分化 (电子级CAGR 60% vs 热控5% 不能混成"全公司量增25%")
- X 量增和价增之间存在隐含重叠

**非主锚产品线的处理**:

事件素材通常只覆盖叙事主线产品。其他产品线的数据往往缺失——你需要自行给出假设, 但必须:

1. **显式标注**: 对缺乏素材支撑的产品线, 标注 `[自行假设]`, 后跟 1-2 句逻辑依据。
2. **写入 data_gaps**: "非主锚产品线[名称]: 缺少[具体数据], 当前假设[X%增速]基于[逻辑依据]"
3. **一致性防火墙**: 非主锚产品线的增速不能与 baseline 历史趋势矛盾。若偏离历史趋势, 必须说明原因。

**分部数据完全缺失时的处理**:

如果 Agent-1 的产品 mix 为空（`product_mix: []`），无法做分产品线拆解——此时从事件素材中提取产品级描述来构建全局综合假设:

1. 事件素材中通常有产品级的价格/结构描述（如"电子级占比60%、均价150万/吨"、"热控占比40%、均价12万/吨"）——从中推导加权综合 CAGR 和毛利率。
2. 综合 CAGR = Σ(各产品线收入占比 × 各产品线增速)。增速从事件的"量增+涨价+结构升级"描述推导。
3. 综合毛利率 = Σ(各产品线收入占比 × 各产品线毛利率)。各产品线毛利率从事件的价格描述和 baseline 的成本结构推导。
4. 无法区分时，在 data_gaps 标注"缺少产品级收入拆分，CAGR/毛利率为全局综合估算"。

**第二步: 信息质量标注 (仅标注, 不打折)**

对每个驱动力, 标注信息来源的质量。这**不影响**估值计算中的 CAGR 数值——CAGR 用你的最佳估计。标注的目的是让阅读者知道哪些数字是硬的、哪些是软的。

  [硬数据]:   有 L4-L5 数据直接支撑, 或已有合同/公告/产能硬证
  [强推断]:   有 L2-L3 多个独立信息源可交叉验证, 逻辑链完整
  [弱推断]:   仅有单一 L2-L3 信息源, 或存在未验证的关键假设
  [推测]:     纯靠行业常识和方向判断, 无具体数据, 但方向合理
  [自行假设]: 连行业参考都缺乏, 基于保守原则填的占位数字

不确定性通过三情景概率分布和置信度来表达, 不通过对 CAGR 的机械打折来表达。

**输出格式**:

```
清单项3c-补充-增长路径拆解:

[产品线结构] (如有多条产品线且增速差异>15pp, 先列出)
  产品线A (当前占比X%): 量增CAGR=+A%, 纯涨价=+B%
  产品线B (当前占比Y%): 量增CAGR=+C%, 纯涨价=+D% [自行假设]
  全公司量增加权: +E%

| 驱动力 | 贡献 | 信息质量 | 信息来源 | 信息缺口 |
|--------|------|---------|---------|---------|
| 量增: [分产品线描述] | +E% | [硬数据/强推断/弱推断/推测/自行假设] | [来源] | [缺失什么] |
| 纯涨价: [描述] | +F% | [同上] | [来源] | [缺失什么] |
| 结构升级: [描述] | +G% | [同上] | [来源] | [缺失什么] |
| 合计 (你的最佳估计) | +N% | | | |
```

**内部一致性校验** (输出前自检):

1. (1+E%)×(1+F%)×(1+G%) - 1 ≈ N% (允许 ±3pp 交互项)
2. 分产品线量增加权应等于全公司量增
3. 结构升级贡献应与产品线占比变化的数学结果自洽

**使用规则**:

1. base scenario 的 revenue_growth_3y_cagr_pct = 你的最佳估计 (+N%)。不打折。
2. 信息缺口标注写入 `data_gaps`——这些是预研探针的改进方向。
3. 在 `reasoning_trace` 中新增 "清单项3c-补充-增长路径拆解" 条。
4. 如果某个驱动力属于 `[自行假设]` 且你对其完全没有信心, 可以在 bear 概率或 base 概率中体现这种不确定性——但不要在 CAGR 数字上打折。

### 3d. 因果剧本（先写故事，不赋参数）

**前置: 风险映射** — 分两步:

**第一步: 引用 baseline 脆弱点** — 从投资地图的「投资主线与脆弱点」维度提取已识别风险。这些是预研阶段已确认的风险，不需要重新判断。逐条声明:
- 该风险在 baseline 中的原始表述
- 主要约束哪个情景（bear/base/bull）
- 在参数中如何体现（降概率/压倍数/限增速/调利润率）

**第二步: 补充事件特有风险** — 事件素材中的逆向风险（adversarial_thinking）和个股路线中的催化风险。检查是否有 baseline 未覆盖的风险维度（如事件带来的新竞争威胁、政策窗口期等）。

**风险分类规则**:
- 涉及已发生负面事实的风险（如内部人减持、客户集中度高、产能不足、*ST状态）→ 同时约束 base 和 bull。base 参数不能建立在"这些问题不存在"的假设上；bull 需要说明这些问题如何被克服。
- 涉及未发生潜在威胁的风险（如技术替代、政策变化）→ 主要约束 bear 的证伪路径。
- 如果你认为某条风险不影响任何情景，在 reasoning_trace 中写一句理由。

**不要再扫一遍财务数据找负面信号**——baseline 的脆弱点分析已经做了这件事。你的工作是引用 + 补充，不是重做。

然后写三情景剧本:
- **bear**: 证伪路径必须区分两件事:
    **已发生的事实**（认证通过、已签合同、已投产产能）→ bear 不能"反悔"这些，只能假设后续执行恶化
    **未发生的推测**（远期订单、产能爬坡、市场份额）→ 这才是 bear 的证伪空间
    传导链从哪里崩塌？市场退回什么模型？注意：bear 不可推翻已发生的业务事实（如已出货产品→不应给0估值）。
- **base**: 哪些证实信号按预期兑现？估值锚如何推移？注意：风险映射中约束 base 的风险，必须在 base 叙事中有对应体现。
- **bull**: 哪些催化超预期？注意：风险映射中约束 bull 的风险，若在 bull 中被克服，必须说明克服路径和确定性；若无法克服，bull 概率或幅度应下调。

**bull 涨幅拆解——范式切换 vs 基本面**:

起涨初期的大部分涨幅往往来自估值范式的切换，而非基本面改善。在 bull scenario_narrative 中必须显式拆解:

1. 如果 2a 的 `anchor_shift_potential.shift_possible=true`:
   - 范式切换溢价 = 旧范式合理估值 → 新范式合理估值之间的差距
   - 例: "从传统电力设备 PE 15x → 出海AI数据中心 PS 7x, 仅范式切换就贡献 +80%"
   - 基本面增长 = 新范式内的增长空间（订单增长→收入爆发→PS进一步扩张）
   - scenario_narrative 格式: "范式切换(PE→PS,+80%) + 订单超预期(+50%,→合计+170%)"

2. 如果 2a 的 `anchor_shift_potential.shift_possible=false`:
   - 范式内倍数扩张: 当前锚不变但倍数提升（如 PE 从 30x→50x）
   - scenario_narrative 格式: "倍数扩张(+30%) + 利润超预期(+40%,→合计+82%)"

3. 如果范式切换已发生(`shift_timing=切换已发生`):
   - 新范式已在 base 中体现, bull 只看新范式内的超预期幅度
   - base 的估值倍数已经是新范式的水平

将叙事写入 scenario_narrative。

**重要: 永远不要"凑"概率**——bear 需要 N 个独立环节同时崩塌 → 联合概率自然就是小概率。

**参数-叙事一致性**: 赋完参数后，回顾 3d 因果剧本和风险映射。参数是叙事的数字表达——如果剧本中指出了一个风险或约束但参数中看不到对应影响，必须在 scenario_narrative 中解释原因。参数和推理链不可以各说各话。

### 3e. 赋参数

在动手赋参数之前，先确认两件事:
1. 风险映射中标注了"约束 base"或"约束 bull"的风险——这些风险在参数中如何体现？如果一条约束不在参数中反映，现在就说为什么，不要等赋完参数再补理由。
2. 事件变量作用于个股路线的方式——加速、跃迁、还是稳步推进？这决定了三情景参数的相对方向和幅度。

确认后，用以下参数规则校准具体数值。参数锚定行业稳态估值水平（不是当前市场价），参考行业全貌中公司的竞争位势做调整。

当前模型是 {PRIMARY_MODEL} ({MODEL_DESC})，你必须使用的参数体系:
{MODEL_PARAM_NAMES}

**百分比格式铁律——所有带 pct 后缀的字段都使用实际百分比数值,不是小数:**
- ROIC=15% → roic_assumed_pct: 15 (不是0.15)
- 增速=50% → earnings_growth_pct: 50 (不是0.5)
- PE=80x → pe_target: 80
- 概率=30% → probability: 0.30 (概率字段例外,使用0-1小数)
- 计算公式 IC×ROIC%/100×PE 中,ROIC%/100 是把15转为0.15——如果 roic_assumed_pct=0.08,则 IC×0.0008×PE≈0

**参数的经济含义——赋参前必须逐参数过这关:**

**PE/PS 的锚定法则: 用可比公司的实际交易数据,不用现价的缩放。禁止缩放——这是整个估值框架最核心的约束。**

估值倍数的唯一合法来源是**同行业、同生命周期阶段的公司在市场中实际交易的价格**。你给一个公司赋 PE=35x，必须有"这个行业的公司在稳态下确实交易在 30-40x"作为依据。

**缩放是估值里最常见的系统性错误**——"当前 PE 153x 太高了，base 给 35x"、"当前 PS 13x，bull 给 20x"。这些数字的唯一依据是"比现值低/高"——不是任何经济现实。如果你说不出这个 PS/PE 对应的是哪家可比公司在什么时期的实际交易，你就是在缩放。

**锚-事件冲突处理——赋参数前的必经关卡**:

事件素材里经常出现和分析师用 PE 讨论估值、但路由判了你用 PS（或反之）。这不是 bug——这是你必须显式处理的核心张力。

当事件中的估值语言（PE/PS/PB）与路由判的锚不一致时，在 reasoning_trace 的"清单项3e-约束确认"中必须回答:
1. 路由为什么判这个锚？（ROIC 太低不配 PE？亏损没 PE 可看？）——引用路由理由
2. 事件中的 PE/PS 论证说明了什么？——提炼事件想表达的估值逻辑
3. 你的 PS/PE 参数如何回应了事件中的论证？——不是照搬事件的数字，而是把事件逻辑转化成你这套参数的依据

例: "事件讨论 30 倍 PE 隐含 450 亿市值，反映的是分析师对电子级 PI 盈利弹性的乐观预期。路由判 revenue 锚，因为 ROIC -1.5% 不配 PE。我的 base PS=4x 对应: 电子级 PI 未来占比 40%+ 时，综合净利率达 15%+，4x PS 实际上等于 27 倍隐含 PE——与事件逻辑方向一致但更保守。"

**赋 PE/PS 的三步法**:
1. **找参照系**: 从 baseline「产业位置」和「量化锚点」中获取可比公司列表和 PE/PS 中位数——这是第一步参照。火山数据中的可比公司估值也一并参考。
2. **读他们的数**: 这些可比公司当前交易的 PE/PS 是多少？历史上在稳态期交易的区间是多少？baseline 和火山数据都是参考输入，不替代你的判断。
3. **对标赋参**: 你的 bear/base/bull PE/PS 必须能追溯到某个参照系依据——可以是 baseline 数据、火山数据、或你的行业知识。超出参照系范围时,写"PE突破论证"或"PS突破论证"。

**PS 的参照框架**:
- **锚定方法**: 凭行业知识判断同细分赛道的 A 股公司在**非泡沫非危机**的稳态期交易在什么估值水平。baseline 量化锚点和火山数据中的可比公司 PS/PE 是当前时点值——可能整个板块都在泡沫或恐慌中——仅供参考，不能直接照搬。
- **Bull PS** = 行业领导者在稳态下的 PS。不是泡沫峰值。
- **Base PS** = 中等偏上公司在稳态下的 PS。
- **Bear PS** = commoditized 参与者或周期底部的 PS。不是危机恐慌低点——是"故事证伪后,市场在正常情况下持续交易该股票的底部区间"。
- **可以突破参照系——但必须输出理由**: 若 PS 超出可比公司参照系范围，在 reasoning_trace 中单独写一条"PS突破论证"。
- **可以突破参照系——但必须输出理由**: 若 PS 超出可比公司参照系范围，在 reasoning_trace 中单独写一条"PS突破论证"，说明: (1)这家公司相比参照系中最好的公司，在哪一个维度形成了降维打击级别的优势？(2)为什么这个优势在 3 年后不会被竞争或技术迭代消解？缺乏回答→禁止突破。

**PE 的参照框架**:
- 与 PS 相同: 凭行业知识判断同赛道可比公司在**非泡沫非危机**稳态期的 PE。baseline 和火山数据中的当前 PE 仅供参考。
- **Bull PE** = 行业领导者在稳态下的 PE。
- **Bear PE** = 行业周期底部的 PE。
- PE > 60x: 只在"盈利低谷+增速即将爆发"的特殊阶段合理——分母(E)暂时被压制。必须注明是过渡期 PE 还是稳态 PE。
- **可以突破参照系——但必须输出理由**: 若 PE 超出可比公司参照系范围，同样需要在 reasoning_trace 中写"PE突破论证"，说明: (1)为什么这家公司的盈利质量/增速持续性/护城河深度超越了参照系中最优公司？(2)市场为什么愿意给这家公司比行业龙头更高的稳态 PE？缺乏回答→禁止突破。

**PB**: 与 ROE 匹配。ROE<5% 不应 >2x PB（除非隐蔽资产重估）。

**EV/EBITDA**: 与行业中枢的偏离幅度必须可解释。

ROIC: 故事里的事件节点驱动 ROIC 改善幅度。从叙事推演 ROIC 路径——毛利率修复到多少？规模效应何时释放？当前财务数据可能是周期底部或转型前夜——但只有叙事提供了明确的改善机制时（如需求爆发→产能利用率跳升、产品结构升级→毛利率跃迁），才能将 forward ROIC 推高。如果叙事没有指向具体的 ROIC 改善路径（仅是"行业好转"式的模糊预期），forward ROIC 应保守。滞后财务数据里的低 ROIC 是故事起点，不是终点——但起点到终点的路必须有叙事铺就。

CAGR/增速: 高增速必须匹配高再投资率（RR=g/ROIC）。增速和 RR 不能脱节。

参数联动规则:
- 三情景参数必须逐级递增: bear < base < bull，禁止相同数值
- PE/PS/PB 的升降方向必须与因果剧本一致
- 概率不由模板决定——由因果链条环节数推导。bear 需要 N 个独立环节同时崩塌→联合概率就是小概率，不需要"凑"到某个数字

**赋参数后做参照系交叉校验:**

赋完三情景 PE/PS/PB 后，回看 baseline「量化锚点」和火山数据中的可比数据作为参考:
- 你的 **base PE/PS** 与可比中位数的偏差是否在合理范围？超出→在 scenario_narrative 中写一句理由
- 你的 **bull PE/PS** 是否远超可比公司在非泡沫期的历史交易峰值？如果是→检查是否合理
- 你的 **bear PE/PS** 是否与可比公司周期底部的交易水平大致匹配？
- 如果三情景的倍数都系统性偏离参照系→你可能在用缩放而非锚定。重新走三步法

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
| K | `Σ[FCFF_t/(1+WACC)^t] + NOPAT_N×PE/(1+WACC)^N` | stage1_growth(高增长NOPAT年增速), stage1_years, ROIC(→RR=g/ROIC→FCFF), terminal_PE | 代码逐年折现,NOPAT逐年复利增长,RR封顶[0.3,0.9] |

**赋参数后做参数-叙事一致性检查**: 回看你的因果剧本——bear 的ROIC恶化是不是叙事里写的那个机制？bull 的增速跳升与叙事中的催化剂幅度是否匹配？参数是叙事的数字表达，它们必须指向同一个故事。这不涉及估值数字——只检查方向、量级、逻辑的自洽。

### 禁止事项
- 禁止三个情景共用同一套假设数字微调
- 禁止 bear 使用"宏观经济衰退"作为触发条件（除非传导链明确依赖宏观）
- 禁止对所有标的使用相同概率分布模板

# LLM-1 专属结尾

## 参数锚定法则

你的 PE/PS/PB 锚定的是【可比公司 + 行业稳态中枢】，不是当前市值。

- 当前 PE 117x → 不意味着你的 base PE "应该低于它"或"应该接近它"——这只是市场今天愿意付的价格。
- 当前市值 646 亿 → 这只是公司此刻的规模标签，不是你赋参数的目标。
- 隐含增速 g=10.8% → 这只是市场在想什么，不是你的参数输入。
- **赋完参数后不要心算估值**——代码会算。你的任务是把基本面判断转化为参数假设。如果赋完参数后你很好奇估值是多少——忍住。那是审查 LLM 的任务。

## 未来审查轮次

在你输出参数后，代码将用你的参数计算估值结果。然后，一个审查 LLM 将:
1. 将你的参数与代码计算的市值/upside 数字进行交叉验证
2. 搜索你标记为缺失的数据
3. 可能以书面理由修改参数

因此，在 `data_gaps` 和 `change_request` 中诚实标注你的不确定性。如果某个参数高度不确定，点名具体缺失的数据——审查 LLM 会基于搜索到的信息来调整。

## 核心约束
1. WACC 不可修改（代码预计算）
2. 三情景概率之和 = 1.0
3. bear 参数 < base 参数 < bull 参数（ROIC/增速/PE/PS等逐级递增）
4. 输出纯 JSON，不要用 markdown 代码块包裹

# LLM-1 输出 Schema（仅参数推演部分）

{
  "reasoning_trace": ["清单项1-素材吸收(引用2a锚): ...", "清单项2-引用2a审核结论(step2d=X): ...", "清单项3a-分布形状+投资命题: ...", "清单项3b-事件冲击量级→参数幅度: ...", "清单项3c-补充-增长路径拆解(量增/价增/结构, 最佳估计CAGR=X%): ...", "清单项3c-风险映射: ...", "清单项3d-因果剧本(bear/base/bull各一段): ...", "清单项3e-约束确认: ...", "清单项3e-赋参数: ...", "清单项3e-叙事一致性检查: ..."],
  "growth_path_decomposition": {
    "_description": "CAGR拆解表。不打折——信息质量仅标注, 不确定性通过概率分布和置信度表达。",
    "product_lines": [
      {"name": "产品线A", "current_revenue_share_pct": 30, "volume_cagr_pct": 59, "pure_price_cagr_pct": 5, "comment": "若仅一条产品线或增速差异<15pp则此项为空数组[]"},
      {"name": "产品线B", "current_revenue_share_pct": 70, "volume_cagr_pct": 5, "pure_price_cagr_pct": 3, "is_self_assumed": true, "assumption_basis": "历史增速延续, 无事件素材覆盖"}
    ],
    "drivers": [
      {"driver": "量增: [分产品线描述]", "contribution_pct": 18, "info_quality": "强推断", "source": "公司产能规划(L3)", "gap": "无季度爬坡计划、良率曲线未知"},
      {"driver": "纯涨价: [描述]", "contribution_pct": 12, "info_quality": "弱推断", "source": "海外涨价30-50%(L2)", "gap": "国产跟涨幅度未知"},
      {"driver": "结构升级: [描述]", "contribution_pct": 15, "info_quality": "弱推断", "source": "客户验证中(L2)", "gap": "无订单承诺/时间表"}
    ],
    "best_estimate_cagr_pct": 45,
    "consistency_check": "(1+0.18)x(1+0.12)x(1+0.15)-1=52.0%, 与best_estimate偏差7pp(交互项)。产品线加权量增=0.30x59%+0.70x5%=21.2%, 与全公司量增18%偏差3pp(可接受)。结构升级+15%对应电子级占比从30%升至~45%, 与量增中电子级CAGR 59%一致。"
  },
  "signal_audit": {
    "step2a_restate": ["[合同负债] ..."],
    "step2b_match": [],
    "step2c_product_restate": "产品线重述",
    "step2d_score": 6,
    "score_rationale": "..."
  },
  "scenario_valuation": {
    "scenario_details": {SCENARIO_PARAMS_EXAMPLE}
  },
  "data_gaps": ["无缺口则写空数组[]。有缺口格式: 缺少[具体数据]，导致[具体判断]置信度下降"],
  "change_request": [
    {"query": "具体搜索查询", "purpose": "填补哪个数据缺口/验证哪个假设"}
  ],
  "preflight_check": ["[OK] 清单项1完成", "[OK] 清单项2a-2d完成", "[OK] 清单项3a-3e完成", "[OK] 概率和=1.00", "[OK] 参数逐级递增,全参数自检通过", "[OK] WACC未修改", "[OK] 纯JSON输出"]
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
    "E": """Model E - EV/EBITDA (资源/矿业):
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, ebitda_growth_pct(**一年期**EBITDA增速%,如50表示EBITDA从5.6→8.4亿), target_ev_ebitda, target_mcap_yi(代码计算=EBITDA×(1+g%)×EV/EBITDA−净负债), upside_pct(代码计算), valuation_method, scenario_narrative(<=60字因果剧本)
    资源溢价/折价直接反映在 target_ev_ebitda 中——战略稀缺性给更高倍数即可,无需单独参数。""",
    "F": """Model F - rNPV pipeline valuation:
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, pos_pct, peak_sales_yi(峰值销售,亿), discount_rate_pct, target_mcap_yi(代码计算), upside_pct(代码计算), valuation_method, scenario_narrative(<=60字因果剧本)""",
    "J": """Model J - SOTP sum-of-parts:
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, target_mcap_yi(目标市值,亿), upside_pct(目标涨幅,%), valuation_method, rationale (<=80 chars), scenario_narrative(<=60字因果剧本)""",
    "K": """Model K - Two-Stage DCF (高增长→稳态):
scenario_details 为字典 {"bear":{...}, "base":{...}, "bull":{...}}，每个情景含: probability, stage1_growth_pct(阶段1:未来N年的NOPAT年增速,如30表示30%), stage1_years(高增长持续年数,通常3-7), roic_assumed_pct(阶段1的ROIC%), terminal_pe(阶段2:终值PE,高增长回落后的稳态倍数), segment_net_margin_pct(分部净利润率,核心参数——NOPAT=分部收入×此%,不填则回退公司整体净利率可能导致严重低估), target_mcap_yi(代码计算), upside_pct(代码计算), valuation_method, scenario_narrative(<=60字因果剧本)
    公式: Σ[NOPAT_t × (1-RR_t) / (1+WACC)^t] + NOPAT_N × terminal_PE / (1+WACC)^N
    RR_t = g1/ROIC, 约束在 [0.3, 0.9] 区间。WACC由代码预计算。""",
}

MODEL_NAMES = {
    "A": "ROIC-RR DCF", "B": "PS+TAM", "C": "Forward DCF+Inflection",
    "D": "PB-ROE", "E": "EV/EBITDA+Resource", "F": "rNPV Pipeline",
    "G": "PEG Growth", "H": "NAV Revaluation", "I": "Earnings Normalization",
    "J": "SOTP",
    "K": "Two-Stage DCF",
}

MODEL_FAMILIES = {
    "A": "盈利乘数", "C": "盈利乘数", "G": "盈利乘数", "I": "盈利乘数",
    "B": "收入乘数",
    "D": "资产乘数", "H": "资产乘数",
    "E": "资源",
    "F": "管线",
    "J": "分拆",
    "K": "盈利乘数",
}


# Model-specific scenario_params examples for output schema
# Model-specific parameter self-check (only lists params relevant to THIS model)
PARAM_SELF_CHECK_MAP = {
    "A": "- ROIC: 不能凭空跳变——改善幅度必须有故事节点对应。改善后的ROIC不能超过同行业ROIC上四分位\n- RR: RR=g/ROIC,高增速必须高RR,否则增速虚高\n- PE: bear PE 必须回到行业周期底部——凭行业知识判断这个'底部'是多少,不是当前PE的缩放",
    "C": "- ROIC: 拐点后ROIC改善幅度必须有时序节点对应(距拐点季度数)\n- PE: 拐点前PE可高于常规(买方为拐点付费),拐点后PE回归正常\n- 距拐点: 越远折现越大(每季度折6%),不应无限远",
    "G": "- earnings_growth_pct: 必须是盈利增速(EPS/净利润),不是收入增速\n- PE: 不能超过 PEG×earnings_growth, 否则违反PEG框架\n- PEG: 通常0.5-2.0,低于0.5=极度低估,高于2.0=增速不足以支持PE",
    "I": "- normalized_roic_pct: 正常化ROIC取5-10年行业中位数,不取当前极值\n- normalized_pe: 正常化PE取行业中位,不取当前畸高/畸低值",
    "B": "- revenue_growth_3y_cagr_pct: 3年收入CAGR。必须用分部对应产品的实际YoY增速校准,不能凭空取值。若Q1增速显著减速,必须反映这一趋势\n- target_ps: **第3年(终端年)的PS**。必須从火山数据/知识补充中找2-3家**同细分赛道**的可比A股公司,用它们在稳态期的实际交易PS作为参照。**同细分赛道=同客户类型+同商业模式+同利润池**,不是同行业标签。AI数据标注(服务大模型厂商)不能用大数据平台(服务政企)的PS——客户不同、毛利率不同、壁垒不同。如果找不到真正同赛道的可比公司,用更宽行业范围的中位数但要打7-8折,并在叙事中注明'无可比公司,使用打折后行业参照'\n- 心算校验: TTM收入 x (1+CAGR%)^3 x target_ps ≈ 你剧本预期的目标市值吗？\n- tam_penetration_pct: 当前TAM渗透率。若<5%则PS可取上限,若>30%则PS应保守",
    "D": "- target_roe_pct: ROE改善必须与PB修复联动(PB=ROE×权益乘数×PE的简化)。ROE从5%→15%可支撑PB从1x→3x\n- target_pb: PB不能远超ROE支撑的合理范围。ROE<5%不应>2x PB(除非隐蔽资产重估)",
    "E": "- ebitda_growth_pct: **一年期**EBITDA增速(%),不是多期累计。公式=EBITDA×(1+g/100)×EV/EBITDA。g=50表示EBITDA从5.6亿→8.4亿。\n- **经营杠杆换算（必须执行,不可跳过）**: 资源股的EBITDA增长≠商品价格涨幅。折旧/人工/摊销固定,涨价部分几乎全部→EBITDA。换算公式: **g_EBITDA% = ΔPrice% ÷ EBITDA率%**。步骤: (1)从上方财务数据取'EBITDA率'(已标注),取你的情景假设的商品价格涨幅ΔP%(如煤价+12%) (2)计算 g = ΔP% ÷ EBITDA率% (3)此g填入ebitda_growth_pct。例: EBITDA率14%,煤价涨12% → g=12%÷14%=85.7%,不是20%! 心算验证: 当前EBITDA×1.85≈你的预期值吗？\n- target_ev_ebitda: 资源溢价/折价直接反映在此倍数中。矿业通常6-10x,战略稀缺性可给更高,但需说明参照系",
    "H": "- nav_discount_pct: NAV折价必须反映资产流动性/变现难度。重资产折价20-40%,现金类资产折价0-10%",
    "F": "- pos_pct: 成功率必须基于临床阶段(Phase1=10%,Phase2=30%,Phase3=60%)\n- peak_sales_yi: 峰值销售必须与TAM×市场份额一致\n- discount_rate_pct: 管线折现率通常12-20%(高于WACC,反映管线风险)",
    "J": "- target_mcap_yi: 必须是SOTP加总结果(各业务线独立估值+现金+投资-负债)",
    "K": "- stage1_growth_pct: 阶段1 NOPAT年增速,从当前出发推演。高增长阶段通常3-7年,增速>ROIC意味着需要外部融资(RR>100%会被代码封顶)\n- stage1_years: 高增长持续年数,根据行业周期和企业生命周期判断(通常3-7)\n- roic_assumed_pct: 阶段1的ROIC,可以高于当前值(改善逻辑)。不能脱离叙事凭空跳变\n- terminal_pe: 终值PE,高增长回落后进入稳态的合理倍数。与行业中枢匹配(通常15-30x)\n- **segment_net_margin_pct: 分部净利润率(净利润/收入),不是毛利率。NOPAT=分部收入×此%。如果不填,代码回退到公司整体净利率,可能导致该分部被严重低估。必须根据火山数据中的产品毛利率减去10-15pp折算,或参考可比公司净利率。**",
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
    "E": "probability, ebitda_growth_pct, target_ev_ebitda, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "F": "probability, pos_pct, peak_sales_yi, discount_rate_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "J": "probability, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
    "K": "probability, stage1_growth_pct, stage1_years, roic_assumed_pct, terminal_pe, segment_net_margin_pct, target_mcap_yi, upside_pct, valuation_method, scenario_narrative",
}

SCENARIO_PARAMS_MAP = {
    "A": '"bear": {"probability":0.XX, "roic_assumed_pct":X, "rr_assumed_pct":X, "pe_target":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "C": '"bear": {"probability":0.XX, "roic_assumed_pct":X, "pe_target":X, "quarters_to_inflection":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "G": '"bear": {"probability":0.XX, "roic_assumed_pct":X, "earnings_growth_pct":X, "pe_target":X, "peg_ratio":X.X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "I": '"bear": {"probability":0.XX, "normalized_roic_pct":X, "normalized_pe":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "B": '"bear": {"probability":0.XX, "revenue_growth_3y_cagr_pct":X, "target_ps":X, "tam_penetration_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "D": '"bear": {"probability":0.XX, "target_roe_pct":X, "target_pb":X.X, "payout_ratio_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "H": '"bear": {"probability":0.XX, "nav_discount_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "E": '"bear": {"probability":0.XX, "ebitda_growth_pct":X, "target_ev_ebitda":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "F": '"bear": {"probability":0.XX, "pos_pct":X, "peak_sales_yi":X, "discount_rate_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "J": '"bear": {"probability":0.XX, "target_mcap_yi":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
    "K": '"bear": {"probability":0.XX, "stage1_growth_pct":X, "stage1_years":X, "roic_assumed_pct":X, "terminal_pe":X, "segment_net_margin_pct":X, "scenario_narrative":"..."}, "base": {...}, "bull": {...}',
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
        "{SCENARIO_PARAMS_EXAMPLE}", "{" + params_example + "}"
    ).replace(
        "{MODEL_PARAM_SELF_CHECK}", self_check
    ).replace(
        "{MODEL_PARAM_NAMES}", param_names
    )


# ═══════════════════════════════════════
# LLM-2 系统提示词 — 审查 + 搜索 + 最终报告
# ═══════════════════════════════════════

LLM2_SYSTEM_PROMPT = """# 你是估值审阅官

你的职责不是重新估值，而是**审阅 LLM-1 的参数推演，对照代码计算出的估值结果，补充缺失数据，纠正错误，输出最终报告**。

## 输入

你收到四部分信息:
- **A 部分: LLM-1 的完整参数输出** — reasoning_trace、三情景参数、CAGR拆解、data_gaps、change_request
- **B 部分: 代码计算的估值结果** — 每个情景的实际目标市值、upside%、概率加权值、ROIC审计警告、跨族校验结果
- **C 部分: 当前市场定价数据** — 市值、PE、PS、PB、隐含增速、BS画像——此时可见
- **D 部分: 完整上下文** — baseline报告、事件数据、2a诊断结论、财务数据

## 多轮对话与搜索工具

你和一个更大的对话系统在进行**多轮对话**——不是一次性问答。

**对话机制**:
- 第 1 轮: 你收到完整上下文（A/B/C/D 部分），开始审阅
- 如果你需要搜索: 在 JSON 输出中包含 `search_requests` 字段。代码会执行搜索（并行），然后将你的本轮输出作为 assistant 消息、搜索结果作为 user 消息追加到对话历史
- 第 2 轮: 你收到完整的对话历史（第 1 轮的上下文 + 你的输出 + 搜索结果），可以基于新信息继续审阅
- 第 3 轮: 同上，最多 3 轮，**每轮最多 2 条搜索**——精炼查询，确保每条带来可操作的增量信息
- 当你不再需要搜索时: **不输出 search_requests 字段**，直接输出最终报告。对话结束。

**search_requests 格式**（每轮最多 2 条）:
```json
"search_requests": [
  {"query": "精炼的搜索查询", "purpose": "要填补什么/验证什么"}
]
```

**搜索范围限制**: 只搜 data_gaps 和 change_request 中列出的具体信息缺口。禁止搜索任何公司的 PE/PS/PB 估值倍数——可比公司信息来自 baseline 产业位置和你的行业知识，不来自火山搜索。

## 任务（按顺序）

### 任务 1: 数据补充——必搜清单

LLM-1 输出的 data_gaps 和 change_request 不是参考——是**必搜清单**。每条都必须通过 search_requests 向火山引擎发起搜索。火山支持自然语言查询，直接用 data_gaps 原文即可。

**执行规则**:
- 逐条读取 LLM-1 的 data_gaps，每条生成一个 search_request
- 逐条读取 LLM-1 的 change_request，每条生成一个 search_request
- volc 预搜索结果（D 部分）如果已覆盖某条缺口，可跳过
- 搜索结果返回后，分析是否填补了缺口，在 supplemented_data 中记录

### 任务 2: 逻辑审查——从推理链找问题

**不要重做 LLM-1 的工作。** 你的起点是 LLM-1 的 reasoning_trace——这是 LLM-1 自述的完整推理链。逐条追溯:

1. LLM-1 的每个参数赋值，在 reasoning_trace 里能找到对应的依据吗？找不到 → 这是拍脑袋的参数
2. LLM-1 引用的数据，和 baseline 里的数字一致吗？不一致 → 数据引用错误
3. LLM-1 的风险映射结论，在参数里有体现吗？没体现 → 风险被选择性忽略
4. LLM-1 三段因果剧本（bear/base/bull）的逻辑分叉点，在参数差异里有对应吗？没有 → 叙事和数字脱节

常规检查:
- **参数内部矛盾**: ROIC 8% 但 PE 50x？CAGR 30% 但再投资率 RR 为零？
- **叙事与数字矛盾**: 风险映射说"零部件毛利率极低是主要拖累"，但 bull 假设毛利率跳升至 20%+？
- **模型选择不当**: 路由选的模型是否真的适合当前事件结构？
- **数据滞后误解**: 是否把涨价前的毛利率当成了稳态？
- **禁止搜索可比公司**: 不要向火山搜索可比公司 PE/PS——搜索结果不可靠。可比公司判断只依赖 baseline 的产业位置和你的行业知识。

**⚠️ 数据时效性铁律: 事件 > 一切。** 事件是唯一最新情报。券商预测、历史财务、火山搜索结果都可能是事件前的旧数据。当你发现矛盾时: 事件说什么就是什么——券商预测没反映涨价 → 券商预测过时，不是事件错了。只有在事件完全没有涉及某个数据点时，才用其他来源。

### 任务 3: 参数修改——发现问题就必须改，不能只写"置信度低"了事

**这是你最重要的职责。** 如果你在任务 2 中发现了问题，不能只写在 confidence note 里了就过关。你必须把纠正落实到参数上。

**修正的铁律——沿事件因果链走，不能跳过事件套历史数据:**

事件是第一性输入。你的修正必须从事件的因果链出发: 事件改变了什么 → 参数应该如何反映这个改变 → LLM-1 的偏差是低估了还是高估了事件冲击 → 往哪个方向调。

反例（禁止）: "ROIC -1.5%，可比公司 ROIC 15%+，因此 PS 应该是 3x 而非 7x"——这句话跳过了事件。正确的分析是: "事件描述了全球 PI 缺口 1-1.2 万吨、杜邦/钟渊零新增产能、公司是唯一国产替代标的——这种结构性格局质变不能用当前 ROIC 做机械对标。ROIC 是事件冲击前的基本面快照，不是事件冲击后的估值锚。LLM-1 的 PS 7x 可能偏高，但下调的依据应该是产能天花板/客户验证节奏/涨价传导速度——这些来自事件描述——而非当前 ROIC。"

常见场景及对应的修改义务:

| 发现的问题 | 必须做的修改 | 不改的后果 |
|-----------|------------|-----------|
| PS/PE 假设与事件的供需格局/竞争位势不匹配 | 按事件描述的行业格局调 PS/PE，不是按当前 ROIC 对标 | 估值忽略了结构性变化 |
| 全公司用 PS 估值，但低毛利分部不该享受高 PS | 拆分分部、或下调整体 PS 反映低毛利拖累 | 低质量收入被高估 |
| 净利率/毛利率改善路径缺乏事件支撑 | 下调 ROIC 改善假设，或在 narrative 中标注不确定性 | 盈利预测悬空 |
| 产能天花板假设远超已建成产能且无硬证据 | 下调 volume growth 至已建成产能可支撑范围 | 增速假设无法落地 |
| 路由选择了 PS 模型但公司盈利业务占比 >60% | 考虑切换为 earnings 锚或至少大幅下调 PS | 模型与业务实质不匹配 |

**禁止**: 发现问题后只在 confidence 里写"PS假设缺乏支撑"然后不改参数。你不改，这个问题就会被带入最终估值。

change_log 每条格式:
- path: 参数路径（如 "base.target_ps"）
- old_value: 原值
- new_value: 新值
- reason: 修改原因
- evidence: 支撑证据（搜索来源或逻辑推理）

- **禁止**: 为"让数字更好看"而修改参数。
- 代码会重新计算修改后的估值。

### 任务 4: 最终判断
基于代码计算出的 **实际 upside 数字**（而非你的心算）:
- 赋值四维置信度（各 1-10）
- 赋值交易标注（tier + 四维 0-3 打分）
- 编写 probability_rationale（引用实际 upside 和 asymmetry_ratio）
- 做预期差分析（市场隐含预期 vs 你的 base 推演）
- **关键**: 如果概率加权 upside 是 -54.7%，你不能写"基本公允"——数字和结论必须一致
- 定义监测 KPI 和风险触发器
- 写最终投资叙事（可引用具体 upside 数字——这些是代码算的，不是心算）

## 核心约束
1. WACC 不可修改
2. 三情景概率之和 = 1.0
3. 参数修改必须有可验证的证据
4. 输出纯 JSON，不要用 markdown 代码块包裹

# 输出 Schema——你输出的是**完整的最终报告**

你的输出将直接替代 LLM-1 的输出成为最终报告。继承 LLM-1 的字段（不做修改的照抄），覆盖修改过的字段。以下是必须包含的全部字段：

{
  "scenario_valuation": {
    "scenario_details": {
      "bear": {"probability": 0.20, "target_ps": 4.0, "revenue_growth_3y_cagr_pct": 10, "...": "照抄 LLM-1 或修改"},
      "base": {"probability": 0.60, "target_ps": 8.0, "revenue_growth_3y_cagr_pct": 25, "...": "照抄 LLM-1 或修改"},
      "bull": {"probability": 0.20, "target_ps": 12.0, "revenue_growth_3y_cagr_pct": 35, "...": "照抄 LLM-1 或修改"}
    }
  },
  "growth_path_decomposition": { "照抄 LLM-1，如修改了增速参数则更新" },
  "signal_audit": { "照抄 LLM-1" },
  "reasoning_trace": [
    "LLM-1: 清单项1-素材吸收: ...",
    "...": "保留 LLM-1 的完整 reasoning_trace，在末尾追加你的审阅条目",
    "LLM-2: 审查-数据补充: ...",
    "LLM-2: 审查-参数修改: 将 base.target_ps 从 12x 降至 8x，因...(理由)",
    "LLM-2: 审查-置信度: ..."
  ],
  "data_gaps": ["补充后的缺口列表"],
  "change_log": [
    {"path": "base.target_ps", "old_value": 12, "new_value": 8, "reason": "ROIC 6.2%<WACC 10%，不配行业龙头PS", "evidence": "有研新材当前PS=3.2x；A股半导体材料中位数PS=5.1x"}
  ],
  "confidence": {
    "overall_score": 1-10,
    "overall_label": "高|中|低",
    "dimensions": {
      "info_quality": {"score": 1-10, "label": "信息质量", "note": "评分依据"},
      "financial_feasibility": {"score": 1-10, "label": "财务可行性", "note": "评分依据"},
      "valuation_safety": {"score": 1-10, "label": "估值安全边际", "note": "评分依据"},
      "historical_precedent": {"score": 1-10, "label": "历史案例匹配", "note": "评分依据"}
    }
  },
  "trade_annotation": { "tier": "★★★ 高赔率机会|★★☆ 中等赔率|★☆☆ 低赔率机会|☆☆☆ 规避", "total_score": "X/10", "dimension_scores": {"odds_quality": 0-3, "pricing_headroom": 0-3, "transmission_confidence": 0-3, "model_consistency": 0-3}, "alignment_signals": ["信号"], "tier_note": "理由", "suggested_action": "建议" },
  "monitoring_kpis": {
    "financial_verification_kpis": [{"name": "KPI名称", "baseline": "当前值", "target": "目标值", "frequency": "季度", "verifies": "验证什么假设"}],
    "event_milestone_kpis": [{"name": "里程碑名称", "expected_timing": "预计时间", "significance": "为什么重要", "verification_source": "信息来源"}],
    "competition_signal_kpis": [{"name": "信号名称", "current_state": "当前状态", "trigger": "触发条件", "action_if_triggered": "应对措施"}],
    "risk_trigger_kpis": [{"name": "风险名称", "linked_to": "关联指标", "severity": "high|medium|low", "monitor": "监控频率"}]
  },
  "risk_triggers": { "bull_trigger": "...", "bear_trigger": "...", "monitoring_frequency": "季度" },
  "narrative": "照抄 LLM-1 的原始叙事——这是 LLM-1 从事件到参数的核心故事线，不要改写。如果你有修正意见，写在 _review_note 字段里。",
  "probability_rationale": "概率推导",
  "expectation_gap": { "level": "市场更乐观|市场更悲观|预期相近|无法解码", "note": "..." },
  "validation_crosscheck": { "validation_model": "...", "assessment": "..." },
  "data_gaps": ["缺口格式: [已搜索:查询词] 原标题 — 搜索结果摘要"],
  "reasoning_trace": ["LLM-1: ...", "LLM-2: 审查-数据补充: 对N条缺口逐一搜索，结果如下...", "LLM-2: 审查-逻辑审查: ...", "LLM-2: 审查-参数修改: ...", "LLM-2: 审查-置信度: ...", "LLM-2: 审查-最终叙事: ..."]
}

**注意**:
- search_requests 字段仅在需要搜索时输出。最终报告不输出 search_requests。
- scenario_details 里的参数体系由路由定的模型决定——如果你修改了参数，输出修改后的完整 scenario_details。
- reasoning_trace: 保留 LLM-1 的全部 reasoning_trace，末尾追加你的审阅条目（以"LLM-2: 审查-XXX"开头）。

**⚠️ 关键铁律 #1: 禁止在 narrative 中写市值数字。** 估值由代码计算，不是由你估算。不要说"修正后市值约XX亿"或"公允价值约XX亿"——你写的数字和代码算出的必然不一致，会污染最终报告。写参数为什么这么设、逻辑为什么这么推演，让代码说话。

**⚠️ 关键铁律 #2: change_log 不能为空。** 如果你的 narrative 里写了"XX参数缺乏支撑"、"YY被低估"、"ZZ假设不合理"，你必须在 change_log 里给出对应的参数修改。narrative 里的每个审阅发现都必须能在 change_log 里找到对应的条目。只有一种情况 change_log 可以为空：你确认 LLM-1 的每个参数都完美无误。但这种情况下你的 narrative 也不应该包含任何批评。
"""


def _fetch_bond_yields(fetcher: DataFetcher) -> dict:
    """获取10年期国债收益率。优先用 DataFetcher 内置方法，失败回退默认值。"""
    try:
        bonds = fetcher.fetch_bond_yields()
        y10 = bonds.get("yield_10y")
        if y10 and 0 < y10 < 10:
            return {"yield_10y": y10, "source": f"investoday API ({bonds.get('date', '')})"}
    except Exception:
        pass
    # 备用: 尝试旧端点
    try:
        raw = fetcher._cli("macro/bond-yields", method="POST",
                          beginDate=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                          endDate=datetime.now().strftime("%Y-%m-%d"),
                          pageNum=1, pageSize=1)
        item = fetcher._first(raw)
        y10 = fetcher._num(item.get("yield10Y"))
        if y10 and 0 < y10 < 10:
            return {"yield_10y": y10, "source": "investoday API (旧端点)"}
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
        erp = max(4.0, min(12.0, base_erp + adj))
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
        return f"隐含g({implied_g_pct}%)为负，市场定价低于零增长"
    g_ratio = implied_g_pct / wacc_pct * 100 if wacc_pct > 0 else 0
    if g_ratio > 90:
        return f"隐含g/WACC={g_ratio:.0f}%: 隐含g({implied_g_pct}%)逼近WACC({wacc_pct}%)上限"
    elif g_ratio > 60:
        return f"隐含g/WACC={g_ratio:.0f}%: 市场定价了显著改善预期"
    elif g_ratio > 35:
        return f"隐含g/WACC={g_ratio:.0f}%: 市场定价了部分改善"
    elif g_ratio > 15:
        return f"隐含g/WACC={g_ratio:.0f}%: 市场定价接近当前盈利能力"
    else:
        return f"隐含g/WACC={g_ratio:.0f}%: 隐含g({implied_g_pct}%)远低于WACC"


def precompute_bs_profile(primary_model: str, data_package: dict,
                          wacc_params: dict, valuation_anchor: str = "earnings") -> dict:
    """计算 BS 画像。V6: 根据估值锚选择对应工具。

    earnings → 反向DCF (g/WACC)
    revenue → 隐含收入CAGR (PS→3y增速)
    asset → 隐含ROE改善 (PB→当前ROE)
    """
    core = data_package.get("packages", {}).get("core", {}).get("fields", {})
    mcap = core.get("market_cap_yi", 50)
    equity = core.get("total_equity_yi", 1)
    pe = core.get("pe_ttm", 0)
    pb_val = core.get("pb", 0)
    nopat = core.get("nopat_yi", 0.01)
    roic = core.get("roic_pct", 0)
    cash = core.get("cash_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    revenue = core.get("revenue_ttm_yi", 1)
    ps = core.get("ps_ttm", 0)
    roe = core.get("roe_ttm_pct", 0)
    ev = mcap + debt - cash
    wacc = wacc_params["wacc_pct"] / 100 if wacc_params["wacc_pct"] > 0 else 0.1
    wacc_pct = wacc_params["wacc_pct"]

    # 始终计算反向DCF作为参考
    rdcf = _compute_reverse_dcf(nopat, ev, wacc)
    warnings = list(rdcf["warnings"])
    secondary = ""
    market_story = ""
    icagr = {}  # 作用域占位
    iroe = {}

    if valuation_anchor == "revenue":
        # ── 收入锚: 用隐含 CAGR ──
        from pricing_tools import implied_revenue_cagr
        ps_val = core.get("ps_ttm", 0)
        icagr = implied_revenue_cagr(mcap, revenue, ps_val, wacc_pct)
        if icagr.get("applicable"):
            imp = icagr["implied_value"]
            bs_method = "隐含收入CAGR (收入锚)"
            bs_level = f"当前PS={ps_val:.1f}x → 市场隐含3年收入CAGR≈{imp}%"
            market_story = f"PS={ps_val:.1f}x 营收={revenue:.1f}亿 市值={mcap:.0f}亿 → 隐含3y CAGR={imp}%"
        else:
            bs_method = "隐含收入CAGR — 不适用"
            bs_level = f"PS={ps_val:.1f}x (营收数据不足以推算CAGR)"
            market_story = f"PS={ps_val:.1f}x 营收={revenue:.1f}亿"
        # 标注反向DCF仅供参考
        if rdcf["applicable"]:
            g_ratio = rdcf["implied_g_pct"] / wacc_pct * 100 if wacc_pct > 0 else 0
            secondary = f"(参考)反向DCF: g/WACC={g_ratio:.0f}% — 基于NOPAT,对收入锚仅供参考"
        if rdcf["market_premium_pct"] >= 999:
            warnings.append("反向DCF不适用: NOPAT极薄,溢价失真(999%=标记值)")
    elif valuation_anchor == "asset":
        # ── 资产锚: 用隐含 ROE 改善 ──
        from pricing_tools import implied_roe_improvement
        iroe = implied_roe_improvement(mcap, equity, pb_val, roe, wacc_pct)
        if iroe.get("applicable"):
            imp = iroe["implied_value"]
            bs_method = "隐含ROE改善 (资产锚)"
            bs_level = f"当前PB={pb_val:.1f}x → 市场隐含ROE需改善{imp}ppt (当前ROE={roe:.1f}%)"
            market_story = f"PB={pb_val:.1f}x ROE={roe:.1f}% 净资产={equity:.0f}亿"
        else:
            bs_method = "隐含ROE改善 — 不适用"
            bs_level = f"PB={pb_val:.1f}x"
            market_story = f"PB={pb_val:.1f}x 净资产={equity:.0f}亿"
        if rdcf["applicable"]:
            g_ratio = rdcf["implied_g_pct"] / wacc_pct * 100 if wacc_pct > 0 else 0
            secondary = f"(参考)反向DCF: g/WACC={g_ratio:.0f}% — 基于NOPAT,对资产锚仅供参考"
    else:
        # ── 利润锚: 用反向 DCF（保持原逻辑）──
        bs_method = "反向DCF(g/WACC)"
        bs_level = _bs_level_from_g_wacc(rdcf["implied_g_pct"], wacc_pct)
        premium_str = f" 溢价{rdcf['market_premium_pct']}%" if rdcf['market_premium_pct'] < 999 else ""
        market_story = (
            f"EV={ev:.0f}亿 NOPAT={nopat:.2f}亿 ROIC={roic:.1f}% "
            f"WACC={wacc_pct}% 隐含g={rdcf['implied_g_pct']}% "
            f"DCF基准={rdcf['base_dcf']}亿{premium_str}"
        )
        # 模型专属辅助
        m = primary_model[0] if primary_model else "A"
        if m == "B":
            rev = core.get("revenue_ttm_yi", 1)
            ps_val2 = mcap / rev if rev > 0 else 0
            secondary = f"PS={ps_val2:.1f}x"
        elif m == "D":
            secondary = f"PB={pb_val:.1f}x"
        elif m == "E":
            ebitda = core.get("ebitda_ttm_yi", 0)
            ev_ebitda_real = ev / ebitda if ebitda > 0 else 0
            secondary = f"EV/EBITDA={ev_ebitda_real:.1f}x"

    # V6: 锚感知的隐含指标
    if valuation_anchor == "revenue":
        implied_main = icagr.get("implied_value", 0) if icagr.get("applicable") else 0
        premium_main = 0  # CAGR无溢价概念
        tool_applicable = icagr.get("applicable", False)
        tool_note = "" if tool_applicable else "隐含CAGR不适用"
    elif valuation_anchor == "asset":
        implied_main = iroe.get("implied_value", 0) if iroe.get("applicable") else 0
        premium_main = 0
        tool_applicable = iroe.get("applicable", False)
        tool_note = "" if tool_applicable else "隐含ROE不适用"
    else:
        implied_main = rdcf["implied_g_pct"]
        premium_main = rdcf["market_premium_pct"]
        tool_applicable = rdcf["applicable"]
        tool_note = rdcf["applicable_note"]

    return {
        "bs_method": bs_method,
        "bs_level": bs_level,
        "bs_secondary": secondary,
        "ev_yi": round(ev, 1),
        "nopat_yi": round(nopat, 2),
        "roic_pct": round(roic, 1),
        "wacc_simple_pct": wacc_pct,
        "market_premium_pct": min(premium_main, 999),
        "implied_g_pct": implied_main,
        "pe_ttm": pe,
        "pb": pb_val,
        "market_story": market_story,
        "warnings": warnings,
        "wacc_params": wacc_params,
        "note_to_llm": "BS画像是代码计算的已知事实。你是LLM裁判——不可修改上述数据，只能解读并围绕它们构建情景。",
        "reverse_dcf_applicable": tool_applicable if valuation_anchor != "earnings" else rdcf["applicable"],
        "reverse_dcf_applicable_note": tool_note if valuation_anchor != "earnings" else rdcf["applicable_note"],
        "valuation_anchor_used": valuation_anchor,  # V6: 标注使用的锚
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


def _build_growth_summary(core: dict) -> str:
    """从 Agent-1 forward_looking 提取产品增速+季度趋势，生成紧凑摘要。"""
    fw = core.get('_forward_looking', {}) or {}
    cats = fw.get('categories', {}) or {}
    products = (cats.get('earnings_elasticity', {}) or {}).get('products', {}) or {}
    mix = products.get('product_mix', []) or []
    et = (cats.get('management_guidance', {}) or {}).get('earnings_trend', {}) or {}

    lines = []

    # 产品级增速
    if mix:
        data_vintage = products.get('data_vintage', '')
        lines.append(f'**分产品增速** ({data_vintage}):')
        for p in mix:
            yoy = p.get('revenue_yoy_pct')
            yoy_str = f'{yoy:+.1f}%' if yoy is not None else '?'
            lines.append(f'  - {p["name"]}: {yoy_str} (占比{p.get("revenue_share_pct",0):.1f}%)')
        if '2025' in str(data_vintage):
            lines.append('  > 以上为年报数据。请在事件素材中查找各产品2026Q1最新增速，判断是否加速。')

    # 季度趋势
    recent = et.get('recent_4q', [])
    if recent:
        parts = []
        for q in recent[:4]:
            period = str(q.get('period', ''))
            if len(period) >= 6:
                label = f'{period[2:4]}Q{(int(period[4:6])-1)//3+1}'
            else:
                label = period
            yoy = q.get('revenue_yoy') or q.get('revenue_q_yoy')
            if yoy is not None:
                parts.append(f'{label} {yoy:+.1f}%')
        if parts:
            trend = et.get('trend_direction', '')
            trend_str = f' 趋势:{trend}' if trend else ''
            lines.append(f'\n**最近4季度营收同比**: {" | ".join(parts)}{trend_str}')

    # 交叉验证提示
    if mix or recent:
        lines.append('\n> **增速交叉验证**（赋CAGR/增速参数前按顺序校验）：')
        lines.append('> 1. 事件素材的\'投资主题\'和\'发展推演\'——2026Q1最新增速是否高于上表年报增速？')
        lines.append('> 2. 火山联网搜索——券商对未来2-3年的预测是否隐含更高增速？')
        lines.append('> 3. 事件驱动逻辑——事件是加速/跃迁/稳步推进？质变节点→非线性加速，非均值回归。')
        lines.append('> 4. **K(DCF)适用性判定**——检查以上交叉验证结论：(a)分产品毛利率是否可直接取到？(b)毛利率改善+规模效应→ROIC改善路径是否可见？(c)火山数据的产能/订单是否约束了增速上限使终局可预见？若三项全满足，应选K(两阶段DCF)而非B(PS+TAM)——K能建模增长→利润→现金流的完整路径。任一不满足则保持B。')

    return '\n'.join(lines) if lines else '（无分产品增速数据）'


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

        # 增速时效性提示：产品表是年报数据，Q1加速信号在软素材和火山数据中
        if "2025" in str(data_vintage):
            lines.append(f'\n  > **增速交叉验证**（以上产品增速基于{data_vintage}，赋CAGR/增速参数前按顺序校验）：')
            lines.append('  > 1. 查看软素材的\'投资主题\'和\'发展推演\'——2026Q1最新增速是否显著高于上述年报增速？')
            lines.append('  > 2. 查看\'火山联网搜索\'——券商对未来2-3年的营收预测是否隐含更高的增速预期？')
            lines.append('  > 3. 结合事件驱动逻辑——事件是加速、跃迁、还是稳步推进？若事件指向质变节点（技术突破/产能释放/客户导入），参数应反映非线性加速而非均值回归。')

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
    event_data: dict,
    agent2a_output: dict | None = None,
    volc_data: dict | None = None,
    baseline_report: str | None = None,
) -> dict:
    """单次 LLM 调用：完整推演裁决（V7: 投资地图 + V6: 信任 Agent-2a 诊断结论）。"""

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
""" + (f"- 市值/代码基准比值: {bs_profile['market_premium_pct']}%\n" if bs_profile.get('market_premium_pct', 0) < 999 else "") + (f"- 辅助指标: {bs_profile['bs_secondary']}\n" if bs_profile.get('bs_secondary') else "")
        bs_warning = ""
    elif anchor_2a == "revenue":
        if pt_full and pt_full.get("applicable"):
            tps = pt_full.get('detail', {}).get('terminal_ps_assumed', '?')
            bs_section = f"""**方法: 隐含收入 CAGR (收入锚, 代码预计算, 仅供参考)**
- 定价工具假设: 当前 PS={core.get('ps_ttm',0):.1f}x 在 3 年后回归至 {tps}x (硬编码规则: PS>30→8x, PS>15→5x, PS>5→3x, 否则→2x)
- 在此假设下反推: 市场隐含 3 年收入 CAGR = {pt_full.get('implied_value','?')}%
- 注: 这是机械规则生成的参照系, 不反映市场真实预期。你应在情景推演中基于护城河/范式切换/成长阶段独立判断 terminal PS 假设, 不受此约束。
"""
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

    # ── 增速数据摘要（从 Agent-1 forward_looking 提取，补充叙事和火山数据的时效差）──
    growth_summary = _build_growth_summary(core)

    # 构建用户消息 (一个完整的大f-string)
    # ── V7: 投资地图 ──
    baseline_section = ""
    if baseline_report and len(baseline_report) > 100:
        baseline_section = f"""
## 投资地图 — Agent-Baseline 合成（事件冲击前的企业全貌，主输入）

{baseline_report}

---
"""

    user_msg = f"""# 推演裁决: {stock}({code})
{baseline_section}
## 市场定价数据 (供清单项4b预期差分析参考，非参数输入)

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

## 路由判决
- 主模型: {primary} ({category})
- 路由理由: {reason}
- 校验模型: {routing.get('validation_models', [])}
- 迁移路径: {json.dumps(routing.get('model_migration_path', {}), ensure_ascii=False)}

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
- 信号评分: {sa.get('step2d_score','?')}/10 — {sa.get('score_rationale','?')[:200]}
- 信号审核结论: {json.dumps(sa.get('step2a_restate',[])[:3], ensure_ascii=False)}
- 交叉验证摘要: {json.dumps([str(m)[:120] for m in sa.get('step2b_match',[])[:3]], ensure_ascii=False)}
"""
        # 注入范式切换潜力
        asp = mn.get("anchor_shift_potential", {}) or {}
        if asp.get("shift_possible"):
            user_msg += f"""
- 范式切换潜力: 是
  从 {asp.get('from_anchor','?')} → {asp.get('to_anchor','?')}
  触发条件: {asp.get('shift_trigger','?')}
  理由: {asp.get('shift_rationale','?')[:200]}
  时机: {asp.get('shift_timing','?')}
  先例: {asp.get('precedent','?')[:150]}
"""
        # (定价工具详情保留给 LLM-2，LLM-1 不需要)

    # ═══ 事件素材：当前情形的一手数据，估值参数的主要锚定来源 ═══
    user_msg += f"""

## 事件素材 — 当前情形的一手数据，是估值参数的主要锚定来源

> **数据层级原则**: 以下来自事件/行业的产能、价格、利用率、客户认证、供需缺口等信息，
> 反映的是"现在正在发生什么"。在事件驱动框架中，这是你判断当前企业状态的首要依据。
> 历史财务数据（见下一节）反映的是事件冲击前的过去状态——只用于理解冲击幅度和商业模式，
> 不可替代事件素材中的产能/价格/利用率作为当前情形的基准。

## 事件变量
{event_data.get('raw_event_text','')}

## 事件研判
{event_data.get('preliminary_reasoning','')}

## 背景知识
{event_data.get('knowledge_supplement','')}

## {stock}的投资主题
{event_data.get('investment_theme','')}

## {stock}的发展推演
{event_data.get('event_deduction','')}

## {stock}的催化节点
{event_data.get('future','')}

## {stock}的逆向风险
{event_data.get('adversarial_thinking','')}

## 行业全貌
{event_data.get('industry_expert_research','')}
"""
    # V6.3: 火山联网搜索补充数据
    volc = volc_data or {}
    volc_text = volc.get("volc_text", "")
    if volc_text:
        user_msg += f"""
## 火山联网搜索补充数据（市场对公司的量化预期和可比估值）

{volc_text}

以上是市场当前对公司的量化预期和可比估值——对你的推演起背景增强作用。事件驱动才是变量和诱因，事件如何重塑或推进上述投资全貌才是你参数改变的逻辑。
"""
    # ═══ 历史财务基线：事件冲击前的企业快照 ═══
    user_msg += f"""
## 历史财务基线 — 事件冲击前的企业快照，用于理解冲击幅度和商业模式

> **正确用法**: 以下数据反映事件发生前的企业状态。不要用这些历史数字直接作为
> "当前情形"——事件已经改变了现状。用法: (1) 对比事件素材中的产能×价格×利用率，
> 推算事件造成的收入/利润增量；(2) 用历史毛利率/净利率理解企业的成本结构和盈利模型，
> 判断价格变化对利润的杠杆效应；(3) 用历史ROIC理解企业的资本回报基线。

- 市值: {core.get('market_cap_yi',0)}亿 营收TTM: {core.get('revenue_ttm_yi',0)}亿
- 净利润: {core.get('net_profit_ttm_yi',0)}亿 经营利润: {core.get('operating_profit_ttm_yi',0)}亿
- EBITDA: {core.get('ebitda_ttm_yi',0):.1f}亿 EBITDA率: {core.get('ebitda_ttm_yi',0)/max(core.get('revenue_ttm_yi',1),1)*100:.1f}%
- ROIC: {core.get('roic_pct',0)}% 毛利率: {core.get('gross_margin_pct',0)}% 净利率: {core.get('net_margin_pct',0)}%
	- 历史分位解读: 0=历史最高位(从未更贵), 50=中位, 100=历史最低位(从未更便宜)
	- 盈利能力分位: ROIC分位={core.get('roic_historical_rank','?')} 毛利率分位={core.get('gross_margin_historical_rank','?')} 净利率分位={core.get('net_margin_historical_rank','?')} ROE分位={core.get('roe_historical_rank','?')} 综合得分={core.get('profitability_composite_score','?')}
- PE: {core.get('pe_ttm',0)}x (历史分位={core.get('pe_historical_rank','?')}) PB: {core.get('pb',0)}x (历史分位={core.get('pb_historical_rank','?')}) PS: {core.get('ps_ttm',0)}x
- 净资产: {core.get('total_equity_yi',0)}亿 总资产: {core.get('total_assets_yi',0)}亿
- 有息负债: {core.get('interest_bearing_debt_yi',0)}亿 现金: {core.get('cash_yi',0)}亿
- 经营CF: {core.get('ocf_ttm_yi',0)}亿 Capex: {core.get('capex_ttm_yi',0)}亿
- 异常标记: {json.dumps(core.get('caution_flags',[]), ensure_ascii=False)}
- 数据质量: {core.get('data_quality_score',10)}/10

## 前瞻信号 — 定量增速摘要（Agent-1 财报提取，赋CAGR前必查）
{growth_summary}
> Agent-2a 已完成信号审核，结论参见上文"Agent-2a 叙事诊断结论"中的 signal_audit。
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
                "max_tokens": 40960,
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
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ScenarioError("E301", f"JSON顶层非object(type={type(parsed).__name__})", {"raw": text[:500]})
        return parsed
    except json.JSONDecodeError:
        # 最后的 fallback: 尝试简单的 { 到 } 截取
        s = text.find("{")
        e = text.rfind("}")
        if s >= 0 and e > s:
            try:
                parsed2 = json.loads(text[s:e + 1])
                if not isinstance(parsed2, dict):
                    raise ScenarioError("E301", f"JSON非object(type={type(parsed2).__name__})", {"raw": text[:500]})
                return parsed2
            except json.JSONDecodeError:
                pass
        raise ScenarioError("E301", "JSON解析失败", {"raw": text[:500]})


# ═══════════════════════════════════════
# LLM-2 调用 — 多轮搜索 + 审阅 + 最终报告
# ═══════════════════════════════════════

def _call_llm2(
    llm1_output: dict,
    computed: dict,
    bs_profile: dict,
    wacc_params: dict,
    data_package: dict,
    routing: dict,
    event_data: dict,
    agent2a_output: dict | None = None,
    baseline_report: str | None = None,
    roic_warnings: list | None = None,
    mandatory_xcheck: dict | None = None,
    volc_pre_search: str = "",
    max_rounds: int = 3,
    system_prompt: str | None = None,
) -> dict:
    """LLM-2: 多轮搜索审阅 + 最终报告。

    最多 max_rounds 轮。每轮 LLM-2 可以输出 search_requests，
    system_prompt: 可选的自定义系统提示词（SOTP 等变体使用）
    代码执行搜索后将结果注入上下文，再次调用 LLM-2。
    """
    core = data_package.get("packages", {}).get("core", {}).get("fields", {})
    stock = core.get("stock_name", data_package.get("stock_name", ""))
    code = data_package.get("stock_code", "")
    primary = routing.get("primary_model", "A")

    # ── 构建 LLM-2 用户消息的静态部分 ──
    # A 部分: LLM-1 完整输出
    alpha_json = json.dumps(llm1_output, ensure_ascii=False, indent=2)

    # B 部分: 代码计算结果
    sv = llm1_output.get("scenario_valuation", {})
    details = sv.get("scenario_details", {})
    computed_table = ""
    for s in ("bear", "base", "bull"):
        d = details.get(s, {})
        prob = d.get("probability", "?")
        up = d.get("upside_pct", "?")
        mcap = d.get("target_mcap_yi", "?")
        computed_table += f"  {s}: prob={prob}, upside={up}%, target_mcap={mcap}亿\n"
    beta_part = f"""概率加权: upside={computed.get('probability_weighted_upside_pct','?')}%, mcap={computed.get('probability_weighted_mcap_yi','?')}亿, asymmetry={computed.get('asymmetry_ratio','?')}x
ROIC审计警告: {json.dumps(roic_warnings or [], ensure_ascii=False)}
跨族底线校验: {json.dumps(mandatory_xcheck or {}, ensure_ascii=False, indent=2)[:500]}"""

    # C 部分: 完整市场定价数据
    anchor_2a = "earnings"
    if agent2a_output:
        anchor_2a = agent2a_output.get("market_narrative", {}).get("primary_anchor", "earnings")

    wacc_pct = wacc_params.get('wacc_pct', 10)
    if anchor_2a == "earnings":
        bs_text = f"""反向 DCF (利润锚):
  隐含永续增速 g = {bs_profile.get('implied_g_pct',0)}% (WACC={wacc_pct}%)
  EV: {bs_profile['ev_yi']}亿 NOPAT: {bs_profile['nopat_yi']}亿 ROIC: {bs_profile['roic_pct']}%
  g/WACC比值: {bs_profile.get('implied_g_pct',0) / max(wacc_pct, 1) * 100:.0f}%"""
    else:
        bs_text = f"BS画像: {json.dumps({k: v for k, v in bs_profile.items() if k not in ('ev_yi', 'nopat_yi')}, ensure_ascii=False)[:300]}"

    market_data = f"""当前PE: {bs_profile.get('pe_ttm','?')}x  PB: {bs_profile.get('pb','?')}x  PS: {bs_profile.get('ps_ttm','?')}x
市值: {core.get('market_cap_yi','?')}亿
{bs_text}
{bs_profile.get('note_to_llm', '')}"""

    # D 部分: 完整上下文（baseline + 2a + 事件 + 财务 + WACC）
    baseline_section = ""
    if baseline_report and len(baseline_report) > 100:
        baseline_section = f"\n## 投资地图\n{baseline_report}\n"

    a2a_section = ""
    if agent2a_output:
        mn = agent2a_output.get("market_narrative", {})
        ep = agent2a_output.get("event_pricing", {})
        sa = agent2a_output.get("signal_audit", {})
        pa = ep.get("pricing_assessment", {})
        a2a_section = f"""
估值锚: {mn.get('primary_anchor','?')}
SOTP触发: {mn.get('sotp_triggered', False)}
事件分布形状: {ep.get('event_profile',{}).get('distribution_shape','?')}
计价程度: {pa.get('overall_priced_in','?')} ({pa.get('priced_in_estimate','?')})
剩余催化: {pa.get('residual_catalyst','?')[:200]}
信号评分: {sa.get('step2d_score','?')}/10 — {sa.get('score_rationale','?')[:200]}
"""

    wacc_text = f"WACC={wacc_params.get('wacc_pct',10)}% (rf={wacc_params.get('rf_pct','?')}% beta={wacc_params.get('beta','?')} ERP={wacc_params.get('erp_pct','?')}%)"

    # ── 组装初始上下文 ──
    context = f"""# 审阅任务: {stock}({code})

## A 部分: LLM-1 参数推演输出
{alpha_json}

## B 部分: 代码计算估值结果
{computed_table}
{beta_part}

## C 部分: 当前市场定价
{market_data}

## D 部分: 上下文数据
{baseline_section}
## Agent-2a 诊断结论
{a2a_section}
## WACC参数
{wacc_text}

## 路由判决
主模型: {primary} ({routing.get('model_category','')})
路由理由: {routing.get('routing_reason','')}

## 事件素材
{json.dumps({k: str(v)[:500] for k, v in event_data.items() if k != 'raw_event_text'}, ensure_ascii=False, indent=2)}

## 预搜索结果
{volc_pre_search if volc_pre_search else '无预搜索结果'}
"""

    # ── 多轮对话 + 并行搜索 ──
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 初始用户消息
    initial_user_msg = context
    sp = system_prompt or LLM2_SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": sp},
        {"role": "user", "content": initial_user_msg},
    ]

    all_searches = []
    for round_num in range(max_rounds):
        t_round = time.time()
        print(f"  [LLM-2] 轮次 {round_num + 1}/{max_rounds} 开始 (消息历史 {len(messages)} 条)...", flush=True)
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": "deepseek-v4-pro",
                "messages": messages,  # ← 带完整历史，不是单条大字符串
                "max_tokens": 40960,
                "temperature": 0.1,
                "thinking": {"type": "enabled"},
            },
            timeout=600,
        )
        resp.raise_for_status()
        usage = resp.json().get("usage", {})
        print(f"  [LLM-2] 轮次 {round_num + 1} 完成 prompt={usage.get('prompt_tokens',0)} completion={usage.get('completion_tokens',0)} latency={time.time()-t_round:.1f}s", flush=True)
        content = resp.json()["choices"][0]["message"]["content"]
        result = _parse_json(content)

        # 检查是否需要更多搜索
        search_requests = result.get("search_requests", [])
        if not search_requests:
            print(f"  [LLM-2] 无更多搜索请求，输出最终报告", flush=True)
            return result  # 完成——最终报告

        # 每轮最多 2 条搜索——截断多余的
        search_requests = search_requests[:2]
        print(f"  [LLM-2] 发起 {len(search_requests)} 条并行搜索...", flush=True)
        # 并行执行所有搜索
        search_results = []
        with ThreadPoolExecutor(max_workers=len(search_requests)) as executor:
            futures = {
                executor.submit(_call_volc_search, sr.get("query", ""), sr.get("purpose", "")): sr
                for sr in search_requests
            }
            for future in as_completed(futures):
                sr = futures[future]
                try:
                    volc_res = future.result()
                except Exception:
                    volc_res = f"搜索失败: {sr.get('query', '')}"
                search_results.append({
                    "query": sr.get("query", ""),
                    "purpose": sr.get("purpose", ""),
                    "result": volc_res,
                })
        all_searches.extend(search_results)
        print(f"  [LLM-2] {len(search_results)} 条搜索完成", flush=True)

        # 将搜索结果作为 assistant + user 追加到对话历史
        search_text = "\n".join(
            f"查询: {s['query']}\n目的: {s['purpose']}\n结果: {s['result']}"
            for s in search_results
        )
        # LLM 本轮输出（含 search_requests 的 JSON）作为 assistant 消息
        assistant_msg = json.dumps(result, ensure_ascii=False, indent=2)
        messages.append({"role": "assistant", "content": assistant_msg})
        # 搜索结果作为 user 消息
        messages.append({"role": "user", "content": f"## 搜索轮次 {round_num + 1} 结果\n\n{search_text}\n\n请基于以上搜索结果继续审阅。如需更多搜索，输出 search_requests；否则输出最终报告（不含 search_requests）。"})

    # 达到最大轮次——返回最后一轮结果
    print(f"  [LLM-2] 达到最大轮次 {max_rounds}，返回最后一轮结果", flush=True)
    return result


def _call_volc_search(query: str, purpose: str = "") -> str:
    """调用火山引擎搜索。返回搜索结果文本。"""
    try:
        from agent_volc import _call_volc_engine
        resp = _call_volc_engine(query)
        if isinstance(resp, dict):
            return resp.get("answer", json.dumps(resp, ensure_ascii=False)[:2000])
        return str(resp)[:2000]
    except Exception:
        return f"搜索不可用: {query}"


def _extract_search_queries(llm1_output: dict) -> list:
    """从 LLM-1 输出中提取预搜索关键词。"""
    queries = []
    # 从 change_request 提取
    for cr in llm1_output.get("change_request", []):
        if isinstance(cr, dict) and cr.get("query"):
            queries.append(cr["query"])
    # 从 data_gaps 提取关键词
    for gap in llm1_output.get("data_gaps", []):
        if isinstance(gap, str) and len(gap) > 10:
            # 取前 60 字符作为搜索关键词
            queries.append(gap[:60])
    return queries[:5]  # 最多 5 个预搜索


def _apply_llm2_changes(llm1_output: dict, llm2_output: dict) -> bool:
    """将 LLM-2 的参数修改应用到 LLM-1 输出。返回是否有修改。"""
    changes = llm2_output.get("change_log", [])
    if not changes:
        return False

    details = llm1_output.get("scenario_valuation", {}).get("scenario_details", {})
    if isinstance(details, list):
        details = {item.get("name", item.get("scenario", "")): item for item in details}
        llm1_output["scenario_valuation"]["scenario_details"] = details

    for change in changes:
        path = change.get("path", "")
        new_val = change.get("new_value")
        parts = path.split(".")
        target = details
        for part in parts[:-1]:
            target = target.get(part, {})
        if parts[-1] in target:
            old = target[parts[-1]]
            target[parts[-1]] = new_val
            change["old_value"] = old

    # 追加修改记录到 reasoning_trace
    llm1_output.setdefault("reasoning_trace", []).append(
        f"[LLM-2 参数修改] 应用了 {len(changes)} 条修改: "
        + "; ".join(f"{c['path']}: {c.get('old_value','?')} → {c['new_value']} ({c.get('reason','?')[:50]})"
                    for c in changes)
    )
    return True


def _merge_llm_outputs(llm1_output: dict, llm2_output: dict) -> dict:
    """以 LLM-2 的完整输出为主体，LLM-1 作为兜底。

    LLM-2 已输出完整报告（含 scenario_valuation、reasoning_trace 等）。
    用 LLM-2 覆盖同名字段，仅保留 LLM-1 独有的元数据字段。
    """
    if not llm2_output:
        # LLM-2 完全故障：用 LLM-1
        return llm1_output

    # 以 LLM-2 为主体，LLM-1 兜底缺失字段
    for key in llm1_output:
        if key not in llm2_output:
            llm2_output[key] = llm1_output[key]

    # 叙事合并: LLM-1 在前，LLM-2 审阅意见追加在后
    llm1_narrative = llm1_output.get("narrative", "")
    llm2_note = llm2_output.get("_review_note", "") or llm2_output.get("narrative", "")
    if llm1_narrative and llm2_note and llm2_note != llm1_narrative:
        llm2_output["narrative"] = llm1_narrative + "\n\n【审阅修正】" + llm2_note
    elif llm1_narrative:
        llm2_output["narrative"] = llm1_narrative

    # 保留审计痕迹
    llm2_output["_llm1_original"] = {
        "scenario_valuation": llm1_output.get("scenario_valuation"),
        "reasoning_trace": llm1_output.get("reasoning_trace"),
    }
    llm2_output["_llm2_change_log"] = llm2_output.get("change_log", [])
    llm2_output["_llm_split_version"] = "2-call"

    return llm2_output


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
    elif m == "K":
        # 两阶段 DCF: 阶段1(高增长N年) + 阶段2(终值PE)
        # LLM控制: stage1_growth_pct, stage1_years, terminal_pe, roic_assumed_pct
        g1 = params.get("stage1_growth_pct", 0) / 100
        years = int(params.get("stage1_years", 5) or 5)
        term_pe = params.get("terminal_pe", 0)
        roic_k = params.get("roic_assumed_pct", 0) / 100
        wacc_k = core.get("_wacc_decimal", 0.10)

        if term_pe <= 0 or roic_k <= 0:
            return None

        nopat = core.get("nopat_yi", 0.01)
        pv_stage1 = 0.0
        for t in range(1, min(years, 10) + 1):
            nopat = nopat * (1 + g1)
            rr = g1 / roic_k if roic_k > 0 else 0.0
            rr = max(0.0, min(0.9, rr))  # RR in [0%, 90%]; g=0→RR=0(no reinvestment needed)
            fcff = nopat * (1 - rr)
            pv_stage1 += fcff / (1 + wacc_k) ** t

        # 终值 = 第N年NOPAT × terminal_PE
        tv = nopat * term_pe
        pv_tv = tv / (1 + wacc_k) ** min(years, 10)

        return round(pv_stage1 + pv_tv, 1)
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
# Step 1.7: ROIC-CAGR 一致性审计 (Q2)
# ═══════════════════════════════════════

def _audit_roic_consistency(llm_output: dict, core: dict, wacc_params: dict) -> list[dict]:
    """检查 base 的 CAGR 和 ROIC 恢复路径是否自洽。

    不约束当期 ROIC（滞后财务数据不应误杀反转故事），
    但要求 LLM 在自己选择的 CAGR 和 ROIC 目标之间保持逻辑一致性。
    """
    warnings = []
    sv = llm_output.get("scenario_valuation", {})
    details_raw = sv.get("scenario_details", {})
    if isinstance(details_raw, list):
        details = {item.get("scenario", ""): item for item in details_raw}
    else:
        details = details_raw

    base = details.get("base", {})
    narrative = base.get("scenario_narrative", "")

    # 提取 base CAGR: 不同模型族字段名不同
    base_cagr = base.get("revenue_growth_3y_cagr_pct") or base.get("stage1_growth_pct") or 0
    wacc_pct = wacc_params.get("wacc_pct", 10)

    if base_cagr <= 20:
        return warnings  # 低增速不需要审计

    # 检查 ROIC 相关关键词是否出现在 base 叙事中
    roic_keywords = ["ROIC", "roic", "投入资本回报", "资本回报", "覆盖WACC", "覆盖资金成本",
                      "价值创造", "回报率改善", "利润率提升至"]
    has_roic_path = any(kw in narrative for kw in roic_keywords)

    if not has_roic_path and base_cagr > 30:
        warnings.append({
            "code": "E308", "severity": "warning",
            "message": (f"Base CAGR={base_cagr}%但场景叙事未说明ROIC恢复路径。"
                       f"高增长+低资本回报的组合意味着增长在加速价值毁灭。"
                       f"请在scenario_narrative中补充: ROIC如何从当前水平改善至覆盖WACC({wacc_pct}%)？"),
            "action": "降置信度一档(若财报可行性评分>=7则强制降至<=6)",
        })

    # 交叉检查: 如果叙事中提到毛利率修复但没提 ROIC
    gm_keywords = ["毛利率", "净利率", "利润率", "gross margin", "net margin"]
    has_gm_path = any(kw in narrative.lower() for kw in gm_keywords)
    if has_gm_path and not has_roic_path and base_cagr > 25:
        warnings.append({
            "code": "E308b", "severity": "warning",
            "message": (f"Base叙事讨论了利润率修复但未涉及ROIC改善。"
                       f"利润率改善不一定意味着ROIC改善（若IC同步膨胀）。"
                       f"请确认: 增长是否需要大量资本投入？若是，ROIC路径是什么？"),
            "action": "提示供人工审阅，不自动降级",
        })

    return warnings


# ═══════════════════════════════════════
# Step 1.8: 强制跨族底线校验 (Q1)
# ═══════════════════════════════════════

def _mandatory_cross_validation(core: dict, llm_output: dict,
                                 routing: dict | None = None) -> dict | None:
    """无论 LLM 选了什么校验策略，代码层强制运行资产族底线校验。

    针对重资产/高负债的亏损公司——即使叙事是 revenue 驱动的，
    PB-ROE 也应作为独立底线参照，防止 PS 模型无限上浮。
    """
    total_assets = core.get("total_assets_yi", 0)
    total_equity = core.get("total_equity_yi", 1)
    if total_assets / max(total_equity, 1) <= 1.5:
        return None  # 非重资产公司，不适用

    bps = core.get("bps", 0)
    total_shares = core.get("total_shares_yi", 1)
    book_value_bps = bps * total_shares if bps > 0 else 0
    # 取较大值防御数据不一致（bps×股数 vs 净资产总额可能因口径不同有差异）
    book_value = max(book_value_bps, total_equity) if book_value_bps > 0 else total_equity

    # PB底线: 制造业重资产公司熊市PB参考 (1.0-1.5x)
    debt_ratio = core.get("debt_to_assets_pct", 50)
    roic = core.get("roic_pct", 0)

    # 根据负债率和ROIC分层确定保守PB
    if debt_ratio > 65 and roic < 0:
        floor_pb = 1.0   # 高负债+亏损 → 资产清算价值
    elif debt_ratio > 50 or roic < 5:
        floor_pb = 1.5   # 中等风险 → 略高于账面
    else:
        floor_pb = 2.0   # 相对健康

    floor_mcap = book_value * floor_pb

    # 取主模型 base target
    sv = llm_output.get("scenario_valuation", {})
    details_raw = sv.get("scenario_details", {})
    if isinstance(details_raw, list):
        details = {item.get("scenario", ""): item for item in details_raw}
    else:
        details = details_raw
    base_mcap = details.get("base", {}).get("target_mcap_yi", 0)

    if base_mcap <= 0 or floor_mcap <= 0:
        return None

    ratio = base_mcap / floor_mcap

    result = {
        "_code_enforced": True,
        "validation_model": "D(PB-ROE)",
        "validation_paradigm": "资产底线",
        "base_target_mcap_yi": base_mcap,
        "validation_mcap_yi": round(floor_mcap, 1),
        "gap_pct": round((base_mcap - floor_mcap) / floor_mcap * 100, 1),
        "detail": {
            "book_value_yi": round(book_value, 1),
            "floor_pb": floor_pb,
            "debt_ratio_pct": debt_ratio,
            "roic_pct": roic,
            "mcap_to_book_ratio": round(base_mcap / book_value, 1) if book_value > 0 else 0,
        },
    }

    if ratio > 3.0:
        result.update({
            "gap_direction": "主模型显著高估(>3x净资产底线)",
            "assessment": "严重偏离: 主模型base估值为净资产底线的{:.0f}倍，PS框架可能过度膨胀。请重新审视PS倍数的合理性。".format(ratio),
        })
    elif ratio > 2.0:
        result.update({
            "gap_direction": "主模型偏高(>2x净资产底线)",
            "assessment": "存在分歧: 主模型base估值为净资产底线的{:.0f}倍。若叙事破裂，估值可能向资产价值回归。".format(ratio),
        })
    else:
        result.update({
            "gap_direction": "基本一致",
            "assessment": "主模型与资产底线估值在合理范围内。",
        })

    return result


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

    # ── E400: 终端倍数离群检测 ──
    # PS/PE应锚定同行业可比公司的实际交易数据。代码层只拦截极端值。
    for sn in ("base", "bull"):
        d = details.get(sn, {})
        # PS离群: 超过40x几乎不可能来自可比公司锚定→必然是现价缩放
        target_ps = d.get("target_ps", 0)
        if target_ps > 40:
            warnings.append({
                "code": "E400", "severity": "warning",
                "message": f"{sn} target_PS={target_ps}x。任何行业的稳态PS都不应超过40x——检查:你的可比公司参照系是什么？它们实际交易在什么PS？",
                "action": "降置信度一档。",
            })
        # PE离群: 超过80x几乎不可能是稳态PE
        pe_target = d.get("pe_target", 0) or d.get("terminal_pe", 0)
        if pe_target > 80:
            warnings.append({
                "code": "E401", "severity": "warning",
                "message": f"{sn} PE={pe_target}x超过任何行业的稳态PE区间。>80x仅可能是盈利低谷过渡期——确认不是误用。",
                "action": "降置信度一档",
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

    # 归一化: 旧版扁平 confidence → 新版 dimensions 嵌套格式
    if "dimensions" not in confidence:
        old_keys = {
            "info_quality": ["info_quality", "data_reliability", "information_quality"],
            "financial_feasibility": ["financial_feasibility", "forecast_accuracy"],
            "valuation_safety": ["valuation_safety", "model_appropriateness"],
            "historical_precedent": ["historical_precedent", "narrative_consistency"],
        }
        dims = {}
        for new_key, old_aliases in old_keys.items():
            score = 5
            note = ""
            for alias in old_aliases:
                if alias in confidence:
                    score = confidence.pop(alias)
                    break
            # 从 notes 字段提取
            if "notes" in confidence:
                note = str(confidence.pop("notes"))[:100]
            dims[new_key] = {"score": score, "label": {"info_quality": "信息质量", "financial_feasibility": "财务可行性", "valuation_safety": "估值安全边际", "historical_precedent": "历史案例匹配"}[new_key], "note": note}
        confidence["dimensions"] = dims

    # 归一化: monitoring_kpis 键名
    kpis = llm_output.get("monitoring_kpis", {})
    if kpis:
        key_map = {
            "event_progress_kpis": "event_milestone_kpis",
            "valuation_marker_kpis": "competition_signal_kpis",
        }
        for old_k, new_k in key_map.items():
            if old_k in kpis and new_k not in kpis:
                kpis[new_k] = kpis.pop(old_k)
        # 字符串 → 对象
        for cat in ("financial_verification_kpis", "event_milestone_kpis", "competition_signal_kpis", "risk_trigger_kpis"):
            items = kpis.get(cat, [])
            if items and isinstance(items[0], str):
                kpis[cat] = [{"name": s, "baseline": "待观测", "target": "待定", "frequency": "季度"} for s in items]

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

    # ── 修正: LLM 误判自校验降级 ──
    # 当主模型≠校验模型时，不应出现"同模型自校验"后缀。
    # LLM 可能因校验模型硬约束不适用而误套自校验降级规则——但 B≠C 就是跨族校验，标签事实错误。
    v_model_raw = vx.get("validation_model", "")
    if not v_model_raw:
        v_model_raw = (routing.get("validation_models") or [None])[0] or ""
    if v_model_raw:
        v_model_letter = v_model_raw[0]
        if v_model_letter != model:
            old_assess = vx.get("assessment", "")
            # 剔除 "(同模型自校验)" / "(同模型自校验,缺乏独立验证)" / "（同模型自校验，缺乏独立范式验证）"
            import re as _re_assess
            new_assess = _re_assess.sub(
                r'\s*[\(（]同模型自校验[^)）]*[\)）]', '', old_assess
            ).strip()
            if new_assess != old_assess:
                vx["assessment"] = new_assess
                vx["_assessment_selfcheck_stripped"] = True

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
        },
        "reverse_dcf": rd,
        "validation_crosscheck": vx,
        "_code_cross_validation": llm_output.get("_code_cross_validation"),
        "expectation_gap": llm_output.get("expectation_gap", {}),
        "confidence": confidence,
        "trade_annotation": ta,
        "monitoring_kpis": llm_output.get("monitoring_kpis", {}),
        "reasoning_trace": _augment_trace_with_fixes(
            llm_output.get("reasoning_trace", []),
            sv,
            llm_original_values or {},
        ),
        "preflight_check": llm_output.get("preflight_check", []),
        "probability_rationale": llm_output.get("probability_rationale", ""),
        "risk_triggers": llm_output.get("risk_triggers", {}),
        "narrative": llm_output.get("narrative", ""),
        "data_gaps": llm_output.get("data_gaps", []),
        "growth_path_decomposition": llm_output.get("growth_path_decomposition"),
        "signal_audit": llm_output.get("signal_audit", {}),
        "scenarios": scenarios,
        "case_comparison_summary": llm_output.get("case_comparison_summary", {}),
        "_validation_warnings": validation_warnings,
        "_llm2_change_log": llm_output.get("_llm2_change_log", llm_output.get("change_log", [])),
        "_llm_split_version": llm_output.get("_llm_split_version", "1-call"),
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
        progress_cb: Callable[[int, str], None] | None = None,
        agent2a_output: dict | None = None,
        volc_data: dict | None = None,
        baseline_report: str | None = None,
    ) -> dict:
        """
        执行完整推演裁决 — V8 双 LLM 架构。

        LLM-1: 事件→基本面→参数（Prompt 禁止市值锚定）
        代码层: 参数→估值计算 + ROIC审计 + 跨族校验
        LLM-2: 多轮搜索审阅 + 参数修正 + 最终报告

        data_package: Agent-1 DataForge 输出
        routing_decision: Agent-2b routing_decision 部分
        event_data: Coze Agent0 输入
        agent2a_output: Agent-2a 叙事诊断输出
        volc_data: 火山联网搜索补充数据
        baseline_report: Agent-Baseline 投资地图报告
        """
        cb = progress_cb or (lambda s, n: None)
        event_data = event_data or {}
        stock_code = data_package.get("stock_code", "")
        primary = routing_decision.get("primary_model", "A")
        core_fields = data_package.get("packages", {}).get("core", {}).get("fields", {})
        core_fields["_wacc_decimal"] = 0.10  # default, will be overwritten

        # ── Step 0: WACC + BS 预计算 ──
        cb(1, "WACC/BS预计算")
        wacc_params = precompute_wacc(self.fetcher, stock_code, data_package)
        core_fields["_wacc_decimal"] = wacc_params.get("wacc_pct", 10) / 100
        anchor = (agent2a_output or {}).get("market_narrative", {}).get("primary_anchor", "earnings")
        bs_profile = precompute_bs_profile(primary, data_package, wacc_params, anchor)

        # ── Step 1: LLM-1 参数推演 ──
        cb(2, "LLM-1 参数推演")
        try:
            llm1_output = _call_llm_scenario(
                bs_profile, wacc_params, data_package,
                routing_decision, event_data,
                agent2a_output=agent2a_output,
                volc_data=volc_data,
                baseline_report=baseline_report,
            )
        except ScenarioError as e:
            cb(3, f"LLM-1 故障: {e.code}")
            if e.code in ("E302", "E303"):
                try:
                    llm1_output = _call_llm_scenario(
                        bs_profile, wacc_params, data_package,
                        routing_decision, event_data,
                        agent2a_output=agent2a_output,
                        volc_data=None,  # 重试时省略火山数据
                        baseline_report=baseline_report,
                    )
                except ScenarioError:
                    raise
            else:
                raise

        # ── Step 1.5: 代码计算（LLM-1 出参数，代码出数字）──
        cb(3, "代码计算")
        sv_pre = llm1_output.get("scenario_valuation", {})
        _llm_orig = {
            "upside": sv_pre.get("probability_weighted_upside_pct", None),
            "asymmetry": sv_pre.get("asymmetry_ratio", None),
            "mcap": sv_pre.get("probability_weighted_mcap_yi", None),
        }
        computed = _compute_from_assumptions(
            llm1_output.get("scenario_valuation", {}), primary, core_fields,
        )
        sv = llm1_output.get("scenario_valuation", {})
        sv["probability_weighted_upside_pct"] = computed["probability_weighted_upside_pct"]
        sv["probability_weighted_mcap_yi"] = computed["probability_weighted_mcap_yi"]
        sv["asymmetry_ratio"] = computed["asymmetry_ratio"]
        sv["_computed_by_code"] = True

        # ── Step 1.7: ROIC-CAGR 一致性审计 ──
        cb(3.5, "ROIC-CAGR审计")
        roic_warnings = _audit_roic_consistency(llm1_output, core_fields, wacc_params)
        if roic_warnings:
            print(f"  [Agent3 roic-audit] warnings: {[w['code'] for w in roic_warnings]}", flush=True)

        # ── Step 1.8: 强制跨族底线校验 ──
        cb(3.7, "跨族底线校验")
        mandatory_xcheck = _mandatory_cross_validation(
            core_fields, llm1_output, routing_decision,
        )
        if mandatory_xcheck:
            existing_xcheck = llm1_output.get("validation_crosscheck", {})
            if existing_xcheck and existing_xcheck.get("validation_strategy") == "self_validation":
                mandatory_xcheck["_overrides_llm_selfcheck"] = True
            llm1_output["_code_cross_validation"] = mandatory_xcheck

        # ── Step 2a: volc 预搜索（从 LLM-1 的 data_gaps + change_request 提取关键词）──
        cb(4, "volc 预搜索")
        pre_search_queries = _extract_search_queries(llm1_output)
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

        # ── Step 2b: LLM-2 多轮搜索审阅 ──
        cb(4.5, "LLM-2 审阅")
        try:
            llm2_output = _call_llm2(
                llm1_output, computed, bs_profile, wacc_params,
                data_package, routing_decision, event_data,
                agent2a_output=agent2a_output,
                baseline_report=baseline_report,
                roic_warnings=roic_warnings,
                mandatory_xcheck=mandatory_xcheck,
                volc_pre_search=volc_pre_search,
            )
        except Exception:
            # LLM-2 故障 → 降级: 用 LLM-1 输出 + 代码修正
            print("  [Agent3] LLM-2 故障，降级为 LLM-1 + 代码修正模式", flush=True)
            import traceback
            traceback.print_exc()
            llm2_output = {
                "confidence": {"overall_score": 4, "overall_label": "低",
                               "dimensions": {
                                   "info_quality": {"score": 5, "label": "信息质量", "note": "LLM-2未执行，降级为默认值"},
                                   "financial_feasibility": {"score": 5, "label": "财务可行性", "note": "LLM-2未执行"},
                                   "valuation_safety": {"score": 3, "label": "估值安全边际", "note": "LLM-2未执行"},
                                   "historical_precedent": {"score": 5, "label": "历史案例匹配", "note": "LLM-2未执行"}}},
                "trade_annotation": {"tier": "☆☆☆ 规避", "total_score": "4/10",
                                     "dimension_scores": {"odds_quality": 1, "pricing_headroom": 1,
                                                         "transmission_confidence": 1, "model_consistency": 1},
                                     "tier_note": "LLM-2未执行，降级为保守默认值"},
            }

        # ── Step 2.5: LLM-2 输出为主体，代码在其参数上重算 ──
        cb(5, "合并+重算")
        llm_output = _merge_llm_outputs(llm1_output, llm2_output)

        # 在 LLM-2 的参数上重新计算（如果 LLM-2 改了参数）
        computed = _compute_from_assumptions(
            llm_output.get("scenario_valuation", {}), primary, core_fields,
        )
        sv = llm_output.get("scenario_valuation", {})
        sv["probability_weighted_upside_pct"] = computed["probability_weighted_upside_pct"]
        sv["probability_weighted_mcap_yi"] = computed["probability_weighted_mcap_yi"]
        sv["asymmetry_ratio"] = computed["asymmetry_ratio"]
        sv["_computed_by_code"] = True

        # ── Step 3: 修复交易标注 ──
        cb(5.5, "修正交易标注")
        ta = llm_output.get("trade_annotation", {})
        details_raw = sv.get("scenario_details", {})
        if isinstance(details_raw, list):
            details = {item.get("scenario", item.get("name", "")): item for item in details_raw}
        else:
            details = details_raw
        bear_u = details.get("bear", {}).get("upside_pct", 0)
        bull_u = details.get("bull", {}).get("upside_pct", 0)
        llm_output["trade_annotation"] = _fix_trade_annotation(
            ta, computed["probability_weighted_upside_pct"],
            computed["asymmetry_ratio"], bear_u, bull_u,
        )

        # ── Step 4: 代码校验 ──
        cb(5.7, "一致性校验")
        validation_warnings = _validate_output(llm_output, bs_profile, wacc_params)
        validation_warnings = [w for w in validation_warnings if not w.get("code", "").startswith("E306")]
        validation_warnings.extend(roic_warnings)
        if validation_warnings:
            print(f"  [Agent3 validation] warnings: {[w['code'] for w in validation_warnings]}", flush=True)

        # ── Step 5: 组装输出 ──
        cb(6, "组装输出")
        output = _assemble_final_output(
            llm_output, bs_profile, data_package, routing_decision, validation_warnings,
            llm_original_values=_llm_orig,
        )

        cb(7, "推演裁决完成")
        return output


# ── 便捷函数 ──

def run_scenario_asymmetry(
    data_package: dict,
    routing_decision: dict,
    event_data: dict | None = None,
) -> dict:
    """便捷入口。"""
    agent = ScenarioAsymmetry()
    return agent.run(data_package, routing_decision,
                     event_data=event_data)
