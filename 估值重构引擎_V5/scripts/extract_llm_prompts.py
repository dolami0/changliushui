"""提取所有 LLM System Prompt 并导出为独立文档。"""
import os, re

src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
output_path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'llm_prompts_inventory.md')

agents = [
    ('agent2a_narrative.py', 'NARRATIVE_DIAGNOSIS_PROMPT',
     'Agent-2a 叙事诊断', 'Phase 2a: 锚识别 → 计价判断 → 信号审核'),
    ('agent2b_routing.py', 'ROUTING_V6_PROMPT',
     'Agent-2b 路由判官', 'Phase 2b: 模型选择 + 校验策略'),
    ('agent2_route_judge.py', 'ROUTE_JUDGE_SYSTEM_PROMPT',
     'Agent-2 路由判官(旧)', 'Phase 2(旧): 模型选择(已被2b替代)'),
    ('agent3_scenario_asymmetry.py', 'SCENARIO_SYSTEM_PROMPT',
     'Agent-3 情景推演', 'Phase 3: 三情景参数推演 + 估值计算'),
    ('agent3s_sotp.py', 'SOTP_SYSTEM_PROMPT',
     'Agent-3s SOTP分叉', 'Phase 3s: 分部估值 + 情景推演'),
    ('rnpv/agent2r_pipeline_valuation.py', 'RNPV_VALUATION_PROMPT',
     'rNPV Agent-2r 管线估值', 'rNPV Phase 2: 管线药物估值'),
    ('rnpv/agent3r_scenario.py', 'RNPV_SCENARIO_PROMPT',
     'rNPV Agent-3r 情景推演', 'rNPV Phase 3: 管线情景概率化'),
]

lines = []
lines.append('# 估值重构引擎 V6 — LLM 调用清单')
lines.append('')
lines.append('> 自动生成，包含所有 LLM 调用的用途、管线位置和完整 System Prompt')
lines.append('')
lines.append('---')
lines.append('')
lines.append('## 管线架构总览')
lines.append('')
lines.append('```')
lines.append('Agent-0(无LLM) → Agent-1(无LLM) → Agent-2a(LLM) → [分叉]')
lines.append('  ├─ standard → Agent-2b(LLM) → Agent-3(LLM)')
lines.append('  ├─ sotp     → Agent-3s(LLM, 跳过2b)')
lines.append('  └─ rnpv     → Agent-1r(无LLM) → Agent-2r(LLM) → Agent-3r(LLM)')
lines.append('```')
lines.append('')
lines.append('| Agent | LLM调用次数 | System Prompt 大小 | 管线位置 |')
lines.append('|-------|------------|-------------------|---------|')
lines.append('| Agent-0 预路由 | 0 | - | 入口 |')
lines.append('| Agent-1 数据炼器 | 0 | - | 数据组装 |')

total_calls = 0
for fname, varname, label, stage in agents:
    fpath = os.path.join(src_dir, fname)
    if not os.path.exists(fpath):
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    start = content.find(varname + ' = """')
    if start < 0:
        start = content.find(varname + ' = """')
    if start < 0:
        continue
    body_start = content.index('"""', start) + 3
    body_end = content.index('\n"""', body_start)
    prompt_text = content[body_start:body_end]

    calls = content.count('call_deepseek(') + content.count('_call_deepseek(')
    total_calls += calls

    prompt_len = len(prompt_text)
    lines.append(f'| {label} | {calls} | {prompt_len}字符 | {stage} |')

lines.append('')
lines.append('---')
lines.append('')

for fname, varname, label, stage in agents:
    fpath = os.path.join(src_dir, fname)
    if not os.path.exists(fpath):
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    start = content.find(varname + ' = """')
    if start < 0:
        continue
    body_start = content.index('"""', start) + 3
    body_end = content.index('\n"""', body_start)
    prompt_text = content[body_start:body_end]

    lines.append(f'## {label}')
    lines.append('')
    lines.append(f'**管线阶段**: {stage}')
    lines.append(f'**源码位置**: `src/{fname}`')
    lines.append(f'**变量名**: `{varname}`')
    lines.append('')
    lines.append('### System Prompt')
    lines.append('')
    lines.append('```')
    lines.append(prompt_text.strip())
    lines.append('```')
    lines.append('')
    lines.append('---')
    lines.append('')

with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'Done: {output_path}')
print(f'Total agents: {len(agents)}, Total LLM calls per pipeline run: {total_calls}')
