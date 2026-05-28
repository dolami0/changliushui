import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { renderMarkdown } from '../lib/utils';
import ValuationReportMobile from './ValuationReportMobile';

/* ================================================================== */
/*  估值重构报告 V5                                                     */
/* ================================================================== */

// ── 首页统一色板 ──
const C = {
  bg:    '#050401',
  green: '#ADFF00',
  orange:'#FF5C00',
  gold:  '#C88D3A',
  white: '#F2F4F3',
  dim:   '#AAA',
  mute:  '#999',
  line:  '#2A2A2A',
};
const F = {
  pixel: "'Geist Pixel',monospace",
  mono:  "'Space Mono',monospace",
  body:  "'IBM Plex Mono','Noto Sans SC',monospace",
};

// ── 工具 ──
function N(v: unknown, d = '—'): string {
  if (v === null || v === undefined) return d;
  const s = String(v); const f = parseFloat(s);
  if (isNaN(f)) return s === 'True' ? '是' : s === 'False' ? '否' : s;
  return f === Math.round(f) ? String(Math.round(f)) : f.toFixed(1);
}
function Pct(v: unknown): string { const s = N(v); return s === '—' ? s : s + '%'; }
const G = (obj: unknown, ...path: string[]): unknown => {
  let cur = obj;
  for (const k of path) { if (cur == null || typeof cur !== 'object') return undefined; cur = (cur as Record<string,unknown>)[k]; }
  return cur;
};

// ── 全局样式 ──
const GLOBAL_CSS = `
  .vr-scroll::-webkit-scrollbar{width:3px}
  .vr-scroll::-webkit-scrollbar-track{background:transparent}
  .vr-scroll::-webkit-scrollbar-thumb{background:rgba(173,255,0,.15)}
  .vr-md{font-family:'IBM Plex Mono','Noto Sans SC',monospace;font-size:15px;line-height:1.9;color:#DDD}
  .vr-md h1{font-size:22px;color:#ADFF00;margin:20px 0 8px;font-weight:700}
  .vr-md h2{font-size:18px;color:#ADFF00;margin:16px 0 6px;font-weight:600}
  .vr-md h3{font-size:16px;color:#F2F4F3;margin:12px 0 6px;font-weight:600}
  .vr-md h4,.vr-md h5,.vr-md h6{font-size:14px;color:#DDD;margin:10px 0 4px;font-weight:600}
  .vr-md p{margin:6px 0;line-height:1.9;color:#DDD}
  .vr-md strong{color:#ADFF00;font-weight:600}
  .vr-md em{color:#C88D3A;font-style:normal}
  .vr-md code{background:rgba(173,255,0,.08);color:#ADFF00;padding:1px 6px;font-size:13px;font-family:'Space Mono',monospace}
  .vr-md li{margin:4px 0;padding:4px 0 4px 12px;color:#DDD;line-height:1.8}
  .vr-md li::marker{color:#ADFF00}
  .vr-md blockquote{border-left:3px solid rgba(173,255,0,.3);padding:10px 20px;margin:10px 0;color:#DDD;background:rgba(173,255,0,.03)}
  .vr-md hr{border:none;border-top:1px solid rgba(255,255,255,0.08);margin:16px 0}
  .vr-md table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}
  .vr-md th{border-bottom:1px solid rgba(173,255,0,.15);padding:10px 14px;text-align:left;color:#ADFF00;font-family:'Space Mono',monospace;font-size:12px;letter-spacing:.08em;font-weight:600}
  .vr-md td{border-bottom:1px solid rgba(255,255,255,.06);padding:10px 14px;color:#DDD}
`;

// ── 组件 ──
function NeoSection({ id, tag, title, subtitle, accent, children, mobile }: {
  id?: string; tag: string; title: string; subtitle?: string; accent?: string; children: React.ReactNode; mobile?: boolean;
}) {
  const ac = accent || C.green;
  return (
    <section id={id} style={{
      marginBottom: mobile ? 12 : 20, padding: mobile ? '14px 12px' : '24px 28px',
      background: 'rgba(255,255,255,0.02)',
      border: `1px solid ${C.line}`,
      borderLeft: `3px solid ${ac}40`, borderRadius: '0 3px 3px 0',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, paddingBottom: 8, borderBottom: `1px solid ${C.line}` }}>
        <span style={{ fontFamily: 'serif', fontSize: 12, color: `${ac}30`, lineHeight: 1 }}>◇</span>
        <span style={{ fontFamily: F.mono, fontSize: 11, color: ac, background: `${ac}10`, padding: '4px 14px', letterSpacing: '0.14em', borderRadius: 4 }}>{tag}</span>
        <h2 style={{ fontFamily: F.mono, fontSize: 14, color: C.white, margin: 0, letterSpacing: '0.1em' }}>{title}</h2>
        {subtitle && <span style={{ fontFamily: F.mono, fontSize: 11, color: C.mute, marginLeft: 'auto' }}>{subtitle}</span>}
        <span style={{ fontFamily: F.mono, fontSize: 9, color: `${ac}40`, marginLeft: -2 }}>◆</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {children}
      </div>
      {/* 阵法节点 */}
      <div style={{ textAlign: 'center', marginTop: 12, opacity: 0.12, fontFamily: F.mono, fontSize: 8, color: ac, letterSpacing: '0.3em' }}>◆ ◆ ◆</div>
    </section>
  );
}

