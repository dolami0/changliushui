import { cozeQuery, DB_DINGSHULU } from './client';

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
