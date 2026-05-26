/**
 * 产业链利润流分析 — 独立展示页面
 *
 * 展示每天产业模式分析的历史记录
 * 每条记录包含：产业链事件 → 前2节点 → 个股赔率排序
 */
import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

// ── 类型 ──────────────────────────────

interface ChainAnalysis {
  source_record_id: string;
  news_content: string;
  industry_chain: string;
  event_summary: string;
  top_nodes_json: string;
  top_pick_code: string;
  top_pick_name: string;
  top_pick_score: string;
  top_pick_thesis: string;
  runner_up_code: string;
  runner_up_name: string;
  runner_up_score: string;
  runner_up_thesis: string;
  top5_json: string;
  analysis_date: string;
  status: string;
}

interface TopNode {
  node_name: string;
  position: string;
  profit_retention_score: number;
  justification: string;
  what_to_look_for: string;
  key_risk: string;
}

interface ScoredStock {
  stock_code: string;
  stock_name: string;
  node_name: string;
  market_cap_yi: number;
  match_score: number;
  elasticity_score: number;
  space_score: number;
  moat_score: number;
  total_score: number;
  rationale: string;
  key_risk: string;
}

// ── 组件 ──────────────────────────────

export default function IndustryChain() {
  const [records, setRecords] = useState<ChainAnalysis[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState('');
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchResults();
  }, []);

  async function fetchResults() {
    const prevCount = records.length;
    setRefreshing(true);
    setToast('');
    try {
      const resp = await fetch('/api/industry-chain/results');
      const data = await resp.json();
      const newRecords = data.results || [];
      setRecords(newRecords);
      if (!loading && newRecords.length === prevCount) {
        setToast('无新增记录');
      } else if (!loading && newRecords.length > prevCount) {
        setToast(`新增 ${newRecords.length - prevCount} 条`);
      }
    } catch (e) {
      console.error('Failed to fetch industry chain results', e);
      setToast('加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
      setTimeout(() => setToast(''), 3000);
    }
  }

  function toggleExpand(id: string) {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        // 展开后滚动到卡片位置
        requestAnimationFrame(() => {
          const el = document.getElementById(`chain-card-${id}`);
          el?.scrollIntoView({ behavior: 'instant', block: 'nearest' });
        });
      }
      return next;
    });
  }

  function parseJSON(str: string): any {
    try { return JSON.parse(str); } catch { return null; }
  }

  // ── 渲染 ────────────────────────────

  return (
    <div ref={containerRef} style={{ color: '#A7A7A7', fontFamily: "'IBM Plex Mono', monospace" }}>
      {/* 刷新按钮 */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          onClick={fetchResults}
          disabled={refreshing}
          style={{
            background: refreshing ? 'rgba(173,255,0,0.04)' : 'transparent',
            border: `1px solid ${refreshing ? 'rgba(173,255,0,0.08)' : 'rgba(173,255,0,0.2)'}`,
            color: refreshing ? '#666' : '#ADFF00',
            padding: '8px 24px', cursor: refreshing ? 'not-allowed' : 'pointer',
            fontFamily: "'IBM Plex Mono', monospace", fontSize: 13,
            transition: 'all 0.2s',
            opacity: refreshing ? 0.6 : 1,
          }}
          onMouseEnter={(e) => { if (!refreshing) { e.currentTarget.style.background = 'rgba(173,255,0,0.08)'; e.currentTarget.style.borderColor = '#ADFF00'; }}}
          onMouseLeave={(e) => { if (!refreshing) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.2)'; }}}
        >
          {refreshing ? '刷新中...' : '刷新'}
        </button>
        <span style={{ fontSize: 12, color: '#555' }}>
          {loading ? '加载中...' : `共 ${records.length} 条分析记录`}
        </span>
        {toast && (
          <span style={{
            fontSize: 12, color: toast.includes('失败') ? '#FF5C00' : toast.includes('无新增') ? '#888' : '#ADFF00',
            animation: 'fadeUp 0.3s ease',
          }}>
            {toast}
          </span>
        )}
      </div>

      {/* 记录列表 */}
      {records.length === 0 && !loading && (
        <div style={{ textAlign: 'center', padding: 80, color: '#444' }}>
          暂无产业链分析记录
        </div>
      )}

      {records.map((r, idx) => {
        const id = `${idx}-${r.source_record_id || '0'}`;
        const isOpen = expanded.has(id);
        const nodes: TopNode[] = parseJSON(r.top_nodes_json) || [];
        const top5: ScoredStock[] = parseJSON(r.top5_json) || [];

        return (
          <div
            key={id}
            id={`chain-card-${id}`}
            style={{
              marginBottom: 20,
              border: isOpen
                ? '1px solid rgba(173,255,0,0.15)'
                : '1px solid rgba(255,255,255,0.04)',
              borderLeft: isOpen
                ? '4px solid #ADFF00'
                : `4px solid ${idx % 4 === 0 ? 'rgba(173,255,0,0.25)'
                  : idx % 4 === 1 ? 'rgba(200,141,58,0.25)'
                  : idx % 4 === 2 ? 'rgba(78,205,196,0.25)'
                  : 'rgba(173,0,255,0.25)'}`,
              background: isOpen
                ? 'rgba(255,255,255,0.025)'
                : idx % 4 === 0 ? 'rgba(173,255,0,0.015)'
                : idx % 4 === 1 ? 'rgba(200,141,58,0.015)'
                : idx % 4 === 2 ? 'rgba(78,205,196,0.015)'
                : 'rgba(173,0,255,0.015)',
              borderRadius: '0 2px 2px 0',
              transition: 'all 0.25s ease',
              cursor: 'pointer',
              boxShadow: isOpen
                ? '0 0 32px rgba(173,255,0,0.04)'
                : undefined,
            }}
            onMouseEnter={(e) => {
              if (!isOpen) {
                e.currentTarget.style.borderLeftWidth = '12px';
                e.currentTarget.style.transform = 'translateX(2px)';
                e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,0,0,0.3)';
              }
            }}
            onMouseLeave={(e) => {
              if (!isOpen) {
                e.currentTarget.style.borderLeftWidth = '4px';
                e.currentTarget.style.transform = 'translateX(0)';
                e.currentTarget.style.boxShadow = 'none';
              }
            }}
          >
            {/* 摘要栏 */}
            <div onClick={() => toggleExpand(id)} style={{
              padding: '20px 24px',
              display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
              gap: 24,
              borderBottom: isOpen ? '1px solid rgba(255,255,255,0.05)' : 'none',
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                  <span style={{
                    fontSize: 12, color: '#ADFF00',
                    background: 'rgba(173,255,0,0.08)', padding: '3px 12px',
                    fontFamily: "'Space Mono', monospace", letterSpacing: '0.06em',
                  }}>
                    {r.industry_chain || '产业链'}
                  </span>
                  <span style={{ fontSize: 11, color: '#555', fontFamily: "'Space Mono', monospace" }}>
                    {r.analysis_date?.slice(0, 16) || ''}
                  </span>
                  {r.status === 'error' && (
                    <span style={{ fontSize: 11, color: '#FF5C00', fontFamily: "'Space Mono', monospace" }}>异常</span>
                  )}
                  <span style={{ flex: 1 }} />
                  <span style={{ fontSize: 10, color: isOpen ? '#ADFF00' : '#555', fontFamily: "'Space Mono', monospace" }}>
                    {isOpen ? '收起 ▲' : '展开 ▼'}
                  </span>
                </div>
                <p style={{ fontSize: 13, color: '#999', margin: '0 0 6px 0', lineHeight: 1.7 }}>
                  {r.event_summary || r.news_content?.slice(0, 100) || '—'}
                </p>

                {/* 节点标签 */}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {nodes.map((n, i) => (
                    <span key={i} style={{
                      fontSize: 11, color: '#C88D3A',
                      border: '1px solid rgba(200,141,58,0.15)',
                      padding: '1px 8px',
                    }}>
                      {n.node_name} ({(n.profit_retention_score || 0)})
                    </span>
                  ))}
                </div>
              </div>

              {/* 前2个股 */}
              <div style={{ textAlign: 'right', flexShrink: 0, minWidth: 160 }}>
                {r.top_pick_name && r.top_pick_name !== '无高赔率标的' ? (
                  <>
                    <div style={{ fontSize: 14, color: '#ADFF00', marginBottom: 2 }}>
                      🥇 {r.top_pick_name}
                      <span style={{ fontSize: 11, color: '#888', marginLeft: 6 }}>
                        {r.top_pick_score}
                      </span>
                    </div>
                    {r.runner_up_name && r.runner_up_name !== '无高赔率标的' && (
                      <div style={{ fontSize: 13, color: '#888' }}>
                        🥈 {r.runner_up_name}
                        <span style={{ fontSize: 11, marginLeft: 6 }}>{r.runner_up_score}</span>
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ fontSize: 13, color: '#C88D3A' }}>
                    ⚠ 无高赔率标的
                  </div>
                )}
              </div>
            </div>

            {/* 展开详情 — 深色内嵌面板 */}
            {isOpen && (
              <div style={{
                background: 'rgba(0,0,0,0.25)',
                padding: '24px 28px 28px',
                borderTop: '1px solid rgba(255,255,255,0.04)',
              }}>
                {/* 前2节点分析 */}
                {nodes.length > 0 && (
                  <div style={{ marginBottom: 24 }}>
                    <div style={{
                      fontFamily: "'Space Mono', monospace", fontSize: 11, color: '#ADFF00',
                      letterSpacing: '0.12em', marginBottom: 14,
                      borderLeft: '2px solid #ADFF00', paddingLeft: 10,
                    }}>
                      产业链节点分析
                    </div>
                    {nodes.map((n, i) => (
                      <div key={i} style={{
                        padding: '16px 18px',
                        marginBottom: 8,
                        background: 'rgba(255,255,255,0.03)',
                        border: '1px solid rgba(255,255,255,0.04)',
                      }}>
                        <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8 }}>
                          <span style={{ fontSize: 15, color: '#C88D3A', fontWeight: 600 }}>
                            {n.node_name}
                          </span>
                          <span style={{
                            fontSize: 10, color: '#888', fontFamily: "'Space Mono', monospace",
                            border: '1px solid rgba(255,255,255,0.1)', padding: '1px 8px',
                            letterSpacing: '0.06em',
                          }}>
                            {n.position}
                          </span>
                          <span style={{ flex: 1 }} />
                          <span style={{ fontSize: 22, color: '#ADFF00', fontFamily: "'Geist Pixel', monospace" }}>
                            {n.profit_retention_score}
                          </span>
                          <span style={{ fontSize: 10, color: '#555', fontFamily: "'Space Mono', monospace" }}>
                            截留分
                          </span>
                        </div>
                        <p style={{ fontSize: 13, color: '#AAA', margin: '0 0 10px 0', lineHeight: 1.7 }}>
                          {n.justification}
                        </p>
                        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                          <span style={{ fontSize: 11, color: '#ADFF00' }}>
                            🔍 {n.what_to_look_for}
                          </span>
                          <span style={{ fontSize: 11, color: '#FF5C00' }}>
                            ⚠ {n.key_risk}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* 个股评分排序 */}
                {top5.length > 0 && (
                  <div style={{ marginBottom: 24 }}>
                    <div style={{
                      fontFamily: "'Space Mono', monospace", fontSize: 11, color: '#ADFF00',
                      letterSpacing: '0.12em', marginBottom: 14,
                      borderLeft: '2px solid #ADFF00', paddingLeft: 10,
                    }}>
                      候选个股赔率排序 (Top 5)
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      <table style={{
                        width: '100%', borderCollapse: 'collapse',
                        fontSize: 12,
                      }}>
                        <thead>
                          <tr style={{ color: '#777', textAlign: 'left' }}>
                            <th style={thStyle}>个股</th>
                            <th style={thStyle}>节点</th>
                            <th style={{ ...thStyle, textAlign: 'right' }}>总分</th>
                            <th style={{ ...thStyle, textAlign: 'right' }}>匹配</th>
                            <th style={{ ...thStyle, textAlign: 'right' }}>弹性</th>
                            <th style={{ ...thStyle, textAlign: 'right' }}>空间</th>
                            <th style={{ ...thStyle, textAlign: 'right' }}>卡位</th>
                            <th style={thStyle}>核心理由</th>
                          </tr>
                        </thead>
                        <tbody>
                          {top5.map((s, i) => (
                            <tr key={i} style={{
                              borderTop: '1px solid rgba(255,255,255,0.04)',
                              background: i === 0 ? 'rgba(173,255,0,0.04)' : undefined,
                            }}>
                              <td style={tdStyle}>
                                <span
                                  onClick={() => s.stock_code && navigate(`/report/v4/${s.stock_code}`)}
                                  style={{
                                    color: i < 2 ? '#ADFF00' : '#AAA',
                                    cursor: s.stock_code ? 'pointer' : 'default',
                                    textDecoration: s.stock_code ? 'underline' : 'none',
                                  }}
                                >
                                  {s.stock_name}
                                  {s.stock_code ? `(${s.stock_code})` : ''}
                                </span>
                              </td>
                              <td style={{ ...tdStyle, color: '#C88D3A', fontSize: 11 }}>
                                {s.node_name}
                              </td>
                              <td style={{ ...tdStyle, textAlign: 'right', color: '#ADFF00', fontFamily: "'Geist Pixel', monospace" }}>
                                {s.total_score}
                              </td>
                              <td style={{ ...tdStyle, textAlign: 'right' }}>{s.match_score}</td>
                              <td style={{ ...tdStyle, textAlign: 'right' }}>{s.elasticity_score}</td>
                              <td style={{ ...tdStyle, textAlign: 'right' }}>{s.space_score}</td>
                              <td style={{ ...tdStyle, textAlign: 'right' }}>{s.moat_score}</td>
                              <td style={{ ...tdStyle, color: '#888', fontSize: 11, maxWidth: 250 }}>
                                {s.rationale}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* 首选投资逻辑 */}
                {r.top_pick_thesis && r.top_pick_name !== '无高赔率标的' && (
                  <div style={{
                    padding: '16px 20px', marginBottom: 8,
                    background: 'rgba(173,255,0,0.04)', borderLeft: '2px solid rgba(173,255,0,0.3)',
                  }}>
                    <div style={{ fontSize: 12, color: '#ADFF00', marginBottom: 8, fontFamily: "'Space Mono', monospace", letterSpacing: '0.06em' }}>
                      🥇 {r.top_pick_name} — 投资逻辑
                    </div>
                    <p style={{ fontSize: 13, color: '#AAA', margin: 0, lineHeight: 1.8 }}>
                      {r.top_pick_thesis}
                    </p>
                  </div>
                )}
                {r.runner_up_thesis && r.runner_up_name !== '无高赔率标的' && (
                  <div style={{
                    padding: '16px 20px', marginBottom: 8,
                    background: 'rgba(200,141,58,0.04)', borderLeft: '2px solid rgba(200,141,58,0.3)',
                  }}>
                    <div style={{ fontSize: 12, color: '#C88D3A', marginBottom: 8, fontFamily: "'Space Mono', monospace", letterSpacing: '0.06em' }}>
                      🥈 {r.runner_up_name} — 投资逻辑
                    </div>
                    <p style={{ fontSize: 13, color: '#AAA', margin: 0, lineHeight: 1.8 }}>
                      {r.runner_up_thesis}
                    </p>
                  </div>
                )}

                {/* 收起按钮 */}
                <div style={{ textAlign: 'center', marginTop: 20 }}>
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleExpand(id); }}
                    style={{
                      fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#555',
                      background: 'transparent', border: '1px solid rgba(255,255,255,0.08)',
                      padding: '8px 28px', cursor: 'pointer', letterSpacing: '0.1em',
                    }}
                    onMouseEnter={(e2) => { e2.currentTarget.style.color = '#ADFF00'; e2.currentTarget.style.borderColor = 'rgba(173,255,0,0.3)'; }}
                    onMouseLeave={(e2) => { e2.currentTarget.style.color = '#555'; e2.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)'; }}
                  >收起 ▲</button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: '8px 10px', fontWeight: 400, fontSize: 11,
  borderBottom: '1px solid rgba(173,255,0,0.1)',
};

const tdStyle: React.CSSProperties = {
  padding: '8px 10px', verticalAlign: 'top',
};
