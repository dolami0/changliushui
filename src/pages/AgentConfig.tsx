import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import {
  loadMemory,
  saveMemory,
  addLingGuang,
  updateLingGuang,
  deleteLingGuang,
  addCase,
  updateCase,
  deleteCase,
  updateConfig,
  type LingGuang,
  type CaseItem,
  type AgentMemory,
} from '../services/agentMemory';

/* ================================================================== */
/*  身外化身 · 配置页 (Phase 1: 旧版 — 仅保留 localStorage 访问)       */
/*                                                                     */
/*  新配置系统已迁移到 .agents/agents/shenwaihuashen/                   */
/*  - config.json  → Agent 配置                                        */
/*  - memory/       → 灵光/案例/追踪 (JSON 文件, 可用 VS Code 编辑)     */
/*                                                                     */
/*  此页面仅作为旧版 localStorage 数据的备份查看和迁移。               */
/*  Phase 2 将改造为 LLM API Key 配置页。                              */
/* ================================================================== */

const inputBase: React.CSSProperties = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.08)',
  color: '#F2F4F3',
  fontFamily: "'Noto Sans SC', sans-serif",
  fontSize: '14px',
  padding: '12px 16px',
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box' as const,
  transition: 'border-color 0.2s',
};

const labelBase: React.CSSProperties = {
  fontFamily: "'Space Mono', monospace",
  fontSize: '11px',
  color: '#888',
  letterSpacing: '0.15em',
  display: 'block',
  marginBottom: '8px',
};

