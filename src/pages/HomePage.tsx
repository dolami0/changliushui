import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { T, F, SectionEyebrow, SectionTitle, GlassCard, Chip } from '@/lib/report-theme'
import { fetchDingshulu, type DingshuluRecord } from '@/services/cozeApi'

gsap.registerPlugin(ScrollTrigger)

/* ================================================================== */
/*  Home Page                                                           */
/* ================================================================== */
export default function HomePage() {
  const navigate = useNavigate()
  const mainRef = useRef<HTMLDivElement>(null)
  const [reports, setReports] = useState<DingshuluRecord[]>([])
  const [stats, setStats] = useState({ upside: 0, asym: 0, count: 0, confAvg: 0 })

  useEffect(() => {
    fetchDingshulu(100).then(ds => {
      setReports(ds)
      const upsides = ds.map(d => parseFloat(d.prob_weighted_upside_pct || '0')).filter(v => !isNaN(v))
      const asyms = ds.map(d => parseFloat(d.asymmetry_ratio || '0')).filter(v => !isNaN(v))
      setStats({
        upside: upsides.length > 0 ? upsides.reduce((a, b) => a + b, 0) / upsides.length : 0,
        asym: asyms.length > 0 ? asyms.reduce((a, b) => a + b, 0) / asyms.length : 0,
        count: ds.length,
        confAvg: 7,
      })
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!mainRef.current) return
    const ctx = gsap.context(() => {
      // Hero entrance
      gsap.from('.hp-hero-anim', { autoAlpha: 0, y: 24, duration: 0.7, ease: 'power3.out', stagger: 0.1, delay: 0.2 })
      // Section reveals
      document.querySelectorAll('.hp-section').forEach(sec => {
        ScrollTrigger.create({ trigger: sec, start: 'top 82%', onEnter: () => gsap.fromTo(sec, { autoAlpha: 0, y: 20 }, { autoAlpha: 1, y: 0, duration: 0.55, ease: 'power2.out' }) })
      })
      // Big numbers bounce
      document.querySelectorAll('.hp-bignum').forEach(el => {
        ScrollTrigger.create({ trigger: el, start: 'top 85%', onEnter: () => gsap.fromTo(el, { scale: 0.7, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 0.6, ease: 'back.out(1.5)' }) })
      })
    }, mainRef.current)
    return () => ctx.revert()
  }, [reports.length])

  return (
    <div ref={mainRef} style={{ background: T.bg, minHeight: '100vh', paddingBottom: 80 }}>
      <div style={{ maxWidth: 960, margin: '0 auto', padding: '48px 40px 40px' }}>

        {/* ═══════════ HERO ═══════════ */}
        <div className="hp-section" style={{ marginBottom: 40 }}>
          <div className="hp-hero-anim" style={{ fontFamily: F.mono, fontSize: 10, color: T.greenDim, letterSpacing: '0.2em', marginBottom: 14, opacity: 0.85 }}>长流水 · 估值重构引擎</div>
          <div style={{ display: 'flex', gap: 28, alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <h1 className="hp-hero-anim" style={{ fontFamily: F.display, fontSize: 52, fontWeight: 700, color: T.ink, margin: '0 0 8px', letterSpacing: '-0.02em', lineHeight: 1.1 }}>
                神机百炼
              </h1>
              <p className="hp-hero-anim" style={{ fontSize: 17, color: T.body, lineHeight: 1.9, fontWeight: 300, marginBottom: 10, maxWidth: 560 }}>
                AI大阵驱动天眼→估值→追踪全链路。念念相续，天机无相。大道所向，因果成章。
              </p>
              <div className="hp-hero-anim" style={{ display: 'flex', gap: 12, fontFamily: F.mono, fontSize: 11, color: T.mute, alignItems: 'center', flexWrap: 'wrap' }}>
                <Chip tone="green">全系统运转中</Chip>
                <span style={{ color: '#333' }}>|</span>
                <span>已产出 <b style={{ color: T.green }}>{stats.count}</b> 份估值报告</span>
                <span>平均不对称比 <b style={{ color: T.body }}>{stats.asym.toFixed(1)}×</b></span>
              </div>
            </div>
            {/* 三大数字 */}
            <div className="hp-hero-anim" style={{ width: 180, flexShrink: 0 }}>
              <div style={{ background: T.glassBg, backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', border: `1px solid ${T.glassBorder}`, borderRadius: 10, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="hp-bignum" style={{ textAlign: 'center', paddingBottom: 8, borderBottom: `1px solid ${T.hairline}` }}>
                  <div className="bignum-val" style={{ fontFamily: F.display, fontSize: 28, fontWeight: 700, color: T.green, lineHeight: 1 }}>{stats.upside >= 0 ? '+' : ''}{stats.upside.toFixed(1)}%</div>
                  <div style={{ fontFamily: F.mono, fontSize: 9, color: T.dim, marginTop: 2 }}>平均概率加权涨幅</div>
                </div>
                <div className="hp-bignum" style={{ textAlign: 'center', paddingBottom: 8, borderBottom: `1px solid ${T.hairline}` }}>
                  <div className="bignum-val" style={{ fontFamily: F.display, fontSize: 24, fontWeight: 700, color: T.ink, lineHeight: 1 }}>{stats.asym.toFixed(1)}×</div>
                  <div style={{ fontFamily: F.mono, fontSize: 9, color: T.dim, marginTop: 2 }}>平均不对称比</div>
                </div>
                <div className="hp-bignum" style={{ textAlign: 'center' }}>
                  <div className="bignum-val" style={{ fontFamily: F.display, fontSize: 24, fontWeight: 700, color: T.ink, lineHeight: 1 }}>{stats.confAvg}/10</div>
                  <div style={{ fontFamily: F.mono, fontSize: 9, color: T.dim, marginTop: 2 }}>平均置信度</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ═══════════ 定数录 ═══════════ */}
        <div className="hp-section" style={{ marginBottom: 40 }}>
          <SectionEyebrow>DINGSHULU</SectionEyebrow>
          <SectionTitle>最新估值报告</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 10 }}>
            {reports.slice(0, 6).map((r, i) => {
              const up = parseFloat(r.prob_weighted_upside_pct || '0')
              const fn = r.report_html_url?.split('/').pop()?.replace('.html', '') || r.stock_code
              return (
                <div key={r.id || i} className="hp-bignum" onClick={() => navigate(`/report/${fn}`)} style={{
                  padding: '18px 20px', background: T.glassBg, backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
                  border: `1px solid ${T.glassBorder}`, borderRadius: 10, cursor: 'pointer',
                  transition: 'border-color 0.2s, transform 0.2s',
                }} onMouseEnter={e => { e.currentTarget.style.borderColor = `${T.green}40`; e.currentTarget.style.transform = 'translateY(-2px)' }}
                   onMouseLeave={e => { e.currentTarget.style.borderColor = T.glassBorder; e.currentTarget.style.transform = 'none' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                    <div>
                      <div style={{ fontFamily: F.display, fontSize: 15, fontWeight: 600, color: T.ink, marginBottom: 2 }}>{r.stock_name}</div>
                      <div style={{ fontFamily: F.mono, fontSize: 11, color: T.mute }}>{r.stock_code}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontFamily: F.mono, fontSize: 20, fontWeight: 700, color: up >= 0 ? T.green : T.orange }}>
                        {up >= 0 ? '+' : ''}{up.toFixed(1)}%
                      </div>
                      <div style={{ fontFamily: F.mono, fontSize: 10, color: T.dim, marginTop: 2 }}>概率加权</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontFamily: F.mono, fontSize: 10, color: T.steel }}>
                    <span>基 {r.base_upside_pct || '—'}%</span>
                    <span style={{ color: '#333' }}>|</span>
                    <span>牛 {r.bull_upside_pct || '—'}%</span>
                    <span style={{ color: '#333' }}>|</span>
                    <span>熊 {r.bear_upside_pct || '—'}%</span>
                    {r.trade_tier && <Chip tone="green">{r.trade_tier.slice(0, 3)}</Chip>}
                  </div>
                </div>
              )
            })}
          </div>
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <button onClick={() => navigate('/cangjingyun?table=dingshulu')} style={{ fontFamily: F.mono, fontSize: 12, color: T.green, background: 'transparent', border: `1px solid ${T.greenBorder}`, padding: '8px 24px', borderRadius: 8, cursor: 'pointer', letterSpacing: '0.08em' }}>
              → 查看全部 {reports.length} 份报告
            </button>
          </div>
        </div>

        {/* ═══════════ 风闻入阵 ═══════════ */}
        <div className="hp-section" style={{ marginBottom: 40 }}>
          <SectionEyebrow>SUBMIT</SectionEyebrow>
          <SectionTitle>风闻入阵</SectionTitle>
          <GlassCard>
            <div style={{ fontSize: 14, color: T.dim, marginBottom: 12 }}>粘贴资讯或分析命题，直送估值引擎炼化</div>
            <QuickSubmitForm />
          </GlassCard>
        </div>

        {/* ═══════════ Footer ═══════════ */}
        <div style={{ textAlign: 'center', paddingTop: 32, borderTop: `1px solid ${T.divider}`, fontFamily: F.mono, fontSize: 10, color: T.steel, letterSpacing: '0.04em' }}>
          长流水 · 赛博仙门十倍股猎杀系统 · 不构成投资建议
        </div>
      </div>
    </div>
  )
}

