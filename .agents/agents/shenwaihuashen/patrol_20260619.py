"""2026-06-19 全面巡检 — A-G 完整协议"""
import json, os, glob, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_coze import upsert, list_records

TRACKING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory', 'tracking')
TODAY = '2026-06-19'
PREV_DATE = '2026-06-15'

# Step 0: Coze source of truth
print('=== Step 0: Coze ===')
coze_records = list_records()
ACTIVE_CODES = [c for c, r in coze_records.items() if r['track_status'] == 'active']
print(f'Active: {ACTIVE_CODES}')

# Step A: 行情 (2026-06-19)
VALUATION = {
    '300726': {'date': TODAY, 'price': 85.41, 'pe': 79.92, 'mv': 351.75},
    '688787': {'date': TODAY, 'price': 159.39, 'pe': 434.10, 'mv': 96.15},
    '688323': {'date': TODAY, 'price': 61.50, 'pe': None, 'mv': 110.70},
    '603690': {'date': TODAY, 'price': 29.32, 'pe': None, 'mv': 112.29},
}

# 与上次巡检 (6/15) 对比
PREV_PRICES = {
    '300726': 72.41, '688787': 154.90, '688323': 49.62, '603690': 27.51
}

# === 今日分析 ===
PRICE_NOTES = {
    '300726': (
        "延续强势！6/15涨停→6/16-19四天从72.41→85.41，累计再+18.0%。"
        "MV 351.75亿(+53.35亿/4天)。PE 67.76→79.92逼近80x。"
        "距前期高点79.92现已超越+6.9%。6/15涨停非一日游→逻辑重估确认。"
        "钽电容涨价逻辑持续获市场认可。距7/15 H1预告仅26天。"
        "⚠️ PE逼近80x，赔率空间快速压缩。估值扩张>基本面兑现速度。"
    ),
    '688787': (
        "+2.9%稳步上行。MV 96.15亿，温和修复。"
        "7月算法备案名单公布在即（核心催化）。"
        "当前较建档基准+15.3%，市场在提前定价备案预期。"
    ),
    '688323': (
        "🔴🔴 4天再涨+23.9%（49.62→61.50）！距6/10公司澄清'无重要新增订单'仅9天，"
        "股价从~31→61.50，10日暴涨+98%。MV 110.70亿（从77.58→110.70，+42.7%/4天）。"
        "⚠️⚠️ 概念炒作已达极端水平：公司L5公告自行否认有实质订单，"
        "但股价仍在概念驱动下近乎翻倍。GM四连降基本面毫无改善。"
        "这是典型的'公司说没有，市场说有'的背离——历史反复证明公司说对。"
        "概念退潮后的回调风险正在指数级积累。"
    ),
    '603690': (
        "+6.6%延续温和反弹。MV 112.29亿。"
        "减持窗口已于6/18（昨天）开启！需密切关注："
        "①是否有减持公告（接下来1-2周最关键）"
        "②减持量级与占总股本比例"
        "半年报8月才是硬验证。减持窗口期+半年报前=双风险叠加。"
    ),
}

# === Pillar 更新 ===
PILLAR_UPDATES = {
    '300726': [
        {"actual": "6/15涨停→四天再+18%至85.41。涨停非一日游→涨价逻辑获市场持续认可。距7/15 H1预告26天。PE 79.92x已偏高。", "trend": "up"},
        {"actual": "Q1 GM=60%维持。涨价逻辑推升估值但GM硬数据要等H1。PE 80x已price in相当乐观预期。", "trend": "stable"},
        {"actual": "KEMET/AVX涨价执行中。钽电容供给缺口持续。公司原材料储备α是核心护城河。", "trend": "up"},
        {"actual": "军品营收>81%稳。Q1净利+70.77%。估值底座未变。", "trend": "stable"},
    ],
    '688787': [
        {"actual": "+2.9%温和上行。AI数据要素叙事稳固。7月备案+8月半年报双验证格局不变。", "trend": "up"},
        {"actual": "ToG合同+100%持续。7月首批名单即将公布（最强催化）。", "trend": "up"},
        {"actual": "OCF改善待半年报。ToG回款季节性特征，H1数据关键。无新变化。", "trend": "flat"},
        {"actual": "智能语音萎缩趋势未改。GM 75.5%支撑利润。H1验证拐点。", "trend": "down"},
        {"actual": "6/8算法备案新规余温。7月名单公布窗口临近。", "trend": "up"},
    ],
    '688323': [
        {"actual": "🔴 四天再+23.9%至61.50！10日累涨+98%。公司6/10澄清'无重要新增订单'后股价仍翻倍。概念炒作(玻璃基板/先进封装/6G)与基本面完全脱节。GM四连降未改。", "trend": "flat"},
        {"actual": "钟渊提价20%利好仍在。但Q1营收仅+15.9%未加速→涨价未驱动营收实质性起飞。", "trend": "flat"},
        {"actual": "半导体PI小批量供货中。PSPI初期研发。无新增验证节点。嘉兴二期规划中。", "trend": "flat"},
        {"actual": "⚠️ 无实际进展。公司自行否认玻璃基板/6G实质应用。概念炒作是唯一驱动力。", "trend": "flat"},
    ],
    '603690': [
        {"actual": "+6.6%温和反弹。减持窗口6/18已开启！需密切监控减持公告。Q1订单19.77亿→Q2收入转化是核心。", "trend": "flat"},
        {"actual": "Q1 GM 27.06%缓慢改善。Q2 GM能否>30%是关键阈值。无新数据。", "trend": "up"},
        {"actual": "制程设备订单8-12亿目标待验证。2025设备收入仅2.86亿(10%)→产能爬坡是瓶颈。", "trend": "flat"},
        {"actual": "负债率73.05%三连升。速动比0.67四连降。减持窗口已开启→资金面双压。", "trend": "down"},
    ],
}

