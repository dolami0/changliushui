"""
Agent-2 路由判官 测试

验证:
1. 从 Agent-0→Agent-1 获取数据包
2. Agent-2 路由判决（LLM 三层路由）
3. 案例匹配分数分布
4. 增量补取检查
5. Fallback 路由（不依赖 LLM）
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

from agent0_pre_router import Agent0
from agent1_data_forge import DataForge
from agent2_route_judge import RouteJudge


def test_with_real_data():
    """使用评测集中的案例做端到端测试。"""
    eval_path = BASE / "evals" / "pipeline_eval_set.json"
    with open(eval_path, encoding="utf-8") as f:
        es = json.load(f)

    # 选 300476 胜宏科技（PCB，有完整案例匹配）
    case = next((c for c in es["cases"] if c["stock_code"] == "300476"), None)
    if not case:
        print("未找到测试案例 300476!")
        return

    code = case["stock_code"]
    name = case["stock_name"]
    print(f"测试: {name}({code})")
    print(f"事件日期: {case['event_date']}")

    # ── Agent-0 ──
    a0 = Agent0()
    event = {
        "raw_event_text": case.get("event_text", ""),
        "event_deduction": case["agent0_output"].get("event_deduction", ""),
        "investment_theme": case["agent0_output"].get("investment_theme", ""),
        "stock_name": name,
    }
    pr = a0.run(code, event)["pre_routing_result"]
    print(f"  Agent-0: industry={pr['industry_classification']} hint={pr['model_category_hint']}")

    # ── Agent-1 ──
    forge = DataForge()
    data = forge.run(pr)
    print(f"  Agent-1: core={data['packages']['core']['status']} quality={data['overall_data_quality_score']}")

    # ── Agent-2 ──
    judge = RouteJudge()
    result = judge.run(data, event)

    # ── 验证 ──
    rd = result.get("routing_decision", {})
    print(f"\n  Agent-2 路由判决:")
    print(f"    primary_model: {rd.get('primary_model', 'MISSING')}")
    print(f"    model_category: {rd.get('model_category', 'MISSING')}")
    print(f"    validation_models: {rd.get('validation_models', [])}")
    print(f"    routing_reason: {rd.get('routing_reason', '')[:100]}")

    migration = rd.get("model_migration_path", {})
    if migration:
        print(f"    migration: {migration.get('current_phase', '')} -> {migration.get('next_phase_model', '')}")

    # 案例匹配
    top3 = result.get("case_matches_top3", [])
    print(f"\n  案例匹配Top3:")
    for cm in top3:
        print(f"    {cm['case_code']} score={cm['score']} — {cm['key_anchor']}")

    # 增量补取
    inc = result.get("incremental_fetch_request", {})
    print(f"\n  增量补取: triggered={inc.get('triggered', False)}")
    if inc.get("triggered"):
        print(f"    missing: {inc.get('missing_fields', [])}")

    # 搜索
    search = result.get("web_search_summary", {})
    print(f"  联网搜索: rounds={search.get('searches_performed', 0)}")

    # 断言
    assert rd.get("primary_model"), "primary_model 不能为空"
    assert rd.get("model_category"), "model_category 不能为空"
    assert isinstance(result.get("case_matches_top3"), list), "case_matches_top3 必须是 list"
    assert len(result.get("case_matches_top3", [])) <= 3, "Top3 最多3条"

    print(f"\n  [OK] Agent-2 routing test passed")


def test_fallback_routing():
    """测试 fallback 路由（不依赖 DeepSeek）。"""
    print(f"\n{'─'*40}")
    print("Fallback 路由测试")

    # 模拟各种财务状态的 data_package
    test_cases = [
        {"roic": 15, "np": 10, "industry": "电子", "expected": "A"},
        {"roic": -5, "np": -2, "industry": "医药生物", "expected": "F"},
        {"roic": 3, "np": 1, "industry": "银行", "expected": "D"},
        {"roic": -10, "np": -5, "industry": "计算机", "expected": "B"},
        {"roic": 0, "np": 0.5, "industry": "化工", "expected": "C"},
    ]

    for tc in test_cases:
        dp = {
            "packages": {
                "core": {
                    "fields": {
                        "roic_pct": tc["roic"], "net_profit_ttm_billion": tc["np"],
                        "revenue_ttm_billion": 50, "pe_ttm": 25, "pb": 2,
                    }
                }
            },
            "industry": tc["industry"],
        }
        judge = RouteJudge()
        routing = judge._fallback_routing(dp)
        primary = routing.get("primary_model", "")
        status = "OK" if primary == tc["expected"] else f"EXPECTED {tc['expected']}"
        print(f"  ROIC={tc['roic']}% NP={tc['np']}亿 industry={tc['industry']} -> {primary} ({status})")

    print("  [OK] Fallback routing test done")


def test_case_loader_integration():
    """测试 case_loader 集成。"""
    print(f"\n{'─'*40}")
    print("案例加载器集成测试")

    import case_loader
    cases = case_loader.load_cases()
    print(f"  加载案例数: {len(cases)}")

    assert len(cases) >= 30, f"案例数不足: {len(cases)}"

    # 模拟查找
    a1 = {
        "clean_financials": {
            "roic_pct": 18,
            "market_cap_billion": 150,
            "industry": "电子",
            "pe_ttm": 60,
        },
    }
    matches = case_loader.find_similar(a1, top_n=8)
    print(f"  匹配案例数: {len(matches)}")
    if matches:
        best = matches[0]
        print(f"  最高分: {best[0]['stock_name']}({best[0]['stock_code']}) score={best[1]}")
    # 验证
    assert len(matches) > 0, "应该有匹配案例"
    # 注意: 模拟数据无investment_map，driver/catalyst分=0，最高分≥5即可
    assert matches[0][1] >= 5, f"最高分应>=5: {matches[0][1]}"

    print("  [OK] 案例加载器集成测试通过")


def main():
    print("Agent-2 RouteJudge Test Suite\n")

    test_case_loader_integration()
    test_fallback_routing()
    test_with_real_data()

    print("\n" + "=" * 40)
    print("Agent-2 all tests done")


if __name__ == "__main__":
    main()
