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

SOTP_SYSTEM_PROMPT = """# 你是达摩达兰式的估值重构师 — SOTP 模式

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

## V6 上下文

Agent-2a 已完成叙事诊断。Agent-2a 判定该公司不同业务线适用完全不同估值范式——触发 SOTP 分部估值。

你的职责: 基于 2a 已验证的叙事框架，对**每个分部**独立推演 bear/base/bull 参数。

## SOTP 两段式估值

公司拆为两段：
1. **叙事主锚分部**: 事件驱动的核心业务。推演 bear/base/bull 三情景参数
2. **其他业务**: 副锚分部合并。推演一组 base 参数（三情景共用，不受事件驱动）

| 锚 | 参数 | 代码公式 | 你需要判断什么 |
|----|------|---------|--------------|
| **earnings** | pe_target, segment_margin_pct | 分部收入 × 毛利率 × PE | 盈利能力和合理PE |
| **revenue** | revenue_growth_3y_cagr_pct, target_ps | 分部收入 × (1+CAGR)³ × PS | 收入增速和合理PS |
| **asset** | target_pb | 净资产 × PB | 资产合理PB |
| **pipeline** | pos_pct, peak_sales_yi, discount_rate_pct | 峰值销售 × PoS / (1+折现率) | 管线成功率和峰值销售 |

注意: SOTP 用收入×毛利率简化估算分部利润（分部投入资本无法从合并报表拆分），不需要 roic_assumed_pct 和 rr_assumed_pct。

分部毛利率优先引用产品结构数据中的实际值。如果没有→基于行业知识和公司整体毛利率做合理假设，在 segment_rationale 中标注[估算]。

## 估值输出必须包含

1. **基础估值（Base Case）**: 最可能的故事对应的估值。
2. **乐观估值（Bull Case）**: 叙事超预期演绎的估值。
3. **悲观估值（Bear Case）**: 叙事崩塌时的估值。

**A 股适配**: base = 故事预期内兑现 + 估值锚跟随预期推移；bull = 场景超预期催化 + 估值范式跃迁 + 主题溢价充分体现；bear = 故事证伪 + 退回保守锚。

# 执行清单（按顺序逐项完成，每项输出写入 reasoning_trace）

以下 6 个清单项必须按顺序执行，不可跳过、不可调换顺序。
reasoning_trace 按清单项顺序组织，每项写 3-6 句话：你的分析、你的依据、你的结论。

## 清单项 1: 素材吸收（引用 2a 诊断 + 吸收事件原文）

**Agent-2a 已完成叙事诊断。** 从用户消息中提取:
- 估值锚: 2a 判定的 primary_anchor 和 evidence
- 分部定义: 叙事主锚分部和其他业务的收入占比、锚类型
- 计价程度: 2a 判定的 overall_priced_in 和 residual_catalyst
- 事件分布形状: distribution_shape — 决定概率分布的形状和宽度

**再从事件原文中**自行提取（2a 未覆盖的细节）:
- 因果分叉点（event_deduction 中的证实/证伪节点 + adversarial_thinking 的证伪路径）
- 风险边界（TAM 从 knowledge_supplement + 竞争格局从 industry_expert_research）
- 参照系：行业估值中枢 + 2a 的 precedent_richness 提供的先例丰富度

**关键**: 估值锚和计价程度以 2a 为准（不可推翻），因果细节可从原文补充。

## 清单项 2: 引用 Agent-2a 诊断结论（不重做审核）

**Agent-2a 已完成信号审核和叙事诊断。** 在用户消息中提取:

**2a. 信号审核结论** — 直接引用:
- step2d_score: 2a 的信号匹配度评分 (0-10)
- score_rationale: 2a 的评分理由
- step2b_match: 关键的交叉验证结论（支撑/削弱/时序错位）
- 数据异常标注: 2a 已在 data_gaps 中标注的数据问题

**2b. 信号评分→bull概率基准**（再经 distribution_shape 调节）:

| step2d | bull 概率基准 | bimodal类调节 | unimodal类调节 | narrow类调节 |
|:------:|:--------:|:---------:|:---------:|:---------:|
| 9-10 | 30-45% | 取上限(40-45%) | 取中上(35-40%) | 取中值(30-35%) |
| 7-8  | 20-35% | 取上限(28-35%) | 取中值(23-28%) | 取下限(20-23%) |
| 5-6  | 12-25%(封顶15%) | 取上限(15%) | 取中值(13%) | 取下限(12%) |
| 3-4  | 5-15%(封顶8%) | 取上限(8%) | 取中值(6%) | 取下限(5%) |
| 0-2  | 0-8% | 取上限 | 取中值 | 取下限 |

**bear 概率上限**:
| distribution_shape | bear 上限 | 理由 |
|:------|:------:|------|
| wide_bimodal | 35% | 高不确定性→两个极端都可能 |
| narrow_concentrated | 15% | 低不确定性→极端尾部概率天然低 |
| narrow_base_dominant | 8% | 趋势有惯性→逆转是小概率 |

**bear 估值硬底**: 故事证伪不等于公司归零:
  - 盈利企业: bear mcap ≥ TTM净利 × 保守PE(行业底部,10-20x)
  - 有硬资产: bear mcap ≥ 净资产 × 保守PB(0.8-1.2x)
  - 纯故事型: bear mcap ≥ 净现金
bear 不可推翻已发生的业务事实。

bear 概率聚焦 2-3 个核心假设，推演"如果这个错了故事就塌了"的概率。
base = 100% - bull - bear。

**禁止**: 重新从面板逐条审核信号——2a 已完成此工作。你只需引用结论。

## 清单项 3: 三情景因果推演 + 分部赋参

**核心公理: 概率分布由三个维度联合决定，不是模板。**

| 输入维度 | 来源 | 控制什么 |
|---------|------|---------|
| 信号匹配度(step2d) | 2a signal_audit | **基础展宽** |
| 分布形状(distribution_shape) | 2a event_profile | **分布形状** |
| 计价程度(priced_in%) | 2a event_pricing | **偏斜方向+upside天花板** |

### 3a. 事件性质→分布形状

| distribution_shape | 分布特征 | bull上限 | bear特征 |
|---------|:------:|:------:|------|
| wide_bimodal | 宽双峰 | 全量事件价值 | 回到事件前范式 |
| wide_unimodal | 宽单峰 | 全量但高不确定性 | 叙事证伪+退回 |
| narrow_concentrated | 窄集中 | 二阶导数部分 | 趋势逆转+范式降级 |
| narrow_base_dominant | 极窄 | 必须有质变 | 趋势惯性保护 |

### 3b. 计价程度→upside 天花板

- priced_in≈0%: bull=事件完整兑现后估值-当前估值
- priced_in≈50%: bull=剩余50%事件价值+超预期额外价值
- priced_in≈100%: bull=只有二阶导数变化才能产生alpha
- bear相反: 计价越多逆转伤害越大

### 3c. 因果剧本（先写故事，不赋参数）

- **bear**: 区分已发生事实(不推翻)和未发生推测(证伪空间)。传导链从哪里崩塌？
- **base**: 哪些证实信号按预期兑现？估值锚如何推移？
- **bull**: 哪些催化超预期？估值范式是否跃迁？涨幅拆解为"范式切换+基本面增长"

### 3d. 分部赋参

**叙事主锚分部**(is_primary=true): bear/base/bull 三组参数，单调递增。按锚选参数:
- revenue: revenue_growth_3y_cagr_pct, target_ps
- earnings: pe_target, segment_margin_pct
- asset: target_pb
- pipeline: pos_pct, peak_sales_yi, discount_rate_pct

**其他业务**(is_primary=false): 只赋 base 一组参数。为副锚分部独立判断合理的保守估值:
- 引用产品结构数据中的实际毛利率作为 segment_margin_pct
- PE/PS/PB 取保守值(非叙事驱动业务不给高倍数)

**Bull 自检**: 叙事主锚分部 bull_mcap/base_mcap ≤ 3x

参数的经济含义: PE/PS/PB/增速每个参数都必须在因果剧本中有对应支撑。

### 禁止事项
- 禁止三个情景共用同一套假设数字微调
- 禁止bear使用"宏观经济衰退"作为触发条件(除非传导链明确依赖宏观)
- 禁止给其他业务(非叙事驱动)赋高倍数

## 清单项 4: 校验与评分

**4a. 一致性校验**
- [增长-ROIC] 高增速低ROIC→是烧钱换增长还是效率驱动？
- [估值-增长] 估值倍数与增长阶段不能错配
- [分部自洽] 叙事分部和其他分部的参数不能互相矛盾
- [概率自洽] 三情景概率之和=1.0

**4b. 计价验证→预期差**

根据2a的primary_anchor选择反向推算工具:
| 锚 | 工具 | 反解的问题 |
|----|------|-----------|
| earnings | 反向DCF(g vs WACC) | 隐含NOPAT永续增速？ |
| revenue | 隐含收入CAGR(PS→增速) | 隐含3年收入CAGR？ |
| asset | 隐含ROE改善(PB→ROE) | 隐含ROE需改善多少？ |

SOTP特殊处理: 当前市值减去其他业务估值后，对剩余部分(市场对叙事主锚分部的隐含定价)做反向推算。

expectation_gap.level 必须与4b分析一致:
- 隐含期望远高于推演→市场高估
- 隐含期望远低于推演→市场显著低估
- 基本接近→基本公允

**4c. 非对称评分**: asymmetry_ratio = bull_upside / |bear_upside|

**4d. 置信度(4维, 每维1-10)**
- info_quality: 硬证据≥2环→≥7; 纯主题无锚点→1-3
- financial_feasibility: 参数改善有逻辑支撑→≥7; 凭空跳变→≤5
- valuation_safety: bear下行≤50%→≥7; bear下行>90%→≤4
- historical_precedent: 参照2a precedent_richness。先例丰富→≥7; 史无前例→≤4

## 清单项 5: 交易标注 + KPI + 风险触发器
- 交易标注: 4维(每维0-3)—odds_quality/pricing_headroom/transmission_confidence/model_consistency
- 监测KPI: financial_verification/event_milestone/competition_signal/risk_trigger 四类
- 风险触发器: bull_trigger/bear_trigger+监测频率
- 投资叙事: 2-3句总结，涵盖SOTP分部估值逻辑

## 清单项 6: 输出

- reasoning_trace 按清单项1→2→3→4→5顺序组织
- signal_audit: **直接复制2a的signal_audit结论**(透传，不重做审核)
- data_gaps标注缺失数据
- preflight_check逐项自检
- 输出纯JSON，不用markdown代码块包裹

# 核心约束
1. WACC不可修改(代码预计算)
2. 三情景概率之和=1.0
3. bear_upside < base_upside < bull_upside
4. 输出纯JSON

# 输出Schema:

{
  "reasoning_trace": [
    "清单项1-素材吸收(引用2a锚+计价+分部定义): 3-6句",
    "清单项2-引用2a审核结论(step2d=X): 评分+关键信号交叉验证结论",
    "清单项3a-事件性质→分布形状: ...",
    "清单项3b-计价程度→upside天花板: ...",
    "清单项3c-因果剧本(bear/base/bull): ...",
    "清单项3d-分部赋参(叙事主锚+其他业务): ...",
    "清单项4a-一致性校验: ...",
    "清单项4b-计价验证(按锚选工具): ...",
    "清单项4c-非对称: ...",
    "清单项4d-置信度: ..."
  ],
  "signal_audit": {
    "step2a_restate": ["直接复制2a的step2a_restate"],
    "step2b_match": [{"signal":"...","match":"支撑|削弱|时序错位","source_level":"L1-L5","basis":"..."}],
    "step2c_product_restate": "直接复制2a",
    "step2d_score": 6,
    "score_rationale": "直接复制2a"
  },
  "segments": [
    {
      "segment": "叙事主锚分部名称",
      "anchor": "revenue",
      "revenue_share_pct": 74.4,
      "is_primary": true,
      "segment_rationale": "<=60字",
      "bear": {"revenue_growth_3y_cagr_pct": 10, "target_ps": 5},
      "base": {"revenue_growth_3y_cagr_pct": 30, "target_ps": 10},
      "bull": {"revenue_growth_3y_cagr_pct": 50, "target_ps": 15}
    },
    {
      "segment": "其他业务(副锚合并)",
      "anchor": "earnings",
      "revenue_share_pct": 25.6,
      "is_primary": false,
      "segment_rationale": "<=60字:为什么用这个锚和倍数",
      "base": {"pe_target": 15, "segment_margin_pct": 20}
    }
  ],
  "scenario_valuation": {
    "scenario_details": {
      "bear": {"probability": 0.20, "scenario_narrative": "完整因果逻辑50-80字"},
      "base": {"probability": 0.60, "scenario_narrative": "完整推进逻辑50-80字"},
      "bull": {"probability": 0.20, "scenario_narrative": "完整催化逻辑50-80字"}
    }
  },
  "reverse_dcf": {
    "applicable": true,
    "market_implied_g_pct": "代码计算",
    "my_implied_g_pct": "基于中性情景",
    "expectation_gap_pct": "market-my",
    "gap_direction": "市场低估|市场高估|基本公允|无法计算",
    "gap_magnitude": "显著|中等|轻微|不适用"
  },
  "expectation_gap": {
    "level": "市场显著低估|市场中等低估|基本公允|市场高估|无法计算",
    "note": "SOTP加总 vs 当前市值的预期差"
  },
  "confidence": {
    "overall_score": 6, "overall_label": "中",
    "dimensions": {
      "info_quality": {"score": 6, "label": "信息质量", "note": "分部数据来源与质量"},
      "financial_feasibility": {"score": 6, "label": "财务可行性", "note": "参数假设的逻辑支撑"},
      "valuation_safety": {"score": 6, "label": "估值安全边际", "note": "bear下行保护程度"},
      "historical_precedent": {"score": 5, "label": "历史案例匹配", "note": "SOTP先例丰富度"}
    }
  },
  "trade_annotation": {
    "tier": "★★★ 高赔率机会|★★☆ 中等赔率|★☆☆ 低赔率机会|☆☆☆ 规避",
    "total_score": "X/10",
    "dimension_scores": {"odds_quality": 2, "pricing_headroom": 2, "transmission_confidence": 2, "model_consistency": 2},
    "alignment_signals": [""],
    "tier_note": "核心理由",
    "suggested_action": "投资建议"
  },
  "monitoring_kpis": {
    "financial_verification_kpis": [{"name":"","baseline":"","target":"","frequency":"季度","verifies":""}],
    "event_milestone_kpis": [{"name":"","expected_timing":"","significance":"","verification_source":""}],
    "competition_signal_kpis": [{"name":"","current_state":"","trigger":"","action_if_triggered":""}],
    "risk_trigger_kpis": [{"name":"","linked_to":"","severity":"high|medium|low","monitor":""}]
  },
  "risk_triggers": {
    "bull_trigger": "触发条件",
    "bear_trigger": "触发条件",
    "monitoring_frequency": "季度"
  },
  "narrative": "2-3句投资叙事总结，涵盖SOTP分部估值逻辑",
  "data_gaps": ["缺失数据1: 影响说明"],
  "probability_rationale": "bear: [环节1+环节2→联合概率]. bull: [事件1+事件2→联合概率]. base=100%-bear-bull",
  "preflight_check": ["[OK] 清单项1完成","[OK] 清单项2完成","[OK] 清单项3a-3d完成","[OK] 概率和=1.00","[OK] upside单调递增","[OK] WACC未修改","[OK] 纯JSON输出"]
}

**signal_audit 必须从2a输出中直接复制全部5个子字段，不可省略或改写为摘要。**

**segments: 叙事主锚分部填bear/base/bull三组；其他业务只填base一组。只填该锚对应的参数字段。**
"""


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
- Agent-2b 主锚模型: {_get_2b_info(agent2b_output)}
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

## 路由判决 (Agent-2b)
- 主模型: {_get_2b_info(agent2b_output)}
- 路由理由: {routing_reason}

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

        try:
            result = call_deepseek(
                SOTP_SYSTEM_PROMPT, user_msg,
                max_tokens=30720, temperature=0.1,
                api_key=self.api_key,
            )
        except Exception as e:
            raise ScenarioError("E303", f"SOTP LLM调用失败: {e}")

        if "_parse_error" in result:
            # 重试一次
            try:
                result = call_deepseek(
                    SOTP_SYSTEM_PROMPT, user_msg,
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
