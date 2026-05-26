import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { renderMarkdown } from '../lib/utils';

const C = { green: '#ADFF00', orange: '#FF5C00', gold: '#C88D3A', white: '#F2F4F3', dim: '#888', mute: '#555', line: '#2A2A2A', bg: '#050401' };
const G = (obj: unknown, ...path: string[]): unknown => {
  let cur = obj;
  for (const k of path) { if (cur == null || typeof cur !== 'object') return undefined; cur = (cur as Record<string,unknown>)[k]; }
  return cur;
};
const N = (v: unknown, d = '—'): string => {
  if (v == null) return d;
  const f = parseFloat(String(v));
  return isNaN(f) ? String(v) : (f === Math.round(f) ? String(Math.round(f)) : f.toFixed(1));
};
const Pct = (v: unknown): string => { const s = N(v); return s === '—' ? s : s + '%'; };

const s = {
  container: { padding: '12px 14px 48px', color: '#F2F4F3', fontFamily: "'Noto Sans SC','IBM Plex Mono',sans-serif" },
  h1: { fontSize: 22, fontWeight: 700, color: C.green, marginBottom: 4 },
  h2: { fontSize: 17, fontWeight: 700, color: C.green, marginBottom: 10, paddingBottom: 8, borderBottom: `1px solid ${C.line}` },
  h3: { fontSize: 14, fontWeight: 600, color: '#CCC' },
  card: { padding: '14px 12px', background: 'rgba(255,255,255,0.03)', border: `1px solid ${C.line}`, borderRadius: 4 },
  pill: (color: string) => ({ display: 'inline-block', padding: '2px 8px', fontSize: 11, borderRadius: 3, background: `${color}18`, color, fontFamily: "'Space Mono',monospace" }),
  tag: { fontSize: 11, fontFamily: "'Space Mono',monospace", color: C.mute },
  body: { fontSize: 15, lineHeight: 1.9, color: '#BBB' },
  num: { fontFamily: "'Geist Pixel','Space Mono',monospace", fontWeight: 700 },
  p: { margin: '4px 0' },
} as const;

function Accordion({ title, subtitle, accent, defaultOpen, children }: { title: string; subtitle?: string; accent?: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const ac = accent || C.green;
  return (
    <div style={{ marginBottom: 10, border: `1px solid ${C.line}`, borderLeft: `3px solid ${ac}40`, borderRadius: '0 4px 4px 0', overflow: 'hidden' }}>
      <div onClick={() => setOpen(!open)} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 12px', background: 'rgba(255,255,255,0.02)', cursor: 'pointer', userSelect: 'none' }}>
        <div>
          <div style={{ ...s.h3, margin: 0 }}>{title}</div>
          {subtitle && <div style={{ ...s.tag, marginTop: 2 }}>{subtitle}</div>}
        </div>
        <span style={{ color: open ? ac : '#555', fontSize: 12, transition: 'transform 0.2s', transform: open ? 'rotate(90deg)' : 'none' }}>▶</span>
      </div>
      {open && <div style={{ padding: '12px' }}>{children}</div>}
    </div>
  );
}

function BigNum({ val, label, color }: { val: string; label: string; color: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '10px 6px', background: 'rgba(255,255,255,0.02)', border: `1px solid ${C.line}`, borderRadius: 4, flex: '1 1 45%' }}>
      <div style={{ ...s.num, fontSize: 22, color, lineHeight: 1.1 }}>{val}</div>
      <div style={{ fontSize: 10, color: C.mute, marginTop: 2 }}>{label}</div>
    </div>
  );
}

function Row({ label, value, hl }: { label: string; value: string; hl?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.03)', fontSize: 14 }}>
      <span style={{ color: C.dim, flexShrink: 0, marginRight: 12 }}>{label}</span>
      <span style={{ color: hl ? C.green : '#CCC', fontWeight: hl ? 600 : 400, textAlign: 'right', wordBreak: 'break-word' }}>{value}</span>
    </div>
  );
}

