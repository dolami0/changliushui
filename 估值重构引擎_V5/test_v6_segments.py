"""V6 分段测试 — Agent-0 → Agent-3 逐段验证"""
import json, sys, time
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent / "valuation_app"))

from agent0_pre_router import Agent0
from agent1_data_forge import DataForge, DataForgeError
from agent2a_narrative import NarrativeDiagnosis
from agent2b_routing import RouteJudgeV6
from agent3_scenario_asymmetry import ScenarioAsymmetry, precompute_wacc
from data_fetcher import DataFetcher
from env_config import DEEPSEEK_API_KEY

with open('valuation_app/config.json', encoding='utf-8') as f:
    cfg = json.load(f)
deepseek_key = cfg.get("deepseek_api_key", "") or DEEPSEEK_API_KEY

# Test stock
sc = "688627"
sn = "精智达"

event_data = {
    'raw_event_text': '精智达半导体测试设备获长鑫存储大额订单,IPO募资295亿扩产',
    'investment_theme': '押注DRAM/HBM存储测试设备国产替代,公司从显示检测向半导体测试平台转型',
    'event_deduction': '长鑫IPO→大规模扩产→精智达订单份额>50%',
    'adversarial_thinking': '竞争加剧(爱德万/泰瑞达),订单不确定性,毛利率压力',
    'knowledge_supplement': '国内DRAM测试设备市场百亿级,AI算力驱动HBM需求',
    'event_date': '2026-05-28',
    'stock_name': sn,
}

print(f"=== V6 Segment Tests: [{sc}] {sn} ===\n")

# ── Test 1: Agent-0 + Agent-1 (no LLM) ──
print("Test 1: Agent-0 + Agent-1")
a0 = Agent0()
a0_out = a0.run(sc, event_data)
pr = a0_out.get('pre_routing_result', {})
print(f"  industry={pr.get('industry_classification','?')} tags={pr.get('event_tags_matched',[])}")
print(f"  event_date={pr.get('event_date','?')}")

forge = DataForge()
try:
    a1_out = forge.run(a0_out)
    core = a1_out.get('packages', {}).get('core', {}).get('fields', {})
    errors = a1_out.get('fetch_errors', [])
    ok = all([
        core.get('market_cap_yi', 0) > 0,
        core.get('revenue_ttm_yi', 0) > 0,
        core.get('pe_ttm', 0) > 0,
    ])
    print(f"  mcap={core.get('market_cap_yi',0):.0f} rev={core.get('revenue_ttm_yi',0):.1f} np={core.get('net_profit_ttm_yi',0):.1f} pe={core.get('pe_ttm',0):.1f}x errors={len(errors)}")
    print(f"  event_window_prices: {'PRESENT' if a1_out.get('event_window_prices') else 'MISSING'}")
    print(f"  TEST 1: {'PASS' if ok else 'FAIL'}")
except Exception as e:
    print(f"  TEST 1: FAIL — {e}")

# ── Test 2: WACC precompute ──
print("\nTest 2: WACC precompute")
fetcher = DataFetcher()
wacc = precompute_wacc(fetcher, sc, a1_out)
print(f"  wacc={wacc.get('wacc_pct','?')}% rf={wacc.get('rf_pct','?')}% beta={wacc.get('beta','?')} erp={wacc.get('erp_pct','?')}%")
print(f"  TEST 2: {'PASS' if wacc.get('wacc_pct',0) > 0 else 'FAIL'}")

# ── Test 3: Agent-2a Narrative Diagnosis (LLM) ──
print("\nTest 3: Agent-2a Narrative Diagnosis (LLM call)...")
t0 = time.time()
a2a = NarrativeDiagnosis(deepseek_key=deepseek_key)
a2a_out = a2a.run(a1_out, event_data, wacc)
elapsed = time.time() - t0

