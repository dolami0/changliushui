"""Full pipeline test with baseline agent"""
import sys, os, json, time
sys.path.insert(0, 'src')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from orchestrator import Orchestrator

# Load raw event from existing report
with open('reports/data/300806_20260609_1104.json', encoding='utf-8') as f:
    d = json.load(f)

a0 = d['agent0']
stock_code = a0['stock_code']
stock_name = a0['stock_name']

# Pass as event_data (Agent-0 will re-process it)
event_data = {
    'stock_code': stock_code,
    'stock_name': stock_name,
    'raw_event_text': a0.get('raw_event_text', ''),
    'event_source': a0.get('event_source', '天机'),
    'created_at': a0.get('created_at', ''),
    'bstudio_create_time': a0.get('bstudio_create_time', ''),
    'response_level': a0.get('response_level', ''),
    'id': a0.get('id', ''),
}

print(f"Running: {stock_name} ({stock_code})")
print(f"Event: OK ({len(event_data['raw_event_text'])} chars)")

orch = Orchestrator()
t0 = time.time()

result = orch.run(
    stock_code=stock_code,
    event_data=event_data,
    progress_cb=lambda stage, step, total, status, msg: print(f"  [{stage}] {status}: {msg}"),
)

elapsed = time.time() - t0
print(f"\n=== Pipeline complete ({elapsed:.0f}s) ===")
print(f"Status: {result.get('status')}")

# Show key outputs
bl = result.get('baseline_report', '')
if bl:
    print(f"Baseline report: {len(bl)} chars")

a2a = result.get('agent2a', {})
mn = a2a.get('market_narrative', {})
print(f"2a anchor: {mn.get('primary_anchor')}, lifecycle: {mn.get('narrative_lifecycle')}")

a2 = result.get('agent2', {})
rd = a2.get('routing_decision', {}) if isinstance(a2, dict) else {}
print(f"2b model: {rd.get('primary_model')} ({rd.get('model_category')})")

a3 = result.get('agent3', {})
vs = a3.get('valuation_summary', {})
print(f"3 upside: {vs.get('probability_weighted_upside_pct',0):+.1f}% asym: {vs.get('asymmetry_ratio',0):.1f}x")
ta = a3.get('trade_annotation', {})
print(f"Rating: {ta.get('tier')} {ta.get('total_score')}")

# Save
out = f'tmp_full_pipeline_{stock_code}.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
print(f"\nSaved: {out}")
