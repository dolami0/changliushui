"""
Agent-3s SOTP 分部估值 (SOTPScenarioAsymmetry) — V6.1

在 Agent-2a 判定 sotp_triggered=true 后分叉进入此管线。
替代标准 Agent-3，专门处理多业务线估值范式冲突的场景。

职责:
  1. 为每个分部在 bear/base/bull 下赋估值参数（LLM）
  2. 代码按各分部对应锚的公式计算价值并加总（代码）
  3. 复用 Agent-3 的校验、交易标注修正、输出组装框架

设计原则:
  - LLM 控制参数（有经济含义），代码控制算术（确定性计算）
  - 单次 LLM 调用完成分部推演 + 情景判断
  - 输出格式与标准 Agent-3 完全兼容，前端无需修改
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

from valuation_utils import call_deepseek, build_forward_signal_panel, fmt_pct
from agent3_scenario_asymmetry import (
    ScenarioError,
    _validate_output,
    _fix_trade_annotation,
    _assemble_final_output,
    _augment_trace_with_fixes,
    MODEL_NAMES,
    MODEL_FAMILIES,
)

# Volcengine 知识问答 (用于 SOTP 分部数据后备)
try:
    from env_config import VOLC_AGENT_KEY
except ImportError:
    VOLC_AGENT_KEY = ""

VOLC_URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
VOLC_BOT_ID = "7640524154441156122"


def _call_volc(query: str, timeout: int = 120) -> str:
    """调用火山引擎知识问答。失败返回空字符串。"""
    if not VOLC_AGENT_KEY:
        return ""
    try:
        r = requests.post(
            VOLC_URL,
            json={
                "bot_id": VOLC_BOT_ID,
                "stream": False,
                "messages": [{"role": "user", "content": query}],
            },
            headers={
                "Authorization": f"Bearer {VOLC_AGENT_KEY}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "") or ""
        return ""
    except Exception:
        return ""


def _search_segment_data(
    stock_name: str,
    stock_code: str,
    secondary_anchors: list[dict],
) -> dict:
    """火山搜索分部数据：分部毛利率 + 行业估值倍数。
    
    Returns: {segment_margins: {segment_name: margin_pct}, industry_multiples: str}
    搜索失败返回空 dict。
    """
    if not VOLC_AGENT_KEY or not secondary_anchors:
        return {}
    
    seg_names = "、".join(sa.get("segment", "?") for sa in secondary_anchors)
    
    # Query 1: 分部毛利率
    q1 = f"{stock_name}({stock_code})的分部业务{seg_names}各自的毛利率大概是多少？给出百分比数字。"
    result1 = _call_volc(q1)
    
    # Query 2: 行业估值倍数
    anchors = set(sa.get("anchor", "earnings") for sa in secondary_anchors)
    anchor_desc = "、".join(anchors)
    q2 = f"{stock_name}所处行业中，{seg_names}这类业务通常用什么估值倍数？{anchor_desc}锚对应的PE或PS大概什么范围？"
    result2 = _call_volc(q2)
    
    if result1 or result2:
        print(f"  [SOTP Volc] segment data found: margins={'YES' if result1 else 'NO'} multiples={'YES' if result2 else 'NO'}", flush=True)
    
    return {
        "segment_margins_text": result1,
        "industry_multiples_text": result2,
        "_volc_used": True,
    }


def _check_data_adequacy(
    data_package: dict,
    secondary_anchors: list[dict],
) -> tuple[bool, str]:
    """检查 SOTP 分部数据是否充分。
    
    Returns: (is_adequate, reason)
    - is_adequate=True: 分部数据足够，可以运行 SOTP
    - is_adequate=False: 数据不足，需要后备方案
    """
    if not secondary_anchors:
        return True, "无副锚，100%主锚，不需要SOTP"
    
    # 检查 product_mix 数据
    fw = data_package.get("forward_looking", {}) or data_package.get("_forward_looking", {}) or {}
    products = fw.get("categories", {}).get("earnings_elasticity", {}).get("products", {}) or {}
    mix = products.get("product_mix", []) or []
    
    issues = []
    
    for sa in secondary_anchors:
        seg_name = sa.get("segment", "?")
        share = sa.get("revenue_share_pct", 0)
        conf = sa.get("data_confidence", "low")
        
        if share <= 0:
            issues.append(f"{seg_name}: 收入占比未知")
        elif conf == "low":
            issues.append(f"{seg_name}: 收入占比置信度低")
        
        # 检查是否有分产品毛利率数据
        if mix:
            matched = [p for p in mix if seg_name in p.get("name", "") or p.get("name", "") in seg_name]
            if not matched:
                issues.append(f"{seg_name}: product_mix中无匹配产品，毛利率未知")
        else:
            issues.append(f"{seg_name}: 无product_mix数据，毛利率未知")
    
    if issues:
        return False, "; ".join(issues)
    return True, "分部数据充分"

# ═══════════════════════════════════════
# System Prompt — SOTP 分部估值
# ═══════════════════════════════════════

SOTP_SYSTEM_PROMPT = """# 你是达摩达兰式的估值重构师

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

本标的触发 SOTP 分部估值。公司将业务拆为两段：
1. **叙事主锚分部**: 事件驱动的核心业务。推演 bear/base/bull 三情景参数
2. **其他业务**: 副锚分部合并。推演一组 base 参数（三情景共用，不受事件驱动）

## 估值输出必须包含

1. **基础估值（Base Case）**: 最可能的故事对应的估值。
2. **乐观估值（Bull Case）**: 叙事超预期演绎的估值。
3. **悲观估值（Bear Case）**: 叙事崩塌时的估值。

**A 股适配**: base = 故事预期内兑现 + 估值锚跟随预期推移；bull = 场景超预期催化 + 估值范式跃迁 + 主题溢价充分体现；bear = 故事证伪 + 退回保守锚。政策壁垒视为临时优势（写明失效时间）。

# SOTP 两段式估值参数体系

