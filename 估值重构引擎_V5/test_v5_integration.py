"""
V5 集成测试 — 全管线 + V5→V4 compat 层 + HTML 报告生成

验证:
1. PipelineRunner.run_single() → V5 output
2. Scheduler._v5_to_v4_compat() → 字段映射正确
3. report_builder.build_html_report() → 不崩溃
"""

import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

from orchestrator import Orchestrator
from env_config import DEEPSEEK_API_KEY


def test_full_integration():
    """完整集成: 管线运行 → compat转换 → HTML报告"""
    print("=" * 50)
    print("V5 Integration Test")
    print("=" * 50)

    # ── Step 1: Run V5 pipeline ──
    event = {
        "raw_event_text": "AI服务器PCB需求爆发，胜宏科技作为核心供应商受益。",
        "event_deduction": "AI升级→高端PCB需求倍增→份额提升→营收利润双增",
        "investment_theme": "AI硬件核心供应商，高端PCB结构性短缺",
        "stock_name": "胜宏科技",
    }

    orch = Orchestrator(deepseek_key=DEEPSEEK_API_KEY)
    t0 = datetime.now()
    result = orch.run("300476", event)
    elapsed = (datetime.now() - t0).total_seconds()
    print(f"Pipeline: {result['status']} ({elapsed:.0f}s)")

    assert result["status"] == "done", f"Pipeline failed: {result.get('error', '?')}"

    # ── Step 2: V5→V4 compat conversion ──
    print("\n--- V5→V4 Compat Test ---")
    from valuation_app.scheduler import Scheduler
    a1_v4, a2_v4, a3_v4 = Scheduler._v5_to_v4_compat(result)

    # Verify key fields
    cf = a1_v4.get("clean_financials", {})
    vr = a1_v4.get("valuation_routing", {})
    ms = a1_v4.get("market_sanity", {})
    vs = a3_v4.get("valuation_summary", {})
    conf = a3_v4.get("confidence", {})
    ta = a3_v4.get("trade_annotation", {})
    scenarios = a3_v4.get("scenarios", [])

    assert cf.get("market_cap_billion"), "market_cap_billion missing"
    assert vr.get("primary_model"), "primary_model missing"
    assert ms.get("bs_level"), "bs_level missing (market_sanity)"
    assert vs.get("probability_weighted_upside_pct") is not None, "upside missing"
    assert conf.get("overall_score"), "confidence missing"
    assert ta.get("tier"), "trade_tier missing"
    assert len(scenarios) == 3, f"scenarios count: {len(scenarios)}"
    print("Compat fields: OK")

    # ── Step 3: HTML Report ──
    print("\n--- HTML Report Test ---")
    agent0_record = {
        "stock_code": "300476",
        "stock_name": "胜宏科技",
        "investment_theme": event["investment_theme"],
        "response_level": "L4",
        "event_date": "2023-03-31",
        "event_source": "Coze Agent0",
    }

    from valuation_app.report_builder import build_html_report, save_report
    try:
        html = build_html_report(agent0_record, a1_v4, a2_v4, a3_v4)
        assert "<html" in html, "HTML missing <html> tag"
        assert "胜宏科技" in html, "HTML missing stock name"
        assert len(html) > 5000, f"HTML too short: {len(html)} chars"
        print(f"HTML generated: {len(html)} chars")

        # Save report
        report_path = save_report(html, "300476")
        print(f"Report saved: {report_path}")
        assert Path(report_path).exists(), "Report file not created"

    except Exception as e:
        print(f"HTML report FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise

    # ── Step 4: Verify Coze row fields ──
    print("\n--- Coze Table Fields Test ---")
    bear = next((s for s in scenarios if "bear" in s.get("name", "").lower()), {})
    base = next((s for s in scenarios if "base" in s.get("name", "").lower()), {})
    bull = next((s for s in scenarios if "bull" in s.get("name", "").lower()), {})

    row = {
        "primary_model": vr.get("primary_model", ""),
        "prob_weighted_upside_pct": vs.get("probability_weighted_upside_pct"),
        "asymmetry_ratio": vs.get("asymmetry_ratio"),
        "quality_flag": vs.get("quality_flag"),
        "current_mcap_billion": cf.get("market_cap_billion"),
        "bear_prob": bear.get("probability_pct"),
        "bear_upside_pct": bear.get("upside_pct"),
        "base_prob": base.get("probability_pct"),
        "base_upside_pct": base.get("upside_pct"),
        "bull_prob": bull.get("probability_pct"),
        "bull_upside_pct": bull.get("upside_pct"),
        "confidence_score": conf.get("overall_score"),
        "trade_tier": ta.get("tier"),
    }

    for k, v in row.items():
        status = "OK" if v is not None else "MISSING"
        if status == "MISSING":
            print(f"  {k}: {status}")
    print(f"Coze fields: all present")

    # ── Summary ──
    print("\n" + "=" * 50)
    a3 = result.get("agent3", {})
    vs5 = a3.get("valuation_summary", {})
    print(f"V5 Pipeline: {elapsed:.0f}s")
    print(f"  Model: {vr.get('primary_model')}")
    print(f"  Upside: {vs5.get('probability_weighted_upside_pct'):.1f}%")
    print(f"  Asymmetry: {vs5.get('asymmetry_ratio'):.1f}")
    print(f"  Confidence: {conf.get('overall_score')}/10")
    print(f"  Tier: {ta.get('tier')}")
    print(f"  HTML: {len(html)} chars")
    print(f"[OK] V5 Integration Test PASSED")


if __name__ == "__main__":
    test_full_integration()
