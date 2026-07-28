"""2026-07-16 全面巡检 — A-G 完整协议"""
import json, os, glob, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_coze import upsert, list_records

TRACKING_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'memory', 'tracking')
TODAY = '2026-07-16'
PREV_DATE = '2026-07-07'

print('=== Step 0: Coze ===')
coze_records = list_records()
ACTIVE_CODES = [c for c, r in coze_records.items() if r['track_status'] == 'active']
print(f'Active: {ACTIVE_CODES}')

# ===== Step A: 行情 =====
# 实时行情 via 东方财富 push2 API
VALUATION = {
    '300726': {'price': 54.67, 'pe': 59.92, 'mv': 225.2, 'prev_close': 58.65, 'chg_pct': -6.79},
    '688323': {'price': 29.19, 'pe': None, 'mv': 58.5, 'prev_close': 30.40, 'chg_pct': -3.98},
    '603690': {'price': 26.69, 'pe': None, 'mv': 102.2, 'prev_close': 28.08, 'chg_pct': -4.95},
}
PREV_PATROL_PRICES = {'300726': 70.66, '688323': 38.95, '603690': 33.90}

# ===== Step D: 新催化剂（联网搜索发现）=====
NEW_CATALYSTS = {
    '300726': [
        {
            "date": "2026-07-15",
            "event": "🔴🔴 H1业绩预告窗口截止——公司未发布预告",
            "type": "财报",
            "impact": "H",
            "bull": "N/A",
            "bear": "🔴 7/15预告窗口已过而未发布预告→创业板强制披露条件(净利变动>50%/盈亏转换)未被触发。Q1净利+70.77%意味着Q2可能大幅减速甚至出现逆转，或全年累计增速回落至50%以下。这与建档核心假设'民品增速>50%+GM>58%'形成直接矛盾。",
            "sourceLevel": "L5",
            "sourceDetail": "深交所创业板半年度业绩预告规定 + 公司未在7/15前发布预告",
            "sourceNote": "🔴 致命信号：预告缺失说明公司判断H1业绩不达强制披露标准。Q1净利+70.77%的高基数被Q2大幅拖累。'民品增速>50%'这个建档时设为entry condition的核心假设被实质性证伪。",
            "status": "triggered",
            "lastChecked": TODAY
        },
        {
            "date": "2026-07-07",
            "event": "董秘回复H1预告提问：'公司将按规定履行信息披露义务'（非正面回应）",
            "type": "公司",
            "impact": "M",
            "bull": "按规定履行→可能预告正在准备中",
            "bear": "措辞谨慎，未给出任何正向暗示→预告可能不存在",
            "sourceLevel": "L5",
            "sourceDetail": "深交所互动易 2026-07-07",
            "sourceNote": "7/7时董秘拒绝正面回应。8天后7/15窗口关闭确认无预告。董秘的谨慎措辞现在看来是伏笔。",
            "status": "triggered",
            "lastChecked": TODAY
        }
    ],
    '688323': [
        {
            "date": "2026-07-10",
            "event": "🔴 第二次股票交易严重异常波动公告（继6/10首次后再次触发）",
            "type": "公司",
            "impact": "H",
            "bull": "监管关注→概念炒作降温→回归基本面→为理性建仓创造条件",
            "bear": "连续两次严重异常波动→监管升级风险→可能触发更严格交易限制",
            "sourceLevel": "L5",
            "sourceDetail": "上海证券交易所 + 公司公告 2026-07-10",
            "sourceNote": "一个月内两次触发严重异常波动公告！第一次(6/10)因概念炒作98%暴涨→第二次(7/10)表明股价仍在极端波动。多家券商同时发布风险提示(国信/国元/安信/长城/东海)。这是监管层面的红色警报。",
            "status": "triggered",
            "lastChecked": TODAY
        },
        {
            "date": "2026-07-14",
            "event": "董秘互动披露新概念：固态电池PI潜在应用+低轨卫星CPI薄膜研发",
            "type": "公司",
            "impact": "M",
            "bull": "PI材料应用场景持续拓展→远期想象空间打开",
            "bear": "均为早期研发/潜在应用→近期无实质收入贡献→可能成为新一轮概念炒作素材",
            "sourceLevel": "L4",
            "sourceDetail": "上交所互动平台 2026-07-14",
            "sourceNote": "公司同时澄清：产品未应用于MLCC封装。在股价暴跌后主动披露新概念方向(固态电池/低轨卫星)，可能意在稳定市场预期，但也为新一轮概念炒作提供了素材。",
            "status": "triggered",
            "lastChecked": TODAY
        },
        {
            "date": "2026-07-09",
            "event": "深圳基地搬迁补偿事项尚在沟通中",
            "type": "公司",
            "impact": "L",
            "bull": "搬迁补偿增厚一次性收益",
            "bear": "金额和时点不确定",
            "sourceLevel": "L5",
            "sourceDetail": "上交所互动平台 2026-07-09",
            "sourceNote": "深圳基地搬迁补偿可能带来一次性收益，但仍在沟通阶段——不确定性和时间均未知。",
            "status": "pending",
            "lastChecked": TODAY
        }
    ],
    '603690': [
        {
            "date": "2026-07-07",
            "event": "🔴 律师公开征集'踩雷'股民索赔——警示函处罚触发证券虚假陈述民事责任",
            "type": "公司",
            "impact": "H",
            "bull": "N/A——此事无bull面",
            "bear": "🔴 法律风险升级：警示函→投资者索赔前置条件满足→集体诉讼风险。潜在赔偿金额取决于:①可索赔股民数量 ②买入均价与违规期间 ③法院认定比例。叠加市值风云诉讼(6/17二次开庭)→法律费用+赔偿支出双重压力。",
            "sourceLevel": "L4",
            "sourceDetail": "21世纪经济报道/南方财经 2026-07-07",
            "sourceNote": "多家律所启动征集。法律风险是新增维度——6/27巡检时只关注了警示函本身的治理问题，但集体诉讼是警示函的自然法律后果。2021-2024多确认4.17亿净利的规模和恶意程度将直接影响赔偿金额。",
            "status": "triggered",
            "lastChecked": TODAY
        },
        {
            "date": "2026-07-02",
            "event": "媒体深度报道：'会计差错'背后——监管追责+造血乏力+Q1再亏7885万",
            "type": "公司",
            "impact": "M",
            "bull": "媒体关注→倒逼公司整改→长期治理改善",
            "bear": "负面报道扩散→机构投资者可能被迫减仓→估值承压",
            "sourceLevel": "L2",
            "sourceDetail": "证券之星/同花顺 2026-07-02",
            "sourceNote": "媒体持续跟进报道扩大负面影响。注意Q1再亏7885万→在4.17亿多确认净利曝光后,Q1亏损是否也有类似问题存疑。",
            "status": "triggered",
            "lastChecked": TODAY
        }
    ],
}

