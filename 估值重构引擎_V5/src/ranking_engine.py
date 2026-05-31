"""
赔率排序器 — V5

在批处理完成后对 N 只已分析股票进行跨股比较。
输出: reports/ranking/ranking_YYYY-MM-DD.json
"""

import json
from datetime import datetime
from pathlib import Path

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "reports" / "ranking"


def compute_ranking(results: list[dict], output_dir: str | None = None) -> dict:
    """
    对管线结果列表进行赔率排序。

    results: [{"agent0":..., "agent1":..., "agent2":..., "agent3":..., "status":"done"}, ...]

    返回 ranking dict。
    """
    out = Path(output_dir) if output_dir else _OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    stocks = []
    for r in results:
        if r.get("status") != "done":
            continue
        a3 = r.get("agent3", {})
        a1 = r.get("agent1", {})
        a0 = r.get("agent0", {})

        vs = a3.get("valuation_summary", {})
        ta = a3.get("trade_annotation", {})
        conf = a3.get("confidence", {})
        gap = a3.get("expectation_gap", {})
        sanity = a1.get("market_sanity", {})

        prob_upside = vs.get("probability_weighted_upside_pct", 0)
        asym = vs.get("asymmetry_ratio", 0)
        confidence = conf.get("overall_score", 5)
        tier = ta.get("tier", "")
        premium = sanity.get("market_premium_pct", 50)

        # Tier 分类
        if "规避" in tier:
            stock_tier = 0
        elif prob_upside > 30 and asym > 3:
            stock_tier = 1
        elif prob_upside > 15 and asym > 1.5:
            stock_tier = 2
        elif prob_upside > 0:
            stock_tier = 3
        else:
            stock_tier = 0

        # 综合得分（Tier 内排序用）
        composite = (
            _norm(prob_upside, 0, 200) * 0.35 +
            _norm(asym, 0, 10) * 0.25 +
            _norm(confidence, 0, 10) * 0.20 +
            _norm(100 - premium, 0, 100) * 0.20
        )

        stocks.append({
            "stock_code": a0.get("stock_code") or a3.get("report_meta", {}).get("stock_code", ""),
            "stock_name": a0.get("stock_name") or a3.get("report_meta", {}).get("stock_name", ""),
            "tier": stock_tier,
            "tier_label": {0: "规避", 1: "高赔率", 2: "中赔率", 3: "低赔率"}[stock_tier],
            "composite_score": round(composite, 3),
            "prob_weighted_upside_pct": prob_upside,
            "asymmetry_ratio": asym,
            "confidence_score": confidence,
            "trade_tier": tier,
            "market_premium_pct": premium,
        })

    stocks.sort(key=lambda x: (-x["tier"], -x["composite_score"]))

    ranking = {
        "generated_at": datetime.now().isoformat(),
        "total_analyzed": len(results),
        "total_ranked": len(stocks),
        "tier_summary": {
            "tier1_高赔率": sum(1 for s in stocks if s["tier"] == 1),
            "tier2_中赔率": sum(1 for s in stocks if s["tier"] == 2),
            "tier3_低赔率": sum(1 for s in stocks if s["tier"] == 3),
            "tier0_规避": sum(1 for s in stocks if s["tier"] == 0),
        },
        "ranked_stocks": stocks,
    }

    date_str = datetime.now().strftime("%Y-%m-%d")
    path = out / f"ranking_{date_str}.json"
    path.write_text(json.dumps(ranking, ensure_ascii=False, indent=2), encoding="utf-8")

    return ranking


def _norm(value: float, lo: float, hi: float) -> float:
    """归一化到 [0, 1]，超出范围钳位。"""
    if hi == lo: return 0.5
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))
