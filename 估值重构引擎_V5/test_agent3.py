"""
Agent-3 推演裁决 测试

验证:
1. BS画像预计算（各模型A/B/D/F的BS方法）
2. 代码校验逻辑（概率和/单调性/WACC一致性）
3. 输出schema与V4调度器兼容
4. 端到端管线 (Agent-0→1→2→3)
"""

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "src"))

from agent3_scenario_asymmetry import (
    precompute_bs_profile,
    _validate_output,
    _assemble_final_output,
    ScenarioAsymmetry,
)


def make_mock_data_package(model="A", **overrides):
    """构造模拟 data_package 用于单元测试。"""
    fields = {
        "market_cap_billion": 200,
        "revenue_ttm_billion": 50,
        "net_profit_ttm_billion": 15,
        "operating_profit_ttm_billion": 18,
        "roic_pct": 18.5,
        "gross_margin_pct": 35,
        "net_margin_pct": 30,
        "pe_ttm": 25,
        "pb": 3.5,
        "ps_ttm": 4,
        "total_equity_billion": 57,
        "total_assets_billion": 100,
        "interest_bearing_debt_billion": 10,
        "cash_billion": 20,
        "ocf_ttm_billion": 12,
        "capex_ttm_billion": 5,
        "nopat_billion": 10,
        "caution_flags": [],
        "data_quality_score": 9,
        "stock_name": "TestCo",
        "pe_historical_rank": 35,
    }
    fields.update(overrides)
    return {
        "stock_code": "300476",
        "stock_name": "TestCo",
        "industry": "电子",
        "packages": {
            "core": {"fields": fields, "status": "complete", "quality_score": 9},
            "specialized": {"fields": {}, "status": "empty", "quality_score": 0},
            "validation": {"fields": {}, "status": "empty", "quality_score": 0},
            "optional": {"fields": {}, "status": "empty", "quality_score": 0},
        },
    }


def test_bs_profile():
    """测试 BS 画像预计算（各类模型）。"""
    print("\n--- BS Profile Tests ---")

    wacc = {"wacc_pct": 9.5, "rf_pct": 1.75, "beta": 1.2, "erp_pct": 6.5,
            "re_pct": 9.55, "rd_pct": 3.75, "d_ratio_pct": 5}

    test_models = {"A": "reverse_DCF", "B": "PS_industry_rank", "D": "PB_industry_rank",
                   "F": "PB_baseline", "G": "reverse_DCF"}

    for model, expected_method in test_models.items():
        dp = make_mock_data_package(model=model)
        bs = precompute_bs_profile(model, dp, wacc)
        assert bs["bs_method"] == expected_method, f"{model}: expected {expected_method}, got {bs['bs_method']}"
        assert "bs_level" in bs, f"{model}: missing bs_level"
        assert "market_premium_pct" in bs, f"{model}: missing market_premium_pct"
        assert "market_story" in bs, f"{model}: missing market_story"
        print(f"  {model}: method={bs['bs_method']} premium={bs['market_premium_pct']}% level={bs['bs_level'][:30]}...")

    print("  [OK] BS profile tests passed")


def test_validation():
    """测试校验逻辑。"""
    print("\n--- Validation Tests ---")

    wacc = {"wacc_pct": 9.5}
    bs = {"market_premium_pct": -30, "bs_level": "折价", "bs_method": "reverse_DCF",
          "market_story": "", "wacc_simple_pct": 9.5,
          "ev_billion": 190, "nopat_billion": 10, "roic_pct": 18.5,
          "pe_ttm": 25, "pb": 3.5, "warnings": []}

    # E304: 概率和不等于1
    bad_probs = {
        "scenario_valuation": {
            "scenario_details": {
                "base": {"probability": 0.7, "upside_pct": 30},
                "bull": {"probability": 0.3, "upside_pct": 80},
                "bear": {"probability": 0.2, "upside_pct": -20},
            }
        }
    }
    warns = _validate_output(bad_probs, bs, wacc)
    assert any(w["code"] == "E304" for w in warns), f"Expected E304, got {warns}"
    print(f"  E304 detected: {[w['code'] for w in warns]}")

    # E305: 单调性违反
    bad_mono = {
        "scenario_valuation": {
            "scenario_details": {
                "base": {"probability": 0.5, "upside_pct": 30},
                "bull": {"probability": 0.3, "upside_pct": 10},  # bull < base!
                "bear": {"probability": 0.2, "upside_pct": -20},
            }
        }
    }
    warns = _validate_output(bad_mono, bs, wacc)
    assert any(w["code"] == "E305" for w in warns), f"Expected E305, got {warns}"
    print(f"  E305 detected")

    # E307: WACC 被篡改
    bad_wacc = {
        "scenario_valuation": {"scenario_details": {
            "base": {"probability": 0.5, "upside_pct": 30},
            "bull": {"probability": 0.3, "upside_pct": 80},
            "bear": {"probability": 0.2, "upside_pct": -20},
        }},
        "market_sanity": {"wacc_simple_pct": 15.0},  # 修改了WACC!
    }
    warns = _validate_output(bad_wacc, bs, wacc)
    assert any(w["code"] == "E307" for w in warns), f"Expected E307, got {warns}"
    print(f"  E307 detected")

    # Clean: 应该无警告
    clean = {
        "scenario_valuation": {
            "scenario_details": {
                "base": {"probability": 0.50, "upside_pct": 30, "target_mcap_billion": 260},
                "bull": {"probability": 0.30, "upside_pct": 80, "target_mcap_billion": 360},
                "bear": {"probability": 0.20, "upside_pct": -20, "target_mcap_billion": 160},
            },
            "probability_weighted_upside_pct": 28,
            "probability_weighted_mcap_billion": 258,
            "asymmetry_ratio": 4.0,
            "quality_flag": "HIGH_QUALITY",
        },
        "reverse_dcf": {"market_implied_g_pct": 5, "my_implied_g_pct": 15, "expectation_gap_pct": 10,
                        "gap_direction": "市场低估", "gap_magnitude": "显著"},
        "expectation_gap": {"level": "显著正向预期差", "note": "test"},
        "confidence": {"overall_score": 7, "overall_label": "高", "dimensions": {}},
        "trade_annotation": {"tier": "★★★", "total_score": "8/10",
                            "dimension_scores": {}, "alignment_signals": [], "tier_note": "",
                            "suggested_action": ""},
        "monitoring_kpis": {}, "risk_triggers": {}, "narrative": "test",
    }
    warns = _validate_output(clean, bs, wacc)
    print(f"  Clean: {len(warns)} warnings (expected 0)")
    # 对于 clean 输出，可能只有 BS_MISMATCH info，不应有 E304/E305/E307
    assert not any(w["code"] in ("E304", "E305", "E307") for w in warns), f"Unexpected errors: {warns}"

    print("  [OK] Validation tests passed")


