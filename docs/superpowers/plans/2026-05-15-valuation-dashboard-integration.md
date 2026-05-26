# 估值重构引擎仪表盘整合 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Python 估值重构引擎 V4 的仪表盘和 HTML 报告以 React 页面形式，用长流水设计语言整合进前端。

**Architecture:** 新增 Dashboard 页（SSE 实时进度 + 调度器控制）和 ValuationReport 页（估值报告查看），通过 valuationApi.ts 服务层与 Python FastAPI 后端通信。Python 后端新增 CORS 支持和报告数据 JSON API。

**Tech Stack:** React 19 + TypeScript + CSSProperties (inline styles) + GSAP + EventSource (SSE) + FastAPI (existing)

---

## File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/services/valuationApi.ts` | 新建 | HTTP/SSE 封装，与 Python 后端通信 |
| `src/pages/Dashboard.tsx` | 新建 | 实时监控仪表盘页面 |
| `src/pages/ValuationReport.tsx` | 新建 | 估值报告查看页 |
| `src/App.tsx` | 修改 | 新增 2 条路由 |
| `估值重构引擎_V4/valuation_app/server.py` | 修改 | 添加 CORS + 报告 JSON API |
| `估值重构引擎_V4/valuation_app/scheduler.py` | 修改 | 生成报告时同步保存 JSON |

---

### Task 1: Python 后端 — CORS + 报告数据 JSON 持久化

**Files:**
- Modify: `估值重构引擎_V4/valuation_app/server.py` (lifespan + new endpoint)
- Modify: `估值重构引擎_V4/valuation_app/scheduler.py` (save JSON in _write_result_to_coze)

- [ ] **Step 1: 在 server.py 的 lifespan 中添加 CORS 中间件**

在 `from fastapi import FastAPI, Request` 之后追加导入，在 `@asynccontextmanager` 的 lifespan 中 `app = FastAPI(...)` 之后添加 CORS：

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
```

在 `app = FastAPI(title="估值重构引擎 V4", lifespan=lifespan)` 之后：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: 在 scheduler.py 的 _write_result_to_coze 中保存结果 JSON**

在 `_write_result_to_coze` 方法的末尾，`self.coze.insert_records(...)` 之后添加 JSON 持久化：

```python
# 保存结构化 JSON（供前端 React 报告页使用）
import json as _json
data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"
data_dir.mkdir(parents=True, exist_ok=True)
json_path = data_dir / f"{stock_code}.json"
payload = {
    "agent0": agent0_record,
    "agent1": self._serialize_agent_output(a1_out),
    "agent2": self._serialize_agent_output(a2_out),
    "agent3": self._serialize_agent_output(a3_out),
}
with open(json_path, "w", encoding="utf-8") as f:
    _json.dump(payload, f, ensure_ascii=False, indent=2)
