import { useState, useEffect, useMemo } from 'react'
import { TrendingUp, TrendingDown, Target, Shield, Calendar, AlertTriangle, Activity, X, Zap, Building2, Unlock, Coins } from 'lucide-react'
import { useMobile } from '@/hooks/useMobile'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as ReTooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts'

/* ================================================================== */
/*  Types                                                              */
/* ================================================================== */

interface Pillar {
  name: string
  expectation: string
  quantifiedTarget?: string
  status: 'pending' | 'on_track' | 'at_risk' | 'verified'
  verificationDate: string
  lastChecked: string
  history: { date: string; actual: string; trend: string }[]
}

interface Risk {
  name: string
  probability: string
  impact: string
  monitoring: string
}

interface CatalystEvent {
  date: string
  event: string
  type: string
  impact: 'H' | 'M' | 'L'
  bull: string
  bear: string
  sourceLevel?: 'L5' | 'L4' | 'L3' | 'L2' | 'L1'
  sourceDetail?: string
  sourceNote?: string
  status?: 'pending' | 'triggered' | 'missed' | 'verified'
}

interface PriceLogEntry {
  date: string
  price: number
  pe: number
  mv_yi: number
  return_pct: number
  mv_change_pct: number
  pct_chg_daily?: number
  note: string
}

interface AShareChecks {
  pledgeCheck: { lastChecked: string; result: string }
  unlockCheck: { lastChecked: string; result: string }
  marginCheck: { lastChecked: string; result: string }
  insiderTrading: { lastChecked: string; result: string }
}

interface ThesisVersion {
  version: number
  date: string
  thesis: string
  conviction: number
  delta: string
  trigger: string
  narrative: string
  verifiedAssumptions: string[]
  invalidatedAssumptions: string[]
  newUnknowns: string[]
  narrativeTension: 'rising' | 'stable' | 'easing' | 'breaking'
}

interface TrackingData {
  stockCode: string
  stockName: string
  track_status: 'active' | 'paused'
  thesis: string
  conviction: number
  decisionDate: string
  decision: string
  recommendedPosition: number
  actualPosition: number
  entryCondition: string
  entryPriceTarget: number | null
  pillars: Pillar[]
  risks: Risk[]
  exitConditions: string[]
  catalystCalendar: CatalystEvent[]
  basePrice: number
  baseMarketCap: number
  baseDate: string
  priceLog: PriceLogEntry[]
  positionLog: unknown[]
  thesisLog?: ThesisVersion[]
  valuationComparison?: ValuationComparison
  aShareTracking: AShareChecks
  reviewSchedule: {
    nextFullReview: string
    nextQuickCheck: string
    lastCheck: string
    patrolFrequency?: string
  }
}

interface ScenarioRow {
  myCAGR: number
  myPS: number
  myReturn: number
  upCAGR: number
  upPS: number
  upReturn: number
}

interface ValuationComparison {
  date: string
  method: string
  scenarios: { bear: ScenarioRow; base: ScenarioRow; bull: ScenarioRow }
  myWeightedReturn: number
  upWeightedReturn: number
  myAsymmetry: number
  upAsymmetry: number
  verdict: string
}

/* ================================================================== */
/*  Helpers                                                            */
/* ================================================================== */

const pillarStatusMeta: Record<string, { label: string; color: string; bg: string; border: string }> = {
  on_track:   { label: '运转中', color: 'text-[#ADFF00]',   bg: 'bg-[#ADFF00]/10',   border: 'border-[#ADFF00]/30' },
  pending:    { label: '待验证', color: 'text-amber-400',    bg: 'bg-amber-400/10',    border: 'border-amber-400/30' },
  at_risk:    { label: '有风险', color: 'text-red-400',      bg: 'bg-red-400/10',      border: 'border-red-400/30' },
  verified:   { label: '已验证', color: 'text-emerald-400',  bg: 'bg-emerald-400/10',  border: 'border-emerald-400/30' },
}

const impactColors: Record<string, string> = {
  H: 'text-[#FF5C00] border-[#FF5C00]/40',
  M: 'text-amber-400 border-amber-400/30',
  L: 'text-muted-foreground border-white/10',
}

const tensionMeta: Record<string, { label: string; color: string; icon: string }> = {
  rising:    { label: '叙事强化', color: 'text-[#ADFF00]',   icon: '▲' },
  stable:    { label: '叙事稳定', color: 'text-amber-400',    icon: '▶' },
  easing:    { label: '叙事弱化', color: 'text-orange-400',   icon: '▼' },
  breaking:  { label: '叙事破裂', color: 'text-red-400',      icon: '✕' },
}