| 锚 | 参数 | 代码公式 |
|----|------|----------|
| earnings | pe_target, segment_margin_pct | 分部收入 x 毛利率 x PE |
| revenue | revenue_growth_3y_cagr_pct, target_ps | 分部收入 x (1+CAGR)³ x PS |
| asset | target_pb | 净资产 x PB |
| pipeline | pos_pct, peak_sales_yi, discount_rate_pct | 峰值销售 x PoS / (1+折现率) |

注: SOTP 用收入x毛利率简化估算分部利润(分部投入资本无法拆分)，不需要 roic_assumed_pct。

## 清单项 1: 素材吸收（引用 2a 诊断 + 吸收事件原文）

**Agent-2a 已完成叙事诊断。** 从用户消息末尾的"Agent-2a 叙事诊断结论"中提取:
- 估值锚: 2a 判定的 primary_anchor 和 evidence
- 计价程度: 2a 判定的 overall_priced_in 和 residual_catalyst
- 事件分布形状: distribution_shape — 决定概率分布的形状和宽度

**再从事件原文中**自行提取（2a 未覆盖的细节）:
- 因果分叉点（event_deduction 中的证实/证伪节点 + adversarial_thinking 的证伪路径）
- 风险边界（TAM 从 knowledge_supplement + 竞争格局从 industry_expert_research）
- 参照系：行业估值中枢 + 2a 的 precedent_richness 提供的先例丰富度

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

**bear 概率上限**（防过度悲观）:
| distribution_shape | bear 上限 | 理由 |
|:------|:------:|------|
| wide_bimodal | 35% | 高不确定性→两个极端都可能 |
| narrow_concentrated | **15%** | 低不确定性→极端尾部概率天然低 |
| narrow_base_dominant | 8% | 趋势有惯性→逆转是小概率 |
中间形状按线性插值。若证伪需要N个独立环节同时崩塌→联合概率自然更低。

**bear 估值硬底**: 故事证伪不等于公司归零。自行选择适用底线:
  - 盈利企业: bear mcap ≥ TTM净利 × 保守PE(行业底部,通常10-20x)
  - 有硬资产: bear mcap ≥ 净资产 × 保守PB(通常0.8-1.2x)
  - 纯故事型: bear mcap ≥ 净现金
bear 不可推翻已发生的业务事实（如已出货产品→不应给0估值）。

bear 概率聚焦 2-3 个核心假设，推演"如果这个错了故事就塌了"的概率。
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

### 3e. 分部赋参

**叙事主锚分部** (is_primary=true): bear/base/bull 三组参数，按 2b 选定的 sotp_primary_segment_model 使用 Agent-3 标准参数体系。以下参数规则与原 Agent-3 完全相同:

赋参数时，用 3a 的分布形状约束和 3b 的 upside 天花板反向验证。
剧本 + 清单项2评分修正 -> 三情景参数。
参数锚定行业估值中枢（来自 knowledge_supplement 或行业常识），不锚定具体个股案例。

当前模型是 {PRIMARY_MODEL} ({MODEL_DESC})，你必须使用的参数体系:
{MODEL_PARAM_NAMES}

**百分比格式铁律——所有带 pct 后缀的字段都使用实际百分比数值,不是小数:**
- ROIC=15% -> roic_assumed_pct: 15 (不是0.15)
- 增速=50% -> earnings_growth_pct: 50 (不是0.5)
- PE=80x -> pe_target: 80
- 概率=30% -> probability: 0.30 (概率字段例外,使用0-1小数)

**参数的经济含义——赋参前必须逐参数过这关:**

PE: 不是抽象数字。PE=600x 需要极高增速支撑。bear（事件失败）的 PE 必须回到行业周期底部（通常 10-30x，不是 600x）。

PS: 当前 PS 是市场讲的故事。base PS = 当前PS x f(priced_in):
  - priced_in=not_priced: f=1.0-1.2 (故事刚开始,PS可扩张)
  - priced_in=partially: f=0.85-1.0 (部分计价,PS大体维持)
  - priced_in=fully: f=0.7-0.85 (已充分计价,PS应部分回归)
  再结合增长可持续性微调: 增长加速->取上限,增长放缓->取下限。
  禁止"因为PS很高所以base给低PS"的均值回归,也禁止"因为PS高所以维持高PS"的惯性。

PB: 与 ROE 匹配。ROE<5% 不应 >2x PB（除非隐蔽资产重估）。

ROIC: 故事里的事件节点驱动 ROIC 改善幅度。从叙事推演 ROIC 路径——毛利率修复到多少？规模效应何时释放？——而非从当前低基数线性外推。

CAGR/增速: 高增速必须匹配高再投资率（RR=g/ROIC）。增速和 RR 不能脱节。

参数联动规则:
- 三情景参数必须逐级递增: bear < base < bull，禁止相同数值
- PE/PS/PB 的升降方向必须与因果剧本一致
- 概率不由模板决定——由因果链条环节数推导

**注意: 你只输出参数假设。所有估值数字由代码统一计算:**

| 模型 | 代码公式 | 你控制的参数 |
|------|----------|-------------|
| A | IC x ROIC% x PE | ROIC、RR(->g)、PE |
| B | revenue x (1+cagr)^3 x PS | 3y CAGR、PS |
| C | IC x ROIC% x PE x 拐点折扣 | ROIC、PE、距拐点 |
| D | equity x PB | PB |
| G | IC x ROIC% x min(PE, PEGx增速) | ROIC、PE、PEG、增速 |
| K | sigma[FCFF_t/(1+WACC)^t] + NOPAT_NxPE/(1+WACC)^N | stage1_growth, stage1_years, ROIC, terminal_PE |

**赋参数时反向验证: 用上表公式心算一遍，你的参数产出的数字和你因果剧本应得的估值是否匹配？**

**SOTP 特殊规则:**

