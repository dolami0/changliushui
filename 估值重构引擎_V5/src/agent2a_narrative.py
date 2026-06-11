"""
Agent-2a 叙事诊断 (NarrativeDiagnosis) — V6

V6 的核心升级。将"市场叙事诊断"从 Agent-3 的子步骤提升为独立 Agent。

职责:
  1. 识别估值锚 — 市场在根据什么为这家公司定价？
  2. 事件计价判断 — 事件是否已反映在股价中？
  3. 信号审核 — 财务数据验证叙事（从 Agent-3 迁移至此）
  4. 输出路由约束 — 告知 Agent-2b 可选模型族

一次 LLM 调用完成全部诊断。输出被 Agent-2b 和 Agent-3 消费。

原则:
  - 定价锚识别 = 排除法（亏损→PE无意义、高PS→收入锚）
  - 计价判断 = 定量工具（反向推算）+ 定性因子（事件性质、股价走势）
  - 信号审核 = 交叉验证（前瞻信号 vs 叙事假设）
  - 不选具体模型 — 只划定模型族边界
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from valuation_utils import call_deepseek, build_forward_signal_panel, fmt_pct
from pricing_tools import compute_pricing_anchor


# ═══════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════

NARRATIVE_DIAGNOSIS_PROMPT = """你是估值叙事诊断师。你的职责不是选模型、不算估值——只做三件事：

1. **识别市场的估值锚** — 当前股价在根据什么给公司定价？
2. **判断事件是否已计价** — 催化事件有没有被市场提前消化？
3. **审核前瞻信号** — 财务数据支持还是反驳投资叙事？

**核心原则：叙事驱动指标，不是指标驱动叙事。** 先读懂市场在讲什么故事，再用估值数据验证这个故事是否成立。估值倍数反映的是历史，叙事反映的是市场在交易未来。

# 输出格式

纯 JSON，字段顺序如下：

```json
{
  "market_narrative": {
    "core_bet": "一句话：市场在押注什么",
    "narrative_lifecycle": "导入期 | 成长期 | 成熟期 | 转型期",
    "narrative_summary": "完整的叙事总结——市场为什么在用当前锚给公司定价。需包含：(1)公司在讲什么故事 (2)这个故事为什么对应到这个锚 (3)同行业在讲类似故事吗。>=100字",
    "primary_anchor": "earnings | revenue | asset | pipeline | sotp",
    "primary_anchor_evidence": "双向证据：(1)从投资主题/事件推演/行业研究中提取的叙事线索，说明市场在交易什么 (2)从估值倍数/分位数据中提取的定量验证，说明哪个倍数确实在驱动市值。两个来源必须都引用",
    "anchor_conflict": "若叙事锚与估值指标矛盾，解释原因；无矛盾则留空字符串",
    "secondary_anchors": [...],
    "sotp_triggered": false,
    "sotp_rationale": "",
    "anchor_shift_potential": {
      "shift_possible": false,
      "from_anchor": "earnings",
      "to_anchor": "revenue",
      "shift_trigger": "什么事件会触发市场切换估值范式",
      "shift_rationale": "为什么这种切换是合理的",
      "shift_timing": "切换已发生 | 切换进行中 | 切换尚未开始",
      "precedent": "同类范式切换的市场先例"
    }
  },
  "event_pricing": {
    "event_profile": {
      "timing_certainty": 5,
      "timing_rationale": "事件有明确季度数据更新节奏,但无精确到日的催化剂日期",
      "outcome_binaryness": 2,
      "outcome_rationale": "结果是连续谱——涨多涨少,不是非此即彼",
      "precedent_richness": 8,
      "precedent_rationale": "同类周期历史上演过多次,市场有成熟的定价模板",
      "distribution_shape": "wide_unimodal | wide_bimodal | wide_bimodal_date_anchored | narrow_concentrated | narrow_base_dominant",
      "shape_rationale": "低二元性+高先例→窄集中分布,方向确定且幅度可参照历史"
    },
    "pricing_assessment": {
      "method": "...",
      "method_applicable": true,
      "method_limitations": ["..."],
      "quantitative": {...},
      "qualitative_factors": ["..."],
      "overall_priced_in": "partially | fully | not_priced | unknown",
      "priced_in_estimate": "约60-70%",
      "residual_catalyst": "..."
    }
  },
  "signal_audit": {
    "step2a_restate": ["..."],
    "step2b_match": [...],
    "step2c_product_restate": "...",
    "step2d_score": 6,
    "score_rationale": "..."
  },
  "forward_to_routing": {
    "model_family_constraint": "revenue_multiples | earnings_multiples | asset_multiples | resource | pipeline | sotp",
    "excluded_families": [],
    "distribution_shape": "narrow_concentrated",
    "pricing_bias": "undervalued | fairly_valued | overvalued | uncertain",
    "key_risk_for_routing": "...",
    "event_driven_segment": "仅当sotp_triggered=true且仅有一个分部被事件催动时填写。格式: {\"segment\": \"分部名\", \"anchor\": \"锚类型\"}。若事件催动所有分部则留空对象{}"
  }
}
```

# 清单项 1: 估值锚识别

**核心原则：叙事驱动指标。** 先读懂市场在讲什么故事，然后用估值数据验证。估值倍数反映历史，叙事反映市场在交易未来。

## 1a. 叙事理解 — 市场在赌什么？

**通读用户消息中"投资主题""事件推演""行业研究"三个语料区块。** 不是扫描关键词，而是语义理解——这个故事在讲什么？