/* ------------------------------------------------------------------ */
/*  灵光卡片                                                            */
/* ------------------------------------------------------------------ */
function LingGuangCard({
  lg,
  onUpdate,
  onDelete,
}: {
  lg: LingGuang;
  onUpdate: (id: string, updates: Partial<LingGuang>) => void;
  onDelete: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(lg.title);
  const [content, setContent] = useState(lg.content);

  const save = () => {
    onUpdate(lg.id, { title, content });
    setEditing(false);
  };

  if (!editing) {
    return (
      <div style={{
        padding: '20px',
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.06)',
        transition: 'all 0.3s',
      }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(173,255,0,0.2)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)'; }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
          <h4 style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '16px', color: '#F2F4F3', margin: 0 }}>
            {lg.title}
          </h4>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button onClick={() => setEditing(true)} style={{ ...labelBase, cursor: 'pointer', margin: 0, color: '#ADFF00' }}>
              编辑
            </button>
            <button onClick={() => { if (confirm('确认删除？')) onDelete(lg.id); }} style={{ ...labelBase, cursor: 'pointer', margin: 0, color: '#FF5C00' }}>
              删除
            </button>
          </div>
        </div>
        <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', lineHeight: 1.8, color: '#AAA', margin: 0, whiteSpace: 'pre-wrap' }}>
          {lg.content}
        </p>
      </div>
    );
  }

  return (
    <div style={{ padding: '20px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(173,255,0,0.2)' }}>
      <label style={labelBase}>灵光标题</label>
      <input style={{ ...inputBase, marginBottom: '12px' }} value={title} onChange={(e) => setTitle(e.target.value)} />
      <label style={labelBase}>内容</label>
      <textarea style={{ ...inputBase, minHeight: '120px', resize: 'vertical' as const, marginBottom: '16px' }} value={content} onChange={(e) => setContent(e.target.value)} />
      <div style={{ display: 'flex', gap: '12px' }}>
        <button onClick={save} style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#050401', background: '#ADFF00', border: 'none', padding: '8px 20px', cursor: 'pointer' }}>
          保存
        </button>
        <button onClick={() => setEditing(false)} style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#888', background: 'transparent', border: '1px solid #333', padding: '8px 20px', cursor: 'pointer' }}>
          取消
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  案例卡片 — 完整 evals 数据展示                                       */
/* ------------------------------------------------------------------ */
function CaseCard({
  c,
  onUpdate,
  onDelete,
}: {
  c: CaseItem;
  onUpdate: (id: string, updates: Partial<CaseItem>) => void;
  onDelete: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [stockName, setStockName] = useState(c.stockName);
  const [stockCode, setStockCode] = useState(c.stockCode);
  const [sector, setSector] = useState(c.sector || '');
  const [gainMultiple, _setGainMultiple] = useState(c.gainMultiple || '');
  const [logic, setLogic] = useState(c.logic || '');
  const [keySignals, setKeySignals] = useState(c.keySignals.join(', '));
  // 扩展字段
  const [endState, setEndState] = useState(c.endState || '');
  const [troughQuarter, setTroughQuarter] = useState(c.troughQuarter || '');
  const [roicTrough, setRoicTrough] = useState(c.roicTrough != null ? String(c.roicTrough) : '');
  const [roicPeak, setRoicPeak] = useState(c.roicPeak != null ? String(c.roicPeak) : '');
  const [roicImprovement, setRoicImprovement] = useState(c.roicImprovement != null ? String(c.roicImprovement) : '');
  const [profitExpansion, setProfitExpansion] = useState(c.profitExpansion != null ? String(c.profitExpansion) : '');
  const [gmTrough, setGmTrough] = useState(c.gmTrough != null ? String(c.gmTrough) : '');
  const [gmPeak, setGmPeak] = useState(c.gmPeak != null ? String(c.gmPeak) : '');
  const [gmImprovement, setGmImprovement] = useState(c.gmImprovement != null ? String(c.gmImprovement) : '');
  const [valuationDriven, setValuationDriven] = useState(c.valuationDriven || false);
  const [totalReturn, setTotalReturn] = useState(c.totalReturn != null ? String(c.totalReturn) : '');
  const [totalReturnNote, setTotalReturnNote] = useState(c.totalReturnNote || '');
  const [catalyst, setCatalyst] = useState(c.catalyst || '');
  const [dominantFactor, setDominantFactor] = useState(c.dominantFactor || '');
  const [tagsStr, setTagsStr] = useState((c.tags || []).join(', '));
  const [returnType, setReturnType] = useState(c.returnType || '');
  const [returnTypeDesc, setReturnTypeDesc] = useState(c.returnTypeDesc || '');
  const [primaryDriver, setPrimaryDriver] = useState(c.primaryDriver || '');
  const [signalStrength, setSignalStrength] = useState(c.signalStrength || '');
  const [startPE, setStartPE] = useState(c.startPE != null ? String(c.startPE) : '');
  const [peakPE, setPeakPE] = useState(c.peakPE != null ? String(c.peakPE) : '');
  const [peExpansion, setPeExpansion] = useState(c.peExpansion != null ? String(c.peExpansion) : '');
  const [startMcap, setStartMcap] = useState(c.startMcap != null ? String(c.startMcap) : '');
  const [peakMcap, setPeakMcap] = useState(c.peakMcap != null ? String(c.peakMcap) : '');
  const [routingReason, setRoutingReason] = useState(c.routingReason || '');
  const [editStartPrice, _setEditStartPrice] = useState(c.startPrice != null ? String(c.startPrice) : '');
  const [editStartDate, _setEditStartDate] = useState(c.startDate || '');
  const [editPeakPrice, _setEditPeakPrice] = useState(c.peakPrice != null ? String(c.peakPrice) : '');
  const [editPeakDate, _setEditPeakDate] = useState(c.peakDate || '');
  const [editActualReturn, _setEditActualReturn] = useState(c.actualReturnPct != null ? String(c.actualReturnPct) : '');
  const [editMaxDD, _setEditMaxDD] = useState(c.maxDrawdownPct != null ? String(c.maxDrawdownPct) : '');

  const toNum = (s: string) => { const n = parseFloat(s); return isNaN(n) ? undefined : n; };

  const save = () => {
    onUpdate(c.id, {
      stockName, stockCode, sector, gainMultiple, logic,
      keySignals: keySignals.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
      endState: endState || undefined,
      troughQuarter: troughQuarter || undefined,
      roicTrough: toNum(roicTrough),
      roicPeak: toNum(roicPeak),
      roicImprovement: toNum(roicImprovement),
      profitExpansion: toNum(profitExpansion),
      gmTrough: toNum(gmTrough),
      gmPeak: toNum(gmPeak),
      gmImprovement: toNum(gmImprovement),
      valuationDriven,
      totalReturn: toNum(totalReturn),
      totalReturnNote: totalReturnNote || undefined,
      catalyst: catalyst || undefined,
      dominantFactor: dominantFactor || undefined,
      tags: tagsStr.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
      returnType: returnType || undefined,
      returnTypeDesc: returnTypeDesc || undefined,
      primaryDriver: primaryDriver || undefined,
      signalStrength: signalStrength || undefined,
      startPE: toNum(startPE),
      peakPE: toNum(peakPE),
      peExpansion: toNum(peExpansion),
      startMcap: toNum(startMcap),
      peakMcap: toNum(peakMcap),
      routingReason: routingReason || undefined,
      startPrice: toNum(editStartPrice), startDate: editStartDate || undefined,
      peakPrice: toNum(editPeakPrice), peakDate: editPeakDate || undefined,
      actualReturnPct: toNum(editActualReturn),
      maxDrawdownPct: toNum(editMaxDD),
    });
    setEditing(false);
  };

  if (!editing) {
    return (
      <div style={{
        padding: '28px',
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.06)',
        transition: 'all 0.3s',
      }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(255,92,0,0.2)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)'; }}
      >
        {/* 头部 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', marginBottom: '4px', flexWrap: 'wrap' }}>
              <h4 style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '22px', color: '#F2F4F3', margin: 0 }}>
                {c.stockName}
              </h4>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#888' }}>{c.stockCode}</span>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#555' }}>{c.sector}</span>
            </div>
            {c.gainMultiple && (
              <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '24px', color: '#ADFF00', marginLeft: '12px' }}>{c.gainMultiple}x</span>
            )}
            {c.entryPrice && c.exitPrice && (
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#888', marginLeft: '4px' }}>
                ¥{c.entryPrice} → ¥{c.exitPrice}
              </span>
            )}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginTop: '4px' }}>
              {c.troughQuarter && <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#666' }}>谷底 {c.troughQuarter}</span>}
              {c.signalStrength && (
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: c.signalStrength === '强' ? '#ADFF00' : '#FF5C00', border: `1px solid ${c.signalStrength === '强' ? 'rgba(173,255,0,0.25)' : 'rgba(255,92,0,0.25)'}`, padding: '1px 8px' }}>
                  {c.signalStrength}信号
                </span>
              )}
              {c.dominantFactor && (
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: c.dominantFactor.includes('业绩') ? '#ADFF00' : '#FF5C00' }}>
                  {c.dominantFactor}
                </span>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '6px', flexShrink: 0 }}>
            {c.endState && (
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '10px', color: '#ADFF00', border: '1px solid rgba(173,255,0,0.25)', padding: '2px 12px', letterSpacing: '0.06em' }}>{c.endState}</span>
            )}
            {c.returnType && (
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#C88D3A', border: '1px solid rgba(200,141,58,0.2)', padding: '2px 10px' }}>{c.returnType}</span>
            )}
            {c.primaryDriver && (
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#888' }}>驱动: {c.primaryDriver}</span>
            )}
          </div>
        </div>

        {/* 核心指标面板 */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: '14px', marginBottom: '16px',
          padding: '16px 20px', background: 'rgba(255,255,255,0.02)',
          border: '1px solid rgba(255,255,255,0.04)',
        }}>
          {c.totalReturn != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>总回报 (区间涨幅)</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '20px', color: '#ADFF00' }}>{c.totalReturn?.toFixed(1)}x</div>
              {c.totalReturnNote && <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '8px', color: '#666', marginTop: '3px', lineHeight: 1.4 }}>{c.totalReturnNote.length > 60 ? c.totalReturnNote.slice(0,60)+'…' : c.totalReturnNote}</div>}
            </div>
          )}
          {c.roicImprovement != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>ROIC 改善</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00' }}>+{c.roicImprovement?.toFixed(0)}ppt</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>{c.roicTrough?.toFixed(0)}% → {c.roicPeak?.toFixed(0)}%</div>
            </div>
          )}
          {c.peExpansion != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>PE 扩张</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#FF5C00' }}>{c.peExpansion?.toFixed(1)}x</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>{c.startPE?.toFixed(1)} → {c.peakPE?.toFixed(0)}</div>
            </div>
          )}
          {c.gmImprovement != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>毛利率改善</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00' }}>+{c.gmImprovement?.toFixed(1)}ppt</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>{c.gmTrough?.toFixed(1)}% → {c.gmPeak?.toFixed(1)}%</div>
            </div>
          )}
          {c.startMcap != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>市值变化</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#AAA' }}>{c.peakMcap?.toFixed(0)}亿</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>{c.startMcap?.toFixed(0)} → {c.peakMcap?.toFixed(0)}亿</div>
            </div>
          )}
          {c.actualReturnPct != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>实际涨幅</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: c.actualReturnPct > 500 ? '#ADFF00' : c.actualReturnPct > 100 ? '#C88D3A' : '#AAA' }}>+{c.actualReturnPct?.toFixed(0)}%</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>{c.startDate} → {c.peakDate}</div>
            </div>
          )}
          {c.maxDrawdownPct != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>区间最大回撤</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#FF5C00' }}>-{c.maxDrawdownPct?.toFixed(0)}%</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>任意峰→谷</div>
            </div>
          )}
          {c.maxDrawdownFromStartPct != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>起涨回撤</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#C88D3A' }}>-{c.maxDrawdownFromStartPct?.toFixed(0)}%</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>低于起涨价</div>
            </div>
          )}
          {c.t2xMonths != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>翻倍速度</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00' }}>{c.t2xMonths}月</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>2x | 5x {c.t5xMonths || '—'}月 | 10x {c.t10xMonths || '—'}月</div>
            </div>
          )}
          {c.asymmetryRatio != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>不对称比</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#C88D3A' }}>{c.asymmetryRatio}</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>风险收益结构</div>
            </div>
          )}
          {c.unitExpansion != null && (
            <div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', letterSpacing: '0.1em', marginBottom: '4px' }}>单元扩张</div>
              <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00' }}>{c.unitExpansion}x</div>
              <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#666' }}>单值增长</div>
            </div>
          )}
        </div>


        {/* V3 深度信息 */}
        {c.expectationGap && (
          <div style={{ marginBottom: '8px', padding: '8px 14px', background: 'rgba(173,255,0,0.03)', borderLeft: '2px solid rgba(173,255,0,0.2)' }}>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#ADFF00', letterSpacing: '0.1em' }}>预期差 </span>
            <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '12px', color: '#AAA' }}>{c.expectationGap.length > 80 ? c.expectationGap.slice(0,80)+'…' : c.expectationGap}</span>
          </div>
        )}
        {c.consensusBias && (
          <div style={{ marginBottom: '8px', padding: '8px 14px', background: 'rgba(255,92,0,0.03)', borderLeft: '2px solid rgba(255,92,0,0.2)' }}>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#FF5C00', letterSpacing: '0.1em' }}>市场偏见 </span>
            <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '12px', color: '#AAA' }}>{c.consensusBias.length > 80 ? c.consensusBias.slice(0,80)+'…' : c.consensusBias}</span>
          </div>
        )}
        {c.benchmarkPeerName && (
          <div style={{ marginBottom: '8px', display: 'flex', gap: '12px', flexWrap: 'wrap', fontSize: '10px' }}>
            <span style={{ fontFamily: "'Space Mono', monospace", color: '#888' }}>
              对照: <span style={{ color: '#C88D3A' }}>{c.benchmarkPeerName}</span> ({c.peerGainMultiple}x)
            </span>
            {c.keyDivergence && (
              <span style={{ fontFamily: "'Noto Sans SC', sans-serif", color: '#666' }}>
                {c.keyDivergence.length > 50 ? c.keyDivergence.slice(0,50)+'…' : c.keyDivergence}
              </span>
            )}
          </div>
        )}
        {c.decagenomeTags && c.decagenomeTags.length > 0 && (
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '10px' }}>
            {c.decagenomeTags.map((t) => (
              <span key={t} style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#C88D3A', border: '1px solid rgba(200,141,58,0.2)', padding: '2px 8px' }}>
                {t}
              </span>
            ))}
          </div>
        )}
        {/* 催化剂 */}
        {c.catalyst && (
          <div style={{ marginBottom: '12px', padding: '12px 16px', background: 'rgba(255,92,0,0.04)', borderLeft: '2px solid rgba(255,92,0,0.3)' }}>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#FF5C00', letterSpacing: '0.1em', marginRight: '8px' }}>催化剂</span>
            <span style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '13px', color: '#CCC', lineHeight: 1.6 }}>{c.catalyst}</span>
          </div>
        )}

        {/* 回报类型描述 */}
        {c.returnTypeDesc && (
          <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '12px', color: '#999', margin: '0 0 10px 0', lineHeight: 1.7 }}>
            {c.returnTypeDesc}
          </p>
        )}

        {/* Tags */}
        {c.tags && c.tags.length > 0 && (
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '10px' }}>
            {c.tags.map((t) => (
              <span key={t} style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#C88D3A', border: '1px solid rgba(200,141,58,0.2)', padding: '2px 8px' }}>
                {t}
              </span>
            ))}
          </div>
        )}

        {/* 信号标签 */}
        {c.keySignals.filter((s) => s).length > 0 && (
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '12px' }}>
            {c.keySignals.filter((s) => s).slice(0, 4).map((s) => (
              <span key={s} style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#ADFF00', border: '1px solid rgba(173,255,0,0.15)', padding: '2px 8px' }}>
                {s.length > 24 ? s.slice(0,24)+'…' : s}
              </span>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={() => setEditing(true)} style={{ ...labelBase, cursor: 'pointer', margin: 0, color: '#ADFF00' }}>编辑</button>
          <button onClick={() => { if (confirm('确认删除？')) onDelete(c.id); }} style={{ ...labelBase, cursor: 'pointer', margin: 0, color: '#FF5C00' }}>删除</button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,92,0,0.2)', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
        <div><label style={labelBase}>股票名称</label><input style={inputBase} value={stockName} onChange={(e) => setStockName(e.target.value)} /></div>
        <div><label style={labelBase}>股票代码</label><input style={inputBase} value={stockCode} onChange={(e) => setStockCode(e.target.value)} /></div>
        <div><label style={labelBase}>行业</label><input style={inputBase} value={sector} onChange={(e) => setSector(e.target.value)} /></div>
        <div><label style={labelBase}>终态</label><input style={inputBase} value={endState} onChange={(e) => setEndState(e.target.value)} /></div>
        <div><label style={labelBase}>回报类型</label><input style={inputBase} value={returnType} onChange={(e) => setReturnType(e.target.value)} /></div>
        <div><label style={labelBase}>主驱动</label><input style={inputBase} value={primaryDriver} onChange={(e) => setPrimaryDriver(e.target.value)} /></div>
        <div><label style={labelBase}>信号强度</label><input style={inputBase} value={signalStrength} onChange={(e) => setSignalStrength(e.target.value)} /></div>
        <div><label style={labelBase}>谷底季度</label><input style={inputBase} value={troughQuarter} onChange={(e) => setTroughQuarter(e.target.value)} /></div>
        <div><label style={labelBase}>主驱动因子</label><input style={inputBase} value={dominantFactor} onChange={(e) => setDominantFactor(e.target.value)} /></div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr 1fr', gap: '10px' }}>
        <div><label style={labelBase}>总回报(x)</label><input style={inputBase} value={totalReturn} onChange={(e) => setTotalReturn(e.target.value)} /></div>
        <div><label style={labelBase}>ROIC谷底%</label><input style={inputBase} value={roicTrough} onChange={(e) => setRoicTrough(e.target.value)} /></div>
        <div><label style={labelBase}>ROIC峰值%</label><input style={inputBase} value={roicPeak} onChange={(e) => setRoicPeak(e.target.value)} /></div>
        <div><label style={labelBase}>ROIC改善ppt</label><input style={inputBase} value={roicImprovement} onChange={(e) => setRoicImprovement(e.target.value)} /></div>
        <div><label style={labelBase}>利润扩张x</label><input style={inputBase} value={profitExpansion} onChange={(e) => setProfitExpansion(e.target.value)} /></div>
        <div><label style={labelBase}>毛利率谷底%</label><input style={inputBase} value={gmTrough} onChange={(e) => setGmTrough(e.target.value)} /></div>
        <div><label style={labelBase}>毛利率峰值%</label><input style={inputBase} value={gmPeak} onChange={(e) => setGmPeak(e.target.value)} /></div>
        <div><label style={labelBase}>毛利率改善ppt</label><input style={inputBase} value={gmImprovement} onChange={(e) => setGmImprovement(e.target.value)} /></div>
        <div><label style={labelBase}>PE扩张x</label><input style={inputBase} value={peExpansion} onChange={(e) => setPeExpansion(e.target.value)} /></div>
        <div><label style={labelBase}>起始PE</label><input style={inputBase} value={startPE} onChange={(e) => setStartPE(e.target.value)} /></div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
        <div><label style={labelBase}>峰值PE</label><input style={inputBase} value={peakPE} onChange={(e) => setPeakPE(e.target.value)} /></div>
        <div><label style={labelBase}>起始市值亿</label><input style={inputBase} value={startMcap} onChange={(e) => setStartMcap(e.target.value)} /></div>
        <div><label style={labelBase}>峰值市值亿</label><input style={inputBase} value={peakMcap} onChange={(e) => setPeakMcap(e.target.value)} /></div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <input type="checkbox" checked={valuationDriven} onChange={(e) => setValuationDriven(e.target.checked)} id={`vd-${c.id}`} />
        <label htmlFor={`vd-${c.id}`} style={{ ...labelBase, margin: 0, cursor: 'pointer' }}>估值驱动</label>
      </div>
      <div><label style={labelBase}>催化剂</label><input style={inputBase} value={catalyst} onChange={(e) => setCatalyst(e.target.value)} /></div>
      <div><label style={labelBase}>回报描述</label><input style={inputBase} value={returnTypeDesc} onChange={(e) => setReturnTypeDesc(e.target.value)} /></div>
      <div><label style={labelBase}>回报备注</label><textarea style={{ ...inputBase, minHeight: '50px', resize: 'vertical' as const }} value={totalReturnNote} onChange={(e) => setTotalReturnNote(e.target.value)} /></div>
      <div><label style={labelBase}>标签（逗号分隔）</label><input style={inputBase} value={tagsStr} onChange={(e) => setTagsStr(e.target.value)} /></div>
      <div><label style={labelBase}>核心逻辑</label><textarea style={{ ...inputBase, minHeight: '60px', resize: 'vertical' as const }} value={logic} onChange={(e) => setLogic(e.target.value)} /></div>
      <div><label style={labelBase}>关键信号（逗号分隔）</label><input style={inputBase} value={keySignals} onChange={(e) => setKeySignals(e.target.value)} /></div>
      <div><label style={labelBase}>路由原因</label><textarea style={{ ...inputBase, minHeight: '40px', resize: 'vertical' as const }} value={routingReason} onChange={(e) => setRoutingReason(e.target.value)} /></div>
      <div style={{ display: 'flex', gap: '12px', marginTop: '4px' }}>
        <button onClick={save} style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#050401', background: '#ADFF00', border: 'none', padding: '10px 28px', cursor: 'pointer' }}>保存</button>
        <button onClick={() => setEditing(false)} style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#888', background: 'transparent', border: '1px solid #333', padding: '10px 28px', cursor: 'pointer' }}>取消</button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Tab 按钮                                                            */
/* ------------------------------------------------------------------ */
function TabBtn({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        fontFamily: "'Space Mono', monospace",
        fontSize: '13px',
        letterSpacing: '0.1em',
        color: active ? '#ADFF00' : '#777',
        background: active ? 'rgba(173,255,0,0.06)' : 'transparent',
        border: active ? '1px solid rgba(173,255,0,0.2)' : '1px solid transparent',
        borderBottom: active ? 'none' : '1px solid #2A2A2A',
        padding: '12px 24px',
        cursor: 'pointer',
        transition: 'all 0.2s',
        position: 'relative' as const,
        bottom: '-1px',
      }}
    >
      {label}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  主页面                                                              */
/* ------------------------------------------------------------------ */
type Tab = 'lingguang' | 'case' | 'workflow' | 'config';

export default function AgentConfig() {
  const navigate = useNavigate();
  const mobile = useMobile();
  const [tab, setTab] = useState<Tab>('lingguang');
  const [memory, setMemory] = useState<AgentMemory>(loadMemory);

  const refresh = () => setMemory({ ...loadMemory() });

  // API config local state
  const [sysPrompt, setSysPrompt] = useState(memory.config.systemPrompt);
  const [model, setModel] = useState(memory.config.model);
  const [apiKey, setApiKey] = useState(memory.config.apiKey);
  const [apiBase, setApiBase] = useState(memory.config.apiBase);
  const [enabled, setEnabled] = useState(memory.config.enabled);

  const saveApiConfig = () => {
    updateConfig({ systemPrompt: sysPrompt, model, apiKey, apiBase, enabled });
    refresh();
  };

  useEffect(() => {
    const m = loadMemory();
    setSysPrompt(m.config.systemPrompt);
    setModel(m.config.model);
    setApiKey(m.config.apiKey);
    setApiBase(m.config.apiBase);
    setEnabled(m.config.enabled);
  }, [memory.config.enabled]);

  return (
    <div style={{ minHeight: 'calc(100vh - 58px)', background: '#050401', color: '#F2F4F3' }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, padding: '8px 48px', background: 'rgba(5,4,1,.6)', borderBottom: '1px solid #2A2A2A' }}>
        <button onClick={() => navigate('/avatar')} style={{ fontFamily: "'Space Mono', monospace", fontSize: 12, color: '#ADFF00', background: 'transparent', border: '1px solid rgba(173,255,0,.2)', padding: '6px 16px', cursor: 'pointer', letterSpacing: '0.05em' }}>← 返回推演</button>
      </div>
      {/* Header */}
      <div style={{ maxWidth: '960px', margin: '0 auto', padding: '40px 48px 0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <span style={{ width: '6px', height: '6px', background: '#ADFF00', boxShadow: '0 0 8px rgba(173,255,0,0.5)', animation: 'pulse 2s ease-in-out infinite', display: 'inline-block' }} />
          <h1 style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: '28px', fontWeight: 400, color: '#ADFF00', margin: 0, letterSpacing: '0.06em', textShadow: '0 0 16px rgba(173,255,0,0.3)' }}>身外化身</h1>
        </div>
        <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '15px', color: '#777', margin: '0 0 32px 0' }}>配置你的AI投资身外化身 — 灵光、案例、工作流与API</p>
      </div>

      {/* Tabs — 固定位置 */}
      <div style={{ maxWidth: '960px', margin: '0 auto', padding: mobile ? '0 20px' : '0 48px', borderBottom: '1px solid #2A2A2A', display: 'flex', gap: '4px', overflowX: 'auto' }}>
        <TabBtn label="灵光" active={tab === 'lingguang'} onClick={() => setTab('lingguang')} />
        <TabBtn label="案例" active={tab === 'case'} onClick={() => setTab('case')} />
        <TabBtn label="工作流" active={tab === 'workflow'} onClick={() => setTab('workflow')} />
        <TabBtn label="API配置" active={tab === 'config'} onClick={() => setTab('config')} />
      </div>

      {/* Content */}
      <div style={{ maxWidth: '960px', margin: '0 auto', padding: mobile ? '24px 20px 48px' : '32px 48px 64px' }}>

        {/* ====== 灵光 Tab ====== */}
        {tab === 'lingguang' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#AAA', letterSpacing: '0.15em', margin: 0 }}>
                投资灵光 ({memory.lingguangs.length})
              </h3>
              <button
                onClick={() => {
                  addLingGuang({ title: '新灵光', content: '在此写入你的投资理念精华...' });
                  refresh();
                }}
                style={{
                  fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#ADFF00',
                  background: 'transparent', border: '1px solid rgba(173,255,0,0.25)',
                  padding: '8px 16px', cursor: 'pointer', letterSpacing: '0.1em',
                }}
              >
                + 新增灵光
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {memory.lingguangs.map((lg) => (
                <LingGuangCard
                  key={lg.id}
                  lg={lg}
                  onUpdate={(id, u) => { updateLingGuang(id, u); refresh(); }}
                  onDelete={(id) => { deleteLingGuang(id); refresh(); }}
                />
              ))}
            </div>
          </div>
        )}

        {/* ====== 案例 Tab ====== */}
        {tab === 'case' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#AAA', letterSpacing: '0.15em', margin: 0 }}>
                十倍股案例库 ({memory.cases.length})
              </h3>
              <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => {
                  addCase({ stockName: '新案例', stockCode: '', entryPrice: '', exitPrice: '', gainMultiple: '', sector: '', logic: '', keySignals: [], endState: '', troughQuarter: '', roicTrough: undefined, roicPeak: undefined, roicImprovement: undefined, profitExpansion: undefined, gmTrough: undefined, gmPeak: undefined, gmImprovement: undefined, valuationDriven: false } as any);
                  refresh();
                }}
                style={{
                  fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#ADFF00',
                  background: 'transparent', border: '1px solid rgba(173,255,0,0.25)',
                  padding: '8px 16px', cursor: 'pointer', letterSpacing: '0.1em',
                }}
              >
                + 新增案例
              </button>
              <button
                onClick={async () => {
                  try {
                    const res = await fetch('/case-import.json');
                    if (!res.ok) throw new Error('HTTP ' + res.status);
                    const data = await res.json();
                    const now = new Date().toISOString();
                    const cases = data.map((c: any) => ({
                      id: 'case-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6),
                      stockName: c.stockName || c.stockCode, stockCode: c.stockCode,
                      entryPrice: '', exitPrice: '', gainMultiple: '',
                      sector: c.sector || '', logic: c.logic || '',
                      keySignals: c.keySignals || [],
                      createdAt: now,
                      endState: c.endState,
                      totalReturn: c.totalReturn, totalReturnNote: c.totalReturnNote,
                      catalyst: c.catalyst, dominantFactor: c.dominantFactor,
                      tags: c.tags, returnType: c.returnType, returnTypeDesc: c.returnTypeDesc,
                      primaryDriver: c.primaryDriver, signalStrength: c.signalStrength,
                      troughQuarter: c.troughQuarter,
                      roicTrough: c.roicTrough, roicPeak: c.roicPeak, roicImprovement: c.roicImprovement,
                      profitExpansion: c.profitExpansion,
                      gmTrough: c.gmTrough, gmPeak: c.gmPeak, gmImprovement: c.gmImprovement,
                      valuationDriven: c.valuationDriven,
                      startPE: c.startPE, peakPE: c.peakPE, peExpansion: c.peExpansion,
                      startMcap: c.startMcap, peakMcap: c.peakMcap,
                      routingReason: c.routingReason,
                      startPrice: c.startPrice, startDate: c.startDate,
                      peakPrice: c.peakPrice, peakDate: c.peakDate,
                      actualReturnPct: c.actualReturnPct,
                      maxDrawdownPct: c.maxDrawdownPct,
                        maxDrawdownFromStartPct: c.maxDrawdownFromStartPct,
                        t2xMonths: c.t2xMonths, t5xMonths: c.t5xMonths, t10xMonths: c.t10xMonths,
                        majorDrawdowns: c.majorDrawdowns,
                        asymmetryRatio: c.asymmetryRatio,
                        marketShareTrough: c.marketShareTrough, marketSharePeak: c.marketSharePeak,
                        unitExpansion: c.unitExpansion,
                        decagenomeTags: c.decagenomeTags,
                        benchmarkPeerName: c.benchmarkPeerName, peerGainMultiple: c.peerGainMultiple,
                        keyDivergence: c.keyDivergence, failureMode: c.failureMode,
                        expectationGap: c.expectationGap, consensusBias: c.consensusBias,
                        shareholderEvolution: c.shareholderEvolution,
                        macroRegime: c.macroRegime, styleFactor: c.styleFactor,
                    }));
                    const memory = loadMemory();
                    memory.cases = cases;
                    saveMemory(memory);
                    window.location.reload();
                  } catch (e) { alert('读取失败: ' + String(e)); }
                }}
                style={{
                  fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#FF5C00',
                  background: 'transparent', border: '1px solid rgba(255,92,0,0.25)',
                  padding: '8px 16px', cursor: 'pointer', letterSpacing: '0.1em',
                }}
              >
                重新读取
              </button>
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: mobile ? '1fr' : '1fr 1fr', gap: '12px' }}>
              {memory.cases.map((c) => (
                <CaseCard
                  key={c.id}
                  c={c}
                  onUpdate={(id, u) => { updateCase(id, u); refresh(); }}
                  onDelete={(id) => { deleteCase(id); refresh(); }}
                />
              ))}
            </div>
          </div>
        )}

        {/* ====== 工作流 Tab ====== */}
        {tab === 'workflow' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#AAA', letterSpacing: '0.15em', margin: 0 }}>
                决策工作流 ({memory.workflowSteps.length}步)
              </h3>
              <button
                onClick={() => {
                  const memory = loadMemory();
                  const nextOrder = memory.workflowSteps.length + 1;
                  memory.workflowSteps.push({
                    id: `ws-${Date.now()}`,
                    order: nextOrder,
                    name: `新步骤`,
                    description: '描述此步骤的决策要点...',
                  });
                  saveMemory(memory);
                  refresh();
                }}
                style={{
                  fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#ADFF00',
                  background: 'transparent', border: '1px solid rgba(173,255,0,0.25)',
                  padding: '8px 16px', cursor: 'pointer', letterSpacing: '0.1em',
                }}
              >
                + 新增步骤
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {memory.workflowSteps.sort((a, b) => a.order - b.order).map((step, idx) => (
                <WorkflowStepEditor key={step.id} step={step} index={idx} onRefresh={refresh} />
              ))}
            </div>
          </div>
        )}

        {/* ====== API配置 Tab ====== */}
        {tab === 'config' && (
          <div>
            <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#AAA', letterSpacing: '0.15em', margin: '0 0 20px 0' }}>
              AI 引擎配置
            </h3>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
              <div>
                <label style={labelBase}>模型</label>
                <input style={inputBase} value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o / deepseek-chat" />
              </div>
              <div>
                <label style={labelBase}>API Base URL</label>
                <input style={inputBase} value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="https://api.openai.com/v1" />
              </div>
              <div>
                <label style={labelBase}>API Key</label>
                <input style={inputBase} value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" placeholder="sk-..." />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <button
                  onClick={() => setEnabled(!enabled)}
                  style={{
                    width: '40px', height: '20px', borderRadius: '10px',
                    border: 'none', cursor: 'pointer',
                    background: enabled ? '#ADFF00' : '#333',
                    position: 'relative' as const,
                    transition: 'background 0.2s',
                  }}
                >
                  <span style={{
                    position: 'absolute', top: '2px',
                    left: enabled ? '22px' : '2px',
                    width: '16px', height: '16px', borderRadius: '50%',
                    background: '#fff', transition: 'left 0.2s',
                  }} />
                </button>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: enabled ? '#ADFF00' : '#666' }}>
                  {enabled ? '已启用' : '已停用'}
                </span>
              </div>
            </div>

            <label style={labelBase}>系统提示词（System Prompt）</label>
            <textarea
              style={{ ...inputBase, minHeight: '300px', resize: 'vertical' as const, fontSize: '13px', lineHeight: 1.8, scrollbarWidth: 'none' as const }}
              value={sysPrompt}
              onChange={(e) => setSysPrompt(e.target.value)}
            />

            <div style={{ marginTop: '20px' }}>
              <button onClick={saveApiConfig} style={{
                fontFamily: "'Space Mono', monospace", fontSize: '13px', color: '#050401',
                background: '#ADFF00', border: 'none', padding: '12px 32px',
                cursor: 'pointer', letterSpacing: '0.1em',
              }}>
                保存配置
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  工作流步骤编辑器                                                    */
/* ------------------------------------------------------------------ */
function WorkflowStepEditor({
  step,
  index,
  onRefresh,
}: {
  step: { id: string; order: number; name: string; description: string };
  index: number;
  onRefresh: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(step.name);
  const [desc, setDesc] = useState(step.description);

  const save = () => {
    const memory = loadMemory();
    const idx = memory.workflowSteps.findIndex((s) => s.id === step.id);
    if (idx !== -1) {
      memory.workflowSteps[idx] = { ...memory.workflowSteps[idx], name, description: desc };
      saveMemory(memory);
    }
    setEditing(false);
    onRefresh();
  };

  const moveUp = () => {
    const memory = loadMemory();
    const steps = memory.workflowSteps.sort((a, b) => a.order - b.order);
    const idx = steps.findIndex((s) => s.id === step.id);
    if (idx > 0) {
      const tmp = steps[idx].order;
      steps[idx].order = steps[idx - 1].order;
      steps[idx - 1].order = tmp;
      saveMemory(memory);
      onRefresh();
    }
  };

  const moveDown = () => {
    const memory = loadMemory();
    const steps = memory.workflowSteps.sort((a, b) => a.order - b.order);
    const idx = steps.findIndex((s) => s.id === step.id);
    if (idx < steps.length - 1) {
      const tmp = steps[idx].order;
      steps[idx].order = steps[idx + 1].order;
      steps[idx + 1].order = tmp;
      saveMemory(memory);
      onRefresh();
    }
  };

  const remove = () => {
    const memory = loadMemory();
    memory.workflowSteps = memory.workflowSteps.filter((s) => s.id !== step.id);
    // Re-order
    memory.workflowSteps.sort((a, b) => a.order - b.order).forEach((s, i) => { s.order = i + 1; });
    saveMemory(memory);
    onRefresh();
  };

  if (editing) {
    return (
      <div style={{ padding: '16px 20px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(173,255,0,0.2)' }}>
        <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
          <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00', minWidth: '28px' }}>{String(step.order).padStart(2, '0')}</span>
          <input style={{ ...inputBase, flex: 1 }} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <textarea style={{ ...inputBase, minHeight: '60px', resize: 'vertical' as const, marginBottom: '12px' }} value={desc} onChange={(e) => setDesc(e.target.value)} />
        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={save} style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#050401', background: '#ADFF00', border: 'none', padding: '6px 16px', cursor: 'pointer' }}>保存</button>
          <button onClick={() => setEditing(false)} style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#888', background: 'transparent', border: '1px solid #333', padding: '6px 16px', cursor: 'pointer' }}>取消</button>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      padding: '16px 20px', background: 'rgba(255,255,255,0.03)',
      border: '1px solid rgba(255,255,255,0.06)',
      display: 'flex', alignItems: 'flex-start', gap: '16px',
      transition: 'all 0.3s',
    }}
      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(173,255,0,0.2)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)'; }}
    >
      <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#ADFF00', minWidth: '28px' }}>{String(step.order).padStart(2, '0')}</span>
      <div style={{ flex: 1 }}>
        <h4 style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '15px', color: '#F2F4F3', margin: '0 0 4px 0' }}>{step.name}</h4>
        <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '13px', color: '#888', margin: 0 }}>{step.description}</p>
      </div>
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
        {index > 0 && <button onClick={moveUp} style={{ ...labelBase, cursor: 'pointer', margin: 0 }}>↑</button>}
        <button onClick={moveDown} style={{ ...labelBase, cursor: 'pointer', margin: 0 }}>↓</button>
        <button onClick={() => setEditing(true)} style={{ ...labelBase, cursor: 'pointer', margin: 0, color: '#ADFF00' }}>编辑</button>
        <button onClick={remove} style={{ ...labelBase, cursor: 'pointer', margin: 0, color: '#FF5C00' }}>删除</button>
      </div>
    </div>
  );
}
