"""2026-07-07 全面巡检 — A-G 完整协议（含联网搜索）"""
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

# ===== Step A: 行情 =====
VALUATION = {
    '300726': {'price': 70.66, 'pe': 66.12, 'mv': 291.01},
    '688323': {'price': 38.95, 'pe': None, 'mv': 78.06},
    '603690': {'price': 33.90, 'pe': None, 'mv': 129.82},
}
PREV_PRICES = {'300726': 84.57, '688323': 56.50, '603690': 35.40}
BASE_MV = {'300726': 260.4, '688323': 71.82, '603690': 102.17}

# ===== Step D: 新催化剂（联网搜索发现）=====
NEW_CATALYSTS = {
    '300726': [
        {
            "date": "2026-07-06",
            "event": "中标四川泛华航空898.30万元采购项目",
            "type": "公司", "impact": "L",
            "bull": "军工订单持续落地，验证军品基本盘稳定",
            "bear": "金额小(898万)，对业绩影响有限",
            "sourceLevel": "L5", "sourceDetail": "企查查/同壁财经 2026-07-06",
            "sourceNote": "小额中标，不改变叙事但验证军品订单持续性。",
            "status": "triggered", "lastChecked": TODAY
        },
        {
            "date": "2026-06-18",
            "event": "临时股东会通过经营范围变更及章程修订(99.99%)",
            "type": "公司", "impact": "M",
            "bull": "为拓展新业务领域铺路→可能布局新赛道",
            "bear": "变更目的未披露，存在不确定性",
            "sourceLevel": "L5", "sourceDetail": "公司公告 2026-06-18",
            "sourceNote": "高票通过。市场分析认为或为优化产业结构铺路。具体方向待披露。",
            "status": "triggered", "lastChecked": TODAY
        }
    ],
    '688323': [
        {
            "date": "2026-07-06",
            "event": "瑞科转债赎回完成：4284万元转股，总股本增加11.33%至2.00亿股",
            "type": "公司", "impact": "M",
            "bull": "转债赎回完成→减少未来财务费用和摊薄不确定性",
            "bear": "11.33%股本扩张→每股价值摊薄。转债强赎引发抛压(6/30最后交易日)",
            "sourceLevel": "L5", "sourceDetail": "公司公告 2026-07-06",
            "sourceNote": "6/30最后交易日+7/3赎回登记日引发的抛压是近期-31%暴跌的部分原因。转债赎回完成本身是中性事件(利空出尽?)。",
            "status": "triggered", "lastChecked": TODAY
        }
    ],
    '603690': [
        {
            "date": "2026-06-27",
            "event": "🔴 上海证监局出具警示函：2021-2024年累计多确认净利润4.17亿元(占更正后76%)",
            "type": "公司", "impact": "H",
            "bull": "N/A——此事无bull面",
            "bear": "🔴 财务数据可信度受损：过往所有财务数据(含Q1订单19.77亿)需重新审视。上交所通报批评+记入诚信档案。",
            "sourceLevel": "L5", "sourceDetail": "上海证监局沪证监决〔2026〕160号 + 上交所通报批评 2026-06-27",
            "sourceNote": "🔴 重大治理事件：①2024年调减净利润1.59亿→由盈转亏 ②金融负债分类错误+投资性房地产核算不当+合同负债/应收列报不当 ③近5年第4次收到上交所监管工作函 ④市值风云诉讼进行中(6/17二次开庭)。控股股东减持窗口6/18-9/17。",
            "status": "triggered", "lastChecked": TODAY
        },
        {
            "date": "2026-06-23",
            "event": "高管关联人减持86万股",
            "type": "公司", "impact": "M",
            "bull": "减持量不大(86万股 vs 3%总上限1149万股)",
            "bear": "减持窗口开启后5天即减持→信号偏负面",
            "sourceLevel": "L5", "sourceDetail": "公司公告 2026-06-26",
            "sourceNote": "控股股东蒋渊及一致行动人减持计划(不超3%)进行中。",
            "status": "triggered", "lastChecked": TODAY
        }
    ],
}

