import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useMobile } from '../hooks/useMobile';
import { fetchTotalCount, fetchTianjijuanToday, fetchWangqi } from '../services/cozeApi';

gsap.registerPlugin(ScrollTrigger);

/* ------------------------------------------------------------------ */
/*  宗门机构调度数据                                                    */
/* ------------------------------------------------------------------ */
interface SectDept {
  id: string;
  name: string;
  code: string;
  role: string;
  sub: string;
  status: 'active' | 'idle' | 'hunting';
  route: string;
}

const DEPTS: SectDept[] = [
  { id: 'tianji', name: '天机峰', code: 'TJ-01', role: '司情报监控', sub: '天眼 · 望气 · 寻龙 · 妙音', status: 'active', route: '/tianjifeng' },
  { id: 'cangjing', name: '藏经云', code: 'CJ-02', role: '宗门数据存储', sub: '藏经阁 · 天机卷 · 万业谱 · 定数录 · 因果簿', status: 'active', route: '/cangjingyun' },
  { id: 'shenji', name: '神机百炼', code: 'SJ-03', role: '宗门核心系统', sub: '估值重构炉 · 调度引擎', status: 'active', route: '/dashboard' },
  { id: 'avatar', name: '身外化身', code: 'HS-04', role: 'AI推演决策', sub: '灵光 · 案例 · 推演', status: 'active', route: '/avatar' },
  { id: 'pojun', name: '破军小队', code: 'PJ-05', role: '指标技术组', sub: 'K线之道 · 量化指标', status: 'idle', route: '' },
  { id: 'lingyan', name: '凌烟阁', code: 'LY-06', role: '记录回测与战绩', sub: '历史战绩 · 推动进化', status: 'idle', route: '' },
  { id: 'guanlan', name: '观澜亭', code: 'GL-07', role: '判天下大势', sub: '常委会议事', status: 'active', route: '' },
  { id: 'jianlin', name: '剑林', code: 'JL-08', role: '司虚拟交易及交易排名', sub: '模拟盘 · 天骄榜 · 宗主直属', status: 'hunting', route: '' },
  { id: 'tiangong', name: '天工小队', code: 'TG-11', role: '技术支持与运维', sub: '服务巡检 · 框架运维', status: 'active', route: '' },
  { id: 'heijing', name: '黑镜', code: 'HJ-12', role: '司掌万象投影', sub: '宗门声量 · 研报 · 法旨', status: 'active', route: '' },
];

const statusColor: Record<string, { dot: string; text: string; label: string }> = {
  active:  { dot: '#ADFF00', text: '#ADFF00', label: '运转中' },
  idle:    { dot: '#666',    text: '#888',    label: '闭关升级' },
  hunting: { dot: '#FF5C00', text: '#FF5C00', label: '猎杀中' },
};

