"""2026-06-30 全面巡检 — A-G 完整协议"""
import json, os, glob, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_coze import upsert, list_records

TRACKING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory', 'tracking')
TODAY = '2026-06-30'
PREV_DATE = '2026-06-19'

# Step 0: Coze
print('=== Step 0: Coze ===')
coze_records = list_records()
ACTIVE_CODES = [c for c, r in coze_records.items() if r['track_status'] == 'active']
print(f'Active: {ACTIVE_CODES}')

# Step A: 行情 (2026-06-30)
VALUATION = {
    '300726': {'price': 84.57, 'pe': 79.14, 'mv': 348.29},
    '688323': {'price': 56.50, 'pe': None, 'mv': 101.70},
    '603690': {'price': 35.40, 'pe': None, 'mv': 135.57},
}

# vs 6/19
PREV_PRICES = {'300726': 85.41, '688323': 61.50, '603690': 29.32}

# === 逐标分析 ===
PRICE_NOTES = {
    '300726': (
        "11天高位横盘85.41→84.57(-1.0%)。MV 348.29亿，PE 79.14x。"
        "距7/15 H1预告仅15天。PE 80x附近高位消化，市场在等H1数据验证。"
        "没有新增催化剂——涨价周期持续但已充分定价。"
        "关键看H1预告：民品增速>50%+GM>58%→支撑当前估值；不达预期→PE压缩风险。"
    ),
    '688323': (
        "🔴 11天回调-8.1%（61.50→56.50）。概念炒作开始退潮。MV从110.70→101.70(-8.1%)。"
        "验证了6/19巡检的判断：公司L5澄清'无重要新订单'终将被市场消化。"
        "但56.50仍较6月初~31高+82%——泡沫尚未完全挤出。"
        "GM四连降基本面毫无改善。半年报（8月）是唯一可能改变叙事的事件。"
        "正面：概念退潮→估值回归→赔率改善。当前仍不建议参与。"
    ),
    '603690': (
        "🟢 11天大涨+20.7%（29.32→35.40）！MV 135.57亿(+23.28亿/11天)。"
        "创6个月新高。PE -16.29仍亏损但收窄中。"
        "可能的驱动因素：①半年报前抢跑（Q2订单→收入转化预期）②减持窗口6/18开启后无实质减持→利空出尽"
        "③半导体设备板块整体走强④高纯工艺系统业务季度交付集中。"
        "⚠️ 但Q1营收仅6.21亿(-14.7%)、负债率73%→基本面改善速度能否匹配涨幅存疑。"
        "半年报（8月）硬验证：Q2营收需>8亿才能证明拐点。"
    ),
}

PILLAR_UPDATES = {
    '300726': [
        {"actual": "11天横盘84-85区间。PE 80x高位消化。距H1预告15天。市场等待民品增速+GM硬数据。涨价逻辑已获认可但估值已price in。", "trend": "stable"},
        {"actual": "Q1 GM=60%维持。H1预告将首次验证涨价对毛利率的实际传导效果。", "trend": "stable"},
        {"actual": "KEMET/AVX涨价执行中。供给缺口持续。公司原材料储备α是核心护城河。无新变化。", "trend": "stable"},
        {"actual": "军品营收>81%稳。Q1净利+70.77%。估值底座未变。", "trend": "stable"},
    ],
    '688323': [
        {"actual": "11天-8.1%回调。概念炒作开始退潮——验证了前次巡检判断。从高点61.50→56.50。泡沫在挤出但远未完成(较6月初仍+82%)。", "trend": "down"},
        {"actual": "钟渊提价20%利好。Q1营收+15.9%未加速。涨价传导效果温和。", "trend": "flat"},
        {"actual": "半导体PI小批量供货。PSPI研发中。无新增实质性里程碑。", "trend": "flat"},
        {"actual": "⚠️ 无新进展。公司澄清'无重要新订单'正在被市场消化。概念退潮是健康过程。", "trend": "down"},
    ],
    '603690': [
        {"actual": "11天+20.7%大涨至35.40！MV 135.57亿创6月新高。半年报前抢跑+减持利空出尽。Q2订单→收入转化是关键假设。", "trend": "up"},
        {"actual": "Q1 GM 27.06%。Q2 GM能否>30%是半年报核心验证指标。无新数据。", "trend": "up"},
        {"actual": "制程设备订单8-12亿目标。2025设备收入仅2.86亿→产能爬坡是瓶颈。半年报验证进度。", "trend": "flat"},
        {"actual": "减持窗口6/18已开启11天。若无减持公告→资金面压力边际改善。负债率73%+速动比0.67仍薄。", "trend": "flat"},
    ],
}

