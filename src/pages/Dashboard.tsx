import { useEffect, useRef, useState } from 'react';
import { useMobile } from '../hooks/useMobile';
import {
  fetchStatus, createProgressStream,
  triggerReview, fetchReviewStatus, fetchReviewFiles,
  type ProgressEvent,
  type ReviewStatus,
  type ReviewFile,
} from '../services/valuationApi';
import gsap from 'gsap';

const cardBase: React.CSSProperties = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.06)',
  padding: '20px 24px',
  transition: 'all 0.3s ease',
};

/* ------------------------------------------------------------------ */
/*  StatusCard                                                          */
/* ------------------------------------------------------------------ */
function StatusCard({ label, value, color, dot }: { label: string; value: string; color: string; dot?: boolean }) {
  return (
    <div style={cardBase}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = `${color}30`; e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)'; e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; }}
    >
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#777', letterSpacing: '0.15em' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px' }}>
        {dot && <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: color, boxShadow: `0 0 6px ${color}60`, animation: color === '#ADFF00' ? 'pulse 2s ease-in-out infinite' : 'none' }} />}
        <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '15px', color, fontWeight: 600 }}>{value}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ControlBtn                                                           */
/* ------------------------------------------------------------------ */
function ControlBtn({ label, onClick, disabled, color, loading }: { label: string; onClick: () => void; disabled?: boolean; color: string; loading?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      style={{
        fontFamily: "'Space Mono', monospace", fontSize: '15px',
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

/* ================================================================== */
/*  Dashboard                                                            */
/* ================================================================== */
export default function Dashboard() {
  const navigate = useNavigate();
  const mobile = useMobile();
  const contentRef = useRef<HTMLDivElement>(null);
  const jobsRef = useRef<HTMLDivElement>(null);

  const [sseConnected, setSseConnected] = useState(false);
  const [activeJobs, setActiveJobs] = useState<Array<{ stock_code: string; stock_name: string; status: string }>>([]);
  const [completedJobs, setCompletedJobs] = useState<Array<{ stock_code: string; stock_name: string; status: string; report_url?: string }>>([]);
  const [jobProgress, setJobProgress] = useState<Record<string, ProgressEvent>>({});
  const [jobHistory, setJobHistory] = useState<Record<string, ProgressEvent[]>>({});
  const [error, setError] = useState('');
  const [reviewTriggerLoading, setReviewTriggerLoading] = useState(false);
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus | null>(null);
  const [reviewFiles, setReviewFiles] = useState<ReviewFile[]>([]);
  const [reviewMsg, setReviewMsg] = useState<{ text: string; color: string } | null>(null);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);

  // 初始加载 + SSE 连接
  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = createProgressStream(
        (event) => {
          setJobProgress((prev) => ({ ...prev, [event.stock_code]: event }));
          setJobHistory((prev) => {
            const list = prev[event.stock_code] || [];
            const last = list[list.length - 1];
            if (!last || last.stage !== event.stage || last.step !== event.step || last.status !== event.status) {
              return { ...prev, [event.stock_code]: [...list, event] };
            }
            return prev;
          });
          setSseConnected(true);
        },
        () => {
          setSseConnected(false);
          setError((prev) => prev || 'SSE 连接丢失，正在重连...');
        },
      );
    } catch { /* EventSource not supported */ }

    fetchStatus().then((s) => {
      setActiveJobs(s.active_jobs || []);
      setCompletedJobs(s.completed_jobs || []);
      setSseConnected(true);
      setError('');
    }).catch((err) => {
      setError(`后端连接失败: ${err instanceof Error ? err.message : String(err)}`);
    });

    return () => { if (es) es.close(); };
  }, []);

  // 定时刷新状态 (30s)
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const s = await fetchStatus();
        setActiveJobs(s.active_jobs || []);
        setCompletedJobs(s.completed_jobs || []);
      } catch { /* keep stale */ }
    }, 30_000);
    return () => clearInterval(id);
  }, []);

  // 列表变化时动画
  useEffect(() => {
    if (!jobsRef.current) return;
    const cards = jobsRef.current.querySelectorAll('.job-row');
    if (cards.length > 0) {
      gsap.fromTo(cards, { opacity: 0, x: -12 }, { opacity: 1, x: 0, duration: 0.35, stagger: 0.06, ease: 'power2.out' });
    }
  }, [activeJobs.length, completedJobs.length]);

  // 入场动画
  useEffect(() => {
    if (!contentRef.current) return;
    const cards = contentRef.current.querySelectorAll('.dash-card');
    gsap.fromTo(cards, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 0.5, stagger: 0.08, ease: 'power2.out' });
  }, []);

  const handleReviewTrigger = useCallback(async () => {
    setReviewTriggerLoading(true);
    setReviewMsg(null);
    try {
      const res = await triggerReview();
      if (res.status === 'ok') {
        setReviewStatus({ has_review: true, health: res.health, total_reports: res.reviewed, grade_distribution: res.grade_distribution, top_flags: res.top_flags });
        setReviewMsg({ text: `审阅完成 · ${res.reviewed}份报告 · ${res.health || '?'}`, color: '#ADFF00' });
        fetchReviewFiles().then(setReviewFiles).catch(() => setReviewFiles([]));
      } else {
        setReviewMsg({ text: '审阅触发失败', color: '#FF5C00' });
      }
    } catch (e) { setReviewMsg({ text: `错误: ${String(e)}`, color: '#FF5C00' }); }
    finally { setReviewTriggerLoading(false); }
  }, []);

  useEffect(() => {
    fetchReviewStatus().then(setReviewStatus).catch(() => setReviewStatus(null));
    fetchReviewFiles().then(files => setReviewFiles(files)).catch(e => { console.error('reviewFiles fetch failed:', e); setReviewFiles([]); });
  }, [completedJobs.length]);

  useEffect(() => {
    fetchReviewFiles().then(files => setReviewFiles(files)).catch(e => { console.error('reviewFiles fetch failed:', e); setReviewFiles([]); });
  }, []);

  return (
    <div style={{ minHeight: 'calc(100vh - 58px)', background: '#050401', color: '#F2F4F3' }}>
      <div ref={contentRef} style={{ maxWidth: '960px', margin: '0 auto', padding: mobile ? '24px 20px 48px' : '32px 48px 64px' }}>
        {/* Header */}
        <div className="dash-card" style={{ marginBottom: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ width: '8px', height: '8px', background: '#ADFF00', boxShadow: '0 0 8px rgba(173,255,0,0.5)', animation: 'pulse 2s ease-in-out infinite', display: 'inline-block' }} />
            <h1 style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: '28px', fontWeight: 400, color: '#ADFF00', margin: 0, letterSpacing: '0.06em', textShadow: '0 0 16px rgba(173,255,0,0.3)' }}>估值重构炉</h1>
            <span style={{ flex: 1 }} />
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555' }}>
              {sseConnected ? 'SSE 在线' : 'SSE 离线'} · {completedJobs.length} 份报告
            </span>
          </div>
        </div>

        {error && (
          <p style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#FF5C00', marginBottom: '16px', padding: '10px 16px', background: 'rgba(255,92,0,0.06)', border: '1px solid rgba(255,92,0,0.2)' }}>{error}</p>
        )}

        {/* 报告审阅 */}
        <div className="dash-card" style={{ ...cardBase, marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
            <span style={{ width: '8px', height: '8px', background: reviewStatus?.has_review ? '#ADFF00' : '#444', boxShadow: reviewStatus?.has_review ? '0 0 8px rgba(173,255,0,0.5)' : 'none' }} />
            <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00', letterSpacing: '0.06em' }}>审阅</span>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#666' }}>报告质量监控</span>
            <span style={{ flex: 1 }} />
            <ControlBtn label="🔍 执行审阅" onClick={handleReviewTrigger} disabled={reviewTriggerLoading} color="#ADFF00" loading={reviewTriggerLoading} />
          </div>

          {/* 审阅统计 */}
          {reviewStatus?.has_review ? (
            <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr 1fr' : 'repeat(3, 1fr)', gap: '12px' }}>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#AAA' }}>
                系统健康度: <span style={{ color: reviewStatus.health === '良好' ? '#ADFF00' : '#C88D3A' }}>{reviewStatus.health || '?'}</span>
              </div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#AAA' }}>
                审阅数: <span style={{ color: '#ADFF00' }}>{reviewStatus.total_reports || 0}份</span>
              </div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#AAA' }}>
                评级: {Object.entries(reviewStatus.grade_distribution || {}).map(([g, c]) => (
                  <span key={g} style={{ marginLeft: '6px', color: g === 'A' ? '#ADFF00' : g === 'B' ? '#8BC34A' : g === 'C' ? '#C88D3A' : '#FF5C00' }}>{g}×{c}</span>
                )) || '—'}
              </div>
              {(reviewStatus.top_flags || []).length > 0 && (
                <div style={{ gridColumn: '1 / -1', borderTop: '1px solid #2A2A2A', paddingTop: '8px' }}>
                  <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555' }}>高频标记: </span>
                  {reviewStatus.top_flags!.map((f, i) => (
                    <span key={i} style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px', color: '#C88D3A', marginRight: '12px' }} title={f.action}>
                      {f.code} ×{f.count}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '16px', color: '#555', marginBottom: '8px' }}>
              暂无审阅数据 — 点击「执行审阅」生成
            </div>
          )}

          {/* 审阅消息 */}
          {reviewMsg && (
            <p style={{
              fontFamily: "'Space Mono', monospace", fontSize: '15px', color: reviewMsg.color,
              borderTop: '1px solid #2A2A2A', paddingTop: '10px', marginTop: '8px',
            }}>{reviewMsg.text}</p>
          )}

          {/* 审阅存档 — 始终显示 */}
          <div style={{ borderTop: '1px solid #2A2A2A', paddingTop: '10px', marginTop: '10px' }}>
            {reviewFiles.length > 0 ? (
              <div>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555' }}>审阅存档: </span>
                {reviewFiles.slice(0, 10).map((f) => (
                  <a key={f.filename}
                    href={`${import.meta.env.VITE_API_BASE || ''}/review/view/${f.filename}`}
                    target="_blank" rel="noopener"
                    style={{
                      fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px',
                      color: '#ADFF00', marginRight: '14px', textDecoration: 'none',
                      borderBottom: '1px dashed #444', cursor: 'pointer'
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.color = '#FFF'; e.currentTarget.style.borderBottomColor = '#ADFF00'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.color = '#ADFF00'; e.currentTarget.style.borderBottomColor = '#444'; }}
                  >{f.date}</a>
                ))}
              </div>
            ) : (
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px', color: '#444' }}>审阅存档: 暂无</span>
            )}
          </div>
        </div>

        {/* Active Jobs */}
        {activeJobs.length > 0 && (
          <div className="dash-card" style={{ ...cardBase, marginBottom: '20px' }}>
            <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '15px', color: '#AAA', letterSpacing: '0.15em', margin: '0 0 14px 0' }}>
              活跃任务 ({activeJobs.length})
            </h3>
            <div ref={jobsRef} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {[...activeJobs].sort((a) => a.status === 'running' ? -1 : 1).map((job, i) => {
                const jobKey = `${job.stock_code}`;
                const expanded = expandedJob === jobKey;
                const isRunning = job.status === 'running';
                const prog = jobProgress[job.stock_code];
                const history = jobHistory[job.stock_code] || [];
                const stages: Array<{ id: string; label: string; status: 'pending' | 'running' | 'done' | 'error' }> = [];
                const stageLabels: Record<string, string> = {
                  agent0: '预路由', agent1: '数据炼器', agent2: '路由判决',
                  agent3: '推演裁决', report: '报告输出',
                };
                ['agent0', 'agent1', 'agent2', 'agent3', 'report'].forEach((sid) => {
                  const evts = history.filter(h => h.stage === sid);
                  const doneEvt = evts.find(h => h.status === 'done');
                  const errEvt = evts.find(h => h.status === 'error');
                  const runEvt = evts.find(h => h.status === 'running');
                  if (errEvt) stages.push({ id: sid, label: stageLabels[sid], status: 'error' });
                  else if (doneEvt) stages.push({ id: sid, label: stageLabels[sid], status: 'done' });
                  else if (runEvt) stages.push({ id: sid, label: stageLabels[sid], status: 'running' });
                  else stages.push({ id: sid, label: stageLabels[sid], status: 'pending' });
                });
                return (
                  <div key={`${job.stock_code}-${i}`} className="job-row">
                    <div
                      onClick={() => setExpandedJob(expanded ? null : jobKey)}
                      style={{
                        padding: '14px 16px',
                        background: isRunning ? 'rgba(173,255,0,0.03)' : 'rgba(255,255,255,0.02)',
                        borderLeft: `3px solid ${isRunning ? '#ADFF00' : '#444'}`,
                        border: `1px solid ${isRunning ? 'rgba(173,255,0,0.12)' : 'rgba(255,255,255,0.04)'}`,
                        transition: 'all 0.2s', cursor: 'pointer',
                      }}
                      onMouseEnter={(e) => { if (!expanded) { e.currentTarget.style.borderColor = 'rgba(173,255,0,0.15)'; e.currentTarget.style.background = 'rgba(255,255,255,0.04)'; }}}
                      onMouseLeave={(e) => { if (!expanded) { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.04)'; e.currentTarget.style.background = isRunning ? 'rgba(173,255,0,0.03)' : 'rgba(255,255,255,0.02)'; }}}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          <span style={{
                            fontFamily: "'Space Mono', monospace", fontSize: '14px',
                            color: isRunning ? '#ADFF00' : '#555',
                            transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                            transition: 'transform 0.2s',
                          }}>▶</span>
                          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px', fontWeight: 600, color: '#F2F4F3' }}>{job.stock_code}</span>
                          <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '16px', color: '#AAA' }}>{job.stock_name}</span>
                        </div>
                        <span style={{
                          fontFamily: "'Space Mono', monospace", fontSize: '14px',
                          color: isRunning ? '#ADFF00' : '#666', letterSpacing: '0.1em',
                        }}>
                          {isRunning ? (prog ? `${prog.step_name}` : '处理中') : '排队中'}
                        </span>
                      </div>
                      {/* Pipeline stages — 点状进度 */}
                      {isRunning && (
                        <div style={{ marginTop: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          {stages.map((s, si) => {
                            const color = s.status === 'done' ? '#ADFF00' : s.status === 'running' ? '#ADFF00' : s.status === 'error' ? '#FF5C00' : '#333';
                            const glow = s.status === 'running' ? `0 0 8px ${color}60` : s.status === 'done' ? `0 0 4px ${color}30` : 'none';
                            return (
                              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <span style={{
                                  width: s.status === 'running' ? '12px' : '8px', height: s.status === 'running' ? '12px' : '8px',
                                  borderRadius: '50%', background: color, boxShadow: glow,
                                  transition: 'all 0.3s', display: 'inline-block',
                                }} />
                                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: s.status === 'pending' ? '#333' : '#888' }}>{s.label}</span>
                                {si < stages.length - 1 && <span style={{ color: '#222', fontSize: '10px', margin: '0 2px' }}>—</span>}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                    {/* 展开区 — 详细进度 */}
                    {expanded && isRunning && prog && (
                      <div style={{
                        padding: '14px 16px 14px 32px',
                        background: 'rgba(0,0,0,0.2)',
                        border: '1px solid rgba(173,255,0,0.06)',
                        borderTop: 'none',
                      }}>
                        <div style={{ height: '4px', background: 'rgba(255,255,255,0.06)', borderRadius: '2px', overflow: 'hidden', marginBottom: '10px' }}>
                          <div style={{ height: '100%', width: `${(prog.step / prog.total_steps) * 100}%`, background: '#ADFF00', borderRadius: '2px', transition: 'width 0.5s' }} />
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '8px' }}>
                          {stages.map((s) => {
                            const evt = history.filter(h => h.stage === s.id).pop();
                            const color = s.status === 'done' ? '#ADFF00' : s.status === 'running' ? '#ADFF00' : s.status === 'error' ? '#FF5C00' : '#444';
                            return (
                              <div key={s.id} style={{
                                padding: '8px 10px', background: s.status === 'running' ? 'rgba(173,255,0,0.04)' : 'rgba(255,255,255,0.01)',
                                border: `1px solid ${s.status === 'running' ? 'rgba(173,255,0,0.15)' : 'rgba(255,255,255,0.04)'}`,
                                borderLeft: `2px solid ${color}`,
                              }}>
                                <div style={{ fontSize: '10px', fontFamily: "'Space Mono', monospace", color: color, marginBottom: '4px', letterSpacing: '0.1em' }}>{s.label}</div>
                                <div style={{ fontSize: '12px', fontFamily: "'Noto Sans SC', sans-serif", color: s.status === 'pending' ? '#333' : '#AAA' }}>
                                  {s.status === 'done' ? (evt?.step_name || '完成') :
                                   s.status === 'running' ? (evt?.step_name || '运行中') :
                                   s.status === 'error' ? (evt?.step_name || '失败') : '—'}
                                </div>
                                {evt && Number(evt.elapsed_s) > 0 && <div style={{ fontSize: '10px', color: '#555', fontFamily: "'Space Mono', monospace", marginTop: '2px' }}>{evt.elapsed_s.toFixed(1)}s</div>}
                              </div>
                            );
                          })}
                        </div>
                        {prog.error_msg && <div style={{ marginTop: '10px', fontSize: '12px', color: '#FF5C00', fontFamily: "'Space Mono', monospace", padding: '8px', background: 'rgba(255,92,0,0.05)', border: '1px solid rgba(255,92,0,0.15)' }}>{prog.error_msg}</div>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Completed */}
        <div className="dash-card" style={cardBase}>
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '15px', color: '#AAA', letterSpacing: '0.15em', margin: '0 0 14px 0' }}>
            已完成 ({completedJobs.length})
          </h3>
          {completedJobs.length === 0 ? (
            <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', color: '#555', textAlign: 'center', padding: '32px 0' }}>
              暂无完成记录，等待整点自动触发或手动操作
            </p>
          ) : (
            <div ref={jobsRef} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {[...completedJobs].reverse().map((job, i) => (
                <div key={`${job.stock_code}-${i}`} className="job-row"
                  onClick={() => { if (job.report_url) { const fn = job.report_url.split('/').pop(); if (fn) navigate(`/report/v4/${fn}`); } else { navigate(`/report/v4/${job.stock_code}`); } }}
                  style={{ padding: '12px 16px', cursor: 'pointer', background: i % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'rgba(255,255,255,0.03)', borderLeft: '2px solid rgba(173,255,0,0.12)', transition: 'all 0.2s', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(173,255,0,0.04)'; e.currentTarget.style.borderLeftColor = '#ADFF00'; e.currentTarget.style.transform = 'translateX(4px)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = i % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'rgba(255,255,255,0.03)'; e.currentTarget.style.borderLeftColor = 'rgba(173,255,0,0.12)'; e.currentTarget.style.transform = 'translateX(0)'; }}
                >
                  <div>
                    <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px', fontWeight: 600, color: '#F2F4F3' }}>{job.stock_code}</span>
                    <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '16px', color: '#AAA', marginLeft: '10px' }}>{job.stock_name}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#ADFF00' }}>✓ 完成</span>
                    <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#ADFF00', letterSpacing: '0.1em' }}>→ 查看报告</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