# ===== C: Pillar更新 =====
PILLAR_UPDATES = {
    '300726': [
        {
            "actual": "🔴🔴 H1预告窗口(7/15)已过未发布！Q1净利+70.77%→H1若未触发50%强制披露阈值→Q2净利大幅减速甚至逆转。'民品增速>50%'的核心假设被实质性证伪。9天-22.6%回调不仅源于大盘→基本面信号同步恶化。",
            "trend": "down",
            "status": "off_track"
        },
        {
            "actual": "Q1 GM=60%。但H1预告缺失意味着H1整体业绩不达强制披露标准→Q2可能出现了GM或收入环比恶化的隐蔽风险。等待半年报(8月)正式数据。",
            "trend": "stable",
            "status": "on_track"
        },
        {
            "actual": "KEMET/AVX涨价周期持续。供给缺口不变。原材料储备α是抗跌底座但已无法单独支撑叙事。",
            "trend": "stable",
            "status": "on_track"
        },
        {
            "actual": "军品>81%稳。但H1预告缺失→整体业绩信号恶化。军品底座仍在但整体投资逻辑已从'等待验证'转为'核心假设被挑战'。",
            "trend": "stable",
            "status": "warning"
        },
    ],
    '688323': [
        {
            "actual": "🔴 9天再跌-25.1%至29.19！从6/19高点61.50→29.19，27天累计-52.5%腰斩。第二次严重异常波动公告(7/10)。GM四连降未改。泡沫完全破裂——跌破建档基准39.9(-26.8%)。概念炒作→泡沫→崩盘的完整周期已被市场验证。",
            "trend": "down",
            "status": "off_track"
        },
        {
            "actual": "钟渊提价20%利好仍在但股价已不反应。Q1营收+15.9%未加速。涨价传导力度温和。基本面未变，但价格已从过度乐观→过度悲观。",
            "trend": "flat",
            "status": "on_track"
        },
        {
            "actual": "半导体PI小批量供货。7/14董秘披露固态电池PI潜在应用+低轨卫星CPI研发→新概念但近期无收入贡献。PSPI研发中。",
            "trend": "flat",
            "status": "on_track"
        },
        {
            "actual": "🔴 第二次严重异常波动(7/10)！多家券商风险提示。深圳基地搬迁补偿沟通中。一个月两次极端波动→监管关注度升级。新概念(固态电池/低轨卫星)可能引发新一轮炒作→警惕重蹈6月覆辙。",
            "trend": "down",
            "status": "off_track"
        },
    ],
    '603690': [
        {
            "actual": "🔴 7/7律师公开征集股民索赔→警示函的法律后果开始显现。集体诉讼+市值风云案→双重法律压力。Q1已亏7885万→财务+法律+治理三重困境交织。9天-21.3%至26.69已回落至建档基准(26.68)。",
            "trend": "down",
            "status": "off_track"
        },
        {
            "actual": "Q1 GM 27.06%。但财务违规涉及合同负债/应收列报不当→GM基准不可靠。半年报(8月)经审计数据是重新评估的起点。媒体深挖'会计差错'持续发酵。",
            "trend": "flat",
            "status": "off_track"
        },
        {
            "actual": "制程设备订单8-12亿目标。财务数据可信度受损→订单数据同样存疑。半年报是重新校准的起点。",
            "trend": "flat",
            "status": "warning"
        },
        {
            "actual": "🔴🔴 多重风险叠加：控股股东减持(6/18-9/17)+证监局警示函+上交所通报批评+第4次监管函+律师征集索赔+市值风云诉讼+负债率73%+Q1亏损。财务安全+法律+治理三维恶化。",
            "trend": "down",
            "status": "off_track"
        },
    ],
}