NEW_CATALYSTS = {
    '688323': [
        {
            "date": TODAY,
            "event": "概念退潮启动：11天-8.1%回调，验证'公司澄清终将被定价'的判断",
            "type": "市场",
            "impact": "H",
            "bull": "温和退潮→估值回归基本面→PB 4-5x合理区间→为半年报后建仓创造条件",
            "bear": "退潮加速→恐慌性抛售→重回30-40区间→已持有者浮亏扩大",
            "sourceLevel": "L5",
            "sourceDetail": "2026-06-30 交易所行情",
            "sourceNote": "从61.50高点回调至56.50(-8.1%)。概念退潮验证了前两次巡检的预警。泡沫挤出是健康过程。",
            "status": "triggered",
            "lastChecked": TODAY
        }
    ],
    '603690': [
        {
            "date": TODAY,
            "event": "11天+20.7%大涨：半年报前抢跑+减持利空初步消化，半导体设备板块走强",
            "type": "市场",
            "impact": "H",
            "bull": "半年报Q2营收>8亿+GM>30%→确认拐点→估值修复至160-180亿(Base→Bull)",
            "bear": "半年报不达预期→Q2营收<6亿→涨幅全部回吐→重回26-28区间",
            "sourceLevel": "L5",
            "sourceDetail": "2026-06-30 交易所行情",
            "sourceNote": "从29.32→35.40(+20.7%)。驱动待半年报确认。当前涨幅基于预期而非硬数据。",
            "status": "triggered",
            "lastChecked": TODAY
        }
    ],
    '300726': [
        {
            "date": TODAY,
            "event": "PE 80x高位横盘11天：市场消化估值，等待7/15 H1预告",
            "type": "市场",
            "impact": "M",
            "bull": "H1预告全面超预期→PE获基本面支撑→突破90x",
            "bear": "H1预告不及预期→高PE缺乏锚点→回调至65-70",
            "sourceLevel": "L5",
            "sourceDetail": "2026-06-30 交易所行情",
            "sourceNote": "11天横盘84-85区间。7/15 H1预告15天后——分水岭。",
            "status": "pending",
            "lastChecked": TODAY
        }
    ],
}

TENSION = {
    '300726': 'stable',    # 高位横盘等验证，张力趋于中性
    '688323': 'easing',    # 概念退潮→背离修复→张力缓解
    '603690': 'rising',    # 大涨后预期升高→张力上升(预期差风险)
}

