"""
灵光预筛 — 估值管线前置检查关卡 (V6.2)

在 Agent-1 数据就绪后、Agent-2a 叙事诊断前，用 Flash 模型做 4 维快速评估。
两个核心拦截逻辑:
  1. 个股涨不涨不取决于我们分析的事件（叙事-事件不同源）
  2. 蹭概念/暴露度不足/市值过大导致弹性不足

低于阈值 → 标记 is_complete=true，不进入后续估值管线。
"""

import json
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import DEEPSEEK_API_KEY

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
FLASH_MODEL = "deepseek-v4-flash"

# ═══════════════════════════════════════
# Prompt
# ═══════════════════════════════════════

PRE_SCREEN_SYSTEM = """你是一个A股投资标的预筛分析师。你的核心任务是判断: 这只股票的上涨动力是否来自我们要分析的事件，以及是否有足够的弹性值得深度估值。

# 两个核心问题

**问题一: 个股涨不涨取决于我们分析的事件吗？**
事件是我们投资地图框定的变革方向。个股有自己的投资主题。如果两者是平行线——个股涨不涨不取决于这个事件——直接拦截。
例: 事件=商业航天产业化加速，个股投资主题=湖南国资重组摘帽。两者驱动力不同，仅是字面上的"军工"交集。拦截。

**问题二: 个股有足够弹性吗？**
即使事件利好个股，如果暴露度太低(蹭概念)、市值太大(翻倍空间有限)、产业链地位边缘，也不值得深估。

# 评分维度 (每维1-10分)

## 维度1: 叙事-事件同源性 ★核心一

判断"个股上涨的驱动力"和"事件的催化剂"是否来自同一源头、指向同一方向。
注意: 评估的是驱动力是否同源，不是财务数据是否好看。

【常见陷阱：同标签≠同驱动】
行业标签相同不等于驱动力同源。例: 事件="商业航天产业化加速"，个股="湖南国资重组推动军工业务摘帽"——都有"军工"标签，但驱动逻辑完全不同。前者是产业需求拉动，后者是资本运作保壳。这不是"部分相关"，而是"平行线"。

评分标准:
- 8-10: 同源同向。事件直接驱动个股核心业务增长，因果链路清晰，有具体数字/时间节点/协议支撑
- 6-7: 高度相关。事件显著利好个股，逻辑链完整但关键数字模糊或时间不确定
- 4-5: 部分相关。事件与个股有关联且是核心驱动之一，但非唯一或最强驱动
- 2-3: 弱关联/借题发挥。个股投资主题与事件是不同的叙事，仅在行业标签/概念标签上有交集，但驱动力来源不同
- 1: 平行线/无关。个股涨不涨不取决于我们分析的事件

【拦截规则: 同源性<4的直接拦截，不进入后续估值】

## 维度2: 暴露度

评估事件对标的业务的实际影响程度。分两条轨道:

【轨道A: 成熟型】已有事件相关规模化收入
- 8-10: 相关收入占营收 >70%
- 6-7: 50-70%
- 4-5: 30-50%
- 2-3: <30%

【轨道B: 从0到1/验证突破型】产品已验证、赛道明确、收入尚未起量
- 7-9: 叙事100%绑定事件方向，技术/产品已通过客户验证(有具体客户/认证/订单)
- 5-7: 战略明确转向事件方向，验证尚早但方向确定
- 3-5: 有相关布局但非核心战略方向
- 1-3: 仅概念/题材关联，无实质业务布局

在 rationale 中声明轨道选择，格式: "轨道A/B: ..."

## 维度3: 个股弹性

评估股价对正面催化剂可能产生多大幅度的反应。市值是主要因子，但非唯一因子。

评分时综合以下因素（不要机械对照市值）:

- **市值（权重最高）**: 越小弹性越大。参考: <50亿=8-10, 50-100亿=6-7, 100-200亿=4-5, 200-500亿=2-4, >500亿=1-3
- **经营杠杆**: 固定成本占比高的公司，收入小幅改善→利润大幅跃升。重资产/高折旧/高研发费用化的公司 +1~2
- **流通盘**: 自由流通盘越小，同等资金量推动越大。大股东锁仓+机构低配+换手率低 +1
- **估值弹性**: 当前亏损但叙事兑现后盈利跳升（从0到1型），弹性额外 +1~2
- 综合以上，连续光谱取值。例: 市值600亿但高经营杠杆+低流通盘 → 弹性可给3-4而非1-2

## 维度4: 产业链地位

标的在事件相关产业链中的位置:

- 8-10: 核心节点。唯一/第一纯正标的，不可替代
- 6-7: 重要节点。稀缺(仅2-3家)，有议价权
- 4-5: 一般节点。多家竞争，可替代性中等
- 2-3: 边缘节点。无壁垒，大量竞争者
- 1: 蹭节点。产业链外，无实质关联

# 裁量调整

允许对最终总分进行 ±3 分裁量调整。裁量不是随意加减——必须有具体理由。格式:
"裁量+2: 寒武纪在AI芯片赛道的稀缺性远超同市值段，思元590已通过多家云厂商验证且是国内唯一量产替代方案"
"裁量-2: 虽然暴露度轨道A给6分，但该收入来自低壁垒的代理业务而非自主技术，实质暴露度应更低"

# 输出格式

输出纯JSON，不要用markdown代码块包裹:

{
  "stock_code": "从输入中获取",
  "homology": {"score": <1-10>, "rationale": "<<=60字"},
  "exposure": {"score": <1-10>, "rationale": "<<=60字，含轨道声明>"},
  "elasticity": {"score": <1-10>, "rationale": "<<=40字"},
  "position": {"score": <1-10>, "rationale": "<<=40字"},
  "discretionary_adjustment": <+3到-3之间的整数，0表示不调整>,
  "adjustment_reason": "<若adjustment不为0，必须写理由<=40字; 若为0写空字符串>",
  "total_score": <四维求和 + 裁量，范围1-43>,
  "cut_recommendation": "PASS" 或 "BLOCK: <原因<=30字>",
  "summary": "<一句话总结<=60字>"
}"""


