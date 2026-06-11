"""重跑瑞华泰(688323)验证Q1/Q2/Q3修复"""
import json, sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from orchestrator import run_pipeline

# 从原报告中提取的完整事件素材
event_text = """<card title="铋薄膜行业专家会纪要要点">

市场供需情况
- 全球电子级pi产能仅1.8万吨，2025年需求已达3万吨，缺口1-1.2万吨；2026年电子+热控需求约2.8万吨，缺口进一步扩大
- 海外龙头（杜邦/钟渊）近年零新增产能，存货极少，订单排产已到2027Q2；部分产能被英伟达、苹果长单锁定至2027年
- AI领域批需求2025年约3000吨 -> 2026年3600-4000吨（+20-30%），未来三年CAGR 25-30%，2029年突破1万吨

涨价已启动：
- 2026年以来海外电子级PI已涨30%-50%，下半年预计仍有20%-30%涨价空间
- 国产高导热PI当前为进口价60%，跟涨空间充足，导入期结束预计价格会到进口的80%

瑞华泰的产能规划
当前->2026年底：
- 二期投产后总产能达5000吨/年
- 产品结构：电子级+热控占比约40%（~2000吨），其余为电工/光学/航天
2027-2028年：
- 规划总产能提升至7000-8000吨/年（新增产能全为高端电子级）

隐藏产能弹性：
- 现有3000吨非高端产能（电工级等）可通过技改转产电子级，下游认证通过即可切换
- 实际电子级潜在产能远大于账面

瑞华泰的客户验证进展：目前国内进度最领先，T0级别
已稳定供货客户：华为、中兴、比亚迪、通富微电
- 新易盛800G--已批量供货
服务器（当前国产化率约0，突破即第一家）：
- 浪潮 -- 推进中
- 长江存储 -- 已部分导入，目标2028年份额30%-40%（二供）
- 韩国存储客户（年需求4000-5000吨，大于长存）：
- 三星--小批量测试已通过，正在拿代码，2026年有望批量供货
- 海力士 -- 认证流程中，进度略慢于三星
- 中际旭创1.6T-认证中

空间测算
- 2026E有效产量约2350吨，年底产能到5000吨
- 电子级(占比60%)：半导体/光模块验证通过后整体均价有望提升至150万/吨
- 高导热/热控/其他(占比40%)：价格战后均价约12万/吨
- 年底3000吨*200万/吨（价格是海外大厂的一半）=60亿，25%净利率，15亿，30倍市盈率，450亿，潜在10倍股

棱镜收录 | 2026/6/10 14:37:18 | 严禁外传
</card>"""

event_data = {
    "stock_code": "688323",
    "stock_name": "瑞华泰",
    "raw_event_text": event_text,
    "investment_theme": "瑞华泰投资主题报告：押注国产PI薄膜龙头的产能爬坡与高端突破双主线。核心矛盾是嘉兴新产能的折旧压力与高端产品（CPI/TPI）市场突破速度之间的赛跑。",
    "event_source": "天机",
    "response_level": "5",
    "created_at": "2026-06-10 15:47:46",
}

print("=" * 60)
print("重跑瑞华泰(688323) - 验证Q1/Q2/Q3修复")
print("=" * 60)
t0 = time.time()

try:
    result = run_pipeline("688323", event_data)
    elapsed = time.time() - t0
    print(f"\n管线完成，耗时 {elapsed:.0f}s")

    # 提取关键输出
    a3 = result.get("agent3", {})
    sv = a3.get("scenario_valuation", {})
    vs = a3.get("valuation_summary", {})
    conf = a3.get("confidence", {})
    xcheck = a3.get("_code_cross_validation")
    growth = a3.get("growth_path_decomposition")
    warnings = result.get("_validation_warnings", []) or a3.get("_validation_warnings", [])

    print("\n--- 估值摘要 ---")
    print(f"  路由模型: {result.get('agent2',{}).get('routing_decision',{}).get('primary_model','?')}")
    print(f"  概率加权 upside: {vs.get('probability_weighted_upside_pct','?')}%")
    print(f"  概率加权市值: {vs.get('probability_weighted_mcap_yi','?')}亿")
    print(f"  非对称比率: {vs.get('asymmetry_ratio','?')}")
    print(f"  置信度: {conf.get('overall_score','?')}/10")

    details = sv.get("scenario_details", {})
    if isinstance(details, dict):
        for s in ("bear", "base", "bull"):
            d = details.get(s, {})
            print(f"  {s}: prob={d.get('probability','?')}, upside={d.get('upside_pct','?')}%, mcap={d.get('target_mcap_yi','?')}亿")

    # Q1: 强制跨族校验
    print("\n--- Q1: 强制跨族底线校验 ---")
    if xcheck:
        print(f"  校验模型: {xcheck.get('validation_model','?')}")
        print(f"  净资产底线: {xcheck.get('validation_mcap_yi','?')}亿 (PB={xcheck.get('detail',{}).get('floor_pb','?')}x)")
        print(f"  Base/底线比值: {xcheck.get('base_target_mcap_yi',0)/max(xcheck.get('validation_mcap_yi',1),1):.1f}x")
        print(f"  评估: {xcheck.get('assessment','?')[:100]}")
        if xcheck.get("_overrides_llm_selfcheck"):
            print(f"  [覆盖] LLM选择了self_validation，代码层强制覆盖")
    else:
        print(f"  未触发(非重资产公司或数据不足)")

    # Q2: ROIC-CAGR 审计
    print("\n--- Q2: ROIC-CAGR审计 ---")
    e308_warnings = [w for w in warnings if w.get("code","").startswith("E308")]
    if e308_warnings:
        for w in e308_warnings:
            print(f"  [{w['code']}] {w['message'][:120]}")
    else:
        print(f"  无E308警告 (ROIC路径已论证 或 CAGR<=20%)")

    # Q3: CAGR拆解表
    print("\n--- Q3: CAGR增长路径拆解 ---")
    if growth:
        drivers = growth.get("drivers", [])
        if drivers:
            for d in drivers:
                print(f"  {d.get('driver','?')}: +{d.get('nominal_pct','?')}% [{d.get('support_level','?')}]")
            print(f"  名义CAGR: {growth.get('nominal_cagr_pct','?')}%")
            print(f"  有效CAGR: {growth.get('effective_cagr_pct','?')}%")
            print(f"  折扣说明: {growth.get('discount_detail','?')}")
        else:
            print(f"  LLM未输出拆解表 (字段存在但drivers为空)")
    else:
        print(f"  LLM未输出growth_path_decomposition字段 (新增Prompt可能未生效)")

    # 其他warnings
    other_warnings = [w for w in warnings if not w.get("code","").startswith("E308")]
    if other_warnings:
        print(f"\n--- 其他校验警告 ({len(other_warnings)}条) ---")
        for w in other_warnings[:5]:
            print(f"  [{w.get('code','?')}] {w.get('message','?')[:100]}")

    # 保存结果
    out_path = os.path.join(os.path.dirname(__file__), "reports", "data", f"688323_retest_{time.strftime('%m%d_%H%M')}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已保存: {out_path}")

except Exception as e:
    elapsed = time.time() - t0
    print(f"\n管线异常 ({elapsed:.0f}s): {e}")
    import traceback
    traceback.print_exc()
