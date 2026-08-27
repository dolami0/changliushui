import { useState, useEffect, useMemo } from 'react'
import { Target, Shield, Calendar, AlertTriangle, Activity, X, Zap, Building2, Unlock, Coins, Pause, Play } from 'lucide-react'
import { useMobile } from '@/hooks/useMobile'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { fetchTracking, updateTrackStatus } from '@/services/cozeApi'
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
  id: string
  stockCode: string
  stockName: string
  trackStatus: 'active' | 'paused' | 'hidden'
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
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
  if (m) return `${parseInt(m[2])}/${parseInt(m[3])} ${m[4]}:${m[5]}`
  return fmtDate(d)
}

function fmtNum(n: number, decimals = 1) {
  if (n == null) return '--'
  return n.toFixed(decimals)
}
