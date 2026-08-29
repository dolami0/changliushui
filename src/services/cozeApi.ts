/* ------------------------------------------------------------------ */
/*  Coze 通用数据服务层 — 五大古籍分类（barrel re-export）              */
/* ------------------------------------------------------------------ */

export { fetchAll } from './coze/client';

export type { CozeRecord } from './coze/cangjing';
export {
  fetchLatestRecords,
  fetchTotalCount,
  fetchRecordById,
  searchRecords,
  parseRecordToReport,
} from './coze/cangjing';

export type { TianjijuanRecord } from './coze/tianjijuan';
export {
  fetchTianjijuan,
  fetchTianjijuanToday,
  fetchTianjijuanByUuid,
  stripHtml,
  extractNewsTitle,
} from './coze/tianjijuan';

export type { DingshuluRecord } from './coze/dingshulu';
export {
  extractReportFilename,
  fetchDingshuluCount,
  fetchDingshulu,
  fetchDingshuluToday,
} from './coze/dingshulu';

export type { WanyepuRecord } from './coze/wanyepu';
export { fetchWanyepu } from './coze/wanyepu';

export type { YinguobuRecord, WangqiResult } from './coze/yinguobu';
export { fetchYinguobu, fetchWangqi } from './coze/yinguobu';

export { fetchReportByFilename, fetchReportSummaries } from './coze/reportsLookup';

export type { ReportV6Record } from './coze/reportsV6';
export { fetchReportFromCoze } from './coze/reportsV6';

export type { TrackStatus, TrackingItem } from './coze/tracking';
export { fetchTracking, updateTrackStatus } from './coze/tracking';

export type { LingguangItem } from './coze/lingguang';
export {
  fetchLingguang,
  fetchLingguangBySlug,
  saveLingguang,
  deleteLingguang,
} from './coze/lingguang';

export type { CaseItem } from './coze/cases';
export { fetchCases, fetchCaseByCode, saveCase } from './coze/cases';