function MD({ text, maxH }: { text: string; maxH?: number }) {
  return (
    <div
      style={{ fontSize: 14, lineHeight: 1.9, color: '#BBB', maxHeight: maxH || 'none', overflowY: maxH ? 'auto' : 'visible', wordBreak: 'break-word' }}
      dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }}
    />
  );
}

function ScenarioCard({ name, data, accent }: { name: string; data: Record<string,unknown>; accent: string }) {
  const upside = Number(G(data, 'upside_pct') || 0);
  const mcap = Number(G(data, 'target_mcap_yi') || G(data, 'target_mcap_billion') || 0);
  const prob = Number(G(data, 'probability_pct') || G(data, 'probability') || 0);
  const logic = String(G(data, 'causal_logic') || G(data, 'logic') || '');
  return (
    <div style={{ ...s.card, borderLeft: `3px solid ${accent}`, marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ ...s.num, fontSize: 16, color: accent }}>{name}</span>
        <span style={{ ...s.pill(accent) }}>{prob.toFixed(0)}%</span>
      </div>
      <div style={{ display: 'flex', gap: 16, marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: C.dim }}>涨幅 <span style={{ color: upside >= 0 ? C.green : C.orange, fontWeight: 600 }}>{upside >= 0 ? '+' : ''}{upside.toFixed(1)}%</span></span>
        {mcap > 0 && <span style={{ fontSize: 13, color: C.dim }}>市值 <span style={{ color: '#CCC', fontWeight: 600 }}>{N(mcap)}亿</span></span>}
      </div>
      {logic && <div style={{ fontSize: 13, color: '#999', lineHeight: 1.7 }}>{logic}</div>}
    </div>
  );
}

