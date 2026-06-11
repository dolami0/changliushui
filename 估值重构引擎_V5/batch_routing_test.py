"""Batch test routing decisions for multiple stocks — only up to Agent-2b."""
import sys, os, json, time, requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'valuation_app'))
os.chdir(os.path.dirname(__file__))

from env_config import DEEPSEEK_API_KEY, COZE_SAT_TOKEN
from data_fetcher import DataFetcher
from agent0_pre_router import Agent0
from agent1_data_forge import DataForge
from agent2a_narrative import NarrativeDiagnosis
from agent2b_routing import RouteJudgeV6
from pre_screen_gate import PreScreenGate

# Fetch all stocks from Coze
url = 'https://api.coze.cn/v1/databases/7644911309938589711/records/query'
headers = {'Authorization': f'Bearer {COZE_SAT_TOKEN}', 'Content-Type': 'application/json'}
resp = requests.post(url, headers=headers, json={'page_num': 1, 'page_size': 50, 'is_async': False}, timeout=15)
items = resp.json().get('data', {}).get('items', [])

# Pick diverse stocks — deduplicate by code (Coze may have multiple records)
targets = ['688720', '688313', '300617', '688627', '300726']

results = []
seen = set()
for item in items:
    code = item.get('stock_code', '')
    if code not in targets:
        continue
    if code in seen:
        continue
    seen.add(code)

    name = item.get('stock_name', '')
    a0_raw = item.get('agent0_json', '{}')
    a0 = json.loads(a0_raw) if isinstance(a0_raw, str) else a0_raw

    event_data = {
        'stock_code': code,
        'stock_name': name,
        'raw_event_text': a0.get('raw_event_text', ''),
        'event_deduction': a0.get('event_deduction', ''),
        'investment_theme': a0.get('investment_theme', ''),
        'adversarial_thinking': a0.get('adversarial_thinking', ''),
        'knowledge_supplement': a0.get('knowledge_supplement', ''),
        'preliminary_reasoning': a0.get('preliminary_reasoning', ''),
        'industry_expert_research': a0.get('industry_expert_research', ''),
        'future': a0.get('future', ''),
    }

    print(f'\n{"="*60}')
    print(f'{code} {name}')
    print(f'{"="*60}')

    t0 = time.time()

    # Agent-0
    a0_agent = Agent0()
    a0_out = a0_agent.run(code, event_data)
    pre_routing = a0_out.get('pre_routing_result', {})
    industry = pre_routing.get('industry_classification', '?')
    print(f'  [A0] industry={industry} ({time.time()-t0:.0f}s)')

    # Agent-1 (pass pre_routing_result directly, same as orchestrator)
    t1 = time.time()
    forge = DataForge()
    try:
        a1_out = forge.run(pre_routing)
    except Exception as e:
        print(f'  [A1] ERROR: {e}')
        continue
    if not isinstance(a1_out, dict):
        print(f'  [A1] ERROR: DataForge returned {type(a1_out).__name__}')
        continue
    core = a1_out.get('packages', {}).get('core', {}).get('fields', {})
    mcap = core.get('market_cap_yi', 0)
    roic = core.get('roic_pct', 0)
    nopat = core.get('nopat_yi', 0)
    ps = core.get('ps_ttm', 0)
    pe = core.get('pe_ttm', 0)
    quality = a1_out.get('overall_data_quality_score', '?')
    print(f'  [A1] mcap={mcap:.0f}yi ROIC={roic:.1f}% NOPAT={nopat:.2f}yi PS={ps:.1f}x PE={pe:.0f}x quality={quality} ({time.time()-t1:.0f}s)')

    # Pre-screen
    t1 = time.time()
    ps_gate = PreScreenGate()
    ps_result = ps_gate.run(event_data=event_data, agent1_output=a1_out, stock_code=code)
    passed = ps_result.passed
    print(f'  [PreScreen] {"PASS" if passed else "CUT"} score={ps_result.total_score}/40 ({time.time()-t1:.0f}s)')

    if not passed:
        print(f'  [SKIP] Pre-screen cut: {ps_result.cut_reason}')
        results.append({'code': code, 'name': name, 'status': 'cut', 'reason': ps_result.cut_reason})
        continue

    # Agent-2a (WACC not critical for routing, use defaults)
    t1 = time.time()
    wacc_params = {'wacc_pct': 10, 'rf_pct': 2.5, 'beta': 1.0, 'erp_pct': 6.5, 're_pct': 9, 'rd_pct': 3.5, 'd_ratio_pct': 20, 'rf_source': 'default', 'beta_source': 'default', 'erp_method': 'default', 'note': 'batch test'}
    a2a = NarrativeDiagnosis(deepseek_key=DEEPSEEK_API_KEY)
    a2a_out = a2a.run(a1_out, event_data, wacc_params)
    mn = a2a_out.get('market_narrative', {})
    fwd = a2a_out.get('forward_to_routing', {})
    anchor = mn.get('primary_anchor', '?')
    family = fwd.get('model_family_constraint', '?')
    sotp = mn.get('sotp_triggered', False)
    dist = fwd.get('distribution_shape', '?')
    print(f'  [A2a] anchor={anchor} family={family} sotp={sotp} dist={dist} ({time.time()-t1:.0f}s)')

    # Agent-2b
    t1 = time.time()
    a2b = RouteJudgeV6(deepseek_key=DEEPSEEK_API_KEY)
    a2b_out = a2b.run(a1_out, a2a_out, event_data, volc_data=None)
    rd = a2b_out.get('routing_decision', {})
    primary = rd.get('primary_model', '?')
    cat = rd.get('model_category', '?')
    valid = rd.get('validation_models', [])
    override = rd.get('constraint_compliance', {}).get('constraint_override', False)
    blocked = rd.get('_k_blocked_by_code', False)
    reason = rd.get('routing_reason', '')[:200]
    nopat_ratio = nopat / max(mcap, 1) * 100
    print(f'  [A2b] model={primary}({cat}) valid={valid} override={override} K_blocked={blocked} ({time.time()-t1:.0f}s)')
    print(f'  [A2b] NOPAT/mcap={nopat_ratio:.2f}%')
    print(f'  [A2b] reason: {reason}')

    results.append({
        'code': code, 'name': name,
        'mcap': mcap, 'roic': roic, 'nopat': nopat, 'ps': ps, 'pe': pe,
        'nopat_ratio': nopat_ratio,
        'anchor': anchor, 'family': family, 'sotp': sotp,
        'model': primary, 'category': cat, 'override': override, 'k_blocked': blocked,
    })

print(f'\n{"="*60}')
print('SUMMARY')
print(f'{"="*60}')
print(f'{"Code":<8} {"Name":<12} {"MCap":>6} {"ROIC":>6} {"NOPAT":>6} {"NOPAT%":>7} {"Anchor":<10} {"Family":<20} {"Model":>5} {"KBlocked":>8}')
print('-' * 105)
for r in results:
    if r.get('status') == 'cut':
        print(f'{r["code"]:<8} {r["name"]:<12} {"CUT: " + r.get("reason","")[:30]}')
    else:
        print(f'{r["code"]:<8} {r["name"]:<12} {r["mcap"]:>5.0f}yi {r["roic"]:>5.1f}% {r["nopat"]:>5.2f}yi {r["nopat_ratio"]:>6.2f}% {r["anchor"]:<10} {r["family"]:<20} {r["model"]:>5} {str(r["k_blocked"]):>8}')

# Save results
with open('tmp_routing_test.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f'\nSaved: tmp_routing_test.json')
