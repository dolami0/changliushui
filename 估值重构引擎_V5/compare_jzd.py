import json

with open('reports/data/688627_20260527_1908.json', encoding='utf-8') as f:
    r1 = json.load(f)
with open('reports/data/688627_20260528_0027.json', encoding='utf-8') as f:
    r2 = json.load(f)

def extract(d, label):
    a3 = d.get('agent3', {})
    sv = a3.get('scenario_valuation', {})
    vs = a3.get('valuation_summary', sv)
    details = sv.get('scenario_details', {})
    if isinstance(details, list):
        details = {x.get('scenario', ''): x for x in details}
    a2 = d.get('agent2', {})
    rd = a2.get('routing_decision', {})
    a2a = d.get('agent2a', {})

    lines = [f'=== {label} ===']
    lines.append(f'version: {d.get("pipeline_version", "?")}  has_agent2a: {bool(a2a)}')

    for s in ('bear', 'base', 'bull'):
        sc = details.get(s, {})
        p = sc.get('probability', 0)
        u = sc.get('upside_pct', 0)
        m = sc.get('target_mcap_yi', 0)
        lines.append(f'{s}: p={p:.0%} u={u:+.1f}% m={m:.0f}yi')

    w = vs.get('probability_weighted_upside_pct', 0)
    a = vs.get('asymmetry_ratio', 0)
    lines.append(f'weighted: {w:+.1f}%  asym: {a:.1f}x')

    conf = a3.get('confidence', {})
    ta = a3.get('trade_annotation', {})
    lines.append(f'conf: {conf.get("overall_score", "?")}/10  tier: {ta.get("tier", "?")}')
    lines.append(f'model: {rd.get("primary_model", "?")} ({rd.get("model_category", "?")})')
    lines.append(f'route: {rd.get("routing_reason", "?")[:250]}')

    if a2a:
        mn = a2a.get('market_narrative', {})
        ep = a2a.get('event_pricing', {}).get('event_profile', {})
        pa = a2a.get('event_pricing', {}).get('pricing_assessment', {})
        sa = a2a.get('signal_audit', {})
        lines.append(f'[2a] anchor: {mn.get("primary_anchor", "?")}  sotp: {mn.get("sotp_triggered", False)}')
        lines.append(f'[2a] spectrum: {ep.get("distribution_shape", "?")}  T={ep.get("timing_certainty", "?")}  B={ep.get("outcome_binaryness", "?")}  P={ep.get("precedent_richness", "?")}')
        lines.append(f'[2a] priced: {pa.get("overall_priced_in", "?")} ({pa.get("priced_in_estimate", "?")})  step2d: {sa.get("step2d_score", "?")}')

    rt = a3.get('reasoning_trace', [])
    lines.append(f'reasoning: {len(rt)} items')
    for t in rt[:6]:
        lines.append(f'  {t[:200]}')
    lines.append('')
    return '\n'.join(lines)

result = extract(r1, 'V5 (20260527_1908)') + '\n' + extract(r2, 'V6 (20260528_0027)')
with open('docs/jingzhida_compare.txt', 'w', encoding='utf-8') as f:
    f.write(result)
print('Saved to docs/jingzhida_compare.txt')