export default function ValuationReportMobile() {
  const { code } = useParams<{ code: string }>();
  const [data, setData] = useState<Record<string,unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!code) { setError('无效股票代码'); setLoading(false); return; }
    fetch(`/api/report/${code}/data`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(setData)
      .catch((e: Error) => setError(`加载失败: ${e.message}`))
      .finally(() => setLoading(false));
  }, [code]);

  if (loading) return <div style={{ padding: 80, textAlign: 'center', color: C.dim, fontSize: 16 }}>加载估值报告中...</div>;
  if (error) return <div style={{ padding: 80, textAlign: 'center', color: C.orange, fontSize: 16 }}>{error}</div>;
  if (!data) return null;

  const a0 = (data.agent0 || {}) as Record<string,unknown>;
  const a1 = (data.agent1 || {}) as Record<string,unknown>;
  const a2 = (data.agent2 || {}) as Record<string,unknown>;
  const a3 = (data.agent3 || {}) as Record<string,unknown>;
  const cf = (G(a1, 'packages', 'core', 'fields') || G(a1, 'clean_financials') || {}) as Record<string,unknown>;
  const ms = (G(a3, 'market_sanity') || {}) as Record<string,unknown>;
  const vr = (G(a3, 'valuation_routing') || {}) as Record<string,unknown>;
  const rd = (G(a2, 'routing_decision') || {}) as Record<string,unknown>;
  const vs = (G(a3, 'valuation_summary') || {}) as Record<string,unknown>;
  const conf = (G(a3, 'confidence') || {}) as Record<string,unknown>;
  const ta = (G(a3, 'trade_annotation') || {}) as Record<string,unknown>;
  const rdcf = (G(a3, 'reverse_dcf') || {}) as Record<string,unknown>;
  const gap = (G(a3, 'expectation_gap') || {}) as Record<string,unknown>;
  const waccParams = (G(ms, 'wacc_params') || {}) as Record<string,unknown>;

  const stockName = String(cf?.stock_name || a0?.stock_name || code || '?');
  const primaryModel = String(vr?.primary_model || rd?.primary_model || '?');
  const upside = parseFloat(String(vs?.probability_weighted_upside_pct ?? 0));
  const asym = parseFloat(String(vs?.asymmetry_ratio ?? 0));
  const quality = String(vs?.quality_flag || '?');
  const confOverall = Number(G(conf, 'overall_score') || 5);

  const scenarios: Array<Record<string,unknown>> = Array.isArray(G(a3, 'scenarios')) ? G(a3, 'scenarios') as Array<Record<string,unknown>> : [];
  const bear = scenarios.find(s => /bear/i.test(String(s.name || ''))) || {} as Record<string,unknown>;
  const base = scenarios.find(s => /base/i.test(String(s.name || ''))) || {} as Record<string,unknown>;
  const bull = scenarios.find(s => /bull/i.test(String(s.name || ''))) || {} as Record<string,unknown>;

  const cm = (G(a2, 'case_matches_top3') || G(a2, 'case_comparison') || []) as Array<Record<string,unknown>>;
  const signalAudit = (G(a3, 'signal_audit') || {}) as Record<string,unknown>;
  const kpis = (G(a3, 'monitoring_kpis') || {}) as Record<string,unknown>;
  const triggers = (G(a3, 'risk_triggers') || {}) as Record<string,unknown>;
  const trace = (G(a3, 'reasoning_trace') || []) as string[];
  const narrative = String(G(a3, 'narrative') || '');
  const vx = (G(a3, 'validation_crosscheck') || {}) as Record<string,unknown>;

  return (
    <div style={{ minHeight: '100vh', background: C.bg }}>
      <div style={s.container}>

        {/* ── Header ── */}
        <div style={{ marginBottom: 16 }}>
          <h1 style={s.h1}>{stockName}<span style={{ fontWeight: 400, color: '#555', fontSize: 14, marginLeft: 8 }}>({code})</span></h1>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginTop: 8 }}>
            <span style={s.pill(C.green)}>模型 {primaryModel}</span>
            <span style={s.tag}>质量 {quality}</span>
            <span style={s.tag}>置信 {confOverall}/10</span>
          </div>
        </div>

        {/* ── 大数 ── */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
          <BigNum val={`${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%`} label="概率加权涨幅" color={upside >= 0 ? C.green : C.orange} />
          <BigNum val={`${asym.toFixed(1)}×`} label="不对称比" color={C.white} />
          <BigNum val={quality} label="质量等级" color={C.green} />
          <BigNum val={`${confOverall}/10`} label="置信度" color={C.gold} />
        </div>

        {/* ── 三情景 — 手机专用排版 ── */}
        <Accordion title="三情景推演" defaultOpen accent={C.green}>
          <div style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', height: 28, borderRadius: 4, overflow: 'hidden', marginBottom: 10 }}>
              {(() => { const bp2 = Number(G(bear, 'probability_pct') || G(bear, 'probability') || 25); const bsp2 = Number(G(base, 'probability_pct') || G(base, 'probability') || 50); const blp2 = Number(G(bull, 'probability_pct') || G(bull, 'probability') || 25); const t = bp2+bsp2+blp2 || 1; return (<><div style={{ flex: `${bp2/t*100}`, background: '#FF5C00', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: '#fff' }}>bear {bp2.toFixed(0)}%</div><div style={{ flex: `${bsp2/t*100}`, background: '#888', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: '#fff' }}>base {bsp2.toFixed(0)}%</div><div style={{ flex: `${blp2/t*100}`, background: C.green, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: C.bg }}>bull {blp2.toFixed(0)}%</div></>); })()}
            </div>
          </div>
          <ScenarioCard name="bull" data={bull} accent={C.green} />
          <ScenarioCard name="base" data={base} accent="#888" />
          <ScenarioCard name="bear" data={bear} accent={C.orange} />
          {Boolean(G(a3, 'probability_rationale')) && (
            <div style={{ marginTop: 8 }}>
              <MD text={String(G(a3, 'probability_rationale'))} maxH={300} />
            </div>
          )}
        </Accordion>

        {/* ── BS 检测 ── */}
        {(Object.keys(ms).length > 0 || Object.keys(rdcf).length > 0) && (
          <Accordion title="BS 检测 · 市场定价" accent={C.orange}>
            {Boolean(ms?.bs_level) && <div style={{ ...s.body, fontSize: 17, color: C.orange, fontWeight: 700, marginBottom: 10 }}>{String(ms.bs_level)}</div>}
            {Boolean(ms?.bs_secondary) && <div style={{ ...s.body, fontSize: 14, color: '#999', marginBottom: 8 }}>{String(ms.bs_secondary)}</div>}
            <div style={s.card}>
              <Row label="EV" value={`${N(ms?.ev_yi || ms?.ev_billion)}亿`} />
              <Row label="NOPAT" value={`${N(ms?.nopat_yi || ms?.nopat_billion)}亿`} />
              <Row label="ROIC" value={Pct(ms?.roic_pct)} />
              <Row label="WACC" value={Pct(ms?.wacc_simple_pct)} />
              <Row label="隐含g" value={Pct(ms?.implied_g_pct || G(rdcf, 'market_implied_g_pct'))} hl />
              <Row label="市场溢价" value={Pct(ms?.market_premium_pct || G(rdcf, 'market_premium_pct'))} />
              <Row label="PE(TTM)" value={`${N(ms?.pe_ttm)}×`} />
              <Row label="PB" value={`${N(ms?.pb)}×`} />
            </div>
            {Boolean(ms?.market_story) && <div style={{ marginTop: 8 }}><MD text={String(ms.market_story)} maxH={200} /></div>}
          </Accordion>
        )}

        {/* ── 估值路由 ── */}
        <Accordion title="估值路由" accent={C.green}>
          <Row label="主模型" value={primaryModel} hl />
          <Row label="校验模型" value={String(vr?.secondary_model || rd?.secondary_model || '?')} />
          <Row label="模型分类" value={String(vr?.model_category || rd?.model_category || '?')} />
          {Boolean(G(vr, 'routing_reason')) && <div style={{ marginTop: 8 }}><MD text={String(G(vr, 'routing_reason') || '')} maxH={200} /></div>}
        </Accordion>

        {/* ── 财务 ── */}
        {Object.keys(cf).length > 3 && (
          <Accordion title="财务全景" accent={C.green}>
            <div style={s.card}>
              <Row label="营收TTM" value={`${N(cf?.revenue_ttm_yi || cf?.revenue_ttm_billion)}亿`} />
              <Row label="净利TTM" value={`${N(cf?.net_profit_ttm_yi || cf?.net_profit_billion)}亿`} />
              <Row label="ROIC" value={Pct(cf?.roic_pct)} hl />
              <Row label="毛利率" value={Pct(cf?.gross_margin_pct)} />
              <Row label="净利率" value={Pct(cf?.net_margin_pct)} />
              <Row label="ROE" value={Pct(cf?.roe_ttm_pct)} />
              <Row label="经营CF" value={`${N(cf?.ocf_ttm_yi || cf?.operating_cf_ttm_billion)}亿`} />
              <Row label="总资产" value={`${N(cf?.total_assets_yi || cf?.total_assets_billion)}亿`} />
            </div>
            {Object.keys(waccParams).length > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 12, color: C.mute, marginBottom: 6 }}>WACC 参数</div>
                <div style={s.card}>
                  <Row label="Rf" value={Pct(waccParams?.rf_pct)} />
                  <Row label="Beta" value={N(waccParams?.beta)} />
                  <Row label="ERP" value={Pct(waccParams?.erp_pct)} />
                  <Row label="WACC" value={Pct(waccParams?.wacc_pct)} hl />
                </div>
              </div>
            )}
          </Accordion>
        )}

        {/* ── Agent0 预路由 ── */}
        {(Boolean(G(a0, 'investment_theme')) || Boolean(G(a0, 'event_deduction'))) && (
          <Accordion title="事件分析" accent={C.green}>
            {Boolean(G(a0, 'investment_theme')) && <MD text={String(G(a0, 'investment_theme')).slice(0, 2000)} maxH={300} />}
            {Boolean(G(a0, 'event_deduction')) && <MD text={String(G(a0, 'event_deduction')).slice(0, 2000)} maxH={300} />}
            {Boolean(G(a0, 'preliminary_reasoning')) && <MD text={String(G(a0, 'preliminary_reasoning')).slice(0, 1500)} maxH={200} />}
          </Accordion>
        )}

        {/* ── 案例比对 ── */}
        {cm.length > 0 && (
          <Accordion title="案例比对" accent={C.gold}>
            {cm.map((c, i) => {
              const dims = (c?.six_dimension_judgment || c?.dimensions || {}) as Record<string,unknown>;
              const dl: Record<string,string> = { driver_strength:'驱动', market_space:'空间', moat:'卡位', paradigm:'范式', catalyst_density:'催化剂', failure_risk:'风险' };
              return (
                <div key={i} style={{ ...s.card, marginBottom: 8, borderLeft: `2px solid ${C.gold}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontWeight: 600, color: C.white, fontSize: 15 }}>{String(c?.case_code || '?')}</span>
                    <span style={{ ...s.pill(C.gold) }}>折扣 {N(c?.comprehensive_discount_pct)}%</span>
                  </div>
                  {Object.entries(dims).map(([k, v]) => (
                    <div key={k} style={{ fontSize: 13, color: '#999', padding: '2px 0' }}>
                      <span style={{ color: C.dim }}>{dl[k] || k}:</span> {String(v)}
                    </div>
                  ))}
                </div>
              );
            })}
          </Accordion>
        )}

        {/* ── 信号审计 ── */}
        {Boolean(G(signalAudit, 'step2b_match')) && (
          <Accordion title={`信号审计 · ${N(G(signalAudit, 'step2d_score'))}分`} accent={C.green}>
            {(G(signalAudit, 'step2b_match') as Array<Record<string,unknown>>).map((m, i) => (
              <div key={i} style={{ fontSize: 14, color: '#BBB', padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                <b style={{ color: m?.match === '支持' ? C.green : C.orange }}>{String(m?.match)}</b>{' '}
                {String(m?.signal)}{' '}
                <span style={{ color: C.dim, fontSize: 12 }}>(L{String(m?.source_level)})</span>
              </div>
            ))}
          </Accordion>
        )}

        {/* ── 预期差 ── */}
        {Boolean(G(gap, 'level')) && (
          <Accordion title="预期差" accent={C.green}>
            <div style={{ ...s.num, fontSize: 18, color: C.green, marginBottom: 8 }}>{String(gap?.level || '?')}</div>
            {Boolean(gap?.note) && <div style={s.body}>{String(gap.note)}</div>}
          </Accordion>
        )}

        {/* ── 置信度 ── */}
        {Object.keys(conf).length > 0 && (
          <Accordion title={`置信度 · ${confOverall}/10`} accent={C.green}>
            {Object.entries(G(conf, 'dimensions') as Record<string, Record<string,unknown>> || {}).map(([key, d]) => (
              <div key={key} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 2 }}>
                  <span style={{ color: '#AAA' }}>{String(d?.label || key)}</span>
                  <span style={{ fontFamily: "'Space Mono',monospace", color: C.green }}>{N(d?.score)}/10</span>
                </div>
                <div style={{ height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 2 }}>
                  <div style={{ height: '100%', width: `${Number(d?.score || 5) * 10}%`, background: C.green, borderRadius: 2 }} />
                </div>
                {Boolean(d?.note) && <div style={{ fontSize: 11, color: C.mute, marginTop: 2 }}>{String(d.note).slice(0, 120)}</div>}
              </div>
            ))}
          </Accordion>
        )}

        {/* ── 交易标注 ── */}
        {Boolean(G(ta, 'tier')) && (
          <Accordion title={`交易标注 · ${String(G(ta, 'tier') || '?')}`} accent={C.orange}>
            <div style={{ ...s.card, marginBottom: 8 }}>
              {Object.entries({ odds_quality:'赔率质量', pricing_headroom:'定价空间', transmission_confidence:'传导确定', model_consistency:'模型自洽' }).map(([key, label]) => {
                const taScores = (G(ta, 'dimension_scores') || {}) as Record<string, number>;
                return (
                  <Row key={key} label={label} value={`${taScores[key] || 0}/4`} hl={(taScores[key] || 0) >= 3} />
                );
              })}
            </div>
            {Boolean(G(ta, 'tier_note')) && <MD text={String(G(ta, 'tier_note'))} maxH={200} />}
            {Boolean(G(ta, 'suggested_action')) && <div style={{ marginTop: 8, padding: '10px 12px', background: 'rgba(173,255,0,0.04)', border: `1px solid ${C.green}20`, borderRadius: 4, fontSize: 14, color: '#BBB' }}>{String(G(ta, 'suggested_action'))}</div>}
          </Accordion>
        )}

        {/* ── 校验 ── */}
        {Boolean(G(vx, 'validation_model')) && (
          <Accordion title={`校验: ${String(vx?.validation_model)}`} accent={C.gold}>
            <Row label="主模型" value={`${N(vx?.base_target_mcap_yi || vx?.base_target_mcap_billion)}亿`} />
            <Row label="校验模型" value={vx?.validation_mcap_yi != null ? `${N(vx.validation_mcap_yi)}亿` : '数据异常'} />
            <Row label="差异" value={`${Pct(vx?.gap_pct)} (${String(vx?.gap_direction || '')})`} hl />
            {Boolean(vx?.assessment) && <div style={{ marginTop: 8 }}><MD text={String(vx.assessment)} maxH={200} /></div>}
          </Accordion>
        )}

        {/* ── KPI ── */}
        {Object.keys(kpis).length > 0 && (
          <Accordion title="未来跟踪指标" accent={C.green}>
            {(['financial_verification_kpis','event_milestone_kpis','competition_signal_kpis','risk_trigger_kpis'] as const).map(cat => {
              const items = (G(kpis, cat) || []) as Array<Record<string,unknown>>;
              if (!items.length) return null;
              return (
                <div key={cat} style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 12, color: C.mute, marginBottom: 4 }}>{cat === 'financial_verification_kpis' ? '财务验证' : cat === 'event_milestone_kpis' ? '事件里程碑' : cat === 'competition_signal_kpis' ? '竞争信号' : '风险触发'}</div>
                  {items.map((item, i) => (
                    <div key={i} style={{ fontSize: 13, color: '#999', padding: '4px 0' }}>▸ {String(item?.name || '')} {Boolean(item?.target) && <span style={{ color: C.green }}>→ {String(item.target)}</span>}</div>
                  ))}
                </div>
              );
            })}
          </Accordion>
        )}

        {/* ── 风险触发器 ── */}
        {Object.keys(triggers).length > 0 && (
          <Accordion title="风险触发器" accent={C.orange}>
            {Boolean(triggers?.bull_trigger) && <div style={{ ...s.card, marginBottom: 6, borderLeft: `2px solid ${C.green}` }}><div style={s.h3}>Bull 触发</div><div style={s.body}>{String(triggers.bull_trigger)}</div></div>}
            {Boolean(triggers?.bear_trigger) && <div style={{ ...s.card, borderLeft: `2px solid ${C.orange}` }}><div style={s.h3}>Bear 触发</div><div style={s.body}>{String(triggers.bear_trigger)}</div></div>}
          </Accordion>
        )}

        {/* ── 推理追踪 ── */}
        {trace.length > 0 && (
          <Accordion title="推理追踪" accent={C.dim}>
            {trace.map((step, i) => (
              <div key={i} style={{ fontSize: 14, color: '#999', padding: '6px 8px', borderBottom: '1px solid rgba(255,255,255,0.02)', lineHeight: 1.8 }}>
                <span style={{ color: C.dim, fontFamily: "'Space Mono',monospace", fontSize: 11, marginRight: 8 }}>[{i + 1}]</span>
                {step}
              </div>
            ))}
          </Accordion>
        )}

        {/* ── 叙事 ── */}
        {narrative && (
          <Accordion title="投资叙事" accent={C.green}>
            <div style={{ ...s.body, padding: '10px 0' }}>{narrative}</div>
          </Accordion>
        )}

        <div style={{ marginTop: 20, paddingTop: 12, borderTop: `1px solid ${C.line}`, fontSize: 11, color: '#444', textAlign: 'center' }}>
          估值重构引擎 V5 · {code} · 本报告不构成投资建议
        </div>
      </div>
    </div>
  );
}
