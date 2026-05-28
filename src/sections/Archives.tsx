import { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
  fetchLatestRecords, searchRecords, parseRecordToReport, type CozeRecord,
  fetchTianjijuan, extractNewsTitle, type TianjijuanRecord,
  fetchWanyepu, type WanyepuRecord,
  fetchDingshulu, extractReportFilename, type DingshuluRecord,
  fetchYinguobu, type YinguobuRecord,
} from '../services/cozeApi';
import { useMobile } from '../hooks/useMobile';

gsap.registerPlugin(ScrollTrigger);

const TABLE_TABS = [
  { key: 'dingshulu', label: '定数录' },
  { key: 'cangjing', label: '藏经阁' },
  { key: 'tianjijuan', label: '天机卷' },
  { key: 'wanyepu', label: '万业谱' },
  { key: 'yinguobu', label: '因果簿' },
] as const;
type TableKey = typeof TABLE_TABS[number]['key'];

const TJ_LEVEL_CONFIG: Record<string, { name: string; color: string }> = {
  '5': { name: '道变', color: '#AD00FF' },
  '4': { name: '天兆', color: '#FF5C00' },
  '3': { name: '雷动', color: '#FF8C00' },
  '2': { name: '风起', color: '#4ECDC4' },
  '1': { name: '微澜', color: '#666' },
};

const ratingColor: Record<string, string> = {
  'A+': '#ADFF00', 'A': '#ADFF00', 'A-': '#88CC00', 'B+': '#FF5C00', 'B': '#666',
};

function getRating(score: string): string {
  const n = parseFloat(score) || 0;
  if (n >= 85) return 'A+';
  if (n >= 70) return 'A';
  if (n >= 55) return 'A-';
  if (n >= 40) return 'B+';
  return 'B';
}