# === 催化剂更新 ===
NEW_CATALYSTS = {
    '300726': [
        {
            "date": TODAY,
            "event": "四连涨+18%：涨停非一日游，钽电容涨价逻辑获市场持续重估，PE逼近80x",
            "type": "市场",
            "impact": "H",
            "bull": "PE修复至85-90x→市场将2-3年涨价周期定价→MV>370亿",
            "bear": "PE 80x已透支乐观预期→H1预告若不达预期→回调30%+",
            "sourceLevel": "L5",
            "sourceDetail": "2026-06-19 交易所行情",
            "sourceNote": "6/15涨停后四天再+18%至85.41。MV 351.75亿(+53亿/4天)。距7/15 H1预告26天。PE 80x已price in相当乐观预期。",
            "status": "triggered",
            "lastChecked": TODAY
        }
    ],
    '688323': [
        {
            "date": TODAY,
            "event": "10日暴涨+98%：公司澄清'无重要新订单'9天后股价翻倍，概念炒作极端化",
            "type": "市场",
            "impact": "H",
            "bull": "市场认定TPI突破叙事→无视公司澄清→PE持续扩张",
            "bear": "概念退潮→股价从61.5腰斩回30+区间→回归基本面定价",
            "sourceLevel": "L5",
            "sourceDetail": "2026-06-19 交易所行情 + 6/10公司澄清公告",
            "sourceNote": "🔴 极端背离：公司L5公告自认无实质订单，股价10日暴涨+98%。GM四连降。风险指数级积累。",
            "status": "triggered",
            "lastChecked": TODAY
        }
    ],
    '603690': [
        {
            "date": "2026-06-18",
            "event": "减持窗口开启（6/18-9/17）：需监控减持公告",
            "type": "公司",
            "impact": "M",
            "bull": "无减持→资金面压力缓解",
            "bear": "大股东减持→短期抛压+信心打击",
            "sourceLevel": "L5",
            "sourceDetail": "2025年报后6个月解锁窗口",
            "sourceNote": "窗口期6/18-9/17。重点观察未来1-2周是否有减持预披露公告。",
            "status": "pending",
            "lastChecked": TODAY
        }
    ],
}

# === 叙事张力 ===
TENSION = {
    '300726': 'rising',    # 涨价逻辑获持续认可，趋势加速
    '688787': 'stable',    # 稳中微升，等催化
    '688323': 'tension',   # 概念炒作极端化 → 警报升级
    '603690': 'stable',    # 温和反弹，减持窗口刚开启
}

# === Conviction 调整 ===
CONVICTION_ADJ = {
    '300726': 0,     # 价格涨但基本面未变→Conviction不变
    '688787': 0,     # 无新信息
    '688323': -3,    # 概念炒作持续但公司否认→基本面/价格背离加剧
    '603690': -2,    # 减持窗口开启→新增风险因子
}

