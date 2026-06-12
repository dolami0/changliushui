"""批量巡检脚本 — A-G 协议 Step A→B→C→D→E→G

重要变更：Coze 表格是 track_status 的 source of truth。
巡检前必须从 Coze 读取状态，只巡检 Coze 中 active 的标的。
"""
import json, os, glob, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_coze import upsert, list_records

TRACKING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory', 'tracking')

# Step 0: 从 Coze 读取真实状态（source of truth）
print('=== Step 0: 从 Coze 读取 track_status ===')
coze_records = list_records()

# 筛选 active 标的
ACTIVE_CODES = [code for code, r in coze_records.items() if r['track_status'] == 'active']
print(f'\nActive: {len(ACTIVE_CODES)} stocks: {ACTIVE_CODES}')
print(f'Paused: {[c for c,r in coze_records.items() if r["track_status"]=="paused"]}')

# 同步 Coze track_status 到本地 JSON（Coze → local）
for code, r in coze_records.items():
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches:
        continue
    fpath = matches[0]
    with open(fpath, 'r', encoding='utf-8') as f:
        d = json.load(f)
    local_status = d.get('track_status', '')
    if local_status != r['track_status']:
        d['track_status'] = r['track_status']
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        print(f'[SYNC] {code} {d["stockName"]}: local [{local_status}] → Coze [{r["track_status"]}] 已对齐')

VALUATION = {
    '300726': {'date':'20260612','price':60.34,'pe':61.94,'mv':248.50},
    '603690': {'date':'20260612','price':26.68,'pe':None,'mv':102.17},
    '688323': {'date':'20260612','price':43.10,'pe':None,'mv':77.58},
    '688787': {'date':'20260612','price':153.83,'pe':657.54,'mv':92.83},
}

PATROL_NOTES = {
    '300726': (
        "MLCC炒作退潮-6.3%。6/12再次澄清MLCC体量极小。"
        "股价从高点79.92→60.34(-24.5%)。钽电容涨价周期持续(AVX+KEMET)。"
        "PE从82x→62x赔率修复。民品MLCC仅占11%。"
    ),
    '603690': (
        "建档次日。今日-6.25%主力净流出5848万。"
        "减持窗口6/18-9/17临近。等8月半年报。"
    ),
    '688323': (
        "5日涨+45%(概念炒作:玻璃基板/先进封装)。"
        "6/10异常波动公告:公司自认[目前没有重要新增订单]。"
        "TPI突破打破国外专利壁垒。半导体PI小批量供货韩国。CPI送样。"
    ),
    '688787': (
        "AI数据要素政策催化持续。7月首批算法备案名单临近。"
        "MV+10.4%。等8月半年报验证GM+OCF改善。"
    ),
}

PILLAR_UPDATES = {
    '300726': [
        {"actual": "MLCC炒作退潮，6/12再澄清MLCC极小(仅11%)。钽电容涨价逻辑持续，PE回至62x。非钽业务占比升至66%。", "trend": "stable"},
        {"actual": "Q1 GM=60%维持高位，稳如预期。MLCC退潮≠基本面恶化。", "trend": "stable"},
        {"actual": "KEMET高端+50-65%涨价已执行。钽电容供不应求持续。公司原材料储备优势未变。", "trend": "up"},
        {"actual": "军品营收>81%，Q1+70.77%。十三五百订单锁定，稳。", "trend": "stable"},
    ],
    '603690': [
        {"actual": "Q1订单19.77亿(翻倍级)，Q1营收仅6.21亿(-14.7%)。订单→收入转化待Q2验证。6/12大跌-6.25%。", "trend": "flat"},
        {"actual": "Q1 GM 27.06%(vs 2025FY 22.76%)，改善趋势中。Q2是关键。", "trend": "up"},
        {"actual": "2025设备收入2.86亿(10%)。2026制程设备订单目标8-12亿，待确认转化。", "trend": "flat"},
        {"actual": "负债率73.05%三连升。OCF Q1 -0.30亿(较2025FY -4.30亿收窄)。速动比0.67四连降。财务仍紧张。", "trend": "down"},
    ],
    '688323': [
        {"actual": "6/10异常波动公告:公司自认无重要新增订单。深圳9条线利用率86.2%，嘉兴5条已投产利用率~70%。GM四连降未改。", "trend": "flat"},
        {"actual": "钟渊4月提价20%确认。公司无新增订单公告。股价5日+45%系概念炒作(玻璃基板/先进封装)，与基本面无关。", "trend": "flat"},
        {"actual": "半导体PI已通过韩国企业评测(非三星)小批量供货。PSPI初期研发，与中芯国际无合作。", "trend": "flat"},
        {"actual": "无新进展。公司澄清玻璃基板封装暂未应用。新增6G概念。", "trend": "flat"},
    ],
    '688787': [
        {"actual": "Q1 GM=56.4%回升(季节性)。综合GM从FY2025 48.1%改善趋势待半年报确认。", "trend": "up"},
        {"actual": "Q1 ToG合同+100%。6/8国家数据局政策+L5算法备案新规。7月首批备案名单待公布。", "trend": "up"},
        {"actual": "FY2025 OCF同比-93.8%。H1改善情况待半年报验证。ToG业务回款仍是核心风险。", "trend": "flat"},
        {"actual": "FY2025语音1.50亿(-8.7%)，GM 75.5%支撑利润。降幅是否收窄待H1验证。", "trend": "down"},
        {"actual": "6/8算法备案新规已发布(L5)。7月首批名单。政策→订单转化周期3-6月。", "trend": "up"},
    ],
}