/* ------------------------------------------------------------------ */
/*  记录卡片                                                          */
/* ------------------------------------------------------------------ */
function RecordCard({ record, index }: { record: CozeRecord; index: number }) {
  const navigate = useNavigate();
  const report = parseRecordToReport(record);
  const score = record.comprehensive_score || '0';
  const rating = getRating(score);

  return (
    <div
      onClick={() => navigate(`/report/${record.id}`)}
      style={{
        padding: '28px 32px',
        background: index % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'rgba(255,255,255,0.03)',
        borderLeft: '2px solid rgba(173,255,0,0.08)',
        transition: 'all 0.3s ease',
        cursor: 'pointer',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'rgba(173,255,0,0.04)';
        e.currentTarget.style.borderLeftColor = '#ADFF00';
        e.currentTarget.style.transform = 'translateX(4px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = index % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'rgba(255,255,255,0.03)';
        e.currentTarget.style.borderLeftColor = 'rgba(173,255,0,0.08)';
        e.currentTarget.style.transform = 'translateX(0)';
      }}
    >
      {/* 头部 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '6px' }}>
            <span style={{
              fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace",
              fontSize: '22px', color: '#F2F4F3', letterSpacing: '0.04em',
            }}>
              {record.stock_name || '—'}
            </span>
            <span style={{
              fontFamily: "'IBM Plex Mono', monospace", fontSize: '13px', color: '#666',
            }}>
              {record.stock_code || ''}
            </span>
          </div>
          <span style={{
            fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555', letterSpacing: '0.1em',
          }}>
            {record.source || '综合'}
          </span>
        </div>
        <div style={{ textAlign: 'right' }}>
          <span style={{
            fontFamily: "'Geist Pixel', monospace", fontSize: '28px', color: ratingColor[rating] || '#666',
            textShadow: `0 0 12px ${ratingColor[rating] || '#666'}40`,
          }}>
            {rating}
          </span>
          <span style={{
            display: 'block', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#444', marginTop: '4px',
          }}>
            评分 {score}
          </span>
        </div>
      </div>

      {/* 摘要 */}
      {record.background && (
        <p style={{
          fontFamily: "'Noto Sans SC', sans-serif",
          fontSize: '14px', lineHeight: 1.8, color: '#888', margin: '0 0 20px 0',
        }}>
          {report.summary}
        </p>
      )}

      {/* 底部指标 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '32px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '16px' }}>
        <div>
          <span style={{ display: 'block', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#777', marginBottom: '4px' }}>
            潜力涨幅
          </span>
          <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '16px', color: '#ADFF00' }}>
            {record.potential_increase || report.potential}
          </span>
        </div>
        <div>
          <span style={{ display: 'block', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#777', marginBottom: '4px' }}>
            产业链
          </span>
          <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '13px', color: '#AAA' }}>
            {record.cylfx?.slice(0, 12) || '—'}
          </span>
        </div>
        <span style={{ flex: 1 }} />
        {record.is_analyzed === 'false' && (
          <span style={{
            fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px',
            color: '#FF5C00', letterSpacing: '0.1em', border: '1px solid rgba(255,92,0,0.3)',
            padding: '2px 8px', marginRight: '12px',
          }}>
            尚未推演
          </span>
        )}
        <span style={{
          fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#ADFF00', letterSpacing: '0.1em',
        }}>
          → 查看完整报告
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  万业谱卡片                                                         */
/* ------------------------------------------------------------------ */
function WanyepuCard({ record }: { record: WanyepuRecord }) {
  const excerpt = record.industry_expert_research
    ? record.industry_expert_research.replace(/[#*]/g, '').replace(/\n/g, ' ').slice(0, 80) + '...'
    : '暂无研报';
  return (
    <div style={{
      padding: '24px 28px', background: 'rgba(255,255,255,0.02)',
      borderLeft: '2px solid rgba(78,205,196,0.2)',
      transition: 'all 0.3s ease', cursor: 'pointer',
    }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(78,205,196,0.04)'; e.currentTarget.style.borderLeftColor = '#4ECDC4'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; e.currentTarget.style.borderLeftColor = 'rgba(78,205,196,0.2)'; }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
        <div>
          <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '16px', fontWeight: 600, color: '#F2F4F3' }}>
            {record.stock_name || '—'}
          </span>
          <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px', color: '#666', marginLeft: '12px' }}>
            {record.stock_code || ''}
          </span>
        </div>
        {record.confidence_score && (
          <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#4ECDC4' }}>
            置信 {record.confidence_score}
          </span>
        )}
      </div>
      <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '13px', lineHeight: 1.7, color: '#888', margin: '0 0 12px 0' }}>
        {excerpt}
      </p>
      <div style={{ display: 'flex', gap: '20px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '12px' }}>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#777' }}>{record.event_date || ''}</span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#555' }}>{record.source || ''}</span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#555' }}>{record.status || ''}</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  定数录卡片                                                         */
/* ------------------------------------------------------------------ */
function DingshuluCard({ record }: { record: DingshuluRecord }) {
  const navigate = useNavigate();
  const probWtd = parseFloat(record.prob_weighted_upside_pct || '0');
  return (
    <div style={{
      padding: '24px 28px', background: 'rgba(255,255,255,0.02)',
      borderLeft: '2px solid rgba(173,255,0,0.15)',
      transition: 'all 0.3s ease', cursor: 'pointer',
    }}
      onClick={() => { const fn = extractReportFilename(record); if (fn) navigate(`/report/v4/${fn}`); }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(173,255,0,0.04)'; e.currentTarget.style.borderLeftColor = '#ADFF00'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; e.currentTarget.style.borderLeftColor = 'rgba(173,255,0,0.15)'; }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '14px', color: '#ADFF00' }}>
            {record.trade_tier || '—'}
          </span>
        </div>
        <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: probWtd >= 0 ? '#ADFF00' : '#FF5C00' }}>
          {probWtd >= 0 ? '+' : ''}{record.prob_weighted_upside_pct || '—'}%
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '10px' }}>
        <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '16px', fontWeight: 600, color: '#F2F4F3' }}>
          {record.stock_name}
        </span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px', color: '#888' }}>{record.stock_code}</span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>{record.event_source}</span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>置信 {record.confidence_score}</span>
      </div>
      <div style={{ display: 'flex', gap: '2px', height: '4px', borderRadius: '2px', overflow: 'hidden', marginBottom: '10px' }}>
        <div style={{ width: `${record.bull_prob || 0}%`, background: '#ADFF00' }} />
        <div style={{ width: `${record.base_prob || 0}%`, background: '#888' }} />
        <div style={{ width: `${record.bear_prob || 0}%`, background: '#FF5C00' }} />
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.04)' }} />
      </div>
      <div style={{ display: 'flex', gap: '20px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#777' }}>
        <span>牛 {record.bull_prob}% / 基 {record.base_prob}% / 熊 {record.bear_prob}%</span>
        <span style={{ color: '#ADFF00' }}>→ 完整报告</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  因果簿卡片                                                         */