/* ------------------------------------------------------------------ */
/*  几何标识                                                            */
/* ------------------------------------------------------------------ */
function DeptGlyph({ id, color }: { id: string; color: string }) {
  const glyphs: Record<string, ReactNode> = {
    tianji:   <svg viewBox="0 0 60 60" width="36" height="36"><circle cx="30" cy="30" r="12" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><circle cx="30" cy="30" r="22" fill="none" stroke={color} strokeWidth="0.5" opacity="0.3" strokeDasharray="4 4"/><circle cx="30" cy="30" r="3" fill={color} opacity="0.8"/></svg>,
    cangjing: <svg viewBox="0 0 60 60" width="36" height="36"><rect x="14" y="18" width="32" height="24" rx="2" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><line x1="20" y1="26" x2="40" y2="26" stroke={color} strokeWidth="0.8" opacity="0.4"/><line x1="20" y1="32" x2="36" y2="32" stroke={color} strokeWidth="0.8" opacity="0.4"/><circle cx="42" cy="42" r="4" fill={color} opacity="0.3"/></svg>,
    shenji:   <svg viewBox="0 0 60 60" width="36" height="36"><polygon points="30,8 50,48 10,48" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><circle cx="30" cy="34" r="6" fill="none" stroke={color} strokeWidth="1" opacity="0.5"/><circle cx="30" cy="34" r="2" fill={color} opacity="0.8"/></svg>,
    avatar:   <svg viewBox="0 0 60 60" width="36" height="36"><circle cx="30" cy="22" r="10" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><path d="M10,50 Q30,34 50,50" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><circle cx="30" cy="30" r="14" fill="none" stroke={color} strokeWidth="0.5" opacity="0.3" strokeDasharray="3 3"/></svg>,
    pojun:    <svg viewBox="0 0 60 60" width="36" height="36"><polyline points="10,45 20,25 30,35 40,15 50,30" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><circle cx="40" cy="15" r="3" fill={color} opacity="0.8"/><line x1="10" y1="48" x2="50" y2="48" stroke={color} strokeWidth="0.5" opacity="0.3"/></svg>,
    lingyan:  <svg viewBox="0 0 60 60" width="36" height="36"><rect x="12" y="14" width="36" height="32" rx="2" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><line x1="12" y1="22" x2="48" y2="22" stroke={color} strokeWidth="0.5" opacity="0.3"/><circle cx="30" cy="36" r="8" fill="none" stroke={color} strokeWidth="1" opacity="0.4" strokeDasharray="2 2"/></svg>,
    guanlan:  <svg viewBox="0 0 60 60" width="36" height="36"><path d="M10,40 Q20,20 30,35 T50,25" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><circle cx="50" cy="25" r="4" fill="none" stroke={color} strokeWidth="1" opacity="0.5"/><line x1="10" y1="45" x2="50" y2="45" stroke={color} strokeWidth="0.5" opacity="0.3"/></svg>,
    jianlin:  <svg viewBox="0 0 60 60" width="36" height="36"><line x1="30" y1="6" x2="30" y2="38" stroke={color} strokeWidth="1.5" opacity="0.7"/><line x1="22" y1="28" x2="38" y2="28" stroke={color} strokeWidth="1" opacity="0.5"/><rect x="26" y="4" width="8" height="6" rx="1" fill={color} opacity="0.3"/><line x1="26" y1="42" x2="30" y2="54" stroke={color} strokeWidth="1.2" opacity="0.6"/><line x1="34" y1="42" x2="30" y2="54" stroke={color} strokeWidth="1.2" opacity="0.6"/><line x1="18" y1="42" x2="22" y2="52" stroke={color} strokeWidth="0.8" opacity="0.4"/><line x1="42" y1="42" x2="38" y2="52" stroke={color} strokeWidth="0.8" opacity="0.4"/></svg>,
    tiangong: <svg viewBox="0 0 60 60" width="36" height="36"><circle cx="30" cy="30" r="16" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><circle cx="30" cy="30" r="8" fill="none" stroke={color} strokeWidth="1" opacity="0.4" strokeDasharray="3 3"/><rect x="26" y="26" width="8" height="8" rx="1" fill={color} opacity="0.5"/></svg>,
    heijing:  <svg viewBox="0 0 60 60" width="36" height="36"><rect x="10" y="14" width="40" height="32" rx="4" fill="none" stroke={color} strokeWidth="1.5" opacity="0.6"/><circle cx="30" cy="30" r="10" fill="none" stroke={color} strokeWidth="1" opacity="0.4" strokeDasharray="2 2"/><circle cx="30" cy="30" r="4" fill={color} opacity="0.5"/><line x1="10" y1="42" x2="50" y2="42" stroke={color} strokeWidth="0.5" opacity="0.3"/></svg>,
  };
  return glyphs[id] || null;
}

