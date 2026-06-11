"""直接用 orchestrator 重跑 002653 海思科（Flash 模型），输出新报告。"""
import json, sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from orchestrator import ValuationOrchestrator
from env_config import DEEPSEEK_API_KEY

# 读取原始 event_data
data_path = os.path.join(os.path.dirname(__file__), '..', 'reports', 'data', '002653_20260602_1115.json')
with open(data_path, 'r', encoding='utf-8') as f:
    old = json.load(f)

event_data = old.get('agent0', {})
stock_code = event_data.get('stock_code', '002653')
stock_name = event_data.get('stock_name', '海思科')
print(f"事件: {stock_name} ({stock_code})")
print(f"日期: {event_data.get('bstudio_create_time', event_data.get('event_date', '?'))}")
print(f"模型: deepseek-v4-flash (新)")

# 进度回调
def progress_cb(agent, step, total, status, msg):
    print(f"  [{agent}] {status}: {msg}")

# 跑管线
orch = ValuationOrchestrator(api_key=DEEPSEEK_API_KEY)
t0 = time.time()
result = orch.run(stock_code, event_data=event_data, progress_cb=progress_cb)
elapsed = time.time() - t0
print(f"\n完成! 耗时 {elapsed:.1f}s")
print(f"管线类型: {result.get('pipeline_type', 'standard')}")

# 提取关键结论
a3 = result.get('agent3', {})
vs = a3.get('valuation_summary', {})
conf = a3.get('confidence', {})
a2 = result.get('agent2', {})
a2a = result.get('agent2a', a2)
sotp = a2.get('sotp_total', {}) if isinstance(a2, dict) else {}

print(f"\n=== 核心结论 ===")
print(f"概率加权涨幅: {vs.get('probability_weighted_upside_pct', 0):+.1f}%")
print(f"不对称比: {vs.get('asymmetry_ratio', 0):.2f}x")
print(f"置信度: {conf.get('overall_score', '?')}/10 ({conf.get('overall_label', '?')})")
print(f"主模型: {a2.get('routing_decision',{}).get('primary_model','?') if isinstance(a2,dict) else '?'}")

if sotp:
    print(f"\nSOTP: 成熟{sotp.get('mature_products_yi','?')}亿 + 管线{sotp.get('pipeline_yi','?')}亿 = {sotp.get('total_fair_value_yi','?')}亿")
    print(f"当前市值: {sotp.get('current_mcap_yi','?')}亿, 上行: {sotp.get('upside_pct','?')}%")

# 情景
for sc in a3.get('scenarios', []):
    print(f"  {sc.get('name','?')}: p={sc.get('probability_pct',0)}% upside={sc.get('upside_pct',0):+.1f}% mcap={sc.get('target_mcap_yi',0):.0f}亿")

# 保存结果
ts = time.strftime('%Y%m%d_%H%M')
out_path = os.path.join(os.path.dirname(__file__), '..', 'reports', 'data', f'002653_flash_{ts}.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nJSON 已保存: {out_path}")

# 生成 markdown 报告
try:
    from valuation_app.report_builder import build_markdown_report
    a0 = result.get('agent0', {})
    a1 = result.get('agent1', {})
    r_a2a = result.get('agent2a', {})
    md = build_markdown_report(a0, a1, a2, a3, agent2a=r_a2a)
    md_path = os.path.join(os.path.dirname(__file__), '..', 'reports', f'002653_flash_{ts}.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md)
    print(f"Markdown 报告: {md_path}")
except Exception as e:
    print(f"报告生成失败: {e}")

print(f"\n总耗时: {elapsed:.1f}s")
