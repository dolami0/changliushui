/* ------------------------------------------------------------------ */
/*  身外化身 记忆 API — 前端数据通道                                    */
/*  通过后端 (port 8081) 读写 .agents/agents/shenwaihuashen/memory/   */
/* ------------------------------------------------------------------ */

const BASE = '/api/avatar/memory';

export interface LingGuangItem {
  id: string;
  title: string;
  content: string;
  tags: string[];
  source: string;
  confidence: number;
  revisionHistory: Array<{ version: number; date: string; change: string }>;
  createdAt: string;
  updatedAt: string;
}

export interface CaseSummary {
  id: string;
  stockName: string;
  stockCode: string;
  sector: string;
  gainMultiple: string;
  totalReturn?: number;
  returnType?: string;
  logic: string;
  keySignals: string[];
  tags: string[];
  decagenomeTags?: string[];
  catalyst?: string;
  primaryDriver?: string;
  dominantFactor?: string;
  expectationGap?: string;
  endState?: string;
  t2xMonths?: number;
  roicImprovement?: number;
  peExpansion?: number;
  maxDrawdownPct?: number;
  actualReturnPct?: number;
  startDate?: string;
  peakDate?: string;
  createdAt: string;
  updatedAt: string;
}

export interface TrackingItem {
  stockCode: string;
  stockName: string;
  status: 'active' | 'exited' | 'watching';
  decisionCycle: {
    initialDecisionDate: string;
    decision: string;
    convictionScore: number;
    suggestedPosition: number;
    decisionBasis: string;
    keyAssumptions: string[];
    entryPriceRef: number;
    targetPriceRef: number;
  };
  priceTracking: Array<{ date: string; price: number; returnPct: number; note: string }>;
  eventTracking: Array<{ date: string; event: string; expected: string; actual: string; impact: string }>;
  assumptionValidation: Array<{ assumption: string; status: string; evidence: string; date: string }>;
  reassessmentNotes: Array<{ date: string; note: string }>;
  exitConditions: Array<{ condition: string; triggered: boolean }>;
  feedbackLoop: {
    lastReviewDate: string;
    nextReviewDate: string;
    decisionQuality: string | null;
  };
  createdAt: string;
  updatedAt: string;
}

export interface MemoryIndex {
  version: number;
  lastUpdated: string;
  lingguangCount: number;
  caseCount: number;
  trackingCount: number;
  lingguangIndex: Record<string, { title: string; tags: string[]; updatedAt: string }>;
  caseIndex: Record<string, { stockName: string; stockCode: string; sector: string; gainMultiple: string; returnType: string; tags: string[] }>;
  trackingIndex: Record<string, { stockName: string; status: string; lastUpdated: string }>;
}

export async function fetchMemoryIndex(): Promise<MemoryIndex> {
  const resp = await fetch(`${BASE}/index`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchLingGuangList(): Promise<LingGuangItem[]> {
  const resp = await fetch(`${BASE}/lingguang`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function saveLingGuang(slug: string, data: Partial<LingGuangItem>): Promise<{ ok: boolean }> {
  const resp = await fetch(`${BASE}/lingguang/${slug}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return resp.json();
}

export async function deleteLingGuang(slug: string): Promise<{ ok: boolean }> {
  const resp = await fetch(`${BASE}/lingguang/${slug}`, {
    method: 'DELETE',
  });
  return resp.json();
}

export async function fetchCaseList(): Promise<CaseSummary[]> {
  const resp = await fetch(`${BASE}/cases`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchCaseDetail(slug: string): Promise<CaseSummary> {
  const resp = await fetch(`${BASE}/cases/${slug}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function saveCase(slug: string, data: Partial<CaseSummary>): Promise<{ ok: boolean }> {
  const resp = await fetch(`${BASE}/cases/${slug}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return resp.json();
}

export async function fetchTrackingList(): Promise<TrackingItem[]> {
  const resp = await fetch(`${BASE}/tracking`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchTrackingDetail(ticker: string): Promise<TrackingItem> {
  const resp = await fetch(`${BASE}/tracking/${ticker}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function saveTracking(ticker: string, data: Partial<TrackingItem>): Promise<{ ok: boolean }> {
  const resp = await fetch(`${BASE}/tracking/${ticker}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return resp.json();
}
