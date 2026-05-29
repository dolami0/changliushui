// 宗门控制台 — 调度器 + 望气独立管理后台
// 通过 Vite proxy /admin/api/* → admin-server:3002

import { useEffect, useState, useCallback } from 'react';
import { useMobile } from '../hooks/useMobile';

const cardBase: React.CSSProperties = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.06)',
  padding: '20px 24px',
  transition: 'all 0.3s ease',
};

function StatusCard({ label, value, color, dot }: { label: string; value: string; color: string; dot?: boolean }) {
  return (
    <div style={cardBase}>
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#777', letterSpacing: '0.15em' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px' }}>
        {dot && <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}60` }} />}
        <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '15px', color, fontWeight: 600 }}>{value}</span>
      </div>
    </div>
  );
}

function ControlBtn({ label, onClick, disabled, color, loading }: {
  label: string; onClick: () => void; disabled?: boolean; color: string; loading?: boolean;
}) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      fontFamily: "'Space Mono', monospace", fontSize: '15px', color: disabled ? '#444' : color,
      background: disabled ? 'transparent' : `${color}10`,
      border: `1px solid ${disabled ? '#333' : `${color}40`}`,
      padding: '8px 16px', cursor: disabled ? 'not-allowed' : 'pointer',
      letterSpacing: '0.1em', transition: 'all 0.2s', opacity: loading ? 0.6 : 1,
    }}>
      {loading ? '处理中...' : label}
    </button>
  );
}

// ── API 调用 (通过 /admin/api/* → admin-server) ──

const ADMIN = '/admin';

async function fetchSchedulerStatus() {
  const r = await fetch(`${ADMIN}/api/scheduler/status`);
  return r.json() as Promise<{ running: boolean; interval_minutes: number; active_jobs: number; completed_jobs: number; last_poll_at: string | null }>;
}
async function startScheduler() { await fetch(`${ADMIN}/api/scheduler/start`, { method: 'POST' }); }
async function stopScheduler() { await fetch(`${ADMIN}/api/scheduler/stop`, { method: 'POST' }); }
async function setInterval(seconds: number) {
  await fetch(`${ADMIN}/api/scheduler/interval`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ interval_sec: seconds }),
  });
}
async function triggerPipeline() {
  const r = await fetch(`${ADMIN}/api/trigger`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ stock_code: '' }) });
  return r.json() as Promise<{ accepted: boolean; error?: string }>;
}

async function fetchWangqiStatus() {
  const r = await fetch(`${ADMIN}/api/industry-chain/status`);
  return r.json() as Promise<{
    scheduler: { initialized: boolean; running: boolean; interval_sec: number; last_poll_at: string | null; next_poll_at: string | null; completed_count: number; completed_jobs: { top_pick?: string; runner_up?: string }[] };
  }>;
}
async function startWangqi() { await fetch(`${ADMIN}/api/industry-chain/start`, { method: 'POST' }); }
async function stopWangqi() { await fetch(`${ADMIN}/api/industry-chain/stop`, { method: 'POST' }); }
async function triggerWangqi() { await fetch(`${ADMIN}/api/industry-chain/trigger`, { method: 'POST' }); }

async function triggerReview() {
  const r = await fetch(`${ADMIN}/api/review/trigger`, { method: 'POST' });
  return r.json() as Promise<{ status: string; reviewed: number; health: string; grade_distribution: Record<string, number> }>;
}

// ── 组件 ──────────────────────────────────────

export default function Admin() {
  const mobile = useMobile();

  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [schedulerStatus, setSchedulerStatus] = useState<{ interval_minutes: number; active_jobs: number; completed_jobs: number; last_poll_at: string | null }>({ interval_minutes: 10, active_jobs: 0, completed_jobs: 0, last_poll_at: null });
  const [wangqiRunning, setWangqiRunning] = useState(false);
  const [wangqiStatus, setWangqiStatus] = useState<{ interval_sec: number; completed_count: number; last_poll_at: string | null; completed_jobs: { top_pick?: string; runner_up?: string }[] }>({ interval_sec: 3600, completed_count: 0, last_poll_at: null, completed_jobs: [] });
  const [msg, setMsg] = useState<{ text: string; color: string } | null>(null);
  const [intervalInput, setIntervalInput] = useState('600');

  const toast = (text: string, color: string) => {
    setMsg({ text, color });
    setTimeout(() => setMsg(null), 4000);
  };

  const refresh = useCallback(async () => {
    try {
      const s = await fetchSchedulerStatus();
      setSchedulerRunning(s.running);
      setSchedulerStatus({ interval_minutes: s.interval_minutes, active_jobs: s.active_jobs, completed_jobs: s.completed_jobs, last_poll_at: s.last_poll_at });
    } catch { /* 后端未启动 */ }
    try {
      const w = await fetchWangqiStatus();
      setWangqiRunning(w.scheduler.running);
      setWangqiStatus({ interval_sec: w.scheduler.interval_sec, completed_count: w.scheduler.completed_count, last_poll_at: w.scheduler.last_poll_at, completed_jobs: w.scheduler.completed_jobs || [] });
    } catch { /* 后端未启动 */ }
  }, []);

  useEffect(() => { refresh(); const id = setInterval(refresh, 10_000); return () => clearInterval(id); }, [refresh]);

  return (
    <div style={{ minHeight: 'calc(100vh - 58px)', background: '#050401', color: '#F2F4F3' }}>
      <div style={{ maxWidth: '960px', margin: '0 auto', padding: mobile ? '24px 20px 48px' : '32px 48px 64px' }}>
        <h1 style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '28px', color: '#ADFF00', letterSpacing: '0.06em', textShadow: '0 0 16px rgba(173,255,0,0.3)', marginBottom: '24px' }}>宗门控制台</h1>

        {msg && (
          <div style={{ ...cardBase, marginBottom: '16px', borderColor: `${msg.color}30`, background: `${msg.color}08` }}>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: msg.color }}>{msg.text}</span>
          </div>
        )}

        {/* ── 估值调度器 ── */}
        <div style={cardBase} className="dash-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
            <span style={{ width: '8px', height: '8px', background: schedulerRunning ? '#ADFF00' : '#444', boxShadow: schedulerRunning ? '0 0 8px rgba(173,255,0,0.5)' : 'none' }} />
            <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00', letterSpacing: '0.06em' }}>估值调度器</span>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#666' }}>V6 管线</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: '12px', marginBottom: '16px' }}>
            <StatusCard label="状态" value={schedulerRunning ? '运行中' : '已暂停'} color={schedulerRunning ? '#ADFF00' : '#666'} dot />
            <StatusCard label="间隔" value={`${schedulerStatus.interval_minutes}分钟`} color="#AAA" />
            <StatusCard label="活跃任务" value={String(schedulerStatus.active_jobs)} color="#C88D3A" />
            <StatusCard label="已完成" value={String(schedulerStatus.completed_jobs)} color="#ADFF00" />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
            <ControlBtn label="▶ 启动" onClick={async () => { await startScheduler(); setSchedulerRunning(true); toast('调度器已启动', '#ADFF00'); }} disabled={schedulerRunning} color="#ADFF00" />
            <ControlBtn label="■ 停止" onClick={async () => { await stopScheduler(); setSchedulerRunning(false); toast('调度器已停止', '#FF5C00'); }} disabled={!schedulerRunning} color="#FF5C00" />
          </div>

          <div style={{ borderTop: '1px solid #2A2A2A', paddingTop: '12px', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555' }}>间隔(秒):</span>
            <input value={intervalInput} onChange={(e) => setIntervalInput(e.target.value)}
              style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#ADFF00', background: '#121212', border: '1px solid #333', padding: '4px 8px', width: '80px' }} />
            <ControlBtn label="设置" onClick={async () => { await setInterval(Number(intervalInput)); toast(`间隔已设为 ${intervalInput}秒`, '#ADFF00'); }} color="#888" />
            <span style={{ flex: 1 }} />
            {schedulerStatus.last_poll_at && (
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#444' }}>
                上次: {new Date(schedulerStatus.last_poll_at).toLocaleTimeString('zh-CN')}
              </span>
            )}
          </div>
        </div>

        {/* ── 望气 ── */}
        <div style={{ ...cardBase, marginTop: '20px' }} className="dash-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
            <span style={{ width: '8px', height: '8px', background: wangqiRunning ? '#C88D3A' : '#444', boxShadow: wangqiRunning ? '0 0 8px rgba(200,141,58,0.5)' : 'none' }} />
            <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#C88D3A', letterSpacing: '0.06em' }}>望气</span>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#666' }}>产业利润流</span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(3, 1fr)', gap: '12px', marginBottom: '16px' }}>
            <StatusCard label="状态" value={wangqiRunning ? '运转中' : '已暂停'} color={wangqiRunning ? '#C88D3A' : '#666'} dot />
            <StatusCard label="间隔" value={`${Math.floor((wangqiStatus.interval_sec || 3600) / 60)}分钟`} color="#AAA" />
            <StatusCard label="已完成" value={`${wangqiStatus.completed_count}次`} color="#C88D3A" />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <ControlBtn label="▶ 启动" onClick={async () => { await startWangqi(); setWangqiRunning(true); toast('望气已启动', '#C88D3A'); }} disabled={wangqiRunning} color="#C88D3A" />
            <ControlBtn label="■ 停止" onClick={async () => { await stopWangqi(); setWangqiRunning(false); toast('望气已停止', '#FF5C00'); }} disabled={!wangqiRunning} color="#FF5C00" />
            <ControlBtn label="⚡ 洞察" onClick={async () => { await triggerWangqi(); toast('洞察已触发', '#C88D3A'); }} color="#C88D3A" />
          </div>

          {wangqiStatus.completed_jobs.length > 0 && (
            <div style={{ marginTop: '14px', borderTop: '1px solid #2A2A2A', paddingTop: '10px' }}>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555', marginRight: '16px' }}>最近洞察</span>
              {wangqiStatus.completed_jobs.slice(-3).reverse().map((j, i) => (
                <span key={i} style={{ fontSize: '14px', color: i === 0 ? '#C88D3A' : '#888', marginRight: '24px' }}>
                  {j.top_pick || '无标的'}
                  {j.runner_up ? ` | ${j.runner_up}` : ''}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* ── 审阅 ── */}
        <div style={{ ...cardBase, marginTop: '20px' }} className="dash-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00', letterSpacing: '0.06em' }}>审阅</span>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#666' }}>报告质量审核</span>
            <span style={{ flex: 1 }} />
            <ControlBtn label="🔍 执行审阅" onClick={async () => {
              try {
                const res = await triggerReview();
                toast(`审阅完成 · ${res.reviewed}份 · ${res.health || '?'}`, '#ADFF00');
              } catch { toast('审阅失败', '#FF5C00'); }
            }} color="#ADFF00" />
          </div>
        </div>

        <p style={{ marginTop: '48px', fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#222', textAlign: 'center' }}>
          估值重构引擎 V6 · 宗门控制台 · 独立于前端运行
        </p>
      </div>
    </div>
  );
}
