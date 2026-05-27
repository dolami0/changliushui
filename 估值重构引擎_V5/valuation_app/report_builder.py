"""
HTML 报告生成器 — 将 Agent0-3 产出渲染为完整估值报告。

输入: Agent0 记录 + Agent1 输出 + Agent2 输出 + Agent3 输出
输出: 完整 HTML 字符串（CSS 内联，单文件自包含）

设计方向: 精密金融终端 × 现代编辑美学
"""

from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════

CSS = """
:root {
  --bg: #080b0d; --surface: #0f1419; --card: #141a21;
  --elevated: #1a2129; --border: #1f2933;
  --text: #c8d2dc; --text-dim: #6b7d8e; --text-bright: #e8f0f8;
  --gold: #c88d3a; --gold-dim: rgba(200,141,58,0.12);
  --steel: #508aa8; --steel-dim: rgba(80,138,168,0.12);
  --green: #2d9d6c; --green-dim: rgba(45,157,108,0.12);
  --red: #c84a4a; --red-dim: rgba(200,74,74,0.12);
  --bull: #2d9d6c; --bear: #c84a4a;
  --mono: 'Cascadia Code','Consolas','Microsoft YaHei',monospace;
  --sans: 'PingFang SC','Microsoft YaHei','Noto Sans SC',sans-serif;
  --serif: 'PingFang SC','Microsoft YaHei','Noto Sans SC',sans-serif;
  --radius: 6px; --gap: 16px;
}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:17px;line-height:1.85;-webkit-font-smoothing:antialiased}
.container{max-width:1040px;margin:0 auto;padding:48px 36px 72px}

.rpt-header{text-align:center;padding:64px 0 40px;border-bottom:1px solid var(--border);margin-bottom:40px}
.rpt-header h1{font-family:var(--sans);font-size:30px;font-weight:700;color:var(--text-bright);letter-spacing:-0.5px;margin-bottom:8px}
.rpt-header .subtitle{color:var(--text-dim);font-size:16px;margin-bottom:18px}
.rpt-header .score-badges{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.rpt-header .badge{display:inline-block;padding:6px 18px;border-radius:var(--radius);font-family:var(--mono);font-size:15px;font-weight:700}
.badge-up{background:var(--green-dim);color:var(--green);border:1px solid rgba(45,157,108,.25)}
.badge-down{background:var(--red-dim);color:var(--red);border:1px solid rgba(200,74,74,.25)}
.badge-neutral{background:var(--steel-dim);color:var(--steel);border:1px solid rgba(80,138,168,.25)}

.section{margin-bottom:28px;animation:fadeUp .5s ease both}
.section:nth-child(2){animation-delay:.05s}.section:nth-child(3){animation-delay:.1s}
.section:nth-child(4){animation-delay:.15s}.section:nth-child(5){animation-delay:.2s}
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}

.section-title{display:flex;align-items:center;gap:12px;margin-bottom:16px;padding-bottom:10px;border-bottom:1px solid var(--border)}
.section-num{font-family:var(--mono);font-size:14px;color:var(--gold);background:var(--gold-dim);padding:4px 12px;border-radius:var(--radius);letter-spacing:1px;font-weight:600}
.section-title h2{font-family:var(--sans);font-size:20px;font-weight:700;color:var(--text-bright);letter-spacing:0.5px;margin:0}

.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;margin-bottom:var(--gap)}
.card h3{font-family:var(--sans);font-size:15px;font-weight:600;color:var(--steel);letter-spacing:1px;margin-bottom:14px;margin-top:0}
.card h4{font-family:var(--sans);font-size:14px;font-weight:600;color:var(--text-dim);margin:14px 0 8px}
.card p{font-size:15px;line-height:1.8;margin-bottom:6px}
.card blockquote{font-size:16px;line-height:1.9;color:var(--text);border-left:3px solid var(--gold);padding:10px 18px;margin:12px 0;background:var(--elevated);border-radius:0 var(--radius) var(--radius) 0}

.bignums{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:var(--gap)}
.bignum{background:var(--elevated);border:1px solid var(--border);border-radius:var(--radius);padding:18px;text-align:center}
.bignum .val{font-family:var(--mono);font-size:34px;font-weight:700;line-height:1.15}
.bignum .val.up{color:var(--green)}.bignum .val.down{color:var(--red)}.bignum .val.neutral{color:var(--gold)}
.bignum .lbl{font-size:13px;color:var(--text-dim);margin-top:6px;letter-spacing:1px;text-transform:uppercase}
.bignum .sub{font-family:var(--mono);font-size:13px;color:var(--text-dim);margin-top:3px}

.scenario-bar{display:flex;height:36px;border-radius:var(--radius);overflow:hidden;margin:14px 0}
.scenario-bar>div{display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:13px;font-weight:600}
.bar-bear{background:rgba(200,74,74,.6)}.bar-base{background:rgba(80,138,168,.55)}.bar-bull{background:rgba(45,157,108,.6)}

table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:14px}
table.kv td{padding:7px 14px;border-bottom:1px solid var(--border)}
table.kv td:first-child{color:var(--text-dim);width:130px;white-space:nowrap}
table.kv td:last-child{color:var(--text-bright)}
table.data th,table.data td{padding:9px 14px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
table.data th{color:var(--text-dim);font-weight:500;font-size:13px;letter-spacing:0.5px;white-space:nowrap}
table.data .num{text-align:right;font-feature-settings:'tnum'}
table.data .up{color:var(--green)}table.data .down{color:var(--red)}
table.data tr:hover td{background:rgba(255,255,255,.02)}

.tag{display:inline-block;padding:3px 10px;border-radius:var(--radius);font-family:var(--mono);font-size:13px;font-weight:600}
.tag-up{background:var(--green-dim);color:var(--green)}.tag-down{background:var(--red-dim);color:var(--red)}
.tag-warn{background:var(--gold-dim);color:var(--gold)}.tag-info{background:var(--steel-dim);color:var(--steel)}

.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px}
.kpi-item{background:var(--elevated);border:1px solid var(--border);border-radius:var(--radius);padding:14px 18px}
.kpi-item .kpi-name{font-size:15px;font-weight:600;color:var(--text-bright);margin-bottom:6px}
.kpi-item .kpi-detail{font-size:14px;color:var(--text-dim);line-height:1.7}
.kpi-item .kpi-detail b{color:var(--steel);font-weight:500}

.rt-item{font-size:14px;line-height:1.7;padding:10px 14px;margin:5px 0;background:var(--elevated);border-radius:var(--radius);border-left:2px solid var(--border)}
.rt-item .rt-num{color:var(--gold);font-weight:600;margin-right:8px}

.g2{display:grid;grid-template-columns:1fr 1fr;gap:var(--gap)}
.g3{display:grid;grid-template-columns:repeat(3,1fr);gap:var(--gap)}
@media(max-width:700px){.g2,.g3{grid-template-columns:1fr}}

.prose{font-size:16px;line-height:1.9;color:var(--text)}
.prose strong{color:var(--text-bright)}.prose em{color:var(--gold);font-style:normal}

.rpt-footer{text-align:center;padding:36px 0 20px;color:var(--text-dim);font-family:var(--mono);font-size:13px;border-top:1px solid var(--border);margin-top:40px;letter-spacing:0.5px}

.dim-bar-wrap{display:flex;align-items:center;gap:12px;margin:6px 0}
.dim-bar-wrap .dim-label{width:100px;font-size:14px;color:var(--text-dim);flex-shrink:0}
.dim-bar-wrap .dim-track{flex:1;height:10px;background:var(--border);border-radius:5px;overflow:hidden}
.dim-bar-wrap .dim-fill{height:100%;border-radius:5px}
.dim-bar-wrap .dim-score{font-family:var(--mono);font-size:15px;font-weight:700;width:55px;text-align:right}

.md-block{font-size:15px;line-height:1.8}
.md-block p{margin:5px 0}
.md-block strong{color:var(--text-bright)}
.md-block em{color:var(--gold);font-style:italic}
.md-block ul,.md-block ol{margin:5px 0;padding-left:22px}
.md-block li{margin:3px 0;color:var(--text)}
.md-block code{font-family:var(--mono);font-size:14px;background:var(--elevated);padding:2px 8px;border-radius:3px;color:var(--steel)}
"""

