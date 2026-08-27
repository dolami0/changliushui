export type ViewKey = 'tracking' | 'archive' | 'fengwen' | 'avatar' | 'config';

export type SignalGrade = 'S' | 'A' | 'B' | 'C' | 'D';
export type PillarStatus = 'pending' | 'on_track' | 'at_risk' | 'verified';
export type AlertLevel = 'high' | 'mid' | 'ok';

export interface Pillar {
  name: string;
  score: number;
  status: PillarStatus;
}

export interface Catalyst {
  date: string;
  name: string;
  countdown?: string;
  status?: 'pending' | 'verified';
  done?: boolean;
}

export interface AlertItem {
  text: string;
  level: AlertLevel;
  time: string;
}

export interface NoteItem {
  date: string;
  kind: string;
  text: string;
}

export interface Thesis {
  version: number;
  statement: string;
}

export interface TrackingStock {
  code: string;
  name: string;
  price: number;
  chgPct: string;
  up: boolean;
  signal: SignalGrade;
  signalText: string;
  signalMeta: string;
  health: [number, number, number];
  retPct: string;
  bear: number;
  base: number;
  bull: number;
  pointerPct: number;
  convergence: string;
  zone: string;
  upside: string;
  posPct: string;
  entryZone: string;
  stopLoss: string;
  target: string;
  tags: string[];
  pillars: Pillar[];
  catalysts: Catalyst[];
  marketValue: string;
  drawdown: string;
  syncStatus: string;
  spark: number[];
  alerts: AlertItem[];
  notes: NoteItem[];
  thesis: Thesis;
}

export interface PortfolioSummary {
  totalCapital: string;
  marketValueCash: string;
  totalReturn: string;
  maxDrawdown: string;
  macroNote: string;
}

export type AvatarVerdict = 'pass' | 'cond' | 'none';

export interface ReportCard {
  id: string;
  name: string;
  code: string;
  upside: string;
  model: string;
  industry: string;
  date: string;
  verdict: AvatarVerdict;
  verdictText: string;
}

export interface ProseParagraph {
  lead: string;
  text: string;
}

export interface ReportDetail extends ReportCard {
  meta: string;
  bear: number;
  base: number;
  bull: number;
  pointerPct: number;
  probs: string;
  thesisParas: ProseParagraph[];
  catalysts: Catalyst[];
  avatarScores: [number, number, number, number];
  avatarNote: string;
  verifyItems: string[];
}

export interface Corpus {
  stockName: string;
  stockCode: string;
  eventNote: string;
  dims: string[];
  paras: ProseParagraph[];
}

export interface ChainNode {
  stage: string;
  name: string;
  desc: string;
  score: number;
  tone: 'azure' | 'gold' | 'mute';
  hot?: boolean;
}

export interface ChainCandidate {
  name: string;
  code: string;
  node: string;
  odds: string;
  oddsTone: 'gold' | 'azure' | 'dim';
  verdict: string;
  verdictCls: 'st-verified' | 'st-ontrack' | 'st-atrisk';
  status: string;
}

export interface ChainFlow {
  title: string;
  nodes: ChainNode[];
  candidates: ChainCandidate[];
}

export type FengwenStatus = 'queue' | 'run' | 'done' | 'drop';

export interface FengwenItem {
  id: string;
  text: string;
  source: string;
  modeNote: string;
  dateNote: string;
  statusNote: string;
  status: FengwenStatus;
}

export interface FengwenInput {
  content: string;
  stock?: string;
  source: string;
  level: number;
}

export interface AvatarReview {
  code: string;
  name: string;
  verdict: AvatarVerdict;
  verdictText: string;
  meta: string;
  scores: [number, number, number, number] | null;
  conclusion: ProseParagraph[];
  redline: string;
  records: { date: string; kind: string; text: string }[];
}

export interface NotificationItem {
  id: string;
  icon: string;
  iconBg: string;
  title: string;
  stockName?: string;
  sub: string;
  view: ViewKey;
}

export interface AppConfig {
  schedulerOn: boolean;
  dailyInspectOn: boolean;
  keyStatus: string;
  lockGuard: string;
  totalCapital: string;
  macroStance: '紧' | '中性' | '宽';
  notifyUiOn: boolean;
  notifyWebhookOn: boolean;
  promptVersion: string;
  errorDist: string;
  tokenUsage: string;
  p95Latency: string;
  proposals: { id: string; text: string; note?: string; state: 'pending' | 'gray' }[];
}

export type DecisionType = 'pass' | 'cond' | 'reject';
