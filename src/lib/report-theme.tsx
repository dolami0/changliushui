/* ================================================================== */
/*  Report Theme — 杂志排版 · 霓虹绿 · 毛玻璃                            */
/* ================================================================== */

export const T = {
  /* Background */
  bg:       '#050401',
  bgCard:   'rgba(255,255,255,0.02)',
  glassBg:  'rgba(255,255,255,0.035)',
  glassBorder: 'rgba(255,255,255,0.08)',

  /* Accent */
  green:    '#ADFF00',
  greenDim: 'rgba(173,255,0,0.6)',
  greenBg:  'rgba(173,255,0,0.04)',
  greenBorder: 'rgba(173,255,0,0.12)',

  orange:   '#FF5C00',
  orangeDim:'rgba(255,92,0,0.6)',
  orangeBg: 'rgba(255,92,0,0.03)',
  orangeBorder: 'rgba(255,92,0,0.1)',

  gold:     '#C88D3A',

  /* Text */
  ink:      '#F2F4F3',   /* titles */
  body:     '#BBB',       /* paragraphs */
  bodyMd:   '#CCC',       /* markdown body */
  dim:      '#999',       /* secondary labels */
  mute:     '#888',       /* tertiary */
  steel:    '#666',       /* footer */

  /* Lines */
  hairline: 'rgba(255,255,255,0.06)',
  divider:  'rgba(255,255,255,0.07)',
} as const

export const F = {
  display:  "'Source Serif 4', 'Noto Sans SC', serif",
  body:     "'Noto Sans SC', system-ui, sans-serif",
  mono:     "'IBM Plex Mono', 'Space Mono', monospace",
  pixel:    "'Geist Pixel', monospace",
} as const

/* ================================================================== */
/*  Glass card style object                                             */
/* ================================================================== */

export const glass: React.CSSProperties = {
  background: T.glassBg,
  backdropFilter: 'blur(12px)',
  WebkitBackdropFilter: 'blur(12px)',
  border: `1px solid ${T.glassBorder}`,
  borderRadius: 10,
  padding: '24px',
}

export function glassRow(_k: string, _v: React.ReactNode, _hl?: boolean): React.CSSProperties {
  // Helper for key-value rows inside glass cards
  return {}
}

/* ================================================================== */
/*  Dot Grid Background                                                 */
/* ================================================================== */

export function DotGridBg() {
  return null
}

/* ================================================================== */
/*  Section header                                                     */
/* ================================================================== */

export function SectionEyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontFamily: F.mono,
      fontSize: 10,
      color: T.greenDim,
      letterSpacing: '0.16em',
      marginBottom: 12,
      opacity: 0.85,
    }}>{children}</div>
  )
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{
      fontFamily: F.display,
      fontSize: 26,
      fontWeight: 600,
      color: T.ink,
      margin: '0 0 18px',
      letterSpacing: '-0.01em',
    }}>{children}</h2>
  )
}

/* ================================================================== */
/*  Glass card wrapper                                                 */
/* ================================================================== */

export function GlassCard({ children, style, pad }: { children: React.ReactNode; style?: React.CSSProperties; pad?: string }) {
  return (
    <div style={{
      ...glass,
      padding: pad ?? '24px',
      ...style,
    }}>{children}</div>
  )
}

/* ================================================================== */
/*  KvRow — label: value inside a glass card                           */
/* ================================================================== */

export function KvRow({ label, value, hl }: { label: string; value: string; hl?: boolean }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '9px 0',
      borderBottom: `1px solid ${T.hairline}`,
      fontSize: 13,
      color: T.body,
    }}>
      <span style={{ color: T.dim, fontFamily: F.mono, fontSize: 11, letterSpacing: '0.06em', minWidth: 80 }}>{label}</span>
      <span style={{ color: hl ? T.green : T.body, fontFamily: F.mono, fontSize: 13, textAlign: 'right' as const, fontWeight: hl ? 600 : 400 }}>{value}</span>
    </div>
  )
}

/* ================================================================== */
/*  Chip / Badge                                                       */
/* ================================================================== */

export function Chip({ children, tone }: { children: string; tone?: 'green' | 'orange' }) {
  const c = tone === 'orange' ? T.orange : T.green
  return (
    <span style={{
      display: 'inline-block',
      fontSize: 10,
      padding: '2px 8px',
      borderRadius: 100,
      border: `1px solid ${c}33`,
      color: c,
      background: `${c}0a`,
      fontFamily: F.mono,
      letterSpacing: '0.04em',
    }}>{children}</span>
  )
}

/* ================================================================== */
/*  Progress bar                                                       */
/* ================================================================== */

export function ProgBar({ label, score, max, color }: { label: string; score: number; max: number; color?: string }) {
  const c = color ?? (score >= 7 ? T.green : score >= 5 ? T.gold : T.orange)
  const pct = Math.min(100, (score / max) * 100)
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontSize: 13, marginBottom: 5, color: T.body }}>
        <span>{label}</span>
        <span style={{ fontFamily: F.mono, fontWeight: 600, fontSize: 14, color: c }}>
          {score}<small style={{ fontSize: 11, fontWeight: 400, opacity: 0.4 }}>/{max}</small>
        </span>
      </div>
      <div style={{ height: 3, background: 'rgba(255,255,255,0.04)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: c, borderRadius: 2, opacity: 0.6 }} />
      </div>
    </div>
  )
}