# ===== C: Pillar更新 =====
PILLAR_UPDATES = {
    '300726': [
        {"actual": "7天-16.4%正常回调。PE 80x→66x赔率改善。距H1预告8天。中标四川泛华航空898万(7/6)，军品订单持续。", "trend": "stable", "status": "on_track"},
        {"actual": "Q1 GM=60%。H1预告8天后首次验证涨价对GM传导。", "trend": "stable", "status": "on_track"},
        {"actual": "KEMET/AVX涨价持续。供给缺口不变。", "trend": "up", "status": "on_track"},
        {"actual": "军品>81%稳。中标四川泛华898万→军品订单连续性获验证。", "trend": "stable", "status": "on_track"},
    ],
    '688323': [
        {"actual": "7天-31.1%暴跌！转债赎回(6/30最后交易日)引发抛压+概念泡沫破裂。从61.50→38.95(-36.7%/18天)。GM四连降+公司L5否认终被定价。", "trend": "down", "status": "off_track"},
        {"actual": "钟渊提价20%利好仍在。Q1营收+15.9%未加速。涨价传导力度温和。", "trend": "flat", "status": "on_track"},
        {"actual": "半导体PI小批量。PSPI研发中。无新催化。", "trend": "flat", "status": "on_track"},
        {"actual": "转债赎回完成→总股本+11.33%至2.00亿股。概念退潮是唯一驱动力。", "trend": "down", "status": "warning"},
    ],
    '603690': [
        {"actual": "🔴 6/27证监局警示函+上交所通报批评！2021-2024多确认净利4.17亿(占更正后76%)→财务可信度严重受损。过往所有数据(含Q1订单19.77亿)需重新审视。", "trend": "down", "status": "off_track"},
        {"actual": "Q1 GM 27.06%。但财务违规涉及合同负债/应收列报不当→GM也可能存在偏差。不再采信为可靠基准。", "trend": "flat", "status": "off_track"},
        {"actual": "制程设备订单8-12亿目标。但财务数据可信度受损→需等待半年报经审计数据重新评估。", "trend": "flat", "status": "warning"},
        {"actual": "🔴 负债率73%+速动比0.67+控股股东减持进行中(6/18-9/17,不超3%)+证监局警示函+上交所通报批评+第4次监管函。财务安全+治理双风险。", "trend": "down", "status": "off_track"},
    ],
}

# ===== E: 叙事张力 =====
TENSION = {
    '300726': 'stable',
    '688323': 'easing',
    '603690': 'breaking',  # 🔴 财务违规→叙事断裂
}

# ===== Conviction调整 =====
# 603690: 财务违规 → 支柱信用崩塌 → 大幅下调
# 688323: 转债赎回完成+泡沫挤出→不调(已price in)
# 300726: 不调
CONVICTION_ADJ = {
    '300726': 0,
    '688323': 0,
    '603690': -18,  # 50→32：财务可信度受损是根本性降级
}

