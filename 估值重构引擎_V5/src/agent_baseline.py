"""
Agent-Baseline 投资地图绘制 — V7.0

在 Agent-0（预研语料）/ Agent-1（财务数据）/ 火山搜索完成后，
在 Agent-2a（叙事诊断）之前运行。

职责:
  将零散的预研语料、财务数据、行业信息、火山搜索结果，
  合成为一份结构化的"投资地图"——事件冲击前的企业全貌。

设计原则:
  - 维度清晰的自然语言 + 量化锚点（非纯 JSON，非纯散文）
  - 下游 Agent 依赖此报告理解"公司是谁"，不再需要翻阅原始数据
  - 明确区分事实（财报数字）和推断（行业分析结论）
  - 量化锚点附带数据来源和置信度，供下游交叉验证

输入:
  - Agent-0: industry_expert_research, investment_theme, knowledge_supplement,
             adversarial_thinking, event_deduction, preliminary_reasoning
  - Agent-1: core financial fields, product mix, forward-looking signals
  - 火山搜索: segment data, comparable companies, market expectations

输出:
  一份六维投资地图报告（Markdown），约 2000-4000 tokens
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests
from env_config import DEEPSEEK_API_KEY

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
BASELINE_MODEL = "deepseek-v4-pro"  # 需要综合推理能力，不用 Flash

# ═══════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════

BASELINE_SYSTEM_PROMPT = """# 你是投资地图绘制师

你的任务不是估值，不是判断买卖。你的唯一任务是**绘制一幅公司在事件冲击前的完整画像**。

## 核心哲学

预研语料、财务数据、行业信息、可比公司——这些共同构成一幅"投资地图"，描述:
- 这家公司做什么、怎么赚钱
- 它在产业中处于什么位置
- 它的财务基线是什么
- 市场在事件前如何理解它的投资逻辑
- 它的脆弱点在哪里（什么会打破当前叙事）
- 它在未来 6-12 个月原定要经历哪些里程碑

**事件是变量，冲击这幅地图。** 你的工作不是分析事件——那是下游 Agent 的职责。
你的工作是让下游 Agent 拿到的地图足够清晰、准确、完整，从而能精准判断事件冲击的幅度和方向。

## 素材映射指引

你的输入中包含不同类型的素材。以下是每种素材应该被吸收到哪个维度：

| 输入素材 | 主要映射维度 | 提取要点 |
|---------|------------|---------|
| 财务硬数据 + 产品结构 | 一(收入结构)、二(财务基线) | 数字直接填入，不做二次加工 |
| 行业全貌 (industry_expert_research) | 三(产业位置) | 产业链位置、竞争格局、护城河、利润传导 |
| 投资主题 (investment_theme) | 五(投资主线) | 核心叙事、估值锚、关键假设 |
| 背景知识 (knowledge_supplement) | 六(量化锚点)、一(收入结构) | 产能/价格/客户/市占率等硬数字，填入锚点表 |
| 发展推演 (event_deduction) | 四(增长轨迹) | T+30/90/180 的预期路径和关键分叉点，提取为"原定里程碑时间线" |
| 催化节点 (future) | 四(增长轨迹) | P0/P1/P2 节点的证实/证伪信号和时间窗口 |
| 逆向风险 (adversarial_thinking) | 五(投资主线) | 核心假设脆弱性、利益相关方博弈、反身性触发条件 |
| 事件研判 (preliminary_reasoning) | 跨维度参考 | 只提取对公司的定性判断(生命周期阶段/利润链条清晰度)，不提取事件评分 |
| 火山联网搜索 | 六(量化锚点)、三(产业位置) | 可比公司估值倍数、券商预测数字 |

## 输出要求

输出一份六维投资地图，使用 Markdown 格式。

**六维是覆盖清单，不是等权重要求。用 80% 的篇幅展开对公司估值有决定性影响的 2-3 个维度，其他维度简述即可。各维度的详略和侧重由你根据公司实际情况自主决定。**

### 一、公司身份与收入结构

- 用 3-5 句话描述公司的核心业务和商业模式
- 用表格列出各产品/分部的收入、占比、毛利率、同比增速
- 标注哪些是成熟业务、哪些是成长业务、哪些是亏损/拖累业务
- 地域结构（境内/境外收入占比）如有数据则列出

### 二、财务基线

回答: 这家公司的财务质地如何？

