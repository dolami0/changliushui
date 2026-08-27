// 身外化身 记忆 API — Coze 直连, 零后端
import { fetchLingguang, saveLingguang as cozeSaveLingguang, deleteLingguang as cozeDeleteLingguang, fetchCases, saveCase as cozeSaveCase, fetchTracking, type LingguangItem as CozeLingguang, type CaseItem as CozeCase, type TrackingItem as CozeTrackingItem } from './cozeApi';
export { updateTrackStatus } from './cozeApi';

export interface LingGuangItem {
  id: string; title: string; content: string; tags: string[]; source: string;
  confidence: number; revisionHistory: Array<{ version: number; date: string; change: string }>;
  createdAt: string; updatedAt: string;
}

export interface CaseSummary {
  id: string; stockName: string; stockCode: string; sector: string;
  gainMultiple: string; totalReturn?: number; returnType?: string;
  logic: string; keySignals: string[]; tags: string[];
  decagenomeTags?: string[]; catalyst?: string; primaryDriver?: string;
  dominantFactor?: string; expectationGap?: string; endState?: string;
  t2xMonths?: number; roicImprovement?: number; peExpansion?: number;
  maxDrawdownPct?: number; actualReturnPct?: number;
  startDate?: string; peakDate?: string; createdAt: string; updatedAt: string;
}

export interface TrackingItem {
  stockCode: string; stockName: string; status: 'active' | 'exited' | 'watching';
  decisionCycle: { initialDecisionDate: string; decision: string; convictionScore: number; suggestedPosition: number; decisionBasis: string; keyAssumptions: string[]; entryPriceRef: number; targetPriceRef: number };
  priceTracking: Array<{ date: string; price: number; returnPct: number; note: string }>;
  eventTracking: Array<{ date: string; event: string; expected: string; actual: string; impact: string }>;
  assumptionValidation: Array<{ assumption: string; status: string; evidence: string; date: string }>;
  reassessmentNotes: Array<{ date: string; note: string }>;
  exitConditions: Array<{ condition: string; triggered: boolean }>;
  feedbackLoop: { lastReviewDate: string; nextReviewDate: string; decisionQuality: string | null };
  createdAt: string; updatedAt: string;
}

export interface MemoryIndex {
  version: number; lastUpdated: string; lingguangCount: number; caseCount: number; trackingCount: number;
  lingguangIndex: Record<string, { title: string; tags: string[]; updatedAt: string }>;
  caseIndex: Record<string, { stockName: string; stockCode: string; sector: string; gainMultiple: string; returnType: string; tags: string[] }>;
  trackingIndex: Record<string, { stockName: string; status: string; lastUpdated: string }>;
}

function adaptLingguang(c: CozeLingguang): LingGuangItem {
  return { ...c, revisionHistory: c.revisionHistory as LingGuangItem['revisionHistory'] };
}
function adaptCase(c: CozeCase, id: string): CaseSummary {
  return { id, stockName: c.stockName, stockCode: c.stockCode, sector: c.sector, gainMultiple: c.gainMultiple, returnType: c.returnType, logic: c.logic, keySignals: [], tags: c.tags, catalyst: c.catalyst, primaryDriver: c.primaryDriver, endState: c.endState, roicImprovement: c.roicImprovement, peExpansion: c.peExpansion, maxDrawdownPct: c.maxDrawdownPct, actualReturnPct: c.actualReturnPct, createdAt: '', updatedAt: '' };
}
function adaptTracking(r: CozeTrackingItem): TrackingItem {
  return {
    stockCode: r.stockCode, stockName: r.stockName, status: r.trackStatus === 'paused' ? 'watching' : 'active',
    decisionCycle: { initialDecisionDate: r.decisionDate || '', decision: r.decision || '', convictionScore: r.conviction || 0, suggestedPosition: r.recommendedPosition || 0, decisionBasis: r.thesis || '', keyAssumptions: [], entryPriceRef: r.basePrice || 0, targetPriceRef: 0 },
    priceTracking: [], eventTracking: [], assumptionValidation: [], reassessmentNotes: [], exitConditions: [],
    feedbackLoop: { lastReviewDate: '', nextReviewDate: '', decisionQuality: null },
    createdAt: r.createdAt || '', updatedAt: r.updatedAt || '',
  };
}