NEW_CATALYSTS = {
    '688323': [
        {
            "date": "2026-06-10",
            "event": "异常波动公告:公司自认[目前没有重要新增订单]",
            "type": "公司",
            "impact": "H",
            "bull": "概念炒作退潮→股价回归基本面",
            "bear": "无实质订单+炒作破灭→恐慌抛售",
            "sourceLevel": "L5",
            "sourceDetail": "2026-06-10 异常波动公告",
            "sourceNote": "公司主动澄清，是L5级信号。股价5日+45%后公司说无订单→炒作风险。",
            "status": "triggered",
            "lastChecked": "2026-06-12"
        },
        {
            "date": "2026-06-12",
            "event": "TPI薄膜突破打破国外专利壁垒+CPI送样折叠屏",
            "type": "公司",
            "impact": "M",
            "bull": "TPI订单规模持续提升→贡献增量收入",
            "bear": "送样阶段→批量销售周期不确定",
            "sourceLevel": "L4",
            "sourceDetail": "2025年报+互动平台回复",
            "sourceNote": "渐进式进展，短期收入贡献有限",
            "status": "pending",
            "lastChecked": "2026-06-12"
        }
    ],
}

TENSION = {
    '300726': 'rising',
    '603690': 'stable',
    '688323': 'easing',
    '688787': 'stable',
}

for code in ACTIVE_CODES:
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches:
        print(f'SKIP {code}: file not found')
        continue

    fpath = matches[0]
    with open(fpath, 'r', encoding='utf-8') as f:
        d = json.load(f)

    v = VALUATION[code]
    note = PATROL_NOTES[code]
    base_mv = d.get('baseMarketCap', 0)
    return_pct = round((v['mv'] / base_mv - 1) * 100, 1) if base_mv else 0

    # === B: priceLog ===
    prev_log = d['priceLog'][-1] if d['priceLog'] else {}
    prev_mv = prev_log.get('mv_yi', base_mv)
    mv_change = round((v['mv'] - prev_mv) / prev_mv * 100, 1) if prev_mv else 0

    d['priceLog'].append({
        'date': '2026-06-12',
        'price': v['price'],
        'pe': v['pe'],
        'mv_yi': v['mv'],
        'return_pct': return_pct,
        'mv_change_pct': mv_change,
        'note': f'巡检。{note}'
    })

    # === C: pillars ===
    if code in PILLAR_UPDATES:
        for i, update in enumerate(PILLAR_UPDATES[code]):
            if i < len(d['pillars']):
                d['pillars'][i]['history'].append({
                    'date': '2026-06-12',
                    'actual': update['actual'],
                    'trend': update['trend']
                })
                d['pillars'][i]['lastChecked'] = '2026-06-12'

    # === D: catalysts ===
    for c in d['catalystCalendar']:
        c['lastChecked'] = '2026-06-12'

    if code in NEW_CATALYSTS:
        d['catalystCalendar'].extend(NEW_CATALYSTS[code])

    # Deduplicate catalysts by event name
    seen = set()
    unique_catalysts = []
    for c in d['catalystCalendar']:
        key = c.get('event', '') + c.get('date', '')
        if key not in seen:
            seen.add(key)
            unique_catalysts.append(c)
    d['catalystCalendar'] = unique_catalysts

    # === E: thesisLog ===
    last_v = max((t.get('version', 0) for t in d['thesisLog']), default=0)
    d['thesisLog'].append({
        'version': last_v + 1,
        'date': '2026-06-12T22:00:00',
        'thesis': d['thesis'],
        'conviction': d['conviction'],
        'delta': note,
        'trigger': '每日巡检',
        'narrative': note,
        'verifiedAssumptions': [],
        'invalidatedAssumptions': [],
        'newUnknowns': [],
        'narrativeTension': TENSION.get(code, 'stable')
    })

    # reviewSchedule
    d['reviewSchedule']['lastCheck'] = '2026-06-12(巡检)'
    d['reviewSchedule']['nextQuickCheck'] = '2026-06-13(明日巡检)'

    # Write back
    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    print(f'[UPDATED] {code} {d["stockName"]} | price={v["price"]} | mv={v["mv"]}亿 | return={return_pct}% | tension={TENSION.get(code,"?")}')

print('\n=== All local files updated. Starting Coze sync ===')

# === G: Coze sync ===
for code in ACTIVE_CODES:
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches:
        continue
    ok = upsert(matches[0])
    status = 'OK' if ok else 'FAIL'
    print(f'[Coze {status}] {code}')

print('\n=== Patrol complete ===')