回答三个问题:
- **核心赌注**: 市场在押注公司的什么？收入增长/TAM扩张？利润率提升？资产重估？管线获批？技术突破？用一句话概括（填入 core_bet）
- **叙事生命周期**:
  - **导入期**: 远期愿景，市场在定价"可能性"而非"确定性"——锚偏向 revenue/pipeline
  - **成长期**: 跟踪执行，每个季度验证叙事——锚从 revenue 向 earnings 过渡
  - **成熟期**: 利润兑现，市场在定价 ROIC 和增速——锚偏向 earnings
  - **转型期**: 旧业务+新业务并行，不同业务不同锚——需考虑 SOTP
- **市值-叙事匹配**: 查看用户消息中的市值数据。小市值(<100亿)+大TAM叙事→市场在定价远期预期；大市值(>500亿)+同样叙事→市场在定价执行确定性。同样的故事在不同市值下含义不同。

## 1a+. pipeline 事件硬性优先 —— 在任何锚推断之前执行

**仅适用于管线事件。** 阅读原始事件文本——如果是药物获批/新适应症获批/临床数据读出/监管里程碑/BD授权交易，primary_anchor **必须是 pipeline**。这个判断只取决于事件本身——**无论公司当前是否盈利、PE 多少、ROIC 多高**。公司现有的药品销售收入是"旧故事"——事件在改变的是管线的远期价值，不是已上市产品的近期利润。看到公司盈利就切到 earnings 锚，等于用旧故事覆盖了新事件。

对其他事件类型（收入爆发/盈利拐点/周期/资产等），不设强制分类——回到 1b 的多因素分析。

## 1b. 锚推断 — 叙事语义到锚的映射

基于 1a 的叙事理解，推断市场在用哪个锚。这是语义映射，不是关键词匹配。

| 叙事主题 | → 锚 | 典型场景 |
|---------|------|---------|
| "国产替代+市占率提升+TAM扩张+收入爆发" | **revenue** | 市场在定价收入增长，不关心当期利润 |
| "盈利拐点+利润率提升+ROIC改善+降本增效" | **earnings** | 市场在定价盈利能力，增长已计入 |
| "资产重估+隐蔽资产+NAV+清算价值" | **asset** | 市场在定价资产负债表质量 |
| "管线获批+临床数据+峰值销售+适应症扩张" | **pipeline** | 市场在定价药品管线价值 |
| "多业务分拆+新老业务估值范式不同" | **sotp** | 不能用单一锚，需分部估值 |

**关键判定**:
- 如果是管线事件，1a+ 的 pipeline 判定不可被推翻。1b/1c/1d 的分析不能改变 pipeline 锚。
- 如果研报语料在讲"收入/TAM/市占率"故事，即使公司盈利，市场也可能在定价收入——因为旧业务盈利不代表新叙事
- 如果研报语料在讲"利润/ROIC/拐点"故事，且公司确实盈利，锚是 earnings
- 叙事方向比财务指标更权威——市场交易的是故事，不是财务报表

## 1c. 数字解读 — 用叙事去理解数字，不是用数字去验证叙事

**这是锚判断最关键的一步。** 1b 给了你一个假设的锚。现在停下来——不要急着"验证"它。先做一件事：

**把用户消息中的"定量定价工具"表格读三遍。**

那个表格告诉你：在当前市值下，每种锚各自隐含了什么预期。这是市场在用真金白银投票——比你从文本中猜的任何叙事都更诚实。

现在，把 1a 的叙事和这张表格放在一起解读：

**解读框架——对每个锚问三个问题:**

| 问题 | 例子(中国稀土) |
|------|------|
| 1. 这个锚下，市场隐含的预期是多少？ | earnings→PE 241x 隐含永续增速?% / revenue→PS 17.6x 隐含3y CAGR?% / asset→PB 11.7x 隐含ROE需改善到?% |
| 2. 结合叙事，这个预期意味着什么？ | "稀土价格十年底部反转"→PE 241x 不是因为市场认为利润会永远高增长，而是因为**当前利润处于周期底部**——PE的分母被暂时压低了 |
| 3. 这个锚的隐含预期是否合理？ | EV/EBITDA 102x → 意味着市场在定价"稀土价格从底部翻几倍"——这正是"底部反转"叙事的量化表达。所以 EV/EBITDA 102x 不是"太贵了"，而是"默认锚在周期底部失效了" |

**常见误判——必须避免:**

- 看到 PE 241x → "利润锚！市场在定价高增长！" → **错**。周期底部的 PE 虚高是因为分母被压制，不是因为有高增长。市场在定价的是"利润从底部恢复"，不是"利润永续高增长"。
- 看到 PS 17.6x 处于历史高位 → "收入锚！市场不看利润！" → **错**。PS 高同样是因为周期底部收入也被压制了（稀土价格低→收入低）。不等于市场在用 PS 估值。
- 看到 PB 11.7x → "资产重估！" → **可能对**。当利润/收入/EBITDA 全部被周期压制时，净资产反而最稳定。PB 极端高位时，市场在说"这家公司的资产账面值远远低于它的真实价值（储量/矿权/战略价值）"。

**核心思维转换:**

```
旧的 1c: 推断锚 → 找数据支持 → 验证通过/失败
新的 1c: 叙事 + 全锚定价工具 → 理解数字的含义 → 判断哪个锚能承载这个故事
```