function fmtDate(d: string) {
  if (!d) return '--'
  const parts = d.split('-')
  if (parts.length === 2) return `${parts[0]}年${parts[1]}月`
  return d
}

function fmtDateTime(d: string) {
  if (!d) return '--'
  // ISO: "2026-05-29T10:00:00" → "5/29 10:00"
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (m) return `${parseInt(m[2])}/${parseInt(m[3])} ${m[4]}:${m[5]}`
  // fallback: just the date part
  return fmtDate(d)
}

function fmtNum(n: number, decimals = 1) {
  if (n == null) return '--'
  return n.toFixed(decimals)
}

/* ================================================================== */
/*  Sub-components                                                     */
/* ================================================================== */

function ConvictionRing({ value }: { value: number }) {
  const color = value >= 70 ? '#ADFF00' : value >= 40 ? '#C88D3A' : '#FF5C00'
  const radius = 28
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (value / 100) * circumference

  return (
    <div className="relative w-[72px] h-[72px] flex items-center justify-center shrink-0">
      <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
        <circle cx="36" cy="36" r={radius} fill="none" stroke={color} strokeWidth="5"
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
      </svg>
      <span className="text-base font-semibold" style={{ fontFamily: 'Space Mono, monospace' }}>{value}</span>
    </div>
  )
}

function TrackStatusBadge({ status }: { status: string }) {
  const meta: Record<string, { label: string; color: string; border: string; bg: string }> = {
    active:  { label: '跟踪中', color: 'text-[#ADFF00]', border: 'border-[#ADFF00]/30', bg: 'bg-[#ADFF00]/5' },
    paused:  { label: '已暂停', color: 'text-amber-400',  border: 'border-amber-400/30',  bg: 'bg-amber-400/5' },
  }
  const m = meta[status] ?? meta.active
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-sm font-medium border',
      m.color, m.border, m.bg
    )}>
      {status === 'active' ? <Activity size={12} /> : <AlertTriangle size={12} />}
      {m.label}
    </span>
  )
}

/* ================================================================== */
/*  Stock sidebar card                                                 */
/* ================================================================== */

function StockListItem({ stock, isSelected, onClick }: {
  stock: TrackingData; isSelected: boolean; onClick: () => void
}) {
  const isPaused = stock.track_status === 'paused'
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left p-4 border-b border-white/5 transition-colors',
        'hover:bg-white/[0.03] focus:outline-none',
        isSelected && 'bg-white/[0.05] border-l-2 border-l-[#ADFF00]',
        isPaused && 'opacity-50'
      )}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold">{stock.stockName}</span>
          <span className="text-sm text-muted-foreground font-mono">{stock.stockCode}</span>
          {isPaused && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400 border border-amber-400/20">已暂停</span>}
        </div>
        <TrackStatusBadge status={stock.track_status} />
      </div>
      <div className="flex items-center gap-2 mt-2">
        <div className="flex-1">
          <Progress value={stock.conviction} className="h-1.5 [&>div]:bg-[#ADFF00]" />
        </div>
        <span className="text-sm text-muted-foreground font-mono w-8 text-right">{stock.conviction}</span>
      </div>
      <div className="flex items-center justify-between mt-1.5">
        <span className="text-xs text-muted-foreground">{stock.decision}</span>
        <span className="text-xs text-muted-foreground">{stock.reviewSchedule.lastCheck}</span>
      </div>
    </button>
  )
}

/* ================================================================== */
/*  Pillar cards                                                       */
/* ================================================================== */

