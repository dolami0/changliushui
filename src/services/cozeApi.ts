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
