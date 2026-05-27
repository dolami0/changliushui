# -*- coding: utf-8 -*-
"""
望气工作流评测脚本 (v2 — 纯推理模式)
评测模式下不联网搜索，仅用 news_content 原文推理，避免未来信息泄露
"""
import sys, os, json, time

# 确保工作目录和 src 路径正确
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from industry_chain_workflow import IndustryChainWorkflow

LOG_FILE = 'eval_run.log'
RESULT_FILE = 'eval_results.json'

def log(msg: str):
    """同时写文件和终端"""
    print(msg, flush=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


# ── 加载 ──
with open('valuation_app/config.json') as f:
    cfg = json.load(f)
with open('evals/industry_chain_eval.json', encoding='utf-8') as f:
    evals = json.load(f)

wf = IndustryChainWorkflow(deepseek_key=cfg['deepseek_api_key'])
cases = evals['cases']

# 清空日志
with open(LOG_FILE, 'w', encoding='utf-8') as f:
    f.write(f'评测启动 {time.strftime("%Y-%m-%d %H:%M:%S")} | {len(cases)} 条 | eval_mode=True (无联网)\n\n')


# ── 评分函数 ──
def score_case(case: dict, result: dict) -> dict:
    gt = case['ground_truth']
    tp = result.get('top_pick', {})
    ru = result.get('runner_up', {})

    # 1. 产业链匹配
    pred_chain = result.get('chain_analysis', {}).get('chain_overview', {}).get('industry', '')
    true_chain = case.get('industry_chain', '')
    chain_match = 1.0 if true_chain and true_chain in pred_chain else 0.5

    # 2. 节点命中（关键词模糊匹配）
    true_nodes = [n['node_name'] for n in gt.get('top_nodes', [])]
    pred_nodes = []
    for n in result.get('chain_analysis', {}).get('top_two_nodes', []):
        pred_nodes.append(n.get('node_name', ''))

    node_hits = 0
    for tn in true_nodes:
        # 提取核心关键词（括号内+括号外）
        tn_core = tn.replace('（', '').replace('）', '').replace('/', '')
        for pn in pred_nodes:
            pn_clean = pn.replace('（', '').replace('）', '').replace('/', '')
            # 检查至少有 2 个共同字
            common = set(tn_core) & set(pn_clean)
            if len(common) >= 2:
                node_hits += 1
                break
    node_hit_rate = node_hits / max(len(true_nodes), 1)

    # 3. 个股命中
    true_picks = {p['stock_code'] for p in gt.get('top_picks', [])}
    all_true = {p['stock_code'] for p in gt.get('top_picks', [])}
    all_true.update(p['stock_code'] for p in gt.get('reference_picks', []))

    pred_codes = set()
    if tp.get('stock_code'):
        pred_codes.add(tp['stock_code'])
    if ru.get('stock_code'):
        pred_codes.add(ru['stock_code'])

    top_hits = sum(1 for c in pred_codes if c in true_picks)
    any_hits = sum(1 for c in pred_codes if c in all_true)

    top_pick_hit = top_hits / max(len(true_picks), 1)
    any_hit = any_hits / max(len(pred_codes), 1) if pred_codes else 0

    # 4. 无高赔率标的合理性
    no_pick = tp.get('stock_name', '') == '无高赔率标的'
    all_low_return = all(p.get('actual_return_pct', 0) < 50 for p in gt.get('top_picks', []))
    no_pick_valid = 1.0 if (no_pick and all_low_return) else (0.0 if no_pick else 1.0)

    total = (
        chain_match * 0.10 +
        node_hit_rate * 0.30 +
        top_pick_hit * 0.40 +
        any_hit * 0.10 +
        no_pick_valid * 0.10
    )
    return {
        'chain_match': chain_match,
        'node_hit_rate': node_hit_rate,
        'top_pick_hit': top_pick_hit,
        'any_hit': any_hit,
        'no_pick_valid': no_pick_valid,
        'total': total,
    }


# ── 逐条跑 ──
all_results = []
for i, case in enumerate(cases):
    cid = case['id']
    chain_name = case['industry_chain']
    log(f'=== [{i+1}/{len(cases)}] {cid}: {chain_name} ===')
    log(f'  资讯: {case["news_content"][:80]}...')

    record = {
        'id': cid,
        'news_content': case['news_content'],
        'step_one': f'产业模式, level=5, {chain_name}',
        'level': 5,
        'mode': '产业模式',
    }

    t0 = time.time()
    result = wf.run_on_record(record, eval_mode=True)  # 关键：评测模式
    elapsed = time.time() - t0

    scores = score_case(case, result)
    tp = result.get('top_pick', {})
    ru = result.get('runner_up', {})

    # 节点预测
    pred_nodes = []
    for n in result.get('chain_analysis', {}).get('top_two_nodes', []):
        pred_nodes.append(n.get('node_name', ''))

    # 写入逐条结果
    entry = {
        'id': cid,
        'chain_true': case['industry_chain'],
        'chain_pred': result.get('chain_analysis', {}).get('chain_overview', {}).get('industry', ''),
        'nodes_pred': pred_nodes,
        'nodes_true': [n['node_name'] for n in case['ground_truth']['top_nodes']],
        'top_pick_code': tp.get('stock_code', ''),
        'top_pick_name': tp.get('stock_name', ''),
        'top_pick_node': tp.get('node_name', ''),
        'runner_up_code': ru.get('stock_code', ''),
        'runner_up_name': ru.get('stock_name', ''),
        'runner_up_node': ru.get('node_name', ''),
        'scores': scores,
        'elapsed': round(elapsed),
    }
    all_results.append(entry)

    # 日志
    gt_picks = case['ground_truth']['top_picks']
    ref_text = ', '.join(
        f'{p["stock_name"]}({p["stock_code"]}, +{p["actual_return_pct"]}%)'
        for p in gt_picks
    )
    log(f'  预测: {tp.get("stock_name","?")}({tp.get("stock_code","?")}) / '
        f'{ru.get("stock_name","?")}({ru.get("stock_code","?")})')
    log(f'  参考: {ref_text}')
    log(f'  节点预测: {pred_nodes}')
    log(f'  评分: 链={scores["chain_match"]:.0%} 节={scores["node_hit_rate"]:.0%} '
        f'首={scores["top_pick_hit"]:.0%} 任={scores["any_hit"]:.0%} 综合={scores["total"]:.0%}')
    log(f'  耗时: {elapsed:.0f}s\n')

    # 立即保存（增量写入，防止中断丢数据）
    with open(RESULT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'results': all_results}, f, ensure_ascii=False, indent=2)