/* ================================================================== */
/*  QuickSubmitForm — 风闻入阵迷你表单                                   */
/* ================================================================== */
function QuickSubmitForm() {
  const [input, setInput] = useState('')
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)

  const handleSend = async () => {
    if (!input.trim() || sending) return
    setSending(true)
    try {
      const TOKEN = import.meta.env.VITE_COZE_TOKEN || ''
      await fetch('https://api.coze.cn/v1/databases/7479116110479048754/records', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json' },
        body: JSON.stringify({ records: [{ fields: { news_content: input.trim(), stock_code: code.trim() || 'USER_INPUT', stock_name: name.trim() || '用户传讯', level: '3', mode: 'manual' } }] }),
      })
      setSent(true); setInput(''); setCode(''); setName('')
      setTimeout(() => setSent(false), 3000)
      fetch('/api/trigger', { method: 'POST' }).catch(() => {})
    } catch {}
    setSending(false)
  }

  return (
    <div>
      <textarea value={input} onChange={e => setInput(e.target.value)} placeholder="在此输入资讯内容或分析命题…" rows={5}
        style={{ width: '100%', boxSizing: 'border-box', background: 'rgba(255,255,255,0.03)', border: `1px solid ${T.glassBorder}`, color: T.body, padding: '12px 14px', fontFamily: `${F.mono},${F.body}`, fontSize: 14, lineHeight: 1.7, resize: 'vertical', outline: 'none', borderRadius: 8 }}
        onFocus={e => { e.currentTarget.style.borderColor = `${T.green}60` }}
        onBlur={e => { e.currentTarget.style.borderColor = T.glassBorder }} />
      <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
        <input value={code} onChange={e => setCode(e.target.value)} placeholder="代码(可选)"
          style={{ flex: 1, background: 'rgba(255,255,255,0.03)', border: `1px solid ${T.glassBorder}`, color: T.body, padding: '8px 12px', fontFamily: F.mono, fontSize: 13, outline: 'none', borderRadius: 8 }}
          onFocus={e => { e.currentTarget.style.borderColor = `${T.green}60` }} onBlur={e => { e.currentTarget.style.borderColor = T.glassBorder }} />
        <input value={name} onChange={e => setName(e.target.value)} placeholder="名称(可选)"
          style={{ flex: 1, background: 'rgba(255,255,255,0.03)', border: `1px solid ${T.glassBorder}`, color: T.body, padding: '8px 12px', fontFamily: F.mono, fontSize: 13, outline: 'none', borderRadius: 8 }}
          onFocus={e => { e.currentTarget.style.borderColor = `${T.green}60` }} onBlur={e => { e.currentTarget.style.borderColor = T.glassBorder }} />
        <button onClick={handleSend} disabled={sending || !input.trim()}
          style={{ padding: '8px 28px', background: input.trim() && !sending ? `${T.green}18` : 'rgba(255,255,255,0.03)', border: `1px solid ${input.trim() && !sending ? `${T.green}40` : T.glassBorder}`, color: input.trim() && !sending ? T.green : T.mute, fontFamily: F.mono, fontSize: 13, letterSpacing: '0.06em', cursor: input.trim() && !sending ? 'pointer' : 'not-allowed', borderRadius: 8, transition: 'all 0.2s', opacity: input.trim() ? 1 : 0.5 }}>
          {sending ? '传讯中…' : sent ? '✓ 已传讯' : '传讯入阵'}
        </button>
      </div>
      {sent && <div style={{ marginTop: 8, fontFamily: F.mono, fontSize: 12, color: T.green, textAlign: 'center' }}>传讯已入阵，估值引擎将自动处理</div>}
    </div>
  )
}