export async function fetchMemoryIndex(): Promise<MemoryIndex> {
  const [lg, cs, tr] = await Promise.all([fetchLingguang(), fetchCases(), fetchTracking()]);
  return {
    version: 1, lastUpdated: new Date().toISOString(),
    lingguangCount: lg.length, caseCount: cs.length, trackingCount: tr.length,
    lingguangIndex: Object.fromEntries(lg.map((l) => [l.id, { title: l.title, tags: l.tags, updatedAt: l.updatedAt }])),
    caseIndex: Object.fromEntries(cs.map((c) => [`case-${c.stockCode}`, { stockName: c.stockName, stockCode: c.stockCode, sector: c.sector, gainMultiple: c.gainMultiple, returnType: c.returnType, tags: c.tags }])),
    trackingIndex: Object.fromEntries(tr.map((t) => [t.stockCode as string, { stockName: t.stockName as string, status: 'active', lastUpdated: t.updatedAt as string }])),
  };
}

export async function fetchLingGuangList(): Promise<LingGuangItem[]> {
  return (await fetchLingguang()).map(adaptLingguang);
}

export async function saveLingGuang(slug: string, data: Partial<LingGuangItem>): Promise<{ ok: boolean }> {
  const existing = await fetchLingguang();
  const item = existing.find((l) => l.id === slug);
  const merged = { ...(item ?? { id: slug, title: '', content: '', tags: [], source: '', confidence: 0, revisionHistory: [], createdAt: '', updatedAt: '' }), ...data, id: slug };
  const ok = await cozeSaveLingguang(merged as CozeLingguang);
  return { ok };
}

export async function deleteLingGuang(slug: string): Promise<{ ok: boolean }> {
  const ok = await cozeDeleteLingguang(slug);
  return { ok };
}

export async function fetchCaseList(): Promise<CaseSummary[]> {
  const cs = await fetchCases();
  return cs.map((c, _idx) => adaptCase(c, `case-${c.stockCode}`));
}

export async function fetchCaseDetail(slug: string): Promise<CaseSummary> {
  const code = slug.replace('case-', '');
  const cs = await fetchCases();
  const c = cs.find((c) => c.stockCode === code);
  if (!c) throw new Error('not found');
  return adaptCase(c, slug);
}

export async function saveCase(slug: string, data: Partial<CaseSummary>): Promise<{ ok: boolean }> {
  const code = slug.replace('case-', '');
  const cs = await fetchCases();
  const existing = cs.find((c) => c.stockCode === code);
  const merged = { ...(existing ?? { stockCode: code, stockName: '', sector: '', entryPrice: '', exitPrice: '', gainMultiple: '', actualReturnPct: 0, startPrice: 0, startDate: '', peakPrice: 0, peakDate: '', maxDrawdownPct: 0, primaryDriver: '', returnType: '', catalyst: '', logic: '', endState: '', roicImprovement: 0, peExpansion: 0, tags: [] }), ...data };
  const ok = await cozeSaveCase(merged as CozeCase);
  return { ok };
}

export async function fetchTrackingList(): Promise<TrackingItem[]> {
  return (await fetchTracking()).map(adaptTracking);
}

export async function fetchTrackingDetail(ticker: string): Promise<TrackingItem> {
  const items = await fetchTracking();
  const item = items.find((t) => t.stockCode === ticker);
  if (!item) throw new Error('not found');
  return adaptTracking(item);
}

export async function saveTracking(ticker: string, data: Partial<TrackingItem>): Promise<{ ok: boolean }> {
  const body: Record<string, unknown> = { stockCode: ticker, ...data, updatedAt: new Date().toISOString() };
  const COZE_BASE = "https://api.coze.cn/v1/databases";
  const DB_TRACKING = "7645332166129287218";
  const TOKEN = (typeof window !== 'undefined' ? (window as unknown as Record<string, unknown>).__COZE_TOKEN : undefined) as string;
  const tk = TOKEN || '';
  if (!tk) return { ok: false };
  try {
    await fetch(`${COZE_BASE}/${DB_TRACKING}/records`, {
      method: "POST", headers: { Authorization: `Bearer ${tk}`, "Content-Type": "application/json" },
      body: JSON.stringify({ insert_rows: [Object.fromEntries(Object.entries(body).map(([k, v]) => [k, String(v ?? "")]))], is_async: false }),
    });
    return { ok: true };
  } catch { return { ok: false }; }
}