**其他业务** (is_primary=false): 事件催化剂只驱动叙事主线，不影响传统业务。因此其他业务不需要推演三情景——只需要判断它的合理保守估值是多少（一组 base 参数），bear/base/bull 三个情景都用这同一个估值。具体来说：
  - 如果产品结构数据中有该分部的实际毛利率 -> 引用为 segment_margin_pct
  - 如果没有 -> 基于行业知识和公司整体毛利率做合理假设，在 segment_rationale 中标注[估算]
  - PE 取行业周期底部（通常 10-20x），PS 取保守值（通常 0.5-2.0x），PB 取 0.8-1.2x
  - 这不是精确估值——其他业务的作用是提供一个稳定的基准锚，防止叙事锚把整家公司高估或低估

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

**4e. 置信度(4维, 每维1-10)**
- info_quality: 信息来源可靠性。硬证据≥2环(订单/产能/专利/政策)→≥7; 纯主题无锚点→1-3。**强制降级: 清单项2c标注"事件-产品映射失败"→info_quality≤5**
- financial_feasibility: 财务假设可行性。参数改善幅度有逻辑支撑→≥7; 凭空跳变→≤5
- valuation_safety: 估值安全边际。bear 下行≤50%→≥7; bear 下行>90%→≤4
- historical_precedent: 参照 2a 的 precedent_richness。先例丰富(P≥8)→≥7; 史无前例(P≤3)→≤4

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
  "reasoning_trace": ["清单项1-素材吸收(引用2a锚+计价): ...", "清单项2-引用2a审核结论(step2d=X): ...", "清单项3a-投资命题: ...", "清单项3e-赋参数: ...", "清单项4a-一致性校验: ...", "清单项4b-计价验证(按锚选工具): ...", "清单项4c-校验交叉: ...", "清单项4d-非对称: ...", "清单项4e-置信度: ..."],
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
  "segments": [
    {
      "segment": "叙事主锚分部",
      "anchor": "revenue", "revenue_share_pct": 74.4, "is_primary": true,
      "segment_rationale": "<=60字",
      "bear": {"revenue_growth_3y_cagr_pct": 10, "target_ps": 5},
      "base": {"revenue_growth_3y_cagr_pct": 30, "target_ps": 10},
      "bull": {"revenue_growth_3y_cagr_pct": 50, "target_ps": 15}
    },
    {
      "segment": "其他业务(副锚合并)",
      "anchor": "earnings", "revenue_share_pct": 25.6, "is_primary": false,
      "segment_rationale": "<=60字",
      "base": {"pe_target": 15, "segment_margin_pct": 20}
    }
  ],
  "scenario_valuation": {
    "scenario_details": {SCENARIO_PARAMS_EXAMPLE},
    "probability_weighted_mcap_yi": XX,
    "probability_weighted_upside_pct": XX,
    "asymmetry_ratio": X.X
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
}"""


# ═══════════════════════════════════════
# 数据格式兼容层
# ═══════════════════════════════════════

def _get_core_fields(data_package: dict) -> dict:
    """从 data_package 提取核心财务字段，兼容两种格式：
    - 新格式: packages.core.fields (Agent-1 标准输出)
    - 旧格式: clean_financials (历史缓存/快照)
    """
    # 新格式
    pkgs = data_package.get("packages", {}) or {}
    core = pkgs.get("core", {}) or {}
    fields = core.get("fields", {}) or {}
    if fields:
        return fields

    # 旧格式 (clean_financials 平坦结构)
    cf = data_package.get("clean_financials", {}) or {}
    if cf:
        return cf

    # 兜底：从 data_package 顶层直接取
    return {
        k: data_package.get(k, 0)
        for k in ["market_cap_yi", "revenue_ttm_yi", "net_profit_ttm_yi",
                   "total_equity_yi", "total_assets_yi", "cash_yi",
                   "interest_bearing_debt_yi", "pe_ttm", "pb", "ps_ttm",
                   "roic_pct", "gross_margin_pct", "net_margin_pct",
                   "stock_name", "data_quality_score"]
    }


def _build_bs_section(data_package: dict, agent2a_output: dict, wacc_params: dict) -> tuple:
    """构建 BS 画像文本，与 Agent-3 对齐。"""
    from agent3_scenario_asymmetry import precompute_bs_profile, precompute_wacc
    core = _get_core_fields(data_package)
    anchor = agent2a_output.get("market_narrative", {}).get("primary_anchor", "earnings")
    pt = agent2a_output.get("_pricing_tool", {}) or {}

    mcap = core.get("market_cap_yi", 50)
    if anchor == "earnings":
        nopat = core.get("nopat_yi", 0.01)
        wacc = wacc_params.get("wacc_pct", 10)
        ev = mcap + core.get("interest_bearing_debt_yi", 0) - core.get("cash_yi", 0)
        implied_g = round((ev * wacc / 100 - nopat) / nopat * 100, 1) if nopat > 0 else 0
        lines = [
            "**方法: 反向 DCF (利润锚)**",
            "- EV: {:.0f}亿 NOPAT: {:.2f}亿 ROIC: {:.1f}%".format(ev, nopat, core.get('roic_pct',0)),
            "- 隐含永续增速 g ≈ {}% (WACC={}%)".format(implied_g, wacc),
            "- PE: {:.1f}x PB: {:.1f}x".format(core.get('pe_ttm',0), core.get('pb',0)),
        ]
        section = "\n".join(lines)
        warning = ""
    elif anchor == "revenue":
        ps = core.get("ps_ttm", 0)
        rev = core.get("revenue_ttm_yi", 1)
        section = f"""**方法: 隐含收入 CAGR (收入锚)**
- 当前 PS = {ps:.1f}x 营收TTM = {rev:.1f}亿 市值 = {mcap:.0f}亿"""
        if pt.get("applicable"):
            section += "\\n- 隐含3年收入CAGR = " + str(pt.get('implied_value','?')) + "%"
        warning = f"- PE: {core.get('pe_ttm',0):.1f}x PB: {core.get('pb',0):.1f}x (利润锚仅供参考)\\n"
    elif anchor == "asset":
        pb = core.get("pb", 0)
        roe = core.get("roe_ttm_pct", 0)
        section = f"""**方法: 隐含 ROE 改善 (资产锚)**