- 规模: 营收、利润、市值、总资产
- 盈利质量: 毛利率、净利率、ROIC、ROE，各自的历史分位含义
- 成本结构: 固定 vs 变动的定性判断，经营杠杆方向（固定成本占比高→收入小幅改善→利润大幅跃升）
- 现金流: OCF/NI 比值（利润含金量），FCF 状态，CAPEX 强度
- 资本结构: 有息负债、净现金、资产负债率
- **关键**: 标注 ROIC 与 WACC 的关系——公司在创造价值还是销毁价值？

### 三、产业位置

回答: 这家公司在产业链中处于什么位置？竞争格局如何？

- 产业链位置: 上游-中游-下游，利润池分布
- 竞争格局: 主要竞争对手及其差异化定位，公司的市场份额
- 护城河: 成本优势/技术壁垒/客户粘性/牌照壁垒的评级和依据
- 客户/供应商集中度: 是否有单点依赖风险

### 四、增长轨迹与原定里程碑

回答: 这家公司过去和未来的增长引擎是什么？未来 6-12 个月原定要经历哪些关键节点？

- 历史增速: 近 4 个季度收入 YoY 趋势（加速/平稳/减速）
- 产能与利用率: 现有产能、产能利用率、在建产能、扩产时间表
- 增长驱动力: 量增？价升？新产品？新市场？
- 前瞻信号: 合同负债是否跳升？存货是否异常？CAPEX/折旧比处于什么阶段？
- 业绩预告方向（如有）
- **原定里程碑时间线**: 从"发展推演"和"催化节点"中提取关键节点，按时间排列。每项标注: 时间窗口、事件、证实/证伪信号、当前状态（已发生/待验证/已证伪）。这是事件冲击的"靶子"——事件可能加速、推迟或取消这些节点。

### 五、投资主线与脆弱点

回答: 市场在事件前如何理解这家公司的投资逻辑？这个逻辑的脆弱点在哪里？

- 投资主题: 市场为什么买这家公司？核心叙事是什么？
- 估值锚: 市场主要用什么指标给它定价（PE/PS/PB）？当前倍数处于历史什么位置？
- 关键假设: 当前估值隐含了什么预期（增速、利润率、市占率）？
- **脆弱点分析**: 从"逆向风险"中提取。逐条列出核心假设及其脆弱度（高/中/低），包括:
  - 假设内容——什么前提成立故事才能继续
  - 反面证据——什么情况下这个前提会崩
  - 触发条件——观察到什么信号说明脆弱点正在被激活
  - 利益相关方动态——谁会做什么来打断叙事
  - 反身性风险——股价本身的涨跌会不会改变基本面

### 六、量化锚点

回答: 定义这家公司当前状态的硬数字——这些是事件冲击的起点。

从"背景知识"和"财务硬数据"中提取。用表格列出:
| 锚点 | 当前值 | 来源 | 置信度 |

只列对估值有实质影响的锚点。典型锚点类型:
- 产能类: 现有产能、利用率、在建产能、扩产时间
- 价格类: 产品均价、价格趋势、定价机制
- 市占率类: 国内/全球市占率、客户渗透率
- 壁垒类: 认证周期、客户切换成本、技术代差年限
- 财务类: 毛利率、净利率、ROIC、CAPEX/折旧比

每个锚点必须有明确来源。不确定时标注置信度"低"或"估算"。不要编造数字。

## 思维禁区

- 不要做估值判断——不要写"合理"、"低估"、"高估"
- 不要分析事件——事件是下游 Agent 的工作，你只描述事件前的状态
- 不要模糊——有数字就用数字，没有数字就标注"未披露"
- 不要编造——所有数字必须有来源。从输入材料中提取
- 不要省略负面信息——亏损业务、ROIC<WACC、业绩预减、脆弱点都是地图的重要特征
- 不要做事件研判——preliminary_reasoning 中的评分和等级是给下游 Agent 用的，你只从中提取对公司的定性描述

## 输出格式