ok = all([
    a2a_out.get('market_narrative', {}).get('primary_anchor'),
    a2a_out.get('event_pricing', {}).get('event_profile', {}).get('distribution_shape'),
    a2a_out.get('signal_audit', {}).get('step2d_score') is not None,
    a2a_out.get('forward_to_routing', {}).get('model_family_constraint'),
])
mn = a2a_out.get('market_narrative', {})
ep = a2a_out.get('event_pricing', {})
sa = a2a_out.get('signal_audit', {})
fwd = a2a_out.get('forward_to_routing', {})
print(f"  anchor={mn.get('primary_anchor','?')} sotp={mn.get('sotp_triggered',False)}")
print(f"  spectrum={ep.get('event_profile',{}).get('distribution_shape','?')} T={ep.get('event_profile',{}).get('timing_certainty','?')} B={ep.get('event_profile',{}).get('outcome_binaryness','?')} P={ep.get('event_profile',{}).get('precedent_richness','?')}")
print(f"  priced={ep.get('pricing_assessment',{}).get('overall_priced_in','?')} step2d={sa.get('step2d_score','?')}")
print(f"  family={fwd.get('model_family_constraint','?')} shape={fwd.get('distribution_shape','?')}")
print(f"  pricing_tool: {'PRESENT' if a2a_out.get('_pricing_tool') else 'MISSING'}")
print(f"  elapsed={elapsed:.0f}s")
print(f"  TEST 3: {'PASS' if ok else 'FAIL'}")
if not ok:
    print(f"  DEBUG: mn={bool(mn)} ep={bool(ep)} sa={bool(sa)} fwd={bool(fwd)}")

# ── Test 4: Agent-2b Routing (LLM) ──
print("\nTest 4: Agent-2b Routing (LLM call)...")
t0 = time.time()
a2b = RouteJudgeV6(deepseek_key=deepseek_key)
a2b_out = a2b.run(a1_out, a2a_out, event_data)
elapsed = time.time() - t0

rd = a2b_out.get('routing_decision', {})
cc = rd.get('constraint_compliance', {})
ok = bool(rd.get('primary_model'))
print(f"  model={rd.get('primary_model','?')} cat={rd.get('model_category','?')} valid={rd.get('validation_models',[])}")
print(f"  constraint={cc.get('family_constraint_applied','?')} override={cc.get('constraint_override',False)}")
print(f"  reason: {(rd.get('routing_reason','?') or '')[:120]}")
print(f"  elapsed={elapsed:.0f}s")
print(f"  TEST 4: {'PASS' if ok else 'FAIL'}")

# ── Test 5: Agent-3 Scenario (LLM) ──
print("\nTest 5: Agent-3 Scenario (LLM call)...")
t0 = time.time()
a3 = ScenarioAsymmetry(deepseek_key=deepseek_key)
a3_out = a3.run(a1_out, rd, event_data, agent2a_output=a2a_out)
elapsed = time.time() - t0

sv = a3_out.get('scenario_valuation', {})
vs = a3_out.get('valuation_summary', sv)
details = sv.get('scenario_details', {})
if isinstance(details, list):
    details = {d.get('scenario',''): d for d in details}

ok = all([
    vs.get('probability_weighted_upside_pct', 999) != 999,
    vs.get('asymmetry_ratio', 999) != 999,
    details.get('bear',{}).get('probability') is not None,
    details.get('base',{}).get('probability') is not None,
    details.get('bull',{}).get('probability') is not None,
])
for s in ('bear','base','bull'):
    sc = details.get(s,{})
    print(f"  {s}: p={sc.get('probability',0):.0%} u={sc.get('upside_pct',0):+.1f}% m={sc.get('target_mcap_yi',0):.0f}yi")
print(f"  weighted={vs.get('probability_weighted_upside_pct',0):+.1f}% asym={vs.get('asymmetry_ratio',0):.1f}x q={vs.get('quality_flag','?')}")
print(f"  conf={a3_out.get('confidence',{}).get('overall_score','?')}/10")
print(f"  tier={a3_out.get('trade_annotation',{}).get('tier','?')}")
print(f"  elapsed={elapsed:.0f}s")

# Check that upside values are non-zero
u_ok = abs(vs.get('probability_weighted_upside_pct', 0)) > 0.1
print(f"  TEST 5: {'PASS' if (ok and u_ok) else 'FAIL'} {'(upside=0!)' if not u_ok else ''}")

# ── Summary ──
print(f"\n{'='*50}")
print(f"All segment tests complete.")
print(f"Total time: ~{elapsed + (time.time()-t0):.0f}s")
