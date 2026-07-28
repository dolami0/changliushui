"""2026-07-07 全面巡检 — A-G 协议"""
import json, os, glob, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_coze import upsert, list_records

TRACKING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory', 'tracking')
TODAY = '2026-07-07'
PREV_DATE = '2026-06-30'

print('=== Step 0: Coze ===')
coze_records = list_records()
ACTIVE_CODES = [c for c, r in coze_records.items() if r['track_status'] == 'active']
print(f'Active: {ACTIVE_CODES}')

VALUATION = {
    '300726': {'price': 70.66, 'pe': 66.12, 'mv': 291.01},
    '688323': {'price': 38.95, 'pe': None, 'mv': 78.06},
    '603690': {'price': 33.90, 'pe': None, 'mv': 129.82},
}
PREV_PRICES = {'300726': 84.57, '688323': 56.50, '603690': 35.40}

PRICE_NOTES = {
    '300726': (
        "🔴 7天-16.4%（84.57→70.66）。MV 348→291亿(-57亿/7天)。PE 79→66x。"
        "前期PE 80x高位横盘后遭遇获利了结+市场调整。距7/15 H1预告仅8天！"
        "当前回调的性质：①获利了结(从60→85涨了42%，回调16%正常)"
        "②PE 80x→66x赔率改善 ③并非基本面恶化——涨价周期仍在。"
        "H1预告(8天后)是分水岭：若民品>50%+GM>58%→回调是加仓机会；若低于预期→回调只是开始。"
        "较建档基准63.2仍+11.8%。"
    ),
    '688323': (
        "🔴🔴 7天暴跌-31.1%（56.50→38.95）！MV 102→78亿(-24亿/7天)。"
        "概念泡沫加速破裂——验证了连续三次巡检的预警！"
        "从6/19高点61.50→38.95，18天累计-36.7%。6/10公司澄清'无重要新订单'终被市场定价。"
        "GM四连降的悲惨基本面终于被价格反映。"
        "38.95已接近6月初启动位~31。泡沫挤出接近完成但尚未完成。"
        "⚠️ Even now, 38.95 vs 建档基准39.9→仅-2.4%——实际上几乎回到了起点。"
        "正面：赔率大幅改善。但PB仍在4x+，且GM四连降→半年报前无买入理由。"
    ),
    '603690': (
        "-4.2%温和回调（35.40→33.90）。MV 136→130亿(-6亿/7天)。"
        "相对宏达(-16%)和瑞华泰(-31%)，至纯展现了防御性——或只是未涨够就没得跌。"
        "减持窗口6/18已开20天，尚无减持公告→正面。"
        "核心变量未变：8月半年报验证Q2订单→收入转化。"
        "当前较建档基准26.68仍+27.1%。"
    ),
}

PILLAR_UPDATES = {
    '300726': [
        {"actual": "7天-16.4%回调。PE 80x→66x赔率改善。距H1预告8天。涨价逻辑未变，回调性质为获利了结而非基本面恶化。", "trend": "stable"},
        {"actual": "Q1 GM=60%。H1预告将首次验证涨价对GM的实际传导。当前市场在等数据。", "trend": "stable"},
        {"actual": "KEMET/AVX涨价持续。供给缺口不变。原材料储备α是抗跌底座。", "trend": "stable"},
        {"actual": "军品>81%稳。股价回调中军品底座提供基本面支撑。Q1净利+70.77%。", "trend": "stable"},
    ],
    '688323': [
        {"actual": "🔴 7天-31.1%暴跌！18天从高点-36.7%。概念泡沫加速破裂——连续三次巡检的预警获验证。公司L5澄清'无新订单'终被定价。", "trend": "down"},
        {"actual": "钟渊提价20%利好仍在但股价不反应。Q1营收+15.9%未加速。基本面与价格同向回归。", "trend": "flat"},
        {"actual": "半导体PI小批量。PSPI研发中。无新催化。", "trend": "flat"},
        {"actual": "无新进展。概念退潮是唯一驱动力。6/10公司澄清终于被市场听见。赔率在改善。", "trend": "down"},
    ],
    '603690': [
        {"actual": "-4.2%温和回调，相对抗跌。减持窗口第20天无减持公告→正面。核心等8月半年报。", "trend": "stable"},
        {"actual": "Q1 GM 27.06%。Q2 GM>30%是半年报关键。无新数据。", "trend": "flat"},
        {"actual": "制程设备订单8-12亿目标待验证。设备收入占比仅10%→爬坡是瓶颈。", "trend": "flat"},
        {"actual": "减持窗口无减持→边际改善。负债率73%+速动比0.67仍薄但未恶化。", "trend": "flat"},
    ],
}

TENSION = {
    '300726': 'stable',     # 回调是正常修正，H1预告前等待
    '688323': 'easing',     # 概念退潮加速→背离修复→赔率改善
    '603690': 'stable',     # 温和回调，减持窗口平稳
}