- 当前 PB = {pb:.1f}x ROE = {roe:.1f}%"""
        if pt.get("applicable"):
            section += "\\n- 隐含ROE需改善 " + str(pt.get('implied_value','?')) + "ppt"
        warning = f"- PE: {core.get('pe_ttm',0):.1f}x (利润锚仅供参考)\\n"
    else:
        section = f"**方法: {anchor}锚 (定性判断)**"
        warning = ""

    return section, warning


# ═══════════════════════════════════════
# 用户消息构建
# ═══════════════════════════════════════

def _build_segments_section(
    secondary_anchors: list[dict],
    primary_anchor: str,
    market_narrative: dict,
    core: dict,
) -> str:
    """构建两段式分部信息——叙事主锚 + 其他业务（合并所有副锚）。"""
    total_rev = core.get("revenue_ttm_yi", 1)
    secondary_total = sum(sa.get("revenue_share_pct", 0) for sa in secondary_anchors)
    primary_share = max(0, 100 - secondary_total)

    lines = ["| 分部 | 角色 | 锚 | 收入占比 | 估算收入(亿) |",
             "|------|------|-----|---------|-------------|"]

    # 叙事主锚分部（事件驱动，三情景变参）
    primary_label = market_narrative.get("core_bet", "叙事主线")[:20]
    primary_rev = total_rev * primary_share / 100
    lines.append(f"| {primary_label} | 叙事主锚(变参) | {primary_anchor} | {primary_share:.1f}% | {primary_rev:.1f} |")

    # 其他业务（合并所有副锚，基准不变）
    other_share = secondary_total
    if other_share > 0:
        other_rev = total_rev * other_share / 100
        # 副锚中可能有不同锚类型，取第一个作为"其他业务"的代表锚；若无副锚，用 earnings
        other_anchor = secondary_anchors[0].get("anchor", "earnings") if secondary_anchors else "earnings"
        other_names = " + ".join(sa.get("segment", "?") for sa in secondary_anchors)
        lines.append(f"| {other_names} | 其他业务(不变) | {other_anchor} | {other_share:.1f}% | {other_rev:.1f} |")

    # 如果没有任何副锚（100% 主锚），标注特殊处理
    if not secondary_anchors:
        lines.append("| （无其他业务，100%为叙事主锚分部） | — | — | — | — |")

    return "\n".join(lines)


def _build_product_mix_section(data_package: dict) -> str:
    """从 Agent-1 的 forward_looking 提取分产品收入/毛利率数据。"""
    # forward_looking 在 data_package 顶层（与 clean_financials 同级）或嵌套在 packages.core.fields._forward_looking 中
    fw = data_package.get("forward_looking", {}) or data_package.get("_forward_looking", {}) or {}
    core = _get_core_fields(data_package)
    # 也检查 core fields 内部是否有 _forward_looking
    if not fw:
        fw = core.get("_forward_looking", {}) or {}
    products = fw.get("categories", {}).get("earnings_elasticity", {}).get("products", {}) or {}
    mix = products.get("product_mix", []) or []

    if not mix:
        return "（无分产品数据）\n\n注: 分部毛利率请基于行业知识和公司整体毛利率估算，并在 segment_rationale 中标注[估算]。"

    lines = ["| 产品 | 收入(亿) | 占比 | 毛利率 | 同比 |",
             "|------|---------|------|--------|------|"]
    for p in mix:
        rev = p.get("revenue", 0)
        share = p.get("revenue_share_pct", 0)
        gm = p.get("gross_margin_pct")
        gm_str = f"{gm:.1f}%" if gm is not None else "?"
        yoy = p.get("revenue_yoy_pct")
        yoy_str = f"{yoy:+.1f}%" if yoy is not None else "?"
        lines.append(f"| {p['name']} | {rev:.2f} | {share:.1f}% | {gm_str} | {yoy_str} |")

    # 毛利率数据质量标注
    gm_src = products.get("gm_source", "actual")
    gm_cov = products.get("gm_coverage_pct", 100)
    notes = []
    if gm_src != "actual":
        notes.append(f"毛利率来源={gm_src}(覆盖率{gm_cov}%)——非实际分产品数据")
    if products.get("has_h1_data"):
        notes.append("含H2半年轨迹数据（年报-半年报推算下半年趋势）")
    if notes:
        lines.append(f"\n数据质量: {'; '.join(notes)}")

    # 毛利率结构分析
    margin = products.get("margin_structure", {}) or {}
    if margin:
        gm_spread = margin.get("gm_spread_ppt", 0)
        imp_src = margin.get("gm_improvement_source", "?")
        lines.append(f"毛利率极差: {gm_spread}ppt | 改善来源: {imp_src}")

    return "\n".join(lines)


def _build_volc_section(volc_data: dict | None) -> str:
    """构建火山搜索补充数据段落。"""
    if not volc_data or not volc_data.get("_volc_used"):
        return "（未触发火山搜索——分部数据充分）"
    
    lines = []
    margins = volc_data.get("segment_margins_text", "")
    multiples = volc_data.get("industry_multiples_text", "")
    
    if margins:
        lines.append(f"**分部毛利率参考**: {margins[:500]}")
    if multiples:
        lines.append(f"**行业估值倍数参考**: {multiples[:500]}")
    
    if not lines:
        return "（火山搜索未返回有效数据）"
    
    lines.insert(0, "以下数据来自火山引擎知识搜索，作为产品结构数据缺失时的补充参考：")
    return "\n\n".join(lines)


def _format_signal_audit(sa: dict) -> str:
    """格式化信号审核摘要。"""
    if not sa:
        return "无"
    items = []
    matches = sa.get("step2b_match", [])
    if matches:
        items.append("交叉验证: " + "; ".join(
            f"{m.get('signal','?')}={m.get('match','?')}" for m in matches[:3]
        ))
    return " | ".join(items) if items else "无异常信号"


def _format_anchor_shift(mn: dict) -> str:
    """格式化范式切换潜力。"""
    asp = mn.get("anchor_shift_potential", {}) or {}
    if not asp.get("shift_possible"):
        return "- 范式切换潜力: 否"
    lines = [
        "- 范式切换潜力: 是",
        "  从 {} -> {}".format(asp.get('from_anchor','?'), asp.get('to_anchor','?')),
        "  触发条件: {}".format(asp.get('shift_trigger','?')),
        "  理由: {}".format(str(asp.get('shift_rationale','?'))[:200]),
        "  时机: {}".format(asp.get('shift_timing','?')),
    ]
    return "\\n".join(lines)


def _format_pricing_tool(agent2a_output: dict) -> str:
    """格式化定价工具详情。"""
    pt = agent2a_output.get("_pricing_tool", {}) or {}
    if not pt or not pt.get("applicable"):
        return "- 定价工具: 不适用"
    lines = [
        "- 定价工具: " + str(pt.get('method','?')),
        "  隐含指标: " + str(pt.get('implied_metric','?')) + " = " + str(pt.get('implied_value','?')),
        "  局限: " + str(pt.get('limitations',[])),
    ]
    return "\n".join(lines)


def _fill_sotp_placeholders(prompt: str, agent2b_output: dict | None = None) -> str:
    """替换 SOTP prompt 中残留的 Agent-3 占位符。"""
    # 从 2b 取主锚分部模型
    seg_model = "?"
    if agent2b_output:
        rd = agent2b_output.get("routing_decision", {})
        if isinstance(rd, dict):
            seg_model = rd.get("sotp_primary_segment_model", "B")

    replacements = {
        "{PRIMARY_MODEL}": "J",
        "{MODEL_DESC}": "SOTP",
        "{MODEL_FAMILY}": "分拆",
        "{VALIDATION_MODEL}": "自校验(SOTP无独立校验模型)",
        "{VALIDATION_MODEL_DESC}": "SOTP不分拆校验",
        "{SCENARIO_PARAMS_EXAMPLE}": '"bear": {...}, "base": {...}, "bull": {...}',
        "{MODEL_PARAM_NAMES}": f"叙事主锚: {seg_model}模型参数; 其他业务: pe_target/segment_margin_pct(earnings)或target_ps(revenue)或target_pb(asset)",
        "{MODEL_PARAM_SELF_CHECK}": "- 叙事分部参数单调递增\n- 其他业务参数保守合理\n- Bull/base<=3x",
    }
    for k, v in replacements.items():
        prompt = prompt.replace(k, v)
    return prompt


def _get_sotp_primary_model(agent2b_output: dict | None) -> str:
    """从 Agent-2b 输出提取叙事主锚分部的模型。"""
    if not agent2b_output:
        return "?"
    rd = agent2b_output.get("routing_decision", {})
    if isinstance(rd, dict):
        return rd.get("sotp_primary_segment_model", "?")
    return "?"


def _get_2b_info(agent2b_output: dict | None) -> str:
    """从 Agent-2b 输出提取主锚模型信息。"""
    if not agent2b_output:
        return "未提供(2b未运行)"
    rd = agent2b_output.get("routing_decision", {})
    model = rd.get("primary_model", "?")
    cat = rd.get("model_category", "?")
    return f"{model} ({cat})"


def _build_sotp_user_message(
    data_package: dict,
    agent2a_output: dict,
    agent2b_output: dict | None,
    event_data: dict,
    wacc_params: dict,
    volc_data: dict | None = None,
) -> str:
    """构建 SOTP Agent 用户消息——注入分部数据、财务数据、叙事诊断、事件背景、2b路由。"""
    core = _get_core_fields(data_package)
    stock = core.get("stock_name", data_package.get("stock_name", ""))
    code = data_package.get("stock_code", "")

    mn = agent2a_output.get("market_narrative", {})
    ep = agent2a_output.get("event_pricing", {})
    sa = agent2a_output.get("signal_audit", {})
    pa = ep.get("pricing_assessment", {})
    primary = mn.get("primary_anchor", "earnings")
    sas = mn.get("secondary_anchors", [])

    # 路由理由
    rd_2b = (agent2b_output or {}).get("routing_decision", {}) if isinstance(agent2b_output, dict) else {}
    routing_reason = rd_2b.get("routing_reason", "SOTP分部估值")

    # BS画像 (与 Agent-3 对齐)
    bs_section, bs_warning = _build_bs_section(data_package, agent2a_output, wacc_params)

    # ── 核心财务 ──
    mcap = core.get("market_cap_yi", 0)
    rev = core.get("revenue_ttm_yi", 0)
    np = core.get("net_profit_ttm_yi", 0)
    equity = core.get("total_equity_yi", 0)
    cash = core.get("cash_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    gm = core.get("gross_margin_pct", 0)
    nm = core.get("net_margin_pct", 0)
    roic = core.get("roic_pct", 0)
    pe = core.get("pe_ttm", 0)
    pb = core.get("pb", 0)
    ps = core.get("ps_ttm", 0)
    net_cash = cash - debt

    # ── 事件窗口价格 ──
    ew = data_package.get("event_window_prices", {}) or {}
    ew_text = ""
    if ew and ew.get("source") not in ("none", None):
        pre = ew.get("pre_event") or {}
        post = ew.get("post_event") or {}
        cur = ew.get("current") or {}
        ew_text = f"""