直接输出 Markdown，不要用代码块包裹。以 `# 投资地图: {公司名} ({股票代码})` 开头。"""


# ═══════════════════════════════════════
# User Message Builder
# ═══════════════════════════════════════

def _get_core_fields(data_package: dict) -> dict:
    """从 Agent-1 输出中提取核心财务字段。"""
    pkgs = data_package.get("packages", {}) if isinstance(data_package, dict) else {}
    core = pkgs.get("core", {}) if isinstance(pkgs, dict) else {}
    fields = core.get("fields", {}) if isinstance(core, dict) else {}
    if not fields:
        fields = data_package.get("clean_financials", {}) if isinstance(data_package, dict) else {}
    return fields


def _build_product_table(data_package: dict) -> str:
    """从 forward_looking 中提取产品结构表格。"""
    core = _get_core_fields(data_package)
    fw = core.get("_forward_looking", {}) or {}
    ea = ((fw.get("categories", {}) or {}).get("earnings_elasticity", {}) or {})
    mix = ea.get("product_mix", []) or []
    if not mix:
        return "（无分产品数据）"

    lines = ["| 产品 | 收入(亿) | 占比 | 毛利率 | 同比增速 |",
             "|------|---------|------|--------|---------|"]
    for p in mix:
        rev = p.get("revenue", 0)
        share = p.get("revenue_share_pct", 0)
        gm = p.get("gross_margin_pct")
        gm_str = f"{gm:.1f}%" if gm is not None else "?"
        yoy = p.get("revenue_yoy_pct")
        yoy_str = f"{yoy:+.1f}%" if yoy is not None else "?"
        lines.append(f"| {p['name']} | {rev:.2f} | {share:.1f}% | {gm_str} | {yoy_str} |")

    # 数据质量
    gm_src = ea.get("gm_source", "?")
    gm_cov = ea.get("gm_coverage_pct", 100)
    data_vintage = ea.get("data_vintage", "")
    lines.append(f"\n数据时效: {data_vintage} | 毛利率来源: {gm_src} (覆盖率{gm_cov}%)")

    return "\n".join(lines)


def _build_recent_growth(core: dict) -> str:
    """提取近 4 季度收入趋势。"""
    fw = core.get("_forward_looking", {}) or {}
    mg = (fw.get("categories", {}) or {}).get("management_guidance", {}) or {}
    et = mg.get("earnings_trend", {}) or {}
    recent = et.get("recent_4q", [])
    if not recent:
        return "（无季度趋势数据）"

    trend = et.get("trend_direction", "?")
    lines = [f"近4季度趋势: **{trend}**", "| 季度 | 收入YoY | ROIC | 毛利率 |",
             "|------|--------|------|--------|"]
    for q in recent[:4]:
        period = str(q.get("period", ""))
        yoy = q.get("revenue_yoy", q.get("revenue_q_yoy", "?"))
        yoy_str = f"{yoy:+.1f}%" if isinstance(yoy, (int, float)) else str(yoy)
        roic = q.get("roic", "?")
        roic_str = f"{roic:.1f}%" if isinstance(roic, (int, float)) else str(roic)
        gm = q.get("gm", "?")
        gm_str = f"{gm:.1f}%" if isinstance(gm, (int, float)) else str(gm)
        lines.append(f"| {period} | {yoy_str} | {roic_str} | {gm_str} |")

    return "\n".join(lines)


def _build_forecast_section(core: dict) -> str:
    """提取业绩预告/快报/股东趋势。"""
    fw = core.get("_forward_looking", {}) or {}
    mg = (fw.get("categories", {}) or {}).get("management_guidance", {}) or {}

    parts = []
    forecast = mg.get("forecast", {}) or {}
    if forecast.get("flag"):
        parts.append(f"业绩预告: **{forecast.get('type','?')}** ({forecast.get('np_change_range','?')})")
        if forecast.get("interpretation"):
            parts.append(f"  {forecast['interpretation']}")

    shareholder = mg.get("shareholder", {}) or {}
    if shareholder.get("flag"):
        parts.append(f"股东人数: **{shareholder.get('trend','?')}**")
        if shareholder.get("interpretation"):
            parts.append(f"  {shareholder['interpretation']}")

    return "\n".join(parts) if parts else "（无业绩预告/股东异常信号）"


def _build_forward_signals(core: dict) -> str:
    """提取前瞻信号摘要。"""
    fw = core.get("_forward_looking", {}) or {}
    cats = fw.get("categories", {}) or {}

    signals = []

    # 合同负债
    cl = (cats.get("demand_reality", {}) or {}).get("contract_liab", {}) or {}
    if cl:
        anomaly = cl.get("anomaly", {}) or {}
        if anomaly.get("level") in ("elevated", "significant"):
            signals.append(f"合同负债: {cl.get('value','?')}亿, 偏离{anomaly.get('sigma','?')}σ ↑")

    # 应收账款
    ar = (cats.get("demand_reality", {}) or {}).get("accounts_receivable", {}) or {}
    if ar:
        anomaly = ar.get("anomaly", {}) or {}
        if anomaly.get("level") in ("elevated", "significant"):
            signals.append(f"应收/营收比: {ar.get('ar_to_rev_ratio','?')}, 偏离{anomaly.get('sigma','?')}σ ↑")

    # 存货
    inv = (cats.get("supply_readiness", {}) or {}).get("inventory", {}) or {}
    if inv:
        anomaly = inv.get("anomaly", {}) or {}
        if anomaly.get("level") in ("elevated", "significant"):
            signals.append(f"存货: {inv.get('value','?')}亿, 偏离{anomaly.get('sigma','?')}σ ↑")

    # CAPEX
    cdr = (cats.get("supply_readiness", {}) or {}).get("capex_depr_ratio", {}) or {}
    if cdr:
        signals.append(f"CAPEX/折旧: {cdr.get('value','?')}x — {cdr.get('supply_label','?')}")

    # OCF/NI
    ocf = (cats.get("cashflow_quality", {}) or {}).get("ocf_to_ni", {}) or {}
    if ocf:
        signals.append(f"OCF/净利润: {ocf.get('value','?')}x — {ocf.get('quality_label','?')}")

    return "\n".join(f"- {s}" for s in signals) if signals else "（无异常前瞻信号）"


def build_baseline_user_message(
    stock_code: str,
    stock_name: str,
    agent0_output: dict,
    agent1_output: dict,
    volc_data: dict | None = None,
) -> str:
    """构建 baseline agent 的用户消息。

    将 Agent-0 的预研语料和 Agent-1 的财务数据整合为一组输入，
    让 LLM 合成投资地图。
    """
    core = _get_core_fields(agent1_output)

    # ── 财务核心数据 ──
    mcap = core.get("market_cap_yi", 0)
    rev = core.get("revenue_ttm_yi", 0)
    np_val = core.get("net_profit_ttm_yi", 0)
    equity = core.get("total_equity_yi", 0)
    cash_val = core.get("cash_yi", 0)
    debt_val = core.get("interest_bearing_debt_yi", 0)
    gm = core.get("gross_margin_pct", 0)
    nm = core.get("net_margin_pct", 0)
    roic = core.get("roic_pct", 0)
    roe = core.get("roe_ttm_pct", 0)
    pe = core.get("pe_ttm", 0)
    pb = core.get("pb", 0)
    ps = core.get("ps_ttm", 0)
    ocf = core.get("ocf_ttm_yi", 0)
    capex = core.get("capex_ttm_yi", 0)
    ebitda = core.get("ebitda_ttm_yi", 0)
    wacc = core.get("_wacc_decimal", 0.10) * 100
    net_cash = cash_val - debt_val
    fcf = ocf - capex
    total_assets = core.get("total_assets_yi", 0)
    total_liab = core.get("total_liabilities_yi", 0)
    asset_liab_ratio = total_liab / max(total_assets, 1) * 100

    msg = f"""# 请为 {stock_name}({stock_code}) 绘制投资地图

