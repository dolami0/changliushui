// ============================================================================
// 长流水 3.0 · 数据层 — Coze 直连，不做字段裁切
//
// 视图直接消费 Coze 原始类型（TrackingItem / DingshuluRecord /
// WangqiResult / TianjijuanRecord 等），保证所有字段原样透传。
// 写操作通过 cozeApi 直写 Coze，失败时无 mock 兜底——弹 toast 报错。
// ============================================================================

export {
  type CozeRecord,
  type TianjijuanRecord,
  type DingshuluRecord,
  type WanyepuRecord,
  type YinguobuRecord,
  type WangqiResult,
  type ReportV6Record,
  type TrackingItem,
  type TrackStatus,
  type LingguangItem,
  type CaseItem,
  fetchAll,
  fetchLatestRecords,
  fetchTotalCount,
  fetchRecordById,
  searchRecords,
  parseRecordToReport,
  fetchTianjijuan,
  fetchTianjijuanToday,
  fetchTianjijuanByUuid,
  stripHtml,
  extractNewsTitle,
  fetchDingshuluCount,
  fetchDingshulu,
  fetchDingshuluAll,
  fetchDingshuluToday,
  extractReportFilename,
  fetchWanyepu,
  fetchYinguobu,
  fetchWangqi,
  fetchReportByFilename,
  fetchReportSummaries,
  fetchTracking,
  updateTrackStatus,
  fetchReportFromCoze,
  fetchLingguang,
  fetchLingguangBySlug,
  saveLingguang,
  deleteLingguang,
  fetchCases,
  fetchCaseByCode,
  saveCase,
  cozeInsert,
  cozeUpdate,
  cozeUpsert,
} from './services/cozeApi';

export {
  fetchStatus,
  fetchSchedulerDetail,
  triggerPoll,
  startScheduler,
  stopScheduler,
  triggerReview,
  fetchReviewStatus,
  fetchReviewFiles,
  fetchReviewFileContent,
  setSchedulerInterval,
  createProgressStream,
} from './services/valuationApi';

export { loadMemory, addLingGuang, addCase } from './services/agentMemory';

let demoMode = false;
const demoListeners = new Set<() => void>();

function setDemo(v: boolean) {
  if (demoMode === v) return;
  demoMode = v;
  demoListeners.forEach((fn) => fn());
}

export function subscribeDemo(fn: () => void): () => void {
  demoListeners.add(fn);
  return () => demoListeners.delete(fn);
}

export function isDemo(): boolean { return demoMode; }

/** 调用 Coze 查询，成功则标记 live，失败则标记 demo */
export async function withCoze<T>(fn: () => Promise<T[]>, fallback: T[] = []): Promise<T[]> {
  try {
    const items = await fn();
    if (items.length > 0) { setDemo(false); return items; }
  } catch (e) { console.warn('Coze fetch failed', e); }
  setDemo(true);
  return fallback;
}