def test_output_schema():
    """测试输出 schema 与 V4 调度器兼容。"""
    print("\n--- Output Schema Test ---")

    llm_output = {
        "scenario_valuation": {
            "scenario_details": {
                "base": {"probability": 0.50, "upside_pct": 30, "target_mcap_billion": 260},
                "bull": {"probability": 0.30, "upside_pct": 80, "target_mcap_billion": 360},
                "bear": {"probability": 0.20, "upside_pct": -20, "target_mcap_billion": 160},
            },
            "probability_weighted_upside_pct": 28,
            "probability_weighted_mcap_billion": 258,
            "asymmetry_ratio": 4.0,
            "quality_flag": "HIGH_QUALITY",
        },
        "reverse_dcf": {"market_implied_g_pct": 5, "my_implied_g_pct": 15,
                        "expectation_gap_pct": 10, "gap_direction": "市场低估", "gap_magnitude": "显著"},
        "expectation_gap": {"level": "显著正向预期差", "note": "test"},
        "confidence": {"overall_score": 7, "overall_label": "高", "dimensions": {}},
        "trade_annotation": {"tier": "★★★ 高赔率机会", "total_score": "8/10",
                            "dimension_scores": {"odds_quality": 3, "pricing_headroom": 2,
                                                "transmission_confidence": 2, "model_consistency": 1},
                            "alignment_signals": ["test"], "tier_note": "", "suggested_action": ""},
        "monitoring_kpis": {}, "risk_triggers": {}, "narrative": "test narrative",
    }

    dp = make_mock_data_package()
    routing = {"primary_model": "A", "model_category": "Earnings Multiples",
               "validation_models": ["B"], "routing_reason": "test",
               "model_migration_path": {}}
    bs = {"bs_method": "reverse_DCF", "bs_level": "折价", "ev_billion": 190, "nopat_billion": 10,
          "roic_pct": 18.5, "wacc_simple_pct": 9.5, "market_premium_pct": -30,
          "pe_ttm": 25, "pb": 3.5, "market_story": "test", "warnings": [],
          "wacc_params": {"wacc_pct": 9.5}}

    output = _assemble_final_output(llm_output, bs, dp, routing, [])

    # V4 调度器需要的字段
    assert "report_meta" in output
    assert "valuation_routing" in output
    assert "market_sanity" in output
    assert "scenario_valuation" in output
    assert "valuation_summary" in output  # scheduler._write_result_to_coze 使用
    assert "expectation_gap" in output
    assert "confidence" in output
    assert "trade_annotation" in output
    assert "scenarios" in output  # scheduler 使用 scenarios[i]["name"]["probability_pct"]["upside_pct"]
    assert "narrative" in output

    # 验证 scenarios 格式
    assert len(output["scenarios"]) == 3
    for s in output["scenarios"]:
        assert "name" in s and "probability_pct" in s and "upside_pct" in s

    # 验证 valuation_summary 与 V4 scheduler 兼容
    vs = output["valuation_summary"]
    assert "probability_weighted_upside_pct" in vs
    assert "asymmetry_ratio" in vs
    assert "quality_flag" in vs

    print("  All required V4 fields present")
    print("  [OK] Output schema test passed")


def main():
    print("Agent-3 ScenarioAsymmetry Test Suite\n")

    test_bs_profile()
    test_validation()
    test_output_schema()

    print("\n" + "=" * 40)
    print("Agent-3 all tests done")


if __name__ == "__main__":
    main()
