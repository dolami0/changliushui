"""SOTP Agent-3s 独立测试 — 使用已保存的 688805 数据"""
import json, sys, time
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))

from agent3s_sotp import SOTPScenarioAsymmetry
from agent3_scenario_asymmetry import precompute_wacc
from data_fetcher import DataFetcher
from env_config import DEEPSEEK_API_KEY

# 加载保存的报告数据
report_file = Path(__file__).resolve().parent / "reports" / "data" / "688805_20260528_2209.json"
if not report_file.exists():
    # 尝试找最新的
    data_dir = Path(__file__).resolve().parent / "reports" / "data"
    files = sorted(data_dir.glob("688805_*.json"), reverse=True)
    report_file = files[0] if files else None

if not report_file or not report_file.exists():
    print("未找到 688805 报告数据！")
    sys.exit(1)

print(f"加载报告: {report_file.name}")
with open(report_file, encoding="utf-8") as f:
    saved = json.load(f)

# 提取必要数据
a0 = saved.get("agent0", {})
a1 = saved.get("agent1", {})
a2a = saved.get("agent2a", {})

code = saved.get("audit", {}).get("stock_code", "688805")
name = saved.get("audit", {}).get("stock_name", "健信超导")

# 检查 SOTP 是否触发
sotp_triggered = a2a.get("market_narrative", {}).get("sotp_triggered", False)
sas = a2a.get("market_narrative", {}).get("secondary_anchors", [])
print(f"SOTP触发: {sotp_triggered} | 副锚: {len(sas)}个")
for sa in sas:
    print(f"  - {sa.get('segment','?')}: anchor={sa.get('anchor','?')} share={sa.get('revenue_share_pct',0):.1f}%")

# 从 agent0 提取 event_data
event_data = {}
pr = a0.get("pre_routing_result", {})
# event_data 需要 raw_event_text, investment_theme, event_deduction 等
# 实际上 agent0 输出中不包含原始 event_data（那是从 Coze 来的）
# 我们需要从 saved 的上下文中找，或者模拟一个最小集

# 构造最小 event_data（SOTP agent 主要需要行业研究等背景信息）
event_data = {
    "investment_theme": a2a.get("market_narrative", {}).get("narrative_summary", ""),
    "event_deduction": "",
    "adversarial_thinking": "",
    "knowledge_supplement": "",
    "industry_expert_research": "",
    "raw_event_text": "",
    "preliminary_reasoning": "",
    "future": "",
}

print(f"\nWACC 预计算...")
fetcher = DataFetcher()
wacc = precompute_wacc(fetcher, code, a1)
print(f"  wacc={wacc.get('wacc_pct','?')}% rf={wacc.get('rf_pct','?')}% beta={wacc.get('beta','?')} erp={wacc.get('erp_pct','?')}%")

print(f"\n=== 启动 SOTP Agent-3s ===")
t0 = time.time()

a3s = SOTPScenarioAsymmetry(deepseek_key=DEEPSEEK_API_KEY)
# 从已保存报告提取 agent2b 输出（键名为 "agent2" 向后兼容）
a2b = saved.get("agent2", {})
try:
    result = a3s.run(
        data_package=a1,
        agent2a_output=a2a,
        agent2b_output=a2b,
        event_data=event_data,
        wacc_params=wacc,
    )
    elapsed = time.time() - t0
    print(f"\n耗时: {elapsed:.0f}s")

    # 打印关键结果
    vs = result.get("valuation_summary", {})
    sv = result.get("scenario_valuation", {})
    details = sv.get("scenario_details", {})

    print(f"\n=== SOTP 估值结果 ===")
    print(f"概率加权涨幅: {vs.get('probability_weighted_upside_pct',0):+.1f}%")
    print(f"不对称比: {vs.get('asymmetry_ratio',0):.1f}x")
    print(f"概率加权市值: {vs.get('probability_weighted_mcap_yi',0):.1f}亿")

    for s in ("bear", "base", "bull"):
        d = details.get(s, {})
        print(f"\n{s.upper()}:")
        print(f"  概率: {d.get('probability',0):.0%}")
        print(f"  目标市值: {d.get('target_mcap_yi',0):.1f}亿")
        print(f"  涨幅: {d.get('upside_pct',0):+.1f}%")
        print(f"  叙事主锚: {d.get('_primary_value_yi',0):.1f}亿 | 其他业务: {d.get('_other_value_yi',0):.1f}亿 | 净现金: {d.get('_net_cash_yi',0):.1f}亿")
        print(f"  叙事: {d.get('scenario_narrative','?')[:100]}")

    print(f"\n置信度: {result.get('confidence',{}).get('overall_score','?')}/10")
    print(f"交易标注: {result.get('trade_annotation',{}).get('tier','?')}")
    print(f"预期差: {result.get('expectation_gap',{}).get('level','?')}")

    # 对比原报告
    orig_a3 = saved.get("agent3", {})
    orig_vs = orig_a3.get("valuation_summary", {})
    if orig_vs:
        print(f"\n=== 对比原 Agent-3 (Model J 黑箱) ===")
        print(f"原概率加权涨幅: {orig_vs.get('probability_weighted_upside_pct',0):+.1f}%")
        print(f"原不对称比: {orig_vs.get('asymmetry_ratio',0):.1f}x")
        new_upside = vs.get('probability_weighted_upside_pct', 0)
        old_upside = orig_vs.get('probability_weighted_upside_pct', 0)
        print(f"差异: {new_upside - old_upside:+.1f}ppt")

except Exception as e:
    elapsed = time.time() - t0
    print(f"\n耗时: {elapsed:.0f}s")
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
