import { useEffect, useState } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import { MobileBackHeader } from '@/mobile/components/MobileBackHeader'
import { MobileLoading } from '@/mobile/components/MobileLoading'
import { fetchReportFromCoze, type DingshuluRecord } from '@/services/cozeApi'
import { renderMarkdown } from '@/lib/utils'

const G = (obj: unknown, ...path: string[]): unknown => {
  let cur = obj
  for (const k of path) { if (cur == null || typeof cur !== 'object') return undefined; cur = (cur as Record<string,unknown>)[k] }
  return cur
}
const N = (v: unknown, d = '—'): string => {
  if (v == null) return d
  const f = parseFloat(String(v))
  return isNaN(f) ? String(v) : (f === Math.round(f) ? String(Math.round(f)) : f.toFixed(1))
}
const Pct = (v: unknown): string => { const s = N(v); return s === '—' ? s : s + '%' }

const T = { bg:'#0a0a0f', green:'#ADFF00', orange:'#FF5C00', gold:'#C88D3A',
  ink:'#F2F4F3', body:'#BBB', md:'#CCC', dim:'#999', mute:'#888',
  glass:'rgba(255,255,255,0.025)', glassBorder:'rgba(255,255,255,0.06)',
  hairline:'rgba(255,255,255,0.04)', divider:'rgba(255,255,255,0.05)',
  greenBg:'rgba(173,255,0,0.04)', orangeBg:'rgba(255,92,0,0.03)' }

function MD({ text }: { text: string }) {
  if (!text || text === '—') return null
  return <div className="report-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }} />
}

function GlassCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-xl p-4 mb-2.5 ${className}`}
    style={{ background: T.glass, backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', border: `1px solid ${T.glassBorder}` }}>
    {children}</div>
}

function SecEyebrow({ children }: { children: string }) {
  return <div className="text-[10px] tracking-[0.16em] mb-2 uppercase" style={{ color: T.green, opacity: 0.7, fontFamily: "'IBM Plex Mono',monospace" }}>{children}</div>
}

function SecTitle({ children }: { children: string }) {
  return <h2 className="text-lg font-semibold mb-3" style={{ color: T.ink, fontFamily: "'Source Serif 4','Noto Sans SC',serif" }}>{children}</h2>
}

function KvRow({ label, value, hl }: { label: string; value: string; hl?: boolean }) {
  return (
    <div className="flex items-center justify-between py-2 text-sm" style={{ borderBottom: `1px solid ${T.hairline}` }}>
      <span className="text-xs tracking-wider" style={{ color: T.dim, fontFamily: "'IBM Plex Mono',monospace" }}>{label}</span>
      <span className="text-sm" style={{ color: hl ? T.green : T.body, fontFamily: "'IBM Plex Mono',monospace", fontWeight: hl ? 600 : 400 }}>{value}</span>
    </div>
  )
}

function Chip({ children, tone }: { children: string; tone?: 'green'|'orange' }) {
  const c = tone === 'orange' ? T.orange : T.green
  return <span className="inline-block text-[10px] px-2 py-0.5 rounded-full" style={{ border:`1px solid ${c}33`, color:c, background:`${c}08`, fontFamily:"'IBM Plex Mono',monospace", letterSpacing:'0.04em' }}>{children}</span>
}

function MetricBlock({ label, value, tone }: { label: string; value: string; tone?: 'up'|'down' }) {
  const c = tone === 'up' ? T.green : tone === 'down' ? T.orange : T.ink
  return (
    <div className="flex-1 text-center py-3 px-2 rounded-lg"
      style={{ background: T.glass, backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', border: `1px solid ${T.glassBorder}` }}>
      <div className="text-xl font-bold" style={{ color: c, fontFamily: "'Source Serif 4',serif" }}>{value}</div>
      <div className="text-[10px] mt-1 tracking-[0.1em] uppercase" style={{ color: T.dim, fontFamily: "'IBM Plex Mono',monospace" }}>{label}</div>
    </div>
  )
}

function ScenarioCardMobile({ name, prob, upside, rows, logic, accent }: {
  name: string; prob: number; upside: string; rows: [string,string][]; logic: string; accent: 'bear'|'base'|'bull'
}) {
  const isBear = accent === 'bear'; const isBull = accent === 'bull'
  const c = isBear ? T.orange : isBull ? T.green : T.body
  const bg = isBear ? T.orangeBg : T.glass
  return (
    <div className="rounded-lg p-3.5" style={{ background: bg, backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', border: `1px solid ${isBear ? 'rgba(255,92,0,0.1)' : isBull ? 'rgba(173,255,0,0.1)' : T.glassBorder}` }}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-bold tracking-[0.06em]" style={{ color: c, fontFamily: "'IBM Plex Mono',monospace" }}>{name}</span>
        <span className="text-lg font-bold opacity-35" style={{ color: c, fontFamily: "'Source Serif 4',serif" }}>{prob}<small className="text-xs">%</small></span>
      </div>
      <div className="text-2xl font-bold mb-2" style={{ color: c, fontFamily: "'IBM Plex Mono',monospace" }}>{upside}<small className="text-sm font-normal opacity-50">%</small></div>
      {rows.map(([k, v]) => <KvRow key={k} label={k} value={v} />)}
      <div className="text-xs leading-relaxed pt-2 mt-1" style={{ color: T.dim, borderTop: `1px solid ${T.hairline}` }}>{logic}</div>
    </div>
  )
}

export function DingshuluDetail() {
  const { id: _id } = useParams<{ id: string }>()
  void _id
  const location = useLocation()
  const record = (location.state as { record?: DingshuluRecord })?.record
  const [report, setReport] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)
  const [a0Open, setA0Open] = useState(false)

  useEffect(() => {
    if (!record) return
    const filename = record.report_html_url
      ? record.report_html_url.split('/').pop()?.replace(/\.html$/, '.json') || ''
      : ''
    const query = filename || record.stock_code
    if (!query) return
    setLoading(true)
    fetchReportFromCoze(query).then(setReport).finally(() => setLoading(false))
  }, [record?.report_html_url, record?.stock_code])

  if (!record) {
    return (
      <div className="flex flex-col h-full">
        <MobileBackHeader title="报告详情" />
        <div className="flex items-center justify-center flex-1 text-sm" style={{ color: T.mute }}>未找到记录</div>
      </div>
    )
  }

  const upside = parseFloat(record.prob_weighted_upside_pct || '0')
  const asym = parseFloat(record.asymmetry_ratio || '0')
  const baselineMd = typeof report?.baseline_report === 'string' && (report.baseline_report as string).trim() ? report.baseline_report as string : null
  const baselineObj = (report?.agent0 || {}) as Record<string,unknown>
  const a1 = (report?.agent1 || {}) as Record<string,unknown>
  const a2 = (report?.agent2 || {}) as Record<string,unknown>
  const a3 = (report?.agent3 || {}) as Record<string,unknown>
  const cf = (G(a1, 'packages', 'core', 'fields') || G(a1, 'clean_financials') || {}) as Record<string,unknown>
  const ms = (G(a3, 'market_sanity') || {}) as Record<string,unknown>
  const vr = (G(a3, 'valuation_routing') || {}) as Record<string,unknown>
  const rd = (G(a2, 'routing_decision') || {}) as Record<string,unknown>
  const vs = (G(a3, 'valuation_summary') || {}) as Record<string,unknown>
  const conf = (G(a3, 'confidence') || {}) as Record<string,unknown>
  const rdcf = (G(a3, 'reverse_dcf') || {}) as Record<string,unknown>
  const waccParams = (G(ms, 'wacc_params') || {}) as Record<string,unknown>
  const stockName = String(cf?.stock_name || baselineObj?.stock_name || record.stock_name || '?')
  const primaryModel = String(vr?.primary_model || rd?.primary_model || record.primary_model || '?')
  const confOverall = Number(G(conf, 'overall_score') || 5)
  const scenarios: Array<Record<string,unknown>> = Array.isArray(G(a3, 'scenarios')) ? G(a3, 'scenarios') as Array<Record<string,unknown>> : []
  const sd = (G(vs || {}, 'scenario_details') || {}) as Record<string,unknown>
  const bear = scenarios.find(s => /bear/i.test(String(s.name || ''))) || sd.bear || {} as Record<string,unknown>
  const base = scenarios.find(s => /base/i.test(String(s.name || ''))) || sd.base || {} as Record<string,unknown>
  const bull = scenarios.find(s => /bull/i.test(String(s.name || ''))) || sd.bull || {} as Record<string,unknown>
  const bp = (() => { const v = Number(G(bear, 'probability_pct') || G(bear, 'probability') || 25); return v < 1 && G(bear, 'probability') ? v * 100 : v })()
  const bsp = (() => { const v = Number(G(base, 'probability_pct') || G(base, 'probability') || 50); return v < 1 && G(base, 'probability') ? v * 100 : v })()
  const blp = (() => { const v = Number(G(bull, 'probability_pct') || G(bull, 'probability') || 25); return v < 1 && G(bull, 'probability') ? v * 100 : v })()
  const trace = (G(a3, 'reasoning_trace') || []) as string[]
  const narrative = String(G(a3, 'narrative') || '')
  const dataGaps = (G(a3, 'data_gaps') || []) as string[]
  const signalAudit = (G(a3, 'signal_audit') || {}) as Record<string,unknown>
  const isPE = ['A','C','G','I'].includes(String(primaryModel[0] || 'A'))
  const isPS = String(primaryModel[0]) === 'B'
  const isPB = String(primaryModel[0]) === 'D'
  const isEV = String(primaryModel[0]) === 'E'
  const hasReport = report && Object.keys(report).length > 0

  return (
    <div className="flex flex-col h-full" style={{ background: T.bg }}>
      <style>{`
        .report-md{font-size:14px;line-height:1.8;color:#CCC;font-family:'Noto Sans SC',system-ui,sans-serif}
        .report-md p{margin:4px 0}
        .report-md strong{color:#E8E8ED;font-weight:600}
        .report-md em{color:#ADFF00;font-style:normal}
        .report-md h1,.report-md h2{font-family:'Source Serif 4','Noto Sans SC',serif;font-size:18px;color:#E8E8ED;margin:12px 0 6px;font-weight:600}
        .report-md h3{font-size:15px;color:#DDD;margin:10px 0 4px;font-weight:600}
        .report-md table{width:100%;border-collapse:separate;border-spacing:0;margin:12px 0;border:1px solid rgba(255,255,255,0.06);border-radius:8px;overflow:hidden;empty-cells:show}
        .report-md th{background:rgba(255,255,255,0.03);padding:11px 14px;text-align:left;color:#999;font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.06em;font-weight:500;border-bottom:1px solid rgba(255,255,255,0.06)}
        .report-md td{padding:11px 14px;color:#BBB;border-bottom:1px solid rgba(255,255,255,0.04);font-size:15px;background:rgba(255,255,255,0.015)}
        .report-md tr:last-child td{border-bottom:none}
        .report-md td:empty::after{content:'—';color:#666;font-size:13px}
        .report-md td:first-child{color:#999;font-family:'IBM Plex Mono',monospace;font-size:13px}
        .report-md table strong,.report-md table b{color:#E8E8ED}
        .report-md li{margin:2px 0;color:#BBB}
        .report-md li::marker{color:rgba(173,255,0,.4)}
        .report-md code{background:rgba(173,255,0,.04);color:#ADFF00;padding:1px 5px;border-radius:3px;font-family:'IBM Plex Mono',monospace;font-size:12px}
        .report-md blockquote{border-left:1px solid rgba(173,255,0,.15);padding:8px 14px;margin:8px 0;color:#BBB;background:rgba(173,255,0,.02)}
        .report-md hr{border:none;border-top:1px solid rgba(255,255,255,0.05);margin:12px 0}
      `}</style>
      <MobileBackHeader title={stockName || '报告详情'} />
      <div className="flex-1 overflow-y-auto px-4 pb-8">
        <div className="pt-3 pb-4 mb-2" style={{ borderBottom: `1px solid ${T.divider}` }}>
          <div className="text-[10px] tracking-[0.2em] mb-2 uppercase" style={{ color: T.green, opacity: 0.7, fontFamily: "'IBM Plex Mono',monospace" }}>定数录 · 估值报告</div>
          <h1 className="text-2xl font-bold mb-1.5" style={{ color: T.ink, fontFamily: "'Source Serif 4','Noto Sans SC',serif" }}>{stockName}</h1>
          <div className="text-sm leading-relaxed mb-2" style={{ color: T.body }}>
            {String(G(baselineObj, 'raw_event_text') || G(baselineObj, 'investment_theme') || '').replace(/[#*]/g, '')}
          </div>
          <div className="flex items-center gap-2 flex-wrap text-xs" style={{ color: T.mute, fontFamily: "'IBM Plex Mono',monospace" }}>
            <span>{record.stock_code}</span><span style={{color:'#444'}}>|</span>
            <span>主模型 <b style={{color:T.green}}>{primaryModel}</b></span>
            {record.trade_tier && <Chip tone="green">{record.trade_tier}</Chip>}
          </div>
        </div>
        {hasReport && (
          <div className="flex gap-2 mb-4 mt-3">
            <MetricBlock label="概率加权涨幅" value={`${upside>=0?'+':''}${upside.toFixed(1)}%`} tone={upside>=0?'up':'down'} />
            <MetricBlock label="不对称比" value={`${asym.toFixed(1)}×`} />
            <MetricBlock label="置信度" value={`${confOverall}/10`} />
          </div>
        )}
        {loading && <MobileLoading />}
        {hasReport && !loading && (<>
          <div className="mb-4">
            <SecEyebrow>SCENARIO ANALYSIS</SecEyebrow>
            <SecTitle>三情景概率分布</SecTitle>
            <div className="flex h-1 rounded-full overflow-hidden mb-3">
              <div style={{width:`${bp}%`,background:`${T.orange}66`}} />
              <div style={{width:`${bsp}%`,background:'rgba(255,255,255,0.08)'}} />
              <div style={{width:`${blp}%`,background:`${T.green}4d`}} />
            </div>
            {scenarios.length > 0 ? (
              <div className="flex flex-col gap-2">
                {scenarios.map((s, i) => {
                  const u = parseFloat(String(s?.upside_pct ?? 0))
                  const name = String(s?.name || '?').toUpperCase()
                  const prob = Number(s?.probability_pct || N(s?.probability))
                  const accent: 'bear'|'base'|'bull' = name.includes('BEAR') ? 'bear' : name.includes('BULL') ? 'bull' : 'base'
                  const rows: [string,string][] = []
                  if (isPE) { rows.push(['ROIC',Pct(s?.roic_assumed_pct||s?.roic_pct)],['PE',N(s?.pe_target)]) }
                  if (isPS) { rows.push(['3y CAGR',Pct(s?.revenue_growth_3y_cagr_pct||s?.revenue_growth_pct)],['PS',N(s?.target_ps)]) }
                  if (isPB) { rows.push(['ROE',Pct(s?.target_roe_pct)],['PB',N(s?.target_pb)]) }
                  if (isEV) { rows.push(['EBITDA G',Pct(s?.ebitda_growth_pct)],['EV/EBITDA',N(s?.target_ev_ebitda)]) }
                  rows.push(['目标市值',`${N(s?.target_mcap_yi||s?.target_mcap_billion)} 亿`])
                  return <ScenarioCardMobile key={i} name={name} prob={prob} upside={`${u>=0?'+':''}${u.toFixed(1)}`} rows={rows} logic={String(s?.scenario_narrative||'')} accent={accent} />
                })}
              </div>
            ) : <GlassCard><div className="text-sm" style={{color:T.mute}}>情景数据未生成</div></GlassCard>}
            {G(a3, 'probability_rationale') != null && <div className="mt-2"><MD text={String(G(a3, 'probability_rationale'))} /></div>}
          </div>
          <div className="mb-4">
            <SecEyebrow>VALUATION ROUTING</SecEyebrow>
            <SecTitle>估值路由与模型决策</SecTitle>
            <GlassCard>
              <KvRow label="主模型" value={primaryModel} hl />
              <KvRow label="校验模型" value={String(vr?.secondary_model||rd?.secondary_model||'?')} />
              <KvRow label="模型分类" value={String(vr?.model_category||rd?.model_category||'?')} />
              {G(vr,'routing_reason')!=null&&<div className="mt-2"><MD text={String(G(vr,'routing_reason')||'')}/></div>}
            </GlassCard>
          </div>
          {baselineMd && (
            <div className="mb-4">
              <SecEyebrow>BASELINE</SecEyebrow>
              <SecTitle>基线分析</SecTitle>
              <GlassCard><MD text={baselineMd} /></GlassCard>
            </div>
          )}
          {G(baselineObj, 'knowledge_supplement') && (
            <div className="mb-4">
              <SecEyebrow>KNOWLEDGE</SecEyebrow>
              <SecTitle>背景知识补充</SecTitle>
              <GlassCard><MD text={String(G(baselineObj, 'knowledge_supplement')).slice(0,3000)}/></GlassCard>
            </div>
          )}
          {(Object.keys(ms).length>0||Object.keys(rdcf).length>0) && (
            <div className="mb-4">
              <SecEyebrow>BS DETECTOR</SecEyebrow>
              <SecTitle>市场定价了什么？</SecTitle>
              <GlassCard>
                {ms?.bs_level!=null&&<div className="text-base font-bold mb-2" style={{color:T.orange}}>{String(ms.bs_level)}</div>}
                {ms?.bs_secondary!=null&&<div className="text-sm mb-2" style={{color:T.dim}}>{String(ms.bs_secondary)}</div>}
                <KvRow label="EV" value={`${N(ms?.ev_yi||ms?.ev_billion)} 亿`}/>
                <KvRow label="ROIC" value={Pct(ms?.roic_pct)} hl/>
                <KvRow label="WACC" value={Pct(ms?.wacc_simple_pct)}/>
                <KvRow label="隐含 g" value={Pct(ms?.implied_g_pct||G(rdcf,'market_implied_g_pct'))} hl/>
                <KvRow label="PE(TTM)" value={`${N(ms?.pe_ttm)}×`}/>
                <KvRow label="PB" value={`${N(ms?.pb)}×`}/>
                {Object.keys(waccParams).length>0&&(<>
                  <div className="text-[10px] tracking-[0.14em] mt-3 mb-2" style={{color:T.green,opacity:.5,fontFamily:"'IBM Plex Mono',monospace"}}>◇ WACC</div>
                  <KvRow label="Rf" value={Pct(waccParams?.rf_pct)}/>
                  <KvRow label="Beta" value={N(waccParams?.beta)}/>
                  <KvRow label="ERP" value={Pct(waccParams?.erp_pct)}/>
                  <KvRow label="WACC" value={Pct(waccParams?.wacc_pct)}/>
                </>)}
                {ms?.market_story!=null&&<div className="mt-2"><MD text={String(ms.market_story)}/></div>}
              </GlassCard>
            </div>
          )}
          {Object.keys(cf).length>3 && (
            <div className="mb-4">
              <SecEyebrow>FINANCIALS</SecEyebrow>
              <SecTitle>财务全景</SecTitle>
              <GlassCard>
                <div className="grid grid-cols-2 gap-x-3">
                  <KvRow label="营收 TTM" value={`${N(cf?.revenue_ttm_yi||cf?.revenue_ttm_billion)} 亿`}/>
                  <KvRow label="净利 TTM" value={`${N(cf?.net_profit_ttm_yi||cf?.net_profit_billion)} 亿`}/>
                  <KvRow label="ROIC" value={Pct(cf?.roic_pct)} hl/>
                  <KvRow label="毛利率" value={Pct(cf?.gross_margin_pct)}/>
                  <KvRow label="ROE" value={Pct(cf?.roe_ttm_pct)}/>
                  <KvRow label="经营 CF" value={`${N(cf?.ocf_ttm_yi||cf?.operating_cf_ttm_billion)} 亿`}/>
                </div>
              </GlassCard>
            </div>
          )}
          {G(signalAudit,'step2b_match')&&(
            <div className="mb-4">
              <SecEyebrow>SIGNAL AUDIT</SecEyebrow>
              <SecTitle>信号审计</SecTitle>
              <GlassCard>
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-xl font-bold" style={{color:T.green,fontFamily:"'Source Serif 4',serif"}}>{N(G(signalAudit,'step2d_score'))}</span>
                  <span className="text-sm" style={{color:T.dim}}>{String(G(signalAudit,'score_rationale')||'').slice(0,150)}</span>
                </div>
                {(G(signalAudit,'step2b_match') as Array<Record<string,unknown>>).map((m,i)=>(
                  <div key={i} className="text-sm py-2" style={{color:T.body,borderBottom:`1px solid ${T.hairline}`}}>
                    <b style={{color: m?.match==='支持'?T.green:T.orange}}>{String(m?.match)}</b>{' '}
                    {String(m?.signal)} <span className="text-xs" style={{color:T.mute}}>({String(m?.source_level)})</span> — {String(m?.basis)}
                  </div>
                ))}
              </GlassCard>
            </div>
          )}
          {trace.length>0&&(
            <div className="mb-4">
              <SecEyebrow>REASONING TRACE</SecEyebrow>
              <SecTitle>推理追踪</SecTitle>
              <GlassCard>
                {trace.map((t,i)=>(
                  <div key={i} className="text-sm py-2 px-3 mb-1 rounded" style={{color:T.dim,background:'rgba(0,0,0,.15)',lineHeight:1.7}}>
                    <span className="text-xs" style={{color:T.mute,fontFamily:"'IBM Plex Mono',monospace"}}>[{i+1}]</span> {t}
                  </div>
                ))}
              </GlassCard>
            </div>
          )}
          <div className="mb-4">
            <SecEyebrow>NARRATIVE</SecEyebrow>
            <SecTitle>叙事</SecTitle>
            <GlassCard><MD text={narrative||'暂无叙事数据'}/></GlassCard>
          </div>
          {Object.keys(baselineObj).length>0&&(
            <div className="mb-4" style={{opacity:a0Open?1:.55}}>
              <SecEyebrow>AGENT-0 PRE-ROUTING</SecEyebrow>
              <SecTitle>预路由 · 事件分析</SecTitle>
              <GlassCard>
                <button onClick={()=>setA0Open(!a0Open)} className="w-full flex items-center justify-between bg-transparent border-none text-sm"
                  style={{color:T.dim,fontFamily:"'IBM Plex Mono',monospace"}}>
                  <span>{a0Open?'▲ 收起预路由分析':'▶ 展开预路由分析'}</span>
                  <Chip tone="green">{`L${String(baselineObj?.response_level||'?')}`}</Chip>
                </button>
                {a0Open&&(
                  <div className="mt-3 pt-3 flex flex-col gap-2" style={{borderTop:`1px solid ${T.hairline}`}}>
                    {Boolean(G(baselineObj,'investment_theme'))&&<MD text={String(G(baselineObj,'investment_theme')).slice(0,3000)}/>}
                    {Boolean(G(baselineObj,'event_deduction'))&&<MD text={String(G(baselineObj,'event_deduction'))}/>}
                    {Boolean(G(baselineObj,'preliminary_reasoning'))&&<MD text={String(G(baselineObj,'preliminary_reasoning'))}/>}
                    {Boolean(G(baselineObj,'adversarial_thinking'))&&<MD text={String(G(baselineObj,'adversarial_thinking')).slice(0,1500)}/>}
                    {Boolean(G(baselineObj,'industry_expert_research'))&&<MD text={String(G(baselineObj,'industry_expert_research')).slice(0,2000)}/>}
                    {Boolean(G(baselineObj,'future'))&&<MD text={String(G(baselineObj,'future')).slice(0,1000)}/>}
                  </div>
                )}
              </GlassCard>
            </div>
          )}
          {dataGaps.length>0&&(
            <div className="mb-4">
              <SecEyebrow>DATA GAPS</SecEyebrow>
              <SecTitle>数据缺口</SecTitle>
              <GlassCard>
                {dataGaps.map((g,i)=><div key={i} className="text-sm py-1" style={{color:T.gold}}>▸ {g}</div>)}
              </GlassCard>
            </div>
          )}
          <div className="text-center pt-6 mt-4 text-[10px] tracking-[0.04em]" style={{color:'#666',fontFamily:"'IBM Plex Mono',monospace",borderTop:`1px solid ${T.divider}`}}>
            估值重构引擎 V5 · {record.stock_code} · 不构成投资建议
          </div>
        </>)}
      </div>
    </div>
  )
}