# ═══════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════

@dataclass
class PreScreenResult:
    """预筛结果"""
    total_score: int = 0
    passed: bool = True          # True=通过, False=拦截
    homology: int = 5            # 叙事-事件同源性 1-10
    exposure: int = 5            # 暴露度 1-10
    elasticity: int = 5          # 个股弹性 1-10
    position: int = 5            # 产业链地位 1-10
    discretionary_adjustment: int = 0  # 裁量调整 ±3
    cut_reason: str = ""         # 拦截原因
    summary: str = ""            # 一句话总结
    raw_response: str = ""       # Flash 原始响应 (审计用)
    latency_s: float = 0.0
    _error: str | None = None    # 调用异常


# ═══════════════════════════════════════
# Gate Logic
# ═══════════════════════════════════════

def _evaluate_rules(
    homology: int,
    total: int,
    elasticity: int,
    exposure: int,
    position: int,
    market_cap_yi: float,
) -> tuple[bool, str]:
    """应用通过规则，返回 (passed, reason)。"""
    # 核心一: 同源性 < 4 → 直接拦截（弱关联/平行线）
    # 注意: 同源性3="仅在字面上有交集，不同驱动力"→应拦截
    # 同源性4="有关联但非核心驱动"→最低通过线
    if homology < 4:
        return False, f"核心一拦截: 叙事-事件同源性={homology}/10，个股涨不涨不取决于我们分析的事件"

    # 核心二: 大市值(>500亿)需更高总分门槛
    # 注意: 弹性维度已综合评估市值+经营杠杆+流通盘，此处不再设四维底线
    if market_cap_yi > 500:
        if total < 28:
            return False, f"核心二拦截: 市值{market_cap_yi:.0f}亿>500亿但总分{total}/40<28，大市值需全方位契合"
        return True, f"通过(大市值{market_cap_yi:.0f}亿+总分{total}/40≥28)"

    # 核心二: 中小市值
    if total >= 20:
        return True, f"通过(总分{total}/40≥20)"
    else:
        return False, f"核心二拦截: 总分{total}/40<20，弹性/暴露度不足"


# ═══════════════════════════════════════
# Flash API Call
# ═══════════════════════════════════════

