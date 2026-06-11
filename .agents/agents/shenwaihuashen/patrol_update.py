"""工作日巡检更新脚本 — 2026-06-08"""
import json, os
from datetime import date

TRACKING_DIR = os.path.join(os.path.dirname(__file__), "memory", "tracking")
TODAY = "2026-06-08"
TRADE_DATE = "2026-06-05"  # 最近交易日

def load_json(code, name):
    path = os.path.join(TRACKING_DIR, f"{code}-{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f), path

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ═══════════════════════════════════════════════════════════
# 300617 安靠智电
# ═══════════════════════════════════════════════════════════
def update_300617():
    data, path = load_json("300617", "安靠智电")

    # Step B: priceLog
    data["priceLog"].append({
        "date": TRADE_DATE,
        "price": 63.03,
        "pe": 141.92,
        "mv_yi": 104.45,
        "return_pct": round((63.03 - data["basePrice"]) / data["basePrice"] * 100, 2),
        "mv_change_pct": round((104.45 - data["baseMarketCap"]) / data["baseMarketCap"] * 100, 2),
        "pct_chg_daily": 3.67,
        "note": "巡检: 6/5放量反弹+3.67%(量1.6亿), 陈晓凌6/3-4增持34500股→减持转增持信号"
    })

    # Step C: pillar updates
    # P1: 北美AIDC订单交付 — verificationDate=2026-10-31, pending
    data["pillars"][0]["lastChecked"] = TODAY
    data["pillars"][0]["history"].append({
        "date": TODAY,
        "actual": "【巡检】北卡审厂6月窗口已过第一周，无结果公告。陈晓凌6/3-4增持(均价64.61/60.27)逆转5月减持趋势——管理层在60元附近增持是正面信号。股价从60.80反弹至63.03",
        "trend": "up"
    })

    # P2: 海外收入占比突破5% — verificationDate=2027-04-30, pending
    data["pillars"][1]["lastChecked"] = TODAY
    data["pillars"][1]["history"].append({
        "date": TODAY,
        "actual": "【巡检】无新增数据。海外收入占比需半年报验证",
        "trend": "stable"
    })

    # P3: 毛利率持续改善 — on_track, verificationDate=2026-08-31
    data["pillars"][2]["lastChecked"] = TODAY
    data["pillars"][2]["history"].append({
        "date": TODAY,
        "actual": "【巡检】Q1 GM=38.8%已达标。Q1 ROE仅1.63%偏低(季节性+转型阵痛)，等待半年报全面验证",
        "trend": "stable"
    })

    # P4: 扣非利润恢复增长 — verificationDate=2027-04-30, pending
    data["pillars"][3]["lastChecked"] = TODAY
    data["pillars"][3]["history"].append({
        "date": TODAY,
        "actual": "【巡检】无新增数据。半年报(8月)是关键验证点",
        "trend": "stable"
    })

    # P5: 应收/营收比率改善 — verificationDate=2026-08-31, pending
    data["pillars"][4]["lastChecked"] = TODAY
    data["pillars"][4]["history"].append({
        "date": TODAY,
        "actual": "【巡检】无新增数据。半年报验证",
        "trend": "stable"
    })

    # Step D: catalyst updates
    # 北卡审厂(6月) — still pending, no results
    data["catalystCalendar"][0]["note"] = f"6月第一周已过(巡{TODAY})，北卡审厂结果待公告。预计6月中下旬或有进展"

    # 新增催化剂: 陈晓凌增持
    data["catalystCalendar"].insert(0, {
        "date": "2026-06-04",
        "event": "陈晓凌6/3-4增持3.45万股",
        "type": "公司",
        "impact": "M",
        "bull": "管理层在60元附近增持=信心信号，减持计划可能提前终止",
        "bear": "增持量小(仅3.45万股)→象征性动作",
        "status": "triggered",
        "note": "5月减持238万股套现1.12亿后，6/3-4小额增持。减持计划有效期至7/23，仍需关注后续动向"
    })

    # Step E: exit conditions
    # 跌破58元(~95亿) — not triggered (63.03 > 58)
    # 大股东质押率 — 陈晓凌0.88%, 无变化
    # No exit condition triggered

    # Step F: aShare updates
    data["aShareTracking"]["marginCheck"] = {
        "lastChecked": TODAY,
        "result": "tushare margin_detail返回空(300617创业板可能无两融数据或接口限制)"
    }
    data["aShareTracking"]["insiderTrading"] = {
        "lastChecked": TODAY,
        "result": "陈晓凌6/3-4增持3.45万股(均价64.61/60.27)，逆转5月减持趋势。减持计划有效期至7/23，剩余额度未用完。正面信号但需持续观察"
    }

    # Step G: thesisLog — 新增版本(陈晓凌减持转增持+股价低位反弹)
    data["thesisLog"].append({
        "version": 4,
        "date": f"{TODAY}T09:07:00",
        "thesis": "国内GIL龙头凭借北美全认证切入AIDC变压器蓝海，北美订单指引$1亿(翻倍)已落地~4亿人民币。新增关键信号：董事长陈晓凌6/3-4在60元附近增持3.45万股，逆转5月减持趋势——管理层低位增持是强于订单数据本身的信心信号。若9月首批主变如期发货，范式切换成立。",
        "conviction": 52,
        "delta": "+2",
        "trigger": f"巡检: 陈晓凌6/3-4增持(均价64.61/60.27)逆转5月减持趋势 + 股价低位反弹至63.03 + 北卡审厂6月窗口待结果",
        "narrative": "本轮巡检发现一个重要信号反转：董事长陈晓凌在5月大幅减持238万股(套现~1.12亿)后，6月3-4日在60元附近增持了3.45万股。虽然增持量很小(约200万元)，但在减持窗口期内转为增持，至少说明管理层认为60元附近已进入合理估值区间——这比任何券商目标价都更有说服力。负面因素：北卡审厂6月窗口已过一周仍无结果，若6月全月无公告则审厂可能延迟；减持计划有效期至7月23日，陈晓凌仍有剩余额度可减持。Conviction从50上调至52——管理层增持是独立于订单数据之外的信心验证信号，但小额增持≠减持计划终止。",
        "verifiedAssumptions": [
            "北美全认证完成(IEC/ANSI/CSA)",
            "北美订单指引上修至$1亿",
            "已落地~4亿订单",
            "陈晓凌60元附近增持→管理层信心"
        ],
        "invalidatedAssumptions": [],
        "newUnknowns": [
            "北卡审厂结果(6月窗口)",
            "陈晓凌减持计划剩余额度(有效期至7/23)",
            "微软6000万订单能否落地",
            "9月100台主变能否如期发货"
        ],
        "narrativeTension": "rising"
    })

    # Step H: reviewSchedule
    data["reviewSchedule"]["lastCheck"] = f"{TODAY}(巡检)"
    data["reviewSchedule"]["nextQuickCheck"] = "2026-06-09(周二巡检)"

    save_json(data, path)
    print(f"[OK] 300617 安靠智电 updated")
    return data

# ═══════════════════════════════════════════════════════════
# 300726 宏达电子
# ═══════════════════════════════════════════════════════════
def update_300726():
    data, path = load_json("300726", "宏达电子")

    # Step B: priceLog
    data["priceLog"].append({
        "date": TRADE_DATE,
        "price": 75.01,
        "pe": 77.00,
        "mv_yi": 308.92,
        "return_pct": round((75.01 - data["basePrice"]) / data["basePrice"] * 100, 2),
        "mv_change_pct": round((308.92 - data["baseMarketCap"]) / data["baseMarketCap"] * 100, 2),
        "pct_chg_daily": -6.14,
        "note": "巡检: 6/5回撤-6.14%(量35.9亿天量), 前期涨停后获利盘出逃, PE从82x→77x, 炒作情绪降温"
    })

    # Step C: pillar updates
    # P1: AI转单驱动民品高增 — verificationDate=2026-07-15, pending
    data["pillars"][0]["lastChecked"] = TODAY
    data["pillars"][0]["history"].append({
        "date": TODAY,
        "actual": "【巡检】公司6/4异常波动公告澄清：民品MLCC规模极小，民品收入仅占总营收18.04%。大摩Rubin MLCC研报驱动的涨停本质是市场炒作而非基本面兑现。真正的α在钽电容涨价+原材料储备，而非MLCC。7/15 H1预告仍是核心验证窗口",
        "trend": "stable"
    })

    # P2: 毛利率稳定在高位 — on_track, verificationDate=2026-07-15
    data["pillars"][1]["lastChecked"] = TODAY
    data["pillars"][1]["history"].append({
        "date": TODAY,
        "actual": "【巡检】Q1 GM=60%达预期。钽电容涨价+原材料储备→利润转化逻辑未变。新增无锡封测产线(一期3亿)布局半导体高端器件",
        "trend": "up"
    })

    # P3: 供给缺口持续+涨价落地 — on_track, verificationDate=2026-06-30
    data["pillars"][2]["lastChecked"] = TODAY
    data["pillars"][2]["history"].append({
        "date": TODAY,
        "actual": "【巡检】6月已到，松下/基美涨价应已进入执行阶段。但公司董秘对涨价回应谨慎('结合市场实际判断')，未明确披露幅度。AVX 5月生效+KEMET 6/1第四次调价确认涨价周期成立",
        "trend": "up"
    })

    # P4: 军工基本盘稳定 — on_track, verificationDate=2026-08-31
    data["pillars"][3]["lastChecked"] = TODAY
    data["pillars"][3]["history"].append({
        "date": TODAY,
        "actual": "【巡检】公司澄清公告重申高可靠元器件营收占比超81%，强化了军工主业稳定逻辑。Q1净利+70.77%",
        "trend": "stable"
    })

    # Step D: catalyst updates
    # 松下/基美涨价(6月) — already triggered
    data["catalystCalendar"][0]["note"] = f"已触发(巡{TODAY})。AVX 5月+KEMET 6/1涨价生效。但公司董秘未明确披露自身涨价幅度"

    # 新增催化剂
    data["catalystCalendar"].insert(0, {
        "date": "2026-06-04",
        "event": "异常波动公告澄清MLCC炒作",
        "type": "公司",
        "impact": "M",
        "bull": "炒作退潮后估值回归合理→健康上行",
        "bear": "炒作破灭→恐慌性抛售",
        "status": "triggered",
        "note": "6/4公告：民用MLCC规模极小/民品仅18%/PE 82x风险提示。6/5回撤-6.14%初步验证炒作退潮"
    })

    data["catalystCalendar"].insert(1, {
        "date": "2026-06-02",
        "event": "无锡封测产线(一期3亿)章程修订",
        "type": "公司",
        "impact": "M",
        "bull": "封测产线如期推进→半导体高端化",
        "bear": "投入过大影响短期利润",
        "status": "pending",
        "note": "6/2章程修订公告，一期2026-2028年，面向新能源/消费/工控"
    })

    # Step E: exit conditions
    # Q2民品增速<30% → 不参与 → not yet (7/15验证)
    # PE突破90x → 6/4 PE=82x, 6/5 PE=77x → not triggered
    # No exit triggered

    # Step F: aShare
    data["aShareTracking"]["insiderTrading"] = {
        "lastChecked": TODAY,
        "result": "三大控股股东(曾琛34.48%/钟若农29.72%/曾继疆5.05%)持股未变。北向资金减持162.8万股(调仓，非大股东减持)。无减持公告"
    }
    # margin was checked 5/23, <30 days

    # Step G: thesisLog — 新增版本(MLCC炒作+澄清+回撤)
    data["thesisLog"].append({
        "version": 4,
        "date": f"{TODAY}T09:07:00",
        "thesis": "军工钽电容龙头，涨价周期全面确认，原材料储备优势将涨价100%转化为净利润。但6/3-4涨停由AI-MLCC概念炒作驱动，公司自己澄清民品MLCC体量极小——股价已从涨停高点回撤-6.14%。核心验证点仍为7/15 H1业绩预告：民品增速>50%+GM>58%。",
        "conviction": 62,
        "delta": "0",
        "trigger": f"巡检: 6/5回撤-6.14%/PE从82x→77x/公司澄清MLCC非主业/无锡封测产线新布局",
        "narrative": "6/3-4宏达电子涨停(+20%)后，6/5回撤-6.14%至75.01元。这验证了上期巡检的判断——MLCC概念本质是市场炒作而非基本面兑现。公司6/4公告明确澄清三件事：(1)民品MLCC规模极小、(2)民品收入仅占18.04%、(3)PE已达82倍存在过热风险。回调后PE从82x降至77x，赔率空间有所修复但仍偏高。积极面：涨价周期确认(AVX+KEMET已执行)，新增无锡封测产线(一期3亿)布局半导体高端领域，三大控股股东零减持。Conviction维持62不变——涨价+军工基本面逻辑完整，炒作退潮是健康调整而非论点证伪。",
        "verifiedAssumptions": [
            "AVX涨价5月已生效",
            "KEMET第四轮涨价6/1启动",
            "公司澄清MLCC非主业→确认炒作偏差"
        ],
        "invalidatedAssumptions": [],
        "newUnknowns": [
            "Q2民品增速能否>50%(7/15 H1预告)",
            "MLCC炒作退潮后能否守住70元支撑位",
            "钽电容涨价在公司层面的实际兑现幅度"
        ],
        "narrativeTension": "tension"
    })

    data["reviewSchedule"]["lastCheck"] = f"{TODAY}(巡检)"
    data["reviewSchedule"]["nextQuickCheck"] = "2026-06-09(周二巡检)"

    save_json(data, path)
    print(f"[OK] 300726 宏达电子 updated")
    return data

# ═══════════════════════════════════════════════════════════
# 688627 精智达
# ═══════════════════════════════════════════════════════════
def update_688627():
    data, path = load_json("688627", "精智达")

    # Step B: priceLog
    data["priceLog"].append({
        "date": TRADE_DATE,
        "price": 385.56,
        "pe": 554.74,
        "mv_yi": 362.92,
        "return_pct": round((385.56 - data["basePrice"]) / data["basePrice"] * 100, 2),
        "mv_change_pct": round((362.92 - data["baseMarketCap"]) / data["baseMarketCap"] * 100, 2),
        "pct_chg_daily": -0.63,
        "note": "巡检: 6/5微调-0.63%, PE 555x, 前日+9.1%反弹后正常消化。融资余额11.71亿(占市值3.2%), 无融券"
    })

    # Step C: pillar updates
    # P1: 半导体收入持续高增 — verificationDate=2026-08-31, pending
    data["pillars"][0]["lastChecked"] = TODAY
    data["pillars"][0]["history"].append({
        "date": TODAY,
        "actual": "【巡检】6家机构一致买入/增持，2026E营收16.82亿/净利2.65亿(+70% YoY)。Q1营收+119%验证超预期。2026年1月斩获13.11亿大单。长鑫占新增订单80%+",
        "trend": "up"
    })

    # P2: 长鑫IPO注册批文 — on_track, verificationDate=2026-07-31
    data["pillars"][1]["lastChecked"] = TODAY
    data["pillars"][1]["history"].append({
        "date": TODAY,
        "actual": "【巡检】5/27过会+提交注册后等待证监会批文。万得专题称'2万亿国产存储巨头IPO渐近'。市场预期6-7月下发。进度符合预期",
        "trend": "up"
    })

    # P3: 18Gbps FT验证通过 — verificationDate=2026-12-31, pending
    data["pillars"][2]["lastChecked"] = TODAY
    data["pillars"][2]["history"].append({
        "date": TODAY,
        "actual": "【巡检】无新增技术进展。流片已完成是积极前置信号",
        "trend": "up"
    })

    # P4: 扣非利润恢复正增长 — verificationDate=2026-08-31, pending
    data["pillars"][3]["lastChecked"] = TODAY
    data["pillars"][3]["history"].append({
        "date": TODAY,
        "actual": "【巡检】Q1营收+119%预示扣非改善，但股份支付+研发费用仍吞噬利润。券商预期2026归母2.65亿(+70%)",
        "trend": "up"
    })

    # P5: 应收/客户集中度改善 — verificationDate=2026-08-31, pending
    data["pillars"][4]["lastChecked"] = TODAY
    data["pillars"][4]["history"].append({
        "date": TODAY,
        "actual": "【巡检】无新增数据。长江存储IPO推进中→客户多元化逻辑强化",
        "trend": "stable"
    })

    # Step D: catalyst updates
    # 长鑫IPO注册批文(7月) — pending, 等待证监会
    data["catalystCalendar"][0]["note"] = f"已过会+提交注册(巡{TODAY}确认)。等待证监会正式注册批文，预期6-7月。万得专题称2万亿存储巨头IPO渐近"
    data["catalystCalendar"][0]["status"] = "pending"  # 仍pending, 批文未下发

    # 定增29.02亿 — pending
    data["catalystCalendar"][4]["note"] = f"预案修订稿已发布(巡{TODAY})，金额29.02亿，等待上交所审核"

    # Step E: exit conditions — none triggered
    # 长鑫批文被否 — not yet
    # 半年报半导体增速<80% — not yet (8月)
    # PE回落至200x可加仓 — PE=555x, far from 200x

    # Step F: aShare
    data["aShareTracking"]["marginCheck"] = {
        "lastChecked": TODAY,
        "result": f"融资余额11.71亿(占市值362.9亿的3.2%), 无融券余额。6/3-5融资买入约3.1亿/日, 融资余额稳定在11-13亿区间, 无异常"
    }

    # Step G: thesisLog — 新增版本(券商一致性确认+融资数据)
    data["thesisLog"].append({
        "version": 3,
        "date": f"{TODAY}T09:07:00",
        "thesis": "国内唯一DRAM/HBM全制程存储测试设备商，长鑫IPO已提交注册(5/27过会)，半导体在手订单35亿+超预期，6家机构一致买入/增持(2026E净利2.65亿/+70%)。若注册批文6-7月下发+长鑫首标份额>50%，估值范式切换确立。",
        "conviction": 62,
        "delta": "+2",
        "trigger": f"巡检: 6家机构一致买入确认(2026E净利2.65亿)+融资余额11.71亿(+3.2%)+长鑫2万亿IPO渐近(万得专题)+512GB DDR5进入验证",
        "narrative": "本轮巡检强化了精智达叙事的机构共识面：(1)6家机构(中泰/东兴/东北/广发/中邮/华安)一致买入/增持评级，2026E营收16.82亿(+49%)、净利2.65亿(+70%)，增长逻辑得到专业验证。(2)长鑫2万亿IPO专题出现在万得终端——作为Wind核心用户的基金经理群体正在关注这条产业链。(3)融资余额11.71亿(占市值3.2%)、无融券——杠杆资金偏多但未到过热水平。(4)512GB DDR5 DRAM测试进入验证阶段(最新产品进展)。核心风险仍是PE 555x的高估值——如果批文延迟至8月后或半导体增速放缓，PE压缩风险显著。Conviction从60上调至62——机构共识+长鑫IPO专题传播扩大，确定性提升。",
        "verifiedAssumptions": [
            "长鑫IPO过会+提交注册(5/27)",
            "6家机构一致买入/增持评级",
            "在手订单35亿+/Q1营收+119%",
            "512GB DDR5进入验证"
        ],
        "invalidatedAssumptions": [],
        "newUnknowns": [
            "注册批文实际下发时间(6-7月还是延迟)",
            "长存导入的具体份额",
            "12月科创板解禁→大股东态度"
        ],
        "narrativeTension": "rising"
    })

    data["reviewSchedule"]["lastCheck"] = f"{TODAY}(巡检)"
    data["reviewSchedule"]["nextQuickCheck"] = "2026-06-09(周二巡检)"

    save_json(data, path)
    print(f"[OK] 688627 精智达 updated")
    return data

# ═══════════════════════════════════════════════════════════
# 688720 艾森股份
# ═══════════════════════════════════════════════════════════
def update_688720():
    data, path = load_json("688720", "艾森股份")

    # Step B: priceLog
    data["priceLog"].append({
        "date": TRADE_DATE,
        "price": 92.50,
        "pe": 159.11,
        "mv_yi": 81.52,
        "return_pct": round((92.50 - data["basePrice"]) / data["basePrice"] * 100, 2),
        "mv_change_pct": round((81.52 - data["baseMarketCap"]) / data["baseMarketCap"] * 100, 2),
        "pct_chg_daily": -3.49,
        "note": "巡检: 6/5回撤-3.49%, 前两日累计反弹+10.5%后获利回吐, PE 159x, 市值82亿。融资余额5.72亿(占7.0%)偏高"
    })

    # Step C: pillar updates
    # P1: 光刻胶产品升级 — verificationDate=2026-08-31, pending
    data["pillars"][0]["lastChecked"] = TODAY
    data["pillars"][0]["history"].append({
        "date": TODAY,
        "actual": "【巡检】中邮证券5/19研报：2026E营收7.96亿/净利0.71亿，买入评级。先进封装负性光刻胶稳定量产(HBM封装)，PSPI小量产，KrF 13:1验证中。Q1扣非+73.26%验证利润质量",
        "trend": "up"
    })

    # P2: 电镀液先进制程放量 — verificationDate=2026-08-31, pending
    data["pillars"][1]["lastChecked"] = TODAY
    data["pillars"][1]["history"].append({
        "date": TODAY,
        "actual": "【巡检】28nm大马士革镀铜添加剂稳定量产，5-14nm钴制程获首个国产化量产订单。TSV高速镀铜验证中。GM仍需关注(Q1 GM=27.7%季节性低位)",
        "trend": "up"
    })

    # P3: 华为韬定律催化兑现 — verificationDate=2026-10-31, pending
    data["pillars"][2]["lastChecked"] = TODAY
    data["pillars"][2]["history"].append({
        "date": TODAY,
        "actual": "【巡检】无新增华为相关动态。9-10月秋发是关键验证窗口。等待华为秋季麒麟芯片发布",
        "trend": "stable"
    })

    # P4: GM趋势持续改善 — verificationDate=2026-08-31, pending
    data["pillars"][3]["lastChecked"] = TODAY
    data["pillars"][3]["history"].append({
        "date": TODAY,
        "actual": "【巡检】Q1 GM=27.7%季节性偏低。中邮证券最新研报看好高毛利产品放量→综合GM持续改善。等待半年报验证",
        "trend": "stable"
    })

    # P5: 南通基地如期投产 — verificationDate=2026-12-31, pending
    data["pillars"][4]["lastChecked"] = TODAY
    data["pillars"][4]["history"].append({
        "date": TODAY,
        "actual": "【巡检】华东制造基地(20亿/23000吨)推进中，构建'国内+海外'全球化产能体系。马来西亚INOFINE已并表(~8%营收)",
        "trend": "stable"
    })

    # Step D: catalyst updates — none triggered this round
    # 新增催化剂
    data["catalystCalendar"].insert(0, {
        "date": "2026-05-19",
        "event": "中邮证券发布买入研报(目标未公开)",
        "type": "券商",
        "impact": "L",
        "bull": "2026E净利0.71亿(+70% YoY)",
        "bear": "",
        "sourceLevel": "L3",
        "status": "triggered",
        "note": "5/19中邮证券买入研报：2026E营收7.96亿/净利0.71亿，当前PE 114x(基于2026E)"
    })

    # Step E: exit conditions
    # 跌破60元(~55亿) — not triggered (92.50 > 60)
    # 光刻胶增速<30% — not yet (8月)
    # 电镀液GM再降>3ppt — not yet (8月)

    # Step F: aShare
    data["aShareTracking"]["marginCheck"] = {
        "lastChecked": TODAY,
        "result": f"融资余额5.72亿(占市值81.5亿的7.0%)。融资余额偏高(>5%警戒线)，近两周从5.45亿升至5.72亿(+5%)。无融券。需关注：若股价持续下跌+融资盘被迫平仓可能加剧下跌"
    }

    # Step G: thesisLog — 新增版本
    data["thesisLog"].append({
        "version": 2,
        "date": f"{TODAY}T09:07:00",
        "thesis": "国内唯一光刻胶+电镀液双赛道企业，华为韬定律确立3D堆叠后摩尔主线。中邮证券买入评级(2026E净利0.71亿/+70%)，Q1扣非+73.26%验证利润质量。南通20亿基地推进全球化产能布局。核心验证点：2026H1光刻胶+电镀液增速>80%+华为秋发拆解证实逻辑折叠规模采用。",
        "conviction": 63,
        "delta": "+2",
        "trigger": f"巡检: 中邮证券买入研报(5/19)+Q1扣非+73.26%+南通基地推进+融资余额5.72亿(7.0%)偏高警示",
        "narrative": "本轮巡检更新了艾森股份的机构共识面：中邮证券5/19发布买入研报，2026E营收7.96亿(+21% vs FY2025 6.56亿)、净利0.71亿(+70% vs FY2025 0.42亿)。注意中邮净利预测低于此前独立估值时的隐含假设(当时Base情景隐含~1.0亿净利)——需要根据券商数据重新校准盈利预期。积极面：Q1扣非+73.26%、28nm+5-14nm钴制程量产突破、南通20亿基地推进。风险面：融资余额5.72亿(占市值7.0%)偏高，若股价继续下行可能触发融资盘平仓→加剧下跌的负反馈。Conviction从61上调至63——机构覆盖+扣非持续高增增强确定性，但融资偏高是新的风险点。",
        "verifiedAssumptions": [
            "Q1扣非+73.26%验证利润质量",
            "中邮证券买入评级确认机构认可",
            "28nm/5-14nm制程量产突破"
        ],
        "invalidatedAssumptions": [],
        "newUnknowns": [
            "券商净利预测(0.71亿)低于此前独立假设(~1.0亿)的影响",
            "融资偏高(7.0%)→下跌负反馈风险",
            "华为秋发+半年报(8月)"
        ],
        "narrativeTension": "stable"
    })

    data["reviewSchedule"]["lastCheck"] = f"{TODAY}(巡检)"
    data["reviewSchedule"]["nextQuickCheck"] = "2026-06-09(周二巡检)"

    save_json(data, path)
    print(f"[OK] 688720 艾森股份 updated")
    return data

# ═══════════════════════════════════════════════════════════
# 执行所有更新
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    r1 = update_300617()
    r2 = update_300726()
    r3 = update_688627()
    r4 = update_688720()
    print("\n═══════════════════════════════════════════════════════════")
    print("所有标的巡检更新完成!")
    print(f"日期: {TODAY} | 交易日期: {TRADE_DATE}")
    print(f"300617 安靠智电: {len(r1['priceLog'])}条价格记录, thesis v{len(r1['thesisLog'])}")
    print(f"300726 宏达电子: {len(r2['priceLog'])}条价格记录, thesis v{len(r2['thesisLog'])}")
    print(f"688627 精智达:   {len(r3['priceLog'])}条价格记录, thesis v{len(r3['thesisLog'])}")
    print(f"688720 艾森股份: {len(r4['priceLog'])}条价格记录, thesis v{len(r4['thesisLog'])}")