```

在 Scheduler 类中添加辅助方法 `_serialize_agent_output`：

```python
@staticmethod
def _serialize_agent_output(obj) -> dict:
    """将 Agent 输出转为 JSON 可序列化格式"""
    if isinstance(obj, dict):
        return {k: Scheduler._serialize_agent_output(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [Scheduler._serialize_agent_output(v) for v in obj]
    elif hasattr(obj, '__dict__'):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
    else:
        return obj
```

- [ ] **Step 3: 在 server.py 添加报告数据 API 端点**

在 server.py 的 API 路由区域末尾，`if __name__ == "__main__"` 之前，添加：

```python
@app.get("/api/report/{stock_code}/data")
async def get_report_data(stock_code: str):
    """返回估值报告的完整结构化 JSON 数据"""
    import json as _json
    data_path = Path(__file__).resolve().parent.parent / "reports" / "data" / f"{stock_code}.json"
    if not data_path.exists():
        return JSONResponse({"error": f"未找到 {stock_code} 的报告数据"}, status_code=404)
    with open(data_path, encoding="utf-8") as f:
        return JSONResponse(_json.load(f))
```

- [ ] **Step 4: 验证后端改动**

```bash
cd D:\长流水前端\估值重构引擎_V4 && python -c "from valuation_app.server import app; print('OK')"
```

Expected: `OK` (无 import 错误)

---

### Task 2: 前端 — valuationApi 服务层

**Files:**
- Create: `src/services/valuationApi.ts`

- [ ] **Step 1: 创建 valuationApi.ts**

所有函数封装对 `http://localhost:8081` 的调用：

```typescript
const API_BASE = 'http://localhost:8081';

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
    try { onEvent(JSON.parse(e.data)); } catch { /* ignore */ }
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
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd D:\长流水前端 && npx tsc --noEmit src/services/valuationApi.ts
```

Expected: 无错误

---

### Task 3: 前端 — Dashboard 页面

**Files:**
- Create: `src/pages/Dashboard.tsx`

- [ ] **Step 1: 创建 Dashboard.tsx — 框架 + 导航栏**

```tsx
import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { navigationConfig } from '../config';
import {
  fetchStatus, fetchSchedulerDetail, createProgressStream,
  triggerPoll, startScheduler, stopScheduler, setSchedulerInterval,
  type SchedulerState, type ProgressEvent,
} from '../services/valuationApi';
import gsap from 'gsap';

const labelStyle: React.CSSProperties = {
  fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#777',
  letterSpacing: '0.15em',
};

const cardBase: React.CSSProperties = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.06)',
  padding: '20px 24px',
  transition: 'all 0.3s ease',
};

export default function Dashboard() {
  const navigate = useNavigate();
  const mobile = useMobile();
  const contentRef = useRef<HTMLDivElement>(null);

  const [sseConnected, setSseConnected] = useState(false);
  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [lastPollAt, setLastPollAt] = useState<string | null>(null);
  const [nextPollAt, setNextPollAt] = useState<string | null>(null);
  const [interval, setInterval] = useState(300);
  const [activeJobs, setActiveJobs] = useState<Array<{ stock_code: string; stock_name: string; status: string }>>([]);
  const [completedJobs, setCompletedJobs] = useState<Array<{ stock_code: string; stock_name: string; status: string; completed_at: string }>>([]);
  const [recentProgress, setRecentProgress] = useState<ProgressEvent[]>([]);
  const [error, setError] = useState('');
  const [triggerLoading, setTriggerLoading] = useState(false);

  // 后续步骤填充具体逻辑...
}
```

- [ ] **Step 2: 添加 SSE 连接逻辑（useEffect）**

在 Dashboard 组件中，fetchStatus 之后添加：

```tsx
// SSE 进度流
useEffect(() => {
  const es = createProgressStream(
    (event) => {
      setRecentProgress((prev) => [event, ...prev].slice(0, 20));
      setSseConnected(true);
    },
    () => setSseConnected(false)
  );
  // 初始状态拉取
  fetchStatus().then((s) => {
    setSchedulerRunning(s.scheduler_running);
    setLastPollAt(s.last_poll_at);
    setNextPollAt(s.next_poll_at);
    setActiveJobs(s.active_jobs || []);
    setCompletedJobs(s.completed_jobs || []);
    setSseConnected(true);
  }).catch(() => setSseConnected(false));

  return () => es.close();
}, []);

// 定时轮询状态 (10s)
useEffect(() => {
  const id = setInterval(async () => {
    try {
      const s = await fetchStatus();
      setSchedulerRunning(s.scheduler_running);
      setLastPollAt(s.last_poll_at);
      setNextPollAt(s.next_poll_at);
      setActiveJobs(s.active_jobs || []);
      setCompletedJobs(s.completed_jobs || []);
    } catch { /* keep old data */ }
  }, 10_000);
  return () => clearInterval(id);
}, []);
```

- [ ] **Step 3: 添加控制操作和入场动画**

```tsx
const handleTrigger = useCallback(async () => {
  setTriggerLoading(true);
  try {
    await triggerPoll();
  } catch (e) { setError(String(e)); }
  finally { setTriggerLoading(false); }
}, []);

const handleStart = useCallback(async () => {
  try { await startScheduler(); setSchedulerRunning(true); }
  catch (e) { setError(String(e)); }
}, []);

const handleStop = useCallback(async () => {
  try { await stopScheduler(); setSchedulerRunning(false); setNextPollAt(null); }
  catch (e) { setError(String(e)); }
}, []);

const handleInterval = useCallback(async (sec: number) => {
  try { await setSchedulerInterval(sec); setInterval(sec); }
  catch (e) { setError(String(e)); }
}, []);

// GSAP 入场
useEffect(() => {
  if (!contentRef.current) return;
  const cards = contentRef.current.querySelectorAll('.dash-card');
  gsap.fromTo(cards, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.08, ease: 'power2.out' });
}, [activeJobs.length, completedJobs.length]);
```

- [ ] **Step 4: 渲染 JSX — 导航栏 + 标题区**

```tsx
return (
  <div style={{ minHeight: '100vh', background: '#050401', color: '#F2F4F3' }}>
    {/* Nav */}
    <nav style={{ position: 'sticky', top: 0, zIndex: 50, display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: mobile ? '16px 20px' : '20px 48px', background: 'rgba(5,4,1,0.92)', backdropFilter: 'blur(6px)', borderBottom: '1px solid #2A2A2A' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
        <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: '#ADFF00', letterSpacing: '0.06em' }}>{navigationConfig.brandName}</span>
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#444', letterSpacing: '0.1em' }}>/ 估值重构仪表盘</span>
      </div>
      <button onClick={() => navigate('/')} style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#888', background: 'transparent', border: '1px solid #2A2A2A', padding: '8px 20px', cursor: 'pointer', letterSpacing: '0.1em' }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#ADFF00'; e.currentTarget.style.color = '#ADFF00'; }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#2A2A2A'; e.currentTarget.style.color = '#888'; }}>
        ← 返回宗门
      </button>
    </nav>

    <div ref={contentRef} style={{ maxWidth: '960px', margin: '0 auto', padding: mobile ? '24px 20px 48px' : '32px 48px 64px' }}>
      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <span style={{ width: '8px', height: '8px', background: '#ADFF00', boxShadow: '0 0 8px rgba(173,255,0,0.5)', animation: 'pulse 2s ease-in-out infinite', display: 'inline-block' }} />
          <h1 style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: '28px', fontWeight: 400, color: '#ADFF00', margin: 0, letterSpacing: '0.06em', textShadow: '0 0 16px rgba(173,255,0,0.3)' }}>估值重构炉</h1>
        </div>
        <p style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#777', margin: 0 }}>
          {schedulerRunning ? '引擎运转中' : '引擎已暂停'} · 每 {interval}s 轮询 · 已产出 {completedJobs.length} 份报告
        </p>
      </div>
```

- [ ] **Step 5: 渲染 JSX — 状态卡片行（4列）**

```tsx
      {/* Status Cards */}
      <div className="dash-card" style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: '12px', marginBottom: '20px' }}>
        <StatusCard
          label="SSE 连接"
          value={sseConnected ? '已连接' : '未连接'}
          color={sseConnected ? '#ADFF00' : '#FF5C00'}
          dot
        />
        <StatusCard
          label="调度器"
          value={schedulerRunning ? '运行中' : '已暂停'}
          color={schedulerRunning ? '#ADFF00' : '#666'}
          dot
        />
        <StatusCard
          label="上次轮询"
          value={lastPollAt ? new Date(lastPollAt).toLocaleTimeString('zh-CN') : '—'}
          color="#AAA"
        />
        <StatusCard
          label="下次轮询"
          value={nextPollAt ? new Date(nextPollAt).toLocaleTimeString('zh-CN') : '—'}
          color="#AAA"
        />
      </div>
```

其中 `StatusCard` 是文件内的辅助组件：

```tsx
function StatusCard({ label, value, color, dot }: { label: string; value: string; color: string; dot?: boolean }) {
  return (
    <div style={cardBase}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = `${color}30`; e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)'; e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; }}
    >
      <span style={labelStyle}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px' }}>
        {dot && <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}60`, animation: color === '#ADFF00' ? 'pulse 2s ease-in-out infinite' : 'none' }} />}
        <span style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '15px', color, fontWeight: 600 }}>{value}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: 渲染 JSX — 控制面板**