function PillarCard({ pillar }: { pillar: Pillar }) {
  const meta = pillarStatusMeta[pillar.status] ?? pillarStatusMeta.pending
  return (
    <div className={cn('border rounded-lg p-4', meta.border, meta.bg)}>
      <div className="flex items-start justify-between mb-2">
        <h4 className="text-base font-semibold leading-snug pr-4">{pillar.name}</h4>
        <span className={cn('text-xs px-2 py-0.5 rounded-full border whitespace-nowrap', meta.color, meta.border)}>
          {meta.label}
        </span>
      </div>
      <p className="text-sm text-muted-foreground mb-3 leading-relaxed">{pillar.expectation}</p>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>验证日: {pillar.verificationDate}</span>
        <span>检查: {pillar.lastChecked}</span>
      </div>
      {pillar.history.length > 0 && (
        <div className="mt-2 pt-2 border-t border-white/5">
          {pillar.history.slice(-1).map((h, i) => (
            <div key={i} className="text-xs text-muted-foreground">
              <span className="text-[#ADFF00]/70">{h.date}</span>: {h.actual}
              <span className={cn('ml-1', h.trend === 'up' ? 'text-emerald-400' : h.trend === 'down' ? 'text-red-400' : 'text-muted-foreground')}>
                ↑
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ================================================================== */
/*  Price chart panel                                                  */
/* ================================================================== */

function PriceChartPanel({ priceLog, basePrice, baseDate, baseMarketCap }: {
  priceLog: PriceLogEntry[]; basePrice: number; baseDate: string; baseMarketCap: number
}) {
  const chartData = useMemo(() => priceLog.map(p => ({
    ...p,
    label: p.date.slice(5), // MM-DD
  })), [priceLog])

  const latest = priceLog[priceLog.length - 1]
  const returnColor = (latest?.return_pct ?? 0) >= 0 ? 'text-[#ADFF00]' : 'text-red-400'

  return (
    <Card className="border-white/5 bg-[#050401]">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Activity size={14} className="text-[#ADFF00]" />
          灵气走势
        </CardTitle>
        <CardDescription className="text-sm">
          基准日 {baseDate} · 基准价 ¥{basePrice}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-4 gap-3 mb-4">
          <div className="text-center p-2 rounded bg-white/[0.02]">
            <div className="text-xs text-muted-foreground">最新价</div>
            <div className="text-base font-semibold font-mono">¥{fmtNum(latest?.price, 2)}</div>
          </div>
          <div className="text-center p-2 rounded bg-white/[0.02]">
            <div className="text-xs text-muted-foreground">累计收益</div>
            <div className={cn('text-base font-semibold font-mono', returnColor)}>
              {fmtNum(latest?.return_pct, 1)}%
            </div>
          </div>
          <div className="text-center p-2 rounded bg-white/[0.02]">
            <div className="text-xs text-muted-foreground">入选价</div>
            <div className="text-base font-semibold font-mono">¥{basePrice.toFixed(2)}</div>
          </div>
          <div className="text-center p-2 rounded bg-white/[0.02]">
            <div className="text-xs text-muted-foreground">入选市值</div>
            <div className="text-base font-semibold font-mono">{baseMarketCap.toFixed(0)}亿</div>
          </div>
        </div>

        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={chartData}>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fill: '#666', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis domain={['auto', 'auto']} tick={{ fill: '#666', fontSize: 10 }} axisLine={false} tickLine={false}
                tickFormatter={v => `¥${v}`} width={50}
              />
              <ReTooltip
                contentStyle={{
                  background: '#111', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px',
                  fontSize: '12px', fontFamily: 'Space Mono, monospace', color: '#F2F4F3'
                }}
                formatter={(v: number) => [`¥${v.toFixed(2)}`, '价格']}
                labelFormatter={(l: string) => `日期: ${l}`}
              />
              <ReferenceLine y={basePrice} stroke="rgba(173,255,0,0.2)" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="price" stroke="#ADFF00" strokeWidth={1.5}
                dot={{ r: 2, fill: '#ADFF00', strokeWidth: 0 }} activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[160px] flex items-center justify-center text-sm text-muted-foreground">
            数据不足，暂无走势图
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ================================================================== */
/*  Valuation comparison (身外化身 vs 定数录)                             */
/* ================================================================== */

const SCENARIO_COLORS = {
  bull:  { dot: 'bg-[#ADFF00]', border: 'border-[#ADFF00]/20', bg: 'bg-[#ADFF00]/[0.02]', label: '牛 Bull' },
  base:  { dot: 'bg-amber-400',  border: 'border-amber-400/20',  bg: 'bg-amber-400/[0.02]',  label: '基 Base' },
  bear:  { dot: 'bg-red-400',    border: 'border-red-400/20',    bg: 'bg-red-400/[0.02]',    label: '熊 Bear' },
}

function ValuationCompare({ vc, basePrice, baseMarketCap }: { vc: ValuationComparison; basePrice: number; baseMarketCap: number }) {
  return (
    <Card className="border-white/5 bg-[#050401]">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Activity size={14} className="text-[#C88D3A]" />
          估值推演对比
          <span className="text-xs text-muted-foreground font-normal">{vc.date}</span>
        </CardTitle>
        <CardDescription className="text-xs">{vc.method}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 三情景 —— 每情景一行 */}
        {(['bear', 'base', 'bull'] as const).map(scenario => {
          const s = vc.scenarios[scenario]
          const c = SCENARIO_COLORS[scenario]
          const returnColor = s.myReturn >= 0 ? 'text-[#ADFF00]' : 'text-red-400'
          const upReturnColor = s.upReturn >= 0 ? 'text-[#ADFF00]/60' : 'text-red-400/60'
          return (
            <div key={scenario} className={cn('rounded-lg border p-3', c.border, c.bg)}>
              {/* 情景标签 + 涨跌幅 + 目标市值/价 */}
              <div className="flex items-center gap-2 mb-2">
                <span className={cn('w-2 h-2 rounded-full', c.dot)} />
                <span className="text-sm font-semibold">{c.label}</span>
                <span className="flex-1" />
                <span className={cn('text-sm font-mono font-semibold', returnColor)}>
                  {s.myReturn >= 0 ? '+' : ''}{s.myReturn.toFixed(1)}%
                </span>
                <span className="text-xs text-muted-foreground">化身</span>
              </div>

              {/* 目标市值 + 目标价 */}
              <div className="flex items-center gap-3 text-xs mb-2">
                {/* 化身 */}
                <div className="flex-1">
                  <span className="text-muted-foreground">市值 </span>
                  <span className="font-mono text-[#ADFF00]/80">
                    {(baseMarketCap * (1 + s.myReturn / 100)).toFixed(0)}亿
                  </span>
                  <span className="text-muted-foreground ml-2">价 </span>
                  <span className="font-mono text-[#ADFF00]/80">
                    ¥{(basePrice * (1 + s.myReturn / 100)).toFixed(1)}
                  </span>
                </div>
                {/* 定数录 */}
                <div className="flex-1 text-muted-foreground/60">
                  <span className="text-muted-foreground/50">定数录 </span>
                  <span className="font-mono">
                    {(baseMarketCap * (1 + s.upReturn / 100)).toFixed(0)}亿
                  </span>
                  <span className="ml-1">
                    ¥{(basePrice * (1 + s.upReturn / 100)).toFixed(1)}
                  </span>
                </div>
              </div>

              {/* CAGR + PS 对比条 */}
              <div className="flex items-center gap-3 text-xs">
                <div className="flex items-center gap-1">
                  <span className="text-muted-foreground">CAGR</span>
                  <span className="font-mono text-[#ADFF00]/80">{s.myCAGR.toFixed(0)}%</span>
                  <span className="text-muted-foreground/40">·</span>
                  <span className="font-mono text-muted-foreground/60">{s.upCAGR.toFixed(0)}%</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-muted-foreground">PS</span>
                  <span className="font-mono text-[#ADFF00]/80">{s.myPS.toFixed(0)}x</span>
                  <span className="text-muted-foreground/40">·</span>
                  <span className="font-mono text-muted-foreground/60">{s.upPS.toFixed(0)}x</span>
                </div>
              </div>
            </div>
          )
        })}

        {/* 汇总行 */}
        <div className="flex items-center gap-4 p-2 rounded bg-white/[0.02] text-xs">
          <div className="flex items-center gap-1">
            <span className="text-muted-foreground">概率加权</span>
            <span className="font-mono text-[#ADFF00]">{vc.myWeightedReturn.toFixed(1)}%</span>
            <span className="text-muted-foreground/40">vs</span>
            <span className="font-mono text-muted-foreground">{vc.upWeightedReturn.toFixed(1)}%</span>
          </div>
          <span className="text-muted-foreground/20">|</span>
          <div className="flex items-center gap-1">
            <span className="text-muted-foreground">不对称</span>
            <span className="font-mono text-[#ADFF00]">{vc.myAsymmetry.toFixed(1)}x</span>
            <span className="text-muted-foreground/40">vs</span>
            <span className="font-mono text-muted-foreground">{vc.upAsymmetry.toFixed(1)}x</span>
          </div>
          <span className="flex-1" />
          <span className="text-muted-foreground/50">
            {vc.myWeightedReturn < vc.upWeightedReturn ? '↓ 更保守' : '↑ 更乐观'}
          </span>
        </div>

        {/* 裁决 */}
        {vc.verdict && (
          <div className="p-2 rounded border border-[#C88D3A]/10 bg-[#C88D3A]/[0.02]">
            <div className="text-xs text-muted-foreground leading-relaxed">{vc.verdict}</div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ================================================================== */
/*  Thesis timeline (叙事演进)                                          */
/* ================================================================== */

function ThesisTimeline({ thesisLog }: { thesisLog: ThesisVersion[] }) {
  const [expanded, setExpanded] = useState(false)
  const latest = thesisLog[thesisLog.length - 1]
  const hasHistory = thesisLog.length > 1

  return (
    <Card className="border-white/5 bg-[#050401]">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Target size={14} className="text-[#C88D3A]" />
            投资论点
          </CardTitle>
          {hasHistory && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-xs text-muted-foreground hover:text-[#ADFF00] transition-colors"
            >
              {expanded ? '收起演进史' : `展开演进史 (${thesisLog.length}版)`}
            </button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {/* ---- 当前版本 ---- */}
        <div className="mb-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#ADFF00]/10 text-[#ADFF00] font-mono">v{latest.version}</span>
            <span className="text-[10px] text-muted-foreground font-mono">{fmtDateTime(latest.date)}</span>
            <span className={cn('text-xs flex items-center gap-1', tensionMeta[latest.narrativeTension]?.color)}>
              {tensionMeta[latest.narrativeTension]?.icon} {tensionMeta[latest.narrativeTension]?.label}
            </span>
            {latest.delta !== '0' && (
              <span className={cn('text-xs font-mono', latest.delta.startsWith('+') ? 'text-[#ADFF00]' : 'text-red-400')}>
                Conviction {latest.delta}
              </span>
            )}
          </div>
          <p className="text-base leading-relaxed text-muted-foreground">{latest.thesis}</p>
        </div>

        {/* ---- 最新原委 ---- */}
        {latest.narrative && (
          <div className="p-3 rounded-lg border border-white/5 bg-white/[0.02] mb-3">
            <div className="text-xs text-muted-foreground mb-1">触发事件</div>
            <p className="text-sm mb-2">{latest.trigger}</p>
            <div className="text-xs text-muted-foreground mb-1">原委</div>
            <p className="text-sm text-muted-foreground/80 leading-relaxed">{latest.narrative}</p>
          </div>
        )}

        {/* ---- 假设追踪 ---- */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-3">
          {latest.verifiedAssumptions.length > 0 && (
            <div className="p-2 rounded bg-emerald-400/5 border border-emerald-400/15">
              <div className="text-[11px] text-emerald-400/70 mb-1">✓ 已验证假设</div>
              {latest.verifiedAssumptions.map((a, i) => (
                <div key={i} className="text-xs text-emerald-400/80">· {a}</div>
              ))}
            </div>
          )}
          {latest.invalidatedAssumptions.length > 0 && (
            <div className="p-2 rounded bg-red-400/5 border border-red-400/15">
              <div className="text-[11px] text-red-400/70 mb-1">✕ 被推翻假设</div>
              {latest.invalidatedAssumptions.map((a, i) => (
                <div key={i} className="text-xs text-red-400/80">· {a}</div>
              ))}
            </div>
          )}
          {latest.newUnknowns.length > 0 && (
            <div className="p-2 rounded bg-amber-400/5 border border-amber-400/15">
              <div className="text-[11px] text-amber-400/70 mb-1">? 新未知数</div>
              {latest.newUnknowns.map((a, i) => (
                <div key={i} className="text-xs text-amber-400/80">· {a}</div>
              ))}
            </div>
          )}
        </div>

        {/* ---- 演进历史 ---- */}
        {expanded && hasHistory && (
          <div className="relative pl-5 border-l border-white/10 space-y-4 mt-4 pt-2">
            {thesisLog.slice().reverse().map((v, i) => (
              <div key={v.version} className="relative">
                <div className="absolute -left-[21px] top-1 w-2 h-2 rounded-full border border-[#C88D3A]/50 bg-[#C88D3A]/20" />
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-[#C88D3A]">v{v.version}</span>
                  <span className="text-[10px] text-muted-foreground font-mono">{fmtDateTime(v.date)}</span>
                  <span className="text-xs font-mono text-muted-foreground">Conviction: {v.conviction}</span>
                  <span className={cn('text-xs', tensionMeta[v.narrativeTension]?.color)}>
                    {tensionMeta[v.narrativeTension]?.icon}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground/80 mb-1">{v.thesis}</p>
                {v.trigger && <p className="text-xs text-muted-foreground/60">触发: {v.trigger}</p>}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ================================================================== */
/*  Catalyst timeline                                                  */
/* ================================================================== */

function CatalystTimeline({ events }: { events: CatalystEvent[] }) {
  const upcoming = events.filter(e => e.date >= '2026-05-23').sort((a, b) => a.date.localeCompare(b.date))
  if (upcoming.length === 0) return null

  return (
    <Card className="border-white/5 bg-[#050401]">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Zap size={14} className="text-[#FF5C00]" />
          催化剂日历
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="relative pl-5 border-l border-white/10 space-y-4">
          {upcoming.map((ev, i) => (
            <div key={i} className="relative">
              <div className={cn(
                'absolute -left-[21px] top-0.5 w-2.5 h-2.5 rounded-full border-2',
                ev.impact === 'H' ? 'bg-[#FF5C00]/30 border-[#FF5C00]' :
                ev.impact === 'M' ? 'bg-amber-400/30 border-amber-400' :
                'bg-white/10 border-white/20'
              )} />
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-sm font-mono text-muted-foreground">{fmtDate(ev.date)}</span>
                <Badge variant="outline" className={cn('text-[11px] px-1.5 py-0 h-4', impactColors[ev.impact])}>
                  {ev.impact === 'H' ? '重大' : ev.impact === 'M' ? '中等' : '轻微'}
                </Badge>
                {ev.sourceLevel && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className={cn(
                        'text-[10px] px-1 py-0 rounded cursor-help',
                        ev.sourceLevel === 'L5' ? 'bg-emerald-400/15 text-emerald-400' :
                        ev.sourceLevel === 'L4' ? 'bg-amber-400/15 text-amber-400' :
                        ev.sourceLevel === 'L3' ? 'bg-orange-400/15 text-orange-400' :
                        'bg-red-400/15 text-red-400'
                      )}>{ev.sourceLevel}</span>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-[260px] text-xs">
                      {ev.sourceDetail && <p className="text-muted-foreground">{ev.sourceDetail}</p>}
                      {ev.sourceNote && <p className="text-amber-400/80 mt-0.5">{ev.sourceNote}</p>}
                    </TooltipContent>
                  </Tooltip>
                )}
                <span className="text-[11px] text-muted-foreground">{ev.type}</span>
                {ev.status && (
                  <span className={cn(
                    'text-[10px]',
                    ev.status === 'triggered' ? 'text-[#ADFF00]' :
                    ev.status === 'missed' ? 'text-red-400' :
                    ev.status === 'verified' ? 'text-emerald-400' : 'text-muted-foreground'
                  )}>
                    {ev.status === 'triggered' ? '▶已触发' : ev.status === 'missed' ? '✗已错过' : ev.status === 'verified' ? '✓已验证' : ''}
                  </span>
                )}
              </div>
              <p className="text-base font-medium">{ev.event}</p>
              <div className="flex gap-3 mt-1 text-xs">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="text-emerald-400/70 cursor-help">🐂 {ev.bull}</span>
                  </TooltipTrigger>
                  <TooltipContent>看多情景</TooltipContent>
                </Tooltip>
                {ev.bear && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="text-red-400/70 cursor-help">🐻 {ev.bear}</span>
                    </TooltipTrigger>
                    <TooltipContent>看空情景</TooltipContent>
                  </Tooltip>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/* ================================================================== */
/*  A-share monitoring checks                                          */
/* ================================================================== */

function ASharePanel({ checks }: { checks: AShareChecks }) {
  const items = [
    { key: 'pledgeCheck', label: '股权质押', icon: Shield, data: checks.pledgeCheck },
    { key: 'unlockCheck', label: '解禁检查', icon: Unlock, data: checks.unlockCheck },
    { key: 'marginCheck', label: '融资融券', icon: Coins, data: checks.marginCheck },
    { key: 'insiderTrading', label: '内部交易', icon: Building2, data: checks.insiderTrading },
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {items.map(({ key, label, icon: Icon, data }) => (
        <div key={key} className="flex items-start gap-3 p-3 rounded-lg border border-white/5 bg-[#050401]">
          <Icon size={16} className="text-muted-foreground mt-0.5 shrink-0" />
          <div className="min-w-0">
            <div className="text-sm text-muted-foreground mb-0.5">{label}</div>
            <div className="text-sm font-medium truncate">{data.result}</div>
            <div className="text-[11px] text-muted-foreground mt-1">{data.lastChecked}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

/* ================================================================== */
/*  Main component                                                     */
/* ================================================================== */

export default function Tracking() {
  const mobile = useMobile()
  const [navHeight, setNavHeight] = useState(64)
  const [stocks, setStocks] = useState<TrackingData[]>([])

  useEffect(() => {
    const nav = document.querySelector('nav')
    if (nav) setNavHeight(nav.offsetHeight)
  }, [])
  const [selected, setSelected] = useState<TrackingData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/tracking')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((data: TrackingData[]) => {
        setStocks(data)
        if (data.length > 0) setSelected(data[0])
        setLoading(false)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  const selectedStock = selected

  return (
    <div style={{ display: 'flex', flexDirection: mobile ? 'column' : 'row', height: `calc(100vh - ${navHeight}px)`, background: '#050401', color: '#F2F4F3' }}>
      {/* ================================================================ */}
      {/*  Sidebar — Stock List                                             */}
      {/* ================================================================ */}
      <aside style={{
        width: mobile ? '100%' : '320px', height: mobile ? '200px' : '100%',
        flexShrink: 0, borderRight: mobile ? 'none' : '1px solid rgba(255,255,255,0.05)',
        borderBottom: mobile ? '1px solid rgba(255,255,255,0.05)' : 'none',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        minHeight: mobile ? 0 : undefined,
      }}>
        <div className="p-5 border-b border-white/5">
          <h2 className="text-base font-semibold flex items-center gap-2" style={{ fontFamily: 'Geist Pixel, monospace' }}>
            <Target size={15} className="text-[#ADFF00]" />
            追踪令
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            {loading ? '加载中...' : `${stocks.length} 只标的追踪中`}
          </p>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-5 h-5 border-2 border-[#ADFF00]/30 border-t-[#ADFF00] rounded-full animate-spin" />
              <span className="text-sm text-muted-foreground">神识扫描中...</span>
            </div>
          </div>
        ) : error ? (
          <div className="flex-1 flex items-center justify-center p-5">
            <div className="text-center">
              <AlertTriangle size={24} className="text-[#FF5C00] mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">灵气紊乱，无法连接追踪阵</p>
              <p className="text-xs text-red-400/70 mt-1">{error}</p>
            </div>
          </div>
        ) : stocks.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-5">
            <div className="text-center">
              <div className="text-3xl mb-3 opacity-20">☷</div>
              <p className="text-sm text-muted-foreground">尚无追踪标的</p>
              <p className="text-xs text-muted-foreground/50 mt-1">待身外化身开启猎杀后，追踪令将自动显现</p>
            </div>
          </div>
        ) : (
          <ScrollArea className="flex-1" style={{ minHeight: 0 }}>
            {stocks.filter(s => s.track_status !== 'paused').map(s => (
              <StockListItem
                key={s.stockCode}
                stock={s}
                isSelected={selectedStock?.stockCode === s.stockCode}
                onClick={() => setSelected(s)}
              />
            ))}
          </ScrollArea>
        )}
      </aside>

      {/* ================================================================ */}
      {/*  Main — Detail View                                               */}
      {/* ================================================================ */}
      <main className="flex-1 flex flex-col" style={{ overflow: 'hidden', minHeight: 0 }}>
        {!selectedStock ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-5xl mb-4 opacity-10">☰</div>
              <p className="text-base text-muted-foreground">择一追踪令以观其势</p>
            </div>
          </div>
        ) : (
          <ScrollArea className="flex-1" style={{ minHeight: 0 }}>
            <div className="p-6 space-y-5 max-w-4xl">
              {/* ---- 概览头部 ---- */}
              <div className="flex items-start justify-between flex-wrap gap-4">
                <div className="flex items-start gap-4">
                  <ConvictionRing value={selectedStock.conviction} />
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h1 className="text-2xl font-semibold">{selectedStock.stockName}</h1>
                      <span className="text-base font-mono text-muted-foreground">{selectedStock.stockCode}</span>
                      <TrackStatusBadge status={selectedStock.track_status} />
                      <button
                        onClick={async () => {
                          const next = selectedStock.track_status === 'active' ? 'paused' : 'active'
                          try {
                            const res = await fetch(`/api/tracking/${selectedStock.stockCode}/status`, {
                              method: 'PATCH',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ track_status: next }),
                            })
                            if (res.ok) {
                              const updated = { ...selectedStock, track_status: next }
                              setSelected(updated)
                              setStocks(prev => prev.map(s => s.stockCode === selectedStock.stockCode ? updated : s))
                            }
                          } catch { /* ignore */ }
                        }}
                        className="text-xs text-muted-foreground hover:text-[#ADFF00] transition-colors px-1.5 py-0.5 rounded border border-white/10 hover:border-[#ADFF00]/30"
                        title="切换跟踪状态"
                      >
                        ⇄
                      </button>
                    </div>
                    <div className="flex items-center gap-3 text-sm text-muted-foreground mb-2">
                      <span>决议: {selectedStock.decisionDate}</span>
                      <span className="text-[#ADFF00]">{selectedStock.decision}</span>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                      <span className="text-muted-foreground">
                        建议仓位 <span className="text-[#ADFF00] font-mono">{selectedStock.recommendedPosition}%</span>
                      </span>
                      <span className="text-muted-foreground">
                        实际仓位 <span className="font-mono">{selectedStock.actualPosition}%</span>
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* ---- 入场条件 ---- */}
              {selectedStock.entryCondition && (
                <div className="p-4 rounded-lg border border-[#ADFF00]/20 bg-[#ADFF00]/[0.02]">
                  <div className="text-xs text-muted-foreground mb-1">入场条件</div>
                  <p className="text-base">{selectedStock.entryCondition}</p>
                </div>
              )}

              {/* ---- 核心论点 (叙事演进) ---- */}
              <ThesisTimeline thesisLog={selectedStock.thesisLog || [{
                version: 1,
                date: selectedStock.decisionDate,
                thesis: selectedStock.thesis,
                conviction: selectedStock.conviction,
                delta: '0',
                trigger: '建档',
                narrative: '',
                verifiedAssumptions: [],
                invalidatedAssumptions: [],
                newUnknowns: [],
                narrativeTension: 'stable' as const
              }]} />

              {/* ---- 四大支柱 ---- */}
              <div>
                <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-2">
                  <Activity size={13} className="text-[#ADFF00]" />
                  论点支柱验证
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {selectedStock.pillars.map((p, i) => (
                    <PillarCard key={i} pillar={p} />
                  ))}
                </div>
              </div>

              {/* ---- 价格走势 ---- */}
              <PriceChartPanel
                priceLog={selectedStock.priceLog}
                basePrice={selectedStock.basePrice}
                baseDate={selectedStock.baseDate}
                baseMarketCap={selectedStock.baseMarketCap}
              />

              {/* ---- 估值对比 ---- */}
              {selectedStock.valuationComparison && (
                <ValuationCompare vc={selectedStock.valuationComparison} basePrice={selectedStock.basePrice} baseMarketCap={selectedStock.baseMarketCap} />
              )}

              {/* ---- 催化剂日历 ---- */}
              <CatalystTimeline events={selectedStock.catalystCalendar} />

              {/* ---- 风险矩阵 ---- */}
              {selectedStock.risks.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-2">
                    <AlertTriangle size={13} className="text-[#FF5C00]" />
                    风险矩阵
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {selectedStock.risks.map((r, i) => (
                      <div key={i} className="p-3 rounded-lg border border-white/5 bg-[#050401]">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-base font-medium">{r.name}</span>
                          <div className="flex items-center gap-1.5">
                            {r.probability && (
                              <span className="text-[11px] px-1.5 py-0.5 rounded bg-white/5 text-muted-foreground">
                                概率: {r.probability}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="text-sm text-muted-foreground mb-1.5">
                          <span className="text-red-400/70">影响: {r.impact}</span>
                        </div>
                        <p className="text-xs text-muted-foreground/70 leading-relaxed">
                          监控: {r.monitoring}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ---- 退出条件 ---- */}
              {selectedStock.exitConditions.length > 0 && (
                <Card className="border-white/5 bg-[#050401]">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base font-semibold flex items-center gap-2">
                      <X size={14} className="text-red-400" />
                      退出条件
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-1.5">
                      {selectedStock.exitConditions.map((c, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
                          <span className="text-red-400/60 mt-0.5 shrink-0">▪</span>
                          {c}
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              )}

              {/* ---- A股监测 ---- */}
              <div>
                <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-2">
                  <Shield size={13} className="text-[#C88D3A]" />
                  A股异动监测
                </h3>
                <ASharePanel checks={selectedStock.aShareTracking} />
              </div>

              {/* ---- 审查周期 ---- */}
              <Card className="border-white/5 bg-[#050401]">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base font-semibold flex items-center gap-2">
                    <Calendar size={14} className="text-muted-foreground" />
                    审查周期
                    {selectedStock.reviewSchedule.patrolFrequency && (
                      <span className="text-xs text-[#ADFF00]/70 font-normal ml-auto">
                        {selectedStock.reviewSchedule.patrolFrequency}
                      </span>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                      <div className="text-xs text-muted-foreground">上次检查</div>
                      <div className="text-sm font-mono">{selectedStock.reviewSchedule.lastCheck}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">下次检查</div>
                      <div className="text-sm font-mono text-amber-400">{selectedStock.reviewSchedule.nextQuickCheck}</div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">全面复审</div>
                      <div className="text-sm font-mono text-[#ADFF00]">{selectedStock.reviewSchedule.nextFullReview}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Spacer for scroll comfort */}
              <div className="h-8" />
            </div>
          </ScrollArea>
        )}
      </main>
    </div>
  )
}