# === 执行 ===
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

    prev_log = d['priceLog'][-1] if d['priceLog'] else {}
    prev_mv = prev_log.get('mv_yi', base_mv)
    mv_change = round((v['mv'] - prev_mv) / prev_mv * 100, 1) if prev_mv else 0
    prev_price = prev_log.get('price', 0)
    daily_chg = round((v['price'] / prev_price - 1) * 100, 2) if prev_price else 0

    # 跨日涨跌 (vs 6/15)
    prev_patrol_price = PREV_PRICES.get(code, prev_price)
    multi_day_chg = round((v['price'] / prev_patrol_price - 1) * 100, 1) if prev_patrol_price else 0

    # B: priceLog
    d['priceLog'].append({
        'date': TODAY,
        'price': v['price'],
        'pe': v['pe'],
        'mv_yi': v['mv'],
        'return_pct': return_pct,
        'mv_change_pct': mv_change,
        'pct_chg_daily': daily_chg,
        'note': f'巡检。{note} | 4日累计: {multi_day_chg:+.1f}%'
    })

    # C: pillars
    if code in PILLAR_UPDATES:
        for i, update in enumerate(PILLAR_UPDATES[code]):
            if i < len(d['pillars']):
                d['pillars'][i]['history'].append({
                    'date': TODAY,
                    'actual': update['actual'],
                    'trend': update['trend']
                })
                d['pillars'][i]['lastChecked'] = TODAY

    # D: catalysts — update lastChecked + add new
    for c in d['catalystCalendar']:
        c['lastChecked'] = TODAY

    if code in NEW_CATALYSTS:
        d['catalystCalendar'].extend(NEW_CATALYSTS[code])

    seen = set()
    unique_catalysts = []
    for c in d['catalystCalendar']:
        key = c.get('event', '') + c.get('date', '')
        if key not in seen:
            seen.add(key)
            unique_catalysts.append(c)
    d['catalystCalendar'] = unique_catalysts

    # Conviction
    new_conviction = d['conviction'] + CONVICTION_ADJ.get(code, 0)
    if new_conviction != d['conviction']:
        d['conviction'] = new_conviction
        print(f'  Conviction {code}: {d["conviction"]}→{new_conviction} ({CONVICTION_ADJ[code]:+d})')

    # E: thesisLog
    tension = TENSION.get(code, 'stable')
    last_v = max((t.get('version', 0) for t in d['thesisLog']), default=0)

    narratives = {
        '300726': (
            f"6/15涨停→6/16-19四天再+18.0%至85.41。MV 351.75亿({return_pct:+.1f}% vs基准)。"
            "涨停非一日游→钽电容涨价逻辑获市场持续重估。PE从61.94→79.92，意味着市场已将2-3年涨价周期部分定价。"
            "核心α(原材料储备+供给缺口)未变。距7/15 H1预告仅26天——这是首次硬验证窗口。"
            "⚠️ PE 80x意味着：若Q2民品增速<50%或GM<58%，高估值缺乏支撑→回调风险显著。"
            "绝对正面：涨价逻辑从'待验证'→'获认可'阶段。"
            "最大风险：估值跑在基本面之前太远。H1预告是分水岭。"
        ),
        '688787': (
            f"+2.9%至159.39。MV 96.15亿({return_pct:+.1f}% vs基准)。"
            "7月首批算法备案名单→近期最强催化。当前股价已在温和定价备案预期。"
            "若入选名单→ToG叙事获确认→估值修复至105-120亿(Base)。"
            "若未入选→短期回调至140-145区间。8月半年报GM+OCF是硬数据验证。"
        ),
        '688323': (
            f"🔴🔴 四天再+23.9%至61.50。MV 110.70亿({return_pct:+.1f}% vs基准)。"
            "10日累涨+98%，公司6/10澄清'无重要新订单'9天后股价翻倍。"
            "核心矛盾已从'待验证'升级为'已验证背离'——公司L5公告与股价方向完全相反。"
            "GM四连降(20.87%→17.37%)基本面毫无改善。概念炒作(玻璃基板/先进封装/6G)是唯一驱动力。"
            "Conviction 40→37：背离加剧+风险指数级累积。"
            "⚠️ 这不是'错失机会'这是'风险累积'。概念退潮后回调幅度可能>40%。"
            "严守半年报GM≥20%建仓条件，绝不在当前价位参与炒作。"
        ),
        '603690': (
            f"+6.6%至29.32。MV 112.29亿({return_pct:+.1f}% vs基准)。"
            "减持窗口6/18已开启！未来1-2周是减持预披露高发期。"
            "Q1订单19.77亿→Q2营收转化率是核心矛盾。半年报8月唯一硬验证。"
            "减持窗口+半年报前=双风险叠加期。Conviction 50→48。"
            "负债率73%+速动比0.67的财务安全边际仍然薄。"
        ),
    }

    d['thesisLog'].append({
        'version': last_v + 1,
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
    d['reviewSchedule']['nextQuickCheck'] = '2026-06-20(明日巡检)'

    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    print(f'[OK] {code} {d["stockName"]} | {prev_patrol_price}→{v["price"]} ({multi_day_chg:+.1f}%/4d) | mv={v["mv"]}亿 | tension={tension} | conviction={d["conviction"]}')

print('\n=== 本地文件更新完毕，同步 Coze ===')
for code in ACTIVE_CODES:
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches:
        continue
    ok = upsert(matches[0])
    s = 'OK' if ok else 'FAIL'
    print(f'[Coze {s}] {code}')
print('=== 巡检完成 ===')
