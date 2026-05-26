import AsciiCanvas from '../components/AsciiCanvas';
import { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import { fetchDingshulu, fetchTianjijuan, extractNewsTitle, extractReportFilename, type DingshuluRecord } from '../services/cozeApi';
import { useMobile } from '../hooks/useMobile';
import { useBackendHealth } from '../hooks/useBackendHealth';

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
        bottom: '240px',
        left: '48px',
        zIndex: 12,
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
function ValuationCorePanel({ mobile }: { mobile: boolean }) {
  const navigate = useNavigate();
  const [total, setTotal] = useState(0);
  const [activeCount, setActiveCount] = useState(0);
  const online = useBackendHealth();
  const isBurning = activeCount > 0;

  useEffect(() => {
    fetchDingshulu().then((ds) => setTotal(ds.length)).catch(() => setTotal(-1));
    const check = () => {
      fetch('/api/status')
        .then((r) => r.json())
        .then((s) => setActiveCount((s.active_jobs || []).length))
        .catch(() => setActiveCount(-1));
    };
    check();
    const id = setInterval(check, 15_000);
    return () => clearInterval(id);
  }, []);

  const glowIntensity = isBurning ? '0 0 28px rgba(173,255,0,0.6), 0 0 60px rgba(255,92,0,0.25)' : '0 0 16px rgba(173,255,0,0.3)';
  const borderColor = isBurning ? 'rgba(173, 255, 0, 0.4)' : 'rgba(173, 255, 0, 0.15)';
  const bgAlpha = isBurning ? '0.92' : '0.85';

  return (
    <div
      onClick={() => navigate('/dashboard')}
      title="进入估值重构仪表盘"
      style={{
        position: 'absolute',
        bottom: mobile ? '16px' : '48px',
        left: mobile ? '16px' : '48px',
        zIndex: 15,
        width: mobile ? 'calc(100% - 32px)' : '420px',
        background: `rgba(5, 4, 1, ${bgAlpha})`,
        backdropFilter: 'blur(10px)',
        border: `1px solid ${borderColor}`, borderRadius: 6,
        padding: mobile ? '20px 24px' : '32px 36px',
        pointerEvents: 'auto',
        cursor: 'pointer',
        transition: 'all 0.4s ease',
        boxShadow: isBurning ? glowIntensity : 'none',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#ADFF00';
        e.currentTarget.style.boxShadow = isBurning
          ? '0 0 40px rgba(173,255,0,0.75), 0 0 80px rgba(255,92,0,0.35)'
          : '0 0 24px rgba(173,255,0,0.4)';
        e.currentTarget.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = borderColor;
        e.currentTarget.style.boxShadow = isBurning ? glowIntensity : 'none';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      <span style={{
        fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#777',
        letterSpacing: '0.18em',
      }}>
        宗门核心系统
      </span>

      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <h2 style={{
          fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace",
          fontSize: mobile ? '22px' : '28px', fontWeight: 400, color: '#ADFF00',
          letterSpacing: '0.08em', margin: '10px 0 0 0',
          textShadow: glowIntensity,
          animation: isBurning ? 'pulse 1.5s ease-in-out infinite' : 'none',
        }}>
          估值重构炉
        </h2>
        {isBurning && (
          <span style={{
            marginTop: '10px', fontFamily: "'Space Mono', monospace", fontSize: '10px',
            color: '#FF5C00', border: '1px solid rgba(255,92,0,0.3)',
            padding: '1px 8px', animation: 'pulse 1.2s ease-in-out infinite',
          }}>
            炼化中 · {activeCount}
          </span>
        )}
      </div>

      <div style={{ margin: '20px 0', display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span style={{ display: 'block', width: '40px', height: '2px', background: isBurning ? 'rgba(255,92,0,0.5)' : 'rgba(173,255,0,0.3)', transition: 'background 0.4s' }} />
        <span style={{ width: '4px', height: '4px', background: isBurning ? '#FF5C00' : '#ADFF00', boxShadow: isBurning ? '0 0 8px rgba(255,92,0,0.6)' : 'none', transition: 'all 0.4s' }} />
        <span style={{ display: 'block', flex: 1, height: '2px', background: 'rgba(255,255,255,0.06)' }} />
      </div>

      <p style={{
        fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
        fontSize: '15px', fontWeight: 400, lineHeight: 1.9,
        color: '#AAA', margin: '0 0 20px 0',
      }}>
        {isBurning
          ? `丹炉烈焰正盛 · ${activeCount} 道工序正在炼化中`
          : '以事件驱动引擎扫描市场异动，以预研数据炼制「潜力报告」。念念相续，天机无相。'}
      </p>

      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr',
        gap: '16px', borderTop: '1px solid rgba(255,255,255,0.06)',
        paddingTop: '18px',
      }}>
        <div>
          <span style={{
            display: 'block', fontFamily: "'Space Mono', monospace",
            fontSize: '11px', color: '#777', letterSpacing: '0.1em', marginBottom: '6px',
          }}>
            引擎状态
          </span>
          <span style={{
            display: 'block', fontFamily: "'Geist Pixel', monospace",
            fontSize: '18px', color: !online ? '#FF5C00' : (isBurning ? '#FF5C00' : '#ADFF00'),
            letterSpacing: '0.04em', transition: 'color 0.4s',
          }}>
            {!online ? '离线' : (isBurning ? '炼化中' : '运转中')}
          </span>
        </div>
        <div>
          <span style={{
            display: 'block', fontFamily: "'Space Mono', monospace",
            fontSize: '11px', color: '#777', letterSpacing: '0.1em', marginBottom: '6px',
          }}>
            报告产出
          </span>
          <span style={{
            display: 'block', fontFamily: "'Geist Pixel', monospace",
            fontSize: '18px', color: total < 0 ? '#FF5C00' : '#A7A7A7', letterSpacing: '0.04em',
          }}>
            {total < 0 ? '—' : total.toLocaleString()}
          </span>
        </div>
      </div>

      {/* hover 提示 */}
      <div style={{
        marginTop: '14px', textAlign: 'right', opacity: 0.6,
        fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#ADFF00',
        letterSpacing: '0.1em', transition: 'opacity 0.3s',
      }}>
        → 进入仪表盘
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
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
        {/* Header — 固定标题区 */}
        <div style={{
          flexShrink: 0,
          padding: mobile ? '24px 20px 0' : '32px 40px 0',
        }}>
          <p style={{
            fontFamily: "'Space Mono', monospace", fontSize: '13px',
            letterSpacing: '0.2em', color: '#555', margin: '0 0 16px 0',
          }}>
            // 长流水
          </p>
          <h1 style={{
            fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace",
            fontSize: mobile ? '42px' : 'clamp(48px, 6vw, 84px)',
            fontWeight: 400, lineHeight: 1.0, color: '#ADFF00',
            margin: '0 0 24px 0', letterSpacing: '0.04em',
            textShadow: '0 0 32px rgba(173,255,0,0.28)',
          }}>
            神机百炼
          </h1>
          <div style={{ marginBottom: '24px' }}>
            <p style={{
              fontFamily: "'Noto Sans SC', sans-serif", fontSize: '18px',
              fontWeight: 400, lineHeight: 2.0, color: '#888', margin: 0, letterSpacing: '0.08em',
            }}>念念相续，天机无相。</p>
            <p style={{
              fontFamily: "'Noto Sans SC', sans-serif", fontSize: '18px',
              fontWeight: 400, lineHeight: 2.0, color: '#888', margin: 0, letterSpacing: '0.08em',
            }}>大道所向，因果成章。</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
            <span style={{
              width: '8px', height: '8px', background: '#ADFF00',
              boxShadow: '0 0 8px rgba(173,255,0,0.5)',
              display: 'inline-block', animation: 'pulse 2s ease-in-out infinite',
            }} />
            <p style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '15px', color: '#A7A7A7', letterSpacing: '0.1em', margin: 0 }}>
              当前状态: 持续运转
            </p>
          </div>
        </div>

        {/* Scroll — 报告列表 */}
        <div style={{
          flex: 1, overflowY: 'auto', overflowX: 'hidden',
          padding: mobile ? '0 20px 24px' : '0 40px 28px',
          scrollbarWidth: 'none',
        }}>
          <TodayReports />
        </div>

        {/* Bottom: Countdown */}
        <div style={{
          padding: mobile ? '16px 20px' : '20px 40px',
          borderTop: '1px solid rgba(173,255,0,0.12)',
          background: '#050401',
          zIndex: 10,
        }}>
          <CountdownTimer />
        </div>
      </div>

      {/* ====== RIGHT PANEL ====== */}
      {!mobile && (
        <div style={{ position: 'relative', width: '60%', background: '#050401', overflow: 'hidden' }}>
          <AsciiCanvas />
          {/* 有钱花吉祥物 — 面板背后 */}
          <MascotSprite />
          <ValuationCorePanel mobile={false} />
        </div>
      )}
    </section>
  );
}