/* ------------------------------------------------------------------ */
function YinguobuCard({ record }: { record: YinguobuRecord }) {
  return (
    <div style={{
      padding: '24px 28px', background: 'rgba(255,255,255,0.02)',
      borderLeft: '2px solid rgba(173,0,255,0.15)',
      transition: 'all 0.3s ease', cursor: 'pointer',
    }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(173,0,255,0.04)'; e.currentTarget.style.borderLeftColor = '#AD00FF'; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; e.currentTarget.style.borderLeftColor = 'rgba(173,0,255,0.15)'; }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
        <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '16px', fontWeight: 600, color: '#F2F4F3' }}>
          {record.industry_chain || '未分类产业链'}
        </span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
          {record.analysis_date || ''}
        </span>
      </div>
      {record.event_summary && (
        <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '13px', lineHeight: 1.7, color: '#888', margin: '0 0 12px 0' }}>
          {record.event_summary.slice(0, 100)}{record.event_summary.length > 100 ? '...' : ''}
        </p>
      )}
      <div style={{ display: 'flex', gap: '32px', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '12px' }}>
        <div>
          <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#777', display: 'block', marginBottom: '4px' }}>首选标的</span>
          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '13px', color: '#ADFF00' }}>
            {record.top_pick_name || '—'} {record.top_pick_score ? `(${record.top_pick_score})` : ''}
          </span>
        </div>
        <div>
          <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#777', display: 'block', marginBottom: '4px' }}>次选标的</span>
          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '13px', color: '#AAA' }}>
            {record.runner_up_name || '—'} {record.runner_up_score ? `(${record.runner_up_score})` : ''}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  天机卷卡片                                                         */
/* ------------------------------------------------------------------ */
function TianjijuanCard({ record }: { record: TianjijuanRecord }) {
  const lv = TJ_LEVEL_CONFIG[record.level] || TJ_LEVEL_CONFIG['1'];
  return (
    <div style={{
      padding: '24px 28px', background: 'rgba(255,255,255,0.02)',
      borderLeft: `2px solid ${lv.color}40`,
      transition: 'all 0.3s ease', cursor: 'pointer',
    }}
      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.05)'; e.currentTarget.style.borderLeftColor = lv.color; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(255,255,255,0.02)'; e.currentTarget.style.borderLeftColor = `${lv.color}40`; }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
        <span style={{
          fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: lv.color,
          border: `1px solid ${lv.color}40`, padding: '2px 10px', letterSpacing: '0.1em',
        }}>{lv.name}</span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
          {record.bstudio_create_time?.replace(' +0800 CST', '') || ''}
        </span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#666', border: '1px solid rgba(255,255,255,0.06)', padding: '1px 8px' }}>
          {record.mode}
        </span>
        <span style={{ flex: 1 }} />
        {record.stock_name && (
          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '12px', color: '#888' }}>
            {record.stock_name} {record.stock_code || ''}
          </span>
        )}
      </div>
      <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', lineHeight: 1.7, color: '#AAA', margin: 0 }}>
        {extractNewsTitle(record.news_content, 60)}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  CangjingYun — 藏经云 · 精简卡片布局                              */
/* ------------------------------------------------------------------ */
const PAGE_SIZE = 20;

function PaginationBar({ page, total, onPrev, onNext }: {
  page: number; total: number; onPrev: () => void; onNext: () => void;
}) {
  const totalPages = Math.max(1, total);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      gap: '16px', marginTop: '28px', paddingTop: '20px',
      borderTop: '1px solid rgba(255,255,255,0.04)',
    }}>
      <button onClick={onPrev} disabled={page <= 1}
        style={{
          fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px',
          color: page <= 1 ? '#444' : '#ADFF00',
          background: 'transparent', border: `1px solid ${page <= 1 ? '#333' : 'rgba(173,255,0,0.25)'}`,
          padding: '8px 20px', cursor: page <= 1 ? 'not-allowed' : 'pointer',
          letterSpacing: '0.1em', transition: 'all 0.2s',
        }}
        onMouseEnter={(e) => { if (page > 1) { e.currentTarget.style.background = 'rgba(173,255,0,0.08)'; e.currentTarget.style.borderColor = '#ADFF00'; }}}
        onMouseLeave={(e) => { if (page > 1) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.25)'; }}}
      >← 上一页</button>
      <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#888', letterSpacing: '0.1em' }}>
        {page} / {totalPages}
      </span>
      <button onClick={onNext} disabled={page >= totalPages}
        style={{
          fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px',
          color: page >= totalPages ? '#444' : '#ADFF00',
          background: 'transparent', border: `1px solid ${page >= totalPages ? '#333' : 'rgba(173,255,0,0.25)'}`,
          padding: '8px 20px', cursor: page >= totalPages ? 'not-allowed' : 'pointer',
          letterSpacing: '0.1em', transition: 'all 0.2s',
        }}
        onMouseEnter={(e) => { if (page < totalPages) { e.currentTarget.style.background = 'rgba(173,255,0,0.08)'; e.currentTarget.style.borderColor = '#ADFF00'; }}}
        onMouseLeave={(e) => { if (page < totalPages) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.25)'; }}}
      >下一页 →</button>
    </div>
  );
}

