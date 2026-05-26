"""
V3 案例库加载器 — V5

数据源: .agents/agents/shenwaihuashen/memory/cases/case-*.json (42条)

匹配算法 (8规则, 满分 20):
  R1 行业匹配 +3    R2 驱动语义 +3    R3 ROIC连续 +3
  R4 ROIC临近 +2    R5 市值量级 +2    R6 PE符号 +1
  R7 催化剂共词 +1  R8 PE轨迹 +2     NEG 驱动矛盾 -2
"""

import json
import re
from pathlib import Path

_CASES_DIR = Path(__file__).resolve().parent.parent.parent / ".agents" / "agents" / "shenwaihuashen" / "memory" / "cases"

_INDUSTRY_KEYWORDS = {
    "通信设备": ["通信", "光模块", "光通信", "网络"],
    "电子": ["半导体", "芯片", "集成电路", "电子", "PCB", "封测"],
    "医药生物": ["医药", "制药", "生物", "医疗", "药"],
    "计算机": ["软件", "AI", "人工智能", "算力", "云"],
    "有色金属": ["矿", "锂", "钴", "稀土", "金属"],
    "化工": ["化工", "化学", "材料", "乙烯"],
    "电力设备": ["电力", "光伏", "储能", "电池", "新能源"],
    "机械设备": ["机械", "设备", "制造", "机器人"],
    "汽车": ["汽车", "智能驾驶", "零部件"],
    "消费": ["食品", "饮料", "零售", "消费"],
}

DRIVER_TYPES = {
    "技术突破": {"技术突破", "国产替代", "打破垄断", "从0到1", "认证", "突破", "替代", "创新", "首发"},
    "业绩拐点": {"业绩拐点", "扭亏", "盈利改善", "利润", "增长", "加速", "拐点", "反转"},
    "商业模式升级": {"商业模式", "平台化", "转型", "SaaS", "订阅", "升级"},
    "政策驱动": {"政策", "补贴", "扶持", "碳中和", "碳达峰", "环保", "双碳"},
}

CATALYST_KEYWORDS = ["订单", "审批", "技术突破", "并购", "政策", "投产", "认证", "签约", "放量", "涨价", "扩产", "通过"]