# ═══════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════

def _n(v, default="—"):
    if v is None: return default
    try:
        f = float(v)
        if abs(f) >= 100: return f"{f:.0f}"
        if abs(f) >= 10: return f"{f:.1f}"
        return f"{f:.2f}"
    except: return str(v)

def _fmt_pct(v):
    if v is None: return "—"
    try: return f"{float(v):+.1f}%"
    except (ValueError, TypeError): return str(v)
def _fmt_yi(v):
    if v is None: return "—"
    try: return f"{float(v):.1f}亿"
    except (ValueError, TypeError): return str(v)
def _up_cls(v): return "up" if (v or 0) >= 0 else "down"

def _section(num, title, body):
    return f'<div class="section"><div class="section-title"><span class="section-num">{num}</span><h2>{title}</h2></div>{body}</div>'

def _card(title, body):
    return f'<div class="card"><h3>{title}</h3>{body}</div>'

def _kv_row(k, v, cls=""): return f'<tr><td>{k}</td><td class="{cls}">{v}</td></tr>'

def _kv_table(rows): return f'<table class="kv">{"".join(_kv_row(*r) for r in rows)}</table>'

def _big_num(val, label, unit="", sub=""):
    v = _n(val); cls = _up_cls(val) if isinstance(val, (int,float)) and val != 0 else "neutral"
    return f'<div class="bignum"><div class="val {cls}">{v}{unit}</div><div class="lbl">{label}</div>' + (f'<div class="sub">{sub}</div>' if sub else '') + '</div>'

def _dim_bar(label, score, max_s=10):
    pct = min(100, max(0, score / max_s * 100))
    c = "var(--green)" if score >= 7 else ("var(--gold)" if score >= 4 else "var(--red)")
    return f'<div class="dim-bar-wrap"><span class="dim-label">{label}</span><div class="dim-track"><div class="dim-fill" style="width:{pct}%;background:{c}"></div></div><span class="dim-score" style="color:{c}">{score}/{max_s}</span></div>'

def _md(text: str) -> str:
    """Simple markdown-to-HTML renderer for inline content in JSON fields."""
    if not text: return ""
    import re
    t = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\*(.+?)\*', r'<em>\1</em>', t)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\n\s*[-*]\s+(.+)', r'<br>• \1', t)
    t = re.sub(r'\n(\d+)\.\s+(.+)', r'<br>\1. \2', t)
    t = t.replace('\n\n', '</p><p>').replace('\n', '<br>')
    return f'<div class="md-block"><p>{t}</p></div>'

def build_html_report(agent0_record: dict, a1: dict, a2: dict, a3: dict) -> str:
    """生成完整 HTML 估值报告 —— V5 数据流编排"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 解包 ──
    cf = a1.get("clean_financials", {})
    va = a1.get("valuation_anchor", {})
    vr = a1.get("valuation_routing", {})
    sanity = a1.get("market_sanity", {})
    fw = a1.get("forward_looking", {})

    stock_code = agent0_record.get("stock_code", cf.get("stock_code", "?"))
    stock_name = agent0_record.get("stock_name", cf.get("stock_name", "?"))
    primary = vr.get("primary_model", "?")

    # Agent-3 数据
    vs = a3.get("valuation_summary", {})
    scenarios = a3.get("scenarios", [])
    conf = a3.get("confidence", {})
    gap = a3.get("expectation_gap", {})
    vx = a3.get("validation_crosscheck", {})
    rd = a3.get("reverse_dcf", {})
    ta = a3.get("trade_annotation", {})
    kpis = a3.get("monitoring_kpis", {})
    triggers = a3.get("risk_triggers", {})
    rt = a3.get("reasoning_trace", [])
    sa = a3.get("signal_audit", {})
    narrative = a3.get("narrative", "")
    dg = a3.get("data_gaps", [])

    # ── 构建 ──
    body = (
        _v5_header(stock_code, stock_name, now, primary, vr, vs)
        + _v5_routing(vr)
        + _v5_bs_profile(sanity, cf)
        + _v5_signal_audit(sa, fw)
        + _v5_scenarios(scenarios, primary, cf)
        + _v5_validation_crosscheck(vx)
        + _v5_reverse_dcf(rd)
        + _v5_expectation_gap(gap)
        + _v5_confidence(conf)
        + _v5_trade_annotation(ta)
        + _v5_kpis(kpis)
        + _v5_triggers(triggers)
        + _v5_reasoning_trace(rt)
        + _v5_narrative(narrative, dg)
        + _v5_footer(stock_code, now)
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>估值重构报告 — {stock_name}({stock_code})</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
{body}
</div>
</body>
</html>"""


# ═══════════════════════════════════════════════
# V5 区块构建函数
# ═══════════════════════════════════════════════