# 瑞华泰概念退潮验证了预警→不调conviction（不因价格涨跌调），但叙事张力从tension→easing
# 宏达回调是估值修正→不调
# 至纯无新信息→不调
CONVICTION_ADJ = {'300726': 0, '688323': 0, '603690': 0}

for code in ACTIVE_CODES:
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches:
        print(f'SKIP {code}: file not found')
        continue
    fpath = matches[0]
    with open(fpath, 'r', encoding='utf-8') as f:
        d = json.load(f)

    v = VALUATION[code]
    note = PRICE_NOTES[code]
    base_mv = d.get('baseMarketCap', 0)
    return_pct = round((v['mv'] / base_mv - 1) * 100, 1) if base_mv else 0
    prev_patrol_price = PREV_PRICES.get(code, 0)
    multi_day_chg = round((v['price'] / prev_patrol_price - 1) * 100, 1) if prev_patrol_price else 0
    prev_log = d['priceLog'][-1] if d['priceLog'] else {}
    prev_price = prev_log.get('price', 0)
    daily_chg = round((v['price'] / prev_price - 1) * 100, 2) if prev_price else 0
    prev_mv = prev_log.get('mv_yi', base_mv)
    mv_change = round((v['mv'] - prev_mv) / prev_mv * 100, 1) if prev_mv else 0

    d['priceLog'].append({
        'date': TODAY, 'price': v['price'], 'pe': v['pe'], 'mv_yi': v['mv'],
        'return_pct': return_pct, 'mv_change_pct': mv_change,
        'pct_chg_daily': daily_chg,
        'note': f'巡检。{note} | 7日累计: {multi_day_chg:+.1f}%'
    })

    if code in PILLAR_UPDATES:
        for i, update in enumerate(PILLAR_UPDATES[code]):
            if i < len(d['pillars']):
                d['pillars'][i]['history'].append({'date': TODAY, 'actual': update['actual'], 'trend': update['trend']})
                d['pillars'][i]['lastChecked'] = TODAY

    for c in d['catalystCalendar']:
        c['lastChecked'] = TODAY

    tension = TENSION.get(code, 'stable')
    last_v = max((t.get('version', 0) for t in d['thesisLog']), default=0)

    narratives = {
        '300726': (
            f"7天-16.4%回调至70.66。MV 291.01亿({return_pct:+.1f}% vs基准)。PE 66.12x。"
            "前期PE 80x高位横盘后遭遇获利了结。距7/15 H1预告仅8天——最关键分水岭。"
            "回调性质：PE从80x→66x是估值修正而非基本面恶化。涨价周期仍在，原材料储备α未变。"
            "若H1预告验证民品>50%+GM>58%→回调是加仓机会(PE 66x回到80x=+21%仅估值修复)。"
            "若H1预告不及预期→PE可能压缩至50-55x→进一步回调至60-65区间。"
            "8天后见分晓。当前赔率比6/30(PE 80x)显著改善。"
        ),
        '688323': (
            f"7天暴跌-31.1%至38.95。MV 78.06亿({return_pct:+.1f}% vs基准)。"
            "18天从高点61.50-36.7%。概念泡沫加速破裂——连续三次巡检预警获市场验证。"
            "6/10公司L5澄清'无重要新订单'→6/15巡检警告背离→6/19警告极端→6/30确认退潮→7/7加速崩塌。"
            "38.95仅较建档基准39.9低2.4%——几乎回到起点，泡沫挤出接近完成。"
            "正面：赔率从极差→中性。半年报GM≥20%是唯一可能的正面催化。"
            "教训：当L5公告与价格方向相反时，L5终将胜出。这个原则再次得到验证。"
        ),
        '603690': (
            f"-4.2%至33.90。MV 129.82亿({return_pct:+.1f}% vs基准)。"
            "相对抗跌——减持窗口第20天无减持公告。核心等8月半年报验证Q2营收转化。"
            "负债率73%+速动比0.67仍薄。不增不减，耐心等待。"
        ),
    }

    d['thesisLog'].append({
        'version': last_v + 1, 'date': f'{TODAY}T22:00:00',
        'thesis': d['thesis'], 'conviction': d['conviction'],
        'delta': note, 'trigger': '每日巡检',
        'narrative': narratives.get(code, note),
        'verifiedAssumptions': [], 'invalidatedAssumptions': [], 'newUnknowns': [],
        'narrativeTension': tension
    })

    d['reviewSchedule']['lastCheck'] = f'{TODAY}(巡检)'
    d['reviewSchedule']['nextQuickCheck'] = '2026-07-08(明日巡检)'

    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    print(f'[OK] {code} {d["stockName"]} | {prev_patrol_price}→{v["price"]} ({multi_day_chg:+.1f}%/7d) | mv={v["mv"]}亿 | tension={tension} | conv={d["conviction"]}')

print('\n=== Coze sync ===')
for code in ACTIVE_CODES:
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches: continue
    ok = upsert(matches[0])
    status = "OK" if ok else "FAIL"
    print(f'[Coze {status}] {code}')
print('=== DONE ===')
