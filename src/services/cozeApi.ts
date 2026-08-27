/* ------------------------------------------------------------------ */
/*  Coze 通用数据服务层 — 五大古籍分类                                 */
/* ------------------------------------------------------------------ */

const COZE_BASE = 'https://api.coze.cn/v1/databases';
const TOKEN = import.meta.env.VITE_COZE_TOKEN || '';

// ====== 数据库 ID 常量 ======
const DB_CANGJING  = '7611455655748304896'; // 藏经阁
const DB_TIANJIJUAN = '7479116110479048754'; // 天机卷
const DB_TRACKING   = '7645332166129287218'; // 追踪令
const DB_LINGGUANG  = '7645332554400153646'; // 灵光
const DB_CASES      = '7645333715039830079'; // 案例
const DB_WANYEPU   = '7639784337973477386'; // 万业谱
const DB_DINGSHULU  = '7640094415800860724'; // 定数录
const DB_YINGUOBU   = '7640928034144698374'; // 因果簿
const DB_REPORTS_V6 = '7644911309938589711'; // 估值报告V6（按Agent拆分存储）

interface ApiResponse<T> {
  code: number;
  data: { has_more: boolean; total_count: number; items: T[] };
  msg: string;
}

async function cozeQuery<T>(databaseId: string, body: Record<string, unknown> = {}): Promise<ApiResponse<T>> {
  const resp = await fetch(`${COZE_BASE}/${databaseId}/records/query`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Coze HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchAll<T>(databaseId: string, maxPages = 10, filter?: Record<string, unknown>): Promise<T[]> {
  const items: T[] = [];
  let pageToken = '';
  for (let i = 0; i < maxPages; i++) {
    const body: Record<string, unknown> = {
      page_size: 1000,
      order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
    };
    if (filter) body.filter = filter;
    if (pageToken) body.page_token = pageToken;
    const result = await cozeQuery<T>(databaseId, body);
    items.push(...(result.data?.items || []));
    if (!result.data?.has_more) break;
    pageToken = (result as unknown as Record<string, unknown>).data_page_token as string || '';
    if (!pageToken) break;
  }
  return items;
}

export interface CozeRecord {
  id: string;
  stock_code: string;
  stock_name: string;
  background: string;
  source: string;
  is_analyzed: string;
  is_transferred: string;
  analysis_report: string;
  high_yield_investment_opportunity: string;
  potential_increase: string;
  knowledge: string;
  comprehensive_score: string;
  cylfx: string;
  uuid: string;
  bstudio_create_time?: string;
}

export async function fetchLatestRecords(pageSize: number = 20): Promise<CozeRecord[]> {
  const result = await cozeQuery<CozeRecord>(DB_CANGJING, {
    page_size: pageSize,
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  return result.data?.items || [];
}

export async function fetchTotalCount(): Promise<number> {
  const result = await cozeQuery<CozeRecord>(DB_CANGJING, {
    page_size: 1,
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  return result.data?.total_count || 0;
}

export async function fetchRecordById(id: string): Promise<CozeRecord | null> {
  const all = await fetchAll<CozeRecord>(DB_CANGJING);
  return all.find((r) => r.id === id) || null;
}

export async function searchRecords(query: string): Promise<CozeRecord[]> {
  const all = await fetchAll<CozeRecord>(DB_CANGJING);
  if (!query.trim()) return all;
  const q = query.toLowerCase();
  return all.filter(
    (r) =>
      r.stock_name?.toLowerCase().includes(q) ||
      r.stock_code?.includes(q) ||
      r.source?.toLowerCase().includes(q) ||
      r.background?.toLowerCase().includes(q)
  );
}

export function parseRecordToReport(record: CozeRecord) {
  const summary = record.background
    ? record.background.replace(/\*\*/g, '').replace(/\n/g, ' ').slice(0, 60) + '...'
    : '暂无摘要';
  const sectorMatch = record.background?.match(/行业分类[：:]\s*([^\n]+)/);
  const sector = sectorMatch ? sectorMatch[1].split('，')[0] : record.source || '综合';
  const score = record.comprehensive_score || '0';
  const scoreNum = parseFloat(score);
  let signal = '中';
  if (scoreNum >= 80) signal = '强';
  else if (scoreNum >= 50) signal = '中';
  else if (scoreNum > 0) signal = '弱';
  const potential = record.potential_increase || '—';
  const targetPrice = scoreNum > 0 ? Math.round(scoreNum * 4.2).toString() : '—';
  return {
    id: record.id, ticker: record.stock_name || '未知', code: record.stock_code || '',
    tag: sector, target: targetPrice,
    potential: potential !== '—' ? potential : scoreNum > 0 ? `${(scoreNum / 25).toFixed(1)}x` : '—',
    signal, time: record.bstudio_create_time
      ? new Date(parseInt(record.bstudio_create_time)).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
      : '', summary, raw: record,
  };
}

export interface TianjijuanRecord {
  id: string;
  date: string;
  bstudio_create_time: string;
  level: string;
  mode: string;
  stock_code: string;
  stock_name: string;
  news_content: string;
  knowledge: string;
  is_analyzed: string;
  uuid: string;
}

export async function fetchTianjijuan(pageSize = 500): Promise<TianjijuanRecord[]> {
  const result = await cozeQuery<TianjijuanRecord>(DB_TIANJIJUAN, {
    page_size: pageSize,
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  return result.data?.items || [];
}

export function fetchTianjijuanToday(): Promise<TianjijuanRecord[]> {
  return fetchAll<TianjijuanRecord>(DB_TIANJIJUAN);
}

export function fetchTianjijuanByUuid(uuid: string): Promise<TianjijuanRecord[]> {
  return fetchTianjijuan().then((items) => items.filter((r) => r.uuid === uuid));
}

export function stripHtml(html: string): string {
  return html.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, ' ').replace(/\s+/g, ' ').trim();
}

export function extractNewsTitle(newsContent: string, maxLen = 40): string {
  const text = stripHtml(newsContent);
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text;
}

export interface DingshuluRecord {
  id: string;
  stock_code: string;
  stock_name: string;
  event_date: string;
  event_source: string;
  trade_tier: string;
  quality_flag: string;
  confidence_score: string;
  base_prob: string;
  bull_prob: string;
  bear_prob: string;
  base_upside_pct: string;
  bull_upside_pct: string;
  bear_upside_pct: string;
  prob_weighted_upside_pct: string;
  prob_weighted_mcap_billion: string;
  current_mcap_billion: string;
  asymmetry_ratio: string;
  primary_model: string;
  news_summary: string;
  report_html_url: string;
  uuid: string;
  processed_at: string;
  bstudio_create_time: string;
  comprehensive_score?: string;
  potential_increase?: string;
  cylfx?: string;
  source?: string;
  background?: string;
  analysis_report?: string;
  high_yield_investment_opportunity?: string;
}

export function extractReportFilename(record: DingshuluRecord): string | null {
  const url = record.report_html_url;
  if (!url) return null;
  const parts = url.split('/');
  return parts[parts.length - 1] || null;
}

export async function fetchDingshuluCount(): Promise<number> {
  const result = await cozeQuery<DingshuluRecord>(DB_DINGSHULU, {
    page_size: 1,
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  return result.data?.total_count || 0;
}

export async function fetchDingshulu(pageSize = 500): Promise<DingshuluRecord[]> {
  const result = await cozeQuery<DingshuluRecord>(DB_DINGSHULU, {
    page_size: pageSize,
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  return result.data?.items || [];
}

export function fetchDingshuluToday(): Promise<DingshuluRecord[]> {
  return fetchDingshulu().then((items) => {
    const today = new Date();
    const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    return items.filter((r) => r.event_date === todayStr);
  });
}

export interface WanyepuRecord {
  id: string;
  stock_code: string;
  stock_name: string;
  event_date: string;
  source: string;
  industry_expert_research: string;
  confidence_score: string;
  status: string;
  is_complete?: boolean;
  uuid: string;
  bstudio_create_time: string;
}

export async function fetchWanyepu(pageSize = 500): Promise<WanyepuRecord[]> {
  const result = await cozeQuery<WanyepuRecord>(DB_WANYEPU, {
    page_size: pageSize,
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  return result.data?.items || [];
}

export interface YinguobuRecord {
  id: string;
  source_record_id: string;
  industry_chain: string;
  event_summary: string;
  chain_analysis_json: string;
  stock_analysis_json: string;
  top5_json: string;
  top_nodes_json: string;
  top_pick_code: string;
  top_pick_name: string;
  top_pick_score: string;
  top_pick_thesis: string;
  runner_up_code: string;
  runner_up_name: string;
  runner_up_score: string;
  runner_up_thesis: string;
  web_research: string;
  news_content: string;
  step_one_data: string;
  analysis_date: string;
  status: string;
  uuid: string;
  bstudio_create_time: string;
}

export async function fetchYinguobu(pageSize = 500): Promise<YinguobuRecord[]> {
  const result = await cozeQuery<YinguobuRecord>(DB_YINGUOBU, {
    page_size: pageSize,
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  return result.data?.items || [];
}

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

function tryParse(s: string | undefined | null): unknown {
  if (!s) return null;
  try { return JSON.parse(sanitizeJson(s)); } catch { return null; }
}

export async function fetchReportByFilename(filename: string): Promise<Record<string, unknown> | null> {
  const code = filename.split('_')[0];
  const names = [...new Set([
    filename,
    filename.endsWith(".json") ? filename : `${filename}.json`,
    filename.replace(/_/g, '').match(/^\d{6}/)?.[0] || code,
  ])].filter(Boolean);

  for (const name of names) {
    const r = await cozeQuery<Record<string, string>>(DB_REPORTS_V6, {
      page_size: 1,
      filter: { logic: "and", conditions: [{ left: "json_filename", operation: "equal", right: name }] },
    });
    const row = r.data?.items?.[0];
    if (row) {
      return {
        agent0: tryParse(row.agent0_json), agent1: tryParse(row.agent1_json),
        agent2: tryParse(row.agent2_json), agent2a: tryParse(row.agent2a_json),
        agent3: tryParse(row.agent3_json), routing_decision: tryParse(row.routing_json),
        baseline_report: row.baseline_report || '',
      };
    }
  }
  if (code.length === 6) {
    const r2 = await cozeQuery<Record<string, string>>(DB_REPORTS_V6, {
      page_size: 1,
      filter: { logic: "and", conditions: [{ left: "stock_code", operation: "equal", right: code }] },
    });
    const row = r2.data?.items?.[0];
    if (row) {
      return {
        agent0: tryParse(row.agent0_json), agent1: tryParse(row.agent1_json),
        agent2: tryParse(row.agent2_json), agent2a: tryParse(row.agent2a_json),
        agent3: tryParse(row.agent3_json), routing_decision: tryParse(row.routing_json),
        baseline_report: row.baseline_report || '',
      };
    }
  }
  return null;
}

export async function fetchReportSummaries(codes: string): Promise<Record<string, string>> {
  const codeList = codes.split(",").map((s) => s.trim()).filter(Boolean);
  const result: Record<string, string> = {};
  if (codeList.length === 0) return result;
  const rows = await fetchAll<Record<string, string>>(DB_DINGSHULU, 2);
  for (const code of codeList) {
    const row = rows.find((r) => r.stock_code === code);
    result[code] = row ? `${row.stock_name}: ups=${row.prob_weighted_upside_pct}% asym=${row.asymmetry_ratio}` : "";
  }
  return result;
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

export interface ReportV6Record {
  id: string;
  stock_code: string;
  stock_name: string;
  json_filename: string;
  agent0_json: string;
  agent1_json: string;
  agent2_json: string;
  agent2a_json: string;
  agent3_json: string;
  routing_json: string;
  baseline_report_json?: string;
  baseline_report?: string;
  processed_at: string;
}

export async function fetchReportFromCoze(codeOrFilename: string): Promise<Record<string, unknown> | null> {
  const input = codeOrFilename.trim();
  const isStockCode = /^\d{6}$/.test(input);

  if (!isStockCode) {
    const names = [...new Set([
      input,
      input.endsWith('.json') ? input : `${input}.json`,
      input.replace(/\.json$/, ''),
    ])].filter(Boolean);

    for (const name of names) {
      const r = await cozeQuery<ReportV6Record>(DB_REPORTS_V6, {
        page_size: 1,
        filter: { logic: 'and', conditions: [{ left: 'json_filename', operation: 'equal', right: name }] },
      });
      const row = r.data?.items?.[0];
      if (row) return reassembleReport(row);
    }
  }

  const stockCode = isStockCode ? input : (input.split('_')[0]?.match(/^\d{6}/)?.[0] || input.slice(0, 6));
  if (stockCode.length === 6) {
    const r = await cozeQuery<ReportV6Record>(DB_REPORTS_V6, {
      page_size: 1,
      filter: { logic: 'and', conditions: [{ left: 'stock_code', operation: 'equal', right: stockCode }] },
    });
    const row = r.data?.items?.[0];
    if (row) return reassembleReport(row);
  }

  return null;
}

function sanitizeJson(raw: string): string {
  return raw.replace(/: NaN/g, ': null').replace(/: Infinity/g, ': null').replace(/: -Infinity/g, ': null')
}

function reassembleReport(r: ReportV6Record): Record<string, unknown> {
  const report: Record<string, unknown> = {};
  if (r.agent0_json) try { report.agent0 = JSON.parse(sanitizeJson(r.agent0_json)); } catch { /* ignore */ }
  if (r.agent1_json) try { report.agent1 = JSON.parse(sanitizeJson(r.agent1_json)); } catch { /* ignore */ }
  if (r.agent2_json) try { report.agent2 = JSON.parse(sanitizeJson(r.agent2_json)); } catch { /* ignore */ }
  if (r.agent2a_json) try { report.agent2a = JSON.parse(sanitizeJson(r.agent2a_json)); } catch { /* ignore */ }
  if (r.agent3_json) try { report.agent3 = JSON.parse(sanitizeJson(r.agent3_json)); } catch { /* ignore */ }
  if (r.routing_json) try { report.routing_decision = JSON.parse(sanitizeJson(r.routing_json)); } catch { /* ignore */ }
  const raw = r as Record<string, unknown>;
  if (raw.baseline_report && typeof raw.baseline_report === 'string' && (raw.baseline_report as string).trim()) {
    report.baseline_report = raw.baseline_report;
  }
  return report;
}

async function cozeInsert(dbId: string, rows: Record<string, unknown>[]): Promise<boolean> {
  const resp = await fetch(`${COZE_BASE}/${dbId}/records`, {
    method: "POST", headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ insert_rows: rows.map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, String(v ?? "")]))), is_async: false }),
  });
  const d = (await resp.json()) as { code: number };
  return d.code === 0;
}

async function cozeUpdate(dbId: string, recordId: string, fields: Record<string, string>): Promise<boolean> {
  const resp = await fetch(`${COZE_BASE}/${dbId}/records`, {
    method: "PUT", headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ update_fields: Object.entries(fields).map(([k, v]) => ({ field_name: k, value: v })), filter: { logic: "and", conditions: [{ left: "id", operation: "equal", right: recordId }] }, is_async: false }),
  });
  const d = (await resp.json()) as { code: number };
  return d.code === 0;
}

async function cozeUpsert(dbId: string, matchField: string, matchValue: string, row: Record<string, unknown>): Promise<boolean> {
  const qr = await fetch(`${COZE_BASE}/${dbId}/records/query`, {
    method: "POST", headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ page_num: 1, page_size: 1, is_async: false, filter: { logic: "and", conditions: [{ left: matchField, operation: "equal", right: matchValue }] } }),
  });
  const qd = (await qr.json()) as { code: number; data?: { items: { id: string }[] } };
  const existingId = qd.data?.items?.[0]?.id;
  if (existingId) {
    return cozeUpdate(dbId, existingId, Object.fromEntries(Object.entries(row).map(([k, v]) => [k, String(v ?? "")])));
  }
  return cozeInsert(dbId, [row]);
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

export async function fetchLingguangBySlug(slug: string): Promise<LingguangItem | null> {
  const result = await cozeQuery<Record<string, string>>(DB_LINGGUANG, {
    page_size: 1, filter: { logic: "and", conditions: [{ left: "slug", operation: "equal", right: slug }] },
  });
  return result.data?.items?.length ? toLingguang(result.data.items[0]!) : null;
}

export async function saveLingguang(item: LingguangItem): Promise<boolean> {
  item.updatedAt = new Date().toISOString();
  if (!item.createdAt) item.createdAt = item.updatedAt;
  return cozeUpsert(DB_LINGGUANG, "slug", item.id, {
    slug: item.id, title: item.title, content: item.content,
    tags_json: JSON.stringify(item.tags), source: item.source,
    confidence: String(item.confidence), matches_json: JSON.stringify(item.matches),
    revision_json: JSON.stringify(item.revisionHistory),
    created_at: item.createdAt, updated_at: item.updatedAt,
  });
}

export async function deleteLingguang(slug: string): Promise<boolean> {
  const r = await cozeQuery<{ id: string }>(DB_LINGGUANG, {
    page_size: 1, filter: { logic: "and", conditions: [{ left: "slug", operation: "equal", right: slug }] },
  });
  const id = r.data?.items?.[0]?.id;
  if (!id) return false;
  return cozeUpdate(DB_LINGGUANG, id, { updated_at: new Date().toISOString(), title: "[已删除]" });
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

export async function fetchCaseByCode(code: string): Promise<CaseItem | null> {
  const result = await cozeQuery<Record<string, string>>(DB_CASES, {
    page_size: 1, filter: { logic: "and", conditions: [{ left: "stock_code", operation: "equal", right: code }] },
  });
  return result.data?.items?.length ? toCase(result.data.items[0]!) : null;
}

export async function saveCase(item: CaseItem): Promise<boolean> {
  return cozeUpsert(DB_CASES, "stock_code", item.stockCode, {
    stock_code: item.stockCode, stock_name: item.stockName, sector: item.sector,
    entry_price: item.entryPrice, exit_price: item.exitPrice,
    gain_multiple: item.gainMultiple, actual_return_pct: String(item.actualReturnPct),
    start_price: String(item.startPrice), start_date: item.startDate,
    peak_price: String(item.peakPrice), peak_date: item.peakDate,
    max_drawdown_pct: String(item.maxDrawdownPct),
    primary_driver: item.primaryDriver, return_type: item.returnType,
    catalyst: item.catalyst, logic: item.logic, end_state: item.endState,
    roic_improvement: String(item.roicImprovement),
    pe_expansion: String(item.peExpansion),
    tags_json: JSON.stringify(item.tags),
  });
}
