import { ArrowUpRight } from 'lucide-react'

/* ================================================================== */
/*  长流水 v2 — 全新布局：侧边导航 + 内容瀑布 + 纹理背景 + 卡片流         */
/* ================================================================== */

const T = {
  canvas:    '#0d0d12',
  surface:   '#16161d',
  surface2:  '#1e1e26',
  ink:       '#e8e8ed',
  charcoal:  '#c0c0cc',
  slate:     '#8888a0',
  steel:     '#5a5a72',
  stone:     '#3a3a4a',
  accent:    '#7eb8da',
  accentBg:  'rgba(126,184,218,0.08)',
  gold:      '#d4af37',
  up:        '#c45c48',
  upBg:      'rgba(196,92,72,0.08)',
  down:      '#5b8c85',
  downBg:    'rgba(91,140,133,0.08)',
  hairline:  'rgba(255,255,255,0.06)',
}

const F = {
  display: "'Noto Sans SC', system-ui, sans-serif",
  body:    "'Noto Sans SC', system-ui, sans-serif",
  mono:    "'IBM Plex Mono', 'Space Mono', monospace",
}

/* ================================================================== */
/*  Background Pattern                                                  */
/* ================================================================== */

function DotGrid() {
  return (
    <div style={{
      position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
      opacity: 0.08,
      backgroundImage: 'radial-gradient(circle, rgba(126,184,218,0.6) 0.5px, transparent 0.5px)',
      backgroundSize: '24px 24px',
    }} />
  )
}

/* ================================================================== */
/*  Sidebar Navigation  (replaces top nav)                              */
/* ================================================================== */

function Sidebar() {
  const links = [
    { label: '宗门总览', icon: '◇' },
    { label: '定数录',   icon: '⊡' },
    { label: '跟踪令',   icon: '◎' },
    { label: '天机峰',   icon: '☲' },
    { label: '风闻入阵', icon: '☳' },
    { label: '身外化身', icon: '⊚' },
  ]
  return (
    <aside style={{
      position: 'fixed', top: 0, left: 0, bottom: 0, zIndex: 40,
      width: 200, background: T.surface,
      borderRight: `1px solid ${T.hairline}`,
      display: 'flex', flexDirection: 'column',
      padding: '32px 20px',
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 40 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8,
          background: T.gold,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: T.canvas, fontSize: 18, fontWeight: 700, fontFamily: F.mono,
        }}>◇</div>
        <div>
          <div style={{ fontFamily: F.display, fontSize: 15, fontWeight: 700, color: T.ink, lineHeight: 1.2 }}>长流水</div>
          <div style={{ fontFamily: F.body, fontSize: 10, color: T.steel, marginTop: 1 }}>青山长流水</div>
        </div>
      </div>

      {/* Nav links */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {links.map((l, i) => (
          <a key={l.label} href="#" style={{
            fontFamily: F.body, fontSize: 13, fontWeight: i === 1 ? 600 : 400,
            color: i === 1 ? T.accent : T.slate,
            background: i === 1 ? T.accentBg : 'transparent',
            textDecoration: 'none',
            padding: '8px 12px', borderRadius: 8,
            display: 'flex', alignItems: 'center', gap: 10,
            transition: 'all 0.15s',
          }}
            onMouseEnter={(e) => { if (i !== 1) { e.currentTarget.style.background = T.surface2; e.currentTarget.style.color = T.charcoal }}}
            onMouseLeave={(e) => { if (i !== 1) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = T.slate }}}
          >
            <span style={{ fontSize: 15, width: 20, textAlign: 'center', color: i === 1 ? T.accent : T.steel }}>{l.icon}</span>
            {l.label}
          </a>
        ))}
      </nav>

      {/* Bottom status */}
      <div style={{ marginTop: 'auto' }}>
        <div style={{
          fontFamily: F.mono, fontSize: 10, color: T.steel,
          background: T.surface2, borderRadius: 8, padding: '12px',
          textAlign: 'center', lineHeight: 1.6,
        }}>
          <div style={{ color: T.up, fontSize: 12, fontWeight: 600, marginBottom: 4 }}>● 猎杀中</div>
          全系统运转中<br />
          灵气吞吐 +18.7%
        </div>
      </div>
    </aside>
  )
}

/* ================================================================== */
/*  Card — clean, border-only on hover                                 */
/* ================================================================== */

function Card({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <div onClick={onClick} style={{
      background: T.surface, borderRadius: 10, padding: '18px 22px',
      border: `1px solid ${T.hairline}`,
      cursor: onClick ? 'pointer' : 'default',
      transition: 'border-color 0.2s',
    }}
      onMouseEnter={(e) => { if (onClick) e.currentTarget.style.borderColor = `${T.accent}30` }}
      onMouseLeave={(e) => { if (onClick) e.currentTarget.style.borderColor = T.hairline }}
    >{children}</div>
  )
}

