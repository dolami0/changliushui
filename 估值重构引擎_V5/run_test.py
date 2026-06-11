"""Run single stock through full pipeline for dcf/K testing."""
import sys, os, json, time, requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'valuation_app'))
os.chdir(os.path.dirname(__file__))

from env_config import DEEPSEEK_API_KEY, COZE_SAT_TOKEN
from pipeline_runner import PipelineRunner

# Fetch 688313 仕佳光子
url = 'https://api.coze.cn/v1/databases/7644911309938589711/records/query'
headers = {'Authorization': f'Bearer {COZE_SAT_TOKEN}', 'Content-Type': 'application/json'}
resp = requests.post(url, headers=headers, json={'page_num': 1, 'page_size': 50, 'is_async': False}, timeout=15)
items = resp.json().get('data', {}).get('items', [])

record = None
for item in items:
    if item.get('stock_code') == '000831':  # 中国稀土, 资源股测试
        a0_raw = item.get('agent0_json', '{}')
        a0 = json.loads(a0_raw) if isinstance(a0_raw, str) else a0_raw
        record = {
            'stock_code': item.get('stock_code', ''),
            'stock_name': item.get('stock_name', ''),
            'raw_event_text': a0.get('raw_event_text', ''),
            'event_deduction': a0.get('event_deduction', ''),
            'investment_theme': a0.get('investment_theme', ''),
            'adversarial_thinking': a0.get('adversarial_thinking', ''),
            'knowledge_supplement': a0.get('knowledge_supplement', ''),
            'preliminary_reasoning': a0.get('preliminary_reasoning', ''),
            'industry_expert_research': a0.get('industry_expert_research', ''),
            'future': a0.get('future', ''),
            'bstudio_create_time': item.get('bstudio_create_time', ''),
            'event_source': a0.get('event_source', ''),
            'response_level': a0.get('response_level', ''),
        }
        break

if not record:
    print('ERROR: target stock not found')
    sys.exit(1)

def progress_cb(event):
    print(f'  [{event.stage}] {event.status}: {event.step_name}')

runner = PipelineRunner(progress_callback=progress_cb)
t0 = time.time()
try:
    result = runner.run_single(record, DEEPSEEK_API_KEY)
except Exception as e:
    import traceback
    traceback.print_exc()
    result = {"status": "error", "error": str(e)}
print(f'\nDone in {time.time()-t0:.0f}s | Status: {result.get("status")}')

# Show routing
a2b = result.get('agent2', {})
rd = a2b.get('routing_decision', {})
model = rd.get('primary_model', '?')
reason = rd.get('routing_reason', '?')
print(f'\n路由: {model} | {reason[:150]}')

# Show key results
a3 = result.get('agent3', {})
vs = a3.get('valuation_summary', {})
print(f'\n加权涨跌幅: {vs.get("probability_weighted_upside_pct",0):+.1f}% | 不对称比: {vs.get("asymmetry_ratio",0):.1f}x')

sv = a3.get('scenario_valuation', {})
details = sv.get('scenario_details', {})
for sn in ('bear', 'base', 'bull'):
    ds = details.get(sn, {})
    if isinstance(ds, dict):
        print(f'\n{sn}: prob={ds.get("probability","?")}')
        if 'stage1_growth_pct' in ds:
            print(f'  K参数: growth={ds.get("stage1_growth_pct","?")}% years={ds.get("stage1_years","?")} roic={ds.get("roic_assumed_pct","?")}% term_pe={ds.get("terminal_pe","?")}')
        elif 'revenue_growth_3y_cagr_pct' in ds:
            print(f'  B参数: cagr={ds.get("revenue_growth_3y_cagr_pct","?")}% ps={ds.get("target_ps","?")}')
        print(f'  target={ds.get("target_mcap_yi","?")}亿 upside={ds.get("upside_pct","?")}%')
        print(f'  叙事: {ds.get("scenario_narrative","?")[:150]}')

# If SOTP, show segments
segments = a3.get('segments', [])
if segments:
    print(f'\n=== SOTP分部 ===')
    for seg in segments:
        print(f'  {seg.get("segment","?")}: anchor={seg.get("anchor","?")} is_primary={seg.get("is_primary","?")}')

out = f'tmp_test_{record["stock_code"]}.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
print(f'\nSaved: {out}')
