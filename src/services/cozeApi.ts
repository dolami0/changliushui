/* ------------------------------------------------------------------ */
/*  Coze 通用数据服务层 — 五大古籍分类                                 */
/* ------------------------------------------------------------------ */

const COZE_BASE = 'https://api.coze.cn/v1/databases';
const TOKEN = import.meta.env.VITE_COZE_TOKEN || '';

// ====== 数据库 ID 常量 ======
const DB_CANGJING  = '7611455655748304896'; // 藏经阁
const DB_TIANJIJUAN = '7479116110479048754'; // 天机卷
const DB_WANYEPU   = '7639784337973477386'; // 万业谱
const DB_DINGSHULU  = '7640094415800860724'; // 定数录
const DB_YINGUOBU   = '7640928034144698374'; // 因果簿
const DB_REPORTS_V6 = '7644911309938589711'; // 估值报告V6（按Agent拆分存储）

// ====== 通用 Coze 客户端 ======
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

// ====== 藏经阁 (7611455655748304896) — 保留兼容 ======
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

// ====== 天机卷 (7479116110479048754) ======
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

// ====== 定数录 (7640094415800860724) ======
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
  // Coze 定数录扩展字段（旧版 Avatar 页面用）
  comprehensive_score?: string;
  potential_increase?: string;
  cylfx?: string;
  source?: string;
  background?: string;
  analysis_report?: string;
  high_yield_investment_opportunity?: string;
}

/** 从 report_html_url 提取报告文件名（如 688805_20260522_1528） */
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

// ====== 万业谱 (7639784337973477386) ======
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

// ====== 因果簿 (7640928034144698374) ======
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

// ====== 估值报告 V6（按 Agent 拆分存储，从 Coze 直读） ======

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
  processed_at: string;
}

/**
 * 按股票代码从 Coze 查询完整估值报告（取最新一条）。
 * 替代原来的 fetch(`/api/report/${code}/data`)。
 */
export async function fetchReportFromCoze(stockCode: string): Promise<Record<string, unknown> | null> {
  const result = await cozeQuery<ReportV6Record>(DB_REPORTS_V6, {
    page_size: 1,
    filter: {
      logic: 'and',
      conditions: [
        { left: 'stock_code', operation: 'equal', right: stockCode },
      ],
    },
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  const items = result.data?.items || [];
  if (items.length === 0) return null;
  return reassembleReport(items[0]);
}

/**
 * 按 json_filename 查询报告（如 300726_20260522_1505）。
 * 替代原来的 fetch(`/api/report/data/${filename}`)。
 */
export async function fetchReportByFilename(filename: string): Promise<Record<string, unknown> | null> {
  const result = await cozeQuery<ReportV6Record>(DB_REPORTS_V6, {
    page_size: 1,
    filter: {
      logic: 'and',
      conditions: [
        { left: 'json_filename', operation: 'equal', right: filename },
      ],
    },
  });
  const items = result.data?.items || [];
  if (items.length === 0) return null;
  return reassembleReport(items[0]);
}

function reassembleReport(r: ReportV6Record): Record<string, unknown> {
  const report: Record<string, unknown> = {};
  if (r.agent0_json) try { report.agent0 = JSON.parse(r.agent0_json); } catch { /* ignore */ }
  if (r.agent1_json) try { report.agent1 = JSON.parse(r.agent1_json); } catch { /* ignore */ }
  if (r.agent2_json) try { report.agent2 = JSON.parse(r.agent2_json); } catch { /* ignore */ }
  if (r.agent2a_json) try { report.agent2a = JSON.parse(r.agent2a_json); } catch { /* ignore */ }
  if (r.agent3_json) try { report.agent3 = JSON.parse(r.agent3_json); } catch { /* ignore */ }
  if (r.routing_json) try { report.routing_decision = JSON.parse(r.routing_json); } catch { /* ignore */ }
  return report;
}