function Badge({ children, tone = 'steel' }: { children: React.ReactNode; tone?: 'accent' | 'up' | 'down' | 'steel' }) {
  const m = {
    accent: { bg: T.accentBg, text: T.accent },
    up:     { bg: T.upBg,    text: T.up },
    down:   { bg: T.downBg,  text: T.down },
    steel:  { bg: T.surface2, text: T.steel },
  }[tone]
  return <span style={{ fontFamily: F.mono, fontSize: 10, fontWeight: 600, color: m.text, background: m.bg, padding: '2px 8px', borderRadius: 5 }}>{children}</span>
}

/* ================================================================== */
/*  Content Area                                                       */
/* ================================================================== */

function PageHeader() {
  return (
    <div style={{ marginBottom: 36 }}>
      <div style={{ fontFamily: F.mono, fontSize: 10, color: T.accent, letterSpacing: '0.18em', marginBottom: 10, opacity: 0.6, textTransform: 'uppercase' }}>定数录 · 估值报告</div>
      <h1 style={{ fontFamily: F.display, fontSize: 32, fontWeight: 800, color: T.ink, margin: '0 0 8px' }}>
        神机百炼
      </h1>
      <p style={{ fontFamily: F.body, fontSize: 15, color: T.slate, maxWidth: 520, lineHeight: 1.7 }}>
        念念相续，天机无相。大道所向，因果成章。
      </p>
    </div>
  )
}

function MetricsStrip() {
  return (
    <div style={{
      display: 'flex', gap: 12, marginBottom: 36, flexWrap: 'wrap',
    }}>
      {[
        { v: '+23.5%', l: '概率加权涨幅', up: true },
        { v: '2.8×',   l: '不对称比', up: null },
        { v: '7/10',   l: '置信度', up: null },
        { v: '-18.2%', l: '最大回撤', up: false },
      ].map((m) => (
        <div key={m.l} style={{
          padding: '14px 20px', borderRadius: 10,
          background: m.up === true ? T.upBg : m.up === false ? T.downBg : T.surface,
          border: `1px solid ${T.hairline}`,
          minWidth: 120, textAlign: 'center',
        }}>
          <div style={{
            fontFamily: F.mono, fontSize: 22, fontWeight: 700,
            color: m.up === true ? T.up : m.up === false ? T.down : T.ink,
            lineHeight: 1.1,
          }}>
            {m.up === true ? '↑ ' : m.up === false ? '↓ ' : ''}{m.v}
          </div>
          <div style={{ fontFamily: F.body, fontSize: 11, color: T.steel, marginTop: 4 }}>{m.l}</div>
        </div>
      ))}
    </div>
  )
}

/* ================================================================== */
/*  Card Grid — 流式卡片布局，水平滚动行 + 纵向瀑布                          */
/* ================================================================== */