# ===== 综合评分卡(F) =====
SCORECARDS = {
    '300726': """评分卡(300726 宏达电子):
  支柱1 AI转单驱动民品高增: on_track (军品订单持续+中标验证)
  支柱2 毛利率稳定≥58%: on_track (Q1 GM=60%, H1预告8天后验证)
  支柱3 供给缺口+涨价: on_track (KEMET/AVX涨价执行中)
  支柱4 军工基本盘: on_track (中标898万+Q1+70.77%)
  风险1 AI需求证伪: 低概率, 7/15验证
  风险2 PE 65x估值收缩: 🟡 PE已从80x→66x, 风险部分释放
  风险3 民品竞争: 低概率
  风险4 军工订单波动: 低概率
  综合: 4/4支柱on_track, 风险可控, H1预告8天后分水岭""",
    '688323': """评分卡(688323 瑞华泰):
  支柱1 TPI突破国产替代: off_track (GM四连降+公司自认无新订单→概念炒作破灭)
  支柱2 钟渊提价传导: on_track (提价20%已生效但营收增速温和)
  支柱3 半导体PI放量: on_track (小批量, 无新进展)
  支柱4 新业务催化剂: warning (转债赎回完成+11.33%股本扩张, 新催化缺失)
  风险1 概念退潮: 🔴 正在发生(-31.1%/7天)
  风险2 GM持续下滑: 🔴 四连降未止
  风险3 半年报验证失败: 8月见分晓
  综合: 1/4支柱off_track, 概念退潮中, 赔率改善但基本面未变""",
    '603690': """评分卡(603690 至纯科技) 🔴🔴:
  支柱1 Q1订单19.77亿→Q2收入转化: off_track (财务违规→订单数据可信度受损)
  支柱2 GM回升至30%+: off_track (财务违规涉及收入确认→GM基准不可靠)
  支柱3 制程设备突破: warning (订单8-12亿目标, 但数据可信度存疑)
  支柱4 财务安全: off_track (控股股东减持+证监局警示函+上交所通报批评+第4次监管函)
  风险1 减持压力: 🔴 进行中(6/18-9/17)
  风险2 财务可信度: 🔴🔴 已发生! 2021-2024多确认净利4.17亿
  风险3 负债率高: 🔴 73%+速动比0.67
  风险4 诉讼: 市值风云案审理中
  综合: 4/4支柱受损, 2项风险已触发, 财务可信度构成一票否决""",
}