# ===== E: 叙事张力 =====
TENSION = {
    '300726': 'breaking',   # 🔴 H1预告缺失→核心假设被证伪
    '688323': 'easing',     # 泡沫完全破裂→背离修复→赔率大幅改善
    '603690': 'breaking',   # 🔴 法律风险升级→三重困境加深
}

# ===== F: Conviction调整 =====
# 300726: H1预告缺失 = entry condition实质性证伪 → 大幅下调
# 688323: 泡沫完全破裂+腰斩→不调(基本面未变,赔率已大幅改善)
# 603690: 法律风险(集体诉讼)升级→进一步下调
CONVICTION_ADJ = {
    '300726': -25,  # 62→37: H1预告缺失是thesis-level的证伪
    '688323': 0,    # 37→37: 基本面不变,赔率改善但等半年报
    '603690': -8,   # 30→22: 法律风险升级叠加
}

# ===== 综合评分卡(F) =====
SCORECARDS = {
    '300726': """评分卡(300726 宏达电子) 🔴:
  支柱1 AI转单驱动民品高增: 🔴 off_track (H1预告7/15未出→民品增速假设被实质性证伪)
  支柱2 毛利率稳定≥58%: on_track (Q1 GM=60%, 但H1整体业绩成谜)
  支柱3 供给缺口+涨价: on_track (KEMET/AVX涨价执行中, 但α被β淹没)
  支柱4 军工基本盘: warning (军品稳定但无法独撑叙事)
  风险1 AI需求证伪: 🔴 已部分触发! H1预告缺失=需求信号中断
  风险2 PE估值收缩: 🔴 进行中 PE 80x→60x
  风险3 民品竞争: 低概率
  风险4 军工订单波动: 低概率
  综合: 1/4支柱off_track, 最核心的催化验证窗口失守, Entry condition未满足→不建仓""",
    '688323': """评分卡(688323 瑞华泰):
  支柱1 TPI突破国产替代: off_track (GM四连降未改, 27天腰斩-52.5%至29.19)
  支柱2 钟渊提价传导: on_track (提价20%已生效, 但传导温和)
  支柱3 半导体PI放量: on_track (小批量+固态电池/低轨卫星远期概念)
  支柱4 新业务催化剂: off_track (第二次严重异常波动+多家券商风险提示)
  风险1 概念退潮: ✅ 已完成! 从61.50→29.19腰斩,泡沫挤出完毕
  风险2 GM持续下滑: 🔴 四连降未止, 半年报8月揭晓
  风险3 半年报验证失败: 8月核心验证
  综合: 2/4支柱off_track, 泡沫完全挤出(跌破基准26.8%), 赔率从极差→良好。但GM四连降基本面未变。等半年报GM拐点信号。""",
    '603690': """评分卡(603690 至纯科技) 🔴🔴:
  支柱1 Q1订单19.77亿→Q2收入转化: off_track (财务违规→订单数据可信度受损+律师征集索赔)
  支柱2 GM回升至30%+: off_track (财务违规涉及收入确认→GM基准不可靠)
  支柱3 制程设备突破: warning (订单目标存疑, 等半年报重新校准)
  支柱4 财务安全: 🔴🔴 off_track (减持+警示函+通报批评+第4次监管函+集体诉讼+市值风云案)
  风险1 减持压力: 🔴 进行中(6/18-9/17)
  风险2 财务可信度: 🔴🔴 持续恶化——已触发集体诉讼
  风险3 负债率高: 🔴 73%+速动比0.67+Q1亏损7885万
  风险4 诉讼: 🔴🔴 市值风云案+新增集体诉讼
  综合: 4/4支柱受损, 3项风险已触发, 法律风险新维度。财务可信度+治理+法律三重困境。等待半年报经审计数据再评估。""",
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
    prev_patrol_price = PREV_PATROL_PRICES.get(code, 0)
    multi_day_chg = round((v['price'] / prev_patrol_price - 1) * 100, 1) if prev_patrol_price else 0
    base_mv = d.get('baseMarketCap', 0)
    return_pct = round((v['mv'] / base_mv - 1) * 100, 1) if base_mv else 0
    prev_log = d['priceLog'][-1] if d['priceLog'] else {}
    prev_price = prev_log.get('price', 0)
    daily_chg = v.get('chg_pct', round((v['price'] / prev_price - 1) * 100, 2) if prev_price else 0)
    prev_mv = prev_log.get('mv_yi', base_mv)
    mv_change = round((v['mv'] - prev_mv) / prev_mv * 100, 1) if prev_mv else 0

    # Build price note
    if code == '300726':
        note = (
            f"🔴🔴 9天暴跌-22.6%(70.66→54.67)！MV 291→225亿(-66亿/9天)。"
            f"7/15 H1预告窗口已过——公司未发布预告！"
            f"Q1净利+70.77%的高基数下Q2大幅减速，'民品增速>50%'的核心假设被实质性证伪。"
            f"从6/19高点85.41→54.67，27天累跌-36.0%。"
            f"较建档基准63.2已-13.5%——首次跌破基准。"
        )
    elif code == '688323':
        note = (
            f"9天再跌-25.1%(38.95→29.19)！MV 78→58.5亿(-19.5亿/9天)。"
            f"从6/19高点61.50→29.19，27天腰斩-52.5%。"
            f"7/10第二次严重异常波动公告。泡沫完全破裂。"
            f"较建档基准39.9已-26.8%——深度跌破基准。"
        )
    elif code == '603690':
        note = (
            f"9天-21.3%(33.90→26.69)。MV 130→102亿(-28亿/9天)。"
            f"7/7律师公开征集股民索赔→集体诉讼风险兑现。"
            f"财务违规(多确认4.17亿)+法律风险+减持三重压力。"
            f"几乎回到建档基准26.68(仅+0.04%)。"
        )

    d['priceLog'].append({
        'date': TODAY, 'price': v['price'], 'pe': v['pe'], 'mv_yi': v['mv'],
        'return_pct': return_pct, 'mv_change_pct': mv_change,
        'pct_chg_daily': daily_chg,
        'note': f'巡检。{note} | 9日累计: {multi_day_chg:+.1f}%'
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
    # Update H1预告 catalyst status for 300726
    if code == '300726':
        for c in d['catalystCalendar']:
            if 'H1业绩预告' in c.get('event', ''):
                c['status'] = 'triggered'
                c['bear'] = '预告窗口(7/15)已过未发布→Q2业绩不达强制披露标准→核心假设证伪'
                c['sourceNote'] = '🔴 7/15窗口已过，公司未发布H1预告。创业板强制披露条件(净利变动>50%)未被触发。'
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
            f"🔴🔴 9天-22.6%至54.67。MV 225.2亿({return_pct:+.1f}% vs基准)。"
            f"从6/19高点85.41→54.67，27天累跌-36.0%。首次跌破建档基准(63.2)。"
            f"最关键事件：7/15 H1业绩预告窗口已过，公司未发布预告。"
            f"这直接挑战了建档时的核心假设——Q1净利+70.77%高基数下，"
            f"若H1未能触发±50%强制披露阈值，意味着Q2出现了显著的业绩减速甚至逆转。"
            f"'民品增速>50%'的entry condition被实质性证伪。"
            f"PE 80x→60x的压缩不仅是估值修正——现在有了基本面信号的支撑。"
            f"军品底座+涨价周期仍在但已无法独撑当前叙事。"
            f"Conviction 62→37：核心验证窗口失守。"
            f"行动：entry condition未满足→不建仓。等8月半年报完整数据重新评估。"
        ),
        '688323': (
            f"9天再跌-25.1%至29.19。MV 58.5亿({return_pct:+.1f}% vs基准)。"
            f"从6/19高点61.50→29.19，27天腰斩-52.5%。跌破建档基准39.9(-26.8%)。"
            f"第二次严重异常波动公告(7/10)→一个月内两次触发监管红色警报。"
            f"7/14董秘披露新概念(固态电池/低轨卫星)→可能成为新一轮炒作素材但近期无收入。"
            f"泡沫完整周期已被市场验证：概念炒作(+98%/10天)→极端背离→退潮启动→加速崩塌→腰斩。"
            f"这是教科书级别的'公司L5否认vs市场情绪炒作'案例。"
            f"赔率从极差→良好(29.19 vs 基准39.9)，但GM四连降基本面未变。"
            f"Conviction维持37：不因价格跌了就加仓——等半年报GM拐点信号。"
            f"教训：当L5公告与价格方向相反时，L5终将胜出。这个原则在本轮巡检中得到四次连续验证。"
        ),
        '603690': (
            f"🔴🔴 9天-21.3%至26.69。MV 102.2亿({return_pct:+.1f}% vs基准)——几乎回到建档原点。"
            f"6/27警示函的法律后果开始显现：7/7律师公开征集股民索赔→集体诉讼风险兑现。"
            f"叠加市值风云诉讼(6/17二次开庭)→双重法律压力。"
            f"财务违规(2021-2024多确认4.17亿)+第4次监管函+减持进行中+负债率73%+Q1亏损7885万。"
            f"财务可信度+治理+法律三维恶化。"
            f"Conviction 30→22：法律风险新维度叠加后进一步下调。"
            f"行动：暂停追踪，等半年报经审计数据后重新评估。不因股价回到基准就抄底——"
            f"这次回到基准不是因为估值合理了，而是因为基本面确实在恶化。"
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
    d['reviewSchedule']['nextQuickCheck'] = '2026-07-17(明日巡检)'

    with open(fpath, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

    print(f'[OK] {code} {d["stockName"]} | {prev_patrol_price}→{v["price"]} ({multi_day_chg:+.1f}%/9d) | mv={v["mv"]}亿 | tension={tension} | conv={d["conviction"]}')

print('\n=== Coze sync ===')
for code in ACTIVE_CODES:
    matches = glob.glob(os.path.join(TRACKING_DIR, f'{code}-*.json'))
    if not matches: continue
    ok = upsert(matches[0])
    s = "OK" if ok else "FAIL"
    print(f'[Coze {s}] {code}')
print('=== DONE ===')