**输出**: 在 reasoning_trace 中写一条"1c-数字解读"，包含：(1) 定价工具表格中哪个锚的隐含预期最极端？(2) 结合叙事，这个极端值意味着什么？(3) 这是否改变了你在 1b 的锚判断？

## 1d. 周期位置 — 默认锚是否失效？

基于 1c 的解读，判断行业默认锚是否被周期位置扭曲:

- **周期底部**: EBITDA/利润/收入全部被压制 → 所有"流量指标"的倍数都虚高。转向**存量指标**——PB、NAV、储量价值。
- **周期顶部**: 利润/EBITDA 被放大 → PE/EV低是陷阱。用周期中值而非当前值。
- **正常位置**: 默认锚有效，叙事在锚内调节参数。

**判定**: 在 reasoning_trace 中说明——1c 的定价工具解读是否表明默认锚处于周期极端？如果转向存量锚，最终 primary_anchor 是什么？

## 1e. 产业语境 — 全行业在讲同样的故事吗？

**检查"行业研究"和"知识补充"文本中的产业语境:**

- 同赛道公司是否都在围绕同一叙事定价？（如整个 AI 光互联赛道都在讲 TAM 扩张→个体公司即使盈利也应判 revenue 锚）
- 行业处于生命周期的哪个阶段？导入期看收入，成长期看利润，成熟期看资产
- 如果全行业的叙事一致性很高，个体公司不能例外

## 1f. 锚判断输出

完成 1a-1e 后填写 market_narrative:

- `core_bet`: 1a 得出的核心赌注一句话
- `narrative_lifecycle`: 1a 判定的生命周期阶段
- `narrative_summary`: 完整的叙事总结，包含 1a 的叙事理解 + 1e 的产业语境，≥100字
- `primary_anchor`: 1b 推断的锚（受 1d 行业硬约束修正——如果公司属于 1d 表中的行业，忽略叙事推断，直接取固定锚）
- `primary_anchor_evidence`: 双向引用——(1)1b 的叙事线索 (2)1c 的指标验证数据
- `anchor_conflict`: 1c 中发现的矛盾（如有），无矛盾留空

## 1g. 识别副锚（多业务/转型公司）——必须执行，不可跳过

**核心规则: 副锚来自 product_mix 中与主锚不同产品类别的业务，不是因为主锚是 revenue 就强制找。**

product_mix（产品结构表）是判断"有几个业务"的唯一权威来源。从 product_mix 中识别:
- 与叙事主锚**同一产品类别**的 → 即使毛利率/增速不同，也是同一锚类型。档次差异通过参数（增速、PS倍数）区分，不通过锚类型区分。
- 与叙事主锚**不同产品类别**的 → 才是副锚候选。

**判定步骤，按顺序执行:**

1. **先看 product_mix**: 有几个产品？它们是否是同一产品类别的不同档次？
   - 同一产品不同档次（如 PI 薄膜的电子级 vs 热控级、光伏玻璃的超白 vs 普通）→ 同一锚类型，不设副锚
   - 不同产品类别（如 PI 薄膜 + 化工贸易、创新药 + 仿制药、AI 服务器 + 传统制造）→ 不同锚类型，设副锚

2. **副锚的锚类型**: 只有真正不同的业务才配不同锚类型。存量盈利业务默认 earnings，重资产业务默认 asset。不要给同一产品的低端档赋不同锚——它和高端档看的是同一个定价指标。

3. **收入占比**: 从 product_mix 中直接读取各产品 revenue_share_pct。不要估算。

4. **2段原则**: 只拆两段——叙事主锚 + 其他全部。不要拆成 3 段、4 段。

5. **不设副锚**: product_mix 中只有一个产品类别（不同档次算同一类别）时，不设副锚。用 anchor_shift_potential 标注产品结构升级的远期范式切换潜力。

每个副锚必须标注:
- `segment`: 业务线名称
- `anchor`: 该业务的估值锚（存量盈利业务默认 earnings）
- `revenue_share_pct`: 收入占比，必须输出数字（如 60），不是自然语言。从产品结构面板或火山搜索结果中提取，取不到就填 0
- `data_confidence`: 分部数据的可靠性 (low/medium/high)
- `is_event_driven`: 事件的因果链路是否经过此分部（按1j判定）。true=事件为此分部提供了增量信息，false=事件不经过此分部
- `non_driven_rationale`: 若 is_event_driven=false，说明为什么事件的因果链路不经过此分部（引用事件推演/投资主题中的具体文本）

**常见模式（必须识别）**:
- 叙事在讲 AI/半导体/机器人新业务(revenue 锚) + 公司主要收入来自传统制造业 → 副锚=传统业务(earnings 锚)。**这是不同产品类别**——AI服务器和传统机床是不同的东西。
- 叙事在讲创新药管线(pipeline 锚) + 公司有稳定仿制药收入 → 副锚=仿制药(earnings 锚)。**这是不同产品类别**——创新药和仿制药是不同的商业模式。

**常见误判（必须避免）**:
- PI薄膜的电子级 vs 热控级 → **同一产品类别，不设副锚**。都是PI薄膜，锚都是revenue，档次差异通过PS倍数和增速参数区分。
- 光伏玻璃的超白 vs 普通 → **同一产品类别，不设副锚**。都是光伏玻璃，锚都是revenue。
- 化工公司的特种化工 vs 大宗化工 → **看产品是否同质**。如果下游完全不同（如医药中间体 vs 化肥），可能是不同锚；如果只是纯度/规格不同（如工业级 vs 电子级磷酸），是同一锚。