```tsx
      {/* Controls */}
      <div className="dash-card" style={{ ...cardBase, marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <ControlBtn label="▶ 启动" onClick={handleStart} disabled={schedulerRunning} color="#ADFF00" />
          <ControlBtn label="■ 停止" onClick={handleStop} disabled={!schedulerRunning} color="#FF5C00" />
          <ControlBtn label="⚡ 手动触发" onClick={handleTrigger} disabled={triggerLoading} color="#ADFF00" loading={triggerLoading} />
          <span style={{ flex: 1, height: '1px', background: '#2A2A2A' }} />
          <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#555', letterSpacing: '0.1em' }}>间隔</span>
          {[60, 300, 600, 1800].map((sec) => (
            <IntervalBtn key={sec} label={sec >= 60 ? `${sec / 60}m` : `${sec}s`} active={interval === sec} onClick={() => handleInterval(sec)} />
          ))}
        </div>
        {error && <p style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#FF5C00', marginTop: '12px' }}>{error}</p>}
      </div>
```

辅助组件：

```tsx
function ControlBtn({ label, onClick, disabled, color, loading }: { label: string; onClick: () => void; disabled?: boolean; color: string; loading?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      style={{
        fontFamily: "'Space Mono', monospace", fontSize: '12px',
        color: disabled ? '#444' : color,
        background: disabled ? 'transparent' : `${color}10`,
        border: `1px solid ${disabled ? '#333' : `${color}40`}`,
        padding: '8px 16px', cursor: disabled ? 'not-allowed' : 'pointer',
        letterSpacing: '0.1em', transition: 'all 0.2s',
        opacity: loading ? 0.6 : 1,
      }}
      onMouseEnter={(e) => { if (!disabled) { e.currentTarget.style.background = `${color}20`; e.currentTarget.style.borderColor = color; }}}
      onMouseLeave={(e) => { if (!disabled) { e.currentTarget.style.background = `${color}10`; e.currentTarget.style.borderColor = `${color}40`; }}}
    >
      {loading ? '处理中...' : label}
    </button>
  );
}

function IntervalBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      style={{
        fontFamily: "'Space Mono', monospace", fontSize: '11px',
        color: active ? '#ADFF00' : '#666',
        background: active ? 'rgba(173,255,0,0.08)' : 'transparent',
        border: active ? '1px solid rgba(173,255,0,0.3)' : '1px solid transparent',
        padding: '4px 10px', cursor: 'pointer', borderRadius: '3px',
        transition: 'all 0.2s',
      }}
      onMouseEnter={(e) => { if (!active) { e.currentTarget.style.color = '#ADFF00'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.2)'; }}}
      onMouseLeave={(e) => { if (!active) { e.currentTarget.style.color = '#666'; e.currentTarget.style.borderColor = 'transparent'; }}}
    >
      {label}
    </button>
  );
}
```

