import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import gsap from 'gsap';
import AsciiCanvas from '../components/AsciiCanvas';
import { useMobile } from '../hooks/useMobile';
import { useBackendHealth } from '../hooks/useBackendHealth';
import {
  fetchDingshulu, fetchTianjijuan, fetchTotalCount,
  extractNewsTitle, extractReportFilename, type DingshuluRecord,
} from '../services/cozeApi';

/* ================================================================== */
/*  通用样式常量                                                        */
/* ================================================================== */
const PANEL_STYLE: React.CSSProperties = {
  background: 'rgba(5,4,1,0.90)',
  backdropFilter: 'blur(3px)',
  border: '1px solid rgba(173,255,0,0.1)',
  overflow: 'hidden',
  display: 'flex',
  flexDirection: 'column',
  flex: 1,
  minHeight: 0,
  cursor: 'pointer',
  transition: 'all 0.3s ease',
};

// 四角阵眼 — hover 时外扩
function Corners({ hover }: { hover: boolean }) {
  const offset = hover ? '-3px' : '0px';
  return <>
    {['top-left','top-right','bottom-left','bottom-right'].map(pos => (
      <div key={pos} style={{
        position:'absolute',width:'10px',height:'10px',zIndex:3,pointerEvents:'none',
        transition: 'all 0.3s ease',
        ...(pos.includes('top')?{top:offset}:{bottom:offset}),
        ...(pos.includes('left')?{left:offset}:{right:offset}),
        ...(pos==='top-left'?{borderTop:'2px solid #ADFF00',borderLeft:'2px solid #ADFF00'}:
            pos==='top-right'?{borderTop:'2px solid #ADFF00',borderRight:'2px solid #ADFF00'}:
            pos==='bottom-left'?{borderBottom:'2px solid #ADFF00',borderLeft:'2px solid #ADFF00'}:
            {borderBottom:'2px solid #ADFF00',borderRight:'2px solid #ADFF00'}),
        opacity:hover ? 1 : 0.8,
      }} />
    ))}
  </>;
}

const PANEL_HEADER_STYLE: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  padding: '10px 14px',
  borderBottom: '1px solid rgba(173,255,0,0.08)',
  flexShrink: 0,
};

function formatDate(ts: string) {
  if (!ts) return '';
  const d = new Date(ts);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

const PANEL_BODY_STYLE: React.CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '8px 14px',
  scrollbarWidth: 'none',
};

/* ================================================================== */
/*  阵法运转特效 — 面板边框符文流光                                        */
/* ================================================================== */
export function ZhenfaBorder({ active }: { active: boolean }) {
  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 2 }}>
      {['top-left', 'top-right', 'bottom-left', 'bottom-right'].map((pos) => {
        const style: React.CSSProperties = {
          position: 'absolute',
          width: '10px', height: '10px',
          ...(pos.includes('top') ? { top: '0px' } : { bottom: '0px' }),
          ...(pos.includes('left') ? { left: '0px' } : { right: '0px' }),
          ...(pos === 'top-left' && { borderTop: '2px solid #ADFF00', borderLeft: '2px solid #ADFF00' }),
          ...(pos === 'top-right' && { borderTop: '2px solid #ADFF00', borderRight: '2px solid #ADFF00' }),
          ...(pos === 'bottom-left' && { borderBottom: '2px solid #ADFF00', borderLeft: '2px solid #ADFF00' }),
          ...(pos === 'bottom-right' && { borderBottom: '2px solid #ADFF00', borderRight: '2px solid #ADFF00' }),
          opacity: active ? 0.9 : 0.3,
          transition: 'opacity 0.8s',
        };
        return <div key={pos} style={style} />;
      })}
      <div style={{
        position: 'absolute', top: '0px', left: '16px', right: '16px', height: '3px',
        backgroundImage: active
          ? 'linear-gradient(90deg, transparent 0%, rgba(173,255,0,0.3) 20%, rgba(173,255,0,0.95) 50%, rgba(173,255,0,0.3) 80%, transparent 100%)'
          : 'linear-gradient(90deg, transparent, rgba(173,255,0,0.2) 50%, transparent)',
        backgroundSize: '200% 100%',
        backgroundRepeat: 'no-repeat',
        animation: active ? 'shimmer 3s ease-in-out infinite' : 'none',
        boxShadow: active ? '0 0 8px rgba(173,255,0,0.4)' : 'none',
      }} />
    </div>
  );
}

function PanelHeader({ code, name, subtitle, status, onClick }: {
  code: string; name: string; subtitle: string; status?: 'active' | 'idle' | 'warning';
  onClick?: () => void;
}) {
  const [h, setH] = useState(false);
  const dotColor = status === 'active' ? '#ADFF00' : status === 'warning' ? '#FF5C00' : '#555';
  const codeColor = h ? '#ADFF00' : '#777';
  const subColor = h ? '#888' : '#555';
  return (
    <div style={{ ...PANEL_HEADER_STYLE, cursor: onClick ? 'pointer' : undefined }}
      onClick={onClick}
      onMouseEnter={() => { if (onClick) setH(true); }}
      onMouseLeave={() => { if (onClick) setH(false); }}
    >
      <span style={{
        width: '6px', height: '6px', borderRadius: '50%',
        background: dotColor,
        boxShadow: status === 'active' ? `0 0 8px ${dotColor}80` : 'none',
        animation: status === 'active' ? 'pulse 2s ease-in-out infinite' : 'none',
        flexShrink: 0,
      }} />
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: codeColor, letterSpacing: '0.1em', flexShrink: 0, transition: 'color 0.2s' }}>
        {code}
      </span>
      <span style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.04)', margin: '0 8px' }} />
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: subColor, letterSpacing: '0.08em', transition: 'color 0.2s' }}>
        {subtitle}
      </span>
    </div>
  );
}

