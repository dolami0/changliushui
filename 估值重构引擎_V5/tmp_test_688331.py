"""Full pipeline test for 荣昌生物(688331) — stop if not rNPV"""
import sys, os, json, time, io
sys.path.insert(0, 'src')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from orchestrator import Orchestrator

# Load event data
with open('tmp_event_688331.json', encoding='utf-8') as f:
    event_data = json.load(f)

stock_code = event_data['stock_code']
stock_name = event_data['stock_name']

print(f"=== Pipeline: {stock_name} ({stock_code}) ===")
print(f"Event: {len(event_data.get('raw_event_text',''))} chars, source={event_data.get('event_source','')}")

orch = Orchestrator()
t0 = time.time()

result = orch.run(
    stock_code=stock_code,
    event_data=event_data,
    progress_cb=lambda stage, step, total, status, msg: print(f"  [{stage}] {status}: {msg}"),
)

elapsed = time.time() - t0

# Check pipeline type
pipeline_type = result.get('pipeline_type', 'standard')
print(f"\n=== Pipeline complete ({elapsed:.0f}s) ===")
print(f"Pipeline type: {pipeline_type}")

if pipeline_type != 'rnpv':
    print(f"\n*** NOTE: Expected rNPV, got {pipeline_type} — showing results anyway ***")
    a2 = result.get('agent2', {})
    if isinstance(a2, dict):
        rd = a2.get('routing_decision', {})
        print(f"Routing: primary={rd.get('primary_model')} ({rd.get('model_category')})")
        print(f"Reason: {rd.get('routing_reason','?')[:200]}")

# Show results
bl = result.get('baseline_report', '')
print(f"Baseline: {len(bl)} chars")

a2a = result.get('agent2a', {})
mn = a2a.get('market_narrative', {}) if isinstance(a2a, dict) else {}
print(f"2a anchor: {mn.get('primary_anchor')}, lifecycle: {mn.get('narrative_lifecycle')}")

a2 = result.get('agent2', {})
rd = a2.get('routing_decision', {}) if isinstance(a2, dict) else {}
print(f"2b model: {rd.get('primary_model')} ({rd.get('model_category')})")

a3 = result.get('agent3', {})
vs = a3.get('valuation_summary', {}) if isinstance(a3, dict) else {}
print(f"3 upside: {vs.get('probability_weighted_upside_pct',0):+.1f}% asym: {vs.get('asymmetry_ratio',0):.1f}x")
ta = a3.get('trade_annotation', {}) if isinstance(a3, dict) else {}
print(f"Rating: {ta.get('tier')} {ta.get('total_score')}")

# Save
out = f'tmp_full_pipeline_{stock_code}.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
print(f"\nSaved: {out}")