## 事件窗口价格
| 窗口 | 均价 |
|------|------|
| 事件前({pre.get('num_days','?')}日) | {pre.get('avg_close','?')} |
| 事件后({post.get('num_days','?')}日) | {post.get('avg_close','?')} |
| 最新({cur.get('date','?')}) | {cur.get('close','?')} |
"""

    # ── 前瞻信号面板 ──
    signal_panel = build_forward_signal_panel(core)

    msg = f"""# SOTP 分部估值: {stock}({code})

## Agent-2a 叙事诊断
- 主锚: {primary}
- 核心赌注: {mn.get('core_bet', '?')}
- 生命周期: {mn.get('narrative_lifecycle', '?')}
- 锚冲突: {mn.get('anchor_conflict', '') or '无'}
- SOTP触发理由: {mn.get('sotp_rationale', '?')}
- Agent-2b 路由: 主模型={_get_2b_info(agent2b_output)}, 叙事主锚分部模型={_get_sotp_primary_model(agent2b_output)}
- 计价程度: {pa.get('overall_priced_in', '?')}（{pa.get('priced_in_estimate', '?')}）
- 事件分布形状: {ep.get('event_profile', {}).get('distribution_shape', '?')}
- 信号评分: {sa.get('step2d_score', '?')}/10 — {sa.get('score_rationale', '?')[:200]}

