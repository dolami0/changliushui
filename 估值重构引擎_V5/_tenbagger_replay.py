"""真实十倍股案例回放测试 — 检验管线各层拦截是否会误杀

用 A 股历史上真实发生过的十倍股事件新闻（标题级重构），
跑天机峰 step1_filter + step2_seed_detect，看哪些会被拦。
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, 'src')

from tianjifeng.pipeline import step1_filter, step2_seed_detect

CASES = [
    {
        "name": "正丹股份(2024, 20亿→200亿, 10倍)",
        "title": "美国英力士宣布永久关闭TMA生产线，全球TMA供给缺口扩大，TMA价格突破历史新高",
        "summary": "全球TMA主要生产商英力士宣布永久性关闭其美国TMA产能，占全球供给约25%。TMA价格从2万元/吨暴涨至5万元/吨以上。国内TMA龙头正丹股份产能利用率拉满，订单排至数月后。",
    },
    {
        "name": "英科医疗(2020, 40亿→400亿, 10倍)",
        "title": "全球疫情蔓延，丁腈手套需求激增价格翻倍，英科医疗订单排满产能全开",
        "summary": "全球新冠疫情爆发，一次性丁腈手套需求暴增，出口价格从20美元/箱涨至100美元以上。英科医疗作为国内丁腈手套龙头，订单已排至明年，新增产能陆续投产。",
    },
    {
        "name": "寒武纪(2023, 500亿→4000亿, 8倍)",
        "title": "ChatGPT引爆AI算力需求，寒武纪思元系列AI芯片获得头部互联网大厂批量订单",
        "summary": "大模型训练带动AI芯片需求爆发，国产AI芯片厂商寒武纪思元590芯片获得多家头部互联网公司批量采购订单，国产算力替代进入加速期。",
    },
    {
        "name": "方大炭素(2017, 200亿→1000亿, 5倍)",
        "title": "供给侧改革叠加环保限产，石墨电极价格单月翻倍，方大炭素利润暴增",
        "summary": "环保督查导致大量石墨电极产能关停，供给骤降。石墨电极价格从3万元/吨暴涨至19万元/吨。方大炭素作为行业龙头，产品供不应求，毛利率大幅提升。",
    },
    {
        "name": "中远海控(2021, 300亿→2000亿, 6倍)",
        "title": "全球航运运价突破历史极值，SCFI指数创十年新高，中远海控业绩爆发",
        "summary": "全球供应链紊乱叠加港口拥堵，集运运价持续暴涨，欧洲航线运价突破1万美元/FEU创历史极值。中远海控作为全球第三大集运公司，单季利润超过去十年总和。",
    },
    {
        "name": "东方通信(2019, 60亿→600亿, 10倍)",
        "title": "工信部发放5G商用牌照，5G基站建设大规模启动，东方通信基站设备订单爆发",
        "summary": "工信部正式向三大运营商发放5G商用牌照，5G网络建设进入大规模部署阶段。东方通信作为基站设备供应商，迎来历史性需求机遇。",
    },
    {
        "name": "九安医疗(2021, 30亿→400亿, 13倍)",
        "title": "九安医疗新冠抗原检测试剂获美国FDA紧急使用授权，获得美国政府采购大单",
        "summary": "九安医疗新冠抗原家用检测试剂盒获得美国FDA紧急使用授权(EUA)，并接连获得美国政府数亿美元采购订单，公司业绩出现爆发式增长。",
    },
]

print("=" * 70)
print("十倍股案例回放测试 — 天机峰 step1_filter(初筛) + step2_seed_detect(种子探测)")
print("=" * 70)

passed = 0
for case in CASES:
    print(f"\n【{case['name']}】")
    print(f"  标题: {case['title'][:60]}")

    r1 = step1_filter(case["title"], case["summary"])
    lv1 = r1.get("level", -1)
    print(f"  [初筛] level={lv1} 理由={r1.get('output','')[:40]}")
    if int(lv1) == 0:
        print(f"  >>> 在初筛层被拦截 ❌")
        continue

    r2 = step2_seed_detect(case["title"], case["summary"])
    if r2.get("pass"):
        passed += 1
        print(f"  [种子] PASS ✓ company={r2.get('company','')}")
    else:
        report = r2.get("report", "")
        print(f"  [种子] REJECTED ✗ {report[:120]}")

print(f"\n{'=' * 70}")
print(f"结果: {passed}/{len(CASES)} 通过种子探测")