/* ------------------------------------------------------------------ */
/*  机构卡片                                                            */
/* ------------------------------------------------------------------ */
function DeptCard({ dept, metric, metric2, services, onRefresh, refreshing }: { dept: SectDept; metric?: string; metric2?: string; services?: Array<{ name: string; ok: boolean }>; onRefresh?: () => void; refreshing?: boolean }) {
  const navigate = useNavigate();
  const s = statusColor[dept.status];
  const clickable = !!dept.route;

  return (
    <div style={{
      padding: '24px 20px',
      background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.06)',
      transition: 'all 0.3s ease',
      cursor: clickable ? 'pointer' : 'default',
      position: 'relative',
    }}
      onClick={() => { if (clickable) navigate(dept.route); }}
      onMouseEnter={(e) => {
        if (clickable) {
          e.currentTarget.style.background = 'rgba(255,255,255,0.06)';
          e.currentTarget.style.borderColor = `${s.dot}40`;
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = `0 8px 24px rgba(0,0,0,0.3)`;
        }
      }}
      onMouseLeave={(e) => {
        if (clickable) {
          e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
          e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)';
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = 'none';
        }
      }}
    >
      {/* 右上角操作区 */}
      <div style={{ position: 'absolute', top: '12px', right: '14px', display: 'flex', gap: '6px', alignItems: 'center' }}>
        {onRefresh && (
          <span
            onClick={(e) => { e.stopPropagation(); onRefresh(); }}
            style={{
              fontFamily: "'Space Mono', monospace", fontSize: '9px', color: refreshing ? '#888' : s.dot,
              cursor: 'pointer', opacity: refreshing ? 0.5 : 0.7,
              transition: 'opacity 0.2s',
            }}
            onMouseEnter={(e2) => { if (!refreshing) e2.currentTarget.style.opacity = '1'; }}
            onMouseLeave={(e2) => { if (!refreshing) e2.currentTarget.style.opacity = '0.7'; }}
          >{refreshing ? '⟳' : '↻'}</span>
        )}
        {clickable && (
          <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: s.dot, opacity: 0.3 }}>→</span>
        )}
      </div>

      {/* 状态 + 几何标识 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{
            width: '6px', height: '6px', background: s.dot,
            boxShadow: `0 0 8px ${s.dot}60`, display: 'inline-block',
            animation: dept.status === 'active' ? 'pulse 2s ease-in-out infinite' : dept.status === 'hunting' ? 'pulse 1.2s ease-in-out infinite' : 'none',
          }} />
          <span style={{
            fontFamily: "'Space Mono', monospace", fontSize: '10px',
            color: s.text, letterSpacing: '0.12em',
          }}>
            {s.label}
          </span>
        </div>
        <DeptGlyph id={dept.id} color={s.dot} />
      </div>

      {/* 机构名 */}
      <h2 style={{
        fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
        fontSize: '20px', fontWeight: 700, color: '#F2F4F3',
        margin: '0 0 6px 0', letterSpacing: '0.04em',
      }}>
        {dept.name}
      </h2>

      {/* 代码 */}
      <p style={{
        fontFamily: "'Space Mono', monospace", fontSize: '11px',
        color: '#777', letterSpacing: '0.1em', margin: '0 0 16px 0',
      }}>
        {dept.code}
      </p>

      {/* 分隔 */}
      <div style={{ width: '100%', height: '1px', background: 'rgba(255,255,255,0.06)', marginBottom: '16px' }} />

      {/* 职责 */}
      <p style={{
        fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
        fontSize: '14px', color: '#AAA', margin: '0 0 6px 0',
      }}>
        {dept.role}
      </p>
      <p style={{
        fontFamily: "'Space Mono', monospace", fontSize: '11px',
        color: '#666', letterSpacing: '0.06em', margin: '0 0 16px 0',
      }}>
        {dept.sub}
      </p>

      {/* 实时指标 */}
      {(metric || metric2 || services) && (
        <div style={{
          fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#888',
          letterSpacing: '0.04em', lineHeight: 1.8,
        }}>
          {metric && <div>{metric}</div>}
          {services && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
              {services.map((svc) => (
                <span key={svc.name} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{
                    display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%',
                    background: svc.ok ? '#ADFF00' : '#555',
                    boxShadow: svc.ok ? '0 0 6px rgba(173,255,0,0.5)' : 'none',
                  }} />
                  {svc.name}
                </span>
              ))}
            </div>
          )}
          {metric2 && (
            <div style={{ color: metric2.includes('异常') ? '#FF5C00' : '#C88D3A' }}>
              {metric2}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  宗门调度总览                                                        */
/* ------------------------------------------------------------------ */
export default function Facilities() {
  const sectionRef = useRef<HTMLElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const mobile = useMobile();
  const [metrics, setMetrics] = useState<Record<string, string>>({});
  const [sysStatus, setSysStatus] = useState({ scheduler: false, sse: false, reports: 0, jobs: 0 });
  const svcRef = useRef({ engine: false, wangqi: false, tianjiPoll: false });
  const [tianGongSvcs, setTianGongSvcs] = useState<Array<{ name: string; ok: boolean }>>([]);
  const [tianjiPolling, setTianjiPolling] = useState(false);

  const updateTiangong = () => {
    const { engine, wangqi, tianjiPoll } = svcRef.current;
    setTianGongSvcs([
      { name: '调度引擎', ok: engine },
      { name: '望气分析', ok: wangqi },
      { name: '天机轮询', ok: tianjiPoll },
    ]);
    const allOk = engine && wangqi;
    setMetrics((m) => ({ ...m, tiangong2: allOk ? '全服务正常' : '存在异常服务' }));
  };

  const fetchTianjiMetrics = () => {
    setTianjiPolling(true);
    Promise.all([
      fetchTianjijuanToday().then((items) => {
        const today = new Date().toISOString().slice(0, 10);
        const highToday = items.filter((r) => (r.level === '4' || r.level === '5') && (r.bstudio_create_time || '').startsWith(today)).length;
        setMetrics((m) => ({ ...m, tianji: `今日监测到天下异象 ${highToday} 处` }));
      }),
      fetchWangqi()
        .then((records) => {
          const chains = [...new Set(records.map((r) => r.industry_chain).filter(Boolean))];
          const total = chains.length;
          const shown = chains.slice(0, 5).join(' · ');
          svcRef.current = { ...svcRef.current, wangqi: true };
          setMetrics((m) => ({ ...m, tianji2: `气运汇集 ${shown}${total > 5 ? ` 等${total}处` : ''}` }));
          updateTiangong();
        }),
    ]).catch(() => {
      svcRef.current = { ...svcRef.current, wangqi: false };
      updateTiangong();
    }).finally(() => {
      svcRef.current = { ...svcRef.current, tianjiPoll: true };
      updateTiangong();
      setTianjiPolling(false);
    });
  };

  useEffect(() => {
    // 藏经云记录数
    fetchTotalCount().then((n) => setMetrics((m) => ({ ...m, cangjing: `藏经阁 ${n}卷` }))).catch(() => setMetrics((m) => ({ ...m, cangjing: '藏经阁 断连' })));
    // 天机峰：异象 + 气运
    fetchTianjiMetrics();
    // 引擎状态
    fetch('/api/status')
      .then((r) => r.json())
      .then((s) => {
        const running = s.scheduler_running;
        const completed = (s.completed_jobs || []).length;
        const active = (s.active_jobs || []).length;
        setSysStatus({ scheduler: running, sse: true, reports: completed, jobs: active });
        const lastPoll = s.last_poll_at
          ? new Date(s.last_poll_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
          : '—';
        const nextPoll = s.next_poll_at
          ? new Date(s.next_poll_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
          : '—';
        svcRef.current = { ...svcRef.current, engine: true };
        setMetrics((m) => ({
          ...m,
          shenji: `${running ? '● 运转中' : '○ 已暂停'} · 产出${completed}份`,
          shenji2: `上次 ${lastPoll} · 下次 ${nextPoll}`,
        }));
        updateTiangong();
      })
      .catch(() => {
        svcRef.current = { ...svcRef.current, engine: false };
        updateTiangong();
      });
  }, []);

  // 10分钟轮询天机峰数据
  useEffect(() => {
    const id = setInterval(fetchTianjiMetrics, 600_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!sectionRef.current || !gridRef.current) return;
    const cards = gridRef.current.children;
    const ctx = gsap.context(() => {
      gsap.fromTo(Array.from(cards),
        { opacity: 0, y: 30 },
        {
          opacity: 1, y: 0, duration: 0.6, stagger: 0.06,
          ease: 'power2.out',
          scrollTrigger: {
            trigger: sectionRef.current,
            start: 'top 65%',
            toggleActions: 'play none none reverse',
          },
        }
      );
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  const activeCount = DEPTS.filter((d) => d.status === 'active' || d.status === 'hunting').length;

  return (
    <section ref={sectionRef} id="facilities" style={{
      background: '#050401', color: '#F2F4F3',
      borderTop: '1px solid #2A2A2A',
    }}>
      {/* Header + 总览条 */}
      <div style={{ padding: mobile ? '24px 20px 16px' : '40px 40px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <h3 style={{
              fontFamily: "'Space Mono', monospace", fontSize: '13px',
              fontWeight: 400, color: '#AAA', margin: '0 0 8px 0',
              letterSpacing: '0.15em',
            }}>
              // 宗门各机构
            </h3>
            <p style={{
              fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
              fontSize: '15px', color: '#777', margin: 0,
            }}>
              十殿同辉 · 各司其职 · 共猎天骄
            </p>
          </div>
          {/* 总览指标 */}
          <div style={{
            display: 'flex', gap: '20px',
            padding: '12px 20px',
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.06)',
          }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: '#ADFF00' }}>{activeCount}</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', marginTop: '2px' }}>运转机构</div>
            </div>
            <div style={{ width: '1px', background: 'rgba(255,255,255,0.06)' }} />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: sysStatus.scheduler ? '#ADFF00' : '#666' }}>{sysStatus.scheduler ? 'ON' : 'OFF'}</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', marginTop: '2px' }}>调度引擎</div>
            </div>
            <div style={{ width: '1px', background: 'rgba(255,255,255,0.06)' }} />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: '#AAA' }}>{sysStatus.reports}</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', marginTop: '2px' }}>报告产出</div>
            </div>
          </div>
        </div>
      </div>

      {/* Grid */}
      <div style={{ padding: mobile ? '0 20px 24px' : '0 40px 40px' }}>
        <div ref={gridRef} style={{
          display: 'grid',
          gridTemplateColumns: mobile ? 'repeat(2, 1fr)' : 'repeat(5, 1fr)',
          gap: '12px',
        }}>
          {DEPTS.map((dept) => (
            <DeptCard
              key={dept.id}
              dept={dept}
              metric={dept.id === 'tiangong' ? undefined : metrics[dept.id]}
              metric2={dept.id === 'tianji' ? metrics.tianji2 : dept.id === 'shenji' ? metrics.shenji2 : dept.id === 'tiangong' ? metrics.tiangong2 : undefined}
              services={dept.id === 'tiangong' ? tianGongSvcs : undefined}
              onRefresh={dept.id === 'tianji' ? fetchTianjiMetrics : undefined}
              refreshing={dept.id === 'tianji' ? tianjiPolling : undefined}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
