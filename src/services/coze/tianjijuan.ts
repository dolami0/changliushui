import { cozeQuery, fetchAll, DB_TIANJIJUAN } from './client';

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
