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

SOTP_SYSTEM_PROMPT = """你是 SOTP（Sum-of-Parts）分部估值师。

你的任务只有一个：推演**叙事主锚分部**在 bear/base/bull 三情景下的经营参数。其他业务由代码自动计算，你不需要处理。

# 为什么需要 SOTP

这家公司的不同业务线适用**完全不同的估值范式**。但催化剂事件只影响叙事主线——其他业务在事件窗口内基本不变。

因此 SOTP 只需拆两段：
1. **叙事主锚分部**: 事件驱动的核心业务。你推演 bear/base/bull 三情景参数
2. **其他业务**: 代码自动计算（简单公式：收入 x 行业毛利率 x 保守PE，或收入 x 保守PS），三情景不变

# 你的输入

1. **叙事主锚分部定义**：名称、锚类型、收入占比
2. **主锚模型**：Agent-2b 选定的估值模型（确定你应该用哪组参数体系）
3. **产品结构数据**：分产品毛利率（如有，优先引用）
4. **核心财务数据**：市值/营收/利润/PE/PB/PS/净现金
5. **事件背景**：投资主题、行业研究
6. **WACC**：预计算值（不可修改）

# 估值锚 -> 参数体系

根据 Agent-2b 选定的主锚模型，输出对应参数：

| 锚 | 对应模型 | 参数 | 代码公式 |
|----|---------|------|---------|
| **earnings** | A/C/G/I/K | pe_target, segment_margin_pct | 分部利润 = 分部收入 x 毛利率; 市值 = 利润 x PE |
| **revenue** | B | revenue_growth_3y_cagr_pct, target_ps | 3年后收入 x PS |
| **asset** | D/H | target_pb | 净资产 x PB |
| **pipeline** | F | pos_pct, peak_sales_yi, discount_rate_pct | 峰值销售 x PoS / (1+折现率) |

注意：earnings 锚**不需要** roic_assumed_pct 和 rr_assumed_pct——SOTP 用收入x毛利率简化估算分部利润（分部投入资本无法从合并报表拆分）。

# 分部收入估算

分部收入 = 公司总收入 x 收入占比。

对于 **earnings 锚**的分部，你需要输出 segment_margin_pct：
- 如果产品结构数据中有该分部的实际毛利率 -> **必须引用该数据**
- 如果没有 -> 基于行业知识和公司整体毛利率做合理假设，在 segment_rationale 中标注[估算]

# 三情景推演（仅叙事主锚分部）

关于情景推演的质量标准——你需要达到和标准 Agent-3 完全相同的要求：

- **bear**: 经营恶化。证伪路径必须区分已发生事实（不推翻）和未发生推测（证伪空间）。传导链从哪里崩塌？回到什么估值？
- **base**: 证实信号按预期兑现。估值锚如何推移？当前已计价的部分是否已在 base 中体现？
- **bull**: 催化超预期。超预期的幅度对应剩余计价空间。估值范式是否跃迁？涨幅拆解为"范式切换 + 基本面增长"。

**Bull 自检**: bull_mcap / base_mcap <= 3x（除非明确范式切换催化剂支撑更高）

**核心约束**:
1. 概率之和 = 1.0
2. bear < base < bull 参数单调递增
3. bear 不能推翻已发生事实
4. 分部毛利率优先引用产品结构实际数据

# 输出格式（必须输出完整字段，不可省略）

以下是**完整 JSON**，每个字段都必须输出实际内容，不可用 "..." 省略：

```json
{
  "reasoning_trace": [
    "清单项1-叙事理解: 叙事主锚分部在讲什么故事？事件如何驱动它？为什么锚是revenue/earnings？3-6句详细分析",
    "清单项2-三情景因果推演: bear触发链(证伪路径，区分已发生vs未发生) + base推进链(预期内兑现节点) + bull催化链(超预期条件+范式切换可能)。每情景3-5句",
    "清单项3-赋参: bear/base/bull 每个情景的参数选取逻辑和数据依据（引用了哪些产品结构数据或行业参照）。每情景2-3句",
    "清单项4-校验: 参数自检(增速-ROIC-倍数是否自洽) + 概率自洽(bear需要哪些独立环节同时崩塌) + 置信度评分依据。5-8句"
  ],
  "primary_segment": {
    "segment": "叙事主锚分部名称",
    "anchor": "revenue",
    "revenue_share_pct": 74.4,
    "segment_rationale": "为什么这个分部是叙事驱动，为什么用这个锚",
    "bear": {"revenue_growth_3y_cagr_pct": 10, "target_ps": 5},
    "base": {"revenue_growth_3y_cagr_pct": 30, "target_ps": 10},
    "bull": {"revenue_growth_3y_cagr_pct": 50, "target_ps": 15}
  },
  "scenario_valuation": {
    "scenario_details": {
      "bear": {"probability": 0.20, "scenario_narrative": "完整因果逻辑: 触发条件→传导链→估值结果，50-80字"},
      "base": {"probability": 0.60, "scenario_narrative": "完整推进逻辑: 预期兑现节点→锚推移→估值结果，50-80字"},
      "bull": {"probability": 0.20, "scenario_narrative": "完整催化逻辑: 超预期条件→范式切换→基本面增长→估值结果，50-80字"}
    }
  },
  "expectation_gap": {
    "level": "市场显著低估 | 市场中等低估 | 基本公允 | 市场高估 | 无法计算",
    "note": "SOTP 加总 vs 当前市值的预期差分析，详细说明差距意味着什么，80-150字"
  },
  "confidence": {
    "overall_score": 6,
    "overall_label": "中",
    "dimensions": {
      "info_quality": {"score": 6, "label": "分部数据质量", "note": "分部收入来源、毛利率数据质量、可比倍数参照的可靠性，20-40字"},
      "financial_feasibility": {"score": 6, "label": "财务假设可行性", "note": "增长率/利润率/倍数假设是否有逻辑支撑，20-40字"},
      "valuation_safety": {"score": 6, "label": "估值安全边际", "note": "bear下行空间保护程度，是否有硬资产/净现金兜底，20-40字"},
      "historical_precedent": {"score": 5, "label": "可比参照质量", "note": "类似SOTP案例的先例丰富度和匹配度，20-40字"}
    }
  },
  "trade_annotation": {
    "tier": "★★★ 高赔率机会 | ★★☆ 中等赔率 | ★☆☆ 低赔率机会 | ☆☆☆ 规避",
    "total_score": "X/10",
    "dimension_scores": {"odds_quality": 2, "pricing_headroom": 2, "transmission_confidence": 2, "model_consistency": 2},
    "alignment_signals": ["支撑信号1", "支撑信号2"],
    "tier_note": "核心理由，包括分部估值的可靠性评估，30-60字",
    "suggested_action": "对投资者的具体建议，20-40字"
  },
  "monitoring_kpis": {
    "financial_verification_kpis": [{"name": "分部收入占比", "baseline": "XX%", "target": "XX%", "frequency": "季度", "verifies": "分部定义准确性"}],
    "event_milestone_kpis": [{"name": "关键催化节点", "expected_timing": "202XHX", "significance": "high", "verification_source": "年报/公告"}],
    "competition_signal_kpis": [{"name": "竞争信号", "current_state": "...", "trigger": "...", "action_if_triggered": "..."}],
    "risk_trigger_kpis": [{"name": "风险指标", "linked_to": "bear情景", "severity": "high", "monitor": "..."}]
  },
  "risk_triggers": {
    "bull_trigger": "bull情景的核心催化条件，30-60字",
    "bear_trigger": "bear情景的核心恶化条件，30-60字",
    "monitoring_frequency": "季度(与财报同步验证分部数据)"
  },
  "narrative": "2-3句完整投资叙事总结，涵盖分部估值逻辑+SOTP加总结论，50-100字",
  "data_gaps": ["缺失数据1: 影响说明", "缺失数据2: 影响说明"],
  "probability_rationale": "bear: [独立环节1(概览%) + 环节2(概览%) + ... → 联合概率Z%]. bull: [超预期事件1(概览%) + 事件2(概览%) + ... → 联合概率Z%]. base = 100% - bear - bull",
  "preflight_check": [
    "[OK] 清单项1叙事主锚理解完成",
    "[OK] 清单项2三情景因果推演完成",
    "[OK] 清单项3赋参完成(引用产品结构/行业数据)",
    "[OK] 概率和=1.00",
    "[OK] bear<base<bull单调递增",
    "[OK] bull/base<=3x自检通过",
    "[OK] 所有字段完整输出,无省略"
  ]
}
```

只填 primary_segment 的 bear/base/bull 参数，其他业务由代码自动计算。

# 核心约束
1. 只输出叙事主锚分部的参数
2. bear < base < bull 单调递增
3. Bull 市值 / Base 市值 <= 3x
4. **所有字段必须完整输出，不可写成 "..." 或留空**
5. **reasoning_trace 至少 4 条，每条至少 3 句**
6. **scenario_narrative 每条至少 50 字**
7. 输出纯 JSON
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

## 事件背景 (Agent-0 预研)

### 投资主题
{event_data.get('investment_theme', '')[:1000]}

### 事件推演
{event_data.get('event_deduction', '')[:800]}

### 行业研究
{event_data.get('industry_expert_research', '')[:800]}

### 知识补充
{event_data.get('knowledge_supplement', '')[:800]}

### 空头审查
{event_data.get('adversarial_thinking', '')[:500]}

{signal_panel}

## 火山搜索补充数据
{_build_volc_section(volc_data)}

请只推演叙事主锚分部的 bear/base/bull 参数。如有火山搜索补充的毛利率数据，优先引用。输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# 核心计算函数 — SOTP 分部加总
# ═══════════════════════════════════════

def _compute_other_value(
    secondary_anchors: list[dict],
    core: dict,
) -> float:
    """纯代码计算其他业务（非叙事驱动）的基准估值。

    简单公式：
    - earnings锚: 分部收入 x 公司净利率 x 保守PE(行业底部10-15x)
    - revenue锚: 分部收入 x 保守PS(0.5-1.5x)
    - asset锚: 分部净资产 x 保守PB(0.6-1.0x)
    - pipeline锚: 不作估（归零，因无管线数据）
    """
    total_rev = core.get("revenue_ttm_yi", 1)
    company_nm = core.get("net_margin_pct", 10)
    total_equity = core.get("total_equity_yi", 1)

    total_other_value = 0.0
    for sa in secondary_anchors:
        anchor = sa.get("anchor", "earnings")
        share = sa.get("revenue_share_pct", 0)
        seg_rev = total_rev * share / 100

        if anchor == "earnings":
            # 分部利润 = 分部收入 x 公司整体净利率（保守估计）
            # 分部市值 = 分部利润 x 保守PE(12x，行业底部)
            seg_nopat = seg_rev * company_nm / 100
            seg_val = seg_nopat * 12
        elif anchor == "revenue":
            # 保守PS = 1.0x（非叙事驱动业务不给高PS）
            seg_val = seg_rev * 1.0
        elif anchor == "asset":
            seg_equity = total_equity * (seg_rev / total_rev) if total_rev > 0 else 0
            seg_val = seg_equity * 0.8  # 保守PB
        else:
            seg_val = 0.0

        total_other_value += seg_val

    return round(total_other_value, 1)


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
    primary_segment: dict,
    secondary_anchors: list[dict],
    scenario_name: str,
    core: dict,
) -> dict:
    """计算单个情景的 SOTP 加总价值。

    SOTP = 叙事主锚分部(LLM参数) + 其他业务(代码自动) + 净现金

    Args:
        primary_segment: LLM 输出的叙事主锚分部（含 bear/base/bull 参数）
        secondary_anchors: Agent-2a 的副锚列表（用于代码计算其他业务）
        scenario_name: "bear" | "base" | "bull"
        core: 公司整体财务数据
    """
    total_revenue = core.get("revenue_ttm_yi", 1)
    cash = core.get("cash_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    net_cash = cash - debt

    # 1. 叙事主锚分部 —— LLM 推演的参数
    primary_name = primary_segment.get("segment", "叙事主线")
    primary_anchor = primary_segment.get("anchor", "earnings")
    primary_share = primary_segment.get("revenue_share_pct", 0)
    primary_params = primary_segment.get(scenario_name, {})
    primary_revenue = total_revenue * primary_share / 100

    primary_val = _compute_segment_value(primary_anchor, primary_params, primary_revenue, core)

    # 2. 其他业务 —— 代码自动计算（三情景不变）
    other_val = _compute_other_value(secondary_anchors, core)

    # 3. 加总
    total_value = net_cash
    segment_values = []

    if primary_val is not None:
        total_value += primary_val
        segment_values.append({
            "segment": primary_name,
            "anchor": primary_anchor,
            "revenue_share_pct": primary_share,
            "segment_revenue_yi": round(primary_revenue, 2),
            "segment_value_yi": primary_val,
            "source": "LLM",
        })

    if other_val > 0:
        total_value += other_val
        segment_values.append({
            "segment": "其他业务",
            "anchor": "mixed",
            "revenue_share_pct": 100 - primary_share,
            "segment_value_yi": other_val,
            "source": "代码自动",
        })

    return {
        "total_mcap_yi": round(total_value, 1),
        "net_cash_yi": round(net_cash, 1),
        "primary_value_yi": primary_val,
        "other_value_yi": other_val,
        "segment_values": segment_values,
        "skipped_segments": [],
    }


def _compute_sotp_from_llm(
    llm_output: dict,
    secondary_anchors: list[dict],
    core: dict,
) -> dict:
    """从 LLM 输出计算 SOTP 三情景加权结果。

    叙事主锚分部用 LLM 参数 + 其他业务用代码自动计算 = SOTP 总价值。
    回写计算结果到 llm_output，使其与 _assemble_final_output 兼容。
    """
    primary_segment = llm_output.get("primary_segment", {})
    if not primary_segment:
        # LLM might have used old format 'segments' array
        segments = llm_output.get("segments", [])
        if segments:
            primary_segment = next((s for s in segments if s.get("is_primary")), segments[0]) if segments else {}
            print(f"  [SOTP] LLM used old 'segments' format, extracted primary: {primary_segment.get('segment','?')}", flush=True)
        else:
            print(f"  [SOTP] WARNING: No primary_segment in LLM output! Keys: {list(llm_output.keys())}", flush=True)
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
        sotp = _compute_sotp_total(primary_segment, secondary_anchors, scenario_name, core)
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
        secondary_anchors = agent2a_output.get("market_narrative", {}).get("secondary_anchors", [])
        sotp_computed = _compute_sotp_from_llm(result, secondary_anchors, core)

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
            "primary_segment": result.get("primary_segment", {}),
            "other_segments": secondary_anchors,
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