## 财务硬数据 (Agent-1 从财报提取)

| 指标 | 数值 | 指标 | 数值 |
|------|------|------|------|
| 市值 | {mcap:.0f}亿 | PE(TTM) | {pe:.1f}x |
| TTM营收 | {rev:.1f}亿 | PB | {pb:.1f}x |
| TTM净利润 | {np_val:.1f}亿 | PS(TTM) | {ps:.1f}x |
| EBITDA | {ebitda:.1f}亿 | EBITDA率 | {ebitda/max(rev,1)*100:.1f}% |
| ROIC | {roic:.1f}% | WACC | {wacc:.1f}% |
| ROE | {roe:.1f}% | 毛利率 | {gm:.1f}% |
| 净利率 | {nm:.1f}% | OCF | {ocf:.1f}亿 |
| 净资产 | {equity:.0f}亿 | 总资产 | {total_assets:.0f}亿 |
| 现金 | {cash_val:.1f}亿 | 有息负债 | {debt_val:.1f}亿 |
| 净现金 | {net_cash:.1f}亿 | 资产负债率 | {asset_liab_ratio:.1f}% |
| CAPEX(TTM) | {capex:.1f}亿 | FCF | {fcf:.1f}亿 |

ROIC vs WACC: {roic:.1f}% vs {wacc:.1f}% → {'创造价值' if roic > wacc else '销毁价值'}

