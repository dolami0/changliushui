import { cozeQuery, fetchAll, DB_CANGJING } from './client';

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
