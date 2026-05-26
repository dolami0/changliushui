"""
Agent-0 + Agent-1 联合测试

测试用例来自评测集 pipeline_eval_set.json（2-3条案例）。
验证: core_package 100% 成功率 / specialized 按行业获取 / 增量补取钩子。
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

from agent0_pre_router import Agent0
from agent1_data_forge import DataForge, DataForgeError


def load_test_cases() -> list[dict]:
    """从评测集加载测试案例（取前2条）。"""
    eval_path = BASE / "evals" / "pipeline_eval_set.json"
    with open(eval_path, encoding="utf-8") as f:
        es = json.load(f)
    # 选 300476 胜宏科技 和 688256 寒武纪
    targets = {"300476", "688256"}
    cases = [c for c in es["cases"] if c["stock_code"] in targets]
    return cases[:2]


def test_agent0(stock_code: str, event_data: dict):
    """测试 Agent-0 预路由。"""
    a0 = Agent0()
    result = a0.run(stock_code, event_data)
    pr = result["pre_routing_result"]
    dr = pr["data_requirements"]

    print(f"\n{'─'*50}")
    print(f"Agent-0: {pr['ticker']} {pr['industry_classification']}")
    print(f"  行业匹配: {pr['industry_key_matched'] or '无→全量拉取'}")
    print(f"  事件标签: {pr['event_tags_matched']}")
    print(f"  Core: {len(dr['core_package']['fields'])}字段 {dr['core_package']['failure_action']}")
    print(f"  Specialized: {len(dr['specialized_package']['fields'])}字段={dr['specialized_package']['fields']}")
    print(f"  Hint: {pr['model_category_hint']} (置信={pr['hint_confidence']})")

    assert dr["core_package"]["mandatory"] is True
    assert dr["core_package"]["failure_action"] == "terminate"
    assert len(dr["core_package"]["fields"]) >= 14
    return result["pre_routing_result"]


def test_agent1(pre_routing: dict):
    """测试 Agent-1 数据炼器。"""
    forge = DataForge()
    try:
        data = forge.run(pre_routing)
    except DataForgeError as e:
        print(f"  ✗ E101: {e}")
        return None

    packages = data["packages"]
    core = packages["core"]
    spec = packages["specialized"]
    val = packages["validation"]

    print(f"\n  Core: {core['status']} quality={core['quality_score']}")
    print(f"    市值={core['fields'].get('market_cap_billion')}亿 "
          f"营收={core['fields'].get('revenue_ttm_billion')}亿 "
          f"净利={core['fields'].get('net_profit_ttm_billion')}亿")
    print(f"    ROIC={core['fields'].get('roic_pct')}% PE={core['fields'].get('pe_ttm')}x "
          f"PB={core['fields'].get('pb')}x")
    print(f"    警告: {core['fields'].get('caution_flags')}")
    assert core["status"] == "complete", f"Core包状态异常: {core['status']}"
    assert core["fields"].get("market_cap_billion"), "市值缺失"

    print(f"  Specialized: {spec['status']} quality={spec['quality_score']} "
          f"fetched={len(spec['fields'])} missing={len(spec['missing_fields'])}")

    print(f"  Validation: {val['status']} quality={val['quality_score']} "
          f"fetched={len(val['fields'])} missing={len(val['missing_fields'])}")

    print(f"  整体质量: {data['overall_data_quality_score']}")
    print(f"  增量补取: {data['incremental_fetch_hook']['available']}")

    # 测试增量补取
    inc = forge.fetch_incremental(["peer_median_pe", "dividend_yield"])
    print(f"  增量补取测试: {len(inc)}字段={list(inc.keys())}")

    return data


def test_incremental_standalone():
    """单独测试增量补取：创建 DataForge 后先 fetch 再补取。"""
    print(f"\n{'='*50}")
    print("增量补取独立测试")

    forge = DataForge()
    # 手动构造最小 pre_routing 测试核心拉取
    pr = {
        "ticker": "300476",
        "stock_name": "胜宏科技",
        "data_requirements": {
            "core_package": {"fields": [], "mandatory": True, "failure_action": "terminate"},
            "specialized_package": {"fields": []},
            "validation_package": {"fields": []},
            "optional_package": {"fields": []},
        },
    }
    data = forge.run({"pre_routing_result": pr})
    print(f"  核心拉取完成: 市值={data['packages']['core']['fields'].get('market_cap_billion')}亿")

    inc = forge.fetch_incremental(["peer_median_pe", "dividend_yield", "unknown_field"])
    print(f"  补取结果: {list(inc.keys())}")
    assert isinstance(inc, dict), "增量补取应返回 dict"


def main():
    cases = load_test_cases()
    if not cases:
        print("未找到测试案例！检查 pipeline_eval_set.json 是否包含 300476/688256")
        return

    print(f"联合测试: {len(cases)} 条案例")
    results = []

    for c in cases:
        code = c["stock_code"]
        name = c["stock_name"]
        event = {
            "raw_event_text": c.get("event_text", ""),
            "event_deduction": c["agent0_output"].get("event_deduction", ""),
            "investment_theme": c["agent0_output"].get("investment_theme", ""),
            "stock_name": name,
        }

        print(f"\n{'='*60}")
        print(f"[{code}] {name}")

        # Agent-0
        pr = test_agent0(code, event)

        # Agent-1
        data = test_agent1(pr)
        results.append({"code": code, "name": name, "status": "OK" if data else "FAIL"})

    # 增量补取独立测试
    test_incremental_standalone()

    # 汇总
    print(f"\n{'='*60}")
    ok = [r for r in results if r["status"] == "OK"]
    fail = [r for r in results if r["status"] != "OK"]
    print(f"结果: {len(ok)} OK, {len(fail)} FAIL")
    for r in fail:
        print(f"  ✗ {r['code']} {r['name']}")

    print("\n[OK] Agent-0 + Agent-1 联合测试完成")


if __name__ == "__main__":
    main()
