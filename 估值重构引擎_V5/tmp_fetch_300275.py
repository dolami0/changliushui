"""Fetch 300275 梅安森 latest record from Coze"""
import json, requests

url = 'https://api.coze.cn/v1/databases/7644911309938589711/records/query'
headers = {'Authorization': 'Bearer sat_UxIpTimxUFwh0BGedY1yxK7YJbqrqryebdRVyt8AjducYxsH8cFkkso6Orh2RTGc', 'Content-Type': 'application/json'}
resp = requests.post(url, headers=headers, json={'page_num': 1, 'page_size': 50, 'is_async': False}, timeout=15)
items = resp.json().get('data', {}).get('items', [])

for item in items:
    if item.get('stock_code') == '300275':
        a0 = json.loads(item.get('agent0_json','{}')) if isinstance(item.get('agent0_json'), str) else item.get('agent0_json',{})
        print('=== Agent-0 ===')
        print(f"stock_name: {item.get('stock_name')}")
        print(f"bstudio_create_time: {item.get('bstudio_create_time','?')[:19]}")
        print(f"event_source: {a0.get('event_source','?')}")
        print(f"response_level: {a0.get('response_level','?')}")
        print(f"\nevent_deduction:\n{a0.get('event_deduction','?')}")
        print(f"\ninvestment_theme:\n{a0.get('investment_theme','?')}")
        print(f"\nadversarial_thinking:\n{a0.get('adversarial_thinking','?')}")
        print(f"\nraw_event_text (first 500):\n{a0.get('raw_event_text','?')[:500]}")

        # V5 result
        v5_raw = item.get('agent_v5_json','{}')
        v5 = json.loads(v5_raw) if isinstance(v5_raw, str) else v5_raw
        if v5 and isinstance(v5, dict):
            print('\n=== V5 Result ===')
            print(f"status: {v5.get('status','?')}")

            # Pre-screen
            ps = v5.get('pre_screen', {})
            if ps:
                print(f"pre_screen: passed={ps.get('passed','?')} reason={ps.get('reason','?')[:200]}")

            a2a = v5.get('agent2a', {})
            a2b = v5.get('agent2b', {})
            a3 = v5.get('agent3', {}) or v5.get('agent3s', {})

            print(f"\n2a anchor: {a2a.get('anchor_diagnosis',{}).get('primary_anchor','?')}")
            print(f"2a SOTP trigger: {a2a.get('anchor_diagnosis',{}).get('sotp_triggered','?')}")
            print(f"2a SOTP reason: {a2a.get('anchor_diagnosis',{}).get('sotp_reason','?')[:300]}")

            rd = a2b.get('routing_decision', {})
            print(f"\n2b model: {rd.get('primary_model','?')}")
            print(f"2b reason: {rd.get('routing_reason','?')[:300]}")
            print(f"2b SOTP model: {rd.get('sotp_primary_segment_model','?')}")

            vs = a3.get('valuation_summary', {})
            sv = a3.get('scenario_valuation', {})
            print(f"\nweighted_upside: {vs.get('probability_weighted_upside_pct','?')}%")
            print(f"asymmetry_ratio: {vs.get('asymmetry_ratio','?')}")

            # SOTP segments
            segs = a3.get('segments', [])
            if segs:
                print(f"\nSOTP segments ({len(segs)}):")
                for seg in segs:
                    print(f"  {seg.get('segment','?')}: anchor={seg.get('anchor','?')} model={seg.get('model','?')} is_primary={seg.get('is_primary','?')}")
                    print(f"    revenue_yi={seg.get('revenue_yi','?')} net_profit_yi={seg.get('net_profit_yi','?')} net_assets_yi={seg.get('net_assets_yi','?')}")
                    print(f"    target_mcap_yi={seg.get('target_mcap_yi','?')} value_per_share={seg.get('value_per_share','?')}")

            # scenario details
            sd = sv.get('scenario_details', {})
            for sn in ('bear','base','bull'):
                d = sd.get(sn, {})
                if isinstance(d, dict):
                    print(f"\n{sn}: prob={d.get('probability','?')} mcap={d.get('target_mcap_yi','?')} upside={d.get('upside_pct','?')}%")
                    print(f"  narrative: {d.get('scenario_narrative','?')[:300]}")
                    if 'stage1_growth_pct' in d:
                        print(f"  K params: growth={d.get('stage1_growth_pct','?')}% y={d.get('stage1_years','?')} roic={d.get('roic_assumed_pct','?')}% term_pe={d.get('terminal_pe','?')}")
                    elif 'revenue_growth_3y_cagr_pct' in d:
                        print(f"  B params: cagr={d.get('revenue_growth_3y_cagr_pct','?')}% ps={d.get('target_ps','?')}")
                    elif 'target_pb' in d:
                        print(f"  H params: pb={d.get('target_pb','?')} discount={d.get('nav_discount_pct','?')}%")
