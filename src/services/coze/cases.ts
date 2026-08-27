import { cozeQuery, fetchAll, DB_CASES } from './client';
import { cozeUpsert } from './write';

// ====== 案例 (DB_CASES) ======

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