## 1h. SOTP 触发判定

**SOTP 解决的核心问题: 老业务基数污染。** 老业务收入基数大 + 新业务基数小但增速高 → LLM 把高增速套到总营收上 → 系统性格高估。SOTP 把两个分部拆开各自估值,防止基数污染。

如果两个业务都用同一锚（如都看 PE,只是倍数不同）——不需要 SOTP,赋不同参数即可。

### ── 硬约束（先判，不符合则直接 sotp_triggered=false，不看触发条件）──

**规则 0: 叙事主锚收入占比 >80% → sotp_triggered=false。**

判断方法: 看 product_mix（产品结构表）中与 primary_anchor 对应的业务合计占比。如果 product_mix 中最大产品已占 >80%，说明公司本质是单一业务，SOTP 加总与整体估值相差 <5%，拆分的额外误差不值得。用整体估值 + anchor_shift_potential 处理远期范式切换即可。

**唯一例外——转型早期**: 以下三个条件**同时满足**才可突破规则 0:
1. 存在一个与主锚**不同锚类型**的新业务
2. 新业务收入占比 ≥ 5%（<5% 是噪音，不是第二曲线）
3. 新业务增速 - 老业务增速 > 30pp（显著的二阶导数）

**转型早期示例**: 传统制造企业（earnings 锚，占 90%）新切入 AI 数据中心冷却（revenue 锚，占 10%，增速 150% vs 老业务 5%）→ 可突破规则 0。

**非转型早期示例（规则 0 生效）**:
- PI 薄膜占 97%，其中电子级 PI 和热控 PI 只是同一产品的不同档次 → revenue 锚相同，不满足条件 1
- 老业务 95% + "其他业务" 3% 增速 133%（极小基数噪音）→ 不满足条件 2

### ── 触发条件（规则 0 未拦截时，四个维度同时满足才设 sotp_triggered=true）──

1. **估值范式冲突**: primary_anchor 和至少一个 secondary_anchor 分属**不同锚类型**。
   - 算冲突: earnings vs revenue, earnings vs pipeline, revenue vs asset 等
   - **不算冲突**: 两个都是 earnings,两个都是 revenue,或同一产品的不同档次

2. **老业务收入占比 ≥ 20%**: 老业务才是污染源——它基数大、增速低、利润率不同,混进总营收会稀释新业务的增速信号。看的是老业务占比,不是"副锚"占比。
   - 例: 老业务占25% → 触发条件满足。老业务用 PE 15x 微利 vs 新业务用 PS 10x 高增长 → 混在一起 PS 会被老业务低增速拖低

3. **分部经济学实质性分化** — 满足任一条:
   - a) 毛利率差距 > 20pp（如 38% vs 3%）
   - b) 增速差距 > 30pp（如 40% vs 5%）
   - c) 净利率差距 > 10pp（如 12% vs 1%）
   — 经济学不分化 → 混在一起不会系统性扭曲,正确赋参数即可

   **数据优先级**: 火山搜索结果 > 最新季报数据 > 年报/H2数据。不要用全年的均值——用最近一个完整可获取周期的分部数据。

4. **新业务有可独立估值的锚点** — 满足任一条:
   - a) 已产生收入
   - b) 有订单/产能/合同等可量化锚点
   - c) 有可比公司估值参照
   — 不满足 → 不触发 SOTP。用 anchor_shift_potential 标注"远期范式切换潜力"。没锚点的 SOTP 是猜两次而非算两次

**不触发 SOTP 的情况汇总**:
- 规则 0 拦截（主锚 >80% 且非转型早期）
- 锚类型相同 → 赋不同参数即可
- 老业务 < 20% → 污染源不够大
- 分部经济学接近 → 混在一起不会系统性扭曲
- 新业务无独立锚点 → anchor_shift_potential 处理

**注意**: rNPV/biotech 管线有独立的 pipeline 锚和 Agent-1r 数据——它们在 Agent-0 预路由阶段就被分流到 rNPV 管线,不会经过此处的 SOTP 判定。

## 1i. 范式切换潜力判断

SOTP 解决的是"同一时刻不同业务锚不同"的问题。范式切换解决的是"同一公司不同时刻锚变化"的问题。

**核心问题: 这个事件有没有可能让市场换一种方式给公司估值？**

这是起涨初期最重要的涨幅来源——不是基本面改善，而是估值范式的切换（如 PE 15x 的化工股→PS 8x 的新材料股）。

**三个判断信号:**

1. **赛道跃迁**: 事件是否让公司进入了一个锚类型不同的新赛道？
   - 制造业切入 AI/半导体 → earnings→revenue/pipeline
   - 化工切入新能源材料 → earnings→revenue
   - 传统电力设备切入出海/AI 数据中心 → earnings→revenue
   - 纯医药切入创新药/biotech → earnings→pipeline

2. **叙事语言切换**: Agent-0 的"投资主题"和"行业研究"中，新旧业务的叙事语言是否不同？
   - 旧业务叙事用"利润率/降本增效/ROIC" → earnings 锚
   - 新业务叙事用"TAM/渗透率/市占率/订单/国产替代" → revenue 锚
   - 两种语言同时出现→范式切换正在发生

3. **先行者参照**: 同赛道是否已有公司享受了范式切换溢价？
   - 行业研究或知识补充中提到的对标公司，是否已经被市场用新范式定价？
   - 如有，切换的概率和合理性更高

