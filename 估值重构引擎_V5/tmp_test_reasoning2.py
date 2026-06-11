"""
多股票对比 high vs max
"""
import json, time, requests, sys, os
sys.path.insert(0, 'src')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
from env_config import DEEPSEEK_API_KEY
from agent_baseline import BASELINE_SYSTEM_PROMPT, build_baseline_user_message

TESTS = [
    ("reports/data/000983_20260608_1806.json", "山西焦煤 - 周期型"),
    ("reports/data/688549_20260608_1718.json", "中巨芯 - 亏损扩张"),
]

results = []

for path, label in TESTS:
    d = json.load(open(path, encoding='utf-8'))
    code = d['agent0']['stock_code']
    name = d['agent0']['stock_name']
    user_msg = build_baseline_user_message(code, name, d['agent0'], d['agent1'], None)

    for effort in ['high', 'max']:
        t0 = time.time()
        resp = requests.post(
            DEEPSEEK_API,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            json={
                "model": "deepseek-v4-pro",
                "messages": [
                    {"role": "system", "content": BASELINE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 8192, "temperature": 0.1, "stream": False,
                "thinking": {"type": "enabled"},
                "reasoning_effort": effort,
            },
            timeout=600,
        )
        elapsed = time.time() - t0
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        reasoning = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)

        # Quick quality checks
        lifecycle_matches = []
        for kw in ['转型', '成长中期', '成长早期', '成熟', '周期', '亏损', '从0到1']:
            if kw in content[:200]:
                lifecycle_matches.append(kw)
        has_milestone_table = '| 时间' in content
        has_vulnerability = '脆弱' in content
        anchor_count = content.count('| 高 |') + content.count('| 中 |') + content.count('| 低 |')

        results.append({
            'stock': label, 'effort': effort,
            'elapsed': elapsed, 'chars': len(content),
            'completion': usage.get('completion_tokens', 0),
            'reasoning': reasoning,
            'lifecycle': '+'.join(lifecycle_matches) if lifecycle_matches else '?',
            'milestone': has_milestone_table,
            'vulnerability': has_vulnerability,
            'anchors': anchor_count,
        })

        out = f"tmp_r_{code}_{effort}.md"
        with open(out, 'w', encoding='utf-8') as f:
            f.write(content)

# Print comparison table
print(f"\n{'Stock':<20} {'E':>5} {'Time':>5} {'Comp':>6} {'Reason':>6} {'Chars':>6} {'Lifecycle':<20} {'MS':>3} {'Vuln':>4} {'Anc':>4}")
print("-" * 95)
for r in results:
    print(f"{r['stock']:<20} {r['effort']:>5} {r['elapsed']:>4.0f}s {r['completion']:>5} {r['reasoning']:>5} {r['chars']:>5} {r['lifecycle']:<20} {'Y' if r['milestone'] else 'N':>3} {'Y' if r['vulnerability'] else 'N':>4} {r['anchors']:>4}")

# Summary stats
for effort in ['high', 'max']:
    subset = [r for r in results if r['effort'] == effort]
    avg_time = sum(r['elapsed'] for r in subset) / len(subset)
    avg_chars = sum(r['chars'] for r in subset) / len(subset)
    avg_reason = sum(r['reasoning'] for r in subset) / len(subset)
    print(f"\n{effort}: avg {avg_time:.0f}s, {avg_chars:.0f} chars, {avg_reason:.0f} reasoning tokens")

print("\nDone")
