import { useState, useEffect, useRef } from 'react';
import { useMobile } from '../hooks/useMobile';
import { fetchTianjijuanToday, extractNewsTitle, stripHtml, type TianjijuanRecord } from '../services/cozeApi';
import { renderMarkdown } from '../lib/utils';
import IndustryChain from './IndustryChain';
import gsap from 'gsap';

/* ------------------------------------------------------------------ */
/*  响应等级配置                                                        */
/* ------------------------------------------------------------------ */
const LEVEL_CONFIG: Record<string, { name: string; color: string; borderColor: string; bgAlpha: string }> = {
  '5': { name: '道变', color: '#AD00FF', borderColor: 'rgba(173,0,255,0.6)', bgAlpha: '0.08' },
  '4': { name: '天兆', color: '#FF5C00', borderColor: 'rgba(255,92,0,0.6)', bgAlpha: '0.06' },
  '3': { name: '雷动', color: '#FF8C00', borderColor: 'rgba(255,140,0,0.5)', bgAlpha: '0.04' },
  '2': { name: '风起', color: '#4ECDC4', borderColor: 'rgba(78,205,196,0.4)', bgAlpha: '0.02' },
  '1': { name: '微澜', color: '#666', borderColor: 'rgba(102,102,102,0.3)', bgAlpha: '0' },
  '0': { name: '尘外', color: '#444', borderColor: 'rgba(68,68,68,0.2)', bgAlpha: '0' },
};
const HIGH_RESPONSE_LEVELS = ['4', '5'];
const PAGE_SIZE = 50;

/* ------------------------------------------------------------------ */
/*  Tab 组件                                                            */
/* ------------------------------------------------------------------ */
const TABS = [
  { key: 'tianyan', label: '天眼' },
  { key: 'wangqi', label: '望气' },
  { key: 'xunlong', label: '寻龙' },
  { key: 'miaoyin', label: '妙音' },
] as const;
type TabKey = typeof TABS[number]['key'];