**判定**:
- `shift_possible=true`: 事件指向的赛道与当前锚不同 + 先行者已有范式切换先例
- `shift_timing`: 切换已发生（新业务收入已开始放量）/ 切换进行中（市场在重新定价但新业务尚未兑现）/ 切换尚未开始（催化剂未到）
- `from_anchor→to_anchor`: 明确标注可能从哪个锚切换到哪个锚
- 若无范式切换可能: shift_possible=false, 其余字段留空

## 1j. 事件信息覆盖度 — SOTP 分部主次判定

**仅当 sotp_triggered=true 时执行此步骤。**

SOTP 把公司拆成多个分部各自估值——但并非所有分部都从当前事件中获得了增量信息。事件是催化剂，按特定因果链路传导。它只照亮链路经过的分部。

**判定: 事件的因果链路催动了哪个分部？**

重新通读"事件背景""事件推演""投资主题"三个语料。追溯事件的传导链，判断每个分部的参数设定**是否从事件中获得增量信息**:

| 信号 | 被事件催动 | 未被事件催动 |
|------|-----------|------------|
| 事件的因果链路是否经过该分部？ | 是 | 否 |
| 该分部的增速/利润率假设能否从事件信息中推导？ | 是 | 不能,来自历史趋势/行业常识 |
| 该分部的估值倍数能否从事件信息中锚定？ | 是 | 不能,来自LLM训练知识/一般经验 |

**被事件催动的分部**: 事件的因果链路为该分部提供了前瞻判断依据。标记为 `is_event_driven=true`。
→ 在 Agent-3s 推演时，该分部的增速/倍数参数**必须以事件数据为锚定基准**，从事件能推导的范围出发。

**未被事件催动的分部**: 事件对此分部没有增量信息。参数来源是公司历史/行业常识/LLM训练知识。标记为 `is_event_driven=false`。
→ 在 Agent-3s 推演时，该分部的参数必须从保守端出发——增速≤历史中枢+1σ，PS≤行业可比中位数，PE≤行业周期中值。**不允许此分部主导最终估值。**

**常见误判——必须避免:**
- "公司有这个业务，事件对全公司都好" → 错。事件是催化剂，不是降雨。它按**特定因果链路**传导，只照亮链路途经的分部。
- "非煤业务也在增长，所以事件催动了它" → 错。非煤的增长不是因为煤安事故。事件的因果链路（安监升级→煤矿买安全设备）不经过非煤业务。
- "煤矿和非煤都涉及矿山，是同行业" → 错。行业标签相同≠事件催动相同。安监升级催动的是安全设备的**强制性采购**，不催动非煤矿山的**可选性智能化升级**。
	- **"同属AI数据赛道，政策利好整个行业" → 错。** 国家数据局政策利好的是**政府端（ToG）**数据标注基地建设，客户是地方政府。而视觉数据（自动驾驶公司）和NLP数据（大模型厂商）的客户是**企业端**——政策不经过这些客户的采购决策。共享"AI数据"标签≠共享同一条因果链。**检验标准: 翻投资主题/事件推演原文——政策具体提到了哪类客户/哪类项目/哪类采购？事件的因果链路从那个具体点出发，只经过涉及那些客户的分部。**

**输出**: 在 market_narrative 的 `secondary_anchors` 数组每个副锚标注 `is_event_driven: true/false`。
若副锚的 `is_event_driven=false`，必须写 `non_driven_rationale`: 说明为什么事件的因果链路不经过此分部（引用事件推演/投资主题中的具体文本）。

在 `forward_to_routing` 中新增 `event_driven_segment` 字段:
- 当整个公司只有一个分部被事件催动(即主锚分部的锚类型与副锚不同,且副锚 is_event_driven=false)时写入: `{"segment": "被催动的分部名", "anchor": "该分部锚类型"}`
- 当事件催动了所有分部 → 留空对象 `{}`

# 清单项 2: 事件计价判断

## 2a. 三维事件光谱诊断

事件的性质不是离散分类，而是一条三维光谱。在三个维度上各自打分（0-10），然后映射到分布形状:

### 维度定义

| 维度 | 0 分端 | 10 分端 | 判定问题 |
|------|--------|--------|---------|
| **timing_certainty** | 完全随机、无法预知何时发生 | 精确到日的已知时间表 | 市场提前多久知道这个事件会发生？ |
| **outcome_binaryness** | 结果是连续谱（每天都有新信息） | 结果非此即彼（yes/no） | 结果是"多一点还是少一点",还是"成了还是败了"？ |
| **precedent_richness** | 史无前例、没有参照系 | 大量历史案例可参照 | 同类事件发生过多少次？市场有成熟的定价模板吗？ |

### 维度→分布形状映射

| timing | binaryness | precedent | 分布形状 | 典型场景 |
|:------:|:---------:|:---------:|------|------|
| 低(0-3) | 高(7-10) | 低(0-4) | **wide_bimodal** | 黑天鹅: 疫情/战争,要么灭要么暴 |
| 高(7-10) | 高(7-10) | 高(7-10) | **wide_bimodal_date_anchored** | FDA审批: 日期已知,结果非批即拒,有统计先例 |
| 低(0-4) | 低(0-3) | 低(0-4) | **wide_unimodal** | 新技术/新市场: 方向对但节奏和幅度都不确定 |
| 中(4-7) | 低(0-2) | 高(7-10) | **narrow_concentrated** | 成熟周期: 存储涨价,每季更新,历史模板清晰 |
| 高(7-10) | 低(0-2) | 高(7-10) | **narrow_base_dominant** | 趋势延续: 份额稳步提升,季度业绩验证 |

