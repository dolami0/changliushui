"""
估值重构引擎 V5 — 统一应用入口

用法:
    python main.py 300476                      # 单股完整分析
    python main.py 300476 --event event.json     # 带事件数据
    python main.py 300476 688256 --batch         # 批量分析
    python main.py 300476 --output report.md     # 输出Markdown报告

流程: Agent-0(预路由) → Agent-1(数据炼器) → Agent-2(路由判官) → Agent-3(推演裁决)
"""

import argparse
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 修复Windows终端UTF-8编码
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 添加父目录的 src 到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orchestrator import Orchestrator
from env_config import DEEPSEEK_API_KEY


# ═══════════════════════════════════════
# 配置
# ═══════════════════════════════════════

def load_config():
    """加载API密钥配置"""
    config_path = Path(__file__).resolve().parent / "config.json"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_event(stock_code: str, event_path: str | None = None) -> dict | None:
    """加载事件数据——从文件或agent0表"""
    if event_path:
        p = Path(event_path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return None


# ═══════════════════════════════════════
# 核心管线
# ═══════════════════════════════════════

def run_pipeline(stock_code: str, event: dict | None = None, deepseek_key: str | None = None):
    """完整 V5 4-Agent 估值重构管线"""
    results = {"stock_code": stock_code, "started_at": datetime.now().isoformat()}

    orch = Orchestrator(deepseek_key=deepseek_key or DEEPSEEK_API_KEY)
    t0 = time.time()
    result = orch.run(stock_code, event)
    results["agent_output"] = result
    results["time_s"] = round(time.time() - t0)

    if result.get("status") != "done":
        results["error"] = result.get("error", "管线执行失败")
        return results

    # 提取 Agent3 报告
    a3 = result.get("agent3", {})
    a2 = result.get("agent2", {})
    a1 = result.get("agent1", {})

    # 组装兼容旧 main.py 输出格式
    core = a1.get("packages", {}).get("core", {}).get("fields", {})
    report = {
        **a3,  # 展开 Agent3 全部子结构
        "report_meta": {
            "stock_code": stock_code,
            "stock_name": core.get("stock_name", event.get("stock_name", stock_code) if event else stock_code),
            "industry": a1.get("industry", ""),
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "version": "5.0",
        },
        "_timings": {"total_s": results["time_s"]},
    }
    return report


# ═══════════════════════════════════════
# 输出格式化
# ═══════════════════════════════════════

def print_summary(report: dict):
    """终端友好摘要——含完整校准框架和追踪框架"""
    meta = report["report_meta"]
    vr = report["valuation_routing"]
    sanity = report["market_sanity"]
    vs = report["valuation_summary"]
    gap = report["expectation_gap"]
    conf = report["confidence"]
    ta = report["trade_annotation"]
    timings = report.get("_timings", {})

    print(f"""
╔══════════════════════════════════════════════════════════╗
║  估值重构报告: {meta['stock_name']}({meta['stock_code']}) | {meta['industry']}
║  {meta['report_date']} | v{meta['version']} | 总耗时 {timings.get('total_s','?')}s
╚══════════════════════════════════════════════════════════╝

═══ 估值路由 ═══
  主模型: {vr['primary_model']}  校验: {vr['secondary_model']}
  方法: {vr['method_used']}  理由: {vr['routing_reason']}

═══ 市场检测 ═══
  {sanity['bs_level']}
  EV={sanity.get('ev_yi','?')}亿 | NOPAT={sanity.get('nopat_yi','?')}亿
  隐含g={sanity.get('implied_g_pct','?')}% | 市场溢价{sanity.get('market_premium_pct','?')}%
  PE分位={sanity.get('pe_historical_rank','?')} | PB={sanity.get('pb','?')}x

═══ 参数推演校准框架 ═══
  事件前: {gap.get('current_market_story','?')}
  事件冲击: {gap.get('event_story','?')}

═══ 预期差 ═══
  {gap['level']} | {gap['note']}
  概率加权涨幅: {vs['probability_weighted_upside_pct']:.1f}%
  不对称比: {vs['asymmetry_ratio']:.1f} | {vs['quality_flag']}

═══ 三情景推演 ═══""")

    for s in report.get("scenarios", []):
        arrow = "▲" if s["upside_pct"] > 0 else "▼"
        print(f"  {s['name']:6s} {s['probability_pct']:3d}% {arrow} {abs(s['upside_pct']):5.1f}%  → {s['target_mcap_yi']:.0f}亿")

    # 案例比对
    cc = report.get("case_comparison_summary", {})
    cases = cc.get("compared_cases", [])
    if cases:
        print(f"\n═══ 案例比对校准 ═══")
        pi = cc.get("parameter_impact", {})
        print(f"  综合参数折扣: {pi.get('target_param_discount_pct','?')}%")
        print(f"  校准理由: {pi.get('adjustment_rationale','?')[:120]}")
        for c in cases:
            dims = c.get("six_dimension_judgment", {})
            better = sum(1 for v in dims.values() if v.startswith("优于"))
            worse = sum(1 for v in dims.values() if v.startswith("劣于"))
            print(f"  vs {c['case_code']}: 折扣{c['comprehensive_discount_pct']}% ({better}优于/{worse}劣于)")

    print(f"""
═══ 置信度 {conf['overall_score']}/10 ({conf['overall_label']}) ═══""")
    for dim, d in conf["dimensions"].items():
        print(f"  {d['label']}: {d['score']}/10  {d['note'][:50]}")

    print(f"""
═══ 交易标注 ═══
  {ta['tier']} ({ta['total_score']})""")
    for sig in ta["alignment_signals"]:
        print(f"  {'S' if '赔率' in sig else 'M' if '市场' in sig else 'T' if '传导' in sig else 'V' if '模型' in sig else ' '} {sig}")
    print(f"  → {ta['suggested_action']}")

    # 事件追踪框架 (完整)
    kpis = report.get("monitoring_kpis", {})
    if isinstance(kpis, dict):
        # 通用解析: 接受 tracking_framework 嵌套或顶层两种结构
        tf = kpis.get("tracking_framework", {})
        if not isinstance(tf, dict):
            tf = {}
        # 如果LLM把数据放在顶层,合并
        for k, v in kpis.items():
            if k != "tracking_framework" and k not in tf:
                tf[k] = v

        meta_kpi = tf.get("meta", {})
        if meta_kpi:
            print(f"\n═══ 事件追踪框架 ═══")
            print(f"  传导链: {meta_kpi.get('event_chain','?')[:150]}")
            print(f"  关键假设: {meta_kpi.get('key_assumption','?')[:120]}")
            print(f"  Bear触发: {meta_kpi.get('bear_trigger','?')[:120]}\n")

        # 时间线 — 多层查找
        timeline = tf.get("timeline", [])
        if not timeline:
            for k, v in tf.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and ('date' in v[0] or 'node' in v[0]):
                    timeline = v
                    break
        if timeline:
            print(f"  【事件时间线】({len(timeline)}节点)")
            for t in timeline:
                if not isinstance(t, dict): continue
                status = t.get('status', '')
                marker = "" if status == "已达成" else "○"
                print(f"  {marker} {t.get('date','?')} | {str(t.get('event', t.get('expected','?')))[:80]}")
                threat = t.get('threat', '')
                if threat: print(f"      {str(threat)[:80]}")

        # KPI分类 — 通用解析(从tf中找所有list[dict]类型的值)
        kpi_cats = tf.get("kpi_categories", tf.get("categories", {}))
        if not kpi_cats:
            for k, v in tf.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and k not in ('timeline',):
                    kpi_cats[k] = v
                elif isinstance(v, dict) and k not in ('meta',):
                    for k2, v2 in v.items():
                        if isinstance(v2, list) and len(v2) > 0 and isinstance(v2[0], dict):
                            kpi_cats[k2] = v2
        for cat_key, items in kpi_cats.items():
            if not isinstance(items, list) or not items: continue
            if not isinstance(items[0], dict): continue
            print(f"\n  【{cat_key}】({len(items)}项)")
            for item in items:
                if not isinstance(item, dict): continue
                name = item.get('name', item.get('kpi', item.get('milestone', item.get('signal', item.get('trigger', item.get('period', ''))))))
                print(f"  • {str(name)[:80]}")
                for fk, fv in item.items():
                    fv_str = str(fv) if fv else ''
                    if fv_str.strip(): print(f"    {fk}: {fv_str[:100]}")

    print(f"\n═══ 叙事 ═══\n  {report.get('narrative', '')}")


def export_markdown(report: dict) -> str:
    """Markdown格式完整报告——含校准框架和追踪框架"""
    meta = report["report_meta"]
    vr = report["valuation_routing"]
    sanity = report["market_sanity"]
    vs = report["valuation_summary"]
    gap = report["expectation_gap"]
    conf = report["confidence"]
    ta = report["trade_annotation"]
    timings = report.get("_timings", {})

    md = f"""# 估值重构报告: {meta['stock_name']}({meta['stock_code']})

**行业**: {meta['industry']} | **日期**: {meta['report_date']} | **版本**: v{meta['version']} | **耗时**: {timings.get('total_s','?')}s

---

## 一、估值路由

| 项目 | 值 |
|------|-----|
| 主模型 | **{vr['primary_model']}** |
| 校验模型 | {vr['secondary_model']} |
| 计算方法 | {vr['method_used']} |
| 理由 | {vr['routing_reason']} |

## 二、市场定价检测 (BS检测器)

**{sanity['bs_level']}**

| 指标 | 值 |
|------|-----|
| EV | {sanity.get('ev_yi','?')}亿 |
| NOPAT | {sanity.get('nopat_yi','?')}亿 |
| ROIC | {sanity.get('roic_pct','?')}% |
| 简化WACC | {sanity.get('wacc_simple_pct','?')}% |
| 隐含永续增速g | {sanity.get('implied_g_pct','?')}% |
| 市场溢价 | {sanity.get('market_premium_pct','?')}% |
| PE(TTM) | {sanity.get('pe_ttm','?')}x |
| PE历史分位 | {sanity.get('pe_historical_rank','?')} |
| PB | {sanity.get('pb','?')}x |

> {sanity.get('market_story','')}

## 三、参数推演校准框架

**事件前基线**: {gap.get('current_market_story','?')}

**事件冲击**: {gap.get('event_story','?')}

**校准模型**: {gap.get('valuation_model','?')}

## 四、预期差

**{gap['level']}**: {gap['note']}

| 指标 | 值 |
|------|-----|
| 概率加权涨幅 | **{vs['probability_weighted_upside_pct']:.1f}%** |
| 不对称比 | {vs['asymmetry_ratio']:.1f} |
| 质量等级 | {vs['quality_flag']} |
| 概率加权市值 | {vs['probability_weighted_mcap_yi']:.0f}亿 |
| 当前市值 | {vs['current_mcap_yi']:.0f}亿 |

## 五、三情景推演

| 情景 | 概率 | ROIC | PE | NOPAT路径 | 目标市值 | 涨跌幅 |
|------|:--:|-----:|--:|-----------|--------:|------:|
"""
    for s in report.get("scenarios", []):
        nopat_path = " → ".join([f"{n:.1f}" for n in s.get('nopat_path_yi', [])])
        md += f"| **{s['name']}** | {s['probability_pct']}% | {s.get('roic_pct','?')}% | {s.get('pe_target','?')}x | {nopat_path}亿 | {s['target_mcap_yi']:.0f}亿 | **{s['upside_pct']:+.1f}%** |\n"

    md += f"""
## 六、案例比对校准

**方法**: {report.get('case_comparison_summary', {}).get('comparison_method', '')}

"""
    cc = report.get("case_comparison_summary", {})
    pi = cc.get("parameter_impact", {})
    md += f"**综合参数折扣**: {pi.get('target_param_discount_pct','?')}%\n\n"
    md += f"> {pi.get('adjustment_rationale','?')}\n\n"

    cases = cc.get("compared_cases", [])
    if cases:
        for c in cases:
            md += f"### vs {c['case_code']} (折扣率: {c['comprehensive_discount_pct']}%)\n\n"
            md += "| 维度 | 判断 |\n|------|------|\n"
            for dk, dv in c.get("six_dimension_judgment", {}).items():
                label = {"driver_strength":"驱动强度","market_space":"市场空间","moat":"卡位壁垒",
                         "paradigm":"范式切换","catalyst_density":"催化剂密度","failure_risk":"失败风险"}.get(dk, dk)
                md += f"| {label} | {dv} |\n"
            md += "\n"

    md += f"""
## 七、置信度: {conf['overall_score']}/10 ({conf['overall_label']})

| 维度 | 评分 | 说明 |
|------|:--:|------|
"""
    for dim, d in conf["dimensions"].items():
        md += f"| {d['label']} | {d['score']}/10 | {d['note']} |\n"

    md += f"""
## 八、交易标注: {ta['tier']} ({ta['total_score']})

"""
    labels = ["S1 赔率质量", "S2 定价空间", "S3 传导确定性", "S4 模型自洽"]
    ds = ta.get("dimension_scores", {})
    for i, sig in enumerate(ta["alignment_signals"]):
        score = list(ds.values())[i] if i < len(ds) else "?"
        label = labels[i] if i < len(labels) else f"S{i+1}"
        md += f"| {label} | {score} | {sig} |\n"

    md += f"""
**建议**: {ta['suggested_action']}

## 九、事件追踪框架

"""
    kpis = report.get("monitoring_kpis", {})
    if isinstance(kpis, dict):
        tf = kpis.get("tracking_framework", {})
        if not isinstance(tf, dict): tf = {}
        for k, v in kpis.items():
            if k != "tracking_framework" and k not in tf:
                tf[k] = v
        meta_kpi = tf.get("meta", {})
        if meta_kpi:
            md += f"""**传导链**: {meta_kpi.get('event_chain','?')}

**关键假设**: {meta_kpi.get('key_assumption','?')}

**Bear触发条件**: {meta_kpi.get('bear_trigger','?')}

"""
        timeline = tf.get("timeline", [])
        if not timeline:
            for k, v in tf.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and ('date' in v[0] or 'node' in v[0]):
                    timeline = v; break
        if timeline:
            md += "### 9.1 事件时间线\n\n"
            md += "| 节点 | 日期 | 事件 | 威胁/预警 |\n|------|------|------|----------|\n"
            for t in timeline:
                if not isinstance(t, dict): continue
                node = t.get('node', ''); date = t.get('date', '')
                event = t.get('event', t.get('expected', ''))
                threat = t.get('threat', '')
                status = t.get('status', '')
                prefix = "[已达成] " if status == "已达成" else ""
                md += f"| {node} | {date} | {prefix}{str(event)[:80]} | {str(threat)[:80]} |\n"
            md += "\n"
        kpi_cats = tf.get("kpi_categories", tf.get("categories", {}))
        if not kpi_cats:
            for k, v in tf.items():
                if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict) and k not in ('timeline',):
                    kpi_cats[k] = v
                elif isinstance(v, dict) and k not in ('meta',):
                    # 深入一层: valuation_reconstruction_tracking 等嵌套dict
                    for k2, v2 in v.items():
                        if isinstance(v2, list) and len(v2) > 0 and isinstance(v2[0], dict):
                            kpi_cats[k2] = v2
        section_num = 2
        for cat_key, items in kpi_cats.items():
            if not isinstance(items, list) or not items: continue
            if not isinstance(items[0], dict): continue
            md += f"### 9.{section_num} {cat_key}\n\n"
            section_num += 1
            for item in items:
                if not isinstance(item, dict): continue
                name = item.get('name', item.get('kpi', item.get('milestone', item.get('signal', item.get('trigger', item.get('period', ''))))))
                md += f"**{str(name)[:80]}**\n\n"
                for fk, fv in item.items():
                    fv_str = str(fv) if fv else ''
                    if fv_str.strip():
                        md += f"- **{fk}**: {fv_str[:150]}\n"
                md += "\n"

    md += f"""
## 十、叙事

> {report.get('narrative', '')}
"""

    return md


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="估值重构引擎 V5 — 4-Agent 管线: Agent-0预路由→Agent-1数据炼器→Agent-2路由判官→Agent-3推演裁决",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py 920015                    单股分析
  python main.py 920015 -o report.md       输出Markdown报告
  python main.py 920015 -e event.json      带事件数据
  python main.py 600276 688235 --batch     批量模式
  python main.py 920015 --json             完整JSON输出
        """,
    )
    parser.add_argument("codes", nargs="+", help="股票代码(如920015 600276)")
    parser.add_argument("-e", "--event", help="事件JSON文件路径")
    parser.add_argument("-o", "--output", help="输出文件路径(.json或.md)")
    parser.add_argument("--batch", action="store_true", help="批量模式")
    parser.add_argument("--json", action="store_true", help="输出完整JSON到stdout")
    parser.add_argument("--deepseek-key", help="DeepSeek API Key(或设环境变量DEEPSEEK_API_KEY)")

    args = parser.parse_args()

    config = load_config()
    deepseek_key = args.deepseek_key or config.get("deepseek_api_key") or None

    results = {}
    for code in args.codes:
        if not args.json:
            print(f"\n{'='*60}")
            print(f"  分析 {code} ...")
            print(f"{'='*60}")

        event = load_event(code, args.event)
        report = run_pipeline(code, event, deepseek_key)
        results[code] = report

        # 输出
        if args.json:
            json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif not args.output:
            print_summary(report)

        # 保存
        if args.output:
            out_path = Path(args.output)
            if len(args.codes) > 1:
                stem = out_path.stem
                out_path = out_path.parent / f"{stem}_{code}{out_path.suffix}"

            if out_path.suffix == ".md":
                out_path.write_text(export_markdown(report), encoding="utf-8")
            else:
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"  → 已保存: {out_path}")

    # 批量汇总
    if args.batch and len(results) > 1:
        print(f"\n{'='*60}")
        print(f"  批量汇总 ({len(results)}只)")
        print(f"{'='*60}")
        for code, r in results.items():
            ta = r["trade_annotation"]
            vs = r["valuation_summary"]
            print(f"  {code} {r['report_meta']['stock_name']:6s} | {ta['tier']} | 涨幅{vs['probability_weighted_upside_pct']:+.1f}% | {vs['quality_flag']}")


if __name__ == "__main__":
    main()
