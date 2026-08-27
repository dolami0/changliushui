import { useEffect, useState, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { fetchReportFromCoze } from '@/services/cozeApi'
import { useMobile } from '../hooks/useMobile'
import { renderMarkdown } from '../lib/utils'
import ValuationReportMobile from './ValuationReportMobile'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import {
  T, F, DotGridBg, SectionEyebrow, SectionTitle,
  GlassCard, KvRow, Chip,
} from '@/lib/report-theme'

gsap.registerPlugin(ScrollTrigger)

/* ================================================================== */
/*  Shared styles                                                       */
/* ================================================================== */

const GLOBAL_CSS = `
  .vr-md{font-family:'Noto Sans SC',system-ui,sans-serif;font-size:15px;line-height:2;color:${T.bodyMd}}
  .vr-md h1{font-family:'Source Serif 4','Noto Sans SC',serif;font-size:22px;color:${T.ink};margin:20px 0 8px;font-weight:700}
  .vr-md h2{font-family:'Source Serif 4','Noto Sans SC',serif;font-size:19px;color:${T.ink};margin:16px 0 6px;font-weight:600}
  .vr-md h3{font-size:16px;color:${T.ink};margin:12px 0 6px;font-weight:600}
  .vr-md p{margin:6px 0;line-height:2;color:${T.bodyMd}}
  .vr-md strong{color:${T.ink};font-weight:600}
  .vr-md em{color:${T.green};font-style:normal}
  .vr-md code{background:${T.greenBg};color:${T.green};padding:1px 6px;border-radius:3px;font-family:'IBM Plex Mono',monospace;font-size:13px}
  .vr-md li{margin:4px 0;padding:4px 0;color:${T.bodyMd};line-height:1.9}
  .vr-md li::marker{color:${T.greenDim}}
  .vr-md blockquote{border-left:2px solid ${T.greenBorder};padding:10px 20px;margin:10px 0;color:${T.bodyMd};background:${T.greenBg}}
  .vr-md hr{border:none;border-top:1px solid ${T.divider};margin:16px 0}
  .vr-md table{width:100%;border-collapse:separate;border-spacing:0;margin:16px 0;font-size:16px;border:1px solid ${T.glassBorder};border-radius:8px;overflow:hidden;empty-cells:show}
  .vr-md th{background:rgba(255,255,255,0.03);padding:14px 18px;text-align:left;color:${T.dim};font-family:'IBM Plex Mono',monospace;font-size:13px;letter-spacing:.06em;font-weight:500;border-bottom:1px solid ${T.glassBorder}}
  .vr-md td{padding:14px 18px;color:${T.body};border-bottom:1px solid ${T.hairline};font-size:16px;background:rgba(255,255,255,0.015)}
  .vr-md tr:last-child td{border-bottom:none}
  .vr-md th:last-child,.vr-md td:last-child{border-right:none}
  .vr-md td:empty::after{content:'—';color:${T.steel};font-size:14px}
  .vr-md td:first-child{color:${T.dim};font-family:'IBM Plex Mono',monospace;font-size:14px}
  .vr-md table strong,.vr-md table b{color:${T.ink}}
`

/* ================================================================== */
/*  Helpers                                                             */
/* ================================================================== */

function N(v: unknown, d = '—'): string {
  if (v === null || v === undefined) return d
  const s = String(v); const f = parseFloat(s)
  if (isNaN(f)) return s === 'True' ? '是' : s === 'False' ? '否' : s
  return f === Math.round(f) ? String(Math.round(f)) : f.toFixed(1)
}
function Pct(v: unknown): string { const s = N(v); return s === '—' ? s : s + '%' }
const G = (obj: unknown, ...path: string[]): unknown => {
  let cur = obj
  for (const k of path) { if (cur == null || typeof cur !== 'object') return undefined; cur = (cur as Record<string,unknown>)[k] }
  return cur
}

/* ================================================================== */
/*  Components                                                          */
/* ================================================================== */

function MD({ text }: { text: string }) {
  if (!text || text === '—') return null
  return <div className="vr-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }} />
}

function BigNum({ val, label, tone }: { val: string; label: string; tone?: 'up' | 'down' }) {
  const c = tone === 'up' ? T.green : tone === 'down' ? T.orange : T.ink
  return (
    <div style={{
      flex: 1, textAlign: 'center',
      padding: '28px 24px',
      background: T.glassBg,
      backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
      border: `1px solid ${T.glassBorder}`,
      borderRadius: 10,
    }}>
      <div className="bignum-val" style={{ fontFamily: F.display, fontSize: 46, fontWeight: 700, color: c, lineHeight: 1 }}>{val}</div>
      <div style={{ fontFamily: F.mono, fontSize: 11, color: T.dim, marginTop: 8, letterSpacing: '0.1em' }}>{label}</div>
    </div>
  )
}

function ProbBar({ bear, base, bull }: { bear: number; base: number; bull: number }) {
  return (
    <div className="prob-bar-fill" style={{ height: 4, borderRadius: 2, overflow: 'hidden', marginBottom: 28, display: 'flex' }}>
      <div className="pb-seg" style={{ width: `${bear}%`, background: `${T.orange}66` }} />
      <div className="pb-seg" style={{ width: `${base}%`, background: 'rgba(255,255,255,0.08)' }} />
      <div className="pb-seg" style={{ width: `${bull}%`, background: `${T.green}4d` }} />
    </div>
  )
}

function ScenarioCard({ name, prob, upside, rows, logic, accent }: {
  name: string; prob: number; upside: string; rows: [string,string][]; logic: string; accent: 'bear' | 'base' | 'bull'
}) {
  const isBear = accent === 'bear', isBull = accent === 'bull'
  const c = isBear ? T.orange : isBull ? T.green : T.body
  const bg = isBear ? T.orangeBg : isBull ? T.greenBg : T.glassBg
  const border = isBear ? T.orangeBorder : isBull ? T.greenBorder : T.glassBorder
  return (
    <div className="scenario-card" style={{
      padding: '24px 20px', background: bg, border: `1px solid ${border}`,
      borderRadius: 10, backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
      display: 'flex', flexDirection: 'column', gap: 10, position: 'relative',
    }}>
      {!isBear && !isBull && (
        <div style={{ position: 'absolute', top: -9, left: '50%', transform: 'translateX(-50%)', background: T.bg, padding: '1px 12px', border: `1px solid ${T.glassBorder}`, borderRadius: 10, fontSize: 10, color: T.dim, fontFamily: F.mono, letterSpacing: '0.1em' }}>基准情景</div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: F.mono, fontSize: 13, fontWeight: 700, color: c, letterSpacing: '0.06em' }}>{name}</span>
        <span style={{ fontFamily: F.display, fontSize: 24, fontWeight: 700, color: c, opacity: 0.35 }}>{prob}<small style={{ fontSize: 13 }}>%</small></span>
      </div>
      <div style={{ fontFamily: F.mono, fontSize: 28, fontWeight: 700, color: c }}>{upside}<small style={{ fontSize: 14, opacity: 0.5, fontWeight: 400 }}>%</small></div>
      {rows.map(([k, v]) => (
        <KvRow key={k} label={k} value={v} />
      ))}
      <div style={{ fontSize: 12, color: T.dim, lineHeight: 1.7, paddingTop: 8, borderTop: `1px solid ${T.hairline}` }}>{logic}</div>
    </div>
  )
}

function DimBar({ label, score, max, note }: { label: string; score: number; max: number; note?: string }) {
  const pct = Math.min(100, Math.max(0, (score / max) * 100))
  const c = score >= 7 ? T.green : score >= 4 ? T.gold : T.orange
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontSize: 13, marginBottom: 5, color: T.body }}>
        <span>{label}</span>
        <span style={{ fontFamily: F.mono, fontWeight: 600, fontSize: 14, color: c }}>{score}<small style={{ fontSize: 11, fontWeight: 400, opacity: 0.4 }}>/{max}</small></span>
      </div>
      <div style={{ height: 3, background: 'rgba(255,255,255,0.04)', borderRadius: 2, overflow: 'hidden' }}>
        <div className="prog-fill" style={{ height: '100%', width: `${pct}%`, background: c, borderRadius: 2, opacity: 0.6 }} />
      </div>
      {note && <div style={{ fontSize: 11, color: T.mute, marginTop: 3 }}>{note.slice(0, 140)}</div>}
    </div>
  )
}