/* ------------------------------------------------------------------ */
/*  TianyanFeed — 天眼瀑布流                                            */
/* ------------------------------------------------------------------ */
function TianyanFeed() {
  const containerRef = useRef<HTMLDivElement>(null);
  const prevIdsRef = useRef<Set<string>>(new Set());
  const [records, setRecords] = useState<TianjijuanRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [newIds, setNewIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const fetchData = () => {
    setRefreshing(true);
    fetchTianjijuanToday()
      .then((data) => {
        const ids = new Set(data.map((r) => r.id));
        // 首次加载不标新
        if (prevIdsRef.current.size > 0) {
          const fresh = new Set<string>();
          data.forEach((r) => {
            if (!prevIdsRef.current.has(r.id) && (r.level === '4' || r.level === '5')) {
              fresh.add(r.id);
            }
          });
          setNewIds(fresh);
          if (fresh.size > 0) setTimeout(() => setNewIds(new Set()), 120_000);
        }
        prevIdsRef.current = ids;
        setRecords(data);
        setLoading(false);
      })
      .catch((err) => { setError(String(err)); setLoading(false); })
      .finally(() => setRefreshing(false));
  };

  useEffect(() => { fetchData(); }, []);

  // 10分钟轮询
  useEffect(() => {
    const id = setInterval(fetchData, 600_000);
    return () => clearInterval(id);
  }, []);

  // 高响应等级 (4-5) 置顶，仅当日；其余全部按时间倒序
  const todayStr = new Date().toISOString().slice(0, 10);
  const highResponse = records.filter(
    (r) => HIGH_RESPONSE_LEVELS.includes(r.level) && (r.bstudio_create_time || '').startsWith(todayStr)
  );
  const normalItems = records.filter((r) => !highResponse.includes(r));
  const totalPages = Math.max(1, Math.ceil(normalItems.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedNormal = normalItems.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const levelCounts: Record<string, number> = {};
  records.forEach((r) => { levelCounts[r.level] = (levelCounts[r.level] || 0) + 1; });

  useEffect(() => {
    if (!containerRef.current || records.length === 0) return;
    const items = containerRef.current.querySelectorAll('.tianyan-item');
    gsap.fromTo(items,
      { opacity: 0, y: 20 },
      { opacity: 1, y: 0, duration: 0.3, stagger: 0.04, ease: 'power2.out' }
    );
  }, [records, page]);

  return (
    <div ref={containerRef}>
      {/* 头栏 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: '24px', flexWrap: 'wrap', gap: '12px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{
            fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00',
            letterSpacing: '0.06em', textShadow: '0 0 12px rgba(173,255,0,0.3)',
          }}>天眼</span>
          <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
            近 {records.length} 条 · 今日高响应 {highResponse.length} 条
          </span>
          <button
            onClick={fetchData}
            disabled={refreshing}
            style={{
              fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px',
              color: refreshing ? '#888' : '#ADFF00',
              background: 'transparent', border: `1px solid ${refreshing ? 'rgba(255,255,255,0.08)' : 'rgba(173,255,0,0.2)'}`,
              padding: '3px 10px', cursor: refreshing ? 'not-allowed' : 'pointer',
              opacity: refreshing ? 0.5 : 1,
            }}
            onMouseEnter={(e) => { if (!refreshing) { e.currentTarget.style.background = 'rgba(173,255,0,0.08)'; }}}
            onMouseLeave={(e) => { if (!refreshing) { e.currentTarget.style.background = 'transparent'; }}}
          >{refreshing ? '⟳' : '↻'}</button>
        </div>
        <div style={{ display: 'flex', gap: '8px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px' }}>
          {[5, 4, 3, 2, 1, 0].map((l) => {
            const cfg = LEVEL_CONFIG[String(l)];
            const count = levelCounts[String(l)] || 0;
            return (
              <span key={l} style={{ color: cfg.color, opacity: count > 0 ? 1 : 0.3 }}>
                {cfg.name} {count}
              </span>
            );
          })}
        </div>
      </div>

      {/* 加载 / 错误 */}
      {loading && (
        <div style={{ textAlign: 'center', padding: '60px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
          天眼开启中...
        </div>
      )}
      {error && (
        <div style={{ textAlign: 'center', padding: '60px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#FF5C00' }}>
          {error}
        </div>
      )}

      {!loading && records.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
          今日暂无天机资讯
        </div>
      )}

      {/* ====== 高响应等级置顶区 ====== */}
      {highResponse.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          <div style={{
            fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#FF5C00',
            letterSpacing: '0.12em', marginBottom: '10px',
            borderBottom: '1px solid rgba(255,92,0,0.2)', paddingBottom: '8px',
          }}>
            ▍高响应信号 ({highResponse.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {highResponse.map((rec) => <NewsCard key={rec.id} rec={rec} isExpanded={expandedId === rec.id} isNew={newIds.has(rec.id)} onToggle={() => setExpandedId(expandedId === rec.id ? null : rec.id)} />)}
          </div>
        </div>
      )}

      {/* ====== 全部资讯瀑布流 ====== */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {highResponse.length > 0 && (
          <div style={{
            fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555',
            letterSpacing: '0.12em', marginBottom: '4px',
            borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '8px',
          }}>
            ▍全部资讯 ({normalItems.length})
          </div>
        )}
        {pagedNormal.map((rec) => <NewsCard key={rec.id} rec={rec} isExpanded={expandedId === rec.id} isNew={newIds.has(rec.id)} onToggle={() => setExpandedId(expandedId === rec.id ? null : rec.id)} />)}
        {normalItems.length === 0 && highResponse.length > 0 && (
          <div style={{ textAlign: 'center', padding: '20px', fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '12px', color: '#555' }}>
            其余资讯中暂无更多内容
          </div>
        )}
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: '16px', marginTop: '24px', paddingTop: '20px',
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
          >← 上一页</button>
          <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#888', letterSpacing: '0.1em' }}>
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
          >下一页 →</button>
        </div>
      )}
    </div>
  );
}

/* 单条资讯卡片 — 点击展开/收起 */
function NewsCard({
  rec,
  isExpanded,
  onToggle,
  isNew,
}: {
  rec: TianjijuanRecord;
  isExpanded: boolean;
  onToggle: () => void;
  isNew?: boolean;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const cfg = LEVEL_CONFIG[rec.level] || LEVEL_CONFIG['1'];
  const isHigh = HIGH_RESPONSE_LEVELS.includes(rec.level);
  const fullText = stripHtml(rec.news_content);

  const handleToggle = () => {
    if (!isExpanded) {
      onToggle();
      requestAnimationFrame(() => {
        cardRef.current?.scrollIntoView({ behavior: 'instant', block: 'nearest' });
      });
    } else {
      onToggle();
    }
  };

  return (
    <div
      ref={cardRef}
      className="tianyan-item"
      style={{
        borderLeft: `3px solid ${cfg.borderColor}`,
        ...(isNew ? {
          animation: 'newSignal 2s ease-in-out infinite',
          boxShadow: `0 0 16px ${cfg.color}40, inset 0 0 8px ${cfg.color}15`,
          borderLeftColor: cfg.color,
        } : {}),
      }}
    >
      {/* 折叠行 — 始终显示截断标题 */}
      <div
        onClick={handleToggle}
        style={{
          padding: '18px 20px',
          background: isHigh
            ? `linear-gradient(90deg, rgba(255,255,255,${cfg.bgAlpha}) 0%, rgba(255,255,255,0.01) 100%)`
            : 'rgba(255,255,255,0.01)',
          display: 'flex', gap: '16px', alignItems: 'flex-start',
          cursor: 'pointer',
        }}
        onMouseEnter={(e) => {
          if (!isExpanded) e.currentTarget.style.background = isHigh
            ? `linear-gradient(90deg, rgba(255,255,255,${cfg.bgAlpha}) 0%, rgba(255,255,255,0.04) 100%)`
            : 'rgba(255,255,255,0.04)';
        }}
        onMouseLeave={(e) => {
          if (!isExpanded) e.currentTarget.style.background = isHigh
            ? `linear-gradient(90deg, rgba(255,255,255,${cfg.bgAlpha}) 0%, rgba(255,255,255,0.01) 100%)`
            : 'rgba(255,255,255,0.01)';
        }}
      >
        {/* 等级徽标 */}
        <span style={{
          flexShrink: 0, fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: cfg.color,
          border: `1px solid ${cfg.borderColor}`, padding: '2px 10px', letterSpacing: '0.1em',
          minWidth: '36px', textAlign: 'center',
        }}>{cfg.name}</span>
        {/* 内容 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{
            fontFamily: "'Noto Sans SC', sans-serif",
            fontSize: isHigh ? '14px' : '13px', color: isHigh ? '#DDD' : '#AAA',
            margin: '0 0 6px 0', lineHeight: 1.7,
            fontWeight: isHigh ? 600 : 400,
          }}>
            {extractNewsTitle(rec.news_content, isHigh ? 60 : 40)}
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <span style={{ fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#555' }}>
              {rec.bstudio_create_time?.replace(' +0800 CST', '') || ''}
            </span>
            <span style={{
              fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#666',
              border: '1px solid rgba(255,255,255,0.08)', padding: '1px 8px',
            }}>{rec.mode}</span>
            {rec.is_analyzed === 'true' && (
              <span style={{
                fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#ADFF00',
                border: '1px solid rgba(173,255,0,0.25)', background: 'rgba(173,255,0,0.06)',
                padding: '1px 8px', letterSpacing: '0.08em',
              }}>已推演</span>
            )}
            {rec.stock_name && (
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '12px', color: '#888' }}>
                {rec.stock_name}{rec.stock_code ? ` ${rec.stock_code}` : ''}
              </span>
            )}
            <span style={{ flex: 1 }} />
            <span style={{
              fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: isExpanded ? '#ADFF00' : '#555',
            }}>{isExpanded ? '▲' : '▼'}</span>
          </div>
        </div>
      </div>
      {/* 展开区 — 完整资讯 + 深度研究 */}
      {isExpanded && (
        <div style={{
          padding: '0 20px 20px', marginLeft: '52px',
          borderTop: '1px solid rgba(255,255,255,0.06)',
        }}>
          {/* 完整资讯 */}
          <div style={{ padding: '16px 0 0' }}>
            <div style={{
              fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#555',
              letterSpacing: '0.1em', marginBottom: '10px',
            }}>▍完整资讯</div>
            <div style={{
              fontFamily: "'Noto Sans SC', sans-serif",
              fontSize: '13px', lineHeight: 1.9, color: '#BBB',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              maxHeight: '400px', overflowY: 'auto',
              padding: '14px 16px',
              background: 'rgba(255,255,255,0.015)',
              border: '1px solid rgba(255,255,255,0.05)',
            }}>
              {fullText}
            </div>
          </div>
          {/* 深度研究 (Markdown) */}
          {rec.knowledge && (
            <div style={{
              marginTop: '16px',
              padding: '16px',
              background: 'rgba(173,255,0,0.02)',
              borderLeft: '2px solid rgba(173,255,0,0.12)',
            }}>
              <div style={{
                fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px', color: '#ADFF00',
                letterSpacing: '0.1em', marginBottom: '12px',
              }}>▍深度研究</div>
              <div
                style={{
                  fontFamily: "'Noto Sans SC', sans-serif",
                  fontSize: '13px', lineHeight: 1.8, color: '#AAA',
                  maxHeight: '500px', overflowY: 'auto',
                }}
                dangerouslySetInnerHTML={{ __html: renderMarkdown(rec.knowledge) }}
              />
            </div>
          )}
          {/* 收起按钮 */}
          <div style={{ textAlign: 'center', marginTop: '18px' }}>
            <button
              onClick={(e) => { e.stopPropagation(); onToggle(); }}
              style={{
                fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#ADFF00',
                background: 'rgba(173,255,0,0.06)', border: '1px solid rgba(173,255,0,0.2)',
                padding: '8px 28px', cursor: 'pointer', letterSpacing: '0.1em',
              }}
              onMouseEnter={(e2) => { e2.currentTarget.style.background = 'rgba(173,255,0,0.12)'; e2.currentTarget.style.borderColor = '#ADFF00'; }}
              onMouseLeave={(e2) => { e2.currentTarget.style.background = 'rgba(173,255,0,0.06)'; e2.currentTarget.style.borderColor = 'rgba(173,255,0,0.2)'; }}
            >收起 ▲</button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PlaceholderTab                                                      */
/* ------------------------------------------------------------------ */
function PlaceholderTab({ title, text }: { title: string; text: string }) {
  return (
    <div style={{
      textAlign: 'center', padding: '100px 40px',
    }}>
      <div style={{
        width: '60px', height: '60px', borderRadius: '50%',
        border: '2px solid rgba(173,255,0,0.15)',
        margin: '0 auto 24px',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: '#ADFF00', opacity: 0.3 }}>炼</span>
      </div>
      <h3 style={{
        fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace",
        fontSize: '22px', color: '#ADFF00', margin: '0 0 12px 0',
        letterSpacing: '0.06em', opacity: 0.6,
      }}>{title}</h3>
      <p style={{
        fontFamily: "'Noto Sans SC', sans-serif",
        fontSize: '14px', color: '#666', margin: 0, lineHeight: 1.8,
      }}>{text}</p>
    </div>
  );
}

/* ================================================================== */
/*  TianjiPeak                                                         */
/* ================================================================== */
export default function TianjiPeak() {
  const mobile = useMobile();
  const [activeTab, setActiveTab] = useState<TabKey>('tianyan');

  return (
    <div style={{ minHeight: 'calc(100vh - 58px)', background: '#050401', color: '#F2F4F3' }}>
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: mobile ? '24px 20px 48px' : '32px 48px 80px' }}>
        {/* 页面标题 */}
        <div style={{ marginBottom: '32px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <span style={{ width: '8px', height: '8px', background: '#ADFF00', boxShadow: '0 0 8px rgba(173,255,0,0.5)', animation: 'pulse 2s ease-in-out infinite' }} />
            <h1 style={{
              fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace",
              fontSize: '28px', fontWeight: 400, color: '#ADFF00', margin: 0,
              letterSpacing: '0.06em', textShadow: '0 0 16px rgba(173,255,0,0.3)',
            }}>天机峰</h1>
          </div>
          <p style={{ fontFamily: "'Noto Sans SC', 'IBM Plex Mono', sans-serif", fontSize: '15px', color: '#777', margin: 0 }}>
            天眼观六路 · 寻龙定乾坤 · 妙音入三界
          </p>
        </div>

        {/* Tabs */}
        <div style={{
          display: 'flex', gap: '0', borderBottom: '1px solid rgba(255,255,255,0.06)',
          marginBottom: '32px',
        }}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                fontFamily: "'Space Mono', 'Noto Sans SC', monospace", fontSize: '13px',
                color: activeTab === tab.key ? '#ADFF00' : '#555',
                background: 'transparent', border: 'none',
                borderBottom: activeTab === tab.key ? '2px solid #ADFF00' : '2px solid transparent',
                padding: '12px 24px', cursor: 'pointer', letterSpacing: '0.1em',
                transition: 'all 0.2s',
              }}
              onMouseEnter={(e) => { if (activeTab !== tab.key) e.currentTarget.style.color = '#888'; }}
              onMouseLeave={(e) => { if (activeTab !== tab.key) e.currentTarget.style.color = '#555'; }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {activeTab === 'tianyan' && <TianyanFeed />}
        {activeTab === 'wangqi' && <IndustryChain />}
        {activeTab === 'xunlong' && (
          <PlaceholderTab
            title="寻龙尺尚在炼制中"
            text="涨停股分析功能即将开启，届时可在此猎寻龙脉。"
          />
        )}
        {activeTab === 'miaoyin' && (
          <PlaceholderTab
            title="妙音传讯阵尚未布成"
            text="个性化资讯分析功能即将开启，届时可在此聆听市场妙音。"
          />
        )}
      </div>
    </div>
  );
}