def _call_flash_pre_screen(
    system_prompt: str,
    user_message: str,
    api_key: str | None = None,
) -> dict:
    """调用 Flash 模型做预筛评分。"""
    key = api_key or DEEPSEEK_API_KEY

    try:
        resp = requests.post(
            DEEPSEEK_API,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            json={
                "model": FLASH_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": 4096,
                "temperature": 0,
                "stream": False,
            },
            timeout=60,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        print(
            f"  [PreScreen] model={FLASH_MODEL} "
            f"prompt={usage.get('prompt_tokens')} "
            f"completion={usage.get('completion_tokens')}",
            flush=True,
        )

        # 解析 JSON（容错 markdown 包裹）
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        return json.loads(content)

    except Exception as e:
        print(f"  [PreScreen] Flash 调用失败: {e}", flush=True)
        return {"_parse_error": str(e)[:200]}


# ═══════════════════════════════════════
# User Message Builder
# ═══════════════════════════════════════

def _get_core_financials(agent1_output: dict) -> dict:
    """提取核心财务数据——兼容多种数据格式。

    优先级:
      1. packages.core.fields (Agent-1 V6+ 标准格式)
      2. clean_financials (历史格式)
      3. 顶层直接字段 (兜底)

    字段名兼容: market_cap_yi 和 market_cap_billion 均被归一化为 market_cap_yi。
    """
    pkgs = agent1_output.get("packages", {}) if isinstance(agent1_output, dict) else {}
    core = pkgs.get("core", {}) if isinstance(pkgs, dict) else {}
    fields = core.get("fields", {}) if isinstance(core, dict) else {}

    cf = agent1_output.get("clean_financials", {}) if isinstance(agent1_output, dict) else {}

    # 合并: fields 优先, cf 填充缺失
    result = {}
    for src in (cf, fields):
        if not isinstance(src, dict):
            continue
        for k, v in src.items():
            if k not in result or result[k] in (None, 0, '', '?'):
                result[k] = v

    # 字段名归一化: market_cap_billion → market_cap_yi
    if "market_cap_yi" not in result or not result.get("market_cap_yi"):
        if result.get("market_cap_billion"):
            result["market_cap_yi"] = result["market_cap_billion"]

    # 兜底: 从顶层提取
    if not result:
        result = {
            k: agent1_output.get(k, 0)
            for k in ["market_cap_yi", "revenue_ttm_yi", "net_profit_ttm_yi",
                       "total_equity_yi", "total_assets_yi", "cash_yi",
                       "interest_bearing_debt_yi", "pe_ttm", "pb", "ps_ttm",
                       "roic_pct", "gross_margin_pct", "net_margin_pct"]
        }

    return result


def _build_pre_screen_user_message(
    event_data: dict,
    agent1_output: dict,
    stock_code: str,
) -> str:
    """构建预筛用户消息 — 显式分离"事件端"和"个股端"。

    核心设计: 不做隐式的数据混合。让 LLM 清楚看到:
      - 左侧: 投资地图框定的事件方向
      - 右侧: Agent-0 为该个股提取的投资主题
    然后问: 这两个是同一件事吗？
    """
    cf = _get_core_financials(agent1_output)
    stock_name = event_data.get("stock_name", cf.get("stock_name", ""))

    return f"""# 股票
{stock_code} {stock_name}
市值:{cf.get('market_cap_yi','?')}亿 | 营收:{cf.get('revenue_ttm_yi','?')}亿 | 净利:{cf.get('net_profit_ttm_yi','?')}亿
毛利率:{cf.get('gross_margin_pct','?')}% | ROIC:{cf.get('roic_pct','?')}% | PE:{cf.get('pe_ttm','?')}x PB:{cf.get('pb','?')}x

# ── 事件端: 投资地图框定的变革方向 ──
这是我们要分析的事件——它决定了"哪类公司"值得深估。

**原始事件触发词**:
{str(event_data.get('raw_event_text', ''))[:800]}

**事件产业链分析** (Agent-0 预研):
{str(event_data.get('industry_expert_research', ''))[:1200]}

**事件逆向风险**:
{str(event_data.get('adversarial_thinking', ''))[:600]}

# ── 个股端: Agent-0 为该标的提取的投资主题 ──
这是该个股当前的核心叙事——它决定了"这只股票因为什么涨"。

**个股投资主题**:
{str(event_data.get('investment_theme', ''))[:2000]}

**个股事件推演 (T+30/90/180)**:
{str(event_data.get('event_deduction', ''))[:1200]}

# ── 核心问题 ──
对比上面的「事件端」和「个股端」:
- 事件讲的是: ________ (什么产业变革？)
- 个股讲的是: ________ (什么驱动股价？)
- 这两个故事是同一个驱动力，还是两条平行线？

请按系统指令完成4维评分。特别警惕: 行业标签相同(如都涉及"军工"、"芯片"、"新能源")不等于驱动力同源。"""


# ═══════════════════════════════════════
# PreScreenGate
# ═══════════════════════════════════════

class PreScreenGate:
    """灵光预筛 — 估值管线前置检查关卡。"""

    def __init__(
        self,
        api_key: str | None = None,
        total_threshold_small: int = 20,
        total_threshold_large: int = 28,
        homology_hard_cut: int = 4,
        large_cap_threshold: float = 500.0,
    ):
        self.api_key = api_key
        self.total_threshold_small = total_threshold_small
        self.total_threshold_large = total_threshold_large
        self.homology_hard_cut = homology_hard_cut
        self.large_cap_threshold = large_cap_threshold

    def run(
        self,
        event_data: dict,
        agent1_output: dict,
        stock_code: str,
    ) -> PreScreenResult:
        """
        执行预筛判断。

        Returns:
            PreScreenResult (passed=True → 继续管线; passed=False → 拦截)

        失败策略: fail-open — Flash 调用失败时 passed=True，记录 _error。
        """
        t0 = time.time()

        # ── 构建用户消息 ──
        user_msg = _build_pre_screen_user_message(event_data, agent1_output, stock_code)

        # ── 调用 Flash ──
        raw = _call_flash_pre_screen(PRE_SCREEN_SYSTEM, user_msg, self.api_key)

        if "_parse_error" in raw:
            # 重试一次
            raw = _call_flash_pre_screen(PRE_SCREEN_SYSTEM, user_msg, self.api_key)

        latency = round(time.time() - t0, 2)

        if "_parse_error" in raw:
            print(f"  [PreScreen] fail-open: Flash 调用失败，放行", flush=True)
            return PreScreenResult(
                total_score=40, passed=True,
                cut_reason="",
                summary="Flash调用失败，fail-open放行",
                raw_response=str(raw),
                latency_s=latency,
                _error=raw.get("_parse_error", "unknown"),
            )

        # ── 提取分数 ──
        try:
            homology = int(raw.get("homology", {}).get("score", 5))
            exposure = int(raw.get("exposure", {}).get("score", 5))
            elasticity = int(raw.get("elasticity", {}).get("score", 5))
            position = int(raw.get("position", {}).get("score", 5))
            adj = int(raw.get("discretionary_adjustment", 0))
            adj = max(-3, min(3, adj))  # 限制在 ±3
            total = homology + exposure + elasticity + position + adj
            total = max(4, min(43, total))  # 物理边界
        except (ValueError, TypeError, KeyError) as e:
            print(f"  [PreScreen] 分数解析失败: {e}，fail-open 放行", flush=True)
            return PreScreenResult(
                total_score=40, passed=True,
                cut_reason="",
                summary="分数解析失败，fail-open放行",
                raw_response=str(raw),
                latency_s=latency,
                _error=f"parse_error: {e}",
            )

        # ── 应用通过规则 ──
        cf = _get_core_financials(agent1_output)
        mcap = float(cf.get("market_cap_yi", 50))
        passed, reason = _evaluate_rules(
            homology, total, elasticity, exposure, position, mcap,
        )

        # LLM 的 cut_recommendation 仅供参考，实际以代码规则为准
        llm_rec = raw.get("cut_recommendation", "")

        print(
            f"  [PreScreen] {'PASS' if passed else 'BLOCK'} "
            f"同源={homology} 暴露={exposure} 弹性={elasticity} 地位={position} "
            f"裁量={adj:+d} 总分={total}/40 市值={mcap:.0f}亿 | {reason[:80]}",
            flush=True,
        )

        return PreScreenResult(
            total_score=total,
            passed=passed,
            homology=homology,
            exposure=exposure,
            elasticity=elasticity,
            position=position,
            discretionary_adjustment=adj,
            cut_reason=reason,
            summary=raw.get("summary", ""),
            raw_response=json.dumps(raw, ensure_ascii=False),
            latency_s=latency,
        )