function KpiList({ items, color }: { items: Array<Record<string,unknown>>; color: string }) {
  if (!items.length) return null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {items.map((k, i) => {
        const name = String(k.name || k.kpi || k.milestone || k.signal || k.trigger || '?')
        const target = String(k.target || k.threshold || k.expected_timing || '—')
        const baseline = String(k.baseline || k.current_state || '')
        const freq = String(k.frequency || k.monitor || '')
        return (
          <div key={i} style={{ fontSize: 13, color: T.body, lineHeight: 1.7, padding: '10px 16px', background: 'rgba(0,0,0,.15)', borderRadius: 6 }}>
            <b style={{ color }}>{name}</b>: {target}
            {baseline && baseline !== '—' ? <span style={{ color: T.mute }}>（基线: {baseline}）</span> : ''}
            {freq && freq !== '—' ? <span style={{ color: T.steel, marginLeft: 10 }}>▸ {freq}</span> : ''}
          </div>
        )
      })}
    </div>
  )
}

/* ================================================================== */
/*  Main Report                                                         */
/* ================================================================== */

export default function ValuationReport() {
  const { code } = useParams<{ code: string }>()
  const mobile = useMobile()
  const [data, setData] = useState<Record<string,unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [a0Open, setA0Open] = useState(false)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [activeSec, setActiveSec] = useState('exec')
  const mainRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!code) { setError('无效股票代码'); setLoading(false); return }
    fetchReportFromCoze(code).then(data => {
      if (data) setData(data)
      else setError('报告未找到')
    }).catch((e: Error) => setError(`加载失败: ${e.message}`))
      .finally(() => setLoading(false))
  }, [code])

  useEffect(() => {
    const ids = ['exec','scenario','model','narrative','baseline','knowledge','bs','financial','signal','gap','confidence','trade','crosscheck','kpi','triggers','trace','a0']
    const h = () => {
      for (const id of ids) {
        const el = document.getElementById(id)
        if (el) { const r = el.getBoundingClientRect(); if (r.top < 200 && r.bottom > 200) { setActiveSec(id); break } }
      }
    }
    window.addEventListener('scroll', h, { passive: true })
    return () => window.removeEventListener('scroll', h)
  }, [])

  // ── GSAP animations ──
  useEffect(() => {
    if (!data || !mainRef.current) return
    const ctx = gsap.context(() => {
      // 1. Hero entrance
      const heroEls = mainRef.current!.querySelectorAll('.hero-anim')
      if (heroEls.length) {
        gsap.from(heroEls, { autoAlpha: 0, y: 28, duration: 0.7, ease: 'power3.out', stagger: 0.1, delay: 0.2 })
      }

      // 2. Big numbers: count-up + pop
      const bignums = mainRef.current!.querySelectorAll('.report-bignum .bignum-val')
      bignums.forEach((el, i) => {
        const text = el.textContent || ''
        const numMatch = text.match(/[+-]?[\d.]+/)
        const wrapper = el.closest('.report-bignum')
        if (numMatch && wrapper) {
          const target = parseFloat(numMatch[0])
          const prefix = text.slice(0, numMatch.index)
          const suffix = text.slice((numMatch.index || 0) + numMatch[0].length)
          const decimals = target % 1 === 0 ? 0 : 1
          gsap.from(wrapper, { scale: 0.6, autoAlpha: 0, duration: 0.6, ease: 'back.out(1.6)', delay: 0.6 + i * 0.15 })
          gsap.fromTo(el, { textContent: '0' }, {
            textContent: target, duration: 1.2, ease: 'power2.out', delay: 0.6 + i * 0.15,
            snap: { textContent: 0.1 },
            onUpdate() {
              const v = parseFloat(el.textContent || '0')
              el.textContent = prefix + (isNaN(v) ? '0' : v.toFixed(decimals)) + suffix
            }
          })
        } else if (wrapper) {
          gsap.from(wrapper, { scale: 0.6, autoAlpha: 0, duration: 0.6, ease: 'back.out(1.6)', delay: 0.6 + i * 0.15 })
        }
      })

      // 3. Section reveals on scroll
      const sections = document.querySelectorAll('.report-section')
      sections.forEach((sec) => {
        if (sec.classList.contains('report-hero')) return
        ScrollTrigger.create({
          trigger: sec,
          start: 'top 82%',
          onEnter: () => gsap.fromTo(sec, { autoAlpha: 0, y: 20 }, { autoAlpha: 1, y: 0, duration: 0.55, ease: 'power2.out' }),
        })
      })

      // 4. Scenario cards
      document.querySelectorAll('.scenario-card').forEach((card) => {
        ScrollTrigger.create({
          trigger: card,
          start: 'top 82%',
          onEnter: () => gsap.fromTo(card, { autoAlpha: 0, y: 30, rotationX: 4 }, { autoAlpha: 1, y: 0, rotationX: 0, duration: 0.5, ease: 'back.out(1.2)' }),
        })
      })

      // 5. Prob bar
      const probBar = document.querySelector('.prob-bar-fill')
      if (probBar) {
        ScrollTrigger.create({
          trigger: probBar,
          start: 'top 82%',
          onEnter: () => gsap.fromTo(probBar.querySelectorAll('.pb-seg'), { scaleX: 0 }, { scaleX: 1, duration: 0.7, ease: 'power3.inOut', stagger: 0.1, transformOrigin: 'left center' }),
        })
      }

      // 6. Progress bars
      document.querySelectorAll('.prog-fill').forEach((bar) => {
        const el = bar as HTMLElement
        const tw = el.style.width
        ScrollTrigger.create({
          trigger: el,
          start: 'top 85%',
          onEnter: () => gsap.fromTo(el, { width: '0%' }, { width: tw, duration: 0.7, ease: 'power2.out' }),
        })
      })

      // 7. Narrative — gold quote pop + line draw
      const narrSec = document.querySelector('.narrative-section')
      if (narrSec) {
        const quote = narrSec.querySelector('.narrative-quote') as HTMLElement
        const line = narrSec.querySelector('.narrative-line') as HTMLElement
        ScrollTrigger.create({
          trigger: narrSec,
          start: 'top 75%',
          onEnter: () => {
            if (quote) gsap.fromTo(quote, { autoAlpha: 0, scale: 0.3, rotation: -15 }, { autoAlpha: 1, scale: 1, rotation: 0, duration: 1, ease: 'elastic.out(1, 0.5)' })
            if (line) gsap.to(line, { width: '100%', duration: 1.5, ease: 'power3.inOut' })
          },
        })
      }
    }, mainRef.current)
    return () => ctx.revert()
  }, [data])

  if (mobile) return <ValuationReportMobile />
  if (!data && !loading && !error) return null

  /* ── Data extraction (unchanged from original) ── */
  const baselineMd = typeof data?.baseline_report === 'string' && (data.baseline_report as string).trim() ? data.baseline_report as string : null
  const baselineObj = (data?.agent0 || {}) as Record<string,unknown>
  const a1 = (data?.agent1 || {}) as Record<string,unknown>
  const a2 = (data?.agent2 || {}) as Record<string,unknown>
  const a3 = (data?.agent3 || {}) as Record<string,unknown>

  const core = (G(a1, 'packages', 'core', 'fields') || {}) as Record<string,unknown>
  const cf = Object.keys(core).length > 3 ? core : (G(a1, 'clean_financials') || {}) as Record<string,unknown>
  const va = (G(a1, 'valuation_anchor') || {}) as Record<string,unknown>
  const ms = (G(a3, 'market_sanity') || G(a1, 'market_sanity') || {}) as Record<string,unknown>
  const vr = (G(a3, 'valuation_routing') || G(a1, 'valuation_routing') || {}) as Record<string,unknown>
  const rd = (G(a2, 'routing_decision') || {}) as Record<string,unknown>
  const sv = (G(a3, 'scenario_valuation') || {}) as Record<string,unknown>
  const vs = (G(a3, 'valuation_summary') || sv || {}) as Record<string,unknown>
  const gap = (G(a3, 'expectation_gap') || {}) as Record<string,unknown>
  const rdcf = (G(a3, 'reverse_dcf') || {}) as Record<string,unknown>
  const conf = (G(a3, 'confidence') || {}) as Record<string,unknown>
  const ta = (G(a3, 'trade_annotation') || {}) as Record<string,unknown>
  const vx = (G(a3, 'validation_crosscheck') || {}) as Record<string,unknown>
  const kpis = (G(a3, 'monitoring_kpis') || {}) as Record<string,unknown>
  const triggers = (G(a3, 'risk_triggers') || {}) as Record<string,unknown>
  const dataGaps = (G(a3, 'data_gaps') || []) as string[]
  const signalAudit = (G(a3, 'signal_audit') || {}) as Record<string,unknown>
  const preflight = (G(a3, 'preflight_check') || []) as string[]
  const trace = (G(a3, 'reasoning_trace') || []) as string[]
  const narrative = String(G(a3, 'narrative') || '')
  const probRationale = String(G(a3, 'probability_rationale') || '')
  const waccParams = (G(ms, 'wacc_params') || G(va, 'wacc_params') || {}) as Record<string,unknown>
  const confDims = (G(conf, 'dimensions') || {}) as Record<string, Record<string,unknown>>
  const taSignals = (G(ta, 'alignment_signals') || []) as string[]
  const taScores = (G(ta, 'dimension_scores') || {}) as Record<string, number>

  const primaryModel = String(vr?.primary_model || rd?.primary_model || '?')
  const stockName = String(cf?.stock_name || baselineObj?.stock_name || code || '?')
  const mcap = parseFloat(String(cf?.market_cap_yi || cf?.market_cap_billion || 0))
  const modelKey = String(primaryModel[0] || 'A')

  const scenarios: Array<Record<string,unknown>> = Array.isArray(G(a3, 'scenarios')) ? G(a3, 'scenarios') as Array<Record<string,unknown>> : []
  const sd = (G(sv, 'scenario_details') || {}) as Record<string,unknown>
  const bear = scenarios.find(s => /bear/i.test(String(s.name || ''))) || sd.bear || {} as Record<string,unknown>
  const base = scenarios.find(s => /base/i.test(String(s.name || ''))) || sd.base || {} as Record<string,unknown>
  const bull = scenarios.find(s => /bull/i.test(String(s.name || ''))) || sd.bull || {} as Record<string,unknown>

  const upside = parseFloat(String(vs?.probability_weighted_upside_pct ?? 0))
  const asym = parseFloat(String(vs?.asymmetry_ratio ?? 0))
  const bp = (() => { const v = Number(G(bear, 'probability_pct') || G(bear, 'probability') || 25); return v < 1 && G(bear, 'probability') ? v * 100 : v })()
  const bsp = (() => { const v = Number(G(base, 'probability_pct') || G(base, 'probability') || 50); return v < 1 && G(base, 'probability') ? v * 100 : v })()
  const blp = (() => { const v = Number(G(bull, 'probability_pct') || G(bull, 'probability') || 25); return v < 1 && G(bull, 'probability') ? v * 100 : v })()
  const confOverall = Number(G(conf, 'overall_score') || 5)

  const isPS = modelKey === 'B', isPE = ['A','C','G','I'].includes(modelKey), isPB = modelKey === 'D', isEV = modelKey === 'E'

  const toc: Record<string,string> = { exec:'摘要', scenario:'情景', model:'路由', narrative:'叙事', baseline:'基线', knowledge:'背景', bs:'BS', financial:'财务', signal:'信号', gap:'预期差', confidence:'置信', trade:'标注', crosscheck:'校验', kpi:'KPI', triggers:'触发', trace:'推理', a0:'预路由' }

  return (
    <>
    <style>{GLOBAL_CSS}</style>
    <div ref={mainRef} style={{ minHeight: '100vh', background: T.bg, color: T.body, paddingBottom: 80, position: 'relative' }}>
      <DotGridBg />

      <div style={{ maxWidth: 960, margin: '0 auto', padding: '48px 40px 40px', position: 'relative', zIndex: 1 }}>
        {loading && <div style={{ padding: 100, textAlign: 'center', fontFamily: F.mono, fontSize: 16, color: T.mute }}>加载估值报告中...</div>}
        {error && !loading && <div style={{ padding: 100, textAlign: 'center', fontFamily: F.mono, fontSize: 16, color: T.orange }}>{error}</div>}

        {data && !loading && (<>

          {/* ═══════ HERO ═══════ */}
          <div className="report-section report-hero" style={{ marginBottom: 28 }}>
            <div className="hero-anim" style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.2em', marginBottom: 12, opacity: 0.85 }}>定数录 · 估值报告</div>
            <h1 className="hero-anim" style={{ fontFamily: F.display, fontSize: 48, fontWeight: 700, color: T.ink, margin: '0 0 8px', letterSpacing: '-0.02em', lineHeight: 1.1 }}>
              {stockName}
            </h1>
            {(() => {
              const summary = String(G(baselineObj, 'raw_event_text') || G(baselineObj, 'investment_theme') || '').replace(/[#*]/g, '')
              const long = summary.length > 250
              return (
                <div className="hero-anim">
                  <div style={{
                    fontSize: 15, color: T.body, lineHeight: 1.85, fontWeight: 300, marginBottom: long ? 4 : 8,
                    overflow: 'hidden',
                    maxHeight: summaryOpen || !long ? 'none' : '3.7em',
                    transition: 'max-height 0.35s ease',
                  }}>
                    {summary}
                  </div>
                  {long && (
                    <button onClick={() => setSummaryOpen(!summaryOpen)} style={{
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      fontFamily: F.mono, fontSize: 11, color: T.green, opacity: 0.7,
                      padding: 0, marginBottom: 8,
                    }}>
                      {summaryOpen ? '▲ 收起' : '▼ 展开全文'}
                    </button>
                  )}
                </div>
              )
            })()}
            <div className="hero-anim" style={{ display: 'flex', gap: 14, fontFamily: F.mono, fontSize: 11, color: T.mute, alignItems: 'center', flexWrap: 'wrap' }}>
              <span>{code} · {String(G(a3, 'report_meta', 'industry') || G(a1, 'industry') || '?')}</span>
              <span style={{ color: '#333' }}>|</span>
              <span>主模型 <b style={{ color: T.green }}>{primaryModel}</b></span>
              <span>校验 <span style={{ color: T.body }}>{String(vr?.secondary_model || rd?.secondary_model || '?')}</span></span>
              <Chip tone="green">{`L${String(baselineObj?.response_level || '?')}`}</Chip>
              <span>市值 <b style={{ color: T.body }}>{N(mcap)} 亿</b></span>
            </div>

            {/* 三大数字 — 横排 */}
            <div className="report-section" id="exec" style={{ display: 'flex', gap: 10, marginTop: 18, marginBottom: 20 }}>
              <div className="report-bignum" style={{ flex: 1 }}><BigNum val={`${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%`} label="概率加权涨幅" tone="up" /></div>
              <div className="report-bignum" style={{ flex: 1 }}><BigNum val={`${asym.toFixed(1)}×`} label="不对称比" /></div>
              <div className="report-bignum" style={{ flex: 1 }}><BigNum val={`${confOverall}/10`} label="置信度" /></div>
            </div>

            {/* TOC */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, padding: '12px 0', borderTop: `1px solid ${T.divider}` }}>
              {Object.entries(toc).map(([id, label]) => (
                <a key={id} href={`#${id}`} style={{
                  fontFamily: F.mono, fontSize: 11, padding: '3px 9px', borderRadius: 6,
                  color: activeSec === id ? T.green : T.mute,
                  background: activeSec === id ? T.greenBg : 'transparent',
                  border: activeSec === id ? `1px solid ${T.greenBorder}` : '1px solid transparent',
                  textDecoration: 'none', transition: 'all .2s', fontWeight: activeSec === id ? 600 : 400,
                }}>{label}</a>
              ))}
            </div>
          </div>

          {/* ═══════ 三情景 ═══════ */}
          <div className="report-section" id="scenario" style={{ marginBottom: 40 }}>
            <SectionEyebrow>SCENARIO ANALYSIS</SectionEyebrow>
            <SectionTitle>三情景概率分布</SectionTitle>
            <ProbBar bear={bp} base={bsp} bull={blp} />
            {scenarios.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                {scenarios.map((s, i) => {
                  const u = parseFloat(String(s?.upside_pct ?? 0))
                  const name = String(s?.name || '?').toUpperCase()
                  const prob = Number(s?.probability_pct || N(s?.probability))
                  const accent: 'bear'|'base'|'bull' = name.includes('BEAR') ? 'bear' : name.includes('BULL') ? 'bull' : 'base'
                  const rows: [string,string][] = []
                  if (isPE) { rows.push(['ROIC', Pct(s?.roic_assumed_pct || s?.roic_pct)], ['PE', N(s?.pe_target)]) }
                  if (isPS) { rows.push(['3y CAGR', Pct(s?.revenue_growth_3y_cagr_pct || s?.revenue_growth_pct)], ['Target PS', N(s?.target_ps)]) }
                  if (isPB) { rows.push(['ROE', Pct(s?.target_roe_pct)], ['PB', N(s?.target_pb)]) }
                  if (isEV) { rows.push(['EBITDA G', Pct(s?.ebitda_growth_pct)], ['EV/EBITDA', N(s?.target_ev_ebitda)]) }
                  rows.push(['目标市值', `${N(s?.target_mcap_yi || s?.target_mcap_billion)} 亿`])
                  return (
                    <ScenarioCard key={i} name={name} prob={prob} upside={`${u >= 0 ? '+' : ''}${u.toFixed(1)}`} rows={rows} logic={String(s?.scenario_narrative || '')} accent={accent} />
                  )
                })}
              </div>
            ) : (
              <GlassCard><div style={{ fontSize: 14, color: T.mute }}>情景数据未生成</div></GlassCard>
            )}
            {probRationale && (
              <div className="report-section" style={{ marginTop: 16 }}>
                <MD text={probRationale} />
              </div>
            )}
          </div>

          {/* ═══════ 估值路由 ═══════ */}
          <div className="report-section" id="model" style={{ marginBottom: 40 }}>
            <SectionEyebrow>VALUATION ROUTING</SectionEyebrow>
            <SectionTitle>估值路由与模型决策</SectionTitle>
            <div style={{ display: 'flex', background: T.glassBg, backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', border: `1px solid ${T.glassBorder}`, borderRadius: 10, padding: '24px', gap: 0 }}>
              <div style={{ flex: 1, paddingRight: 20, borderRight: `1px solid ${T.hairline}` }}>
                <div style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.14em', marginBottom: 10 }}>主模型</div>
                <div style={{ fontSize: 20, fontWeight: 600, color: T.green, fontFamily: F.mono }}>{primaryModel}</div>
                <div style={{ fontSize: 13, color: T.mute, marginTop: 4 }}>{String(vr?.model_category || rd?.model_category || '?')}</div>
              </div>
              <div style={{ flex: 1, padding: '0 20px', borderRight: `1px solid ${T.hairline}` }}>
                <div style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.14em', marginBottom: 10 }}>校验模型</div>
                <div style={{ fontSize: 20, fontWeight: 600, color: T.body, fontFamily: F.mono }}>{String(vr?.secondary_model || rd?.secondary_model || '?')}</div>
              </div>
              <div style={{ flex: 2, paddingLeft: 20 }}>
                <div style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.14em', marginBottom: 10 }}>路由理由</div>
                <div style={{ fontSize: 13, color: T.body, lineHeight: 1.8 }}>
                  {String(G(vr, 'routing_reason') || G(rd, 'routing_reason') || '')}
                </div>
              </div>
            </div>
          </div>

          {/* ═══════ 叙事 ═══════ */}
          <div className="report-section narrative-section" id="narrative" style={{ marginBottom: 40 }}>
            <div style={{
              background: T.glassBg, backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
              border: `1px solid ${T.glassBorder}`, borderRadius: 12, padding: '40px 44px',
              borderTop: `2px solid ${T.gold}40`,
            }}>
              <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', marginBottom: 24 }}>
                <div className="narrative-quote" style={{
                  fontFamily: F.display, fontSize: 72, fontWeight: 700, color: T.gold,
                  lineHeight: 0.7, flexShrink: 0, marginTop: -6, opacity: 0.8,
                }}>〝</div>
                <div>
                  <div style={{ fontFamily: F.mono, fontSize: 10, color: T.gold, letterSpacing: '0.2em', marginBottom: 6, opacity: 0.7 }}>◆ NARRATIVE ◆</div>
                  <h2 style={{ fontFamily: F.display, fontSize: 28, fontWeight: 600, color: T.ink, margin: 0, letterSpacing: '-0.01em' }}>叙事</h2>
                </div>
              </div>
              <div style={{ fontSize: 30, lineHeight: 2.0, color: T.body, fontFamily: F.display, fontWeight: 350 }}>
                <MD text={narrative || '暂无叙事数据'} />
              </div>
              <div className="narrative-line" style={{
                height: 1, background: `linear-gradient(90deg, ${T.gold}40, transparent)`,
                marginTop: 28, width: '0%',
              }} />
            </div>
          </div>

          {/* ═══════ 基线分析 ═══════ */}
          {baselineMd && (
            <div className="report-section" id="baseline" style={{ marginBottom: 40 }}>
              <SectionEyebrow>BASELINE</SectionEyebrow>
              <SectionTitle>基线分析</SectionTitle>
              <div style={{
                display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap',
              }}>
                {[
                  { v: `${N(mcap)} 亿`, l: '市值' },
                  { v: primaryModel, l: '模型' },
                  { v: `${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%`, l: '涨幅', c: T.green },
                  { v: `${confOverall}/10`, l: '置信度' },
                ].map((m) => (
                  <div key={m.l} style={{
                    padding: '6px 14px', borderRadius: 8,
                    background: T.glassBg, border: `1px solid ${T.glassBorder}`,
                    fontFamily: F.mono, fontSize: 12, color: m.c || T.ink,
                    display: 'flex', alignItems: 'baseline', gap: 6,
                  }}>
                    <span style={{ fontWeight: 600 }}>{m.v}</span>
                    <span style={{ fontSize: 10, color: T.mute, fontWeight: 400 }}>{m.l}</span>
                  </div>
                ))}
              </div>
              <GlassCard>
                <div style={{ fontSize: 16, lineHeight: 2.1, color: T.body, fontFamily: F.display, fontWeight: 350 }}>
                  <MD text={baselineMd} />
                </div>
              </GlassCard>
            </div>
          )}

          {/* ═══════ 背景知识补充 ═══════ */}
          {G(baselineObj, 'knowledge_supplement') && (
            <div className="report-section" id="knowledge" style={{ marginBottom: 40 }}>
              <SectionEyebrow>KNOWLEDGE</SectionEyebrow>
              <SectionTitle>背景知识补充</SectionTitle>
              <div style={{
                padding: '28px 32px', background: T.glassBg,
                backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
                border: `1px solid ${T.glassBorder}`, borderRadius: 12,
                borderLeft: `0px`,
              }}>
                <div style={{ fontSize: 15, lineHeight: 2.1, color: T.body }}>
                  <MD text={String(G(baselineObj, 'knowledge_supplement')).slice(0, 3000)} />
                </div>
              </div>
            </div>
          )}

          {/* ═══════ BS检测 ═══════ */}
          <div className="report-section" id="bs" style={{ marginBottom: 40 }}>
            <SectionEyebrow>BS DETECTOR</SectionEyebrow>
            <SectionTitle>市场定价了什么？</SectionTitle>
            <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 300 }}>
                <div style={{ fontFamily: F.display, fontSize: 18, color: T.orange, fontWeight: 700, marginBottom: 12 }}>{String(ms?.bs_level || '?')}</div>
                {Boolean(ms?.bs_secondary) && <div style={{ fontSize: 14, color: T.dim, marginBottom: 8 }}>{String(ms.bs_secondary)}</div>}
                <div style={{ fontSize: 15, color: T.body, lineHeight: 2, fontWeight: 350 }}>
                  {Boolean(ms?.market_story) && <MD text={String(ms.market_story)} />}
                </div>
              </div>
              <GlassCard style={{ width: 280, flexShrink: 0 }}>
                <div style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.14em', marginBottom: 12, opacity: 0.5 }}>◇ 关键数据</div>
                <KvRow label="EV" value={`${N(ms?.ev_yi || ms?.ev_billion)} 亿`} />
                <KvRow label="NOPAT" value={`${N(ms?.nopat_yi || ms?.nopat_billion)} 亿`} />
                <KvRow label="ROIC" value={Pct(ms?.roic_pct)} hl />
                <KvRow label="WACC" value={Pct(ms?.wacc_simple_pct)} />
                <KvRow label="隐含 g" value={Pct(ms?.implied_g_pct)} hl />
                <KvRow label="PE(TTM)" value={`${N(ms?.pe_ttm)}×`} />
                <KvRow label="PB" value={`${N(ms?.pb)}×`} />
                {Object.keys(waccParams).length > 0 && (<>
                  <div style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.14em', marginTop: 14, marginBottom: 8, opacity: 0.5 }}>◇ WACC</div>
                  <KvRow label="Rf" value={Pct(waccParams?.rf_pct)} />
                  <KvRow label="Beta" value={N(waccParams?.beta)} />
                  <KvRow label="ERP" value={Pct(waccParams?.erp_pct)} />
                  <KvRow label="WACC" value={Pct(waccParams?.wacc_pct || va?.wacc_mid_pct)} />
                </>)}
              </GlassCard>
            </div>
          </div>

          {/* ═══════ 财务全景 ═══════ */}
          {Object.keys(cf).length > 3 && (
            <div className="report-section" id="financial" style={{ marginBottom: 40 }}>
              <SectionEyebrow>FINANCIALS</SectionEyebrow>
              <SectionTitle>财务全景</SectionTitle>
              <GlassCard>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 32px' }}>
                  <div>
                    <div style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.14em', marginBottom: 10, opacity: 0.5 }}>盈利能力</div>
                    <KvRow label="营收 TTM" value={`${N(cf?.revenue_ttm_yi || cf?.revenue_ttm_billion)} 亿`} />
                    <KvRow label="净利 TTM" value={`${N(cf?.net_profit_ttm_yi || cf?.net_profit_billion)} 亿`} />
                    <KvRow label="ROIC" value={Pct(cf?.roic_pct)} hl />
                    <KvRow label="毛利率" value={Pct(cf?.gross_margin_pct)} />
                    <KvRow label="净利率" value={Pct(cf?.net_margin_pct)} />
                    <KvRow label="ROE" value={Pct(cf?.roe_ttm_pct)} />
                  </div>
                  <div>
                    <div style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.14em', marginBottom: 10, opacity: 0.5 }}>资产负债</div>
                    <KvRow label="经营 CF" value={`${N(cf?.ocf_ttm_yi || cf?.operating_cf_ttm_billion)} 亿`} />
                    <KvRow label="资本开支" value={`${N(cf?.capex_ttm_yi || cf?.capex_ttm_billion)} 亿`} />
                    <KvRow label="总资产" value={`${N(cf?.total_assets_yi || cf?.total_assets_billion)} 亿`} />
                    <KvRow label="净资产" value={`${N(cf?.total_equity_yi || cf?.total_equity_billion)} 亿`} />
                    <KvRow label="有息负债" value={`${N(cf?.interest_bearing_debt_yi || cf?.interest_bearing_debt_billion)} 亿`} />
                    <KvRow label="EBITDA" value={`${N(cf?.ebitda_ttm_yi || cf?.ebitda_ttm_billion)} 亿`} />
                  </div>
                </div>
              </GlassCard>
            </div>
          )}

          {/* ═══════ 信号审计 ═══════ */}
          {G(signalAudit, 'step2b_match') && (
            <div className="report-section" id="signal" style={{ marginBottom: 40 }}>
              <SectionEyebrow>SIGNAL AUDIT</SectionEyebrow>
              <SectionTitle>信号审计</SectionTitle>
              <GlassCard>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 12 }}>
                  <span style={{ fontFamily: F.display, fontSize: 22, color: T.green }}>{N(G(signalAudit, 'step2d_score'))}</span>
                  <span style={{ fontSize: 14, color: T.dim }}>{String(G(signalAudit, 'score_rationale') || '').slice(0, 200)}</span>
                </div>
                {(G(signalAudit, 'step2b_match') as Array<Record<string,unknown>>).map((m, i) => (
                  <div key={i} style={{ fontSize: 13, color: T.body, padding: '8px 14px', borderBottom: `1px solid ${T.hairline}`, background: 'rgba(0,0,0,.1)', borderRadius: 4, marginBottom: 2 }}>
                    <b style={{ color: m?.match === '支持' ? T.green : T.orange }}>{String(m?.match)}</b>{' '}
                    {String(m?.signal)} <span style={{ color: T.mute, fontSize: 11 }}>({String(m?.source_level)})</span> — {String(m?.basis)}
                  </div>
                ))}
              </GlassCard>
            </div>
          )}

          {/* ═══════ 预期差 ═══════ */}
          <div className="report-section" id="gap" style={{ marginBottom: 40 }}>
            <SectionEyebrow>EXPECTATION GAP</SectionEyebrow>
            <SectionTitle>预期差</SectionTitle>
            <GlassCard>
              {Boolean(G(gap, 'level')) && (
                <div style={{ fontFamily: F.mono, fontSize: 17, color: T.green, marginBottom: 8, fontWeight: 700 }}>{String(gap?.level || '?')}</div>
              )}
              {Boolean(gap?.note) && <MD text={String(gap.note)} />}
              {(Boolean(G(rdcf, 'my_implied_g_pct')) || Boolean(G(rdcf, 'expectation_gap_pct'))) && (<>
                <KvRow label="市场隐含 g" value={Pct(G(rdcf, 'market_implied_g_pct'))} />
                <KvRow label="推演隐含 g" value={Pct(G(rdcf, 'my_implied_g_pct'))} hl />
                <KvRow label="Gap 幅度" value={`${Pct(G(rdcf, 'expectation_gap_pct'))} (${String(G(rdcf, 'gap_direction') || '')}·${String(G(rdcf, 'gap_magnitude') || '')})`} />
              </>)}
            </GlassCard>
          </div>

          {/* ═══════ 置信度 ═══════ */}
          <div className="report-section" id="confidence" style={{ marginBottom: 40 }}>
            <SectionEyebrow>CONFIDENCE</SectionEyebrow>
            <SectionTitle>置信度评估：{confOverall}/10</SectionTitle>
            <GlassCard>
              {Object.entries(confDims).map(([key, d]) => (
                <DimBar key={key} label={String(d?.label || key)} score={Number(d?.score || 5)} max={10} note={String(d?.note || '')} />
              ))}
            </GlassCard>
          </div>

          {/* ═══════ 交易标注 ═══════ */}
          <div className="report-section" id="trade" style={{ marginBottom: 40 }}>
            <SectionEyebrow>TRADE ANNOTATION</SectionEyebrow>
            <SectionTitle>交易标注：{String(G(ta, 'tier') || '?')}（{String(G(ta, 'total_score') || '?')}）</SectionTitle>
            <GlassCard>
              {Object.entries({ odds_quality:'S₁ 赔率质量', pricing_headroom:'S₂ 定价空间', transmission_confidence:'S₃ 传导确定性', model_consistency:'S₄ 模型自洽' }).map(([key, label]) => (
                <DimBar key={key} label={label} score={Number(taScores?.[key] || 0)} max={4} />
              ))}
              {taSignals.length > 0 && (
                <ul style={{ listStyle: 'none', margin: '10px 0 0', padding: 0 }}>
                  {taSignals.map((s, i) => <li key={i} style={{ fontSize: 13, color: T.dim, padding: '4px 0' }}>▸ {s}</li>)}
                </ul>
              )}
              {Boolean(G(ta, 'tier_note')) && <div style={{ marginTop: 8 }}><MD text={String(G(ta, 'tier_note'))} /></div>}
              {Boolean(G(ta, 'suggested_action')) && <div style={{ marginTop: 8 }}><MD text={String(G(ta, 'suggested_action'))} /></div>}
            </GlassCard>
          </div>

          {/* ═══════ 交叉验证 ═══════ */}
          {G(vx, 'validation_model') && (
            <div className="report-section" id="crosscheck" style={{ marginBottom: 40 }}>
              <SectionEyebrow>CROSSCHECK</SectionEyebrow>
              <SectionTitle>校验：{String(vx?.validation_model)}（{String(vx?.validation_paradigm || '')}）</SectionTitle>
              <GlassCard>
                <KvRow label="主模型" value={`${N(vx?.base_target_mcap_yi || vx?.base_target_mcap_billion)} 亿`} />
                <KvRow label="校验模型" value={vx?.validation_mcap_yi != null ? `${N(vx.validation_mcap_yi)} 亿` : '数据异常'} hl />
                <KvRow label="差异" value={`${Pct(vx?.gap_pct)} (${String(vx?.gap_direction || '')})`} />
                {Boolean(vx?.assessment) && <div style={{ marginTop: 8 }}><MD text={String(vx.assessment)} /></div>}
              </GlassCard>
            </div>
          )}

          {/* ═══════ 监测 KPI ═══════ */}
          <div className="report-section" id="kpi" style={{ marginBottom: 40 }}>
            <SectionEyebrow>MONITORING KPIs</SectionEyebrow>
            <SectionTitle>未来跟踪指标</SectionTitle>
            <GlassCard>
              <div style={{ fontFamily: F.mono, fontSize: 11, color: T.green, letterSpacing: '0.1em', marginTop: 0, marginBottom: 8 }}>财务验证</div>
              <KpiList items={(G(kpis, 'financial_verification_kpis') || []) as Array<Record<string,unknown>>} color={T.green} />
              <div style={{ fontFamily: F.mono, fontSize: 11, color: T.gold, letterSpacing: '0.1em', marginTop: 14, marginBottom: 8 }}>事件里程碑</div>
              <KpiList items={(G(kpis, 'event_milestone_kpis') || []) as Array<Record<string,unknown>>} color={T.gold} />
              <div style={{ fontFamily: F.mono, fontSize: 11, color: T.orange, letterSpacing: '0.1em', marginTop: 14, marginBottom: 8 }}>竞争信号</div>
              <KpiList items={(G(kpis, 'competition_signal_kpis') || []) as Array<Record<string,unknown>>} color={T.orange} />
            </GlassCard>
          </div>

          {/* ═══════ 风险触发器 ═══════ */}
          {Object.keys(triggers).length > 0 && (
            <div className="report-section" id="triggers" style={{ marginBottom: 40 }}>
              <SectionEyebrow>RISK TRIGGERS</SectionEyebrow>
              <SectionTitle>风险触发器</SectionTitle>
              <GlassCard>
                {Object.entries(triggers).filter(([k]) => k !== 'monitoring_frequency').map(([k, v]) => (
                  <KvRow key={k} label={k === 'bull_trigger' ? '牛触发' : k === 'bear_trigger' ? '熊触发' : k} value={String(v).slice(0, 200)} hl={k === 'bear_trigger'} />
                ))}
                <div style={{ fontFamily: F.mono, fontSize: 11, color: T.mute, marginTop: 8 }}>验证频率: {String(triggers?.monitoring_frequency || '?')}</div>
              </GlassCard>
            </div>
          )}

          {/* ═══════ 数据缺口 ═══════ */}
          {dataGaps.length > 0 && (
            <div className="report-section" style={{ marginBottom: 40 }}>
              <SectionEyebrow>DATA GAPS</SectionEyebrow>
              <SectionTitle>数据缺口</SectionTitle>
              <GlassCard>
                {dataGaps.map((g, i) => <div key={i} style={{ fontSize: 14, color: T.gold, padding: '4px 0' }}>▸ {g}</div>)}
              </GlassCard>
            </div>
          )}

          {/* ═══════ 推理追踪 ═══════ */}
          {trace.length > 0 && (
            <div className="report-section" id="trace" style={{ marginBottom: 40 }}>
              <SectionEyebrow>REASONING TRACE</SectionEyebrow>
              <SectionTitle>推理追踪</SectionTitle>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {trace.map((t, i) => (
                  <div key={i} style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                      background: i === 0 ? T.greenBg : 'rgba(255,255,255,0.03)',
                      border: `1px solid ${i === 0 ? T.greenBorder : T.glassBorder}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontFamily: F.mono, fontSize: 11, color: i === 0 ? T.green : T.mute, fontWeight: 600,
                    }}>{i + 1}</div>
                    <div style={{
                      flex: 1, padding: '12px 18px', background: T.glassBg,
                      backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
                      border: `1px solid ${T.glassBorder}`, borderRadius: 8,
                      fontSize: 14, color: T.body, lineHeight: 1.8,
                    }}>{t}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ═══════ Preflight ═══════ */}
          {preflight.length > 0 && (
            <div className="report-section" style={{ marginBottom: 40 }}>
              <SectionEyebrow>PREFLIGHT</SectionEyebrow>
              <SectionTitle>起飞前检查</SectionTitle>
              <GlassCard>
                {preflight.map((s, i) => <div key={i} style={{ fontSize: 14, color: /PASS/i.test(s) ? T.green : T.orange, padding: '4px 0' }}>▸ {s}</div>)}
              </GlassCard>
            </div>
          )}

          {/* ═══════ Agent0 预路由（折叠在最后） ═══════ */}
          {Object.keys(baselineObj).length > 0 && (
            <div className="report-section" id="a0" style={{ marginBottom: 40, opacity: a0Open ? 1 : 0.55 }}>
              <SectionEyebrow>AGENT-0 PRE-ROUTING</SectionEyebrow>
              <SectionTitle>预路由 · 事件分析</SectionTitle>
              <GlassCard>
                <button onClick={() => setA0Open(!a0Open)} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  width: '100%', background: 'transparent', border: 'none', cursor: 'pointer',
                  fontFamily: F.mono, fontSize: 12, color: T.dim, padding: 0,
                }}>
                  <span>{a0Open ? '▲ 收起预路由分析' : '▶ 展开预路由分析'}</span>
                  <Chip tone="green">{`L${String(baselineObj?.response_level || '?')}`}</Chip>
                </button>
                {a0Open && (
                  <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10, borderTop: `1px solid ${T.hairline}`, paddingTop: 16 }}>
                    {Boolean(G(baselineObj, 'investment_theme')) && <MD text={String(G(baselineObj, 'investment_theme')).slice(0, 3000)} />}
                    {Boolean(G(baselineObj, 'event_deduction')) && <MD text={String(G(baselineObj, 'event_deduction'))} />}
                    {Boolean(G(baselineObj, 'preliminary_reasoning')) && <MD text={String(G(baselineObj, 'preliminary_reasoning'))} />}
                    {Boolean(G(baselineObj, 'adversarial_thinking')) && <MD text={String(G(baselineObj, 'adversarial_thinking')).slice(0, 1500)} />}
                    {Boolean(G(baselineObj, 'industry_expert_research')) && <MD text={String(G(baselineObj, 'industry_expert_research')).slice(0, 2000)} />}
                    {Boolean(G(baselineObj, 'future')) && <MD text={String(G(baselineObj, 'future')).slice(0, 1000)} />}
                    {Boolean(G(baselineObj, 'raw_event_text')) && <MD text={String(G(baselineObj, 'raw_event_text')).slice(0, 1000)} />}
                  </div>
                )}
              </GlassCard>
            </div>
          )}

          {/* ═══════ Footer ═══════ */}
          <div style={{ textAlign: 'center', paddingTop: 32, borderTop: `1px solid ${T.divider}`, fontFamily: F.mono, fontSize: 10, color: T.steel, letterSpacing: '0.04em' }}>
            估值重构引擎 V5 · {code} · 不构成投资建议
          </div>
        </>)}
      </div>
    </div>
    </>
  )
}
