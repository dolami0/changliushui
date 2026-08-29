import { cozeQuery, fetchAll, tryParse, DB_REPORTS_V6, DB_DINGSHULU } from './client';

// 按文件名查报告 (给 PanoramicMonitor 用)
export async function fetchReportByFilename(filename: string): Promise<Record<string, unknown> | null> {
  // 尝试多种格式: 300726_20260522_1004, 300726_20260522_1004.json, 300726
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
  // 最后兜底: 按 stock_code 模糊匹配
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

// 报告批量摘要 (给 Hero.tsx 用)
export async function fetchReportSummaries(codes: string): Promise<Record<string, string>> {
  const codeList = codes.split(",").map((s) => s.trim()).filter(Boolean);
  const result: Record<string, string> = {};
  if (codeList.length === 0) return result;
  // 用 fetchAll 批量拉取 (已验证可靠)
  const rows = await fetchAll<Record<string, string>>(DB_DINGSHULU, 2);
  for (const code of codeList) {
    const row = rows.find((r) => r.stock_code === code);
    result[code] = row ? `${row.stock_name}: ups=${row.prob_weighted_upside_pct}% asym=${row.asymmetry_ratio}` : "";
  }
  return result;
}
