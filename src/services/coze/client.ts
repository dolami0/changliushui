/* ------------------------------------------------------------------ */
/*  Coze 通用数据服务层 — client                                       */
/* ------------------------------------------------------------------ */

export const COZE_BASE = 'https://api.coze.cn/v1/databases';
export const TOKEN = import.meta.env.VITE_COZE_TOKEN || '';

// ====== 数据库 ID 常量 ======
export const DB_CANGJING  = '7611455655748304896'; // 藏经阁
export const DB_TIANJIJUAN = '7479116110479048754'; // 天机卷
export const DB_TRACKING   = '7645332166129287218'; // 追踪令
export const DB_LINGGUANG  = '7645332554400153646'; // 灵光
export const DB_CASES      = '7645333715039830079'; // 案例
export const DB_WANYEPU   = '7639784337973477386'; // 万业谱
export const DB_DINGSHULU  = '7640094415800860724'; // 定数录
export const DB_YINGUOBU   = '7640928034144698374'; // 因果簿
export const DB_REPORTS_V6 = '7644911309938589711'; // 估值报告V6（按Agent拆分存储）

// ====== 通用 Coze 客户端 ======
export interface ApiResponse<T> {
  code: number;
  data: { has_more: boolean; total_count: number; items: T[] };
  msg: string;
}

export async function cozeQuery<T>(databaseId: string, body: Record<string, unknown> = {}): Promise<ApiResponse<T>> {
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

/** 修复不合法的 JSON 值 (NaN, Infinity, -Infinity) */
export function sanitizeJson(raw: string): string {
  return raw.replace(/: NaN/g, ': null').replace(/: Infinity/g, ': null').replace(/: -Infinity/g, ': null')
}

export function tryParse(s: string | undefined | null): unknown {
  if (!s) return null;
  try { return JSON.parse(sanitizeJson(s)); } catch { return null; }
}
