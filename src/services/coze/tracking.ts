import { COZE_BASE, TOKEN, cozeQuery, sanitizeJson, DB_TRACKING } from './client';

// 追踪令
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

/** 更新追踪令状态（通过更新记录的 track_status 字段） */
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