function CardGrid() {
  const reports = [
    { name: '宏达电子', code: '300726', tier: '★★★', upside: '+28.3', asym: '3.2', quality: 'HIGH_QUALITY', date: '06-08', model: 'PE', sector: '军工电子' },
    { name: '中微公司', code: '688012', tier: '★★☆', upside: '+15.7', asym: '2.1', quality: 'ADEQUATE', date: '06-07', model: 'PS', sector: '半导体设备' },
    { name: '韦尔股份', code: '603501', tier: '★★★', upside: '+32.1', asym: '4.5', quality: 'HIGH_QUALITY', date: '06-07', model: 'PE', sector: '芯片设计' },
    { name: '北方华创', code: '002371', tier: '★☆☆', upside: '-3.2', asym: '0.8', quality: 'SPECULATIVE', date: '06-06', model: 'EV/EBITDA', sector: '半导体设备' },
    { name: '兆易创新', code: '603986', tier: '★★★', upside: '+19.8', asym: '2.7', quality: 'HIGH_QUALITY', date: '06-05', model: 'PE', sector: '存储芯片' },
    { name: '卓胜微',   code: '300782', tier: '★★☆', upside: '+11.2', asym: '1.9', quality: 'ADEQUATE', date: '06-04', model: 'PS', sector: '射频芯片' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 16 }}>
        <h2 style={{ fontFamily: F.display, fontSize: 16, fontWeight: 700, color: T.ink, margin: 0 }}>最新报告</h2>
        <span style={{ fontFamily: F.mono, fontSize: 11, color: T.steel }}>{reports.length} 份</span>
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', gap: 6 }}>
          {['时间', '涨幅'].map((s, i) => (
            <button key={s} style={{
              fontFamily: F.body, fontSize: 12, fontWeight: i === 0 ? 600 : 400,
              color: i === 0 ? '#FFF' : T.slate,
              background: i === 0 ? T.accent : 'transparent',
              border: i === 0 ? 'none' : `1px solid ${T.hairline}`,
              padding: '5px 14px', borderRadius: 100, cursor: 'pointer',
            }}>{s}</button>
          ))}
        </div>
      </div>

      {/* Masonry-like 2-column card grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 10,
      }}>
        {reports.map((r) => {
          const isUp = parseFloat(r.upside) > 0
          return (
            <Card key={r.code} onClick={() => {}}>
              {/* Top row: name + date */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                <div>
                  <div style={{ fontFamily: F.display, fontSize: 14, fontWeight: 600, color: T.ink, marginBottom: 2 }}>{r.name}</div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontFamily: F.mono, fontSize: 11, color: T.steel }}>{r.code}</span>
                    <span style={{ fontFamily: F.mono, fontSize: 10, color: T.stone }}>{r.sector}</span>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <Badge tone={isUp ? 'up' : 'down'}>{r.tier}</Badge>
                  <div style={{ fontFamily: F.mono, fontSize: 10, color: T.stone, marginTop: 4 }}>{r.date}</div>
                </div>
              </div>

              {/* Metrics row */}
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 0', borderTop: `1px solid ${T.hairline}`, borderBottom: `1px solid ${T.hairline}`,
                marginBottom: 10,
              }}>
                <div>
                  <span style={{ fontFamily: F.mono, fontSize: 20, fontWeight: 700, color: isUp ? T.up : T.down }}>
                    {r.upside}%
                  </span>
                  <span style={{ fontFamily: F.mono, fontSize: 10, color: T.steel, marginLeft: 4 }}>概率加权</span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: F.mono, fontSize: 12, color: T.charcoal }}>不对称比 {r.asym}x</div>
                  <div style={{ fontFamily: F.mono, fontSize: 10, color: T.steel }}>模型 {r.model}</div>
                </div>
              </div>

              {/* Bottom: quality + arrow */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Badge tone="steel">{r.quality}</Badge>
                <span style={{ fontFamily: F.body, fontSize: 12, color: T.accent, display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
                  查看详情 <ArrowUpRight size={12} />
                </span>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

/* ================================================================== */
/*  Quick Actions Row  (horizontal scroll)                              */
/* ================================================================== */

function QuickActions() {
  return (
    <div style={{
      marginBottom: 36, marginTop: 6,
      display: 'flex', gap: 10, flexWrap: 'wrap',
    }}>
      {[
        { label: '风闻入阵', desc: '提交资讯直送估值引擎', icon: '☳' },
        { label: '身外化身', desc: 'AI 对话 · 上下文分析', icon: '⊚' },
        { label: '追踪令',   desc: '3 只标的跟踪中', icon: '◎' },
        { label: '天机峰',   desc: '17 条今日事件', icon: '☲' },
      ].map((a) => (
        <button key={a.label} style={{
          flex: '1 1 180px', minWidth: 160,
          fontFamily: F.body, textAlign: 'left',
          background: T.surface, border: `1px solid ${T.hairline}`,
          borderRadius: 10, padding: '16px 18px', cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 12,
          transition: 'border-color 0.2s',
        }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = `${T.accent}30` }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = T.hairline }}
        >
          <span style={{ fontSize: 20, color: T.accent, width: 28, textAlign: 'center' }}>{a.icon}</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: T.ink, marginBottom: 2 }}>{a.label}</div>
            <div style={{ fontSize: 11, color: T.steel }}>{a.desc}</div>
          </div>
        </button>
      ))}
    </div>
  )
}

/* ================================================================== */
/*  Page                                                                */
/* ================================================================== */

export default function RedesignDemo() {
  return (
    <div style={{ minHeight: '100vh', background: T.canvas, fontFamily: F.body }}>
      <DotGrid />
      <Sidebar />
      {/* Main content — offset by sidebar width */}
      <main style={{ marginLeft: 200, padding: '40px 48px 80px', position: 'relative', zIndex: 1 }}>
        <PageHeader />
        <MetricsStrip />
        <QuickActions />
        <CardGrid />
        <footer style={{ marginTop: 48, textAlign: 'center', fontFamily: F.mono, fontSize: 11, color: T.stone }}>
          2025 长流水宗门 · 全系统运转中
        </footer>
      </main>
    </div>
  )
}