/* ================================================================== */
/*  TianyanPanel — 天眼司 实时事件监听                                    */
/* ================================================================== */
const LEVEL_LABEL: Record<string, { name: string; color: string }> = {
  '5': { name: '道变', color: '#AD00FF' },
  '4': { name: '天兆', color: '#FF5C00' },
  '3': { name: '雷动', color: '#FF8C00' },
  '2': { name: '风起', color: '#4ECDC4' },
  '1': { name: '微澜', color: '#666' },
  '0': { name: '尘外', color: '#444' },
};
const HIGH_RESPONSE_LEVELS = ['4', '5'];

interface TianjiEvent {
  id: string; stock_name: string; stock_code: string;
  level: string; news_content: string;
  bstudio_create_time?: string;
}

export function TianyanPanel() {
  const navigate = useNavigate();
  const [hover, setHover] = useState(false);
  const [allRecords, setAllRecords] = useState<TianjiEvent[]>([]);
  const [pollInfo, setPollInfo] = useState({ last: '—', next: '—' });
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [fullContent, setFullContent] = useState<Record<string, string>>({});
  const scrollRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(() => {
    Promise.all([
      fetchTianjijuan().then((items) => {
        setAllRecords(items.sort((a, b) => (b.bstudio_create_time || '').localeCompare(a.bstudio_create_time || '')) as TianjiEvent[]);
      }),
      fetch('/api/status')
        .then((r) => r.json())
        .then((s) => {
          setPollInfo({
            last: s.last_poll_at
              ? new Date(s.last_poll_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })
              : '—',
            next: s.next_poll_at
              ? new Date(s.next_poll_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })
              : '—',
          });
        })
        .catch(() => {}),
    ]).catch(() => {});
  }, []);

  useEffect(() => { refresh(); const id = setInterval(refresh, 60_000); return () => clearInterval(id); }, [refresh]);

  const todayStr = new Date().toISOString().slice(0, 10);
  const highResponse = allRecords.filter(
    (r) => HIGH_RESPONSE_LEVELS.includes(r.level) && (r.bstudio_create_time || '').startsWith(todayStr)
  );
  const normalItems = allRecords.filter((r) => !highResponse.includes(r));

  const handleItemClick = (ev: TianjiEvent, e: React.MouseEvent) => {
    e.stopPropagation();
    const lvl = parseInt(ev.level) || 0;
    if (lvl >= 3) {
      const eid = ev.id || `${ev.stock_code}-${ev.bstudio_create_time}`;
      if (expandedId === eid) {
        setExpandedId(null);
      } else {
        setExpandedId(eid);
        if (!fullContent[eid]) {
          setFullContent(prev => ({ ...prev, [eid]: ev.news_content || '' }));
        }
      }
    }
  };

  return (
    <div style={{ ...PANEL_STYLE, position: 'relative' }}
      onMouseEnter={(e) => { setHover(true); e.currentTarget.style.borderColor = '#ADFF00'; }}
      onMouseLeave={(e) => { setHover(false); e.currentTarget.style.borderColor = 'rgba(173,255,0,0.1)'; }}
    >
      <Corners hover={hover} />
      <PanelHeader code="天眼司" name="天眼" subtitle="监听天下异象" status="active" onClick={() => navigate('/tianjifeng')} />
      <div ref={scrollRef} style={PANEL_BODY_STYLE} className="hide-scroll">
        {allRecords.length === 0 && (
          <div style={{ padding: '20px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '24px', color: '#555' }}>
            天眼巡游中，暂无资讯...
          </div>
        )}
        {/* 今日高响应信号 */}
        {highResponse.length > 0 ? (
          <div style={{ marginBottom: '12px' }}>
            <div style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '18px', color: '#FF5C00', letterSpacing: '0.1em', marginBottom: '6px', borderBottom: '1px solid rgba(255,92,0,0.15)', paddingBottom: '6px' }}>
              ▍今日高响应 ({highResponse.length})
            </div>
            {highResponse.map((ev) => {
              const lvl = LEVEL_LABEL[ev.level] || LEVEL_LABEL['0'];
              const timeStr = ev.bstudio_create_time ? new Date(ev.bstudio_create_time + '+08:00').toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' }) : '';
              const eid = ev.id || `${ev.stock_code}-${ev.bstudio_create_time}`;
              const isOpen = expandedId === eid;
              const newsText = (ev.news_content || '').replace(/<[^>]*>/g, '').slice(0, 55);
              return (<div key={ev.id}>
                <div onClick={(e) => handleItemClick(ev, e)} style={{ padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.025)', cursor: 'pointer', borderLeft: `3px solid ${lvl.color}40`, paddingLeft: '6px', transition: 'background 0.15s' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,92,0,0.04)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                    <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '15px', color: lvl.color, border: `1px solid ${lvl.color}40`, padding: '0px 3px', flexShrink: 0 }}>{lvl.name}</span>
                    <span style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '17px', fontWeight: 600, color: '#F2F4F3', flexShrink: 0 }}>{ev.stock_name}</span>
                    <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#666', flexShrink: 0 }}>{ev.stock_code}</span>
                    <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', color: '#F2F4F3', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 0 }}>{newsText || '(无内容)'}</span>
                    <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#FF8C00', flexShrink: 0 }}>{timeStr}</span>
                    <span style={{ color: '#444', fontSize: '12px', transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
                  </div>
                </div>
                {isOpen && fullContent[eid] && (
                  <div style={{ padding: '8px 12px 8px 18px', background: 'rgba(255,255,255,0.02)', borderLeft: `3px solid ${lvl.color}30`, borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                    <div style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', lineHeight: 1.8, color: '#AAA' }}>
                      {fullContent[eid].replace(/<[^>]*>/g, '')}
                    </div>
                  </div>
                )}
              </div>);
            })}
          </div>
        ) : allRecords.length > 0 && (
          <div style={{ marginBottom: '12px', padding: '12px', textAlign: 'center', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#555', letterSpacing: '0.06em' }}>天机潜藏 · 暂无道变天兆</span>
          </div>
        )}
        {/* 其余资讯瀑布 */}
        {normalItems.map((ev, i) => {
          const lvl = LEVEL_LABEL[ev.level] || LEVEL_LABEL['0'];
          const timeStr = ev.bstudio_create_time ? new Date(ev.bstudio_create_time + '+08:00').toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' }) : '';
          const eid = ev.id || `n-${i}`;
          const isOpen = expandedId === eid;
          const newsText = (ev.news_content || '').replace(/<[^>]*>/g, '').slice(0, 55);
          return (<div key={ev.id || `n-${i}`}>
            <div onClick={(e) => handleItemClick(ev, e)} style={{ padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,0.025)', cursor: 'pointer', transition: 'background 0.15s' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(173,255,0,0.03)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '15px', color: lvl.color, border: `1px solid ${lvl.color}40`, padding: '0px 3px', flexShrink: 0, lineHeight: 1.2 }}>{lvl.name}</span>
                <span style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '17px', fontWeight: 600, color: '#F2F4F3', flexShrink: 0 }}>{ev.stock_name}</span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#666', flexShrink: 0 }}>{ev.stock_code}</span>
                <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', color: '#888', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 0 }}>{newsText || '(无内容)'}</span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#444', flexShrink: 0 }}>{timeStr}</span>
                {parseInt(ev.level) >= 3 && <span style={{ color: '#444', fontSize: '12px', transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>}
              </div>
            </div>
            {isOpen && fullContent[eid] && (
              <div style={{ padding: '8px 12px 8px 18px', background: 'rgba(255,255,255,0.02)', borderLeft: `3px solid ${lvl.color}30`, borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                <div style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', lineHeight: 1.8, color: '#AAA' }}>
                  {fullContent[eid].replace(/<[^>]*>/g, '')}
                </div>
              </div>
            )}
          </div>);
        })}
      </div>
      <div style={{ padding: '7px 18px', borderTop: '1px solid rgba(255,255,255,0.04)', textAlign: 'right', flexShrink: 0, cursor: 'pointer', transition: 'background 0.15s' }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; const s = e.currentTarget.querySelector('span'); if (s) { s.style.opacity = '1'; s.style.textShadow = '0 0 8px rgba(173,255,0,0.3)'; } }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; const s = e.currentTarget.querySelector('span'); if (s) { s.style.opacity = '0.6'; s.style.textShadow = 'none'; } }}
        onClick={() => navigate('/tianjifeng')}
        ><span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#ADFF00', letterSpacing: '0.08em', opacity: 0.6 }}>→ 天机峰</span>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  DingshuluPanel — 定数录 估值报告摘要                                  */
/* ================================================================== */
const TIER_STYLE: Record<string, { color: string }> = {
  '★★★': { color: '#ADFF00' },
  '★★☆': { color: '#FF8C00' },
  '★☆☆': { color: '#666' },
};

export function DingshuluPanel() {
  const navigate = useNavigate();
  const [hover, setHover] = useState(false);
  const [reports, setReports] = useState<DingshuluRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [narratives, setNarratives] = useState<Record<string, string>>({});
  const containerRef = useRef<HTMLDivElement>(null);

  // 展开时拉取报告 narrative
  useEffect(() => {
    if (!expandedId) return;
    const rep = reports.find((r, i) => (r.id || String(i)) === expandedId);
    if (!rep?.report_html_url || narratives[expandedId]) return;
    const parts = rep.report_html_url.split('/');
    const filename = parts[parts.length - 1];
    fetch(`/api/report/data/${filename}`)
      .then(r => r.json())
      .then(d => {
        const n = d.agent3?.narrative || d.narrative || '';
        if (n) setNarratives(prev => ({ ...prev, [expandedId]: String(n) }));
      })
      .catch(() => {});
  }, [expandedId, reports]);

  useEffect(() => {
    fetchDingshulu()
      .then((ds) => { setReports(ds.slice(0, 15)); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!containerRef.current || reports.length === 0) return;
    const items = containerRef.current.querySelectorAll('.dingshulu-item');
    gsap.fromTo(items,
      { opacity: 0, y: 8 },
      { opacity: 1, y: 0, duration: 0.4, stagger: 0.06, ease: 'power2.out' }
    );
  }, [reports]);

  const stats = {
    high: reports.filter((r) => r.quality_flag === 'HIGH_QUALITY').length,
    spec: reports.filter((r) => r.quality_flag === 'SPECULATIVE').length,
  };

  return (
    <div ref={containerRef} style={{ ...PANEL_STYLE, position: 'relative' }}
      onMouseEnter={(e) => { setHover(true); e.currentTarget.style.borderColor = '#ADFF00'; }}
      onMouseLeave={(e) => { setHover(false); e.currentTarget.style.borderColor = 'rgba(173,255,0,0.1)'; }}
    >
      <Corners hover={hover} />
      <PanelHeader code="定数录" name="定数录" subtitle="估值重构 · 情景推演" status="active" onClick={() => navigate('/cangjingyun?table=dingshulu')} />

      {/* 今日产出 */}
      <div style={{ padding: '6px 14px', borderBottom: '1px solid rgba(255,255,255,0.04)', flexShrink: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#ADFF00' }}>近期产出 {reports.length} 份估值报告</span>
      </div>

      {/* 报告列表 */}
      <div style={PANEL_BODY_STYLE} className="hide-scroll">
        {loading && (
          <div style={{ padding: '20px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '24px', color: '#555' }}>
            加载中...
          </div>
        )}
        {!loading && reports.length === 0 && (
          <div style={{ padding: '20px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '24px', color: '#555' }}>
            暂无定数录产出
          </div>
        )}
        {reports.map((rep, i) => {
          const tier = TIER_STYLE[rep.trade_tier?.slice(0, 3)] || TIER_STYLE['★☆☆'];
          const probWtd = parseFloat(rep.prob_weighted_upside_pct || '0');
          const isOpen = expandedId === (rep.id || String(i));
          const fn = extractReportFilename(rep);
          const narrativeStr = narratives[rep.id || String(i)] || '';
          return (
            <div
              key={rep.id || i}
              className="dingshulu-item"
              style={{
                padding: '0', borderBottom: '1px solid rgba(255,255,255,0.03)',
                cursor: 'pointer', opacity: 0,
                borderLeft: `3px solid ${tier.color}30`,
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(173,255,0,0.03)';
                e.currentTarget.style.borderLeftColor = tier.color;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.borderLeftColor = `${tier.color}30`;
              }}
            >
              {/* 摘要行 — 始终可见 */}
              <div onClick={() => setExpandedId(isOpen ? null : (rep.id || String(i)))}
                style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 10px' }}>
                <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '22px', color: tier.color, flexShrink: 0 }}>{rep.trade_tier?.slice(0, 3) || '★☆☆'}</span>
                <span
                  onClick={(e) => { e.stopPropagation(); if (fn) navigate(`/report/v4/${fn}`); }}
                  style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '24px', fontWeight: 600, color: '#F2F4F3', textDecoration: 'none' }}
                  onMouseEnter={(e2) => { e2.currentTarget.style.color = '#ADFF00'; }}
                  onMouseLeave={(e2) => { e2.currentTarget.style.color = '#F2F4F3'; }}
                >{rep.stock_name}</span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '20px', color: '#666' }}>{rep.stock_code}</span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '18px', color: '#555', letterSpacing: '0.04em' }}>概率加权</span>
                <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '24px', color: probWtd >= 0 ? '#ADFF00' : '#FF5C00' }}>
                  {probWtd >= 0 ? '+' : ''}{rep.prob_weighted_upside_pct || '—'}%
                </span>
                <span style={{ color: '#444', fontSize: '16px', transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
              </div>
              {/* 三情景 + 日期 */}
              <div style={{ padding: '0 10px 4px 10px', display: 'flex', alignItems: 'center' }}>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#AAA', marginRight: '10px' }}>基 <span style={{ color: '#F2F4F3' }}>{rep.base_upside_pct || '—'}%</span></span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#AAA', marginRight: '10px' }}>牛 <span style={{ color: '#ADFF00' }}>{rep.bull_upside_pct || '—'}%</span></span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#AAA', marginRight: '10px' }}>熊 <span style={{ color: '#FF5C00' }}>{rep.bear_upside_pct || '—'}%</span></span>
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555' }}>{formatDate(rep.bstudio_create_time)}</span>
              </div>
              {/* 展开详情 */}
              {isOpen && (
                <div style={{ padding: '6px 10px 8px 18px', borderTop: '1px solid rgba(255,255,255,0.03)' }}>
                  {narrativeStr && (
                    <div style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '18px', lineHeight: 1.5, color: '#888', marginBottom: '4px' }}>{narrativeStr}</div>
                  )}
                  <div style={{ textAlign: 'right', display: 'flex', gap: '14px', justifyContent: 'flex-end' }}>
                    <span onClick={(e) => { e.stopPropagation(); navigate(`/avatar-cc?code=${rep.stock_code}`); }}
                      style={{ fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#C88D3A', letterSpacing: '0.06em', cursor: 'pointer', opacity: 0.85 }}
                      onMouseEnter={(e2) => { e2.currentTarget.style.opacity = '1'; e2.currentTarget.style.textShadow = '0 0 8px rgba(200,141,58,0.3)'; }}
                      onMouseLeave={(e2) => { e2.currentTarget.style.opacity = '0.85'; e2.currentTarget.style.textShadow = 'none'; }}
                    >→ 化身决策</span>
                    <span onClick={(e) => { e.stopPropagation(); if (fn) navigate(`/report/v4/${fn}`); }}
                      style={{ fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#ADFF00', letterSpacing: '0.06em', cursor: 'pointer', opacity: 0.85 }}
                      onMouseEnter={(e2) => { e2.currentTarget.style.opacity = '1'; e2.currentTarget.style.textShadow = '0 0 8px rgba(173,255,0,0.3)'; }}
                      onMouseLeave={(e2) => { e2.currentTarget.style.opacity = '0.85'; e2.currentTarget.style.textShadow = 'none'; }}
                    >→ 完整报告</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{
        padding: '8px 18px', borderTop: '1px solid rgba(255,255,255,0.04)',
        textAlign: 'right', flexShrink: 0, cursor: 'pointer', transition: 'background 0.15s',
      }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; const s = e.currentTarget.querySelector('span'); if (s) { s.style.opacity = '1'; s.style.textShadow = '0 0 8px rgba(173,255,0,0.3)'; } }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; const s = e.currentTarget.querySelector('span'); if (s) { s.style.opacity = '0.6'; s.style.textShadow = 'none'; } }}
        onClick={() => navigate('/cangjingyun?table=dingshulu')}
      ><span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#ADFF00', letterSpacing: '0.08em', opacity: 0.6 }}>→ 藏经云</span></div>
    </div>
  );
}

/* ================================================================== */
/*  TrackingPanel — 跟踪令 持仓追踪面板                                   */
/* ================================================================== */
interface TrackingSummary {
  stockCode: string;
  stockName: string;
  direction: 'long' | 'short';
  conviction: number;
  thesisStatus: string;
  thesis: string;
  entryCondition: string;
  returnPct: number;
  nextCatalyst?: { date: string; event: string; impact: string };
  atRiskCount: number;
}

export function TrackingPanel() {
  const navigate = useNavigate();
  const [hover, setHover] = useState(false);
  const [stocks, setStocks] = useState<TrackingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetch('/api/tracking')
      .then((r) => r.json())
      .then((data: Array<Record<string, unknown>>) => {
        const summaries: TrackingSummary[] = (data as any[]).map((d: any) => {
          const lastPrice = d.priceLog?.[d.priceLog.length - 1];
          const atRiskPillars = (d.pillars || []).filter((p: any) => p.status === 'at_risk');
          const upcomingCatalysts = (d.catalystCalendar || [])
            .filter((c: any) => new Date(c.date) >= new Date())
            .sort((a: any, b: any) => a.date.localeCompare(b.date));
          return {
            stockCode: d.stockCode,
            stockName: d.stockName,
            direction: d.direction || 'long',
            conviction: d.conviction || 0,
            thesisStatus: (d.pillars || []).some((p: any) => p.status === 'at_risk')
              ? 'at_risk' : (d.pillars || []).every((p: any) => p.status === 'verified')
              ? 'verified' : (d.pillars || []).every((p: any) => p.status === 'on_track' || p.status === 'verified')
              ? 'on_track' : 'pending',
            thesis: d.thesis || '',
            entryCondition: d.entryCondition || '',
            returnPct: lastPrice?.return_pct || 0,
            nextCatalyst: upcomingCatalysts[0] || undefined,
            atRiskCount: atRiskPillars.length,
          };
        });
        summaries.sort((a, b) => {
          if (a.thesisStatus === 'at_risk' && b.thesisStatus !== 'at_risk') return -1;
          if (b.thesisStatus === 'at_risk' && a.thesisStatus !== 'at_risk') return 1;
          return (a.nextCatalyst?.date || '9999').localeCompare(b.nextCatalyst?.date || '9999');
        });
        setStocks(summaries);
        setExpanded(new Set(summaries.filter((s) => s.thesisStatus === 'at_risk').map((s) => s.stockCode)));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const thesisColor: Record<string, string> = {
    on_track: '#ADFF00', at_risk: '#FF5C00', pending: '#C88D3A', verified: '#888',
  };
  const thesisLabel: Record<string, string> = {
    on_track: '运转', at_risk: '警告', pending: '待验', verified: '已验',
  };

  const toggle = (code: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const stats = {
    total: stocks.length,
    atRisk: stocks.filter((s) => s.thesisStatus === 'at_risk').length,
    catalystWeek: stocks.filter((s) => s.nextCatalyst?.date && new Date(s.nextCatalyst.date) <= new Date(Date.now() + 7 * 86400000)).length,
  };

  return (
    <div style={{ ...PANEL_STYLE, position: 'relative' }}
      onMouseEnter={(e) => { setHover(true); e.currentTarget.style.borderColor = '#ADFF00'; }}
      onMouseLeave={(e) => { setHover(false); e.currentTarget.style.borderColor = 'rgba(173,255,0,0.1)'; }}
    >
      <Corners hover={hover} />
      <PanelHeader
        code="跟踪令" name="跟踪令"
        subtitle={`论点追踪 · 催化剂监控 · ${stats.total}标的`}
        status={stats.atRisk > 0 ? 'warning' : 'active'}
        onClick={() => navigate('/tracking')}
      />
      <div style={PANEL_BODY_STYLE} className="hide-scroll">
        {loading && (
          <div style={{ padding: '16px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#555' }}>
            读取追踪令...
          </div>
        )}
        {!loading && stocks.length === 0 && (
          <div style={{ padding: '16px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '16px', color: '#555' }}>
            暂无追踪令签发
          </div>
        )}
        {stocks.map((s, i) => {
          const tc = thesisColor[s.thesisStatus] || '#555';
          const stockKey = s.stockCode || `s-${i}`;
          const isOpen = expanded.has(stockKey);
          const isLong = s.direction === 'long';
          return (
            <div key={stockKey} style={{
              marginBottom: '6px',
              background: isOpen ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.015)',
              border: `1px solid ${isOpen ? tc + '30' : 'rgba(255,255,255,0.04)'}`,
              borderLeft: `3px solid ${tc}60`,
              transition: 'all 0.2s',
              cursor: 'pointer',
            }}>
              {/* 摘要行 — 始终可见 */}
              <div
                onClick={() => toggle(stockKey)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '8px',
                  padding: '8px 10px',
                }}
              >
                <span style={{
                  fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
                  fontSize: '20px', fontWeight: 600, color: '#F2F4F3',
                }}>{s.stockName}</span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '17px', color: '#666' }}>{s.stockCode}</span>
                <span style={{
                  fontSize: '17px', color: isLong ? '#ADFF00' : '#FF5C00',
                }}>{isLong ? '多' : '空'}</span>
                <span style={{ flex: 1 }} />
                <span style={{
                  fontFamily: "'Space Mono', monospace", fontSize: '17px', color: tc,
                  border: `1px solid ${tc}40`, padding: '0px 4px',
                }}>{thesisLabel[s.thesisStatus]}</span>
                <span style={{
                  fontFamily: "'Geist Pixel', monospace", fontSize: '20px',
                  color: s.returnPct >= 0 ? '#ADFF00' : '#FF5C00',
                }}>
                  {s.returnPct >= 0 ? '+' : ''}{s.returnPct.toFixed(1)}%
                </span>
                <span style={{ color: '#444', fontSize: '17px', transition: 'transform 0.2s', transform: isOpen ? 'rotate(180deg)' : 'none' }}>▼</span>
              </div>

              {/* 展开详情 */}
              {isOpen && (
                <div style={{ padding: '0 10px 10px 14px', borderTop: '1px solid rgba(255,255,255,0.03)' }}>
                  {/* 论点状态 + 置信度 */}
                  <div style={{ display: 'flex', gap: '10px', margin: '6px 0' }}>
                    <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '17px', color: '#888' }}>
                      信心 <span style={{ color: s.conviction >= 70 ? '#ADFF00' : s.conviction >= 40 ? '#C88D3A' : '#FF5C00' }}>{s.conviction}</span>
                    </span>
                    {s.atRiskCount > 0 && (
                      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '17px', color: '#FF5C00' }}>
                        异常支柱 {s.atRiskCount}
                      </span>
                    )}
                  </div>
                  {/* 投资论点 + 入场条件 */}
                  {(s.thesis || s.entryCondition) && (
                    <div style={{ marginBottom: '4px', fontSize: '15px', lineHeight: 1.4 }}>
                      {s.thesis && <div style={{ fontFamily: "'Noto Sans SC', sans-serif", color: '#AAA', marginBottom: '2px' }}><span style={{ color: '#ADFF00', fontSize: '14px' }}>论点 </span>{s.thesis}</div>}
                      {s.entryCondition && <div style={{ fontFamily: "'Noto Sans SC', sans-serif", color: '#888' }}><span style={{ color: '#C88D3A', fontSize: '14px' }}>入场 </span>{s.entryCondition}</div>}
                    </div>
                  )}
                  {/* 下一个催化剂 */}
                  {s.nextCatalyst && (
                    <div style={{
                      padding: '6px 8px', background: 'rgba(255,255,255,0.02)',
                      border: '1px solid rgba(255,255,255,0.04)', marginBottom: '6px',
                    }}>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#ADFF00' }}>⌖</span>
                        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#AAA' }}>{s.nextCatalyst.date}</span>
                        <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: s.nextCatalyst.impact === 'H' ? '#FF5C00' : '#888' }}>
                          {s.nextCatalyst.impact === 'H' ? '高' : s.nextCatalyst.impact === 'M' ? '中' : '低'}影响
                        </span>
                      </div>
                      <div style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', color: '#777', marginTop: '2px', lineHeight: 1.4 }}>
                        {s.nextCatalyst.event}
                      </div>
                    </div>
                  )}
                  {/* 跳转链接 */}
                  <div style={{ textAlign: 'right', marginTop: '4px' }}>
                    <span
                      onClick={(e) => { e.stopPropagation(); navigate(`/tracking?code=${s.stockCode}`); }}
                      style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#ADFF00', letterSpacing: '0.06em', cursor: 'pointer', opacity: 0.6 }}
                      onMouseEnter={(e2) => { e2.currentTarget.style.opacity = '1'; }}
                      onMouseLeave={(e2) => { e2.currentTarget.style.opacity = '0.6'; }}
                    >→ 查看追踪令</span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div style={{
        padding: '6px 14px', borderTop: '1px solid rgba(255,255,255,0.04)',
        textAlign: 'right', flexShrink: 0, cursor: 'pointer', transition: 'background 0.15s',
      }}
        onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.03)'; const s = e.currentTarget.querySelector('span'); if (s) { s.style.opacity = '1'; s.style.textShadow = '0 0 8px rgba(173,255,0,0.3)'; } }}
        onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; const s = e.currentTarget.querySelector('span'); if (s) { s.style.opacity = '0.6'; s.style.textShadow = 'none'; } }}
        onClick={() => navigate('/tracking')}
      ><span style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#ADFF00', letterSpacing: '0.08em', opacity: 0.6 }}>→ 追踪司</span></div>
    </div>
  );
}

/* ================================================================== */
/*  MascotCorner — 有钱花吉祥物（半隐藏于页面下边缘）                       */
/* ================================================================== */
function MascotCorner() {
  const navigate = useNavigate();
  const [hover, setHover] = useState(false);
  return (
    <div style={{ position: 'relative', width: '46px', flexShrink: 0, overflow: 'visible' }}>
      <div
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        onClick={() => navigate('/avatar')}
        title="身外化身 · AI投资推演"
        style={{
          position: 'absolute', bottom: '-50px', right: '0px', zIndex: 25,
          cursor: 'pointer',
          transition: 'all 0.35s cubic-bezier(0.22, 0.61, 0.36, 1)',
          transform: hover ? 'translateY(-58px) scale(1.3)' : 'translateY(0) scale(0.85)',
          opacity: hover ? 1 : 0.65,
        }}
      >
        <div style={{ position: 'relative', width: '80px' }}>
          <img src="/images/youqianhua-raw.png" alt="有钱花"
            style={{
              width: '70px', height: 'auto', display: 'block',
              filter: hover
                ? 'drop-shadow(0 0 10px rgba(173,255,0,0.5)) drop-shadow(0 0 20px rgba(173,255,0,0.2))'
                : 'drop-shadow(0 0 3px rgba(220,255,230,0.2))',
              transition: 'filter 0.3s',
            }}
          />
        </div>
        <div style={{
          textAlign: 'center', marginTop: '-4px',
          fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#555',
          letterSpacing: '0.06em', opacity: hover ? 0.6 : 0,
          transition: 'opacity 0.3s',
        }}>
          身外化身
        </div>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  OrgMiniCards — 十殿机构微型指示（5×2网格）                              */
/* ================================================================== */
function OrgMiniCards() {
  const navigate = useNavigate();
  const depts = [
    { id: 'tianji', name: '天机峰', code: 'TJ-01', desc: '天眼·望气·寻龙·妙音', status: 'active', route: '/tianjifeng' },
    { id: 'cangjing', name: '藏经云', code: 'CJ-02', desc: '藏经阁·天机卷·万业谱', status: 'active', route: '/cangjingyun' },
    { id: 'shenji', name: '神机百炼', code: 'SJ-03', desc: '估值重构炉·调度引擎', status: 'active', route: '/dashboard' },
    { id: 'avatar', name: '身外化身', code: 'HS-04', desc: '灵光·案例·推演', status: 'active', route: '/avatar' },
    { id: 'pojun', name: '破军小队', code: 'PJ-05', desc: 'K线之道·量化指标', status: 'idle', route: '' },
    { id: 'lingyan', name: '凌烟阁', code: 'LY-06', desc: '历史战绩·推动进化', status: 'idle', route: '' },
    { id: 'guanlan', name: '观澜亭', code: 'GL-07', desc: '常委会议事·判大势', status: 'active', route: '' },
    { id: 'jianlin', name: '剑林', code: 'JL-08', desc: '模拟盘·天骄榜', status: 'hunting', route: '' },
    { id: 'tiangong', name: '天工小队', code: 'TG-11', desc: '服务巡检·框架运维', status: 'active', route: '' },
    { id: 'heijing', name: '黑镜', code: 'HJ-12', desc: '宗门声量·研报·法旨', status: 'active', route: '' },
  ];
  const sColor: Record<string, string> = { active: '#ADFF00', idle: '#666', hunting: '#FF5C00' };
  // Mini glyph SVGs per department
  const glyph = (id: string, c: string) => {
    const g: Record<string, string> = {
      tianji: '<circle cx="12" cy="12" r="5" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><circle cx="12" cy="12" r="9" fill="none" stroke="'+c+'" stroke-width="0.5" opacity="0.3" stroke-dasharray="2 2"/><circle cx="12" cy="12" r="1.5" fill="'+c+'" opacity="0.8"/>',
      cangjing: '<rect x="4" y="6" width="16" height="12" rx="1" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><line x1="7" y1="10" x2="17" y2="10" stroke="'+c+'" stroke-width="0.5" opacity="0.4"/><line x1="7" y1="13" x2="14" y2="13" stroke="'+c+'" stroke-width="0.5" opacity="0.4"/>',
      shenji: '<polygon points="12,2 22,20 2,20" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><circle cx="12" cy="14" r="3" fill="none" stroke="'+c+'" stroke-width="0.7" opacity="0.5"/><circle cx="12" cy="14" r="1" fill="'+c+'" opacity="0.8"/>',
      avatar: '<circle cx="12" cy="8" r="5" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><path d="M3,22 Q12,13 21,22" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/>',
      pojun: '<polyline points="3,19 7,9 12,14 17,5 21,12" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><circle cx="17" cy="5" r="1.5" fill="'+c+'" opacity="0.8"/>',
      lingyan: '<rect x="4" y="5" width="16" height="14" rx="1" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><circle cx="12" cy="14" r="4" fill="none" stroke="'+c+'" stroke-width="0.7" opacity="0.4" stroke-dasharray="1 1"/>',
      guanlan: '<path d="M3,18 Q8,8 12,14 T21,10" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><circle cx="21" cy="10" r="2" fill="none" stroke="'+c+'" stroke-width="0.7" opacity="0.5"/>',
      jianlin: '<line x1="12" y1="1" x2="12" y2="16" stroke="'+c+'" stroke-width="1" opacity="0.7"/><line x1="8" y1="12" x2="16" y2="12" stroke="'+c+'" stroke-width="0.7" opacity="0.5"/><line x1="10" y1="18" x2="12" y2="23" stroke="'+c+'" stroke-width="0.8" opacity="0.6"/><line x1="14" y1="18" x2="12" y2="23" stroke="'+c+'" stroke-width="0.8" opacity="0.6"/>',
      tiangong: '<circle cx="12" cy="12" r="8" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><circle cx="12" cy="12" r="4" fill="none" stroke="'+c+'" stroke-width="0.7" opacity="0.4" stroke-dasharray="1.5 1.5"/><rect x="10" y="10" width="4" height="4" rx="0.5" fill="'+c+'" opacity="0.5"/>',
      heijing: '<rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="'+c+'" stroke-width="1" opacity="0.6"/><circle cx="12" cy="12" r="5" fill="none" stroke="'+c+'" stroke-width="0.7" opacity="0.4" stroke-dasharray="1 1"/><circle cx="12" cy="12" r="2" fill="'+c+'" opacity="0.5"/>',
    };
    return g[id] || '';
  };
  return (
    <div style={{ padding: '2px', display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '2px', alignContent: 'start', height: '100%' }}>
      {depts.map((d) => {
        const dot = sColor[d.status];
        const clickable = !!d.route;
        return (
          <div key={d.id}
            onClick={() => { if (clickable) navigate(d.route); }}
            style={{
              padding: '4px 3px', textAlign: 'center', cursor: clickable ? 'pointer' : 'default',
              background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)',
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '1px',
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => { if (clickable) { e.currentTarget.style.borderColor = dot; e.currentTarget.style.background = 'rgba(173,255,0,0.04)'; } }}
            onMouseLeave={(e) => { if (clickable) { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.04)'; e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; } }}
          >
            <svg viewBox="0 0 24 24" width="10" height="10" dangerouslySetInnerHTML={{ __html: glyph(d.id, dot) }} />
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px', color: '#CCC', fontWeight: 600, lineHeight: 1.1 }}>{d.name}</span>
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '10px', color: '#555', lineHeight: 1.1, letterSpacing: '0.02em' }}>{d.desc}</span>
          </div>
        );
      })}
    </div>
  );
}

const SLIM_ORGS = [
  { id: 'tianji', name: '天机峰', route: '/tianjifeng' },
  { id: 'cangjing', name: '藏经云', route: '/cangjingyun' },
  { id: 'dashboard', name: '总控台', route: '/dashboard' },
  { id: 'avatar', name: '身外化身', route: '/avatar' },
  { id: 'tracking', name: '追踪令', route: '/tracking' },
  { id: 'agent-config', name: '炼器房', route: '/agent-config' },
];

function SlimOrgStatus() {
  const [pollInfo, setPollInfo] = useState({ last: '—', next: '—' });
  const [time, setTime] = useState('');

  useEffect(() => {
    fetch('/api/status').then(r => r.json()).then(s => {
      setPollInfo({
        last: s.last_poll_at ? new Date(s.last_poll_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' }) : '—',
        next: s.next_poll_at ? new Date(s.next_poll_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' }) : '—',
      });
    }).catch(() => {});
    const tick = () => { const d = new Date(); setTime(`${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`); };
    tick(); const id = setInterval(tick, 1000); return () => clearInterval(id);
  }, []);

  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 2,
      display: 'flex', alignItems: 'center', gap: '12px',
      padding: '5px 20px',
      borderTop: '1px solid rgba(173,255,0,0.06)',
      background: 'rgba(5,4,1,0.85)',
    }}>
      <span style={{ width: '5px', height: '5px', borderRadius: '50%', background: '#ADFF00', boxShadow: '0 0 6px rgba(173,255,0,0.5)', flexShrink: 0 }} />
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#888', letterSpacing: '0.06em' }}>
        调度 {pollInfo.last} → {pollInfo.next}
      </span>
      <span style={{ flex: 1 }} />
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555' }}>UTC+8 {time}</span>
      <span style={{ color: 'rgba(255,255,255,0.08)' }}>|</span>
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#444' }}>长流水宗门</span>
    </div>
  );
}

/* ================================================================== */
/*  PanoramicMonitor — 全景监控主布局                                    */
/* ================================================================== */
export default function PanoramicMonitor() {
  const mobile = useMobile();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    gsap.fromTo(containerRef.current,
      { opacity: 0 },
      { opacity: 1, duration: 0.5, ease: 'power2.out' }
    );
  }, []);

  if (mobile) {
    return (
      <div ref={containerRef} style={{
        display: 'flex', flexDirection: 'column', gap: '6px',
        padding: '6px', background: '#050401', minHeight: '100vh',
      }}>
        <div style={{ height: '400px' }}><DingshuluPanel /></div>
        <div style={{ height: '360px' }}><TianyanPanel /></div>
        <div style={{ height: '360px' }}><TrackingPanel /></div>
        <div style={{ position: 'relative', minHeight: '120px' }}>
          <OrgMiniCards />
          <MascotCorner />
        </div>
        <SlimOrgStatus />
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{
      position: 'relative',
      background: '#050401',
      height: 'calc(100vh - 69px)',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* ── 全屏 ASCII 背景（被面板完全覆盖）── */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 0,
        pointerEvents: 'none', overflow: 'hidden',
      }}>
        <AsciiCanvas dense />
      </div>

      {/* ── 全景监控网格：左定数录 / 右天眼+跟踪令+机构 ── */}
      <div style={{
        position: 'absolute', zIndex: 1,
        top: 0, left: 0, right: 0, bottom: '36px',
        display: 'grid',
        gridTemplateColumns: '0.82fr 1.18fr',
        gridTemplateRows: '2.5fr 2fr 0.8fr',
        gap: '6px',
        padding: '8px',
        overflow: 'hidden',
      }}>
        {/* 左列：定数录 — 全高度 */}
        <div style={{ gridRow: '1 / 4', gridColumn: '1', minHeight: 0 }}>
          <DingshuluPanel />
        </div>

        {/* 右上：天眼司 — 今日高响应 + 瀑布流 */}
        <div style={{ gridRow: '1', gridColumn: '2', minHeight: 0 }}>
          <TianyanPanel />
        </div>

        {/* 右中：跟踪令 — 自选股卡片 */}
        <div style={{ gridRow: '2', gridColumn: '2', minHeight: 0 }}>
          <TrackingPanel />
        </div>

        {/* 右下：吉祥物 */}
        <div style={{ gridRow: '3', gridColumn: '2', position: 'relative', minHeight: 0, overflow: 'visible' }}>
          <MascotCorner />
        </div>
      </div>

      <SlimOrgStatus />
    </div>
  );
}
