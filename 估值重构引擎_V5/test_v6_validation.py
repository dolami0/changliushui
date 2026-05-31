"""
V6 中期验证 — 端到端测试脚本

测试真实 Coze 记录，运行 V6 管线（Agent-0→1→2a→2b→3），
输出完整报告，与已有 V5 报告对比。
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 路径设置
SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent / "valuation_app"))

from agent0_pre_router import Agent0
from agent1_data_forge import DataForge, DataForgeError
from agent2a_narrative import NarrativeDiagnosis
from agent2b_routing import RouteJudgeV6
from agent3_scenario_asymmetry import ScenarioAsymmetry, precompute_wacc, precompute_bs_profile
from data_fetcher import DataFetcher
from coze_client import CozeClient
from env_config import DEEPSEEK_API_KEY


def load_config():
    config_path = Path(__file__).resolve().parent / "valuation_app" / "config.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def run_v6_pipeline(record: dict, deepseek_key: str) -> dict:
    """运行 V6 完整管线: Agent-0 → 1 → 2a → 2b → 3"""
    stock_code = (record.get("stock_code", "") or "").strip()
    stock_name = record.get("stock_name", "")

    if not stock_code:
        return {"status": "error", "error": "stock_code missing"}

    event_data = {
        "raw_event_text": record.get("raw_event_text", ""),
        "event_deduction": record.get("event_deduction", ""),
        "investment_theme": record.get("investment_theme", ""),
        "response_level": record.get("response_level", ""),
        "preliminary_reasoning": record.get("preliminary_reasoning", ""),
        "adversarial_thinking": record.get("adversarial_thinking", ""),
        "knowledge_supplement": record.get("knowledge_supplement", ""),
        "industry_expert_research": record.get("industry_expert_research", ""),
        "future": record.get("future", ""),
        "event_date": (record.get("bstudio_create_time", "") or record.get("event_date", ""))[:10],
        "event_source": record.get("event_source", ""),
        "stock_name": stock_name,
    }

    t_start = time.time()
    trace = {}

    # ── Agent-0: 预路由 ──
    t0 = time.time()
    a0 = Agent0()
    a0_result = a0.run(stock_code, event_data)
    trace["agent0_ms"] = round((time.time() - t0) * 1000)

    # ── Agent-1: 数据炼器 ──
    t0 = time.time()
    forge = DataForge()
    try:
        a1_result = forge.run(a0_result)
    except DataForgeError as e:
        return {"status": "terminated", "error": str(e), "trace": trace}
    trace["agent1_ms"] = round((time.time() - t0) * 1000)

    # ── Agent-2a: 叙事诊断 ──
    t0 = time.time()
    # WACC 预计算（给定价工具用）
    fetcher = DataFetcher()
    wacc_params = precompute_wacc(fetcher, stock_code, a1_result)
    a2a = NarrativeDiagnosis(deepseek_key=deepseek_key)
    a2a_result = a2a.run(a1_result, event_data, wacc_params)
    trace["agent2a_ms"] = round((time.time() - t0) * 1000)

    # ── Agent-2b: 路由判决 ──
    t0 = time.time()
    a2b = RouteJudgeV6(deepseek_key=deepseek_key)
    a2b_result = a2b.run(a1_result, a2a_result, event_data)
    trace["agent2b_ms"] = round((time.time() - t0) * 1000)

    # ── Agent-3: 推演裁决 ──
    t0 = time.time()
    a3 = ScenarioAsymmetry(deepseek_key=deepseek_key)
    rd = a2b_result.get("routing_decision", {})
    a3_result = a3.run(
        data_package=a1_result,
        routing_decision=rd,
        event_data=event_data,
        case_anchors=a2a_result.get("_case_anchors_text", ""),
        agent2a_output=a2a_result,
    )
    trace["agent3_ms"] = round((time.time() - t0) * 1000)

    trace["total_ms"] = round((time.time() - t_start) * 1000)

    return {
        "status": "done",
        "stock_code": stock_code,
        "stock_name": stock_name,
        "agent0": a0_result,
        "agent1": a1_result,
        "agent2a": a2a_result,
        "agent2b": a2b_result,
        "agent3": a3_result,
        "_trace": trace,
    }


def print_summary(result: dict):
    """打印可读的结果摘要。"""
    if result.get("status") != "done":
        print(f"   管线失败: {result.get('error', '?')}")
        return

    trace = result.get("_trace", {})
    a2a = result.get("agent2a", {})
    a2b = result.get("agent2b", {})
    a3 = result.get("agent3", {})
    a1 = result.get("agent1", {})

    # 基本信息
    core = a1.get("packages", {}).get("core", {}).get("fields", {})
    mcap = core.get("market_cap_yi", 0)
    np = core.get("net_profit_ttm_yi", 0)
    pe = core.get("pe_ttm", 0)
    pb = core.get("pb", 0)
    ps = core.get("ps_ttm", 0)
    roic = core.get("roic_pct", 0)

    print(f"   财务: 市值{mcap:.0f}亿 PE{pe:.1f}x PB{pb:.1f}x PS{ps:.1f}x ROIC{roic:.1f}% 净利{np:.1f}亿")
    print(f"  ️  异常: {core.get('caution_flags',[])}")

    # Agent-2a 诊断
    mn = a2a.get("market_narrative", {})
    ep = a2a.get("event_pricing", {})
    ep2 = ep.get("event_profile", {})
    pa = ep.get("pricing_assessment", {})
    sa = a2a.get("signal_audit", {})

    print(f"   锚: {mn.get('primary_anchor','?')} | "
          f"SOTP: {mn.get('sotp_triggered',False)}")
    print(f"   光谱: {ep2.get('distribution_shape','?')} "
          f"(T={ep2.get('timing_certainty','?')} "
          f"B={ep2.get('outcome_binaryness','?')} "
          f"P={ep2.get('precedent_richness','?')})")
    print(f"   计价: {pa.get('overall_priced_in','?')} ({pa.get('priced_in_estimate','?')})")
    print(f"   信号: step2d={sa.get('step2d_score','?')} — {sa.get('score_rationale','?')[:100]}")

    # Agent-2b 路由
    rd = a2b.get("routing_decision", {})
    cc = rd.get("constraint_compliance", {})
    print(f"   路由: 主={rd.get('primary_model','?')} 校验={rd.get('validation_models',[])} "
          f"策略={rd.get('validation_strategy','?')} "
          f"约束={cc.get('family_constraint_applied','?')} override={cc.get('constraint_override',False)}")
    print(f"   理由: {rd.get('routing_reason','?')[:150]}")

    # Agent-3 推演
    sv = a3.get("scenario_valuation", {})
    conf = a3.get("confidence", {})
    ta = a3.get("trade_annotation", {})
    vs = a3.get("valuation_summary", sv)

    details = sv.get("scenario_details", {})
    if isinstance(details, list):
        details = {d.get("scenario",""): d for d in details}

    print(f"   三情景:")
    for s in ("bear", "base", "bull"):
        d = details.get(s, {})
        print(f"     {s:5s}: prob={d.get('probability',0):.0%} "
              f"upside={d.get('upside_pct',0):+.1f}% "
              f"mcap={d.get('target_mcap_yi',0):.0f}亿 "
              f"scenario: {d.get('scenario_narrative','?')[:80]}")

    pw_upside = vs.get("probability_weighted_upside_pct", 0)
    asym = vs.get("asymmetry_ratio", 0)
    print(f"   加权涨幅: {pw_upside:+.1f}% | 非对称: {asym:.1f}x")

    # 置信度
    dims = conf.get("dimensions", {})
    dim_str = " | ".join(f"{d.get('label','?')}={d.get('score','?')}" for d in dims.values())
    print(f"   置信度: {conf.get('overall_score','?')}/10 ({conf.get('overall_label','?')}) [{dim_str}]")

    # 交易标注
    print(f"   交易: {ta.get('tier','?')} | {ta.get('total_score','?')} | {ta.get('tier_note','?')[:100]}")

    # 耗时
    print(f"  ⏱️  耗时: A0={trace.get('agent0_ms','?')}ms A1={trace.get('agent1_ms','?')}ms "
          f"A2a={trace.get('agent2a_ms','?')}ms A2b={trace.get('agent2b_ms','?')}ms "
          f"A3={trace.get('agent3_ms','?')}ms | 总计={trace.get('total_ms','?')}ms")


def main():
    cfg = load_config()
    deepseek_key = cfg.get("deepseek_api_key", "") or DEEPSEEK_API_KEY

    print("=" * 80)
    print("V6 Pipeline — Mid-term Validation")
    print("=" * 80)

    # 拉取 Coze 记录
    print("\n[1] Querying Coze Agent0 table...")
    client = CozeClient(
        token=cfg["coze_sat_token"],
        workspace_id=cfg["coze_workspace_id"],
    )
    records = client.query_all_records(cfg["agent0_database_id"])

    # 过滤: 只测有完整字段的 L4 记录
    test_records = []
    for r in records:
        sc = (r.get("stock_code", "") or "").strip()
        if sc and r.get("investment_theme") and r.get("raw_event_text"):
            test_records.append(r)

    print(f"  有效记录: {len(test_records)}/{len(records)}")
    print(f"  测试数: 3 条\n")

    # 执行管线
    results = []
    for i, rec in enumerate(test_records[:3]):
        code = rec.get("stock_code", "?")
        name = rec.get("stock_name", "?")
        print(f"\n{'='*80}")
        print(f"#{i+1} [{code}] {name}")
        print(f"{'='*80}")

        result = run_v6_pipeline(rec, deepseek_key)
        results.append(result)
        print_summary(result)

    # 保存结果
    out_path = Path(__file__).resolve().parent / "docs" / "v6_validation_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        safe_results = []
        for r in results:
            # 过滤无法序列化的对象
            safe = {}
            for k, v in r.items():
                try:
                    json.dumps(v, ensure_ascii=False, default=str)
                    safe[k] = v
                except Exception:
                    safe[k] = str(v)[:200]
            safe_results.append(safe)
        json.dump(safe_results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n{'='*80}")
    print(f"结果已保存: {out_path}")
    print(f"共 {len(results)} 条, {sum(1 for r in results if r.get('status')=='done')} 成功")


if __name__ == "__main__":
    main()