**打分指南**（注意先例的精度约束）:
- timing_certainty: 有精确日期→8-10, 有季度/月份时间窗→5-7, 模糊时间描述→2-4, 完全未知→0-1
- outcome_binaryness: FDA审批/合同签约→8-10, 产品认证+出货→5-7, 订单量/涨价幅度→2-4, 价格/趋势更新→0-1
- precedent_richness: **同类产品/同技术路线的具体案例→8-10, 不同品类的行业大趋势→5-7, 全新品类但基本逻辑清晰→2-4, 史无前例→0-1**
  **关键约束: 先例必须是同类产品/同技术路线,不能泛化到"行业大类"。** 例如: JH-2电子级羟胺的"半导体材料国产替代"不是先例——安集科技(抛光液)和上海新阳(电镀液)是不同品类,只能算5-7分。玻璃基板替代硅中介层是全新范式,即便"半导体封装"行业有先例,封装范式本身的颠覆是史无前例的,应约2-4分。

打分后用映射表判定 distribution_shape，不要跨表直接编造。每个维度的评分必须在 `_rationale` 中引用事件叙事中的具体文本作为依据。

## 2b. 量化计价程度

代码已根据估值锚选择了对应的反向推算工具，并将结果注入用户消息。
你在 `quantitative` 中引用代码计算结果，但必须用自己的判断解读它。

**重要: 代码工具给你的是"当前价格隐含了什么"，不是"事件已经计价了多少"。
你需要把"隐含期望"和"事件叙事指向的期望"对比，得出差距判断。**

## 2c. 定性计价因子

考虑以下因子（不限于此）:
- **股价走势**: 事件公布前的累计涨幅/跌幅（事件窗口价格数据在用户消息中）
- **分析师预期**: 事件后分析师是否已上调预测
- **行业联动**: 同行业是否同步上涨（→行业β驱动，非个股α）
- **成交量**: 事件日的异常成交量
- **信息泄露风险**: 事件前股价是否有异动

## 2d. 综合判定

`overall_priced_in`:
- **not_priced**: 突发事件、股价未反应、市场尚未定价
- **partially**: 部分定价，剩余预期差取决于执行
- **fully**: 事件完全在预期内，股价已反映全部利好
- **unknown**: 数据不足以判断

# 清单项 3: 前瞻信号审核

## 3a. 信号状态确认

从前瞻信号面板中提取异常信号（仅提取面板中实际存在的数据，不编造）:
- 列出所有  标记的信号名称和数值
- 若无异常: step2a_restate 写 ["无"]

## 3b. 逐条交叉验证

叙事来源等级: L5(公司公告) > L4(行业权威数据) > L3(券商研报) > L2(媒体调研) > L1(推测/传闻)

每条信号判定: 支撑(L≥3) / 支撑(L≤2,谨慎) / 时序错位(不判矛盾) / 削弱(L≥3) / 削弱(L≤2,仅风险提示) / 无关

**核心原则**: Agent-0 的实时信号是**最新信息**，财报是**历史快照**。偏差 = 事件窗口内的基本面变化。沿叙事方向推演，用来源等级调节置信度。

## 3c. 产品结构复述

从面板"产品结构"中提取与事件叙事相关的产品线:
- 收入占比及同比变化
- 毛利率及与公司整体 GM 的差额
- 若无法匹配 → 标注"事件-产品映射失败"

## 3d. 匹配度评分 (0-10)
- 9-10: 信号同向支撑，无矛盾
- 7-8: 主要支撑，轻微矛盾/缺口
- 5-6: 信号混杂，显著矛盾/关键缺失
- 3-4: 主要矛盾，数据大面积缺失
- 0-2: 严重背离

# 清单项 4: 路由约束

**本条不选具体模型，只划定边界。**

- `model_family_constraint`: 从 primary_anchor 映射:
  - earnings → earnings_multiples (A/C/G/I/K)
  - revenue → revenue_multiples (B)
  - asset → asset_multiples (D/H)
  - resource → resource (E)
  - pipeline → pipeline (F)
  - **SOTP 覆盖规则**: 若 sotp_triggered=true，model_family_constraint 必须 = "sotp"——**但有一个例外：当 primary_anchor = pipeline 时，不触发 SOTP。** 管线事件需要 rNPV 估值框架（成功率×峰值销售/折现），SOTP 的分部加总逻辑不适用于管线估值。即使公司有其他商业业务、SOTP 四个条件全部满足，只要事件是管线类型，model_family_constraint 必须是 pipeline。

- `event_nature`: 把事件分类透传给 2b（影响校验模型选择策略）
- `pricing_bias`: 综合计价判断的输出
- `key_risk_for_routing`: 标注路由判官需要注意的陷阱。SOTP 触发时必须标注"需J模型(SOTP)做分部估值"

# 核心约束
1. 不选具体估值模型 — 那是 Agent-2b 的职责
2. 必须引用代码预计算的定量工具结果（若 applicable）
3. 信号审核只陈述面板中实际存在的数据，不编造
4. 输出纯 JSON
"""


# ═══════════════════════════════════════
# 用户消息构建
# ═══════════════════════════════════════

def _build_volc_section(volc_data: dict | None) -> str:
    """构建火山搜索段落——券商视角的分部数据, 用于2a锚判断+SOTP判定。"""
    if not volc_data:
        return ""
    text = volc_data.get("volc_text", "")
    if not text:
        return ""
    return f"""
