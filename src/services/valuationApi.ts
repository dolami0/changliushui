const API_BASE = '';

export interface SchedulerState {
  active_jobs: Array<{ stock_code: string; stock_name: string; status: string }>;
  completed_jobs: Array<{ stock_code: string; stock_name: string; status: string; completed_at: string }>;
  last_poll_at: string | null;
  next_poll_at: string | null;
  scheduler_running: boolean;
  server_started_at: string;
}

export interface ProgressEvent {
  stock_code: string;
  stock_name: string;
  stage: string;
  step: number;
  total_steps: number;
  step_name: string;
  status: string;
  elapsed_s: number;
  error_msg: string | null;
  timestamp: string;
}

export interface ReportData {
  agent0: Record<string, unknown>;
  agent1: Record<string, unknown>;
  agent2: Record<string, unknown>;
  agent3: Record<string, unknown>;
}

export async function fetchStatus(): Promise<SchedulerState> {
  const resp = await fetch(`${API_BASE}/api/status`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchSchedulerDetail(): Promise<Record<string, unknown>> {
  const resp = await fetch(`${API_BASE}/api/scheduler/status`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export function createProgressStream(
  onEvent: (e: ProgressEvent) => void,
  onError?: (e: Event) => void
): EventSource {
  const es = new EventSource(`${API_BASE}/api/progress/stream`);
  es.addEventListener('progress', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data)); } catch { /* ignore malformed */ }
  });
  if (onError) es.onerror = onError;
  return es;
}

export async function triggerPoll(): Promise<{ status: string; processed: number }> {
  const resp = await fetch(`${API_BASE}/api/trigger`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function startScheduler(): Promise<{ status: string; message: string }> {
  const resp = await fetch(`${API_BASE}/api/scheduler/start`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function stopScheduler(): Promise<{ status: string; message: string }> {
  const resp = await fetch(`${API_BASE}/api/scheduler/stop`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// ── 报告审阅 ──

export interface ReviewStatus {
  has_review: boolean;
  health?: string;
  total_reports?: number;
  grade_distribution?: Record<string, number>;
  layer_averages?: Record<string, number>;
  top_flags?: Array<{ code: string; count: number; action: string }>;
  available_files?: string[];
}

export async function triggerReview(): Promise<{
  status: string; reviewed: number; health?: string;
  grade_distribution?: Record<string, number>;
  top_flags?: Array<{ code: string; count: number; action: string }>;
}> {
  const resp = await fetch(`${API_BASE}/api/review/trigger`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchReviewStatus(): Promise<ReviewStatus> {
  const resp = await fetch(`${API_BASE}/api/review/status`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export interface ReviewFile {
  filename: string; date: string; url: string;
}

export async function fetchReviewFiles(): Promise<ReviewFile[]> {
  const resp = await fetch(`${API_BASE}/api/review/list`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchReviewFileContent(filename: string): Promise<{ filename: string; content: string }> {
  const resp = await fetch(`${API_BASE}/api/review/file/${filename}`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function setSchedulerInterval(intervalSec: number): Promise<{ status: string; interval_sec: number }> {
  const resp = await fetch(`${API_BASE}/api/scheduler/interval`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ interval_sec: intervalSec }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function fetchReportData(stockCode: string): Promise<ReportData> {
  const resp = await fetch(`${API_BASE}/api/report/${stockCode}/data`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// ── 天机 (产业链利润流分析) ──────────────

export interface TianjiStatus {
  running: boolean;
  initialized: boolean;
  interval_sec: number;
  last_poll_at: string | null;
  next_poll_at: string | null;
  current_status: string;
  completed_count: number;
  completed_jobs: Array<{
    record_id: string;
    top_pick: string;
    runner_up: string;
    status: string;
    at: string;
  }>;
}

const WANGQI_BASE = window.location.port === '5173' ? 'http://localhost:8080' : '';  // dev: 直连8080; prod/ngrok: 相对路径同源

export async function fetchTianjiStatus(): Promise<TianjiStatus> {
  const resp = await fetch(`${WANGQI_BASE}/api/industry-chain/status`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const data = await resp.json();
  return data.scheduler || { running: false, initialized: false, interval_sec: 0, last_poll_at: null, next_poll_at: null, current_status: 'not_initialized', completed_count: 0 };
}

export async function startWangqi(): Promise<{ status: string; message: string }> {
  const resp = await fetch(`${WANGQI_BASE}/api/industry-chain/start`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function stopWangqi(): Promise<{ status: string; message: string }> {
  const resp = await fetch(`${WANGQI_BASE}/api/industry-chain/stop`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function triggerWangqi(): Promise<{ status: string; processed: number; results: Array<{ record_id: string; top_pick: string; runner_up: string }> }> {
  const resp = await fetch(`${WANGQI_BASE}/api/industry-chain/trigger`, { method: 'POST' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export function createTianjiStream(): EventSource {
  return new EventSource(`${WANGQI_BASE}/api/industry-chain/progress/stream`);
}
