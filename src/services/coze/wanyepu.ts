import { cozeQuery, DB_WANYEPU } from './client';

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