def build_html_report(agent0_record: dict, a1: dict, a2: dict, a3: dict, agent2a: dict | None = None) -> str:
    """V6 完整估值报告 — 覆盖全部 JSON 字段，赛博仙门主题，大字体"""
    now = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M")
    cf = a1.get("clean_financials", {})
    va = a1.get("valuation_anchor", {})
    vr = a1.get("valuation_routing", {})
    sanity = a1.get("market_sanity", {})
    fw = a1.get("forward_looking", {})

    stock_code = agent0_record.get("stock_code", cf.get("stock_code", "?"))
    stock_name = agent0_record.get("stock_name", cf.get("stock_name", "?"))
    primary = vr.get("primary_model", "?")
    industry = cf.get("industry_sw_l1", "") + " / " + cf.get("industry_sw_l2", "")

    # Agent-2a V6 narrative diagnosis
    a2a = agent2a or {}
    a2a_mn = a2a.get("market_narrative", {})
    a2a_ep = a2a.get("event_pricing", {})
    a2a_pr = a2a_ep.get("event_profile", {})
    a2a_pa = a2a_ep.get("pricing_assessment", {})
    a2a_sa = a2a.get("signal_audit", {})
    a2a_pt = a2a.get("_pricing_tool", {})

    # Agent-3 data
    vs = a3.get("valuation_summary", {})
    sv = a3.get("scenario_valuation", {})
    scenarios = a3.get("scenarios", [])
    conf = a3.get("confidence", {})
    gap = a3.get("expectation_gap", {})
    vx = a3.get("validation_crosscheck", {})
    rd = a3.get("reverse_dcf", {})
    ta = a3.get("trade_annotation", {})
    kpis = a3.get("monitoring_kpis", {})
    triggers = a3.get("risk_triggers", {})
    rt = a3.get("reasoning_trace", [])
    sa = a2a_sa or a3.get("signal_audit", {})  # V6: 2a audit is primary source
    narrative = a3.get("narrative", "")
    dg = a3.get("data_gaps", [])
    pr = a3.get("probability_rationale", "")
    pf = a3.get("preflight_check", [])
    wacc = va.get("wacc_params", sanity.get("wacc_params", {}))

    upside = vs.get("probability_weighted_upside_pct", 0)
    asym = vs.get("asymmetry_ratio", 0)
    quality = vs.get("quality_flag", "")

    body = (
        _sec_header(stock_code, stock_name, now, primary, vr, industry, upside, asym, quality)
        + _sec_narrative_diagnosis(a2a_mn, a2a_ep, a2a_pr, a2a_pa, a2a_pt, sanity, cf)  # V6: 叙事诊断
        + _sec_routing(vr)
        + _sec_financials(cf, va, wacc)
        + _sec_bs_profile(sanity, cf, a2a_mn.get("primary_anchor","earnings"))
        + _sec_forward_signals(sa, fw, cf)
        + _sec_scenarios(scenarios, primary, pr)
        + _sec_validation(vx, rd, gap, vs)
        + _sec_confidence(conf)
        + _sec_trade(ta)
        + _sec_kpis(kpis)
        + _sec_triggers(triggers)
        + _sec_reasoning(rt)
        + _sec_narrative(narrative, dg)
        + _sec_appendix(pf, a3.get("_validation_warnings", []))
        + _sec_footer(stock_code, now)
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>估值重构报告 — {stock_name}({stock_code})</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
{body}
</div>
</body>
</html>"""


# ═══════════════════ Section Builders ═══════════════════

def _sec_footer(stock_code, now):
    return f'<div class="rpt-footer">估值重构引擎 V5 | {stock_code} | {now} | 本报告不构成投资建议</div>'

def _sec_header(stock_code, stock_name, now, primary, vr, industry, upside, asym, quality):
    cls = "badge-up" if upside > 0 else ("badge-down" if upside < 0 else "badge-neutral")
    return f"""<div class="rpt-header">
<h1>估值重构报告: {stock_name}({stock_code})</h1>
<div class="subtitle">管线版本 V5 | {now} | 主模型: <strong>{primary}</strong> ({vr.get('model_category','')}) | {industry}</div>
<div class="score-badges">
  <span class="badge {cls}">概率加权涨幅 {upside:+.1f}%</span>
  <span class="badge badge-neutral">不对称比 {asym:.1f}x</span>
  <span class="badge badge-neutral">质量: {quality}</span>
</div>
</div>"""


def _sec_routing(vr):
    rows = [
        ("主模型", f'<strong>{vr.get("primary_model","?")}</strong>'),
        ("模型类别", vr.get("model_category","?")),
        ("校验模型", vr.get("secondary_model", vr.get("validation_models",[""])[0] if vr.get("validation_models") else "?")),
        ("路由理由", _md(vr.get("routing_reason",""))),
    ]
    return _section("01", "估值路由", _kv_table(rows))


def _sec_financials(cf, va, wacc):
    bignums = "".join([
        _big_num(cf.get("market_cap_yi"), "市值", "亿"),
        _big_num(cf.get("revenue_ttm_yi"), "营收TTM", "亿"),
        _big_num(cf.get("net_profit_ttm_yi"), "净利润TTM", "亿"),
        _big_num(cf.get("pe_ttm"), "PE(TTM)", "x", f'分位{cf.get("pe_historical_rank","?")}'),
    ])
    fin_rows = [
        ("PB", f'{_n(cf.get("pb"))}x (分位{_n(cf.get("pb_historical_rank"))})'),
        ("PS(TTM)", f'{_n(cf.get("ps_ttm"))}x'),
        ("ROIC", f'{_n(cf.get("roic_pct"))}% (历史分位{_n(cf.get("roic_historical_rank"))})'),
        ("ROE(TTM)", f'{_n(cf.get("roe_ttm_pct"))}% (历史分位{_n(cf.get("roe_historical_rank"))})'),
        ("毛利率", f'{_n(cf.get("gross_margin_pct"))}% (历史分位{_n(cf.get("gross_margin_historical_rank"))})'),
        ("净利率", f'{_n(cf.get("net_margin_pct"))}% (历史分位{_n(cf.get("net_margin_historical_rank"))})'),
        ("盈利能力综合", f'{_n(cf.get("profitability_composite_score"))}/100'),
        ("经营CF(TTM)", _fmt_yi(cf.get("ocf_ttm_yi"))),
        ("CAPEX(TTM)", _fmt_yi(cf.get("capex_ttm_yi"))),
        ("EBITDA(TTM)", _fmt_yi(cf.get("ebitda_ttm_yi"))),
        ("总资产", _fmt_yi(cf.get("total_assets_yi"))),
        ("净资产", _fmt_yi(cf.get("total_equity_yi"))),
        ("有息负债", _fmt_yi(cf.get("interest_bearing_debt_yi"))),
        ("现金", _fmt_yi(cf.get("cash_yi"))),
        ("净负债", _fmt_yi(cf.get("net_debt_yi"))),
        ("数据质量", f'{cf.get("data_quality_score","?")}/10'),
    ]
    flags = cf.get("caution_flags", [])
    if flags:
        fin_rows.append((" 异常标记", ", ".join(str(f) for f in flags)))
    wacc_rows = [
        ("无风险利率", f'{_n(wacc.get("rf_pct"))}% ({wacc.get("rf_source","")})'),
        ("Beta", f'{_n(wacc.get("beta"))} ({wacc.get("beta_source","")})'),
        ("ERP", f'{_n(wacc.get("erp_pct"))}% ({wacc.get("erp_method","")})'),
        ("Re(股权成本)", f'{_n(wacc.get("re_pct"))}%'),
        ("Rd(债务成本)", f'{_n(wacc.get("rd_pct"))}%'),
        ("D/(D+E)", f'{_n(wacc.get("d_ratio_pct"))}%'),
        ("WACC", f'<strong>{_n(wacc.get("wacc_pct"))}%</strong>'),
        ("备注", wacc.get("note","")),
    ]
    implied_rr = va.get("implied_rr_pct")
    return _section("02", "财务数据总览",
        f'<div class="bignums">{bignums}</div>'
        + _card("核心财务指标", _kv_table(fin_rows))
        + _card("WACC 参数", _kv_table(wacc_rows))
        + _card("估值锚点", _kv_table([
            ("EV", _fmt_yi(va.get("ev_yi"))), ("NOPAT", _fmt_yi(va.get("nopat_yi"))),
            ("ROIC", f'{_n(va.get("roic_pct"))}%'), ("WACC(中)", f'{_n(va.get("wacc_mid_pct"))}%'),
            ("隐含RR", f'{_n(implied_rr)}%' if implied_rr else "—"),
            ("估值模型", va.get("valuation_model","?")),
        ]))
    )


def _sec_narrative_diagnosis(mn, ep, pr, pa, pt, sanity, cf):
    """V6: 叙事诊断 — Agent-2a 估值锚 + 三维光谱 + 计价判断"""
    if not mn:
        return ""
    anchor = mn.get("primary_anchor", "?")
    anchor_labels = {"earnings": "利润锚 (PE/DCF)", "revenue": "收入锚 (PS/TAM)",
                     "asset": "资产锚 (PB/ROE)", "pipeline": "管线锚 (rNPV)", "sotp": "SOTP 分部"}
    shape = pr.get("distribution_shape", "?")
    shape_labels = {"wide_bimodal": "宽双峰(高二元性)", "wide_bimodal_date_anchored": "宽双峰(日期锚定)",
                    "wide_unimodal": "宽单峰(方向确定幅度不确定)", "narrow_concentrated": "窄集中(成熟周期)",
                    "narrow_base_dominant": "极窄(趋势延续)"}

    # 估值锚
    body = _card("估值锚", _kv_table([
        ("主锚", anchor_labels.get(anchor, anchor)),
        ("证据", mn.get("primary_anchor_evidence", "?")[:200]),
        ("SOTP触发", "是" if mn.get("sotp_triggered") else "否"),
    ]))

    # 三维光谱
    body += _card("三维事件光谱", _kv_table([
        ("分布形状", shape_labels.get(shape, shape)),
        ("时机可预见性", f"{pr.get('timing_certainty','?')}/10 — {pr.get('timing_rationale','?')[:80]}"),
        ("结果二元性", f"{pr.get('outcome_binaryness','?')}/10 — {pr.get('outcome_rationale','?')[:80]}"),
        ("先例丰富度", f"{pr.get('precedent_richness','?')}/10 — {pr.get('precedent_rationale','?')[:80]}"),
    ]))

    # 计价判断
    body += _card("事件计价判断", _kv_table([
        ("计价程度", f"{pa.get('overall_priced_in','?')} ({pa.get('priced_in_estimate','?')})"),
        ("剩余催化", pa.get("residual_catalyst","?")[:150]),
    ]))

    # 定价工具结果 (anchor-aware)
    if pt and pt.get("applicable"):
        method = pt.get("method", "?")
        metric = pt.get("implied_metric", "?")
        value = pt.get("implied_value", "?")
        body += _card(f"定价工具: {method}", _kv_table([
            (metric, f"<strong>{value}</strong>"),
        ]))

    return _section("02.5", "叙事诊断 (Agent-2a)", body)


def _sec_bs_profile(sanity, cf, anchor="earnings"):
    bs = sanity.get("bs_level", "?")
    secondary = sanity.get("bs_secondary", "")
    premium = sanity.get("market_premium_pct", 0) or 0
    prem_str = f'{premium:.1f}%' if premium < 999 else "不适用(NOPAT极薄)"

    # V6: 根据估值锚调整 BS 画像展示
    implied_g = sanity.get("implied_g_pct", 0)
    if anchor == "revenue":
        bs_method = "隐含收入CAGR (收入锚)"
        g_label = "隐含3y CAGR"
        g_warning = " (注: 以下反向DCF基于NOPAT,对收入锚仅供参考)"
    elif anchor == "asset":
        bs_method = "隐含ROE改善 (资产锚)"
        g_label = "隐含ROE改善"
        g_warning = " (注: 反向DCF基于NOPAT,对资产锚仅供参考)"
    else:
        bs_method = sanity.get("bs_method", "反向DCF(g/WACC)")
        g_label = "隐含g"
        g_warning = ""

    body = f'<div class="prose"><strong>{bs}</strong></div>'
    body += _kv_table([
        ("BS方法", bs_method),
        ("EV", _fmt_yi(sanity.get("ev_yi"))),
        ("NOPAT", _fmt_yi(sanity.get("nopat_yi"))),
        ("ROIC", f'{_n(sanity.get("roic_pct"))}%'),
        ("WACC", f'{_n(sanity.get("wacc_simple_pct"))}%'),
        (g_label, f'{_n(implied_g)}%{g_warning}'),
        ("市场溢价", prem_str),
        ("PE(TTM)", f'{_n(sanity.get("pe_ttm"))}x (分位{_n(sanity.get("pe_historical_rank"))})'),
        ("PB", f'{_n(sanity.get("pb"))}x'),
    ])
    if secondary:
        body += f'<p style="font-size:13px;color:var(--text-dim);margin-top:8px">{secondary}</p>'
    story = sanity.get("market_story","")
    if story:
        body += f'<blockquote>{story}</blockquote>'
    warnings = sanity.get("warnings", [])
    if warnings:
        body += "<p style='font-size:13px;color:var(--gold)'> " + "; ".join(str(w) for w in warnings) + "</p>"
    return _section("03", "市场定价检测 (BS画像)", body)


def _sec_forward_signals(sa, fw, cf):
    if not sa and not fw: return ""
    parts = []
    score = sa.get("step2d_score")
    if score is not None:
        parts.append(f'<div class="bignums">{_big_num(score, "信号匹配度", "/10")}</div>')
    if sa.get("score_rationale"):
        parts.append(f'<p style="font-size:14px;color:var(--gold)">{sa["score_rationale"]}</p>')
    prod = sa.get("step2c_product_restate", "")
    if prod:
        parts.append(_card("产品结构数据", _md(prod)))
    matches = sa.get("step2b_match", [])
    if matches:
        # 兼容 dict 和 string 两种格式
        def _sig(m):
            if isinstance(m, dict):
                return m.get("signal", "?")
            return str(m)[:60]
        def _match(m):
            if isinstance(m, dict): return m.get("match", "?")
            return "?"
        def _lvl(m):
            if isinstance(m, dict): return f'L{m.get("source_level","?")}'
            return ""
        def _basis(m):
            if isinstance(m, dict): return _md(m.get("basis",""))
            return str(m)[:120]
        rows = "".join(
            f'<tr><td>{_sig(m)}</td>'
            f'<td><span class="tag tag-{"up" if _match(m)=="支撑" else "down" if _match(m)=="削弱" else "warn"}">{_match(m)}</span> {_lvl(m)}</td>'
            f'<td style="font-size:13px">{_basis(m)}</td></tr>'
            for m in matches
        )
        parts.append(_card("信号交叉验证", f'<table class="data"><tr><th>信号</th><th>判定</th><th>依据</th></tr>{rows}</table>'))
    restate = sa.get("step2a_restate", [])
    if restate:
        items = "".join(f'<div class="rt-item"><span class="rt-num">•</span> {r}</div>' for r in restate[:8])
        parts.append(_card("异常信号复述", items))
    fw_text = fw.get("text_summary", "")
    if fw_text:
        parts.append(f'<p style="font-size:13px;margin-top:8px">\U0001f4ca 前瞻综合: {fw_text}</p>')
    # 盈利趋势（单季度 YoY/QoQ）
    mg = fw.get("categories", {}).get("management_guidance", {})
    et = mg.get("earnings_trend", {}) if mg else {}
    if et and not et.get("_note") and et.get("recent_4q"):
        rows = ["<tr><th>期间</th><th>营收YoY</th><th>营收QoQ</th><th>利润YoY</th><th>ROIC</th></tr>"]
        for q in et.get("recent_4q", [])[:4]:
            rows.append("<tr><td style='color:var(--text-dim)'>" + str(q.get('period','?')) + "</td>"
                        "<td class='num'>" + _fmt_pct(q.get('revenue_q_yoy')) + "</td>"
                        "<td class='num'>" + _fmt_pct(q.get('revenue_q_qoq')) + "</td>"
                        "<td class='num'>" + _fmt_pct(q.get('profit_q_yoy')) + "</td>"
                        "<td class='num'>" + _n(q.get('roic')) + "%</td></tr>")
        trend_note = "趋势方向: " + str(et.get('trend_direction','?')) + " | fina_indicator预计算，反映财报历史，非实时信号"
        parts.append(_card("盈利趋势(单季度)", "<p style='font-size:12px;color:var(--text-dim)'>" + trend_note + "</p><table class='data'>" + "".join(rows) + "</table>"))

    fw_cats = fw.get("categories", {})
    if fw_cats:
        cat_labels = {"demand_reality":"需求真实性","supply_readiness":"供给准备度","earnings_elasticity":"盈利弹性","cashflow_quality":"现金流质量","management_guidance":"管理层预期"}
        cat_parts = []
        for cat_key, cat_data in fw_cats.items():
            if not cat_data or cat_data.get("_note"): continue
            label = cat_labels.get(cat_key, cat_key)
            rows = []
            for k, v in cat_data.items():
                if isinstance(v, dict) and v.get("label"):
                    val = v.get("value","?")
                    unit = v.get("unit","")
                    anomaly = v.get("anomaly",{})
                    note = f' <span style="color:var(--gold);font-size:11px">[{anomaly.get("level","")}]</span>' if anomaly else ""
                    rows.append(f'<tr><td style="color:var(--text-dim)">{v["label"]}</td><td>{val}{unit}{note}</td></tr>')
                elif isinstance(v, dict) and v.get("type"):
                    rows.append(f'<tr><td style="color:var(--text-dim)">{v["label"]}</td><td>{v.get("type","?")} {v.get("trend","")}</td></tr>')
            if rows:
                cat_parts.append(f'<h4>{label}</h4><table class="data">{"".join(rows)}</table>')
        if cat_parts:
            parts.append(_card("前瞻信号详情","".join(cat_parts)))
    return _section("04", "前瞻信号审核", "".join(parts)) if parts else ""


_MODEL_COLS = {
    "A": [("ROIC假设","roic_pct","%"),("RR","rr_pct","%"),("增长g","nopat_growth_pct","%"),("PE目标","pe_target","x")],
    "C": [("ROIC假设","roic_pct","%"),("PE目标","pe_target","x"),("距拐点","quarters_to_inflection","Q")],
    "G": [("ROIC假设","roic_pct","%"),("盈利增速","earnings_growth_pct","%"),("PE目标","pe_target","x"),("PEG","peg_ratio","")],
    "I": [("正常化ROIC","normalized_roic_pct","%"),("正常化PE","normalized_pe","x")],
    "B": [("3y收入CAGR","revenue_growth_3y_cagr_pct","%"),("目标PS","target_ps","x"),("TAM渗透","tam_penetration_pct","%")],
    "D": [("ROE目标","target_roe_pct","%"),("PB目标","target_pb","x"),("分红率","payout_ratio_pct","%")],
    "E": [("EBITDA增速","ebitda_growth_pct","%"),("EV/EBITDA","target_ev_ebitda","x"),("资源调整","resource_value_adj_pct","%")],
    "F": [("成功率","pos_pct","%"),("峰值销售","peak_sales_yi","亿"),("折现率","discount_rate_pct","%")],
    "K": [("阶段1增速","stage1_growth_pct","%"),("高增长年数","stage1_years","年"),("ROIC","roic_assumed_pct","%"),("终值PE","terminal_pe","x")],
}


def _sec_scenarios(scenarios, primary, pr):
    if not scenarios: return ""
    model = primary[0] if primary else "A"
    cols = _MODEL_COLS.get(model, _MODEL_COLS["A"])
    probs = [s.get("probability_pct",0) for s in scenarios]
    names = [s.get("name","?") for s in scenarios]
    bar = '<div class="scenario-bar">' + "".join(f'<div class="bar-{n}" style="flex:{p}">{n} {p:.0f}%</div>' for n,p in zip(names,probs)) + '</div>'
    thead = "<tr><th>情景</th><th>概率</th>" + "".join(f"<th>{c[0]}</th>" for c in cols) + "<th>目标市值</th><th>涨跌幅</th><th>因果逻辑</th></tr>"
    tbody = ""
    for s in scenarios:
        name = s.get("name","?"); prob = s.get("probability_pct",0)
        mcap = s.get("target_mcap_yi",0); upside = s.get("upside_pct",0)
        nar = s.get("scenario_narrative","")[:150]
        cls = "up" if upside > 0 else "down"
        row = f'<tr><td><strong>{name}</strong></td><td class="num">{prob:.0f}%</td>'
        for c in cols:
            val = s.get(c[1]); unit = c[2]
            row += f'<td class="num">{_n(val)}{unit}</td>'
        row += f'<td class="num">{mcap:.0f}亿</td><td class="num {cls}">{upside:+.1f}%</td>'
        row += f'<td style="font-size:13px">{nar}</td></tr>'
        tbody += row
    body = bar + f'<table class="data"><thead>{thead}</thead><tbody>{tbody}</tbody></table>'
    if pr:
        body += _card("概率推导", _md(pr))
    return _section("05", "三情景推演", body)


def _sec_validation(vx, rd, gap, vs):
    parts = []
    if vx and vx.get("assessment"):
        parts.append(_card("校验交叉验证", _kv_table([
            ("校验模型", f'{vx.get("validation_model","?")} ({vx.get("validation_paradigm","?")})'),
            ("主模型估值", _fmt_yi(vx.get("base_target_mcap_yi"))),
            ("校验模型估值", _fmt_yi(vx.get("validation_mcap_yi")) if vx.get("validation_mcap_yi") is not None else "数据异常"),
            ("差异方向", vx.get("gap_direction","?")),
            ("判定", f'<strong>{vx.get("assessment","?")}</strong>'),
        ])))
    if rd and rd.get("applicable"):
        parts.append(_card("反向DCF", _kv_table([
            ("市场隐含g", _fmt_pct(rd.get("market_implied_g_pct"))),
            ("我的隐含g", _fmt_pct(rd.get("my_implied_g_pct"))),
            ("预期差", f'{_n(rd.get("expectation_gap_pct"))}% — {rd.get("gap_direction","?")} ({rd.get("gap_magnitude","?")})'),
        ])))
    elif rd and not rd.get("applicable"):
        parts.append(_card("反向DCF", f'<p style="color:var(--text-dim)">不适用: {rd.get("applicable_note","")}</p>'))
    if gap and gap.get("level"):
        parts.append(_card("预期差", f'<p style="font-size:15px"><strong>{gap.get("level","?")}</strong></p><p style="font-size:14px">{_md(gap.get("note",""))}</p>'))
    parts.append(_card("估值汇总", f'<div class="bignums">{"".join([_big_num(vs.get("probability_weighted_upside_pct"),"概率加权涨幅","%"),_big_num(vs.get("probability_weighted_mcap_yi"),"目标市值","亿"),_big_num(vs.get("asymmetry_ratio"),"不对称比","x")])}</div><p style="font-size:14px;margin-top:8px">质量等级: <strong>{vs.get("quality_flag","?")}</strong></p>'))
    return _section("07", "校验与估值汇总", "".join(parts)) if parts else ""


def _sec_confidence(conf):
    if not conf: return ""
    dims = conf.get("dimensions",{})
    bars = "".join(_dim_bar(v.get("label",k), v.get("score",5)) for k,v in dims.items())
    notes = "".join(f'<p style="font-size:13px;margin:2px 0"><strong>{v.get("label",k)}:</strong> {v.get("note","")}</p>' for k,v in dims.items() if v.get("note"))
    return _section("08", "置信度", f'<p style="font-size:16px;margin-bottom:12px"><strong>综合: {conf.get("overall_score","?")}/10 ({conf.get("overall_label","?")})</strong></p>'+bars+notes)


def _sec_trade(ta):
    if not ta: return ""
    dims = ta.get("dimension_scores",{})
    dim_str = " | ".join(f"{k}: {v}/3" for k,v in dims.items())
    signals = ta.get("alignment_signals",[])
    sig_rows = "".join(f'<tr><td>S{i+1}</td><td>{s}</td></tr>' for i,s in enumerate(signals))
    return _section("09", "交易标注",
        f'<p style="font-size:16px"><strong>{ta.get("tier","?")}</strong> (总分: {ta.get("total_score","?")}/10)</p>'
        f'<p style="font-size:13px;color:var(--text-dim)">{dim_str}</p>'
        + (f'<table class="data"><tr><th>#</th><th>信号</th></tr>{sig_rows}</table>' if signals else "")
        + f'<p style="font-size:14px;margin-top:8px">{ta.get("tier_note","")}</p>'
        + f'<p style="font-size:14px"><strong>建议:</strong> {ta.get("suggested_action","")}</p>')


def _sec_kpis(kpis):
    if not kpis: return ""
    cat_labels = {"financial_verification_kpis":"财务验证","event_milestone_kpis":"事件节点","competition_signal_kpis":"竞争信号","risk_trigger_kpis":"风险触发"}
    items_html = ""
    for cat_key, cat_label in cat_labels.items():
        items = kpis.get(cat_key,[])
        if not items: continue
        kpi_cards = ""
        for item in items:
            if not isinstance(item,dict): continue
            name = item.get("name", item.get("kpi", item.get("milestone", item.get("signal",""))))
            target = item.get("target", item.get("expected",""))
            baseline = item.get("baseline", item.get("current_state", item.get("current","")))
            freq = item.get("frequency", item.get("monitor",""))
            verifies = item.get("verifies", item.get("verification_source",""))
            detail = ""
            if target: detail += f"<b>目标:</b> {target}  "
            if baseline: detail += f"<b>基线:</b> {baseline}  "
            if freq: detail += f"<b>频率:</b> {freq}  "
            if verifies: detail += f"<b>验证:</b> {verifies}"
            kpi_cards += f'<div class="kpi-item"><div class="kpi-name">{name}</div><div class="kpi-detail">{detail}</div></div>'
        items_html += f'<h4>{cat_label}</h4><div class="kpi-grid">{kpi_cards}</div>'
    return _section("10", "监测KPI", items_html) if items_html else ""


def _sec_triggers(triggers):
    if not triggers: return ""
    return _section("11", "风险触发器",
        f'<div class="card"><h3>Bull触发</h3><p style="font-size:14px">{triggers.get("bull_trigger","?")}</p></div>'
        f'<div class="card"><h3>Bear触发</h3><p style="font-size:14px">{triggers.get("bear_trigger","?")}</p></div>'
        f'<p style="font-size:13px;color:var(--text-dim);margin-top:8px"><strong>监测频率:</strong> {triggers.get("monitoring_frequency","?")}</p>')


def _sec_reasoning(rt):
    if not rt: return ""
    items = "".join(f'<div class="rt-item"><span class="rt-num">[{i+1}]</span> {_md(step)}</div>' for i,step in enumerate(rt))
    return _section("12", "推理链", f'<div style="max-height:600px;overflow-y:auto">{items}</div>')


def _sec_narrative(narrative, dg):
    parts = [_card("投资叙事", f'<blockquote style="font-size:16px">{narrative}</blockquote>')]
    if dg:
        items = "".join(f"<li style='font-size:14px;margin:4px 0;color:var(--gold)'>{g}</li>" for g in dg)
        parts.append(_card("数据缺口", f'<ul style="list-style:none;padding:0">{items}</ul>'))
    return _section("13", "投资叙事与数据缺口", "".join(parts))


def _sec_appendix(pf, warnings):
    parts = []
    if pf:
        items = "".join(f'<div style="font-size:13px;color:var(--text-dim);margin:2px 0"> {p}</div>' for p in pf)
        parts.append(_card("Preflight Check", items))
    if warnings:
        items = "".join(f'<div style="font-size:13px;color:var(--gold);margin:2px 0"> {w}</div>' for w in warnings)
        parts.append(_card("校验警告", items))
    return "".join(parts) if parts else ""



def build_markdown_report(agent0_record: dict, a1: dict, a2: dict, a3: dict, agent2a: dict | None = None) -> str:
    cf = a1.get("clean_financials", {})
    vr = a1.get("valuation_routing", {})
    sanity = a1.get("market_sanity", {})
    vs = a3.get("valuation_summary", {})
    gap = a3.get("expectation_gap", {})
    conf = a3.get("confidence", {})
    ta = a3.get("trade_annotation", {})
    scenarios = a3.get("scenarios", [])
    narrative = a3.get("narrative", "")
    vx = a3.get("validation_crosscheck", {})
    kpis = a3.get("monitoring_kpis", {})
    triggers = a3.get("risk_triggers", {})
    rd = a3.get("reverse_dcf", {})
    dg = a3.get("data_gaps", [])
    sa = a3.get("signal_audit", {})
    fw = a1.get("forward_looking", {})
    rt = a3.get("reasoning_trace", [])
    pr = a3.get("probability_rationale", "")
    pf = a3.get("preflight_check", [])

    stock_code = agent0_record.get("stock_code", "")
    stock_name = agent0_record.get("stock_name", cf.get("stock_name", ""))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    primary = vr.get('primary_model', '?')

    md = f"""# 估值重构报告: {stock_name}({stock_code})

> **管线版本 V5** | {now} | 主模型: {primary} | 本报告不构成投资建议

---

## 一、估值路由

| 项目 | 值 |
|------|-----|
| 主模型 | **{primary}** |
| 模型类别 | {vr.get('model_category','?')} |
| 校验模型 | {vr.get('secondary_model', vr.get('validation_models', [''])[0] if vr.get('validation_models') else '?')} |
| 路由理由 | {vr.get('routing_reason','?')} |

## 二、市场定价检测

**{sanity.get('bs_level','?')}**
{sanity.get('bs_secondary','') and chr(42)+sanity['bs_secondary']+chr(42) or ""}

| 指标 | 值 |
|------|-----|
| EV | {sanity.get('ev_yi','?')}亿 |
| NOPAT | {sanity.get('nopat_yi','?')}亿 |
| ROIC | {sanity.get('roic_pct','?')}% |
| WACC | {sanity.get('wacc_simple_pct','?')}% |
| 隐含g | {sanity.get('implied_g_pct','?')}% |
| 市场溢价 | {(_n(sanity.get('market_premium_pct',0))+'%') if (sanity.get('market_premium_pct',0) or 0) < 999 else '不适用'} |
| PE(TTM) | {sanity.get('pe_ttm','?')}x (分位{sanity.get('pe_historical_rank','?')}) |
| PB | {sanity.get('pb','?')}x |

> {sanity.get('market_story','')}

"""
    # ── 三、前瞻信号审核 ──
    if sa:
        md += "## 三、前瞻信号审核\n\n"
        score = sa.get("step2d_score")
        if score is not None:
            md += f"**信号匹配度评分: {score}/10**\n\n"
        if sa.get("score_rationale"):
            md += f"{sa['score_rationale']}\n\n"
        if sa.get("step2c_product_restate"):
            md += f"**产品结构**: {sa['step2c_product_restate']}\n\n"
        matches = sa.get("step2b_match", [])
        if matches:
            md += "| 信号 | 判定 | 来源 | 依据 |\n|------|------|------|------|\n"
            for m in matches:
                md += f"| {m.get('signal','?')} | {m.get('match','?')} | {m.get('source_level','?')} | {m.get('basis','')[:200]} |\n"
            md += "\n"

    # ── 盈利趋势 ──
    mg = fw.get("categories", {}).get("management_guidance", {})
    et = mg.get("earnings_trend", {}) if mg else {}
    if et and not et.get("_note") and et.get("recent_4q"):
        md += "## 盈利趋势 (单季度)\n\n"
        md += f"趋势方向: {et.get('trend_direction','?')} | 来源: fina_indicator预计算，反映财报历史\n\n"
        md += "| 期间 | 营收YoY | 营收QoQ | 利润YoY | ROIC |\n|------|:------:|:------:|:------:|:----:|\n"
        for q in et.get("recent_4q", [])[:4]:
            md += f"| {q.get('period','?')} | {_fmt_pct(q.get('revenue_q_yoy'))} | {_fmt_pct(q.get('revenue_q_qoq'))} | {_fmt_pct(q.get('profit_q_yoy'))} | {_n(q.get('roic'))}% |\n"
        md += "\n"

    # ── 四、三情景推演 ──
    model = primary[0] if primary else 'A'
    MODEL_COLS = {
        'A': [('ROIC','roic_pct','%'), ('RR','rr_pct','%'), ('PE','pe_target','x')],
        'C': [('ROIC','roic_pct','%'), ('PE','pe_target','x'), ('距拐点','quarters_to_inflection','Q')],
        'G': [('ROIC','roic_pct','%'), ('盈利增速','earnings_growth_pct','%'), ('PE','pe_target','x'), ('PEG','peg_ratio','')],
        'I': [('正常化ROIC','normalized_roic_pct','%'), ('正常化PE','normalized_pe','x')],
        'B': [('3y收入CAGR','revenue_growth_3y_cagr_pct','%'), ('目标PS','target_ps','x'), ('TAM渗透','tam_penetration_pct','%')],
        'D': [('ROE目标','target_roe_pct','%'), ('PB目标','target_pb','x'), ('分红率','payout_ratio_pct','%')],
        'E': [('EBITDA增速','ebitda_growth_pct','%'), ('EV/EBITDA','target_ev_ebitda','x'), ('资源调整','resource_value_adj_pct','%')],
        'F': [('成功率','pos_pct','%'), ('峰值销售','peak_sales_yi','亿'), ('折现率','discount_rate_pct','%')],
        'H': [('NAV折价','nav_discount_pct','%')],
        'J': [('估值方法','valuation_method','')],
    }
    cols = MODEL_COLS.get(model, MODEL_COLS['A'])

    md += "## 四、三情景推演\n\n"
    md += "| 情景 | 概率 | " + " | ".join(c[0] for c in cols) + " | 目标市值 | 涨跌幅 | 因果逻辑 |\n"
    md += "|------|:--:|" + ":--:|" * len(cols) + "--------:|------:|------|\n"
    for s in scenarios:
        nar = s.get('scenario_narrative', '') or s.get('narrative', '')
        row = f"| **{s['name']}** | {s.get('probability_pct','?')}% |"
        for label, key, unit in cols:
            val = s.get(key, '?')
            if val is None: val = '?'
            row += f" {val}{unit} |"
        row += f" {s.get('target_mcap_yi',0):.0f}亿 | **{s.get('upside_pct',0):+.1f}%** | {nar[:80]} |\n"
        md += row
    md += "\n"
    if pr:
        md += f"**概率推导**: {pr}\n\n"

    # ── 五、校验交叉验证 ──
    if vx.get("validation_model"):
        md += f"## 六、校验交叉验证: {vx.get('validation_model','?')} ({vx.get('validation_paradigm','?')})\n\n"
        md += f"| 指标 | 值 |\n|------|-----|\n"
        md += f"| 主模型估值 | {_n(vx.get('base_target_mcap_yi'))}亿 |\n"
        md += f"| 校验模型估值 | {_n(vx.get('validation_mcap_yi')) if vx.get('validation_mcap_yi') is not None else '数据异常'}亿 |\n"
        md += f"| 差异 | {_n(vx.get('gap_pct'))}% ({vx.get('gap_direction','?')}) |\n"
        md += f"| 判定 | {vx.get('assessment','?')} |\n\n"

    # ── 七、反向DCF ──
    if rd.get("applicable"):
        md += f"## 七、反向DCF\n\n"
        md += f"| 指标 | 值 |\n|------|-----|\n"
        md += f"| 市场隐含g | {rd.get('market_implied_g_pct','?')}% |\n"
        md += f"| 我的隐含g | {rd.get('my_implied_g_pct','?')}% |\n"
        md += f"| 预期差 | {rd.get('expectation_gap_pct','?')}% ({rd.get('gap_direction','?')},{rd.get('gap_magnitude','?')}) |\n\n"

    # ── 八、预期差 ──
    md += f"## 八、预期差\n\n**{gap.get('level','?')}**: {gap.get('note','?')}\n\n"
    md += f"| 指标 | 值 |\n|------|-----|\n"
    md += f"| 概率加权涨幅 | **{vs.get('probability_weighted_upside_pct',0):+.1f}%** |\n"
    md += f"| 不对称比 | {vs.get('asymmetry_ratio',0):.1f}x |\n"
    md += f"| 质量等级 | {vs.get('quality_flag','?')} |\n"
    md += f"| 目标市值 | {vs.get('probability_weighted_mcap_yi',0):.0f}亿 |\n\n"

    # ── 九、置信度 ──
    md += f"## 九、置信度: {conf.get('overall_score','?')}/10 ({conf.get('overall_label','?')})\n\n"
    md += "| 维度 | 评分 | 说明 |\n|------|:--:|------|\n"
    for dim, d in conf.get("dimensions", {}).items():
        md += f"| {d.get('label','?')} | {d.get('score','?')}/10 | {d.get('note','?')} |\n"
    md += "\n"

    # ── 十、交易标注 ──
    ds = ta.get("dimension_scores", {})
    scores = list(ds.values())
    md += f"## 十、交易标注: {ta.get('tier','?')} ({ta.get('total_score','?')})\n\n"
    align = ta.get("alignment_signals", [])
    for i, sig in enumerate(align):
        score = scores[i] if i < len(scores) else "?"
        md += f"| S{i+1} | {score} | {sig} |\n"
    md += f"\n**建议**: {ta.get('suggested_action','?')}\n\n"

    # ── 十一、监测KPI ──
    md += "## 十一、监测KPI\n\n"
    for cat, items in kpis.items():
        if not items or not isinstance(items, list): continue
        md += f"### {cat}\n\n"
        for item in items:
            if isinstance(item, dict):
                name = item.get('name', item.get('kpi', item.get('milestone', item.get('signal', ''))))
                target = item.get('target', item.get('expected', ''))
                baseline = item.get('baseline', item.get('current_state', item.get('current', '')))
                freq = item.get('frequency', item.get('monitor', ''))
                verifies = item.get('verifies', item.get('verification_source', ''))
                parts = [f"**{name}**"]
                if target: parts.append(f"目标: {target}")
                if baseline: parts.append(f"基线: {baseline}")
                if freq: parts.append(f"频率: {freq}")
                if verifies: parts.append(f"验证: {verifies}")
                md += "- " + " | ".join(parts) + "\n"
    md += "\n"

    # ── 十二、风险触发器 ──
    md += f"## 十二、风险触发器\n\n"
    md += f"- **Bull触发**: {triggers.get('bull_trigger','?')}\n"
    md += f"- **Bear触发**: {triggers.get('bear_trigger','?')}\n"
    md += f"- **监测频率**: {triggers.get('monitoring_frequency','?')}\n\n"

    # ── 十三、推理链 ──
    if rt:
        md += "## 十三、推理链\n\n"
        for i, step in enumerate(rt):
            md += f"{i+1}. {step}\n"
        md += "\n"

    # ── 十四、叙事 + 数据缺口 ──
    md += f"## 十四、投资叙事\n\n> {narrative}\n\n"
    if dg:
        md += "## 数据缺口\n\n" + "\n".join(f"- {g}" for g in dg) + "\n\n"

    if pf:
        md += f"## 起飞前检查\n\n" + "\n".join(f"- {x}" for x in pf) + "\n\n"
    md += "---\n*估值重构引擎 V5 | 本报告不构成投资建议*\n"
    return md


# ═══════════════════════════════════════════════
# 保存
# ═══════════════════════════════════════════════

def save_report(content: str, stock_code: str, output_dir: str = "reports", ext: str = "md", ts: str = "") -> str:
    """保存报告文件。每次产生唯一文件：{stock_code}_{timestamp}.{ext}。ts 为空时自动生成。"""
    if not ts:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = Path(output_dir) / f"{stock_code}_{ts}.{ext}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return str(out_path)

def save_html_report(html: str, stock_code: str) -> str:
    """保存 HTML 报告（兼容旧接口）。"""
    return save_report(html, stock_code, "reports/html", "html")
    return str(out_path)