- [ ] **Step 7: 渲染 JSX — 活跃任务面板**

```tsx
      {/* Active Jobs */}
      {activeJobs.length > 0 && (
        <div className="dash-card" style={{ ...cardBase, marginBottom: '20px' }}>
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#AAA', letterSpacing: '0.15em', margin: '0 0 14px 0' }}>
            活跃任务 ({activeJobs.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {activeJobs.map((job, i) => {
              const prog = recentProgress.find((p) => p.stock_code === job.stock_code);
              return (
                <div key={`${job.stock_code}-${i}`}
                  style={{
                    padding: '12px 16px', background: 'rgba(255,255,255,0.02)',
                    borderLeft: `3px solid ${job.status === 'running' ? '#ADFF00' : '#666'}`,
                    border: '1px solid rgba(255,255,255,0.04)',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(173,255,0,0.15)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.04)'; }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px', fontWeight: 600, color: '#F2F4F3' }}>{job.stock_code}</span>
                      <span style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#AAA', marginLeft: '10px' }}>{job.stock_name}</span>
                    </div>
                    <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: job.status === 'running' ? '#ADFF00' : '#666', letterSpacing: '0.1em' }}>
                      {job.status === 'running' ? `处理中${prog ? ` · ${prog.step_name}` : ''}` : '排队中'}
                    </span>
                  </div>
                  {job.status === 'running' && prog && (
                    <div style={{ marginTop: '8px', height: '4px', background: 'rgba(255,255,255,0.06)', borderRadius: '2px', overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${(prog.step / prog.total_steps) * 100}%`, background: '#ADFF00', borderRadius: '2px', transition: 'width 0.3s' }} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