# ── 汇总 ──
if all_results:
    avg_total = sum(r['scores']['total'] for r in all_results) / len(all_results)
    avg_chain = sum(r['scores']['chain_match'] for r in all_results) / len(all_results)
    avg_node = sum(r['scores']['node_hit_rate'] for r in all_results) / len(all_results)
    avg_top = sum(r['scores']['top_pick_hit'] for r in all_results) / len(all_results)
    avg_any = sum(r['scores']['any_hit'] for r in all_results) / len(all_results)
    avg_time = sum(r['elapsed'] for r in all_results) / len(all_results)

    summary = {
        'eval_mode': 'pure_reasoning (no web search)',
        'cases_count': len(all_results),
        'avg_total': round(avg_total, 3),
        'avg_chain_match': round(avg_chain, 3),
        'avg_node_hit': round(avg_node, 3),
        'avg_top_pick_hit': round(avg_top, 3),
        'avg_any_hit': round(avg_any, 3),
        'avg_elapsed_sec': round(avg_time, 0),
    }
    log('=' * 60)
    log(f'评测汇总 (纯推理模式，无联网搜索)')
    log(f'  平均综合分: {avg_total:.0%}')
    log(f'  产业链匹配: {avg_chain:.0%}')
    log(f'  节点命中率: {avg_node:.0%}')
    log(f'  首选命中率: {avg_top:.0%}')
    log(f'  任意命中率: {avg_any:.0%}')
    log(f'  平均耗时: {avg_time:.0f}s')
    log('=' * 60)

    # 写入最终结果
    full = {
        'summary': summary,
        'details': all_results,
    }
    with open(RESULT_FILE, 'w', encoding='utf-8') as f:
        json.dump(full, f, ensure_ascii=False, indent=2)
    log(f'\n结果已保存: {RESULT_FILE}')
else:
    log('\n 没有跑出任何结果')
