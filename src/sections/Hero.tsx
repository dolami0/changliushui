import AsciiCanvas from '../components/AsciiCanvas';
import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { useMobile } from '../hooks/useMobile';
import { useBackendHealth } from '../hooks/useBackendHealth';
import { fetchDingshulu, fetchTianjijuan, fetchDingshuluCount, fetchAll } from '../services/cozeApi';
import { fetchStatus, createProgressStream } from '../services/valuationApi';
import { DingshuluPanel, TianyanPanel, TrackingPanel } from './PanoramicMonitor';

/* ------------------------------------------------------------------ */
/*  Countdown                                                         */
/* ------------------------------------------------------------------ */
function CountdownTimer() {
  const [remaining, setRemaining] = useState('');
  useEffect(() => {
    const calc = () => {
      const now = new Date();
      const next = new Date(now);
      next.setHours(now.getHours() + 1, 0, 0, 0);
      const m = Math.floor((next.getTime() - now.getTime()) / 60000);
      const s = Math.floor(((next.getTime() - now.getTime()) % 60000) / 1000);
      setRemaining(`${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`);
    };
    calc();
    const i = setInterval(calc, 1000);
    return () => clearInterval(i);
  }, []);

  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px' }}>
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#555', letterSpacing: '0.12em' }}>
        下次启动
      </span>
      <span style={{
        fontFamily: "'Geist Pixel', monospace", fontSize: '24px', color: '#ADFF00',
        textShadow: '0 0 12px rgba(173,255,0,0.35)', letterSpacing: '0.06em',
      }}>
        {remaining}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SpiritLamp — 灵灯：估值炉运转状态                                     */
/* ------------------------------------------------------------------ */
const STAGE_ORDER = ['agent0', 'agent1', 'agent2', 'agent3', 'report'];

function SpiritLamp() {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [lastError, setLastError] = useState(false);
  const [countdown, setCountdown] = useState('--:--');
  const [processing, setProcessing] = useState(false);
  const [currentStock, setCurrentStock] = useState({ code: '', name: '' });
  const [queuedJobs, setQueuedJobs] = useState<Array<{ code: string; name: string; status: string }>>([]);
  const [recentDone, setRecentDone] = useState<Array<{ code: string; name: string; time: string }>>([]);
  const [totalCompleted, setTotalCompleted] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const nextPollRef = useRef<string | null>(null);
  const stageMapRef = useRef<Record<string, number>>({});
  const elapsedAccRef = useRef(0);
  const jobResultsRef = useRef<Record<string, { elapsed: number; ok: boolean }>>({});
  const [pendingStocks, setPendingStocks] = useState<Array<{ code: string; name: string }>>([]);
  const [triggering, setTriggering] = useState(false);
  const [, setJobResultsTick] = useState(0);

  useEffect(() => {
    const tick = () => {
      fetchStatus().then((s) => {
        const wasRunning = nextPollRef.current !== null;
        setRunning(s.scheduler_running);
        nextPollRef.current = s.next_poll_at;
        setQueuedJobs((s.active_jobs || []).map((j: { stock_code: string; stock_name: string; status: string }) => ({ code: j.stock_code, name: j.stock_name, status: j.status })));
        const done2 = (s.completed_jobs || []).slice(-1).map((j: { stock_code: string; stock_name: string; completed_at: string }) => ({
          code: j.stock_code, name: j.stock_name,
          time: j.completed_at ? new Date(j.completed_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' }) : '',
        }));
        setRecentDone(done2);
        if (!wasRunning && s.scheduler_running) {
          setLastError(false);
          setErrorMsg('');
          stageMapRef.current = {};
          elapsedAccRef.current = 0;
          setCurrentStock({ code: '', name: '' });
        }
        if (!s.scheduler_running) { setProgress(0); setProcessing(false); setCurrentStock({ code: '', name: '' }); }
        // running 但 SSE 还没连接时保持旧进度，不重置
      }).catch(() => {});
    };
    tick();
    fetchDingshuluCount().then(setTotalCompleted).catch(() => {});
    fetchAll<{ stock_code: string; stock_name: string }>('7639784337973477386', 10, {
      conditions: [{ left: 'is_complete', operation: 'equal', right: 'false' }],
    }).then(items => {
      fetchStatus().then(s => {
        const activeCodes = new Set((s.active_jobs || []).map((j: { stock_code: string }) => j.stock_code));
        setPendingStocks(
          items.filter(r => !activeCodes.has(r.stock_code))
            .map(r => ({ code: r.stock_code, name: r.stock_name }))
        );
      }).catch(() => {});
    }).catch(() => {});
    const id = setInterval(tick, 15_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const calc = () => {
      const npr = nextPollRef.current;
      if (!npr) { setCountdown('--:--'); return; }
      const diff = Math.max(0, new Date(npr).getTime() - Date.now());
      setCountdown(`${String(Math.floor(diff / 60000)).padStart(2, '0')}:${String(Math.floor((diff % 60000) / 1000)).padStart(2, '0')}`);
    };
    calc();
    const id = setInterval(calc, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const es = createProgressStream((e) => {
      setProcessing(true);
      if (e.status === 'error') { setLastError(true); setErrorMsg(e.error_msg || ''); }
      if (e.total_steps > 0) stageMapRef.current[e.stage] = e.step / e.total_steps;
      setCurrentStock({ code: e.stock_code || '', name: e.stock_name || '' });
      if (e.elapsed_s > 0) elapsedAccRef.current = e.elapsed_s;
      if (e.stage === 'report' && (e.status === 'done' || e.status === 'error') && e.stock_code) {
        jobResultsRef.current[e.stock_code] = { elapsed: elapsedAccRef.current, ok: e.status === 'done' };
        setJobResultsTick(t => t + 1); // 触发重渲染
      }
      // 找到最远已触及的阶段索引，之前阶段视为已完成
      let maxIdx = -1;
      for (let i = STAGE_ORDER.length - 1; i >= 0; i--) {
        if (stageMapRef.current[STAGE_ORDER[i]] !== undefined) { maxIdx = i; break; }
      }
      let overall = 0;
      for (let i = 0; i < STAGE_ORDER.length; i++) {
        if (i < maxIdx) { overall += 20; }
        else if (i === maxIdx) {
          const p = stageMapRef.current[STAGE_ORDER[i]] || 0;
          overall += p * 20;
        }
      }
      setProgress(Math.round(overall));
    });
    return () => es.close();
  }, []);

  return (
    <div style={{
      flexShrink: 0,
      position: 'relative',
      background: 'rgba(255,255,255,0.03)',
      backdropFilter: 'blur(8px)',
      WebkitBackdropFilter: 'blur(8px)',
      borderRadius: '6px',
      border: `1px solid ${processing ? 'rgba(173,255,0,0.35)' : 'rgba(255,255,255,0.04)'}`,
      boxShadow: processing ? '0 0 24px rgba(173,255,0,0.12), inset 0 0 24px rgba(173,255,0,0.04)' : 'none',
      padding: '14px 16px',
      display: 'flex', flexDirection: 'column', gap: '6px',
      height: '100%',
      transition: 'border 0.5s ease, box-shadow 0.5s ease, background 0.3s ease',
      overflow: 'hidden',
    }}
      onMouseEnter={(e) => {}}
      onMouseLeave={(e) => {}}
    >
      {/* 内容层 */}
      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', gap: '6px', height: '100%' }}>
      {/* 运转状态 + 进度 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: running ? '#ADFF00' : '#888', letterSpacing: '0.05em' }}>
          {running ? '运转中' : '待命'}
        </span>
        {running && (
          <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '22px', color: '#ADFF00', textShadow: '0 0 12px rgba(173,255,0,0.35)', marginLeft: 'auto' }}>
            {progress > 0 ? `${progress}%` : '...'}
          </span>
        )}
      </div>
      {/* 处理中 + 排队 + 已完成列表 */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {queuedJobs.filter(q => q.status === 'running').map((q, i) => {
          const isSSE = processing && currentStock.code === q.code;
          return (
            <div key={`run-${i}`} style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#ADFF00', border: '1px solid rgba(173,255,0,0.25)', padding: '0px 4px', flexShrink: 0 }}>处理中</span>
              <span style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '14px', fontWeight: 600, color: '#F2F4F3' }}>{q.name}</span>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#888' }}>{q.code}</span>
              <span style={{ flex: 1 }} />
              <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '13px', color: '#ADFF00' }}>{isSSE ? `${progress}%` : '启动中'}</span>
            </div>
          );
        })}
        {queuedJobs.filter(q => q.status !== 'running' && !recentDone.some(d => d.code === q.code)).slice(0, 3).map((q, i) => {
          const res = jobResultsRef.current[q.code];
          return (
            <div key={`q-${i}`} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '2px 0' }}>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#777', border: '1px solid rgba(255,255,255,0.08)', padding: '0px 4px', flexShrink: 0 }}>排队</span>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#999' }}>{q.code}</span>
              <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '12px', color: '#AAA', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q.name}</span>
              <span style={{ flex: 1 }} />
              {res ? (
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: res.ok ? '#999' : '#FF5C00' }}>
                  {res.ok ? '✓' : '✗'} {res.elapsed >= 60 ? `${Math.floor(res.elapsed / 60)}m` : `${Math.floor(res.elapsed)}s`}
                </span>
              ) : (
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#555' }}>—</span>
              )}
            </div>
          );
        })}
        {recentDone.map((d, i) => {
          const res = jobResultsRef.current[d.code];
          return (
            <div key={`d-${i}`} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '2px 0' }}>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#AAA', border: '1px solid rgba(255,255,255,0.06)', padding: '0px 4px', flexShrink: 0 }}>完成</span>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#999' }}>{d.code}</span>
              <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '12px', color: '#AAA', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
              <span style={{ flex: 1 }} />
              {res ? (
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: res.ok ? '#999' : '#FF5C00' }}>
                  {res.ok ? '✓' : '✗'} {res.elapsed >= 60 ? `${Math.floor(res.elapsed / 60)}m` : `${Math.floor(res.elapsed)}s`}
                </span>
              ) : (
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#555' }}>{d.time}</span>
              )}
            </div>
          );
        })}
        {queuedJobs.length === 0 && recentDone.length === 0 && !processing && (
          <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#555', paddingTop: '6px' }}>队列空闲</div>
        )}
      </div>
      {/* 五阶段管线 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0' }}>
        {STAGE_ORDER.map((sid, i) => {
          const p = stageMapRef.current[sid];
          const done = p !== undefined && p >= 1;
          const cur = processing && p !== undefined && p > 0 && p < 1;
          const dot = cur ? '◎' : done ? '●' : '○';
          const c = cur ? '#ADFF00' : done ? '#C88D3A' : '#444';
          return (
            <span key={sid} style={{ display: 'flex', alignItems: 'center' }}>
              {i > 0 && <span style={{ width: '18px', height: '1px', background: done ? 'rgba(200,141,58,0.25)' : 'rgba(255,255,255,0.05)', flexShrink: 0 }} />}
              <span style={{
                fontSize: cur ? '11px' : '8px', color: c,
                textShadow: cur ? '0 0 6px rgba(173,255,0,0.4)' : 'none',
                animation: cur ? 'pulse 2s ease-in-out infinite' : 'none',
                lineHeight: 1,
              }}>{dot}</span>
            </span>
          );
        })}
      </div>
      {/* 错误信息 */}
      {errorMsg && (
        <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#FF5C00', padding: '2px 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {errorMsg}
        </div>
      )}
      {/* 手动触发 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <button
          onClick={() => { if (processing) return; setTriggering(true); setPendingStocks([]); fetch('/api/trigger', { method: 'POST' }).finally(() => setTriggering(false)); }}
          disabled={processing}
          style={{
            flex: 1, padding: '5px 0', border: 'none', borderRadius: '4px',
            background: processing ? 'rgba(255,255,255,0.03)' : 'rgba(173,255,0,0.08)',
            color: processing ? '#555' : '#ADFF00',
            fontFamily: "'Space Mono', monospace", fontSize: '11px', letterSpacing: '0.06em',
            cursor: processing ? 'default' : 'pointer', transition: 'all 0.2s',
            opacity: processing ? 0.4 : 1,
          }}
          onMouseEnter={(e) => { if (!processing) e.currentTarget.style.background = 'rgba(173,255,0,0.15)'; }}
          onMouseLeave={(e) => { if (!processing) e.currentTarget.style.background = 'rgba(173,255,0,0.08)'; }}
        >{processing ? '管线处理中' : triggering ? '触发中…' : '⟐ 手动触发'}</button>
        {pendingStocks.length > 0 && (
          <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#C88D3A', flexShrink: 0 }}>待拉取 {pendingStocks.length}</span>
        )}
      </div>
      {/* 待拉取标的 */}
      {pendingStocks.length > 0 && (
        <div style={{ maxHeight: '60px', overflow: 'hidden' }}>
          {pendingStocks.slice(0, 4).map((p, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '1px 0' }}>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#C88D3A', opacity: 0.5 }}>待</span>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#777' }}>{p.code}</span>
              <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '10px', color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.name}</span>
            </div>
          ))}
        </div>
      )}
      {/* 底栏 — 倒计时 + 总量 */}
      <div style={{ display: 'flex', alignItems: 'center', paddingTop: '5px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#777' }}>下次启动</span>
        <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '14px', color: '#BBB', marginLeft: '6px' }}>{countdown}</span>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#777' }}>累计 {totalCompleted}</span>
      </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  TodayReports                                                       */
