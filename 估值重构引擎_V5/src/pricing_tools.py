"""
多锚定价工具 (Pricing Tools) — V6 Phase 2 量化计算引擎。

纯代码模块，为 Agent-2a 提供"当前价格隐含了什么期望"的定量锚。
每个工具返回统一格式: {method, applicable, implied_value, limitations, detail}。

LLM 在知道限制的前提下解读这些数值，不可盲信。

原则:
  - 所有公式是简化模型，假设和局限随结果一起输出
  - 适用性由代码判定（如 NOPAT≤0 → 反向DCF不适用）
  - 不替代 LLM 判断，只是给 LLM 一个"参考系"
"""

import math
from typing import Any


def reverse_dcf(nopat_yi: float, ev_yi: float, wacc_pct: float) -> dict:
    """
    反向 DCF: 从当前 EV 反解隐含永续增速 g。

    适用条件: NOPAT > 0, WACC > 0, EV > 0
    局限: 假设永续增速恒定、NOPAT 是可持续的基准利润。
          对亏损/微利/投入期公司不适用——NOPAT 当前值不是未来盈利能力的代理变量。
    """
    warnings = []
    if nopat_yi <= 0 or wacc_pct <= 0 or ev_yi <= 0:
        return {
            "method": "reverse_dcf",
            "applicable": False,
            "implied_value": None,
            "implied_metric": "隐含永续增速g(%)",
            "limitations": [
                "NOPAT≤0,反向DCF数学上无解",
                "亏损/微利企业不适合反向DCF——当前NOPAT不反映未来盈利能力",
            ],
            "detail": {"nopat_yi": nopat_yi, "ev_yi": ev_yi, "wacc_pct": wacc_pct},
        }

    wacc = wacc_pct / 100
    base_dcf = nopat_yi / wacc  # 零增长 DCF 值

    lo, hi = -0.05, wacc * 0.95
    implied_g = None
    for _ in range(30):
        mid = (lo + hi) / 2
        spread = wacc - mid
        if spread < wacc * 0.02:
            spread = wacc * 0.02
        tv = nopat_yi * (1 + mid) / spread
        if abs(tv - ev_yi) / ev_yi < 0.001:
            implied_g = mid
            break
        if tv > ev_yi:
            hi = mid
        else:
            lo = mid
    if implied_g is None:
        implied_g = (lo + hi) / 2

    implied_g_pct = round(implied_g * 100, 1)
    premium_pct = round((ev_yi / base_dcf - 1) * 100) if base_dcf > 0 else 0

    limitations = [
        "假设永续增速恒定，实际公司有生命周期",
        f"NOPAT={nopat_yi:.2f}亿为TTM快照，不一定是可持续利润",
    ]
    if implied_g and implied_g > wacc * 0.8:
        warnings.append(f"隐含g({implied_g_pct}%)逼近WACC({wacc_pct}%)的80%——永续增长假设高度敏感")
        limitations.append("隐含g逼近WACC上限，微小参数变化导致大幅估值波动")

    return {
        "method": "reverse_dcf",
        "applicable": True,
        "implied_value": implied_g_pct,
        "implied_metric": "隐含永续增速g(%)",
        "limitations": limitations,
        "detail": {
            "nopat_yi": round(nopat_yi, 2),
            "ev_yi": round(ev_yi, 1),
            "wacc_pct": wacc_pct,
            "base_dcf_yi": round(base_dcf, 1),
            "market_premium_pct": min(premium_pct, 999),
            "g_wacc_ratio_pct": round(implied_g_pct / wacc_pct * 100, 1) if wacc_pct > 0 else 0,
            "warnings": warnings,
        },
    }