## 分部定义 (Agent-2a 判定)
{_build_segments_section(sas, primary, mn, core)}

## 产品结构数据 (Agent-1 财报提取)
{_build_product_mix_section(data_package)}

## 核心财务数据
| 指标 | 数值 | 指标 | 数值 |
|------|------|------|------|
| 市值 | {mcap:.0f}亿 | PE(TTM) | {pe:.1f}x |
| TTM营收 | {rev:.1f}亿 | PB | {pb:.1f}x |
| TTM净利润 | {np:.1f}亿 | PS(TTM) | {ps:.1f}x |
| ROIC | {roic:.1f}% | 毛利率 | {gm:.1f}% |
| 净资产 | {equity:.0f}亿 | 净利率 | {nm:.1f}% |
| 现金 | {cash:.1f}亿 | 有息负债 | {debt:.1f}亿 |
| 净现金 | {net_cash:.1f}亿 | 数据质量 | {core.get('data_quality_score', '?')}/10 |

## WACC (代码预计算, 不可修改)
{wacc_params.get('wacc_pct', 10)}% (rf={wacc_params.get('rf_pct', '?')}% beta={wacc_params.get('beta', '?')} ERP={wacc_params.get('erp_pct', '?')}%)

{ew_text}

## 当前市值隐含假设 (Implied Story)

{bs_section}{bs_warning}

## 事件背景 (Agent-0 预研)

### 投资主题
{event_data.get('investment_theme', '')}

### 事件推演
传导链: {event_data.get('event_deduction', '')}
催化节点: {event_data.get('future', '')}

### 压力测试
{event_data.get('adversarial_thinking', '')}

### 赛道标尺
知识补充: {event_data.get('knowledge_supplement', '')}
行业研究: {event_data.get('industry_expert_research', '')}

### 深度预研
响应等级: L{event_data.get('response_level','?')}
事件原文: {event_data.get('raw_event_text', '')}
预研推理: {event_data.get('preliminary_reasoning', '')}

## Agent-2a 叙事诊断结论（已审核，可直接信任）

- 估值锚: {mn.get('primary_anchor','?')}
- 锚证据: {mn.get('primary_anchor_evidence','?')[:200]}
- 核心赌注: {mn.get('core_bet','?')}
- 叙事总结: {mn.get('narrative_summary','?')[:300]}
- SOTP触发理由: {mn.get('sotp_rationale','?')}
- 锚冲突: {mn.get('anchor_conflict','') or '无'}
- 事件分布形状: {ep.get('event_profile',{}).get('distribution_shape','?')}
- 计价程度: {pa.get('overall_priced_in','?')} ({pa.get('priced_in_estimate','?')})
- 剩余催化: {pa.get('residual_catalyst','?')[:200]}
- 信号评分: {sa.get('step2d_score','?')}/10 — {sa.get('score_rationale','?')[:200]}
- 信号审核: {_format_signal_audit(sa)}

{_format_anchor_shift(mn)}
{_format_pricing_tool(agent2a_output)}

{signal_panel}

## 火山搜索补充数据
{_build_volc_section(volc_data)}

请按分部独立推演 bear/base/bull 参数。输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# 核心计算函数 — SOTP 分部加总
# ═══════════════════════════════════════

# _compute_other_value removed — LLM handles other business params now


def _compute_segment_value(
    anchor: str,
    params: dict,
    segment_revenue: float,
    core: dict,
) -> float | None:
    """计算单个分部的目标市值。

    Args:
        anchor: 该分部的估值锚 (earnings | revenue | asset | pipeline)
        params: LLM 输出的该分部该情景参数
        segment_revenue: 该分部的估算收入（亿元）
        core: 公司整体财务数据字典

    Returns:
        分部目标市值（亿元），None 表示参数不足无法计算
    """
    if anchor == "earnings":
        pe = params.get("pe_target", 0)
        margin = params.get("segment_margin_pct")
        if margin is None:
            margin = core.get("gross_margin_pct", 0)
        if pe > 0 and segment_revenue > 0 and margin > 0:
            segment_nopat = segment_revenue * margin / 100
            return round(segment_nopat * pe, 1)
        return None

    elif anchor == "revenue":
        cagr = params.get("revenue_growth_3y_cagr_pct", 0)
        ps = params.get("target_ps", 0)
        if segment_revenue > 0 and ps > 0:
            future_revenue = segment_revenue * (1 + cagr / 100) ** 3
            return round(future_revenue * ps, 1)
        return None

    elif anchor == "asset":
        pb = params.get("target_pb", 0)
        total_equity = core.get("total_equity_yi", 1)
        total_revenue = core.get("revenue_ttm_yi", 1)
        if pb > 0 and total_revenue > 0:
            # 分部净资产按收入占比估算
            segment_equity = total_equity * (segment_revenue / total_revenue)
            return round(segment_equity * pb, 1)
        return None

    elif anchor == "pipeline":
        pos = params.get("pos_pct", 0)
        peak = params.get("peak_sales_yi", 0)
        rate = params.get("discount_rate_pct", 15)
        if peak > 0 and pos > 0 and rate > 0:
            return round(peak * (pos / 100) / (1 + rate / 100), 1)
        return None

    return None


