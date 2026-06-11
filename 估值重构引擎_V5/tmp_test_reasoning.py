"""
对比 baseline agent 在不同 reasoning_effort 下的表现
"""
import json, time, requests, sys, os
sys.path.insert(0, 'src')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
from env_config import DEEPSEEK_API_KEY
from agent_baseline import BASELINE_SYSTEM_PROMPT, build_baseline_user_message

# 换一只股票
path = "reports/data/300806_20260609_1104.json"  # 斯迪克
d = json.load(open(path, encoding='utf-8'))
code = d['agent0']['stock_code']
name = d['agent0']['stock_name']

user_msg = build_baseline_user_message(code, name, d['agent0'], d['agent1'], None)

# 三组: 关思考, high, max
tests = [
    ("off",  {"type": "disabled"}),
    ("high", {"type": "enabled", "reasoning_effort": "high"}),
    ("max",  {"type": "enabled", "reasoning_effort": "max"}),
]

for label, thinking_cfg in tests:
    print(f"\n{'='*60}")
    print(f"  thinking = {label}")
    print(f"{'='*60}")

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
            "max_tokens": 8192,
            "temperature": 0.1,
            "stream": False,
            "thinking": thinking_cfg,
        },
        timeout=600,
    )
    elapsed = time.time() - t0
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})

    # 检查是否有 reasoning_tokens
    reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", "N/A")

    print(f"  耗时: {elapsed:.0f}s")
    print(f"  prompt_tokens: {usage.get('prompt_tokens')}")
    print(f"  completion_tokens: {usage.get('completion_tokens')}")
    print(f"  reasoning_tokens: {reasoning_tokens}")
    print(f"  输出字数: {len(content)}")

    # 保存
    out = f"tmp_reasoning_{label}.md"
    with open(out, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  保存: {out}")

print("\n=== 完成 ===")