CONVICTION_ADJ = {
    '300726': 0,     # 无新信息，横盘等待
    '688323': 0,     # 概念退潮是积极的，但不改变基本面——不调
    '603690': 0,     # 大涨是价格表现，基本面待半年报验证——不调
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
        'date': TODAY,
        'price': v['price'],
        'pe': v['pe'],
        'mv_yi': v['mv'],
        'return_pct': return_pct,
        'mv_change_pct': mv_change,
        'pct_chg_daily': daily_chg,
        'note': f'巡检。{note} | 11日累计: {multi_day_chg:+.1f}%'
    })

    if code in PILLAR_UPDATES:
        for i, update in enumerate(PILLAR_UPDATES[code]):
            if i < len(d['pillars']):
                d['pillars'][i]['history'].append({
                    'date': TODAY,
                    'actual': update['actual'],
                    'trend': update['trend']
                })
                d['pillars'][i]['lastChecked'] = TODAY

    for c in d['catalystCalendar']:
        c['lastChecked'] = TODAY
    if code in NEW_CATALYSTS:
        d['catalystCalendar'].extend(NEW_CATALYSTS[code])
    seen = set()
    uc = []
    for c in d['catalystCalendar']:
        k = c.get('event','') + c.get('date','')
        if k not in seen:
            seen.add(k); uc.append(c)
    d['catalystCalendar'] = uc

    new_conviction = d['conviction'] + CONVICTION_ADJ.get(code, 0)
    if new_conviction != d['conviction']:
        d['conviction'] = new_conviction
        print(f'  Conviction {code}: {d["conviction"]}→{new_conviction}')

    tension = TENSION.get(code, 'stable')
    last_v = max((t.get('version',0) for t in d['thesisLog']), default=0)

    narratives = {
        '300726': (
            f"11天高位横盘84-85区间。MV 348.29亿({return_pct:+.1f}% vs基准)。PE 79.14x。"
            "涨价逻辑已获市场认可，PE 80x定价了相当乐观的预期。距7/15 H1预告仅15天。"
            "当前处于'等待验证'阶段——市场既不继续推高（等数据），也不撤退（逻辑未破）。"
            "H1预告是分水岭：民品增速>50%+GM>58%→PE可支撑；不达预期→高PE缺乏锚点。"
            "张力从rising→stable：横盘意味着叙事与估值达到暂时平衡。"
        ),
        '688323': (
            f"11天-8.1%回调至56.50。MV 101.70亿({return_pct:+.1f}% vs基准)。"
            "概念退潮启动——验证了前两次巡检的预警：公司L5澄清'无重要新订单'终将被市场消化。"
            "从高点61.50→56.50(-8.1%)，泡沫在挤出但远未完成（较6月初31仍+82%）。"
            "GM四连降基本面毫无改善。半年报（8月）是唯一可能提供正面催化的事件。"
            "张力从tension→easing：概念退潮是健康的背离修复过程。"
            "正面信号：市场开始听公司说什么了。"
        ),
        '603690': (
            f"11天+20.7%大涨至35.40。MV 135.57亿({return_pct:+.1f}% vs基准)，创6月新高。"
            "涨幅驱动推测：①半年报前抢跑(Q2订单→收入转化预期)②减持窗口无实质减持→利空消化"
            "③半导体设备板块整体走强。"
            "但Q1营收仅6.21亿(-14.7%)、负债率73%→基本面改善速度能否匹配+20%涨幅存疑。"
            "半年报（8月）硬验证：Q2营收需>8亿+GM>30%才能证明拐点成立。"
            "张力从stable→rising：股价上涨推高了预期——半年报不达标的代价变大。"
        ),
    }

    d['thesisLog'].append({
        'version': last_v+1,
        'date': f'{TODAY}T22:00:00',
        'thesis': d['thesis'],
        'conviction': d['conviction'],
        'delta': note,
        'trigger': '每日巡检',
        'narrative': narratives.get(code, note),
        'verifiedAssumptions': [],
        'invalidatedAssumptions': [],
        'newUnknowns': [],
        'narrativeTension': tension
    })

    d['reviewSchedule']['lastCheck'] = f'{TODAY}(巡检)'
    d['reviewSchedule']['nextQuickCheck'] = '2026-07-01(明日巡检)'

    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    print(f'[OK] {code} {d["stockName"]} | {prev_patrol_price}→{v["price"]} ({multi_day_chg:+.1f}%/11d) | mv={v["mv"]}亿 | tension={tension} | conv={d["conviction"]}')

print('\n=== Coze sync ===')
for code in ACTIVE_CODES:
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches: continue
    ok = upsert(matches[0])
    status = "OK" if ok else "FAIL"
    print(f'[Coze {status}] {code}')
print('=== DONE ===')