def load_cases() -> list[dict]:
    """加载全部 42 条 V3 案例。"""
    cases = []
    if not _CASES_DIR.exists():
        return cases
    for f in sorted(_CASES_DIR.glob("case-*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                cases.append(_normalize(json.load(fh)))
        except (json.JSONDecodeError, KeyError):
            continue
    return cases


def _normalize(raw: dict) -> dict:
    return {
        "stock_code": raw.get("stockCode", ""),
        "stock_name": raw.get("stockName", ""),
        "sector": raw.get("sector", ""),
        "primary_driver": raw.get("primaryDriver", ""),
        "return_type": raw.get("returnType", ""),
        "tags": raw.get("tags", []),
        "roic_trough": _float(raw, "roicTrough"),
        "roic_peak": _float(raw, "roicPeak"),
        "roic_improvement": _float(raw, "roicImprovement"),
        "gm_trough": _float(raw, "gmTrough"),
        "gm_peak": _float(raw, "gmPeak"),
        "pe_expansion": _float(raw, "peExpansion"),
        "profit_expansion": _float(raw, "profitExpansion"),
        "gain_multiple": _float(raw, "gainMultiple"),
        "actual_return_pct": _float(raw, "actualReturnPct"),
        "start_mcap": _float(raw, "startMcap"),
        "start_pe": _float(raw, "startPE"),
        "peak_pe": _float(raw, "peakPE"),
        "catalyst": raw.get("catalyst", ""),
        "logic": raw.get("logic", ""),
        "end_state": raw.get("endState", ""),
        "routing_reason": raw.get("routingReason", ""),
        "failure_mode": raw.get("failureMode", []),
    }


def _float(d: dict, key: str) -> float | None:
    v = d.get(key)
    if v is None: return None
    try: return float(v)
    except (ValueError, TypeError): return None


# ═══════════════════════════════════════
# 匹配辅助函数
# ═══════════════════════════════════════

def _mcap_bucket(mcap: float | None) -> str:
    if mcap is None: return "unknown"
    if mcap < 30: return "tiny"
    if mcap < 200: return "small"
    if mcap < 1000: return "mid"
    return "large"


def _bigrams(text: str) -> set[str]:
    """提取文本中的双字共词集合。"""
    cleaned = re.sub(r'[^一-鿿]', '', text)
    return {cleaned[i:i+2] for i in range(len(cleaned) - 1)}


def _classify_driver(text: str) -> str:
    """从文本推断驱动类型。"""
    best, best_score = "", 0
    for dt, kws in DRIVER_TYPES.items():
        score = sum(1 for kw in kws if kw in text)
        if score > best_score:
            best, best_score = dt, score
    return best if best_score >= 2 else ""


# ═══════════════════════════════════════
# 匹配质量标签
# ═══════════════════════════════════════

def match_quality_label(top_score: int) -> str:
    """根据最高匹配分返回可信度标签。"""
    if top_score >= 8:
        return "高度可比 — 案例参数可直接参照，模型路径高度相关"
    elif top_score >= 5:
        return "中等可比 — 案例参数作重要参考，需独立验证财务可行性"
    else:
        return "弱可比 — 仅作上限参考，以财务数据为主要依据"


def build_rich_anchors(matches: list[tuple[dict, int]], top_n: int = 5) -> str:
    """构建丰富的案例锚点文本（含 catalyst/logic/routing_reason/end_state）。"""
    if not matches:
        return ""

    top_score = matches[0][1] if matches else 0
    lines = [
        f"\n## V3案例锚点 — {match_quality_label(top_score)}",
        f"42条历史十倍股案例库，匹配最高分: {top_score}/20",
        ""
    ]

    roic_imps, pe_exps, gains = [], [], []
    for c, s in matches[:top_n]:
        roi = c.get("roic_improvement")
        pex = c.get("pe_expansion")
        g = c.get("gain_multiple") or (
            c.get("actual_return_pct", 0) / 100 + 1 if c.get("actual_return_pct") else None)
        if roi: roic_imps.append(roi)
        if pex: pe_exps.append(pex)
        if g and g > 1: gains.append(g)

        lines.append(
            f"### {c['stock_name']}({c['stock_code']}) — 匹配 {s}/20"
        )
        lines.append(f"- 驱动: {c.get('primary_driver', '?')} | 行业: {c.get('sector', '?')}")
        lines.append(f"- ROIC: {c.get('roic_trough','?')}%→{c.get('roic_peak','?')}% (+{roi or '?'}ppt) | "
                     f"PE: {c.get('start_pe','?')}x→{c.get('peak_pe','?')}x (扩张{pex or '?'}x)")
        lines.append(f"- 回报: {g or '?'}x | 起涨市值: {c.get('start_mcap','?')}亿 | 催化剂: {(c.get('catalyst','') or '')}")
        lines.append(f"- 投资逻辑: {(c.get('logic','') or '')}")
        if c.get('routing_reason'):
            lines.append(f"- 路由依据: {(c.get('routing_reason','') or '')}")
        lines.append(f"- 终态: {c.get('end_state', '')}")
        lines.append("")

    if roic_imps:
        sorted_ri = sorted(roic_imps)
        lines.append(f"**ROIC改善范围**: +{sorted_ri[0]:.0f}~+{sorted_ri[-1]:.0f}ppt (中位+{sorted_ri[len(sorted_ri)//2]:.0f}ppt)")
    if pe_exps:
        sorted_pe = sorted(pe_exps)
        lines.append(f"**PE扩张范围**: {sorted_pe[0]:.1f}x~{sorted_pe[-1]:.1f}x (中位{sorted_pe[len(sorted_pe)//2]:.1f}x)")
    if gains:
        sorted_g = sorted(gains)
        lines.append(f"**回报范围**: {sorted_g[0]:.1f}x~{sorted_g[-1]:.1f}x (中位{sorted_g[len(sorted_g)//2]:.1f}x)")

    return "\n".join(lines)


# ═══════════════════════════════════════
# 主匹配函数
# ═══════════════════════════════════════

def find_similar(agent1_output: dict, top_n: int = 8,
                 cases: list[dict] | None = None) -> list[tuple[dict, int]]:
    """8规则匹配，返回 (case_dict, score) 按分降序。

    R1 行业 +3  R2 驱动语义 +3  R3 ROIC连续 +3  R4 ROIC临近 +2
    R5 市值 +2  R6 PE符号 +1    R7 催化剂 +1    R8 PE轨迹 +2
    NEG 驱动矛盾 -2
    满分 = 20
    """
    if cases is None:
        cases = load_cases()

    cf = agent1_output.get("clean_financials", {})
    im = agent1_output.get("investment_map", {})
    current_roic = cf.get("roic_pct", 0)
    current_mcap = cf.get("market_cap_yi", 0)
    current_industry = cf.get("industry", "")
    current_pe = cf.get("pe_ttm") or agent1_output.get("valuation_anchor", {}).get("pe_ttm", 0)
    theme = (im.get("investment_theme", "") or
             im.get("event_deduction", "") or
             agent1_output.get("valuation_routing", {}).get("reason", ""))
    current_driver = _classify_driver(theme)
    theme_bigrams = _bigrams(theme)

    scored = []
    for c in cases:
        score = 0

        # ── R1: 行业匹配 (+3) ──
        score += _industry_score(c["sector"], c["tags"], current_industry)

        # ── R2: 驱动语义匹配 (+3) ──
        case_logic = c.get("logic", "")
        case_bigrams = _bigrams(case_logic + (c.get("catalyst", "") or ""))
        common = theme_bigrams & case_bigrams
        score += min(3, len(common))

        # ── R3: ROIC 连续距离 (+3) ──
        if c["roic_trough"] is not None and isinstance(current_roic, (int, float)):
            diff = abs(c["roic_trough"] - current_roic)
            if diff <= 3: score += 3
            elif diff <= 6: score += 2
            elif diff <= 9: score += 1

        # ── R4: ROIC 临近 (+2) ──
        if c["roic_trough"] is not None and isinstance(current_roic, (int, float)):
            if abs(c["roic_trough"] - current_roic) < 5: score += 2
            elif abs(c["roic_trough"] - current_roic) < 10: score += 1

        # ── R5: 市值量级 (+2) ──
        if _mcap_bucket(c["start_mcap"]) == _mcap_bucket(current_mcap): score += 2
        elif c["start_mcap"] and current_mcap:
            if abs((c["start_mcap"] or 0) - current_mcap) < 200: score += 1

        # ── R6: PE 符号 (+1) ──
        case_pe = c["start_pe"]
        if case_pe and current_pe and (case_pe > 0) == (current_pe > 0): score += 1

        # ── R7: 催化剂共词 (+1) ──
        case_catalyst = (c.get("catalyst") or "").lower()
        for kw in CATALYST_KEYWORDS:
            if kw in case_catalyst and kw in theme.lower():
                score += 1
                break

        # ── R8: PE 扩张轨迹 (+2) ──
        pe_exp = c.get("pe_expansion")
        start_pe = c.get("start_pe")
        peak_pe = c.get("peak_pe")
        if pe_exp and start_pe and peak_pe and start_pe > 0 and current_pe and current_pe > 0:
            case_pe_ratio = peak_pe / start_pe  # 案例 PE 扩张倍数
            # 用 start_pe 与 current_pe 的比例估算"当前相当于案例的哪个阶段"
            # 若 current_pe / start_pe 在 0.5~2.0 之间，说明处于类似估值水位
            stage_ratio = current_pe / start_pe
            if 0.5 <= stage_ratio <= 2.0:
                score += 2
            elif 0.3 <= stage_ratio <= 3.0:
                score += 1

        # ── NEG: 驱动类型矛盾 (-2) ──
        case_driver = c.get("primary_driver", "")
        if current_driver and case_driver and current_driver != case_driver:
            score -= 2

        scored.append((c, max(0, score)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_n]


def assess_anchor_reliability(matches: list[tuple[dict, int]]) -> dict:
    """根据案例匹配质量评估锚定可靠性。

    返回 dict:
      - reliability: "high"|"medium"|"low"|"none"
      - top_score: 最高匹配分
      - top_n_avg: top3 平均分
      - note: 对下游 Agent 的处理建议
    """
    if not matches:
        return {
            "reliability": "none",
            "top_score": 0,
            "top_n_avg": 0,
            "note": "无匹配案例。Agent-3应完全依赖第一性原理推演，案例锚定权重=0。"
        }

    scores = [s for _, s in matches]
    top_score = scores[0]
    top3_avg = sum(scores[:3]) / min(3, len(scores))

    if top_score >= 15:
        return {
            "reliability": "high",
            "top_score": top_score,
            "top_n_avg": round(top3_avg, 1),
            "note": "高度可比案例存在。Agent-3应以此案例统计量作为参数中轴，偏离需有强力叙事支撑。"
        }
    elif top_score >= 10:
        return {
            "reliability": "medium",
            "top_score": top_score,
            "top_n_avg": round(top3_avg, 1),
            "note": "中等可比。Agent-3参考案例统计区间但不锚定中位，参数可偏离50%以内。"
        }
    else:
        return {
            "reliability": "low",
            "top_score": top_score,
            "top_n_avg": round(top3_avg, 1),
            "note": "无可比案例。Agent-3完全使用第一性原理推演。案例仅提供'是否有先例'的思路参考，参数不受案例约束。降低confidence.historical_precedent评分至≤4。"
        }


# ── R1 行业匹配置信函数 ──

def _industry_score(case_sector: str, case_tags: list, target_industry: str) -> int:
    if not target_industry: return 0
    if case_sector and (case_sector in target_industry or target_industry in case_sector):
        return 3
    for ind_name, keywords in _INDUSTRY_KEYWORDS.items():
        if any(kw in (target_industry or "") for kw in keywords):
            if case_sector == ind_name: return 3
            if any(kw in (case_sector or "") for kw in keywords): return 3
            for tag in (case_tags or []):
                if any(kw in tag for kw in keywords): return 2
    return 0