# ===== 执行 =====
for code in ACTIVE_CODES:
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches:
        print(f'SKIP {code}: file not found')
        continue
    fpath = matches[0]
    with open(fpath, 'r', encoding='utf-8') as f:
        d = json.load(f)

    v = VALUATION[code]
    note = ''
    prev_patrol_price = PREV_PRICES.get(code, 0)
    multi_day_chg = round((v['price'] / prev_patrol_price - 1) * 100, 1) if prev_patrol_price else 0
    base_mv = BASE_MV.get(code, 0)
    return_pct = round((v['mv'] / base_mv - 1) * 100, 1) if base_mv else 0
    prev_log = d['priceLog'][-1] if d['priceLog'] else {}
    prev_price = prev_log.get('price', 0)
    daily_chg = round((v['price'] / prev_price - 1) * 100, 2) if prev_price else 0
    prev_mv = prev_log.get('mv_yi', base_mv)
    mv_change = round((v['mv'] - prev_mv) / prev_mv * 100, 1) if prev_mv else 0

    # Build price note
    if code == '300726':
        note = f"7天-16.4%(84.57→70.66)。PE 79→66x赔率改善。距H1预告8天。中标四川泛华898万。"
    elif code == '688323':
        note = f"7天-31.1%(56.50→38.95)！转债赎回+概念退潮双重打击。18天累计-36.7%。近回到基准(39.9)。"
    elif code == '603690':
        note = f"🔴 6/27证监局警示函+财务违规(多确认4.17亿)! 股价-4.2%但基本面已质变。Conviction大幅下调。"

    d['priceLog'].append({
        'date': TODAY, 'price': v['price'], 'pe': v['pe'], 'mv_yi': v['mv'],
        'return_pct': return_pct, 'mv_change_pct': mv_change,
        'pct_chg_daily': daily_chg,
        'note': f'巡检。{note} | 7日累计: {multi_day_chg:+.1f}%'
    })

    # C: Pillars
    if code in PILLAR_UPDATES:
        for i, update in enumerate(PILLAR_UPDATES[code]):
            if i < len(d['pillars']):
                d['pillars'][i]['history'].append({
                    'date': TODAY, 'actual': update['actual'], 'trend': update['trend']
                })
                d['pillars'][i]['lastChecked'] = TODAY
                d['pillars'][i]['status'] = update['status']

    # D: Catalysts
    for c in d['catalystCalendar']:
        c['lastChecked'] = TODAY
    if code in NEW_CATALYSTS:
        d['catalystCalendar'].extend(NEW_CATALYSTS[code])
    seen = set()
    uc = []
    for c in d['catalystCalendar']:
        k = c.get('event', '') + c.get('date', '')
        if k not in seen:
            seen.add(k); uc.append(c)
    d['catalystCalendar'] = uc

    # Conviction
    old_conv = d['conviction']
    new_conv = old_conv + CONVICTION_ADJ.get(code, 0)
    if new_conv != old_conv:
        d['conviction'] = new_conv
        print(f'  Conviction {code}: {old_conv}→{new_conv} ({CONVICTION_ADJ[code]:+d})')

    tension = TENSION.get(code, 'stable')
    last_v = max((t.get('version', 0) for t in d['thesisLog']), default=0)

    narratives = {
        '300726': (
            f"7天-16.4%回调至70.66。MV 291.01亿({return_pct:+.1f}% vs基准)。PE 66.12x。"
            "前期PE 80x→66x是估值修正而非基本面恶化。涨价周期+军品底座未变。"
            "7/6中标四川泛华898万→军品订单连续性获验证。"
            "距7/15 H1预告仅8天——这是整个投资逻辑的分水岭。"
            "H1达标(民品>50%+GM>58%)→回调是加仓机会(PE修复至80x=+21%)。不达标→PE可能至55x→进一步-17%。"
            "所有支柱on_track，风险可控。核心变量8天后揭晓。"
        ),
        '688323': (
            f"7天暴跌-31.1%至38.95。MV 78.06亿({return_pct:+.1f}% vs基准)。"
            "转债赎回(6/30最后交易日→7/3登记日→7/6摘牌)引发的抛压叠加概念退潮，18天-36.7%。"
            "总股本+11.33%至2.00亿股(转债转股)，每股价值摊薄。"
            "泡沫挤出接近完成(38.95仅较基准39.9低2.4%)。赔率改善但GM四连降基本面未变。"
            "半年报(8月)GM≥20%是唯一可能的正面催化。在此之前不参与。"
        ),
        '603690': (
            f"🔴🔴 6/27上海证监局出具警示函！至纯科技2021-2024年累计多确认净利润4.17亿元，"
            f"占更正后累计净利润的76%。其中2024年调减净利润1.59亿元→由盈转亏。"
            f"同时收到上交所通报批评(第4次监管函)。控股股东减持进行中(6/18-9/17,不超3%)。"
            f"股价-4.2%至33.90(MV {return_pct:+.1f}% vs基准)但基本面已发生质变。"
            f"财务可信度是投资的基石——当基石出现裂缝，所有基于财务数据的判断都需要重新验证。"
            f"Q1订单19.77亿、Q1营收6.21亿、GM 27%——这些数字现在都需要打问号。"
            f"Conviction从50→32，不是因股价跌了，是因'数据可信度'这根支柱塌了。"
            f"建议：暂停追踪，等半年报经审计数据后再评估。不因股价跌了就抄底——这次跌是有原因的。"
        ),
    }

    d['thesisLog'].append({
        'version': last_v + 1, 'date': f'{TODAY}T22:00:00',
        'thesis': d['thesis'], 'conviction': d['conviction'],
        'delta': note, 'trigger': '每日巡检',
        'narrative': narratives.get(code, ''),
        'verifiedAssumptions': [], 'invalidatedAssumptions': [],
        'newUnknowns': [],
        'narrativeTension': tension,
        'scorecard': SCORECARDS.get(code, '')
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
    s = "OK" if ok else "FAIL"
    print(f'[Coze {s}] {code}')
print('=== DONE ===')