export default function CangjingYun() {
  const sectionRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const mobile = useMobile();
  const location = useLocation();
  const [records, setRecords] = useState<CozeRecord[]>([]);
  const [filtered, setFiltered] = useState<CozeRecord[]>([]);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTable, setActiveTable] = useState<TableKey>('dingshulu');
  const [tjRecords, setTjRecords] = useState<TianjijuanRecord[]>([]);
  const [wpRecords, setWpRecords] = useState<WanyepuRecord[]>([]);
  const [dsRecords, setDsRecords] = useState<DingshuluRecord[]>([]);
  const [ybRecords, setYbRecords] = useState<YinguobuRecord[]>([]);
  const [tjLevel, setTjLevel] = useState('all');
  // 子标签页分页
  const [tjPage, setTjPage] = useState(1);
  const [wpPage, setWpPage] = useState(1);
  const [dsPage, setDsPage] = useState(1);
  const [ybPage, setYbPage] = useState(1);

  useEffect(() => {
    fetchLatestRecords(500)
      .then((data) => {
        setRecords(data);
        setFiltered(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError('连接失败');
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (activeTable === 'tianjijuan' && tjRecords.length === 0) {
      fetchTianjijuan().then(setTjRecords).catch(() => setTjRecords([]));
    } else if (activeTable === 'wanyepu' && wpRecords.length === 0) {
      fetchWanyepu().then(setWpRecords).catch(() => setWpRecords([]));
    } else if (activeTable === 'dingshulu' && dsRecords.length === 0) {
      fetchDingshulu().then(setDsRecords).catch(() => setDsRecords([]));
    } else if (activeTable === 'yinguobu' && ybRecords.length === 0) {
      fetchYinguobu().then(setYbRecords).catch(() => setYbRecords([]));
    }
  }, [activeTable, tjRecords.length, wpRecords.length, dsRecords.length, ybRecords.length]);

  // 切换标签时重置对应分页 + 支持 ?table= 参数
  useEffect(() => {
    setTjPage(1); setWpPage(1); setDsPage(1); setYbPage(1);
  }, [activeTable]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const table = params.get('table') as TableKey | null;
    if (table && TABLE_TABS.some((t) => t.key === table)) {
      setActiveTable(table);
    }
  }, []);

  useEffect(() => {
    if (!search.trim()) {
      setFiltered(records);
      setPage(1);
      return;
    }
    searchRecords(search).then((data) => {
      setFiltered(data);
      setPage(1);
    }).catch(() => setFiltered(records));
  }, [search, records]);

  useEffect(() => {
    if (!sectionRef.current || !listRef.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(listRef.current, { opacity: 0, y: 20 }, {
        opacity: 1, y: 0, duration: 0.6, ease: 'power2.out',
        scrollTrigger: { trigger: sectionRef.current, start: 'top 70%' },
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const paged = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return (
    <section ref={sectionRef} id="cangjingyun" style={{
      position: 'relative', width: '100%', minHeight: 'calc(100vh - 58px)',
      background: '#050401', color: '#F2F4F3',
    }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: mobile ? '32px 20px 48px' : '32px 48px 80px' }}>
      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <span style={{ width: '8px', height: '8px', background: '#ADFF00', boxShadow: '0 0 8px rgba(173,255,0,0.5)', animation: 'pulse 2s ease-in-out infinite', display: 'inline-block' }} />
          <h1 style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: '28px', fontWeight: 400, color: '#ADFF00', margin: 0, letterSpacing: '0.06em', textShadow: '0 0 16px rgba(173,255,0,0.3)' }}>
            藏经云
          </h1>
          <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#444', letterSpacing: '0.1em' }}>云端预研数据库</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '16px', color: '#999', margin: 0 }}>
            已连接 Coze 数据库 · 五大古籍分类
          </p>
          <p style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#ADFF00' }}>
            共 {records.length} 条
          </p>
        </div>
      </div>

      {/* Table Tabs */}
      <div style={{ maxWidth: '1200px', margin: '0 auto 24px', display: 'flex', gap: '4px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        {TABLE_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTable(tab.key)}
            style={{
              fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px',
              color: activeTable === tab.key ? '#ADFF00' : '#555',
              background: 'transparent', border: 'none',
              borderBottom: activeTable === tab.key ? '2px solid #ADFF00' : '2px solid transparent',
              padding: '10px 20px', cursor: 'pointer', letterSpacing: '0.1em',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => { if (activeTable !== tab.key) e.currentTarget.style.color = '#888'; }}
            onMouseLeave={(e) => { if (activeTable !== tab.key) e.currentTarget.style.color = '#555'; }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Search */}
      {activeTable === 'cangjing' && (
        <div style={{ maxWidth: '1200px', margin: '0 auto 28px' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '16px',
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(173,255,0,0.12)',
            padding: '16px 20px',
          }}>
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#ADFF00' }}>$</span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索股票 / 代码 / 板块..."
              style={{
                flex: 1, background: 'transparent', border: 'none', outline: 'none',
                fontFamily: "'Noto Sans SC', sans-serif",
                fontSize: '16px', color: '#F2F4F3',
              }}
            />
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#777' }}>
              {filtered.length} / {records.length}
            </span>
          </div>
        </div>
      )}

      {/* Content */}
      {activeTable === 'cangjing' && (
        <div ref={listRef} style={{ maxWidth: '1200px', margin: '0 auto', opacity: 0 }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: '80px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
              连接藏经云...
            </div>
          )}
          {error && (
            <div style={{ textAlign: 'center', padding: '80px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#FF5C00' }}>
              {error}
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div style={{ textAlign: 'center', padding: '80px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
              未找到匹配记录
            </div>
          )}

          {/* 卡片列表 — 分页 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {paged.map((record, index) => (
              <RecordCard key={record.id} record={record} index={index} />
            ))}
          </div>

          {/* 分页控制 */}
          {!loading && filtered.length > 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: '16px', marginTop: '28px', paddingTop: '20px',
              borderTop: '1px solid rgba(255,255,255,0.04)',
            }}>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                style={{
                  fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px',
                  color: currentPage <= 1 ? '#444' : '#ADFF00',
                  background: 'transparent', border: `1px solid ${currentPage <= 1 ? '#333' : 'rgba(173,255,0,0.25)'}`,
                  padding: '8px 20px', cursor: currentPage <= 1 ? 'not-allowed' : 'pointer',
                  letterSpacing: '0.1em', transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { if (currentPage > 1) { e.currentTarget.style.background = 'rgba(173,255,0,0.08)'; e.currentTarget.style.borderColor = '#ADFF00'; }}}
                onMouseLeave={(e) => { if (currentPage > 1) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.25)'; }}}
              >
                ← 上一页
              </button>
              <span style={{
                fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#888', letterSpacing: '0.1em',
              }}>
                {currentPage} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                style={{
                  fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px',
                  color: currentPage >= totalPages ? '#444' : '#ADFF00',
                  background: 'transparent', border: `1px solid ${currentPage >= totalPages ? '#333' : 'rgba(173,255,0,0.25)'}`,
                  padding: '8px 20px', cursor: currentPage >= totalPages ? 'not-allowed' : 'pointer',
                  letterSpacing: '0.1em', transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { if (currentPage < totalPages) { e.currentTarget.style.background = 'rgba(173,255,0,0.08)'; e.currentTarget.style.borderColor = '#ADFF00'; }}}
                onMouseLeave={(e) => { if (currentPage < totalPages) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.25)'; }}}
              >
                下一页 →
              </button>
            </div>
          )}
        </div>
      )}

      {/* 天机卷 */}
      {activeTable === 'tianjijuan' && (() => {
        const filtered = tjRecords.filter((r) => tjLevel === 'all' || r.level === tjLevel);
        const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
        const currentPage = Math.min(tjPage, totalPages);
        const paged = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
        return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '1200px', margin: '0 auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#ADFF00' }}>共 {filtered.length} 条</span>
            <select value={tjLevel} onChange={(e) => { setTjLevel(e.target.value); setTjPage(1); }}
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.1)', color: '#AAA', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px', padding: '8px 16px', outline: 'none', cursor: 'pointer' }}>
              <option value="all">全部等级</option>
              {[5, 4, 3, 2, 1].map((l) => { const lv = TJ_LEVEL_CONFIG[String(l)]; return <option key={l} value={String(l)}>{lv.name}</option>; })}
            </select>
          </div>
          {paged.map((rec) => <TianjijuanCard key={rec.id} record={rec} />)}
          {filtered.length > PAGE_SIZE && (
            <PaginationBar page={currentPage} total={totalPages} onPrev={() => setTjPage((p) => Math.max(1, p - 1))} onNext={() => setTjPage((p) => Math.min(totalPages, p + 1))} />
          )}
        </div>
        );
      })()}

      {/* 万业谱 */}
      {activeTable === 'wanyepu' && (() => {
        const totalPages = Math.max(1, Math.ceil(wpRecords.length / PAGE_SIZE));
        const currentPage = Math.min(wpPage, totalPages);
        const paged = wpRecords.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
        return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '1200px', margin: '0 auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#4ECDC4' }}>共 {wpRecords.length} 条</span>
          </div>
          {wpRecords.length === 0 && (
            <div style={{ textAlign: 'center', padding: '60px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
              万业谱暂无记录
            </div>
          )}
          {paged.map((rec) => <WanyepuCard key={rec.id} record={rec} />)}
          {wpRecords.length > PAGE_SIZE && (
            <PaginationBar page={currentPage} total={totalPages} onPrev={() => setWpPage((p) => Math.max(1, p - 1))} onNext={() => setWpPage((p) => Math.min(totalPages, p + 1))} />
          )}
        </div>
        );
      })()}

      {/* 定数录 */}
      {activeTable === 'dingshulu' && (() => {
        const totalPages = Math.max(1, Math.ceil(dsRecords.length / PAGE_SIZE));
        const currentPage = Math.min(dsPage, totalPages);
        const paged = dsRecords.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
        return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '1200px', margin: '0 auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#ADFF00' }}>共 {dsRecords.length} 条</span>
          </div>
          {dsRecords.length === 0 && (
            <div style={{ textAlign: 'center', padding: '60px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
              定数录暂无记录
            </div>
          )}
          {paged.map((rec) => <DingshuluCard key={rec.id} record={rec} />)}
          {dsRecords.length > PAGE_SIZE && (
            <PaginationBar page={currentPage} total={totalPages} onPrev={() => setDsPage((p) => Math.max(1, p - 1))} onNext={() => setDsPage((p) => Math.min(totalPages, p + 1))} />
          )}
        </div>
        );
      })()}

      {/* 因果簿 */}
      {activeTable === 'yinguobu' && (() => {
        const totalPages = Math.max(1, Math.ceil(ybRecords.length / PAGE_SIZE));
        const currentPage = Math.min(ybPage, totalPages);
        const paged = ybRecords.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
        return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '1200px', margin: '0 auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#AD00FF' }}>共 {ybRecords.length} 条</span>
          </div>
          {ybRecords.length === 0 && (
            <div style={{ textAlign: 'center', padding: '60px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
              因果簿暂无记录
            </div>
          )}
          {paged.map((rec) => <YinguobuCard key={rec.id} record={rec} />)}
          {ybRecords.length > PAGE_SIZE && (
            <PaginationBar page={currentPage} total={totalPages} onPrev={() => setYbPage((p) => Math.max(1, p - 1))} onNext={() => setYbPage((p) => Math.min(totalPages, p + 1))} />
          )}
        </div>
        );
      })()}

      {/* Footer */}
      <div style={{
        maxWidth: '1200px', margin: '24px auto 0',
        display: 'flex', justifyContent: 'space-between',
        padding: '16px 0', borderTop: '1px solid rgba(255,255,255,0.04)',
      }}>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px', color: '#ADFF00' }}>
          ● 已连接 Coze
        </span>
        <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px', color: '#555' }}>
          实时同步
        </span>
      </div>
      </div>{/* 1200px container */}
    </section>
  );
}
