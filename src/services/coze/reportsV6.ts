import { cozeQuery, sanitizeJson, DB_REPORTS_V6 } from './client';

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
  baseline_report_json?: string;
  baseline_report?: string;
  processed_at: string;
}

/**
 * 按股票代码或文件名从 Coze 查询完整估值报告。
 * 优先 json_filename 精确匹配，兜底 stock_code。
 * 可用参数: 纯6位代码 "300726" 或文件名 "300726_20260522_1004"
 */
export async function fetchReportFromCoze(codeOrFilename: string): Promise<Record<string, unknown> | null> {
  const input = codeOrFilename.trim();
  // 判断类型: 纯6位数字=stock_code, 含下划线或超过6位=文件名
  const isStockCode = /^\d{6}$/.test(input);

  // 策略1: 如果不是纯 stock_code，先按文件名精确匹配
  if (!isStockCode) {
    // 尝试多种文件名格式
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

  // 策略2: 按 stock_code 匹配 (优先用输入中提取的6位数字)
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

export function reassembleReport(r: ReportV6Record): Record<string, unknown> {
  const report: Record<string, unknown> = {};
  if (r.agent0_json) try { report.agent0 = JSON.parse(sanitizeJson(r.agent0_json)); } catch { /* ignore */ }
  if (r.agent1_json) try { report.agent1 = JSON.parse(sanitizeJson(r.agent1_json)); } catch { /* ignore */ }
  if (r.agent2_json) try { report.agent2 = JSON.parse(sanitizeJson(r.agent2_json)); } catch { /* ignore */ }
  if (r.agent2a_json) try { report.agent2a = JSON.parse(sanitizeJson(r.agent2a_json)); } catch { /* ignore */ }
  if (r.agent3_json) try { report.agent3 = JSON.parse(sanitizeJson(r.agent3_json)); } catch { /* ignore */ }
  if (r.routing_json) try { report.routing_decision = JSON.parse(sanitizeJson(r.routing_json)); } catch { /* ignore */ }
  // baseline_report 是 Markdown 字符串（非 JSON），直接存为文本
  const raw = r as unknown as Record<string, unknown>;
  if (raw.baseline_report && typeof raw.baseline_report === 'string' && (raw.baseline_report as string).trim()) {
    report.baseline_report = raw.baseline_report;
  }
  return report;
}