```

- [ ] **Step 8: 渲染 JSX — 已完成列表**

```tsx
      {/* Completed Jobs */}
      <div className="dash-card" style={cardBase}>
        <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#AAA', letterSpacing: '0.15em', margin: '0 0 14px 0' }}>
          已完成 ({completedJobs.length})
        </h3>
        {completedJobs.length === 0 ? (
          <p style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555', textAlign: 'center', padding: '32px 0' }}>
            暂无完成记录，等待调度器轮询或手动触发
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {[...completedJobs].reverse().map((job, i) => (
              <div key={`${job.stock_code}-${i}`}
                onClick={() => navigate(`/report/v4/${job.stock_code}`)}
                style={{
                  padding: '12px 16px', cursor: 'pointer',
                  background: i % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'rgba(255,255,255,0.03)',
                  borderLeft: '2px solid rgba(173,255,0,0.12)',
                  transition: 'all 0.2s',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(173,255,0,0.04)'; e.currentTarget.style.borderLeftColor = '#ADFF00'; e.currentTarget.style.transform = 'translateX(4px)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = i % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'rgba(255,255,255,0.03)'; e.currentTarget.style.borderLeftColor = 'rgba(173,255,0,0.12)'; e.currentTarget.style.transform = 'translateX(0)'; }}
              >
                <div>
                  <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px', fontWeight: 600, color: '#F2F4F3' }}>{job.stock_code}</span>
                  <span style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#AAA', marginLeft: '10px' }}>{job.stock_name}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#ADFF00' }}>✓ 完成</span>
                  <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#ADFF00', letterSpacing: '0.1em' }}>→ 查看报告</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  </div>
);
```

- [ ] **Step 9: 验证页面存在**

```bash
cd D:\长流水前端 && npx tsc --noEmit src/pages/Dashboard.tsx
```

Expected: 无错误（可能有一些未使用变量警告，可忽略）

---

### Task 4: 前端 — ValuationReport 页面

**Files:**
- Create: `src/pages/ValuationReport.tsx`

这是一个大页面，需要以下区块：
1. 报告头部（股票名/代码/元数据）
2. TOC 导航
3. 执行摘要（大数字 + 情景概率条 + 市值箭头）
4. BS检测器（反向DCF 表格）
5. 三情景推演表格
6. 置信度评分（维度条）
7. 交易标注（S1-S4）
8. KPI 追踪/时间线
9. 叙事

- [ ] **Step 1: 创建 ValuationReport.tsx — 框架 + 数据加载**

```tsx
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { navigationConfig } from '../config';
import { fetchReportData, type ReportData } from '../services/valuationApi';

function _n(v: unknown, d = '—'): string {
  if (v === null || v === undefined) return d;
  const f = parseFloat(String(v));
  if (isNaN(f)) return String(v);
  return f === Math.round(f) ? String(Math.round(f)) : f.toFixed(1);
}

function _tag(text: string, active: boolean) {
  return (
    <span style={{
      fontFamily: "'Space Mono', monospace", fontSize: '10px',
      color: active ? '#ADFF00' : '#666',
      border: `1px solid ${active ? 'rgba(173,255,0,0.3)' : '#333'}`,
      background: active ? 'rgba(173,255,0,0.06)' : 'transparent',
      padding: '2px 8px', letterSpacing: '0.1em',
    }}>{text}</span>
  );
}

export default function ValuationReport() {
  const { code } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const mobile = useMobile();
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeSection, setActiveSection] = useState('exec');

  useEffect(() => {
    if (!code) { setError('无效股票代码'); setLoading(false); return; }
    fetchReportData(code)
      .then(setData)
      .catch((e) => setError(`加载失败: ${e.message}`))
      .finally(() => setLoading(false));
  }, [code]);

  // 滚动高亮 TOC
  useEffect(() => {
    const handleScroll = () => {
      const sections = ['exec', 'bs', 'scenarios', 'confidence', 'trade', 'narrative'];
      for (const id of sections) {
        const el = document.getElementById(id);
        if (el) {
          const rect = el.getBoundingClientRect();
          if (rect.top < 200 && rect.bottom > 200) { setActiveSection(id); break; }
        }
      }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // ... 后续步骤
}
```

- [ ] **Step 2: 添加导航栏 + 头部 + TOC**

```tsx
  return (
    <div style={{ minHeight: '100vh', background: '#050401', color: '#F2F4F3' }}>
      <nav style={{ position: 'sticky', top: 0, zIndex: 50, display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: mobile ? '16px 20px' : '20px 48px', background: 'rgba(5,4,1,0.92)', backdropFilter: 'blur(6px)', borderBottom: '1px solid #2A2A2A' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: '#ADFF00', letterSpacing: '0.06em' }}>{navigationConfig.brandName}</span>
          <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#444', letterSpacing: '0.1em' }}>/ 估值重构报告</span>
        </div>
        <button onClick={() => navigate(-1)} style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#888', background: 'transparent', border: '1px solid #2A2A2A', padding: '8px 20px', cursor: 'pointer', letterSpacing: '0.1em' }}
          onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#ADFF00'; e.currentTarget.style.color = '#ADFF00'; }}
          onMouseLeave={(e) => { e.currentTarget.style.borderColor = '#2A2A2A'; e.currentTarget.style.color = '#888'; }}>
          ← 返回
        </button>
      </nav>

      <div style={{ maxWidth: '960px', margin: '0 auto', padding: mobile ? '24px 20px' : '32px 48px 64px' }}>
        {loading && <div style={{ padding: '80px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555' }}>加载估值报告中...</div>}
        {error && <div style={{ padding: '80px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#FF5C00' }}>{error}</div>}

        {data && (
          <>
            {/* Header */}
            <div style={{ marginBottom: '28px' }}>
              <h1 style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: mobile ? '28px' : '36px', fontWeight: 400, color: '#ADFF00', margin: '0 0 8px 0', letterSpacing: '0.06em', textShadow: '0 0 20px rgba(173,255,0,0.25)' }}>
                {String((data.agent1 as Record<string,unknown>)?.clean_financials as Record<string,unknown> | undefined)?.stock_name || code}
              </h1>
              <p style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#777', margin: 0 }}>
                {code} · 估值重构报告
              </p>
            </div>

            {/* TOC */}
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '32px', padding: '12px 16px', background: 'rgba(255,255,255,0.02)', border: '1px solid #2A2A2A' }}>
              {['exec','bs','scenarios','confidence','trade','narrative'].map((id) => (
                <a key={id} href={`#${id}`}
                  style={{
                    fontFamily: "'Space Mono', monospace", fontSize: '11px',
                    color: activeSection === id ? '#ADFF00' : '#666',
                    textDecoration: 'none', padding: '3px 10px', borderRadius: '3px',
                    border: activeSection === id ? '1px solid rgba(173,255,0,0.2)' : '1px solid transparent',
                    background: activeSection === id ? 'rgba(173,255,0,0.06)' : 'transparent',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#ADFF00'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = activeSection === id ? '#ADFF00' : '#666'; }}
                >
                  {{exec:'执行摘要',bs:'BS检测',scenarios:'三情景',confidence:'置信度',trade:'交易标注',narrative:'叙事'}[id]}
                </a>
              ))}
            </div>
```

- [ ] **Step 3: 添加执行摘要区块**

```tsx
            {/* Exec Summary */}
            <ReportSection id="exec" label="执行摘要" num="EXEC">
              {(() => {
                const a3 = data.agent3 as Record<string,unknown>;
                const vs = (a3?.valuation_summary || {}) as Record<string,unknown>;
                const upside = parseFloat(String(vs?.probability_weighted_upside_pct ?? 0));
                const asym = parseFloat(String(vs?.asymmetry_ratio ?? 0));
                const quality = vs?.quality_flag ?? '?';
                const a1 = data.agent1 as Record<string,unknown>;
                const cf = (a1?.clean_financials || {}) as Record<string,unknown>;
                const curMcap = _n(cf?.market_cap_billion);
                const tgtMcap = _n(vs?.probability_weighted_mcap_billion);
                const scenarios = (a3?.scenarios || []) as Array<Record<string,unknown>>;
                const bear = scenarios.find((s) => String(s?.name||'').toLowerCase().includes('bear')) || {};
                const base = scenarios.find((s) => String(s?.name||'').toLowerCase().includes('base')) || {};
                const bull = scenarios.find((s) => String(s?.name||'').toLowerCase().includes('bull')) || {};
                const bp = Number(bear?.probability_pct || 25);
                const bsp = Number(base?.probability_pct || 50);
                const blp = Number(bull?.probability_pct || 25);
                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
                      <BigNum val={`${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%`} label="概率加权涨幅" color={upside >= 0 ? '#ADFF00' : '#FF5C00'} />
                      <BigNum val={`${asym.toFixed(1)}x`} label="不对称比" color="#F2F4F3" />
                      <BigNum val={String(quality)} label="质量等级" color="#ADFF00" />
                    </div>
                    <div style={{ display: 'flex', height: '24px', borderRadius: '3px', overflow: 'hidden' }}>
                      <div style={{ flex: bp, background: 'rgba(255,92,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#F2F4F3' }}>Bear {bp}%</div>
                      <div style={{ flex: bsp, background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#F2F4F3' }}>Base {bsp}%</div>
                      <div style={{ flex: blp, background: 'rgba(173,255,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#050401' }}>Bull {blp}%</div>
                    </div>
                    <p style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#777', textAlign: 'center', margin: 0 }}>
                      当前市值 <span style={{ color: '#F2F4F3', fontWeight: 600 }}>{curMcap}亿</span> → 目标 <span style={{ color: '#ADFF00', fontWeight: 600 }}>{tgtMcap}亿</span>
                    </p>
                  </div>
                );
              })()}
            </ReportSection>
```

辅助组件 `ReportSection` 和 `BigNum`：

```tsx
function ReportSection({ id, label, num, children }: { id: string; label: string; num: string; children: React.ReactNode }) {
  return (
    <div id={id} style={{ marginBottom: '24px', padding: '24px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px', paddingBottom: '10px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#ADFF00', background: 'rgba(173,255,0,0.08)', padding: '2px 8px', letterSpacing: '0.1em' }}>{num}</span>
        <h2 style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#AAA', margin: 0, letterSpacing: '0.15em' }}>{label}</h2>
      </div>
      {children}
    </div>
  );
}

function BigNum({ val, label, color }: { val: string; label: string; color: string }) {
  return (
    <div style={{ textAlign: 'center', padding: '20px 16px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
      <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '28px', fontWeight: 700, color, lineHeight: 1.1 }}>{val}</div>
      <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#555', marginTop: '4px', letterSpacing: '0.1em' }}>{label}</div>
    </div>
  );
}
```

- [ ] **Step 4: 添加 BS检测器 + 三情景 + 置信度 + 交易标注**

BS检测器渲染（简版 — 从 agent1.market_sanity 取数据并渲染为表格）：

```tsx
            {/* BS Detector */}
            <ReportSection id="bs" label="BS检测器 (反向DCF)" num="BS">
              {(() => {
                const a1 = data.agent1 as Record<string,unknown>;
                const sanity = (a1?.market_sanity || {}) as Record<string,unknown>;
                const rows: Array<[string, string]> = [
                  ['BS 等级', String(sanity?.bs_level || '?')],
                  ['EV', `${_n(sanity?.ev_billion)}亿`],
                  ['NOPAT', `${_n(sanity?.nopat_billion)}亿`],
                  ['ROIC', `${_n(sanity?.roic_pct)}%`],
                  ['WACC', `${_n(sanity?.wacc_simple_pct)}%`],
                  ['隐含 g', `${_n(sanity?.implied_g_pct)}%`],
                  ['市场溢价', `${_n(sanity?.market_premium_pct)}%`],
                  ['PE(TTM)', `${_n(sanity?.pe_ttm)}x`],
                  ['PE分位', `${_n(sanity?.pe_historical_rank)}`],
                ];
                return <KvTable rows={rows} />;
              })()}
            </ReportSection>

            {/* Scenarios */}
            <ReportSection id="scenarios" label="三情景推演" num="S">
              {(() => {
                const a3 = data.agent3 as Record<string,unknown>;
                const scenarios = (a3?.scenarios || []) as Array<Record<string,unknown>>;
                return (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: "'IBM Plex Mono', monospace", fontSize: '13px' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #2A2A2A' }}>
                        {['情景','概率','ROIC','PE','目标市值','涨跌幅'].map((h) => (
                          <th key={h} style={{ padding: '8px 12px', textAlign: h === '情景' ? 'left' : 'right', color: '#777', fontSize: '11px', fontFamily: "'Space Mono', monospace", fontWeight: 400, letterSpacing: '0.1em' }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {scenarios.map((s, i) => {
                        const u = parseFloat(String(s?.upside_pct ?? 0));
                        return (
                          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                            <td style={{ padding: '10px 12px', color: '#F2F4F3', fontWeight: 600 }}>{String(s?.name || '?')}</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: '#AAA' }}>{_n(s?.probability_pct)}%</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: '#AAA' }}>{_n(s?.roic_pct)}%</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: '#AAA' }}>{_n(s?.pe_target)}x</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: '#AAA' }}>{_n(s?.target_mcap_billion)}亿</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: u >= 0 ? '#ADFF00' : '#FF5C00', fontWeight: 600 }}>{u >= 0 ? '+' : ''}{u.toFixed(1)}%</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                );
              })()}
            </ReportSection>

            {/* Confidence */}
            <ReportSection id="confidence" label="置信度评分" num="C">
              {(() => {
                const a3 = data.agent3 as Record<string,unknown>;
                const conf = (a3?.confidence || {}) as Record<string,unknown>;
                const dims = (conf?.dimensions || {}) as Record<string, Record<string,unknown>>;
                return (
                  <div>
                    <p style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: '#ADFF00', margin: '0 0 12px 0' }}>
                      {_n(conf?.overall_score)}/10 <span style={{ fontSize: '14px', color: '#AAA', fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace" }}>{String(conf?.overall_label || '')}</span>
                    </p>
                    {Object.entries(dims).map(([key, d]) => {
                      const score = Number(d?.score || 5);
                      const pct = Math.min(100, Math.max(0, (score / 10) * 100));
                      return (
                        <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
                          <span style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '12px', color: '#888', width: '80px', flexShrink: 0 }}>{String(d?.label || key)}</span>
                          <div style={{ flex: 1, height: '4px', background: 'rgba(255,255,255,0.06)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${pct}%`, background: score >= 7 ? '#ADFF00' : score >= 4 ? '#FF5C00' : '#666', borderRadius: '2px' }} />
                          </div>
                          <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#AAA', width: '36px', textAlign: 'right' }}>{score}/10</span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </ReportSection>

            {/* Trade Annotation */}
            <ReportSection id="trade" label="交易标注" num="T">
              {(() => {
                const a3 = data.agent3 as Record<string,unknown>;
                const ta = (a3?.trade_annotation || {}) as Record<string,unknown>;
                const signals = (ta?.alignment_signals || []) as string[];
                const scores = (ta?.dimension_scores || {}) as Record<string, number>;
                const labels: Record<string, string> = { odds_quality: 'S1 赔率质量', pricing_headroom: 'S2 定价空间', transmission_confidence: 'S3 传导确定性', model_consistency: 'S4 模型自洽' };
                return (
                  <div>
                    <p style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#F2F4F3', margin: '0 0 12px 0' }}>
                      {String(ta?.tier || '?')} <span style={{ color: '#888', fontSize: '12px' }}>({String(ta?.total_score || '?')})</span>
                    </p>
                    {Object.entries(labels).map(([key, label]) => {
                      const s = Number(scores?.[key] || 0);
                      return (
                        <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px' }}>
                          <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#888', width: '120px', flexShrink: 0 }}>{label}</span>
                          <div style={{ flex: 1, height: '4px', background: 'rgba(255,255,255,0.06)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${(s / 10) * 100}%`, background: '#ADFF00', borderRadius: '2px' }} />
                          </div>
                          <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#AAA' }}>{s}</span>
                        </div>
                      );
                    })}
                    <ul style={{ listStyle: 'none', marginTop: '12px' }}>
                      {signals.map((s, i) => (
                        <li key={i} style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#AAA', padding: '2px 0' }}>• {s}</li>
                      ))}
                    </ul>
                    <p style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#ADFF00', marginTop: '10px' }}>
                      <strong>建议:</strong> {String(ta?.suggested_action || '—')}
                    </p>
                  </div>
                );
              })()}
            </ReportSection>

            {/* Narrative */}
            <ReportSection id="narrative" label="叙事" num="N">
              <p style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '15px', lineHeight: 2.0, color: '#AAA', whiteSpace: 'pre-wrap' }}>
                {String((data.agent3 as Record<string,unknown>)?.narrative || '暂无叙事')}
              </p>
            </ReportSection>
          </>
        )}
      </div>
    </div>
  );
}
```

加上 `KvTable` 辅助组件：

```tsx
function KvTable({ rows }: { rows: Array<[string, string]> }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: "'IBM Plex Mono', monospace", fontSize: '13px' }}>
      <tbody>
        {rows.map(([k, v], i) => (
          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            <td style={{ padding: '8px 16px', color: '#777', width: '140px', fontFamily: "'Space Mono', monospace", fontSize: '11px', letterSpacing: '0.1em' }}>{k}</td>
            <td style={{ padding: '8px 16px', color: k === 'BS 等级' ? '#ADFF00' : '#CCC', fontWeight: k.includes('等级') ? 600 : 400 }}>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 5: 把辅助组件移到文件顶部（在 import 和 export default 之间）**

确保 `BigNum`, `ReportSection`, `KvTable` 都在 `export default function ValuationReport()` 之前定义。

- [ ] **Step 6: 验证页面完整**

```bash
cd D:\长流水前端 && npx tsc --noEmit src/pages/ValuationReport.tsx
```

Expected: 无错误。

---

### Task 5: 前端 — 挂载路由

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: 在 App.tsx 中添加导入和路由**

在现有 imports 之后添加：

```tsx
import Dashboard from './pages/Dashboard';
import ValuationReport from './pages/ValuationReport';
```

在 `<Routes>` 内、`</Routes>` 之前添加两条路由：

```tsx
<Route path="/dashboard" element={<Dashboard />} />
<Route path="/report/v4/:code" element={<ValuationReport />} />
```

最终 App.tsx 的 Routes 区块应为：

```tsx
<Routes>
  <Route path="/" element={<Home />} />
  <Route path="/facility/:slug" element={<FacilityDetail />} />
  <Route path="/report/:id" element={<ReportDetail />} />
  <Route path="/report/v4/:code" element={<ValuationReport />} />
  <Route path="/agent-config" element={<AgentConfig />} />
  <Route path="/avatar" element={<AgentAvatar />} />
  <Route path="/dashboard" element={<Dashboard />} />
</Routes>
```

- [ ] **Step 2: TypeScript 编译检查**

```bash
cd D:\长流水前端 && npx tsc --noEmit
```

Expected: 无新增错误。

---

### Task 6: 集成验证

- [ ] **Step 1: 启动 Python 后端**

```bash
cd D:\长流水前端\估值重构引擎_V4 && python valuation_app/server.py &
```
验证: 访问 `http://localhost:8081/api/status` 返回 JSON。

- [ ] **Step 2: 启动 Vite 前端**

```bash
cd D:\长流水前端 && npm run dev
```

- [ ] **Step 3: 检查仪表盘页面**

访问 `http://localhost:5173/dashboard`：
- 导航栏显示 "长流水 / 估值重构仪表盘"
- SSE 连接状态显示
- 控制按钮可见
- 无控制台报错

- [ ] **Step 4: 检查估值报告页面**

如果有已生成的报告数据，访问 `http://localhost:5173/report/v4/{stock_code}`：
- 报告头部显示股票名
- TOC 导航可点击
- 执行摘要/场景等区块渲染正常
- 无控制台报错

- [ ] **Step 5: 运行 lint**

```bash
cd D:\长流水前端 && npm run lint
```
修复任何新增的 lint 问题。

---

## Plan Completion Checklist

- [ ] Task 1: Python 后端 CORS + JSON 持久化
- [ ] Task 2: valuationApi 服务层
- [ ] Task 3: Dashboard 页面
- [ ] Task 4: ValuationReport 页面
- [ ] Task 5: 路由挂载
- [ ] Task 6: 集成验证