def _compute_sotp_total(
    segments: list[dict],
    scenario_name: str,
    core: dict,
) -> dict:
    """计算单个情景的 SOTP 加总价值。

    SOTP = Σ各分部(LLM参数) + 净现金
    叙事主锚分部用 scenario 对应参数(bear/base/bull)；
    其他业务用 base 参数(三情景不变)。

    Args:
        segments: LLM 输出的分部列表(含 is_primary 标志)
        scenario_name: "bear" | "base" | "bull"
        core: 公司整体财务数据
    """
    total_revenue = core.get("revenue_ttm_yi", 1)
    cash = core.get("cash_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    net_cash = cash - debt

    total_value = net_cash
    segment_values = []
    primary_val = None
    other_val = 0.0

    for seg in segments:
        seg_name = seg.get("segment", "?")
        anchor = seg.get("anchor", "earnings")
        share = seg.get("revenue_share_pct", 0)
        is_primary = seg.get("is_primary", True)

        # 非主锚分部：始终使用 base 参数（不受事件驱动）
        if not is_primary:
            params = seg.get("base", {})
        else:
            params = seg.get(scenario_name, {})

        seg_revenue = total_revenue * share / 100
        seg_val = _compute_segment_value(anchor, params, seg_revenue, core)

        if seg_val is not None:
            total_value += seg_val
            segment_values.append({
                "segment": seg_name,
                "anchor": anchor,
                "revenue_share_pct": share,
                "segment_revenue_yi": round(seg_revenue, 2),
                "segment_value_yi": seg_val,
                "source": "LLM(变参)" if is_primary else "LLM(base)",
            })
            if is_primary:
                primary_val = seg_val
            else:
                other_val += seg_val

    return {
        "total_mcap_yi": round(total_value, 1),
        "net_cash_yi": round(net_cash, 1),
        "primary_value_yi": primary_val,
        "other_value_yi": round(other_val, 1) if other_val > 0 else 0,
        "segment_values": segment_values,
        "skipped_segments": [],
    }


def _compute_sotp_from_llm(
    llm_output: dict,
    core: dict,
) -> dict:
    """从 LLM 输出计算 SOTP 三情景加权结果。

    所有分部均由 LLM 输出参数，代码计算各分部价值后加总。
    回写计算结果到 llm_output，使其与 _assemble_final_output 兼容。
    """
    segments = llm_output.get("segments", [])
    # 兼容旧格式: primary_segment
    if not segments:
        ps = llm_output.get("primary_segment", {})
        if ps:
            segments = [ps]
            print(f"  [SOTP] LLM used old 'primary_segment' format", flush=True)
    sv = llm_output.get("scenario_valuation", {})
    details_raw = sv.get("scenario_details", {})

    # 容错: LLM 可能输出数组格式
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

    for scenario_name in ("bear", "base", "bull"):
        sotp = _compute_sotp_total(segments, scenario_name, core)
        target_mcap = sotp["total_mcap_yi"]

        prob = details.get(scenario_name, {}).get("probability", 0)
        probs.append(prob)

        if target_mcap > 0 and current_mcap > 0:
            ups = round((target_mcap / current_mcap - 1) * 100, 1)
        else:
            ups = 0

        mcaps.append(target_mcap)
        upsides.append(ups)

        # 回写计算结果到 details
        if scenario_name not in details:
            details[scenario_name] = {}
        details[scenario_name]["target_mcap_yi"] = target_mcap
        details[scenario_name]["upside_pct"] = ups
        details[scenario_name]["_segment_breakdown"] = sotp["segment_values"]
        details[scenario_name]["_net_cash_yi"] = sotp["net_cash_yi"]
        details[scenario_name]["_primary_value_yi"] = sotp["primary_value_yi"]
        details[scenario_name]["_other_value_yi"] = sotp["other_value_yi"]

    # 概率加权计算
    weighted_upside = sum(p * u for p, u in zip(probs, upsides))
    weighted_mcap = sum(p * m for p, m in zip(probs, mcaps))
    bear_u = upsides[0]
    bull_u = upsides[2]
    asym = abs(bull_u / bear_u) if bear_u != 0 and abs(bull_u) > 0 else 0

    # 回写 scenario_valuation
    sv["scenario_details"] = details
    sv["probability_weighted_upside_pct"] = round(weighted_upside, 1)
    sv["probability_weighted_mcap_yi"] = round(weighted_mcap, 1)
    sv["asymmetry_ratio"] = round(asym, 1)
    sv["_computed_by_code"] = True

    llm_output["scenario_valuation"] = sv

    return {
        "weighted_upside_pct": round(weighted_upside, 1),
        "weighted_mcap_yi": round(weighted_mcap, 1),
        "asymmetry_ratio": round(asym, 1),
    }


# ═══════════════════════════════════════
# SOTPScenarioAsymmetry 主类
# ═══════════════════════════════════════

class SOTPScenarioAsymmetry:
    """SOTP 分部估值 — Agent-3s (V6.1)。

    复用 Agent-3 的校验、组装框架，将估值计算替换为分部加总逻辑。
    单次 LLM 调用完成分部参数推演 + 情景判断。
    """

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key

    def run(
        self,
        data_package: dict,
        agent2a_output: dict,
        agent2b_output: dict | None = None,
        event_data: dict | None = None,
        wacc_params: dict | None = None,
        progress_cb=None,
    ) -> dict:
        """执行 SOTP 分部估值。

        Args:
            data_package: Agent-1 输出（含 product_mix 和财务数据）
            agent2a_output: Agent-2a 输出（含 secondary_anchors + sotp_triggered）
            event_data: Coze Agent0 预研
            wacc_params: WACC 预计算参数
            progress_cb: 进度回调 (step, msg)

        Returns:
            与标准 Agent-3 格式兼容的输出 dict
        """
        cb = progress_cb or (lambda s, n: None)
        event_data = event_data or {}
        wacc_params = wacc_params or {}
        core = _get_core_fields(data_package)

        # ── Step 0: 数据充分性检查 ──
        secondary_anchors_pre = agent2a_output.get("market_narrative", {}).get("secondary_anchors", [])
        is_adequate, adequacy_reason = _check_data_adequacy(data_package, secondary_anchors_pre)
        volc_data = {}
        if not is_adequate:
            print(f"  [SOTP] 分部数据不足: {adequacy_reason}", flush=True)
            cb(0.5, "火山搜索分部数据")
            volc_data = _search_segment_data(
                core.get("stock_name", ""), data_package.get("stock_code", ""),
                secondary_anchors_pre,
            )
            if not volc_data:
                print(f"  [SOTP] 火山搜索失败, 回退标准管线", flush=True)
                return {"_fallback_to_standard": True, "_fallback_reason": adequacy_reason}

        # ── Step 1: LLM 推演分部参数 ──
        cb(1, "SOTP LLM分部推演")
        user_msg = _build_sotp_user_message(
            data_package, agent2a_output, agent2b_output, event_data, wacc_params,
            volc_data=volc_data,
        )

        # 替换 prompt 中的 Agent-3 占位符（SOTP 不需要模型选择，直接填 J/SOTP）
        prompt = _fill_sotp_placeholders(SOTP_SYSTEM_PROMPT, agent2b_output)
        try:
            result = call_deepseek(
                prompt, user_msg,
                max_tokens=30720, temperature=0.1,
                api_key=self.api_key,
            )
        except Exception as e:
            raise ScenarioError("E303", f"SOTP LLM调用失败: {e}")

        if "_parse_error" in result:
            # 重试一次
            try:
                result = call_deepseek(
                    prompt, user_msg,
                    max_tokens=30720, temperature=0.1,
                    api_key=self.api_key,
                )
            except Exception:
                pass

        if "_parse_error" in result:
            raise ScenarioError(
                "E301", "SOTP LLM JSON解析失败",
                {"raw": str(result.get("_parse_error", ""))[:300]},
            )

        # ── Step 2: 代码计算 SOTP 加总 ──
        cb(2, "SOTP代码加总")
        sotp_computed = _compute_sotp_from_llm(result, core)

        # ── Step 3: 修正交易标注（复用 Agent-3）──
        cb(3, "修正交易标注")
        ta = result.get("trade_annotation", {})
        sv = result.get("scenario_valuation", {})
        details = sv.get("scenario_details", {})
        if isinstance(details, list):
            details_dict = {}
            for item in details:
                name = item.get("scenario", "")
                if name in ("bear", "base", "bull"):
                    details_dict[name] = item
            details = details_dict
        bear_u = details.get("bear", {}).get("upside_pct", 0)
        bull_u = details.get("bull", {}).get("upside_pct", 0)
        result["trade_annotation"] = _fix_trade_annotation(
            ta,
            sotp_computed["weighted_upside_pct"],
            sotp_computed["asymmetry_ratio"],
            bear_u, bull_u,
        )

        # ── Step 4: 校验（复用 Agent-3）──
        cb(4, "一致性校验")
        bs_profile = {
            "bs_method": "SOTP 分部加总 (2段: 叙事主锚 + 其他)",
            "bs_level": f"分部独立估值后加总净现金{core.get('cash_yi',0)-core.get('interest_bearing_debt_yi',0):+.1f}亿 → 总市值{sotp_computed['weighted_mcap_yi']:.0f}亿",
            "ev_yi": 0,
            "nopat_yi": 0,
            "roic_pct": 0,
            "wacc_simple_pct": wacc_params.get("wacc_pct", 10),
            "market_premium_pct": 0,
            "implied_g_pct": 0,
            "pe_ttm": core.get("pe_ttm", 0),
            "pb": core.get("pb", 0),
            "market_story": "SOTP: 叙事主锚(LLM推演) + 其他业务(代码自动) + 净现金",
            "warnings": [],
            "wacc_params": wacc_params,
            "bs_secondary": "",
            "note_to_llm": "",
            "reverse_dcf_applicable": False,
            "reverse_dcf_applicable_note": "SOTP 不使用反向DCF——分部加总本身就是定价验证",
            "valuation_anchor_used": "sotp",
        }

        validation_warnings = _validate_output(
            result, bs_profile, wacc_params,
        )
        # 过滤 E306 类（代码已重算，数值差异是预期内的）
        validation_warnings = [
            w for w in validation_warnings
            if not w.get("code", "").startswith("E306")
        ]
        if validation_warnings:
            codes = [w["code"] for w in validation_warnings]
            print(f"  [SOTP validation] warnings: {codes}", flush=True)

        # ── Step 5: 组装输出（复用 Agent-3 的 _assemble_final_output）──
        cb(5, "组装输出")
        routing = {
            "primary_model": "J",
            "model_category": "SOTP",
            "routing_reason": (
                "Agent-2a 触发 SOTP: 2段式(叙事主锚+其他), "
                "范式冲突需分部独立估值"
            ),
            "validation_models": [],
            "model_migration_path": {},
        }

        output = _assemble_final_output(
            result, bs_profile, data_package, routing, validation_warnings,
            llm_original_values={
                "upside": sotp_computed["weighted_upside_pct"],
                "asymmetry": sotp_computed["asymmetry_ratio"],
                "mcap": sotp_computed["weighted_mcap_yi"],
            },
        )

        # ── Step 6: 注入 SOTP 特有字段 ──
        output["_sotp_breakdown"] = {
            "segments": result.get("segments", []),
            "scenario_details": sv.get("scenario_details", {}),
        }

        cb(6, "SOTP估值完成")
        return output


# ── 便捷函数 ──

def run_sotp_scenario(
    data_package: dict,
    agent2a_output: dict,
    event_data: dict | None = None,
    wacc_params: dict | None = None,
) -> dict:
    """便捷入口：运行 SOTP 分部估值。"""
    agent = SOTPScenarioAsymmetry()
    return agent.run(data_package, agent2a_output, event_data, wacc_params)
