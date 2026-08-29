"""N0.4: 市值门禁 — Tushare 实时市值筛查

在预研管线开头（N0 代码验证后、N0.5 公司前置认知前）执行。
市值 > 500 亿的直接跳过，写入 Coze 天机卷 error_log 标记"大市值不做考虑"。

目的: 避免百济神州等大市值标的浪费全管线几百次 LLM token，
      市值 > 500 亿时即使用事件驱动的 TAM 扩张也很难有 5-10 倍上行空间。

用法: 直接作为模块在 pipeline.py 中 import 调用，无需额外配置。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tushare_fetcher import TushareFetcher

GATE_MV_YI = 500  # 市值门禁阈值（亿元）
GATE_MV_YI_WARN = 300  # 警告阈值，超过此值记录但放行


def check_market_cap_gate(verified_code: str, verified_name: str, verbose: bool = True) -> dict:
    """查询最新市值，判断是否超过门禁。

    Args:
        verified_code: 6位A股代码（已验证有效）
        verified_name: 股票名称
        verbose: 是否打印

    Returns:
        {
            "skip": bool,                # True = 应该跳过
            "reason": str,               # skip 原因，写入 error_log
            "total_mv_yi": float | None,  # 市值（亿元），查询失败时为 None
        }
    """
    tf = TushareFetcher()
    if not tf.available:
        if verbose:
            print(f"[N0.4] [PASS] Tushare 不可用，市值门禁放行")
        return {"skip": False, "reason": "", "total_mv_yi": None}

    try:
        data = tf.fetch_daily_basic(verified_code)
    except Exception:
        if verbose:
            print(f"[N0.4] [PASS] Tushare 查询异常，市值门禁放行")
        return {"skip": False, "reason": "", "total_mv_yi": None}

    if data is None or data.get("total_mv") is None:
        if verbose:
            print(f"[N0.4] [PASS] Tushare 无市值数据，市值门禁放行")
        return {"skip": False, "reason": "", "total_mv_yi": None}

    # Tushare daily_basic 的 total_mv 单位是万元
    total_mv_wan = float(data["total_mv"])
    total_mv_yi = total_mv_wan / 10000  # 转换为亿元

    if verbose:
        print(f"[N0.4] {verified_name}({verified_code}) 市值={total_mv_yi:.0f}亿 | 门禁={GATE_MV_YI}亿")

    if total_mv_yi > GATE_MV_YI:
        reason = f"市值门禁: {total_mv_yi:.0f}亿 > {GATE_MV_YI}亿，大市值不做考虑"
        if verbose:
            print(f"[N0.4] [SKIP] {reason}")
        return {"skip": True, "reason": reason, "total_mv_yi": total_mv_yi}

    if total_mv_yi > GATE_MV_YI_WARN:
        if verbose:
            print(f"[N0.4] [WARN] 市值 {total_mv_yi:.0f}亿 > {GATE_MV_YI_WARN}亿，放行但需关注安全边际")

    return {"skip": False, "reason": "", "total_mv_yi": total_mv_yi}