### 产品结构（来自年报分产品数据）
{_build_product_table(agent1_output)}

### 近4季度收入趋势
{_build_recent_growth(core)}

### 业绩预告与股东信号
{_build_forecast_section(core)}

### 前瞻信号（资产负债表先行指标）
{_build_forward_signals(core)}

## 预研语料 (Agent-0 从事件/行业/公司研究中提取)

### 行业全貌（产业链竞争格局）
{agent0_output.get('industry_expert_research','（无）')}

### 投资主题（市场如何理解这家公司）
{agent0_output.get('investment_theme','（无）')}

### 发展推演（T+30/90/180 事件演进路径，含关键分叉点和转移概率）
{agent0_output.get('event_deduction','（无）')}

### 催化节点（未来关键验证节点，含证实/证伪信号和时间窗口）
{agent0_output.get('future','（无）')}

### 背景知识（补充数据：产能/价格/客户/供需）
{agent0_output.get('knowledge_supplement','（无）')}

### 逆向风险
{agent0_output.get('adversarial_thinking','（无）')}

### 事件研判（只提取对公司的定性描述——生命周期阶段、利润链条是否清晰、竞争格局判断。不要提取事件评分和等级）
{agent0_output.get('preliminary_reasoning','（无）')[:800]}

## 火山联网搜索（券商研报/可比公司/市场预期）

{_build_volc_section(volc_data)}

请按系统指令输出六维投资地图。注意：你描述的是事件冲击前的企业状态，不要分析事件的影响。
"""

    return msg


def _build_volc_section(volc_data: dict | None) -> str:
    """格式化火山搜索结果为输入。"""
    if not volc_data:
        return "（无火山搜索数据）"
    text = volc_data.get("volc_text", "")
    if not text:
        return "（火山搜索无结果）"
    return text[:3000]  # 截断过长内容


# ═══════════════════════════════════════
# Agent-Baseline 主类
# ═══════════════════════════════════════

class BaselineMapDrawer:
    """投资地图绘制 Agent。

    在 Agent-0/Agent-1/火山搜索完成后运行，
    输出结构化的六维投资地图报告。
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or DEEPSEEK_API_KEY

    def run(
        self,
        stock_code: str,
        stock_name: str,
        agent0_output: dict,
        agent1_output: dict,
        volc_data: dict | None = None,
    ) -> dict:
        """
        执行投资地图绘制。

        Returns:
            {
                "baseline_report": str,   # Markdown 格式的六维投资地图
                "model": str,             # 使用的模型
                "latency_s": float,       # 耗时
                "usage": dict | None,     # token 用量
            }
        """
        t0 = time.time()

        user_msg = build_baseline_user_message(
            stock_code, stock_name,
            agent0_output, agent1_output, volc_data,
        )

        try:
            resp = requests.post(
                DEEPSEEK_API,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={
                    "model": BASELINE_MODEL,
                    "messages": [
                        {"role": "system", "content": BASELINE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 8192,
                    "temperature": 0.1,
                    "stream": False,
                    "thinking": {"type": "enabled"},
                    "reasoning_effort": "max",
                },
                timeout=300,
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            latency = round(time.time() - t0, 2)
            print(
                f"  [Baseline] model={BASELINE_MODEL} "
                f"prompt={usage.get('prompt_tokens')} "
                f"completion={usage.get('completion_tokens')} "
                f"latency={latency}s",
                flush=True,
            )

            return {
                "baseline_report": content.strip(),
                "model": BASELINE_MODEL,
                "latency_s": latency,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                },
            }

        except Exception as e:
            print(f"  [Baseline] 调用失败: {e}", flush=True)
            return {
                "baseline_report": f"（投资地图生成失败: {e}）",
                "model": BASELINE_MODEL,
                "latency_s": round(time.time() - t0, 2),
                "usage": None,
                "_error": str(e)[:200],
            }


# ═══════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════

def draw_baseline_map(
    stock_code: str,
    agent0_output: dict,
    agent1_output: dict,
    volc_data: dict | None = None,
    api_key: str | None = None,
) -> dict:
    """便捷函数: 一键绘制投资地图。"""
    stock_name = (
        agent0_output.get("stock_name")
        or agent1_output.get("stock_name")
        or stock_code
    )
    drawer = BaselineMapDrawer(api_key=api_key)
    return drawer.run(stock_code, stock_name, agent0_output, agent1_output, volc_data)