def implied_revenue_cagr(
    market_cap_yi: float,
    revenue_ttm_yi: float,
    current_ps: float,
    wacc_pct: float = 10.0,
    terminal_ps: float | None = None,
) -> dict:
    """
    收入锚隐含 CAGR: 从当前 PS 反解 3 年收入复合增速。

    公式: market_cap = revenue × (1 + cagr)³ × terminal_PS
    → cagr = (market_cap / (revenue × terminal_PS))^(1/3) - 1

    适用条件: revenue > 0, PS > 0
    局限: terminal_PS 是主观假设——3 年后市场会给多少倍 PS？
          对高 PS 公司(>20x)，terminal_PS 的选择对结果影响极大。
    """
    if revenue_ttm_yi <= 0 or current_ps <= 0 or market_cap_yi <= 0:
        return {
            "method": "implied_revenue_cagr",
            "applicable": False,
            "implied_value": None,
            "implied_metric": "隐含3年收入CAGR(%)",
            "limitations": ["营收或PS数据不可用"],
            "detail": {},
        }

    # terminal_PS 默认: 增长公司 8x, 成熟公司 5x, 按当前 PS 调节
    if terminal_ps is None:
        if current_ps > 20:
            terminal_ps = 8.0  # 极高 PS → 3 年后仍溢价
        elif current_ps > 10:
            terminal_ps = 5.0
        elif current_ps > 5:
            terminal_ps = 3.0
        else:
            terminal_ps = 2.0

    terminal_mcap = revenue_ttm_yi * terminal_ps
    if terminal_mcap <= 0:
        return {
            "method": "implied_revenue_cagr",
            "applicable": False,
            "implied_value": None,
            "implied_metric": "隐含3年收入CAGR(%)",
            "limitations": ["terminal_PS计算异常"],
            "detail": {},
        }

    ratio = market_cap_yi / terminal_mcap
    cagr = (ratio ** (1 / 3) - 1) * 100 if ratio > 0 else 0

    return {
        "method": "implied_revenue_cagr",
        "applicable": True,
        "implied_value": round(cagr, 1),
        "implied_metric": "隐含3年收入CAGR(%)",
        "limitations": [
            f"terminal_PS={terminal_ps}x 是主观假设——3年后的市场情绪不可知",
            "CAGR假设均匀增长，实际收入路径可能是非线性的",
            f"当前PS={current_ps:.1f}x——PS越高，terminal_PS的选择越敏感",
        ],
        "detail": {
            "market_cap_yi": round(market_cap_yi, 1),
            "revenue_ttm_yi": round(revenue_ttm_yi, 1),
            "current_ps": round(current_ps, 1),
            "terminal_ps_assumed": terminal_ps,
            "terminal_mcap_yi": round(terminal_mcap, 1),
            "wacc_pct": wacc_pct,
        },
    }


def implied_roe_improvement(
    market_cap_yi: float,
    equity_yi: float,
    current_pb: float,
    current_roe_pct: float,
    required_return_pct: float = 10.0,
) -> dict:
    """
    资产锚隐含 ROE 改善: 从当前 PB 反解市场预期的 ROE 改善幅度。

    简化公式: PB ≈ ROE / required_return（零增长 PB-ROE 模型）
    → implied_ROE = PB × required_return
    → ROE_gap = implied_ROE - current_ROE

    适用条件: equity > 0, PB > 0
    局限: 这是极简 PB-ROE 模型——忽略了增长、杠杆、资产质量差异。
          仅适合作为"方向感"参考，不作为精确目标。
    """
    if equity_yi <= 0 or current_pb <= 0:
        return {
            "method": "implied_roe_improvement",
            "applicable": False,
            "implied_value": None,
            "implied_metric": "隐含ROE改善幅度(ppt)",
            "limitations": ["净资产或PB数据不可用"],
            "detail": {},
        }

    implied_roe = current_pb * required_return_pct
    gap = implied_roe - current_roe_pct

    return {
        "method": "implied_roe_improvement",
        "applicable": True,
        "implied_value": round(gap, 1),
        "implied_metric": "隐含ROE改善幅度(ppt)",
        "limitations": [
            "使用零增长PB-ROE模型，忽略了增长和杠杆的影响",
            f"required_return={required_return_pct}%是假设值，实际要求回报因公司而异",
            "仅适合重资产/金融类公司做方向参考",
        ],
        "detail": {
            "market_cap_yi": round(market_cap_yi, 1),
            "equity_yi": round(equity_yi, 1),
            "current_pb": round(current_pb, 1),
            "current_roe_pct": round(current_roe_pct, 1),
            "implied_roe_pct": round(implied_roe, 1),
            "required_return_pct": required_return_pct,
        },
    }


def compute_pricing_anchor(
    anchor: str,
    core_fields: dict,
    wacc_params: dict | None = None,
) -> dict:
    """
    一站式定价锚计算：根据 Phase 1 识别的估值锚，选择对应的量化工具。

    anchor: "earnings" | "revenue" | "asset" | "pipeline" | "sotp"
    返回: 对应工具的输出 dict
    """
    wacc = wacc_params or {}
    wacc_pct = wacc.get("wacc_pct", 10.0)

    mcap = core_fields.get("market_cap_yi", 0)
    nopat = core_fields.get("nopat_yi", 0)
    ev = mcap + core_fields.get("interest_bearing_debt_yi", 0) - core_fields.get("cash_yi", 0)
    revenue = core_fields.get("revenue_ttm_yi", 0)
    ps = core_fields.get("ps_ttm", 0)
    equity = core_fields.get("total_equity_yi", 0)
    pb = core_fields.get("pb", 0)
    roe = core_fields.get("roe_ttm_pct", 0)

    if anchor == "earnings":
        return reverse_dcf(nopat, ev, wacc_pct)
    elif anchor == "revenue":
        return implied_revenue_cagr(mcap, revenue, ps, wacc_pct)
    elif anchor == "asset":
        return implied_roe_improvement(mcap, equity, pb, roe, wacc_pct)
    else:
        return {
            "method": "qualitative",
            "applicable": True,
            "implied_value": None,
            "implied_metric": "无定量工具",
            "limitations": [
                f"估值锚={anchor}无对应的反向推算工具",
                "Phase 2 计价判断依赖定性分析",
            ],
            "detail": {},
        }
