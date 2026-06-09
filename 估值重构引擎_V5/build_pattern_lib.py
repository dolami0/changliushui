"""从42条案例构建结构化传导模式库"""
import json, io, sys, os
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('all_cases_raw.json', encoding='utf-8') as f:
    cases = json.load(f)

patterns = []

for c in cases:
    name = str(c.get('stockName',''))
    code = str(c.get('stockCode',''))
    sector = str(c.get('sector',''))
    g = c.get('gainMultiple',0)
    try: gain = float(g)
    except: gain = 0

    ret_type = str(c.get('returnType',''))
    val_driven = c.get('valuationDriven', False)
    pe_e = c.get('peExpansion') or 0
    pf_e = c.get('profitExpansion') or 0
    gm_i = c.get('gmImprovement') or 0
    roic_i = c.get('roicImprovement') or 0
    s_pe = c.get('startPE')
    p_pe = c.get('peakPE')
    s_mcap = c.get('startMcap') or 0
    p_mcap = c.get('peakMcap') or 0

    driver = str(c.get('primaryDriver',''))
    catalyst = str(c.get('catalyst',''))
    logic = str(c.get('logic',''))
    dom_factor = str(c.get('dominantFactor',''))
    key_signals = str(c.get('keySignals',''))
    failure = str(c.get('failureMode',''))
    tags = str(c.get('tags',''))
    deca_tags = str(c.get('decagenomeTags',''))

    start_date = str(c.get('startDate',''))
    peak_date = str(c.get('peakDate',''))
    t2x = c.get('t2xMonths') or 0
    t5x = c.get('t5xMonths') or 0
    t10x = c.get('t10xMonths') or 0
    max_dd = int(c.get('maxDrawdownPct') or 0)
    asym = c.get('asymmetryRatio') or 0

    expectation_gap = str(c.get('expectationGap',''))
    consensus_bias = str(c.get('consensusBias',''))
    macro_regime = str(c.get('macroRegime',''))
    style_factor = str(c.get('styleFactor',''))

    peer = str(c.get('benchmarkPeerName',''))
    peer_gain = c.get('peerGainMultiple') or 0
    divergence = str(c.get('keyDivergence',''))

    # Anchor shift
    anchor_shift = False
    anchor_from = ''
    anchor_to = ''
    if s_pe is None and p_pe is not None:
        anchor_shift = True
        anchor_from = 'None/亏损'
        anchor_to = 'PE'
    elif s_pe is not None and p_pe is not None and float(pe_e) > 50:
        anchor_shift = True
        anchor_from = 'PE(低)'
        anchor_to = 'PE(高扩张)'
    elif s_pe is None and p_pe is None:
        anchor_from = 'None/亏损'
        anchor_to = 'None/亏损(主题)'
        anchor_shift = True
    elif s_pe is not None and p_pe is not None:
        anchor_from = 'PE'
        anchor_to = 'PE'
        if float(pe_e) > 0:
            anchor_shift = False  # PE内倍数扩张不算范式切换

    # Driver category
    if '技术突破' in driver:
        driver_cat = 'tech_breakthrough'
    elif '业绩拐点' in driver:
        driver_cat = 'earnings_inflection'
    elif '商业模式升级' in driver:
        driver_cat = 'business_model_upgrade'
    elif '景气上行' in driver:
        driver_cat = 'cyclical_upturn'
    else:
        driver_cat = 'composite'

    # Return type
    if ret_type == '利润核弹':
        ret_cat = 'profit_nuke'
        ret_comp = '利润主导(>90%), PE几乎不动或收缩'
    elif ret_type == '戴维斯双击':
        ret_cat = 'davis_double'
        ret_comp = '利润+倍数双轮驱动'
    elif ret_type == '估值锚定重构':
        ret_cat = 'anchor_reconstruction'
        ret_comp = '估值范式切换主导, 利润贡献小或亏损'
    else:
        ret_cat = 'unknown'
        ret_comp = ''

    pattern_id = f'{driver_cat}_{ret_cat}'

    pattern = {
        'pattern_id': pattern_id,
        'stock_code': code,
        'stock_name': name,
        'sector': sector,
        'gain_multiple': gain,
        'return_type': ret_cat,
        'return_type_cn': ret_type,
        'return_composition': ret_comp,
        'driver': driver_cat,
        'driver_cn': driver,
        'dominant_factor': dom_factor,
        'catalyst_summary': catalyst[:300],
        'investment_logic': logic[:500],
        'key_signals': key_signals[:300],
        'failure_mode': failure[:300],
        'tags': tags,
        'decagenome_tags': deca_tags,
        'timeline': {
            'start_date': start_date,
            'peak_date': peak_date,
            'months_to_2x': t2x,
            'months_to_5x': t5x,
            'months_to_10x': t10x,
            'max_drawdown_pct': max_dd,
            'asymmetry_ratio': asym,
        },
        'financial_metrics': {
            'start_pe': s_pe,
            'peak_pe': p_pe,
            'pe_expansion_pct': pe_e,
            'profit_expansion_pct': pf_e,
            'gm_improvement_pp': gm_i,
            'roic_improvement_pp': roic_i,
            'start_mcap_yi': s_mcap,
            'peak_mcap_yi': p_mcap,
        },
        'anchor_shift': {
            'occurred': anchor_shift,
            'from': anchor_from,
            'to': anchor_to,
        },
        'market_context': {
            'expectation_gap': expectation_gap,
            'consensus_bias': consensus_bias,
            'macro_regime': macro_regime,
            'style_factor': style_factor,
        },
        'benchmark': {
            'peer_name': peer,
            'peer_gain': peer_gain,
            'key_divergence': divergence,
        }
    }
    patterns.append(pattern)