function BigNum({ val, label, color, mobile }: { val: string; label: string; color: string; mobile?: boolean }) {
  return (
    <div style={{ textAlign: 'center', padding: mobile ? '12px 8px' : '18px 12px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 6, flex: 1 }}>
      <div style={{ fontFamily: F.pixel, fontSize: mobile ? 20 : 26, fontWeight: 700, color, lineHeight: 1.1 }}>{val}</div>
      <div style={{ fontFamily: F.mono, fontSize: mobile ? 9 : 10, color: C.mute, marginTop: 4, letterSpacing: '0.1em' }}>{label}</div>
    </div>
  );
}

function KvTable({ rows, mobile }: { rows: Array<[string, string, boolean?]>; mobile?: boolean }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <tbody>
        {rows.map(([k, v, hl], i) => (
          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            <td style={{ padding: mobile ? '7px 8px' : '10px 16px', color: C.mute, width: mobile ? 90 : 160, fontFamily: F.mono, fontSize: mobile ? 11 : 13, letterSpacing: '0.06em' }}>{k}</td>
            <td style={{ padding: mobile ? '7px 8px' : '10px 16px', color: hl ? C.green : '#CCC', fontWeight: hl ? 600 : 400, fontFamily: F.body, fontSize: mobile ? 13 : 15 }}>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DimBar({ label, score, max, note }: { label: string; score: number; max: number; note?: string }) {
  const pct = Math.min(100, Math.max(0, (score / max) * 100));
  const c = score >= 7 ? C.green : score >= 4 ? C.orange : '#666';
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ fontFamily: F.body, fontSize: 14, color: '#BBB', width: 160, flexShrink: 0 }}>{label}</span>
        <div style={{ flex: 1, height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${pct}%`, background: c, borderRadius: 6, transition: 'width 0.5s' }} />
        </div>
        <span style={{ fontFamily: F.pixel, fontSize: 14, color: c, width: 40, textAlign: 'right', fontWeight: 700 }}>{score}<span style={{ fontSize: 10, color: C.dim }}>/{max}</span></span>
      </div>
      {note && <div style={{ fontFamily: F.body, fontSize: 12, color: C.dim, marginLeft: 174, marginTop: 3 }}>{note}</div>}
    </div>
  );
}

function MD({ text, maxH }: { text: string; maxH?: number }) {
  if (!text || text === '—') return null;
  const html = renderMarkdown(text);
  return (
    <div className="vr-md" style={{ maxHeight: maxH || 'none', overflowY: maxH ? 'auto' : 'visible', padding: '16px 20px', background: 'rgba(0,0,0,.2)', border: '1px solid rgba(255,255,255,0.05)', borderLeft: '2px solid rgba(173,255,0,.2)', fontFamily: F.body, fontSize: 15, lineHeight: 1.9, color: '#C8C8D4' }}
      dangerouslySetInnerHTML={{ __html: html }} />
  );
}

function Pill({ text, color }: { text: string; color: string }) {
  return <span style={{ fontFamily: F.mono, fontSize: 11, color, border: `1px solid ${color}30`, padding: '4px 12px', letterSpacing: '0.12em', background: `${color}08` }}>{text}</span>;
}

function KpiList({ items, color }: { items: Array<Record<string,unknown>>; color: string }) {
  if (!items.length) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {items.map((k, i) => {
        const name = String(k.name || k.kpi || k.milestone || k.signal || k.trigger || '?');
        const target = String(k.target || k.threshold || k.expected_timing || '—');
        const baseline = String(k.baseline || k.current_state || '');
        const freq = String(k.frequency || k.monitor || '');
        return (
          <div key={i} style={{ fontFamily: F.body, fontSize: 14, color: '#BBB', lineHeight: 1.7, padding: '10px 16px', background: 'rgba(0,0,0,.15)', borderLeft: `3px solid ${color}40` }}>
            <b style={{ color }}>{name}</b>: {target}
            {baseline && baseline !== '—' ? <span style={{ color: C.dim }}>（基线: {baseline}）</span> : ''}
            {freq && freq !== '—' ? <span style={{ color: '#555', marginLeft: 10 }}>▸ {freq}</span> : ''}
          </div>
        );
      })}
    </div>
  );
}

function ProbBar({ bearPct, basePct, bullPct }: { bearPct: number; basePct: number; bullPct: number }) {
  const total = bearPct + basePct + bullPct || 1;
  return (
    <div style={{ display: 'flex', height: 36, borderRadius: 4, overflow: 'hidden', fontFamily: F.mono, fontSize: 13, fontWeight: 700, letterSpacing: '0.06em' }}>
      <div style={{ flex: bearPct / total, background: 'linear-gradient(180deg, rgba(255,107,0,.5) 0%, rgba(255,107,0,.3) 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#FFF' }}>熊 {bearPct}%</div>
      <div style={{ flex: basePct / total, background: 'linear-gradient(180deg, rgba(255,255,255,.15) 0%, rgba(255,255,255,.08) 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#F0F0F5' }}>基 {basePct}%</div>
      <div style={{ flex: bullPct / total, background: 'linear-gradient(180deg, rgba(173,255,0,.5) 0%, rgba(173,255,0,.3) 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#050510' }}>牛 {bullPct}%</div>
    </div>
  );
}

/* ================================================================== */
/*  Main                                                                */
/* ================================================================== */
export default function ValuationReport() {
  const { code } = useParams<{ code: string }>();
  const mobile = useMobile();
  const [data, setData] = useState<Record<string,unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeSec, setActiveSec] = useState('exec');

  useEffect(() => {
    if (!code) { setError('无效股票代码'); setLoading(false); return; }
    fetch(`/api/report/${code}/data`).then(r => r.ok ? r.json() : null).then(data => {
        if (data) { setData(data); }
        else { setError('报告未找到'); }
      })
      .catch((e: Error) => setError(`加载失败: ${e.message}`))
      .finally(() => setLoading(false));
  }, [code]);

  useEffect(() => {
    const ids = ['exec','scenario','model','bs','financial','a0','cases','signal','gap','confidence','trade','crosscheck','kpi','triggers','trace','narrative'];
    const h = () => {
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el) { const r = el.getBoundingClientRect(); if (r.top < 200 && r.bottom > 200) { setActiveSec(id); break; } }
      }
    };
    window.addEventListener('scroll', h, { passive: true });
    return () => window.removeEventListener('scroll', h);
  }, []);

  if (mobile) return <ValuationReportMobile />;
  if (!data && !loading && !error) return null;

  // ── 数据解构 ──
  const a0 = (data?.agent0 || {}) as Record<string,unknown>;
  const a1 = (data?.agent1 || {}) as Record<string,unknown>;
  const a2 = (data?.agent2 || {}) as Record<string,unknown>;
  const a3 = (data?.agent3 || {}) as Record<string,unknown>;

  const core = (G(a1, 'packages', 'core', 'fields') || {}) as Record<string,unknown>;
  const cf = Object.keys(core).length > 3 ? core : (G(a1, 'clean_financials') || {}) as Record<string,unknown>;
  const va = (G(a1, 'valuation_anchor') || {}) as Record<string,unknown>;
  const ms = (G(a3, 'market_sanity') || G(a1, 'market_sanity') || {}) as Record<string,unknown>;
  const vr = (G(a3, 'valuation_routing') || G(a1, 'valuation_routing') || {}) as Record<string,unknown>;
  const rd = (G(a2, 'routing_decision') || {}) as Record<string,unknown>;
  const sv = (G(a3, 'scenario_valuation') || {}) as Record<string,unknown>;
  const vs = (G(a3, 'valuation_summary') || sv || {}) as Record<string,unknown>;
  const rdcf = (G(a3, 'reverse_dcf') || {}) as Record<string,unknown>;
  const gap = (G(a3, 'expectation_gap') || {}) as Record<string,unknown>;
  const conf = (G(a3, 'confidence') || {}) as Record<string,unknown>;
  const ta = (G(a3, 'trade_annotation') || {}) as Record<string,unknown>;
  const vx = (G(a3, 'validation_crosscheck') || {}) as Record<string,unknown>;
  const kpis = (G(a3, 'monitoring_kpis') || {}) as Record<string,unknown>;
  const triggers = (G(a3, 'risk_triggers') || {}) as Record<string,unknown>;
  const dataGaps = (G(a3, 'data_gaps') || []) as string[];
  const signalAudit = (G(a3, 'signal_audit') || {}) as Record<string,unknown>;
  const preflight = (G(a3, 'preflight_check') || []) as string[];
  const trace = (G(a3, 'reasoning_trace') || []) as string[];
  const cm = (G(a2, 'case_matches_top3') || G(a2, 'case_comparison') || []) as Array<Record<string,unknown>>;
  const cmAll = (G(a2, 'case_matches_all') || []) as Array<Record<string,unknown>>;
  const narrative = String(G(a3, 'narrative') || '');
  const probRationale = String(G(a3, 'probability_rationale') || '');
  const waccParams = (G(ms, 'wacc_params') || G(va, 'wacc_params') || {}) as Record<string,unknown>;
  const confDims = (G(conf, 'dimensions') || {}) as Record<string, Record<string,unknown>>;
  const taSignals = (G(ta, 'alignment_signals') || []) as string[];
  const taScores = (G(ta, 'dimension_scores') || {}) as Record<string, number>;

  const primaryModel = String(vr?.primary_model || rd?.primary_model || '?');
  const stockName = String(cf?.stock_name || a0?.stock_name || code || '?');
  const mcap = parseFloat(String(cf?.market_cap_yi || cf?.market_cap_billion || 0));
  const modelKey = String(primaryModel[0] || 'A');

  const scenarios: Array<Record<string,unknown>> = Array.isArray(G(a3, 'scenarios')) ? G(a3, 'scenarios') as Array<Record<string,unknown>> : [];
  const sd = (G(sv, 'scenario_details') || {}) as Record<string,unknown>;
  const bear = scenarios.find(s => /bear/i.test(String(s.name || ''))) || sd.bear || {} as Record<string,unknown>;
  const base = scenarios.find(s => /base/i.test(String(s.name || ''))) || sd.base || {} as Record<string,unknown>;
  const bull = scenarios.find(s => /bull/i.test(String(s.name || ''))) || sd.bull || {} as Record<string,unknown>;

  const upside = parseFloat(String(vs?.probability_weighted_upside_pct ?? 0));
  const asym = parseFloat(String(vs?.asymmetry_ratio ?? 0));
  const quality = String(vs?.quality_flag || '?');
  const bp = (() => { const v = Number(G(bear, 'probability_pct') || G(bear, 'probability') || 25); return v < 1 && G(bear, 'probability') ? v * 100 : v; })();
  const bsp = (() => { const v = Number(G(base, 'probability_pct') || G(base, 'probability') || 50); return v < 1 && G(base, 'probability') ? v * 100 : v; })();
  const blp = (() => { const v = Number(G(bull, 'probability_pct') || G(bull, 'probability') || 25); return v < 1 && G(bull, 'probability') ? v * 100 : v; })();
  const confOverall = Number(G(conf, 'overall_score') || 5);

  const isPS = modelKey === 'B', isPE = ['A','C','G','I'].includes(modelKey), isPB = modelKey === 'D', isEV = modelKey === 'E';

  const toc: Record<string,string> = { exec:'摘要', scenario:'情景', model:'路由', bs:'BS检测', financial:'财务', a0:'预路由', cases:'案例', signal:'信号', gap:'预期差', confidence:'置信', trade:'标注', crosscheck:'校验', kpi:'KPI', triggers:'触发', trace:'推理', narrative:'叙事' };

  return (
    <>
    <style>{GLOBAL_CSS}</style>
    <div style={{ minHeight: 'calc(100vh - 58px)', background: C.bg, color: C.white }}>
      <div style={{ maxWidth: 1020, margin: '0 auto', padding: mobile ? '24px 20px' : '40px 48px 80px', position: 'relative', zIndex: 1 }}>
        {loading && <div style={{ padding: 100, textAlign: 'center', fontFamily: F.pixel, fontSize: 18, color: C.dim }}>加载估值报告中...</div>}
        {error && !loading && <div style={{ padding: 100, textAlign: 'center', fontFamily: F.mono, fontSize: 16, color: C.orange }}>{error}</div>}

        {data && !loading && (
          <>
            {/* ═══════ HEADER ═══════ */}
            <div style={{ marginBottom: 36, paddingBottom: 28, borderBottom: '1px solid rgba(173,255,0,.1)' }}>
              <h1 style={{ fontFamily: F.pixel, fontSize: mobile ? 28 : 34, fontWeight: 400, color: C.green, margin: '0 0 14px 0', letterSpacing: '0.06em' }}>
                {stockName} <span style={{ fontWeight: 400, color: '#555', fontSize: '0.6em' }}>({code})</span>
              </h1>
              <div style={{ fontSize: 15, color: '#AAA', fontFamily: "'Noto Sans SC',sans-serif", lineHeight: 2.0, marginBottom: 16, textIndent: '2em' }}>
                {String(G(a0, 'raw_event_text') || G(a0, 'investment_theme') || '').replace(/[#*]/g, '')}
              </div>
              <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', fontFamily: F.mono, fontSize: 13, color: C.dim, alignItems: 'center' }}>
                <span>主模型 <b style={{ color: C.green }}>{primaryModel}</b></span>
                <span style={{ color: '#333' }}>|</span>
                <span>校验 <b style={{ color: '#AAA' }}>{String(vr?.secondary_model || rd?.secondary_model || '?')}</b></span>
                <span style={{ color: '#333' }}>|</span>
                <span>响应 <Pill text={`L${String(a0?.response_level || '?')}`} color={C.green} /></span>
                <span style={{ color: '#333' }}>|</span>
                <span>市值 <b style={{ color: '#CCC' }}>{N(mcap)}亿</b></span>
                <span style={{ color: '#333' }}>|</span>
                <span>行业 <b style={{ color: '#CCC' }}>{String(G(a3, 'report_meta', 'industry') || G(a1, 'industry') || '?')}</b></span>
              </div>
            </div>

            {/* ═══════ TOC ═══════ */}
            <div style={{ display: 'grid', gridTemplateColumns: mobile ? 'repeat(4, 1fr)' : 'repeat(8, 1fr)', gap: 4, marginBottom: 24, padding: mobile ? '10px 8px' : '14px 18px', background: 'rgba(255,255,255,0.02)', border: `1px solid ${C.line}`, borderRadius: 6 }}>
              {Object.entries(toc).map(([id, label]) => (
                <a key={id} href={`#${id}`} style={{ textAlign: 'center', fontFamily: F.mono, fontSize: 12, color: activeSec === id ? C.green : '#555', textDecoration: 'none', padding: '5px 0', borderRadius: 4, border: activeSec === id ? `1px solid ${C.green}20` : '1px solid transparent', background: activeSec === id ? `${C.green}08` : 'transparent', transition: 'all .2s', fontWeight: activeSec === id ? 600 : 400 }}
                  onMouseEnter={e => { e.currentTarget.style.color = C.green; }}
                  onMouseLeave={e => { e.currentTarget.style.color = activeSec === id ? C.green : '#555'; }}>{label}</a>
              ))}
            </div>

            {/* ═══════ 1. 执行摘要 ═══════ */}
            <NeoSection mobile={mobile} id="exec" tag="EXEC" title="执行摘要" accent={C.green}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
                <BigNum val={`${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%`} label="概率加权涨幅" color={upside >= 0 ? C.green : C.orange} mobile={mobile} />
                <BigNum val={`${asym.toFixed(1)}×`} label="不对称比" color={C.white} mobile={mobile} />
                <BigNum val={quality} label="质量等级" color={C.green} mobile={mobile} />
                <BigNum val={`${confOverall}/10`} label="置信度" color={C.gold} mobile={mobile} />
              </div>
              <ProbBar bearPct={bp} basePct={bsp} bullPct={blp} />
              <p style={{ fontFamily: F.body, fontSize: 15, color: '#999', textAlign: 'center', margin: '8px 0 0', lineHeight: 1.8 }}>
                当前市值 <b style={{ color: C.white, fontSize: 16 }}>{N(mcap)}亿</b> → 概率加权 <b style={{ color: C.green, fontSize: 16 }}>{N(vs?.probability_weighted_mcap_yi || vs?.probability_weighted_mcap_billion)}亿</b>
                {'　'} 隐含g={Pct(G(rdcf, 'market_implied_g_pct') || G(ms, 'implied_g_pct'))}　 溢价={Pct(G(rdcf, 'market_premium_pct') || G(ms, 'market_premium_pct'))}
              </p>
            </NeoSection>

            {/* ═══════ 2. 三情景推演 ═══════ */}
            <NeoSection mobile={mobile} id="scenario" tag="SCENARIOS" title="三情景推演" accent={C.green}>
              {scenarios.length > 0 ? (
                <div className="vr-scroll" style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: `1px solid ${C.green}20` }}>
                        <th style={th}>情景</th>
                        <th style={thR}>概率</th>
                        {isPS ? <><th style={thR}>3y CAGR</th><th style={thR}>目标PS</th><th style={thR}>TAM%</th></> : null}
                        {isPE ? <><th style={thR}>ROIC</th><th style={thR}>PE</th></> : null}
                        {isPB ? <><th style={thR}>ROE</th><th style={thR}>PB</th></> : null}
                        {isEV ? <><th style={thR}>EBITDA增速</th><th style={thR}>EV/EBITDA</th></> : null}
                        <th style={thR}>目标市值(亿)</th>
                        <th style={thR}>涨跌幅</th>
                        <th style={{ ...th, width: '28%' }}>因果逻辑</th>
                      </tr>
                    </thead>
                    <tbody>
                      {scenarios.map((s, i) => {
                        const u = parseFloat(String(s?.upside_pct ?? 0));
                        const nar = String(s?.scenario_narrative || '');
                        const name = String(s?.name || '?');
                        const st: Record<string,{c:string;bg:string}> = { bear:{c:C.orange,bg:'rgba(255,107,0,.06)'}, base:{c:C.white,bg:'rgba(255,255,255,.02)'}, bull:{c:C.green,bg:'rgba(173,255,0,.04)'} };
                        const sk = Object.keys(st).find(k => name.toLowerCase().includes(k)) || 'base';
                        const { c, bg } = st[sk];
                        return (
                          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,.04)', background: bg }}>
                            <td style={{ ...td, color: c, fontFamily: F.mono, fontWeight: 700, fontSize: 15 }}>{name.toUpperCase()}</td>
                            <td style={tdR}>{Pct(s?.probability_pct || N(s?.probability))}</td>
                            {isPS ? <><td style={tdR}>{Pct(s?.revenue_growth_3y_cagr_pct || s?.revenue_growth_pct)}</td><td style={tdR}>{N(s?.target_ps)}</td><td style={tdR}>{Pct(s?.tam_penetration_pct)}</td></> : null}
                            {isPE ? <><td style={tdR}>{Pct(s?.roic_assumed_pct || s?.roic_pct)}</td><td style={tdR}>{N(s?.pe_target)}</td></> : null}
                            {isPB ? <><td style={tdR}>{Pct(s?.target_roe_pct)}</td><td style={tdR}>{N(s?.target_pb)}</td></> : null}
                            {isEV ? <><td style={tdR}>{Pct(s?.ebitda_growth_pct)}</td><td style={tdR}>{N(s?.target_ev_ebitda)}</td></> : null}
                            <td style={{ ...tdR, color: '#CCC', fontSize: 15 }}>{N(s?.target_mcap_yi || s?.target_mcap_billion)}</td>
                            <td style={{ ...tdR, color: u >= 0 ? C.green : C.orange, fontWeight: 700, fontSize: 16 }}>{u >= 0 ? '+' : ''}{u.toFixed(1)}%</td>
                            <td style={{ ...td, color: '#999', fontSize: 14, lineHeight: 1.7, maxWidth: 280 }}>{nar}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : <p style={{ fontFamily: F.body, fontSize: 15, color: C.dim }}>情景数据未生成</p>}
              {probRationale && <MD text={probRationale} maxH={180} />}
            </NeoSection>

            {/* ═══════ 3. 估值路由 ═══════ */}
            <NeoSection mobile={mobile} id="model" tag="ROUTE" title="估值路由与模型决策" accent={C.green}>
              <KvTable mobile={mobile} rows={[
                ['主模型', primaryModel, true],
                ['校验模型', String(vr?.secondary_model || rd?.secondary_model || '?')],
                ['模型分类', String(vr?.model_category || rd?.model_category || '?')],
              ]} />
              {Boolean(G(vr, 'routing_reason')) && <MD text={String(G(vr, 'routing_reason') || G(rd, 'routing_reason') || '')} />}
            </NeoSection>

            {/* ═══════ 4. BS检测器 ═══════ */}
            <NeoSection mobile={mobile} id="bs" tag="BS" title="BS检测器 · 市场定价了什么" accent={C.orange}>
              <div style={{ fontFamily: F.body, fontSize: 16, color: C.orange, fontWeight: 700, marginBottom: 12 }}>{String(ms?.bs_level || '?')}</div>
              {Boolean(ms?.bs_secondary) && <div style={{ fontFamily: F.body, fontSize: 14, color: '#999', marginBottom: 8 }}>{String(ms.bs_secondary)}</div>}
              <KvTable mobile={mobile} rows={[
                ['EV', `${N(ms?.ev_yi || ms?.ev_billion)}亿`], ['NOPAT', `${N(ms?.nopat_yi || ms?.nopat_billion)}亿`],
                ['ROIC', Pct(ms?.roic_pct)], ['WACC', Pct(ms?.wacc_simple_pct)],
                ['隐含g', Pct(ms?.implied_g_pct)], ['市场溢价', Pct(ms?.market_premium_pct)],
                ['PE(TTM)', `${N(ms?.pe_ttm)}×`], ['PE分位', String(ms?.pe_historical_rank || '?')], ['PB', `${N(ms?.pb)}×`],
              ]} />
              {Boolean(ms?.market_story) && <MD text={String(ms.market_story)} />}
              {/* WACC */}
              {Object.keys(waccParams).length > 0 && (
                <div>
                  <h4 style={{ fontFamily: F.mono, fontSize: 13, color: C.green, margin: '12px 0 8px', letterSpacing: '0.1em' }}>▸ WACC 参数</h4>
                  <KvTable mobile={mobile} rows={[
                    ['Rf', Pct(waccParams?.rf_pct)], ['Beta', N(waccParams?.beta)],
                    ['ERP', Pct(waccParams?.erp_pct)], ['Re', Pct(waccParams?.re_pct)],
                    ['Rd', Pct(waccParams?.rd_pct)], ['负债率', Pct(waccParams?.d_ratio_pct)],
                    ['WACC', Pct(waccParams?.wacc_pct || va?.wacc_mid_pct)],
                  ]} />
                </div>
              )}
            </NeoSection>

            {/* ═══════ 5. 财务全景 ═══════ */}
            <NeoSection mobile={mobile} id="financial" tag="FIN" title="财务全景" accent={C.green} subtitle={String(G(a1, 'overall_data_quality_score') || '?') + '/10 数据质量'}>
              <KvTable mobile={mobile} rows={[
                ['营收TTM', `${N(cf?.revenue_ttm_yi || cf?.revenue_ttm_billion)}亿`],
                ['净利TTM', `${N(cf?.net_profit_ttm_yi || cf?.net_profit_billion)}亿`],
                ['ROIC', Pct(cf?.roic_pct)], ['毛利率', Pct(cf?.gross_margin_pct)],
                ['净利率', Pct(cf?.net_margin_pct)], ['ROE', Pct(cf?.roe_ttm_pct)],
                ['经营现金流', `${N(cf?.ocf_ttm_yi || cf?.operating_cf_ttm_billion)}亿`],
                ['资本开支', `${N(cf?.capex_ttm_yi || cf?.capex_ttm_billion)}亿`],
                ['总资产', `${N(cf?.total_assets_yi || cf?.total_assets_billion)}亿`],
                ['净资产', `${N(cf?.total_equity_yi || cf?.total_equity_billion)}亿`],
                ['有息负债', `${N(cf?.interest_bearing_debt_yi || cf?.interest_bearing_debt_billion)}亿`],
                ['净负债', `${N(cf?.net_debt_yi || cf?.net_debt_billion)}亿`],
                ['EBITDA', `${N(cf?.ebitda_ttm_yi || cf?.ebitda_ttm_billion)}亿`],
              ]} />
            </NeoSection>

            {/* ═══════ 6. Agent0 预路由 ═══════ */}
            <NeoSection mobile={mobile} id="a0" tag="A0" title="预路由 · 事件分析" accent={C.green} subtitle="Coze Agent0">
              {Boolean(G(a0, 'investment_theme')) && <MD text={String(G(a0, 'investment_theme')).slice(0, 3000)} />}
              {Boolean(G(a0, 'event_deduction')) && <MD text={String(G(a0, 'event_deduction'))} />}
              {Boolean(G(a0, 'preliminary_reasoning')) && <MD text={String(G(a0, 'preliminary_reasoning'))} />}
              {Boolean(G(a0, 'adversarial_thinking')) && <MD text={String(G(a0, 'adversarial_thinking')).slice(0, 1500)} />}
              {Boolean(G(a0, 'knowledge_supplement')) && <MD text={String(G(a0, 'knowledge_supplement')).slice(0, 1500)} />}
              {Boolean(G(a0, 'industry_expert_research')) && <MD text={String(G(a0, 'industry_expert_research')).slice(0, 2000)} />}
              {Boolean(G(a0, 'future')) && <MD text={String(G(a0, 'future')).slice(0, 1000)} />}
              {Boolean(G(a0, 'raw_event_text')) && <MD text={String(G(a0, 'raw_event_text')).slice(0, 1000)} />}
            </NeoSection>

            {/* ═══════ 7. 案例比对 ═══════ */}
            {cm.length > 0 && (
              <NeoSection mobile={mobile} id="cases" tag="CASE" title="案例比对" accent="#C88D3A" subtitle={`匹配 ${cmAll.length || cm.length} 例`}>
                {cm.map((c, i) => {
                  const dims = (c?.six_dimension_judgment || c?.dimensions || {}) as Record<string,unknown>;
                  const dl: Record<string,string> = { driver_strength:'驱动', market_space:'空间', moat:'卡位', paradigm:'范式', catalyst_density:'催化剂', failure_risk:'风险' };
                  return (
                    <div key={i} style={{ padding: '18px 22px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(200,141,58,.15)', borderLeft: '3px solid #C88D3A' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
                        <span style={{ fontFamily: F.pixel, fontSize: 17, color: C.white }}>{String(c?.case_code || '?')}</span>
                        <span style={{ fontFamily: F.mono, fontSize: 14, color: '#C88D3A' }}>折扣 {N(c?.comprehensive_discount_pct)}%</span>
                      </div>
                      {Boolean(c?.key_anchor) && <div style={{ fontFamily: F.body, fontSize: 13, color: C.mute, marginBottom: 8 }}>{String(c.key_anchor)}</div>}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 6 }}>
                        {Object.entries(dims).map(([k, v]) => (
                          <div key={k} style={{ fontFamily: F.body, fontSize: 13, color: '#999' }}>
                            <span style={{ color: C.dim }}>{dl[k] || k}:</span> {String(v)}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
                {Boolean(G(a2, 'case_anchors_text')) && <MD text={String(G(a2, 'case_anchors_text')).slice(0, 1200)} maxH={200} />}
              </NeoSection>
            )}

            {/* ═══════ 8. 信号审计 ═══════ */}
            {G(signalAudit, 'step2b_match') && (
              <NeoSection mobile={mobile} id="signal" tag="SIG" title="信号审计" accent={C.green}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
                  <span style={{ fontFamily: F.pixel, fontSize: 22, color: C.green }}>{N(G(signalAudit, 'step2d_score'))}</span>
                  <span style={{ fontFamily: F.body, fontSize: 14, color: '#999' }}>{String(G(signalAudit, 'score_rationale') || '').slice(0, 200)}</span>
                </div>
                {(G(signalAudit, 'step2b_match') as Array<Record<string,unknown>>).map((m, i) => (
                  <div key={i} style={{ fontFamily: F.body, fontSize: 14, color: '#BBB', padding: '8px 14px', borderBottom: '1px solid rgba(255,255,255,.03)', background: 'rgba(0,0,0,.1)' }}>
                    <b style={{ color: m?.match === '支持' ? C.green : C.orange }}>{String(m?.match)}</b>{' '}
                    {String(m?.signal)} <span style={{ color: C.dim, fontSize: 12 }}>({String(m?.source_level)})</span> — {String(m?.basis)}
                  </div>
                ))}
              </NeoSection>
            )}

            {/* ═══════ 9. 预期差 ═══════ */}
            <NeoSection mobile={mobile} id="gap" tag="GAP" title="预期差" accent={C.green}>
              {Boolean(G(gap, 'level')) && (
                <div style={{ fontFamily: F.mono, fontSize: 17, color: C.green, marginBottom: 8, textShadow: `0 0 10px ${C.green}20`, fontWeight: 700 }}>{String(gap?.level || '?')}</div>
              )}
              {Boolean(gap?.note) && <MD text={String(gap.note)} />}
              {/* 反向DCF 子字段补充 */}
              {(Boolean(G(rdcf, 'my_implied_g_pct')) || Boolean(G(rdcf, 'expectation_gap_pct')) || Boolean(G(rdcf, 'gap_direction')) || Boolean(G(rdcf, 'gap_magnitude'))) && (
                <KvTable mobile={mobile} rows={[
                  ['市场隐含g', Pct(G(rdcf, 'market_implied_g_pct'))],
                  ['推演隐含g', Pct(G(rdcf, 'my_implied_g_pct'))],
                  ['Gap幅度', `${Pct(G(rdcf, 'expectation_gap_pct'))} (${String(G(rdcf, 'gap_direction') || '')}·${String(G(rdcf, 'gap_magnitude') || '')})`],
                ]} />
              )}
            </NeoSection>

            {/* ═══════ 10. 置信度 ═══════ */}
            <NeoSection mobile={mobile} id="confidence" tag="CONF" title={`置信度: ${confOverall}/10（${String(conf?.overall_label || '?')}）`} accent={C.green}>
              {Object.entries(confDims).map(([key, d]) => (
                <DimBar key={key} label={String(d?.label || key)} score={Number(d?.score || 5)} max={10} note={String(d?.note || '').slice(0, 140)} />
              ))}
            </NeoSection>

            {/* ═══════ 11. 交易标注 ═══════ */}
            <NeoSection mobile={mobile} id="trade" tag="TRADE" title={`交易标注: ${String(G(ta, 'tier') || '?')}（${String(G(ta, 'total_score') || '?')}）`} accent={C.orange}>
              {Object.entries({ odds_quality:'S₁ 赔率质量', pricing_headroom:'S₂ 定价空间', transmission_confidence:'S₃ 传导确定性', model_consistency:'S₄ 模型自洽' }).map(([key, label]) => (
                <DimBar key={key} label={label} score={Number(taScores?.[key] || 0)} max={4} />
              ))}
              {taSignals.length > 0 && (
                <ul style={{ listStyle: 'none', margin: '10px 0 0', padding: 0 }}>
                  {taSignals.map((s, i) => <li key={i} style={{ fontFamily: F.body, fontSize: 14, color: '#999', padding: '4px 0' }}>▸ {s}</li>)}
                </ul>
              )}
              {Boolean(G(ta, 'tier_note')) && <MD text={String(G(ta, 'tier_note'))} />}
              {Boolean(G(ta, 'suggested_action')) && <MD text={String(G(ta, 'suggested_action'))} />}
            </NeoSection>

            {/* ═══════ 12. 交叉验证 ═══════ */}
            {G(vx, 'validation_model') && (
              <NeoSection mobile={mobile} id="crosscheck" tag="CROSS" title={`校验: ${String(vx?.validation_model)}（${String(vx?.validation_paradigm || '')}）`} accent="#C88D3A">
                <KvTable mobile={mobile} rows={[
                  ['主模型', `${N(vx?.base_target_mcap_yi || vx?.base_target_mcap_billion)}亿`],
                  ['校验模型', vx?.validation_mcap_yi != null ? `${N(vx.validation_mcap_yi)}亿` : '数据异常'],
                  ['差异', `${Pct(vx?.gap_pct)} (${String(vx?.gap_direction || '')})`, true],
                ]} />
                {Boolean(vx?.assessment) && <MD text={String(vx.assessment)} />}
              </NeoSection>
            )}

            {/* ═══════ 13. 监测KPI ═══════ */}
            <NeoSection mobile={mobile} id="kpi" tag="KPI" title="未来跟踪指标" accent={C.green}>
              <h4 style={{ fontFamily: F.mono, fontSize: 13, color: C.green, margin: '0 0 8px', letterSpacing: '0.1em' }}>财务验证</h4>
              <KpiList items={(G(kpis, 'financial_verification_kpis') || []) as Array<Record<string,unknown>>} color={C.green} />
              <h4 style={{ fontFamily: F.mono, fontSize: 13, color: '#C88D3A', margin: '14px 0 8px', letterSpacing: '0.1em' }}>事件里程碑</h4>
              <KpiList items={(G(kpis, 'event_milestone_kpis') || []) as Array<Record<string,unknown>>} color="#C88D3A" />
              <h4 style={{ fontFamily: F.mono, fontSize: 13, color: C.orange, margin: '14px 0 8px', letterSpacing: '0.1em' }}>竞争信号</h4>
              <KpiList items={(G(kpis, 'competition_signal_kpis') || []) as Array<Record<string,unknown>>} color={C.orange} />
              <h4 style={{ fontFamily: F.mono, fontSize: 13, color: '#AD00FF', margin: '14px 0 8px', letterSpacing: '0.1em' }}>风险触发</h4>
              <KpiList items={(G(kpis, 'risk_trigger_kpis') || []) as Array<Record<string,unknown>>} color="#AD00FF" />
            </NeoSection>

            {/* ═══════ 14. 风险触发器 ═══════ */}
            {Object.keys(triggers).length > 0 && (
              <NeoSection mobile={mobile} id="triggers" tag="RISK" title="风险触发器" accent={C.orange}>
                <KvTable mobile={mobile} rows={Object.entries(triggers).filter(([k]) => k !== 'monitoring_frequency').map(([k, v]) => [k === 'bull_trigger' ? '牛触发' : k === 'bear_trigger' ? '熊触发' : k, String(v).slice(0, 200), k === 'bear_trigger'] as [string,string,boolean?])} />
                <p style={{ fontFamily: F.mono, fontSize: 12, color: C.dim, marginTop: 8 }}>验证频率: {String(triggers?.monitoring_frequency || '?')}</p>
              </NeoSection>
            )}

            {/* ═══════ 15. 数据缺口 ═══════ */}
            {dataGaps.length > 0 && (
              <NeoSection mobile={mobile} id="gap" tag="GAP" title="数据缺口" accent={C.orange}>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {dataGaps.map((g, i) => <li key={i} style={{ fontFamily: F.body, fontSize: 14, color: '#C88D3A', padding: '5px 0' }}>▸ {g}</li>)}
                </ul>
              </NeoSection>
            )}

            {/* ═══════ 16. 推理追踪 ═══════ */}
            {trace.length > 0 && (
              <NeoSection mobile={mobile} id="trace" tag="TRACE" title="推理追踪" accent={C.dim}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {trace.map((t, i) => (
                    <div key={i} style={{ fontFamily: F.body, fontSize: 14, color: '#999', padding: '10px 16px', background: 'rgba(255,255,255,0.02)', borderLeft: '2px solid rgba(255,255,255,.06)' }}>
                      <span style={{ color: C.dim, fontFamily: F.mono, fontSize: 11 }}>[{i + 1}]</span> {t}
                    </div>
                  ))}
                </div>
              </NeoSection>
            )}

            {/* ═══════ 17. Preflight ═══════ */}
            {preflight.length > 0 && (
              <NeoSection mobile={mobile} id="trace" tag="PRE" title="起飞前检查" accent={C.green}>
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {preflight.map((s, i) => <li key={i} style={{ fontFamily: F.body, fontSize: 14, color: /PASS/i.test(s) ? C.green : C.orange, padding: '4px 0' }}>▸ {s}</li>)}
                </ul>
              </NeoSection>
            )}

            {/* ═══════ 18. 叙事 ═══════ */}
            <NeoSection mobile={mobile} id="narrative" tag="N" title="叙事" accent={C.green}>
              <MD text={narrative || '暂无叙事数据'} />
            </NeoSection>

            {/* ═══════ Footer ═══════ */}
            <div style={{ textAlign: 'center', paddingTop: 28, marginTop: 20, borderTop: `1px solid ${C.line}`, fontFamily: F.mono, fontSize: 12, color: '#444' }}>
              估值重构引擎 V5 | {code} | 不构成投资建议
            </div>
          </>
        )}
      </div>
    </div>
    </>
  );
}

const th: React.CSSProperties = { padding: '12px 14px', textAlign: 'left', color: C.green, fontSize: 12, fontFamily: "'Space Mono',monospace", fontWeight: 600, letterSpacing: '0.08em', borderBottom: `1px solid ${C.green}20` };
const thR: React.CSSProperties = { ...th, textAlign: 'right' };
const td: React.CSSProperties = { padding: '14px 14px', color: '#C8C8D4', verticalAlign: 'top', fontSize: 14 };
const tdR: React.CSSProperties = { ...td, textAlign: 'right', fontFamily: "'Space Mono',monospace", fontSize: 14 };