/* ------------------------------------------------------------------ */
const TIER_STYLE: Record<string, { color: string }> = {
  '★★★': { color: '#ADFF00' },
  '★★☆': { color: '#FF8C00' },
  '★☆☆': { color: '#666' },
};

const QUALITY_LABEL: Record<string, { text: string; color: string }> = {
  'HIGH_QUALITY': { text: '优', color: '#ADFF00' },
  'SPECULATIVE': { text: '投机', color: '#FF8C00' },
  'LOW_QUALITY': { text: '低质', color: '#666' },
};

function TodayReports() {
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const [reports, setReports] = useState<Array<DingshuluRecord & { newsTitle?: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([fetchDingshulu(), fetchTianjijuan()])
      .then(([dsRecords, tjRecords]) => {
        const latest = dsRecords.slice(0, 20);
        const enriched = latest.map((ds) => {
          const match = tjRecords.find(
            (tj) => tj.uuid === ds.uuid && tj.stock_name === ds.stock_name
          );
          return { ...ds, newsTitle: match ? extractNewsTitle(match.news_content, 50) : undefined };
        });
        // 批量补全 disk 摘要（天机卷匹配失败时回退）
        const needSummary = enriched.filter((r) => !r.newsTitle && r.stock_code);
        if (needSummary.length > 0) {
          const codes = needSummary.map((r) => r.stock_code).join(',');
          fetch(`/api/reports/summaries?codes=${codes}`)
            .then((r) => r.json())
            .then((summaries) => {
              for (const r of enriched) {
                if (!r.newsTitle && summaries[r.stock_code]) {
                  r.news_summary = summaries[r.stock_code];
                }
              }
              setReports([...enriched]);
            })
            .catch(() => setReports(enriched));
        } else {
          setReports(enriched);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('TodayReports error:', err);
        setError('数据加载失败');
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!containerRef.current || reports.length === 0) return;
    const items = containerRef.current.querySelectorAll('.report-item');
    gsap.fromTo(items,
      { opacity: 0, x: -20 },
      { opacity: 1, x: 0, duration: 0.6, stagger: 0.12, ease: 'power2.out' }
    );
  }, [reports]);

  return (
    <div ref={containerRef}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <span style={{
          width: '6px', height: '6px', background: '#ADFF00',
          boxShadow: '0 0 4px rgba(173,255,0,0.5)',
          animation: 'pulse 2s ease-in-out infinite',
        }} />
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#999', letterSpacing: '0.15em' }}>
          近期报告
        </span>
        <span style={{ flex: 1, height: '1px', background: 'rgba(173,255,0,0.08)' }} />
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#777', letterSpacing: '0.1em' }}>
          共 {reports.length} 份
        </span>
        <span
          onClick={(e) => { e.stopPropagation(); navigate('/cangjingyun?table=dingshulu'); }}
          style={{
            fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#ADFF00',
            letterSpacing: '0.1em', cursor: 'pointer', marginLeft: '14px',
            border: '1px solid rgba(173,255,0,0.3)', padding: '5px 16px',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(173,255,0,0.1)'; e.currentTarget.style.borderColor = '#ADFF00'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.3)'; }}
        >→ 定数录</span>
      </div>

      <style>{`
        .report-scroll { scrollbar-width: none; -ms-overflow-style: none; }
        .report-scroll::-webkit-scrollbar { display: none; }
      `}</style>
      <div className="report-scroll" style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '540px', overflowY: 'auto', paddingRight: '4px' }}>
        {loading && (
          <div style={{ padding: '20px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#888' }}>
            加载近期报告中...
          </div>
        )}
        {!loading && error && (
          <div style={{ padding: '20px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#FF5C00' }}>
            {error}
          </div>
        )}
        {!loading && !error && reports.length === 0 && (
          <div style={{ padding: '20px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#555' }}>
            暂无报告产出，等待引擎运转...
          </div>
        )}
        {reports.map((rep) => {
          const tier = TIER_STYLE[rep.trade_tier?.slice(0, 3)] || TIER_STYLE['★☆☆'];
          const ql = QUALITY_LABEL[rep.quality_flag] || QUALITY_LABEL['LOW_QUALITY'];
          const probWtd = parseFloat(rep.prob_weighted_upside_pct || '0');
          return (
            <div
              key={rep.id}
              className="report-item"
              onClick={() => { const fn = extractReportFilename(rep); if (fn) navigate(`/report/v4/${fn}`); }}
              style={{
                padding: '16px 20px',
                background: 'rgba(255,255,255,0.04)',
                borderRadius: 6,
                borderLeft: `3px solid ${tier.color}40`,
                transition: 'all 0.3s ease',
                cursor: 'pointer',
                opacity: 0,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(173,255,0,0.04)';
                e.currentTarget.style.borderLeftColor = tier.color;
                e.currentTarget.style.transform = 'translateX(6px)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                e.currentTarget.style.borderLeftColor = `${tier.color}40`;
                e.currentTarget.style.transform = 'translateX(0)';
              }}
            >
              {/* 行1: 层级 + 质量 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '14px', color: tier.color }}>
                  {rep.trade_tier || '★☆☆ 未评级'}
                </span>
                <span style={{
                  fontFamily: "'Space Mono', monospace", fontSize: '10px', color: ql.color,
                  border: `1px solid ${ql.color}40`, padding: '1px 8px', letterSpacing: '0.1em',
                }}>{ql.text}</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#555' }}>
                  置信 {rep.confidence_score || '—'}
                </span>
              </div>

              {/* 行2: 股票名 + 来源 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '6px' }}>
                <span style={{
                  fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
                  fontSize: '18px', fontWeight: 700, color: '#F2F4F3', letterSpacing: '0.04em',
                }}>
                  {rep.stock_name}
                </span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#888', letterSpacing: '0.08em' }}>
                  {rep.stock_code}
                </span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#555' }}>
                  {rep.event_source}
                </span>
              </div>

              {/* 行3: 资讯概要 — 优先天机卷匹配，回退定数录自带摘要 */}
              {(rep.newsTitle || rep.news_summary) && (
                <p style={{
                  fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
                  fontSize: '13px', lineHeight: 1.7, color: '#888', margin: '0 0 10px 0',
                }}>
                  {rep.newsTitle || (() => {
                    const s = rep.news_summary?.replace(/<[^>]*>/g, '').replace(/&[^;]+;/g, ' ').replace(/\s+/g, ' ').trim() || '';
                    return s.length > 80 ? s.slice(0, 80) + '...' : s;
                  })()}
                </p>
              )}

              {/* 行4: 收益 + 情景 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: probWtd >= 0 ? '#ADFF00' : '#FF5C00' }}>
                  {probWtd >= 0 ? '+' : ''}{rep.prob_weighted_upside_pct || '—'}%
                </span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#555' }}>概率加权</span>
                <span style={{ color: '#333' }}>|</span>
                {/* 三情景 — 基最突出 */}
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', fontWeight: 700, color: '#F2F4F3', textShadow: '0 0 10px rgba(255,255,255,0.25)', letterSpacing: '0.06em' }}>基</span>
                <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '17px', color: '#F2F4F3', textShadow: '0 0 12px rgba(255,255,255,0.35)', fontWeight: 700 }}>{rep.base_upside_pct || '—'}%</span>
                <span style={{ color: '#444' }}>|</span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#ADFF00' }}>牛</span>
                <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '14px', color: '#ADFF00', textShadow: '0 0 6px rgba(173,255,0,0.3)' }}>{rep.bull_upside_pct || '—'}%</span>
                <span style={{ color: '#444' }}>|</span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#FF5C00' }}>熊</span>
                <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '14px', color: '#FF5C00', textShadow: '0 0 6px rgba(255,92,0,0.3)' }}>{rep.bear_upside_pct || '—'}%</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#ADFF00', letterSpacing: '0.08em' }}>
                  → 完整报告
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  MascotSprite — 有钱花吉祥物（面板背后，hover 长出）                    */
/* ------------------------------------------------------------------ */
function MascotSprite() {
  const navigate = useNavigate();
  const [hover, setHover] = useState(false);

  const rings: Array<{ size: number; speed: number; dash: boolean; color: string }> = [
    { size: 100, speed: 22, dash: false, color: 'rgba(173,255,0,0.6)' },
    { size: 130, speed: 16, dash: true,  color: 'rgba(255,92,0,0.5)' },
    { size: 160, speed: 25, dash: false, color: 'rgba(173,255,0,0.4)' },
    { size: 190, speed: 13, dash: true,  color: 'rgba(255,92,0,0.35)' },
    { size: 220, speed: 30, dash: false, color: 'rgba(173,255,0,0.25)' },
    { size: 250, speed: 10, dash: true,  color: 'rgba(255,92,0,0.2)' },
  ];

  return (
    <div
      onClick={(e) => { e.stopPropagation(); navigate('/avatar'); }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title="身外化身 · AI投资推演"
      style={{
        position: 'absolute',
        bottom: '290px',
        right: '48px',
        zIndex: 8,
        cursor: 'pointer',
        transition: 'all 0.55s cubic-bezier(0.22, 0.61, 0.36, 1)',
        transform: hover
          ? 'translateY(-72px) scale(1.15)'
          : 'translateY(40px) scale(0.85)',
        opacity: hover ? 1 : 0.7,
      }}
    >
      {/* 多层旋转光环 — 佛光位，以花头为中心（偏左） */}
      {rings.map((r, i) => (
        <div key={`ring-${i}`} style={{
          position: 'absolute',
          top: '22%', left: '0%',
          width: hover ? `${r.size}px` : `${r.size * 0.45}px`,
          height: hover ? `${r.size * 0.8}px` : `${r.size * 0.36}px`,
          transform: 'translate(-50%, -50%)',
          border: `${hover ? 1.5 : 0.5}px ${r.dash ? 'dashed' : 'solid'} ${r.color}`,
          borderRadius: '50%',
          opacity: hover ? 1 : 0.1,
          transition: 'all 0.55s cubic-bezier(0.22, 0.61, 0.36, 1)',
          animation: `spin ${r.speed}s linear infinite ${i % 2 === 0 ? '' : 'reverse'}`,
          pointerEvents: 'none', zIndex: 0,
        }}>
          {/* 铜钱 — 散布在光环上 */}
          {[0, 72, 144, 216, 288].map((deg) => {
            const rad = (deg * Math.PI) / 180;
            const rx = 50 + Math.cos(rad) * 48;
            const ry = 50 + Math.sin(rad) * 38;
            return (
              <div key={deg} style={{
                position: 'absolute',
                left: `${rx}%`, top: `${ry}%`,
                width: hover ? '16px' : '8px',
                height: hover ? '16px' : '8px',
                transform: 'translate(-50%, -50%)',
                transition: 'all 0.55s cubic-bezier(0.22, 0.61, 0.36, 1)',
                opacity: hover ? 0.9 : 0.2,
              }}>
                <svg viewBox="0 0 20 20" width="100%" height="100%">
                  <circle cx="10" cy="10" r="9" fill="none" stroke="#C88D3A" strokeWidth="1.5" />
                  <circle cx="10" cy="10" r="8" fill="rgba(200,141,58,0.2)" />
                  <rect x="6" y="6" width="8" height="8" fill="rgba(5,4,1,0.8)" stroke="#C88D3A" strokeWidth="0.8" />
                </svg>
              </div>
            );
          })}
        </div>
      ))}
      {/* 根系光 */}
      <div style={{
        position: 'absolute',
        top: '-30px', left: '-40px', right: '-40px', bottom: '-30px',
        background: hover
          ? 'radial-gradient(ellipse at 50% 85%, rgba(173,255,0,0.18) 0%, rgba(255,92,0,0.06) 30%, rgba(173,255,0,0.03) 55%, transparent 75%)'
          : 'radial-gradient(ellipse at 50% 85%, rgba(173,255,0,0.03) 0%, transparent 50%)',
        borderRadius: '40%',
        filter: 'blur(8px)',
        transition: 'all 0.55s',
        pointerEvents: 'none', zIndex: 0,
      }} />
      {/* 暗能量波动 — 黑洞吸光感 */}
      <div style={{
        position: 'absolute',
        top: '-60px', left: '-60px', right: '-60px', bottom: '-60px',
        background: 'radial-gradient(circle at 50% 50%, rgba(0,0,0,0.98) 0%, rgba(0,0,0,0.85) 20%, rgba(0,0,0,0.5) 45%, rgba(0,0,0,0.15) 70%, transparent 100%)',
        borderRadius: '50%',
        animation: 'breathe 2.5s ease-in-out infinite',
        pointerEvents: 'none', zIndex: 1,
      }} />
      <div style={{
        position: 'absolute',
        top: '-80px', left: '-80px', right: '-80px', bottom: '-80px',
        background: 'radial-gradient(circle at 50% 50%, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.3) 30%, transparent 60%)',
        borderRadius: '50%',
        filter: 'blur(4px)',
        animation: 'breathe 3.5s ease-in-out infinite 0.7s',
        pointerEvents: 'none', zIndex: 1,
      }} />
      {/* 有钱花图片 — 辉光（隐藏时呼吸+缩放，长出后收敛） */}
      <div style={{ position: 'relative', zIndex: 2, width: '180px' }}>
        <img src="/images/youqianhua-raw.png" alt="有钱花"
          style={{
            width: '180px', height: 'auto', display: 'block',
            filter: hover
              ? 'drop-shadow(0 0 12px rgba(173,255,0,0.55)) drop-shadow(0 0 30px rgba(173,255,0,0.3)) drop-shadow(0 0 50px rgba(173,255,0,0.15))'
              : 'drop-shadow(0 0 8px rgba(220,255,230,0.55)) drop-shadow(0 0 20px rgba(180,255,200,0.35)) drop-shadow(0 0 36px rgba(140,220,160,0.18))',
            transition: 'filter 0.55s ease',
            animation: hover ? 'none' : 'breatheScale 2.5s ease-in-out infinite',
          }}
        />
        {/* 隐藏时辉光呼吸叠加层 */}
        {!hover && (
          <div style={{
            position: 'absolute', inset: '-16px', zIndex: -1, pointerEvents: 'none',
            borderRadius: '45%',
            background: 'radial-gradient(ellipse at 50% 50%, rgba(200,255,220,0.28) 0%, rgba(180,255,200,0.12) 40%, rgba(140,220,160,0.04) 65%, transparent 80%)',
            filter: 'blur(3px)',
            animation: 'breatheScale 2.5s ease-in-out infinite',
          }} />
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ValuationCorePanel                                                */
/* ------------------------------------------------------------------ */
function MiaoyinPanel({ mobile }: { mobile: boolean }) {
  const [hover, setHover] = useState(false);
  const [input, setInput] = useState('');
  const [stockCode, setStockCode] = useState('');
  const [stockName, setStockName] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    setSending(true);
    try {
      const TOKEN = import.meta.env.VITE_COZE_TOKEN || '';
      await fetch('https://api.coze.cn/v1/databases/7479116110479048754/records', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records: [{ fields: {
            news_content: input.trim(),
            stock_code: stockCode.trim() || 'USER_INPUT',
            stock_name: stockName.trim() || '用户传讯',
            level: '3', mode: 'manual',
          }}]
        }),
      });
      setSent(true); setInput(''); setStockCode(''); setStockName('');
      setTimeout(() => setSent(false), 3000);
      fetch('/api/trigger', { method: 'POST' }).catch(() => {});
    } catch {}
    setSending(false);
  };

  return (
    <div style={{
      position: 'absolute', bottom: mobile ? '16px' : '16px', right: mobile ? '16px' : '24px', top: mobile ? 'auto' : '53%',
      zIndex: 15, width: mobile ? 'calc(100% - 32px)' : '540px',
      background: 'rgba(5,4,1,0.90)', backdropFilter: 'blur(3px)',
      border: '1px solid rgba(173,255,0,0.1)', padding: mobile ? '16px 20px' : '20px 28px',
      transition: 'all 0.3s ease', overflow: 'hidden', cursor: 'default',
      display: 'flex', flexDirection: 'column',
    }}
      onMouseEnter={(e) => { setHover(true); e.currentTarget.style.boxShadow = '0 0 24px rgba(173,255,0,0.25)'; e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.borderColor = '#ADFF00'; }}
      onMouseLeave={(e) => { setHover(false); e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.1)'; }}
    >
      {['top-left','top-right','bottom-left','bottom-right'].map(pos => {
        const o = hover ? '-3px' : '0px';
        return (<div key={pos} style={{position:'absolute',width:'10px',height:'10px',zIndex:3,pointerEvents:'none',transition:'all 0.3s ease',opacity:hover?1:0.8,
          ...(pos.includes('top')?{top:o}:{bottom:o}),...(pos.includes('left')?{left:o}:{right:o}),
          ...(pos==='top-left'?{borderTop:'2px solid #ADFF00',borderLeft:'2px solid #ADFF00'}:pos==='top-right'?{borderTop:'2px solid #ADFF00',borderRight:'2px solid #ADFF00'}:pos==='bottom-left'?{borderBottom:'2px solid #ADFF00',borderLeft:'2px solid #ADFF00'}:{borderBottom:'2px solid #ADFF00',borderRight:'2px solid #ADFF00'})}} />);
      })}
      {/* 头部 — 固定 */}
      <div style={{ flexShrink: 0 }}>
        <span style={{ fontFamily:"'Space Mono', monospace",fontSize:'14px',color:'#777',letterSpacing:'0.15em' }}>宗门传讯 · 风闻入阵</span>
        <h2 style={{ fontFamily:"'Geist Pixel','Noto Sans SC',monospace",fontSize:mobile?'20px':'24px',fontWeight:400,color:'#ADFF00',letterSpacing:'0.06em',margin:'8px 0 4px 0' }}>风闻入阵</h2>
        <p style={{ fontFamily:"'Noto Sans SC',sans-serif",fontSize:'14px',color:'#888',margin:'0 0 12px 0',lineHeight:1.5 }}>粘贴资讯或分析命题，直送估值引擎炼化</p>
      </div>
      {/* 正文输入 — 弹性填充 */}
      <textarea value={input} onChange={(e)=>setInput(e.target.value)} placeholder="在此输入资讯内容或分析命题…" rows={mobile?2:6}
        style={{ flex:1,minHeight:0,width:'100%',boxSizing:'border-box',background:'rgba(255,255,255,0.04)',border:'1px solid rgba(173,255,0,0.15)',color:'#F2F4F3',padding:'10px 12px',fontFamily:"'IBM Plex Mono','Noto Sans SC',monospace",fontSize:'15px',lineHeight:1.6,resize:'none',outline:'none',borderRadius:'4px',transition:'border-color 0.2s' }}
        onFocus={(e)=>{e.currentTarget.style.borderColor='#ADFF00'}} onBlur={(e)=>{e.currentTarget.style.borderColor='rgba(173,255,0,0.15)'}} />
      {/* 底部 — 固定 */}
      <div style={{ flexShrink: 0 }}>
        <div style={{ display:'flex',gap:'8px',marginTop:'10px' }}>
          <input value={stockCode} onChange={(e)=>setStockCode(e.target.value)} placeholder="代码(可选)"
            style={{ flex:1,background:'rgba(255,255,255,0.04)',border:'1px solid rgba(255,255,255,0.1)',color:'#AAA',padding:'6px 10px',fontFamily:"'Space Mono',monospace",fontSize:'14px',outline:'none',borderRadius:'4px' }}
            onFocus={(e)=>{e.currentTarget.style.borderColor='#ADFF00'}} onBlur={(e)=>{e.currentTarget.style.borderColor='rgba(255,255,255,0.1)'}} />
          <input value={stockName} onChange={(e)=>setStockName(e.target.value)} placeholder="名称(可选)"
            style={{ flex:1,background:'rgba(255,255,255,0.04)',border:'1px solid rgba(255,255,255,0.1)',color:'#AAA',padding:'6px 10px',fontFamily:"'Space Mono','Noto Sans SC',monospace",fontSize:'14px',outline:'none',borderRadius:'4px' }}
            onFocus={(e)=>{e.currentTarget.style.borderColor='#ADFF00'}} onBlur={(e)=>{e.currentTarget.style.borderColor='rgba(255,255,255,0.1)'}} />
        </div>
        <div style={{ display:'flex',alignItems:'center',gap:'10px',marginTop:'10px' }}>
          <button onClick={handleSend} disabled={sending||!input.trim()}
            style={{ flex:1,padding:'8px 16px',background:sending?'rgba(173,255,0,0.05)':'rgba(173,255,0,0.1)',border:'1px solid '+(sending?'rgba(173,255,0,0.2)':'rgba(173,255,0,0.3)'),color:sending?'#888':'#ADFF00',fontFamily:"'Space Mono','Noto Sans SC',monospace",fontSize:'15px',letterSpacing:'0.08em',cursor:sending||!input.trim()?'not-allowed':'pointer',borderRadius:'4px',transition:'all 0.2s',opacity:input.trim()?1:0.5 }}
            onMouseEnter={(e)=>{if(input.trim()&&!sending)e.currentTarget.style.background='rgba(173,255,0,0.18)'}}
            onMouseLeave={(e)=>{if(!sending)e.currentTarget.style.background='rgba(173,255,0,0.1)'}}>
            {sending?'传讯中…':sent?'✓ 已传讯':'⟐ 传讯入阵'}
          </button>
          <span style={{ fontFamily:"'Noto Sans SC',sans-serif",fontSize:'13px',color:'#FF5C00',letterSpacing:'0.06em',whiteSpace:'nowrap',opacity:0.6 }}>⚒ 施工升级中</span>
        </div>
        {sent&&<div style={{marginTop:'8px',fontFamily:"'Space Mono',monospace",fontSize:'13px',color:'#ADFF00',textAlign:'center'}}>传讯已入阵，估值引擎将自动处理</div>}
      </div>
    </div>
  );
}


/* ---/* ------------------------------------------------------------------ */
/*  Hero                                                               */
/* ------------------------------------------------------------------ */
export default function Hero() {
  const mobile = useMobile();

  return (
    <section id="hero" style={{
      position: 'relative', width: '100%',
      height: mobile ? 'auto' : 'calc(100vh - 60px)',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: mobile ? 'column' : 'row',
    }}>

      {/* ====== LEFT PANEL ====== */}
      <div style={{
        position: 'relative',
        width: mobile ? '100%' : '40%',
        minWidth: mobile ? 'auto' : '420px',
        background: '#050401',
        overflow: 'hidden',
        borderRight: mobile ? 'none' : '1px solid #2A2A2A',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header — 左文右卡，flex 横排 */}
        <div style={{
          flexShrink: 0,
          display: 'flex', alignItems: 'stretch', gap: '52px',
          padding: mobile ? '24px 20px 20px' : '32px 40px 20px',
        }}>
          {/* 左列 — 文案 */}
          <div style={{ width: '340px', flexShrink: 0 }}>
            <p style={{
              fontFamily: "'Space Mono', monospace", fontSize: '13px',
              letterSpacing: '0.2em', color: '#555', margin: '0 0 16px 0',
            }}>
              // 长流水 壹号神器估值重构炉，赛博奇技：
            </p>
            <h1 style={{
              fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace",
              fontSize: mobile ? '42px' : 'clamp(48px, 6vw, 84px)',
              fontWeight: 400, lineHeight: 1.0, color: '#ADFF00',
              margin: '0 0 24px 0', letterSpacing: '0.04em',
              textShadow: '0 0 32px rgba(173,255,0,0.28)',
              whiteSpace: 'nowrap',
            }}>
              神机百炼
            </h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{
                width: '8px', height: '8px', background: '#ADFF00',
                boxShadow: '0 0 8px rgba(173,255,0,0.5)',
                display: 'inline-block', animation: 'pulse 2s ease-in-out infinite',
                flexShrink: 0,
              }} />
              <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', color: '#888', letterSpacing: '0.06em', margin: 0, lineHeight: 1.6 }}>
                AI大阵驱动天眼→估值→追踪全链路
              </p>
            </div>
          </div>
          {/* 右列 — 状态卡 */}
          {!mobile && (
            <div style={{ flex: 1, minWidth: 0, marginRight: '-24px' }}>
              <SpiritLamp />
            </div>
          )}
        </div>

        {/* Scroll — 定数录 */}
        <div style={{
          flex: 1, minHeight: 0,
          display: 'flex', flexDirection: 'column',
          padding: '0 16px 16px',
        }}>
          <DingshuluPanel />
        </div>
      </div>

      {/* ====== RIGHT PANEL ====== */}
      {!mobile && (
        <div style={{ position: 'relative', width: '60%', background: '#050401', overflow: 'hidden' }}>
          <AsciiCanvas />
          {/* 天眼 — 上方全宽，与估值炉左侧对齐 */}
          <div style={{ position: 'absolute', top: '8px', left: '24px', right: '24px', height: '49%', zIndex: 5, display: 'flex', flexDirection: 'column', overflow: 'hidden', transition: 'all 0.3s ease' }}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 0 24px rgba(173,255,0,0.3)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            <TianyanPanel />
          </div>
          {/* 跟踪令 — 与风闻入阵上下沿对齐 */}
          <div style={{ position: 'absolute', bottom: '16px', left: '24px', right: '588px', top: '53%', zIndex: 10, display: 'flex', flexDirection: 'column', overflow: 'hidden', transition: 'all 0.3s ease' }}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 0 24px rgba(173,255,0,0.3)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            <TrackingPanel />
          </div>
          {/* 有钱花遮罩 — 盖住吉祥物，边缘羽化 */}
          <div style={{
            position: 'absolute',
            bottom: '230px',
            right: '20px',
            width: '230px',
            height: '230px',
            background: 'radial-gradient(ellipse at center, #050401 55%, transparent 100%)',
            zIndex: 9,
            pointerEvents: 'none',
          }} />
          {/* 有钱花吉祥物 — 面板背后 */}
          <MascotSprite />
          <MiaoyinPanel mobile={false} />
        </div>
      )}
    </section>
  );
}