with open('pattern_library.json', 'w', encoding='utf-8') as f:
    json.dump(patterns, f, ensure_ascii=False, indent=2)
print(f'Saved: {len(patterns)} patterns')

# Pattern clusters
pid = Counter(p['pattern_id'] for p in patterns)
print('\n=== Pattern clusters ===')
for k,v in pid.most_common():
    samples = [p['stock_name'] for p in patterns if p['pattern_id'] == k][:5]
    print(f'  {k}: {v}条 -> {" ".join(samples)}')

# Aggregate stats per pattern
print('\n=== Aggregate stats ===')
for pid_name in sorted(pid.keys()):
    subset = [p for p in patterns if p['pattern_id'] == pid_name]
    gains = sorted([p['gain_multiple'] for p in subset])
    pe_exp = sorted([p['financial_metrics']['pe_expansion_pct'] for p in subset if p['financial_metrics']['pe_expansion_pct']])
    pf_exp = sorted([p['financial_metrics']['profit_expansion_pct'] for p in subset if p['financial_metrics']['profit_expansion_pct']])
    gm_list = sorted([p['financial_metrics']['gm_improvement_pp'] for p in subset if p['financial_metrics']['gm_improvement_pp']])
    roic_list = sorted([p['financial_metrics']['roic_improvement_pp'] for p in subset if p['financial_metrics']['roic_improvement_pp']])

    # 找出估值驱动的案例
    val_driven_names = []
    for p in subset:
        idx = patterns.index(p)
        if cases[idx].get('valuationDriven'):
            val_driven_names.append(p['stock_name'])

    n = len(subset)
    g_med = gains[n//2] if gains else 0
    pe_m = pe_exp[len(pe_exp)//2] if pe_exp else 0
    pf_m = pf_exp[len(pf_exp)//2] if pf_exp else 0

    print(f'\n[{pid_name}] n={n} gain中位={g_med:.1f}x PE扩张中位={pe_m:.0f}% 利润扩张中位={pf_m:.0f}%')
    print(f'  估值驱动: {len(val_driven_names)}/{n} -> {val_driven_names[:5]}')

    # Driver breakdown
    dc = Counter(p['driver_cn'] for p in subset)
    print(f'  驱动: {" ".join(f"{k}({v})" for k,v in dc.most_common())}')

    # Failure mode summary
    failure_modes = Counter(p['failure_mode'][:50] for p in subset if p['failure_mode'])
    if failure_modes:
        top = failure_modes.most_common(2)
        print(f'  常见失败模式: {" | ".join(f"{k}({v})" for k,v in top)}')

print('\nDone!')
