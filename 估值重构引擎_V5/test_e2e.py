"""
V5 端到端测试 — Agent-0→1→2→3 完整管线

测试:
1. 单条真实标的管线运行
2. 评测模式 frozen 数据注入
3. 核心质量指标验证
"""

import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

from orchestrator import Orchestrator
from env_config import DEEPSEEK_API_KEY


def test_full_pipeline():
    """完整 4-Agent 管线: Agent-0→1→2→3 (真实数据+LLM)。"""
    print("=" * 50)
    print("E2E Test: 完整管线 (300476 胜宏科技)")
    print("=" * 50)

    event = {
        "raw_event_text": "AI服务器PCB需求爆发，胜宏科技作为核心供应商受益。",
        "event_deduction": "AI服务器升级→高端PCB需求倍增→份额提升→营收利润双增",
        "investment_theme": "AI硬件核心供应商，高端PCB结构性短缺",
        "stock_name": "胜宏科技",
    }

    orch = Orchestrator(deepseek_key=DEEPSEEK_API_KEY)

    t0 = datetime.now()
    result = orch.run("300476", event)
    elapsed = (datetime.now() - t0).total_seconds()

    print(f"\n总耗时: {elapsed:.1f}s")
    print(f"状态: {result['status']}")

    # 验证各层产出
    audit = result.get("audit", {})
    print(f"增量补取: {audit.get('incremental_fetch_count', 0)}次")
    for k, v in audit.get("step_times", {}).items():
        print(f"  {k}: {v}s")

    assert result["status"] == "done", f"管线失败: {result.get('error', '?')}"

    # Agent-0
    a0 = result.get("agent0", {})
    pr = a0.get("pre_routing_result", {})
    print(f"\nAgent-0: industry={pr.get('industry_classification','?')} hint={pr.get('model_category_hint',[])}")

    # Agent-1
    a1 = result.get("agent1", {})
    print(f"Agent-1: quality={a1.get('overall_data_quality_score','?')}")
    core = a1.get("packages", {}).get("core", {}).get("fields", {})
    print(f"  mcap={core.get('market_cap_billion')}亿 roic={core.get('roic_pct')}%")

    # Agent-2
    a2 = result.get("agent2", {})
    rd = a2.get("routing_decision", {})
    print(f"Agent-2: model={rd.get('primary_model','?')} category={rd.get('model_category','?')}")
    inc = a2.get("incremental_fetch_request", {})
    print(f"  incremental_fetch: triggered={inc.get('triggered', False)}")

    # Agent-3
    a3 = result.get("agent3", {})
    vs = a3.get("valuation_summary", {})
    print(f"Agent-3: upside={vs.get('probability_weighted_upside_pct',0):.1f}% "
          f"asym={vs.get('asymmetry_ratio',0):.1f}")
    conf = a3.get("confidence", {})
    print(f"  confidence={conf.get('overall_score')}/10")
    ta = a3.get("trade_annotation", {})
    print(f"  tier={ta.get('tier','?')}")

    # 验证核心字段不为空
    assert a0 is not None
    assert a1 is not None
    assert a2 is not None
    assert a3 is not None
    assert vs.get("probability_weighted_upside_pct") is not None
    assert vs.get("asymmetry_ratio") is not None
    assert conf.get("overall_score")

    print(f"\n[OK] E2E pipeline test passed ({elapsed:.0f}s)")

    return result


def test_eval_mode():
    """评测模式: frozen 数据注入。"""
    print("\n" + "=" * 50)
    print("E2E Test: 评测模式 (300476 frozen数据)")
    print("=" * 50)

    eval_path = BASE / "evals" / "pipeline_eval_set.json"
    with open(eval_path, encoding="utf-8") as f:
        es = json.load(f)
    case = next(c for c in es["cases"] if c["stock_code"] == "300476")

    frozen = case.get("frozen_agent1", {})
    cf = frozen.get("clean_financials", {})
    print(f"frozen: mcap={cf.get('market_cap_billion')}亿 roic={cf.get('roic_pct')}%")

    orch = Orchestrator(deepseek_key=DEEPSEEK_API_KEY)
    orch.enable_eval_mode({"frozen_agent1": frozen})

    event = {
        "raw_event_text": case.get("event_text", ""),
        "event_deduction": case["agent0_output"].get("event_deduction", ""),
        "investment_theme": case["agent0_output"].get("investment_theme", ""),
        "stock_name": case["stock_name"],
    }

    t0 = datetime.now()
    result = orch.run(case["stock_code"], event)
    elapsed = (datetime.now() - t0).total_seconds()

    print(f"状态: {result['status']} (耗时{elapsed:.1f}s)")

    a1 = result.get("agent1", {})
    source = a1.get("_source", "")
    assert source == "eval_frozen", f"评测模式未注入frozen数据: {source}"
    print(f"Agent-1: {source}")

    a2 = result.get("agent2", {})
    rd = a2.get("routing_decision", {})
    print(f"Agent-2: model={rd.get('primary_model','?')}")

    a3 = result.get("agent3", {})
    vs = a3.get("valuation_summary", {})
    print(f"Agent-3: upside={vs.get('probability_weighted_upside_pct',0):.1f}% "
          f"asym={vs.get('asymmetry_ratio',0):.1f}")

    assert result["status"] == "done"
    print(f"\n[OK] Eval mode test passed ({elapsed:.0f}s)")

    return result


def main():
    print("V5 E2E Test Suite\n")

    # 评测模式（用frozen数据，更快）
    test_eval_mode()

    # 完整生产管线（真实API数据）
    test_full_pipeline()

    print("\n" + "=" * 50)
    print("V5 E2E tests done")


if __name__ == "__main__":
    main()