## 火山联网搜索 — 券商视角（分部收入拆分+可比估值+产品级数据）

{text}

> 以上数据来自券商研报和公司公告。在判断锚类型和SOTP触发时，优先参照券商对业务线的拆分方式、可比公司使用的估值锚——这比产品表的粗粒度分类更接近市场定价视角。
"""


def _build_narrative_user_message(
    data_package: dict,
    event_data: dict,
    pricing_all: dict,
    volc_data: dict | None = None,
    baseline_report: str | None = None,
) -> str:
    """构建 Agent-2a 的用户消息：注入全量数据。"""
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

    # V7 baseline
    bs = ""
    if baseline_report and len(baseline_report) > 100:
        bs = f"""
## 投资地图 - Agent-Baseline (主输入)

{baseline_report}

---
"""

    msg = f"""# 叙事诊断: {stock}({code})
{bs}
## 估值倍数全矩阵
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
- 异常标记: {json.dumps(core.get('caution_flags',[]), ensure_ascii=False)}

## 历史分位解读
0=历史最高位(从未更贵), 50=中位, 100=历史最低位(从未更便宜)
- PE分位={pe_rank}: {'PE处于历史高位,市场在定价高增长预期' if isinstance(pe_rank, (int,float)) and pe_rank < 20 else 'PE处于历史中低位'}
- PB分位={pb_rank}: {'PB处于历史高位' if isinstance(pb_rank, (int,float)) and pb_rank < 20 else 'PB处于历史中低位'}
- PS分位={ps_rank}: {'PS处于历史高位,收入锚显著' if isinstance(ps_rank, (int,float)) and ps_rank < 20 else 'PS处于历史中低位'}

{ew_text}

## 定量定价工具 — 三个锚各自反推: 当前市值在定价什么？

**用途**: 这是锚判断最关键的定量证据。对比三个锚的隐含预期——哪个锚下市场隐含的增速/改善最离谱,哪个就是市场在用的锚。最离谱的那个≠估值锚错了——它是市场叙事的方向标。

| 锚 | 工具 | 适用 | 当前市值隐含什么？ |
|----|------|:--:|------|
| **earnings** | {pricing_all.get('earnings',{}).get('method','?')} | {pricing_all.get('earnings',{}).get('applicable',False)} | {pricing_all.get('earnings',{}).get('implied_metric','?')} = **{pricing_all.get('earnings',{}).get('implied_value','?')}** |
| **revenue** | {pricing_all.get('revenue',{}).get('method','?')} | {pricing_all.get('revenue',{}).get('applicable',False)} | {pricing_all.get('revenue',{}).get('implied_metric','?')} = **{pricing_all.get('revenue',{}).get('implied_value','?')}** |
| **asset** | {pricing_all.get('asset',{}).get('method','?')} | {pricing_all.get('asset',{}).get('applicable',False)} | {pricing_all.get('asset',{}).get('implied_metric','?')} = **{pricing_all.get('asset',{}).get('implied_value','?')}** |

**判断指南**:
- 如果 earnings 工具显示"隐含永续增速 45%"——这几乎不可能,说明市场不是在定价利润,earnings 锚可能不是主锚
- 如果 revenue 工具显示"隐含 3y CAGR 25%"——在行业增速范围内,说明 revenue 锚是合理的
- 如果 asset 工具显示"隐含 ROE 需从 5%→18%"——改善幅度巨大,说明市场在定价资产重估
- **三个都离谱**: 公司在周期极端位置,所有利润/收入/资产指标都失真 → 考虑 resource 锚或周期调整后的估值

## 事件背景 (Agent-0)
{event_data.get('raw_event_text','')}

## 投资主题
{event_data.get('investment_theme','')}

## 事件推演传导链
{event_data.get('event_deduction','')}

## 空头审查/反方观点
{event_data.get('adversarial_thinking','')}

## 知识补充 + 行业研究
{event_data.get('knowledge_supplement','')}
{event_data.get('industry_expert_research','')}

## 预研推理 (Agent-0 深度分析)
响应等级: L{event_data.get('response_level','?')}（仅反映事件确定性，不直接决定概率）
{event_data.get('preliminary_reasoning','')}

## 未来催化节点
{event_data.get('future','')}

{_build_volc_section(volc_data)}

{build_forward_signal_panel(core)}

请先通读上方"投资主题""事件推演""行业研究"三个语料区块，理解市场在讲什么故事。火山联网搜索数据（如已注入）提供了券商视角的分部收入拆分、可比估值和产品级数据——这些是判断锚类型和SOTP是否触发的关键参照。
锚判断必须从叙事出发——估值倍数数据用于验证叙事，而非替代叙事判断。
然后按清单项 1→2→3→4 顺序完成诊断。输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# Agent2a 主类
# ═══════════════════════════════════════

