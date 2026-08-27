// 望气 (与因果簿同表)
export interface WangqiResult {
  source_record_id: string;
  news_content: string;
  industry_chain: string;
  event_summary: string;
  top_nodes_json: string;
  top_pick_code: string;
  top_pick_name: string;
  top_pick_score: string;
  top_pick_thesis: string;
  runner_up_code: string;
  runner_up_name: string;
  runner_up_score: string;
  runner_up_thesis: string;
  top5_json: string;
  analysis_date: string;
  status: string;
}

function sanitizeJson(raw: string): string {
  return raw.replace(/: NaN/g, ': null').replace(/: Infinity/g, ': null').replace(/: -Infinity/g, ': null')
}

export async function fetchWangqi(pageSize = 100): Promise<WangqiResult[]> {
  const items = await fetchYinguobu(pageSize);
  return items.map((r) => ({
    source_record_id: r.source_record_id || r.uuid || "",
    news_content: r.news_content || "",
    industry_chain: r.industry_chain || "",
    event_summary: r.event_summary || "",
    top_nodes_json: r.top_nodes_json || "",
    top_pick_code: r.top_pick_code || "",
    top_pick_name: r.top_pick_name || "",
    top_pick_score: r.top_pick_score || "",
    top_pick_thesis: r.top_pick_thesis || "",
    runner_up_code: r.runner_up_code || "",
    runner_up_name: r.runner_up_name || "",
    runner_up_score: r.runner_up_score || "",
    runner_up_thesis: r.runner_up_thesis || "",
    top5_json: r.top5_json || "",
    analysis_date: r.bstudio_create_time || "",
    status: r.status === "done" ? "done" : "pending",
  }));
}

export type TrackStatus = 'active' | 'paused';

export interface TrackingItem {
  id: string;
  stockCode: string;
  stockName: string;
  trackStatus: TrackStatus;
  thesis: string;
  conviction: number;
  decisionDate: string;
  decision: string;
  recommendedPosition: number;
  entryCondition: string;
  basePrice: number;
  baseMarketCap: number;
  baseDate: string;
  pillars: unknown[];
  risks: unknown[];
  catalystCalendar: unknown[];
  priceLog: Array<{ date: string; price: number; return_pct: number; note: string }>;
  thesisLog: unknown;
  exitConditions: unknown[];
  aShareTracking: Record<string, unknown>;
  reviewSchedule: Record<string, unknown>;
  updatedAt?: string;
  createdAt?: string;
}

const DB_TRACKING   = '7645332166129287218';
const DB_LINGGUANG  = '7645332554400153646';
const DB_CASES      = '7645333715039830079';

export async function fetchTracking(): Promise<TrackingItem[]> {
  const result = await cozeQuery<Record<string, string>>(DB_TRACKING, { page_size: 50 });
  const items = result.data?.items || [];
  return items.map((r) => {
    const meta = JSON.parse(sanitizeJson(r.meta_json || "{}")) as Record<string, unknown>;
    return {
      id: r.id || "",
      stockCode: r.stock_code || "", stockName: r.stock_name || "",
      trackStatus: (r.track_status as TrackStatus) || 'active',
      thesis: r.thesis || "",
      conviction: Number(r.conviction) || 0, decisionDate: r.decision_date || "",
      decision: r.decision || "", recommendedPosition: Number(r.recommended_position) || 0,
      entryCondition: r.entry_condition || "",
      basePrice: Number(r.base_price) || 0, baseMarketCap: Number(r.base_market_cap) || 0,
      baseDate: r.base_date || "",
      pillars: JSON.parse(sanitizeJson(r.pillars_json || "[]")), risks: JSON.parse(sanitizeJson(r.risks_json || "[]")),
      catalystCalendar: JSON.parse(sanitizeJson(r.catalyst_json || "[]")),
      priceLog: JSON.parse(sanitizeJson(r.price_log_json || "[]")),
      thesisLog: JSON.parse(sanitizeJson(r.thesis_log_json || "null")),
      exitConditions: (meta.exit_conditions ?? []) as unknown[], aShareTracking: (meta.a_share_tracking ?? {}) as Record<string, unknown>,
      reviewSchedule: (meta.review_schedule ?? {}) as Record<string, unknown>,
    };
  });
}

export async function updateTrackStatus(recordId: string, status: TrackStatus): Promise<void> {
  const resp = await fetch(`${COZE_BASE}/${DB_TRACKING}/records`, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      update_fields: [{ field_name: 'track_status', value: status }],
      filter: { logic: 'and', conditions: [{ left: 'id', operation: 'equal', right: recordId }] },
    }),
  });
  if (!resp.ok) throw new Error(`Coze update HTTP ${resp.status}`);
  const result = await resp.json() as { code: number; msg: string };
  if (result.code !== 0) throw new Error(result.msg || 'Update failed');
}

export interface LingguangItem {
  id: string; title: string; content: string;
  tags: string[]; source: string; confidence: number;
  matches: unknown[]; revisionHistory: unknown[];
  createdAt: string; updatedAt: string;
}

function toLingguang(row: Record<string, string>): LingguangItem {
  return {
    id: row.slug || "", title: row.title || "", content: row.content || "",
    tags: JSON.parse(sanitizeJson(row.tags_json || "[]")), source: row.source || "",
    confidence: Number(row.confidence) || 0,
    matches: JSON.parse(sanitizeJson(row.matches_json || "[]")),
    revisionHistory: JSON.parse(sanitizeJson(row.revision_json || "[]")),
    createdAt: row.created_at || "", updatedAt: row.updated_at || "",
  };
}

export async function fetchLingguang(): Promise<LingguangItem[]> {
  const items = await fetchAll<Record<string, string>>(DB_LINGGUANG);
  return items.map(toLingguang);
}

export interface CaseItem {
  stockCode: string; stockName: string; sector: string;
  entryPrice: string; exitPrice: string; gainMultiple: string;
  actualReturnPct: number; startPrice: number; startDate: string;
  peakPrice: number; peakDate: string; maxDrawdownPct: number;
  primaryDriver: string; returnType: string; catalyst: string;
  logic: string; endState: string;
  roicImprovement: number; peExpansion: number;
  tags: string[];
}

function toCase(row: Record<string, string>): CaseItem {
  return {
    stockCode: row.stock_code || "", stockName: row.stock_name || "",
    sector: row.sector || "",
    entryPrice: row.entry_price || "", exitPrice: row.exit_price || "",
    gainMultiple: row.gain_multiple || "",
    actualReturnPct: Number(row.actual_return_pct) || 0,
    startPrice: Number(row.start_price) || 0, startDate: row.start_date || "",
    peakPrice: Number(row.peak_price) || 0, peakDate: row.peak_date || "",
    maxDrawdownPct: Number(row.max_drawdown_pct) || 0,
    primaryDriver: row.primary_driver || "", returnType: row.return_type || "",
    catalyst: row.catalyst || "", logic: row.logic || "",
    endState: row.end_state || "",
    roicImprovement: Number(row.roic_improvement) || 0,
    peExpansion: Number(row.pe_expansion) || 0,
    tags: JSON.parse(row.tags_json || "[]"),
  };
}

export async function fetchCases(): Promise<CaseItem[]> {
  const items = await fetchAll<Record<string, string>>(DB_CASES);
  return items.map(toCase);
}
