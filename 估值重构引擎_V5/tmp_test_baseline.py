"""
快速测试 Agent-Baseline 投资地图输出质量
用法: python tmp_test_baseline.py
"""
import json, sys, time, os
sys.path.insert(0, 'src')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from agent_baseline import BaselineMapDrawer

# 测试标的: (文件路径, 标签)
TESTS = [
    ("reports/data/688146_20260609_1604.json", "中船特气 - 周期+成长"),
    ("reports/data/300806_20260609_1104.json", "斯迪克 - 转型期"),
    ("reports/data/688549_20260608_1718.json", "中巨芯 - 亏损扩张期"),
    ("reports/data/000983_20260608_1806.json", "山西焦煤 - 周期型"),
    ("reports/data/688787_20260608_2206.json", "海天瑞声 - 微利成长"),
]

for path, label in TESTS:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    d = json.load(open(path, encoding='utf-8'))
    a0 = d['agent0']
    a1 = d['agent1']
    code = a0.get('stock_code', '?')
    name = a0.get('stock_name', code)

    # 尝试获取火山数据（可能不存在）
    volc = None
    volc_path = path.replace('.json', '_volc.json')
    if os.path.exists(volc_path):
        volc = json.load(open(volc_path, encoding='utf-8'))

    drawer = BaselineMapDrawer()
    t0 = time.time()
    result = drawer.run(code, name, a0, a1, volc_data=volc)
    elapsed = time.time() - t0

    report = result.get('baseline_report', '')
    print(f"\n[OK {elapsed:.0f}s, {len(report)} chars]")

    # 保存完整输出
    out_path = f'tmp_baseline_{code}.md'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"  -> {out_path}")

print("\n=== 完成 ===")