class NarrativeDiagnosis:
    """叙事诊断 — V6 Agent-2a。"""

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
        执行叙事诊断。

        data_package: Agent-1 输出（含 event_window_prices）
        event_data: Coze Agent0 事件数据
        wacc_params: WACC 预计算参数（用于反向推算工具）
        volc_data: V6.5 火山联网搜索预取数据
        baseline_report: V7 Agent-Baseline 投资地图报告

        返回: {market_narrative, event_pricing, signal_audit, forward_to_routing}
        """
        event_data = event_data or {}
        core = data_package.get("packages", {}).get("core", {}).get("fields", {})

        # ── Step 1: 定量定价工具计算(全锚) ──
        # 为所有可能的锚都计算定价工具, LLM 对比判断哪个锚是市场在用的
        pricing_all = {}
        for a in ("earnings", "revenue", "asset"):
            pricing_all[a] = compute_pricing_anchor(a, core, wacc_params)

        # ── Step 3: LLM 叙事诊断 ──
        user_msg = _build_narrative_user_message(
            data_package, event_data, pricing_all,
            volc_data=volc_data,
            baseline_report=baseline_report,
        )

        result = call_deepseek(
            NARRATIVE_DIAGNOSIS_PROMPT, user_msg,
            temperature=0,
            api_key=self.api_key,
        )

        if "_parse_error" in result:
            # 重试一次
            result = call_deepseek(
                NARRATIVE_DIAGNOSIS_PROMPT, user_msg,
                temperature=0,
                api_key=self.api_key,
            )

        if "_parse_error" in result:
            return self._fallback_diagnosis(core, pricing_all)

        # 注入代码计算值（LLM 不能修改）
        result["_pricing_tool"] = pricing_all

        return result

    # ── 辅助方法 ──

    @staticmethod
    def _infer_anchor_hint(core: dict) -> str:
        """快速推断可能的主锚（用于选择定价工具，LLM 可能推翻）。"""
        np = core.get("net_profit_ttm_yi", 0)
        roic = core.get("roic_pct", 0)
        ps = core.get("ps_ttm", 0)
        pe = core.get("pe_ttm", 0)
        pb = core.get("pb", 0)
        ps_rank = core.get("ps_historical_rank", 50)

        if np <= 0:
            return "revenue" if ps > 0 else "asset"
        if roic > 8 and pe > 0:
            return "earnings"
        if ps_rank is not None and ps_rank < 30 and ps > 5:
            return "revenue"
        if pb > 0 and pb < 3 and roic < 8:
            return "asset"
        return "earnings"

    @staticmethod
    def _fallback_diagnosis(core: dict, pricing_all: dict | None = None) -> dict:
        """LLM 不可用时的纯代码 fallback。"""
        np = core.get("net_profit_ttm_yi", 0)
        roic = core.get("roic_pct", 0)
        ps = core.get("ps_ttm", 0)

        if np > 0 and roic > 8:
            anchor = "earnings"
            family = "earnings_multiples"
        elif ps > 5:
            anchor = "revenue"
            family = "revenue_multiples"
        else:
            anchor = "asset"
            family = "asset_multiples"

        return {
            "market_narrative": {
                "core_bet": f"Fallback: LLM不可用,基于财务数据推断锚={anchor}",
                "narrative_lifecycle": "无法判断(LLM不可用)",
                "narrative_summary": f"LLM不可用,代码根据财务数据(np={np:.1f}亿 roic={roic:.1f}% ps={ps:.1f}x)机械推断主锚={anchor}。叙事诊断和产业语境分析跳过。",
                "primary_anchor": anchor,
                "primary_anchor_evidence": f"Fallback: np={np:.1f}亿 roic={roic:.1f}% ps={ps:.1f}x",
                "anchor_conflict": "LLM不可用,无法检测锚冲突",
                "secondary_anchors": [],
                "sotp_triggered": False,
                "sotp_rationale": "",
            },
            "event_pricing": {
                "event_profile": {
                    "timing_certainty": 5, "timing_rationale": "Fallback默认值",
                    "outcome_binaryness": 5, "outcome_rationale": "Fallback默认值",
                    "precedent_richness": 5, "precedent_rationale": "Fallback默认值",
                    "distribution_shape": "wide_unimodal",
                    "shape_rationale": "LLM不可用,fallback使用默认中等分布"
                },
                "pricing_assessment": {
                    "method": (pricing_all or {}).get("earnings", {}).get("method", "qualitative"),
                    "method_applicable": (pricing_all or {}).get("earnings", {}).get("applicable", False),
                    "method_limitations": (pricing_all or {}).get("earnings", {}).get("limitations", []),
                    "quantitative": {"implied_expectation": str((pricing_all or {}).get("earnings", {}).get("implied_value", "N/A"))},
                    "qualitative_factors": [],
                    "overall_priced_in": "unknown",
                    "priced_in_estimate": "无法判断(LLM不可用)",
                    "residual_catalyst": "",
                },
            },
            "signal_audit": {
                "step2a_restate": [],
                "step2b_match": [],
                "step2c_product_restate": "",
                "step2d_score": 0,
                "score_rationale": "LLM不可用,跳过信号审核",
            },
            "forward_to_routing": {
                "model_family_constraint": family,
                "excluded_families": [],
                "distribution_shape": "wide_unimodal",
                "pricing_bias": "uncertain",
                "key_risk_for_routing": "Fallback诊断,置信度极低",
                "event_driven_segment": {},
            },
            "_pricing_tool": pricing_all,
            "_fallback": True,
        }


# ── 便捷函数 ──

def diagnose_narrative(
    data_package: dict,
    event_data: dict | None = None,
    wacc_params: dict | None = None,
) -> dict:
    """便捷入口：运行叙事诊断。"""
    diag = NarrativeDiagnosis()
    return diag.run(data_package, event_data, wacc_params)
