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
