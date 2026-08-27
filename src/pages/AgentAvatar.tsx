import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { fetchDingshulu, fetchReportFromCoze, type DingshuluRecord } from '../services/cozeApi';
import { loadMemory, callAgentAI } from '../services/agentMemory';
import { fetchLingGuangList, saveLingGuang, deleteLingGuang, fetchCaseList, fetchTrackingList, type LingGuangItem, type CaseSummary, type TrackingItem } from '../services/memoryApi';
import { renderMarkdown } from '../lib/utils';
import gsap from 'gsap';

/* ================================================================== */
/*  身外化身 · 器灵直连 — 模块化上下文 + 记忆中枢                        */
/* ================================================================== */

const HIDE_SCR = '.av-scroll::-webkit-scrollbar{display:none}.av-scroll{scrollbar-width:none}';

const C = { green: '#ADFF00', orange: '#FF5C00', gold: '#C88D3A', white: '#F2F4F3', dim: '#888', mute: '#555', line: '#2A2A2A', bg: '#050401' };
const F = { pixel: "'Geist Pixel','Noto Sans SC',monospace", mono: "'Space Mono','Noto Sans SC',monospace", body: "'Noto Sans SC','IBM Plex Mono',sans-serif" };
const G = (obj: unknown, ...path: string[]): unknown => {
  let cur = obj;
  for (const k of path) { if (cur == null || typeof cur !== 'object') return undefined; cur = (cur as Record<string,unknown>)[k]; }
  return cur;
};
const N = (v: unknown, d = '—'): string => {
  if (v == null) return d;
  const f = parseFloat(String(v));
  return isNaN(f) ? String(v) : (f === Math.round(f) ? String(Math.round(f)) : f.toFixed(1));
};
const Pct = (v: unknown): string => { const s = N(v); return s === '—' ? s : s + '%'; };

// ── V6 叙事诊断·术语自解释映射 ──
const SHAPE_EXPLAIN: Record<string,string> = {
  'narrow_concentrated': '窄集中: 方向确定、幅度可参照历史——置信度应较高',
  'narrow_base_dominant': '窄集中: 基底情景占主导——尾部风险可控',
  'wide_unimodal': '宽单峰: 方向确定但幅度不确定——需留安全边际',
  'wide_bimodal': '宽双峰: 结果高度二元分化——注意尾部风险',
  'wide_bimodal_date_anchored': '宽双峰: 关键时间节点决定方向——关注催化剂日期',
};
const ANCHOR_FOCUS: Record<string,string> = {
  'earnings': '市场在定价盈利能力——核心看ROIC趋势、利润增速、边际变化',
  'revenue': '市场在定价收入增长/TAM扩张——核心看PS倍数、收入增速、渗透率',
  'asset': '市场在定价资产价值重估——核心看PB、ROE改善、资产质量',
  'resource': '市场在定价资源量/价——核心看EV/EBITDA、储量、商品价格',
  'pipeline': '市场在定价管线价值——核心看PoS、峰值销售、rNPV',
  'sotp': '市场需分部估值——不同业务用不同锚，加总后对比市值',
};
const BIAS_EXPLAIN: Record<string,string> = {
  'undervalued': '模型认为当前市值低于内在价值（存在安全边际）',
  'fairly_valued': '当前市值与内在价值基本吻合',
  'overvalued': '模型认为当前市值已高于内在价值（警惕追高）',
  'uncertain': '方向不明确，需结合其他信号综合判断',
};

/* ================================================================== */
/*  模块注册                                                             */
/* ================================================================== */
const MODULES = [
  { id: 'summary', label: '估值摘要', cat: 'core', on: true },
  { id: 'scenarios', label: '三情景', cat: 'core', on: true },
  { id: 'bs', label: 'BS检测', cat: 'core', on: true },
  { id: 'routing', label: '路由', cat: 'core', on: true },
  { id: 'financial', label: '财务+WACC', cat: 'core', on: true },
  { id: 'gap', label: '预期差', cat: 'core', on: true },
  { id: 'confidence', label: '置信度', cat: 'core', on: true },
  { id: 'trade', label: '标注', cat: 'core', on: true },
  { id: 'kpi', label: 'KPI', cat: 'core', on: true },
  { id: 'triggers', label: '触发', cat: 'core', on: true },
  { id: 'baseline', label: '基线分析', cat: 'core', on: true },
  { id: 'narrative', label: '叙事诊断', cat: 'core', on: true },
  { id: 'signal', label: '信号审计', cat: 'core', on: true },
  { id: 'a0_theme', label: '投资主题', cat: 'a0', on: true },
  { id: 'a0_deduction', label: '事件推演', cat: 'a0', on: true },
  { id: 'a0_reasoning', label: '推理', cat: 'a0', on: true },
  { id: 'a0_adversarial', label: '对抗', cat: 'a0', on: true },
  { id: 'a0_knowledge', label: '知识', cat: 'a0', on: true },
  { id: 'a0_research', label: '行业', cat: 'a0', on: true },
  { id: 'a0_raw_event', label: '原始事件', cat: 'a0', on: true },
  { id: 'a0_future', label: '前瞻', cat: 'a0', on: true },
  { id: 'lingguang', label: '灵光', cat: 'match', on: true },
  { id: 'cases', label: '案例', cat: 'match', on: true },
];

/* ================================================================== */
/*  小组件                                                               */
/* ================================================================== */

function RecordSelectCard({ r, sel, onClick }: { r: DingshuluRecord; sel: boolean; onClick: () => void }) {
  const pw = parseFloat(r.prob_weighted_upside_pct || '0');
  return (
    <div onClick={onClick} style={{ padding: '14px 16px', cursor: 'pointer', transition: '.2s', background: sel ? 'rgba(173,255,0,.06)' : 'rgba(255,255,255,.02)', borderLeft: sel ? '3px solid #ADFF00' : '3px solid transparent', border: sel ? '1px solid rgba(173,255,0,.15)' : '1px solid rgba(255,255,255,.04)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 15, fontWeight: 700, color: '#F2F4F3' }}>{r.stock_name}</span>
        <span style={{ fontFamily: F.mono, fontSize: 11, color: '#666' }}>{r.stock_code}</span>
        <span style={{ fontFamily: F.mono, fontSize: 10, color: r.trade_tier?.startsWith('★★★') ? '#ADFF00' : '#888' }}>{r.trade_tier || '—'}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ fontFamily: F.mono, fontSize: 11, color: pw >= 0 ? '#ADFF00' : '#FF5C00' }}>{pw >= 0 ? '+' : ''}{r.prob_weighted_upside_pct || '—'}%</span>
        <span style={{ fontFamily: F.mono, fontSize: 11, color: '#777' }}>置信 {r.confidence_score || '—'}</span>
      </div>
    </div>
  );
}

function DecisionRender({ text }: { text: string }) {
  return <div style={{ fontFamily: F.body, fontSize: 14, color: '#F2F4F3', lineHeight: 2, whiteSpace: 'pre-wrap' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }} />;
}

function LingGuangCard({ lg, onSave, onDelete }: { lg: LingGuangItem; onSave: (s: string, d: Partial<LingGuangItem>) => void; onDelete: (s: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(lg.title);
  const [content, setContent] = useState(lg.content);
  const [tags, setTags] = useState(lg.tags.join(', '));
  const handleSave = () => { onSave(lg.id, { ...lg, title, content, tags: tags.split(',').map(t => t.trim()).filter(Boolean) }); setEditing(false); };
  return (
    <div style={{ padding: 16, marginBottom: 8, background: editing ? 'rgba(173,255,0,.04)' : 'rgba(255,255,255,.02)', border: editing ? '1px solid rgba(173,255,0,.15)' : '1px solid rgba(255,255,255,.06)' }}>
      {editing ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <input value={title} onChange={e => setTitle(e.target.value)} style={{ background: 'rgba(255,255,255,.05)', border: '1px solid rgba(255,255,255,.1)', color: '#ADFF00', fontFamily: F.mono, fontSize: 14, padding: '8px 12px', outline: 'none' }} />
          <textarea value={content} onChange={e => setContent(e.target.value)} rows={4} style={{ background: 'rgba(255,255,255,.05)', border: '1px solid rgba(255,255,255,.1)', color: '#F2F4F3', fontFamily: F.body, fontSize: 13, padding: '8px 12px', outline: 'none', resize: 'vertical' }} />
          <input value={tags} onChange={e => setTags(e.target.value)} placeholder="标签,逗号分隔" style={{ background: 'rgba(255,255,255,.05)', border: '1px solid rgba(255,255,255,.1)', color: '#AAA', fontFamily: F.mono, fontSize: 11, padding: '6px 12px', outline: 'none' }} />
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={handleSave} style={{ fontFamily: F.mono, fontSize: 11, color: '#050401', background: '#ADFF00', border: 'none', padding: '6px 16px', cursor: 'pointer' }}>保存</button>
            <button onClick={() => { setTitle(lg.title); setContent(lg.content); setTags(lg.tags.join(', ')); setEditing(false); }} style={{ fontFamily: F.mono, fontSize: 11, color: '#888', background: 'transparent', border: '1px solid #333', padding: '6px 16px', cursor: 'pointer' }}>取消</button>
          </div>
        </div>
      ) : (
        <div onClick={() => setEditing(true)} style={{ cursor: 'pointer' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 13, color: '#F2F4F3', fontWeight: 600 }}>{lg.title}</span>
            <span style={{ fontFamily: F.mono, fontSize: 10, color: '#555' }}>{lg.updatedAt?.slice(0, 10)}</span>
          </div>
          <p style={{ fontFamily: F.body, fontSize: 12, color: '#888', margin: '0 0 8px 0', lineHeight: 1.6 }}>{lg.content.slice(0, 120)}...</p>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {lg.tags.map(t => <span key={t} style={{ fontFamily: F.mono, fontSize: 9, color: '#666', border: '1px solid #333', padding: '1px 8px' }}>{t}</span>)}
            <span style={{ flex: 1 }} />
            <button onClick={e => { e.stopPropagation(); onDelete(lg.id); }} style={{ fontFamily: F.mono, fontSize: 10, color: '#FF5C00', background: 'transparent', border: '1px solid rgba(255,92,0,.2)', padding: '3px 10px', cursor: 'pointer' }}>删除</button>
          </div>
        </div>
      )}
    </div>
  );
}

function CaseCard({ c }: { c: CaseSummary }) {
  return (
    <div style={{ padding: 16, marginBottom: 8, background: 'rgba(255,255,255,.02)', border: '1px solid rgba(255,255,255,.04)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontFamily: F.pixel, fontSize: 16, color: '#F2F4F3' }}>{c.stockName} <span style={{ fontSize: 12, color: '#666' }}>{c.stockCode}</span></span>
        <span style={{ fontFamily: F.pixel, fontSize: 14, color: '#ADFF00' }}>{c.gainMultiple}x</span>
      </div>
      <p style={{ fontFamily: F.body, fontSize: 12, color: '#888', margin: '0 0 8px 0', lineHeight: 1.6 }}>{c.sector} {c.catalyst ? `· ${c.catalyst}` : ''}</p>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: F.mono, fontSize: 10, color: '#555' }}>ROIC +{c.roicImprovement || '?'}ppt</span>
        {c.t2xMonths != null && <span style={{ fontFamily: F.mono, fontSize: 10, color: '#555' }}>2x/{c.t2xMonths}月</span>}
        <span style={{ fontFamily: F.mono, fontSize: 10, color: '#555' }}>{c.primaryDriver || ''}</span>
      </div>
    </div>
  );
}

function TrackingCard({ t }: { t: TrackingItem }) {
  return (
    <div style={{ padding: 16, marginBottom: 8, background: 'rgba(255,255,255,.02)', border: '1px solid rgba(255,255,255,.04)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 14, fontWeight: 700, color: '#F2F4F3' }}>{t.stockName} ({t.stockCode})</span>
        <span style={{ fontFamily: F.mono, fontSize: 10, color: t.status === 'active' ? '#ADFF00' : '#666', border: `1px solid ${t.status === 'active' ? 'rgba(173,255,0,.3)' : '#333'}`, padding: '2px 8px' }}>{t.status}</span>
      </div>
      <div style={{ fontFamily: F.mono, fontSize: 10, color: '#555', marginTop: 4 }}>{t.updatedAt?.slice(0, 10) || ''}</div>
    </div>
  );
}

/* ================================================================== */
/*  Main                                                                */
/* ================================================================== */

export default function AgentAvatar() {
  const navigate = useNavigate();
  const resultRef = useRef<HTMLDivElement>(null);
  const mobile = useMobile();
  const [navHeight, setNavHeight] = useState(64)
  useEffect(() => { const nav = document.querySelector('nav'); if (nav) setNavHeight(nav.offsetHeight) }, [])

  // Data
  const [records, setRecords] = useState<DingshuluRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const selectedRecord = records.find(r => r.id === selectedId);

  // Context
  const [toggles, setToggles] = useState<Record<string, boolean>>(() => {
    const t: Record<string, boolean> = {};
    MODULES.forEach(m => t[m.id] = m.on);
    return t;
  });
  const [reportJSON, setReportJSON] = useState<Record<string, unknown> | null>(null);
  const [assembledText, setAssembledText] = useState('');
  const [charCount, setCharCount] = useState(0);
  const [showPreview, setShowPreview] = useState(false);

  // 修者注
  const [noteOn, setNoteOn] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [noteExpanded, setNoteExpanded] = useState(false);

  // AI
  const [deciding, setDeciding] = useState(false);
  const [result, setResult] = useState('');
  const [streamText, setStreamText] = useState('');

  // Memory
  const [lingguangs, setLingguangs] = useState<LingGuangItem[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [trackings, setTrackings] = useState<TrackingItem[]>([]);
  const [activeTab, setActiveTab] = useState<'tuiyan' | 'lingguang' | 'cases' | 'tracking'>('tuiyan');

  // Init
  useEffect(() => {
    fetchDingshulu(200).then(setRecords).catch(() => {}).finally(() => setLoading(false));
    fetchLingGuangList().then(setLingguangs).catch(() => setLingguangs([]));
    fetchCaseList().then(setCases).catch(() => setCases([]));
    fetchTrackingList().then(setTrackings).catch(() => setTrackings([]));
  }, []);

  const refreshMemory = useCallback(() => {
    fetchLingGuangList().then(setLingguangs).catch(() => {});
    fetchCaseList().then(setCases).catch(() => {});
    fetchTrackingList().then(setTrackings).catch(() => {});
  }, []);

  // Load report when record selected
  useEffect(() => {
    if (!selectedId || !selectedRecord) { setReportJSON(null); return; }
    fetchReportFromCoze(selectedRecord.stock_code)
      
      .then(json => setReportJSON(json))
      .catch(() => setReportJSON(null));
    setResult('');
    setStreamText('');
    setError('');
  }, [selectedId, records]);

  // ── 组装上下文 ──
  useEffect(() => {
    if (!reportJSON || !selectedRecord) {
      setAssembledText('');
      setCharCount(0);
      return;
    }
    const memory = loadMemory();
    const a0 = (reportJSON.agent0 || {}) as Record<string, unknown>;
    const a3 = (reportJSON.agent3 || {}) as Record<string, unknown>;
    const a2a = (reportJSON.agent2a || {}) as Record<string, unknown>;
    const routing = (reportJSON.routing_decision || {}) as Record<string, unknown>;
    const cf = (G(reportJSON, 'agent1', 'packages', 'core', 'fields') || G(reportJSON, 'agent1', 'clean_financials') || {}) as Record<string, unknown>;
    const parts: string[] = [];
    const add = (t: string, b: string) => { if (b.trim()) parts.push(`## ${t}\n${b}`); };

    const ms = (G(a3, 'market_sanity') || {}) as Record<string, unknown>;
    const vs = (G(a3, 'valuation_summary') || G(a3, 'scenario_valuation') || {}) as Record<string, unknown>;
    const gap = (G(a3, 'expectation_gap') || {}) as Record<string, unknown>;
    const conf = (G(a3, 'confidence') || {}) as Record<string, unknown>;
    const ta = (G(a3, 'trade_annotation') || {}) as Record<string, unknown>;
    const kpis = (G(a3, 'monitoring_kpis') || {}) as Record<string, unknown>;
    const triggers = (G(a3, 'risk_triggers') || {}) as Record<string, unknown>;
    const scenarios = (Array.isArray(G(a3, 'scenarios')) ? G(a3, 'scenarios') as Array<Record<string, unknown>> : []);
    const kw = [selectedRecord.stock_name, selectedRecord.stock_code].filter(Boolean) as string[];

    if (toggles.summary) {
      add('估值摘要', [
        `- ${selectedRecord.stock_name} (${selectedRecord.stock_code}) | 市值 ${N(cf?.market_cap_yi || cf?.market_cap_billion)} 亿`,
        `- 加权市值: ${N(vs?.probability_weighted_mcap_yi || vs?.probability_weighted_mcap_billion)} 亿 | 加权涨幅: ${Pct(vs?.probability_weighted_upside_pct)}`,
        `- 不对称比: ${N(vs?.asymmetry_ratio)} | 质量: ${String(vs?.quality_flag || '?')}`,
      ].join('\n'));
    }
    if (toggles.scenarios && scenarios.length > 0) {
      const h = '| 情景 | 概率 | 目标市值 | 涨跌幅 | 因果 |\n|------|------|----------|------|------|';
      const rows = scenarios.map(s => {
        const u = parseFloat(String(s?.upside_pct ?? 0));
        return `| ${String(s?.name || '?')} | ${Pct(s?.probability_pct || N(s?.probability))} | ${N(s?.target_mcap_yi || s?.target_mcap_billion)} 亿 | ${u >= 0 ? '+' : ''}${u.toFixed(1)}% | ${String(s?.scenario_narrative || '')} |`;
      }).join('\n');
      add('三情景', `${h}\n${rows}`);
    }
    if (toggles.bs) {
      add('BS检测', [
        `- ${String(ms?.bs_level || '?')} | EV: ${N(ms?.ev_yi || ms?.ev_billion)} 亿 | ROIC: ${Pct(ms?.roic_pct)}`,
        `- WACC: ${Pct(ms?.wacc_simple_pct)} | 隐含 g: ${Pct(ms?.implied_g_pct)} | 溢价: ${Pct(ms?.market_premium_pct)}`,
        `- PE: ${N(ms?.pe_ttm)}x (分位 ${String(ms?.pe_historical_rank || '?')}) | PB: ${N(ms?.pb)}x`,
      ].join('\n'));
    }
    if (toggles.routing) {
      const vm = Array.isArray(routing.validation_models) ? routing.validation_models.join('+') : String(routing?.validation_models || routing?.secondary_model || '?');
      const cc = routing?.constraint_compliance as Record<string,unknown> | undefined;
      add('估值路由', [
        `- 主模型: ${String(routing?.primary_model || '?')} (${String(routing?.model_category || '?')})`,
        `- 校验: ${vm} | 策略: ${String(routing?.validation_strategy || '?')}`,
        `- 理由: ${String(routing?.routing_reason || '—')}`,
        cc?.constraint_override ? `- ⚠️ 约束覆写: ${String(cc?.override_rationale || '—')}` : '',
        routing?.anchor_shift_warning ? `- ⚠️ 锚切换预警: ${String(routing?.anchor_shift_warning)}` : '',
      ].filter(Boolean).join('\n'));
    }
    if (toggles.narrative) {
      const mn = (a2a?.market_narrative || a2a?.marketNarrative || {}) as Record<string,unknown>;
      const ep = (a2a?.event_pricing || a2a?.eventPricing || {}) as Record<string,unknown>;
      const epr = (ep?.event_profile || ep?.eventProfile || {}) as Record<string,unknown>;
      const pa = (ep?.pricing_assessment || ep?.pricingAssessment || {}) as Record<string,unknown>;
      const fwd = (a2a?.forward_to_routing || a2a?.forwardToRouting || {}) as Record<string,unknown>;
      const anchor = String(mn?.primary_anchor || '?');
      const shape = String(epr?.distribution_shape || '?');
      const bias = String(fwd?.pricing_bias || 'uncertain');
      const pricedIn = String(pa?.overall_priced_in || '?');
      const pricedEst = String(pa?.priced_in_estimate || '');
      const timing = String(epr?.timing_certainty || '?');
      const binary = String(epr?.outcome_binaryness || '?');
      const precedent = String(epr?.precedent_richness || '?');
      const lines = [
        `- ★ 主锚: **${anchor}** — ${ANCHOR_FOCUS[anchor] || '关注锚定对应指标'}`,
        mn?.narrative_summary ? `- 锚叙事: ${String(mn.narrative_summary).slice(0, 300)}` : '',
        `- 事件分布: ${shape}（${SHAPE_EXPLAIN[shape] || '分布形态反映市场共识度与不确定性'}）`,
        `- 定价偏向: ${bias} — ${BIAS_EXPLAIN[bias] || '需结合情景推演判断'}`,
        pricedIn !== '?' ? `- 市场计价: ${pricedIn}${pricedEst ? ' / ' + pricedEst : ''}${pa?.residual_catalyst ? ' | 剩余催化: ' + String(pa.residual_catalyst) : ''}` : '',
        `- 3D光谱: 时点确定性${timing}/10 | 结果二元性${binary}/10 | 先例丰富度${precedent}/10`,
        mn?.anchor_conflict ? `- ⚠️ 锚冲突: ${String(mn.anchor_conflict)}` : '',
        mn?.sotp_triggered ? '- ⚠️ SOTP已触发 — 需分部估值，不同业务不能混用一个锚' : '',
      ].filter(Boolean);
      add('叙事诊断（Agent-2a V6）', lines.join('\n'));
    }
    if (toggles.signal) {
      const sa = (a2a?.signal_audit || a2a?.signalAudit || {}) as Record<string,unknown>;
      const matches = (G(sa, 'step2b_match') || []) as Array<Record<string,unknown>>;
      const lines = matches.map(m =>
        `- **${String(m?.match || m?.signal || '?')}** (${String(m?.source_level || m?.sourceLevel || '?')}) — ${String(m?.basis || '—')}`
      );
      if (lines.length) add(`信号审计: 评分${String(G(sa, 'step2d_score') || '?')}`, lines.join('\n'));
    }
    if (toggles.financial) {
      const wp = (G(ms, 'wacc_params') || {}) as Record<string, unknown>;
      add('财务+WACC', [
        `营收 ${N(cf?.revenue_ttm_yi || cf?.revenue_ttm_billion)} 亿 | 净利 ${N(cf?.net_profit_ttm_yi || cf?.net_profit_billion)} 亿 | ROIC ${Pct(cf?.roic_pct)} | 毛利 ${Pct(cf?.gross_margin_pct)}`,
        `OCF ${N(cf?.ocf_ttm_yi || cf?.operating_cf_ttm_billion)} 亿 | CAPEX ${N(cf?.capex_ttm_yi || cf?.capex_ttm_billion)} 亿 | EBITDA ${N(cf?.ebitda_ttm_yi || cf?.ebitda_ttm_billion)} 亿`,
        `总资产 ${N(cf?.total_assets_yi || cf?.total_assets_billion)} 亿 | 净资产 ${N(cf?.total_equity_yi || cf?.total_equity_billion)} 亿 | 负债 ${N(cf?.interest_bearing_debt_yi || cf?.interest_bearing_debt_billion)} 亿`,
        `WACC: Rf ${Pct(wp?.rf_pct)} Beta ${N(wp?.beta)} ERP ${Pct(wp?.erp_pct)} WACC ${Pct(wp?.wacc_pct)}`,
      ].join('\n'));
    }
    if (toggles.gap) add('预期差', `- ${String(gap?.level || '?')}\n- ${String(gap?.note || '—')}`);
    if (toggles.confidence) {
      const dims = (G(conf, 'dimensions') || {}) as Record<string, Record<string, unknown>>;
      add(`置信度: ${String(G(conf, 'overall_score') || '?')}/10`, Object.entries(dims).map(([, d]) => `- ${String(d?.label || '?')}: ${String(d?.score || '?')}/10`).join('\n'));
    }
    if (toggles.trade) add(`交易标注: ${String(ta?.tier || '?')} (${String(ta?.total_score || '?')})`, `- ${String(ta?.suggested_action || ta?.tier_note || '')}`);
    if (toggles.kpi) {
      ['financial_verification_kpis', 'event_milestone_kpis', 'competition_signal_kpis', 'risk_trigger_kpis'].forEach(cat => {
        const items = (G(kpis, cat) || []) as Array<Record<string, unknown>>;
        if (items.length) add('KPI', items.map(k => `- **${String(k.name || k.kpi || k.milestone)}**: ${String(k.target || k.threshold || k.expected_timing || '—')}`).join('\n'));
      });
    }
    if (toggles.triggers) add('风险触发器', `- 牛: ${String(triggers?.bull_trigger || '')}\n- 熊: ${String(triggers?.bear_trigger || '')}`);

    if (toggles.baseline) {
      const bl = String(G(reportJSON, 'baseline_report') || '');
      if (bl) add('基线分析', bl.slice(0, 4000));
    }

    const a0Map: Record<string, string> = {
      a0_theme: 'investment_theme', a0_deduction: 'event_deduction', a0_reasoning: 'preliminary_reasoning',
      a0_adversarial: 'adversarial_thinking', a0_knowledge: 'knowledge_supplement', a0_research: 'industry_expert_research',
      a0_raw_event: 'raw_event_text', a0_future: 'future',
    };
    Object.entries(a0Map).forEach(([id, key]) => {
      if (!toggles[id]) return;
      const t = String(G(a0, key) || '');
      if (t) add('A0', t);
    });

    if (toggles.lingguang) {
      const lgs = memory.lingguangs
        .map(lg => ({ ...lg, score: kw.filter(k => (lg.content + lg.title).toLowerCase().includes(k.toLowerCase())).length }))
        .sort((a, b) => b.score - a.score)
        .slice(0, 3);
      if (lgs.length) add('灵光匹配', lgs.map(lg => `- **${lg.title}**: ${lg.content}`).join('\n'));
    }
    if (toggles.cases) {
      const cs = memory.cases
        .map(c => {
          let s = 0;
          const ct = [c.sector, c.primaryDriver, ...(c.tags || [])].filter(Boolean).join(' ').toLowerCase();
          for (const k of kw) if (ct.includes(k.toLowerCase())) s += 2;
          return { ...c, score: s };
        })
        .sort((a, b) => b.score - a.score)
        .slice(0, 5);
      if (cs.length) {
        add('案例匹配', '| # | 案例 | 代码 | 回报 | 行业 | 驱动 |\n|---|------|------|------|------|------|\n'
          + cs.map((c, i) => `| ${i + 1} | ${c.stockName} | ${c.stockCode} | ${c.gainMultiple}x | ${c.sector || '—'} | ${c.primaryDriver || '—'} |`).join('\n'));
      }
    }
    if (noteOn && noteText.trim()) add('修者注', noteText.trim());

    const text = parts.join('\n\n---\n\n');
    setAssembledText(text);
    setCharCount(text.length);
  }, [reportJSON, toggles, selectedRecord, noteOn, noteText]);

  // Animate result
  useEffect(() => {
    if (result && resultRef.current) gsap.fromTo(resultRef.current, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: .5 });
  }, [result]);

  // ── 发令 ──
  const handleDecide = async () => {
    if (!assembledText) return;
    const memory = loadMemory();
    if (!memory.config.enabled || !memory.config.apiKey) { setError('AI 引擎未配置'); return; }
    setDeciding(true);
    setResult('');
    setStreamText('');
    setError('');
    const sp = '你是长流水宗门的"身外化身"——专精十倍股猎杀的 AI 投资决策 Agent。\n\n## 决策六步\n1.产业逻辑 2.财务体检 3.估值空间 4.催化剂 5.风险扫描 6.综合判断\n\n## 输出\n# 投资决策报告\n## 推演结论: {通过/有条件通过/否决} (Conviction: 0-100)\n## 核心逻辑\n## 产业位置\n## 财务快照\n## 估值锚定\n## 催化剂\n## 风险\n## 建议';
    try {
      let full = '';
      await callAgentAI(
        { record: {} as any, matchedLingguangs: [], matchedCases: [], systemPrompt: sp, workflowSteps: [], assembledPrompt: `---\n${assembledText}\n---\n请严格执行六步框架，用中文输出完整决策报告。` },
        c => { full += c; setStreamText(full); }
      );
      setResult(full);
      setStreamText('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '未知错误');
    } finally {
      setDeciding(false);
    }
  };

  // ── Memory actions ──
  const handleSaveLingGuang = async (slug: string, data: Partial<LingGuangItem>) => { await saveLingGuang(slug, data); refreshMemory(); };
  const handleDeleteLingGuang = async (slug: string) => { await deleteLingGuang(slug); refreshMemory(); };

  // ── Toggle helpers ──
  const allIds = MODULES.map(m => m.id);
  const allOn = allIds.every(id => toggles[id]);
  const toggleAll = () => { setToggles(prev => { const next = { ...prev }; const on = !allOn; allIds.forEach(id => next[id] = on); return next; }); };

  const TBtn = ({ id, label }: { id: string; label: string }) => (
    <button onClick={() => setToggles(p => ({ ...p, [id]: !p[id] }))}
      style={{
        fontFamily: F.mono, fontSize: 10, padding: '4px 10px', borderRadius: 4,
        border: `1px solid ${toggles[id] ? 'rgba(173,255,0,.3)' : '#333'}`,
        background: toggles[id] ? 'rgba(173,255,0,.06)' : 'transparent',
        color: toggles[id] ? '#ADFF00' : '#555', cursor: 'pointer', transition: '.2s', whiteSpace: 'nowrap',
      }}
    >{label}</button>
  );

  // ── RENDER ──
  return (
    <div style={{ height: `calc(100vh - ${navHeight}px)`, background: C.bg, color: C.white, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <style>{HIDE_SCR}</style>
      {/* Toolbar — 身外化身功能按钮 */}
      <div style={{ flexShrink: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '10px 48px', background: 'rgba(5,4,1,.6)', borderBottom: '1px solid #2A2A2A' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ width: '6px', height: '6px', background: '#ADFF00', boxShadow: '0 0 8px rgba(173,255,0,0.5)', animation: 'pulse 2s ease-in-out infinite', display: 'inline-block' }} />
          <span style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: '18px', color: '#ADFF00', letterSpacing: '0.06em' }}>身外化身</span>
          <span style={{ fontFamily: F.body, fontSize: '12px', color: '#555' }}>配置你的AI投资身外化身 — 灵光、案例、工作流与API</span>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <button onClick={refreshMemory} style={{ fontFamily: F.mono, fontSize: 12, color: '#888', background: 'transparent', border: '1px solid #2A2A2A', padding: '6px 16px', cursor: 'pointer', letterSpacing: '0.05em' }}>刷新</button>
          <button onClick={() => navigate('/agent-config')} style={{ fontFamily: F.mono, fontSize: 12, color: '#888', background: 'transparent', border: '1px solid #2A2A2A', padding: '6px 16px', cursor: 'pointer', letterSpacing: '0.05em' }}>配置</button>
          <button onClick={() => navigate('/avatar-cc')} style={{ fontFamily: F.mono, fontSize: 12, color: '#D97706', background: 'transparent', border: '1px solid rgba(217,119,6,.3)', padding: '6px 16px', cursor: 'pointer', letterSpacing: '0.05em' }}>CC 上下文 →</button>
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: mobile ? 'column' : 'row', overflow: 'hidden' }}>
        {/* LEFT — 定数录 */}
        <div style={{ width: mobile ? '100%' : '340px', minWidth: mobile ? 'auto' : '340px', borderRight: mobile ? 'none' : '1px solid #2A2A2A', display: 'flex', flexDirection: 'column', background: '#050401', maxHeight: mobile ? '240px' : 'none' }}>
          <div style={{ padding: '20px 16px', borderBottom: '1px solid #2A2A2A' }}>
            <h3 style={{ fontFamily: F.mono, fontSize: 13, color: '#AAA', letterSpacing: '0.15em', margin: '0 0 4px 0' }}>定数录</h3>
            <p style={{ fontFamily: F.mono, fontSize: 11, color: '#555', margin: 0 }}>{records.length} 条 · 选中后右侧推演</p>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }} className="av-scroll">
            {loading && <div style={{ padding: '40px', textAlign: 'center', fontFamily: F.mono, fontSize: 13, color: '#555' }}>加载中...</div>}
            {records.map(r => <RecordSelectCard key={r.id} r={r} sel={r.id === selectedId} onClick={() => { setSelectedId(r.id); setActiveTab('tuiyan'); }} />)}
          </div>
          {/* Memory tabs */}
          <div style={{ padding: '14px 16px', borderTop: '1px solid #2A2A2A' }}>
            <div style={{ display: 'flex', gap: 12 }}>
              {[
                { k: 'lingguang', l: '灵光', n: lingguangs.length },
                { k: 'cases', l: '案例', n: cases.length },
                { k: 'tracking', l: '追踪', n: trackings.length },
              ].map(s => (
                <button key={s.k} onClick={() => setActiveTab(s.k as any)}
                  style={{
                    flex: 1, background: activeTab === s.k ? 'rgba(173,255,0,.06)' : 'transparent',
                    border: activeTab === s.k ? '1px solid rgba(173,255,0,.15)' : '1px solid #2A2A2A',
                    padding: '8px', cursor: 'pointer', textAlign: 'center', transition: '.2s',
                  }}>
                  <div style={{ fontFamily: F.pixel, fontSize: 16, color: activeTab === s.k ? '#ADFF00' : '#888' }}>{s.n}</div>
                  <div style={{ fontFamily: F.mono, fontSize: 9, color: '#555', marginTop: 2 }}>{s.l}</div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* RIGHT */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#050401' }}>
          {activeTab === 'tuiyan' && (
            <>
              {/* 修者注 */}
              {selectedRecord && (
                <div onClick={() => setNoteExpanded(!noteExpanded)}
                  style={{
                    cursor: 'pointer', padding: '12px 20px', borderBottom: '1px solid #2A2A2A',
                    background: noteOn ? 'linear-gradient(90deg,rgba(173,255,0,.14) 0%,rgba(173,255,0,.05) 50%,transparent 100%)' : 'rgba(255,255,255,.01)',
                    transition: '.4s', position: 'relative', overflow: 'hidden',
                  }}>
                  <div className="note-array-bg" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg width=%2740%27 height=%2740%27 xmlns=%27http://www.w3.org/2000/svg%27%3E%3Cpath d=%27M20 2L38 20L20 38L2 20Z%27 fill=%27none%27 stroke=%27%23ADFF00%27 stroke-width=%270.3%27/%3E%3C/svg%3E")', opacity: noteOn ? .25 : .06 }} />
                  <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', opacity: noteOn ? .15 : .04, transition: '.4s', background: 'radial-gradient(ellipse at 15% 50%,rgba(173,255,0,.4) 0%,transparent 70%)' }} />
                  <div className="note-runes" />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, position: 'relative', zIndex: 1 }}>
                    <span style={{ fontFamily: 'serif', fontSize: 22, color: noteOn ? '#ADFF00' : '#555', transition: '.4s', textShadow: noteOn ? '0 0 16px rgba(173,255,0,.6)' : '0 0 4px rgba(173,255,0,.1)', filter: noteOn ? 'brightness(1.3)' : 'grayscale(0.4)' }}>◇</span>
                    <span style={{ fontFamily: F.mono, fontSize: 15, fontWeight: 700, color: noteOn ? '#ADFF00' : '#BBB', letterSpacing: '0.16em', textShadow: noteOn ? '0 0 8px rgba(173,255,0,.3)' : '', transition: '.3s' }}>修 者 注</span>
                    <button onClick={e => { e.stopPropagation(); setNoteOn(!noteOn); }}
                      style={{
                        fontFamily: F.mono, fontSize: 13, fontWeight: 700, padding: '5px 16px', borderRadius: 6,
                        border: '2px solid ' + (noteOn ? '#ADFF00' : 'rgba(173,255,0,.15)'),
                        background: noteOn ? 'rgba(173,255,0,.12)' : 'rgba(173,255,0,.03)',
                        color: noteOn ? '#ADFF00' : '#AAA', cursor: 'pointer', letterSpacing: '0.1em',
                        textShadow: noteOn ? '0 0 12px rgba(173,255,0,.5)' : '',
                        boxShadow: noteOn ? '0 0 16px rgba(173,255,0,.2),inset 0 0 8px rgba(173,255,0,.1)' : '0 0 4px rgba(173,255,0,.05)',
                        transition: '.3s', animation: noteOn ? 'pulse 2s ease-in-out infinite' : 'none',
                      }}
                      onMouseEnter={e => { if (!noteOn) { e.currentTarget.style.borderColor = '#ADFF0080'; e.currentTarget.style.color = '#ADFF00'; } }}
                      onMouseLeave={e => { if (!noteOn) { e.currentTarget.style.borderColor = 'rgba(173,255,0,.15)'; e.currentTarget.style.color = '#AAA'; } }}
                    >{noteOn ? '已采纳' : '采纳'}</button>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontFamily: F.mono, fontSize: 11, color: noteOn ? '#DDD' : '#888' }}>{noteText ? `${noteText.length} 字` : '空'}</span>
                    <span style={{ fontFamily: F.mono, fontSize: 10, color: noteOn ? '#ADFF00' : '#666', transition: '.3s', transform: noteExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
                  </div>
                  {noteExpanded && (
                    <div style={{ position: 'relative', zIndex: 1, marginTop: 12 }} onClick={e => e.stopPropagation()}>
                      <textarea value={noteText} onChange={e => setNoteText(e.target.value)} rows={6}
                        placeholder="独有资讯、另类数据、个人见解…"
                        style={{
                          width: '100%', background: 'rgba(0,0,0,.3)', border: '1px solid ' + (noteOn ? 'rgba(173,255,0,.3)' : '#333'),
                          color: noteOn ? '#DDD' : '#888', fontFamily: F.body, fontSize: 14, padding: '12px 16px',
                          outline: 'none', borderRadius: 6, resize: 'vertical', lineHeight: 1.8, transition: '.3s',
                        }}
                        onFocus={e => { e.currentTarget.style.borderColor = 'rgba(173,255,0,.6)'; e.currentTarget.style.boxShadow = '0 0 16px rgba(173,255,0,.2)'; }}
                        onBlur={e => { e.currentTarget.style.borderColor = noteOn ? 'rgba(173,255,0,.3)' : '#333'; e.currentTarget.style.boxShadow = 'none'; }}
                      />
                    </div>
                  )}
                </div>
              )}

              {/* 模块开关 */}
              {selectedRecord && (
                <div style={{ flexShrink: 0, padding: '8px 20px', borderBottom: '1px solid #2A2A2A', display: 'flex', flexDirection: 'column', gap: 5, background: 'rgba(255,255,255,.01)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: F.mono, fontSize: 10, color: '#555', marginRight: 4 }}>核心</span>
                    {MODULES.filter(m => m.cat === 'core').map(m => <TBtn key={m.id} id={m.id} label={m.label} />)}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: F.mono, fontSize: 10, color: '#555', marginRight: 4 }}>全局</span>
                    <button onClick={toggleAll}
                      style={{
                        fontFamily: F.mono, fontSize: 10, padding: '4px 10px', borderRadius: 4,
                        border: `1px solid ${allOn ? 'rgba(255,92,0,.3)' : '#333'}`,
                        background: allOn ? 'rgba(255,92,0,.06)' : 'transparent',
                        color: allOn ? '#FF5C00' : '#555', cursor: 'pointer', transition: '.2s', whiteSpace: 'nowrap',
                      }}
                    >{allOn ? '全部 OFF' : '全部 ON'}</button>
                    <span style={{ fontFamily: F.mono, fontSize: 10, color: '#555', marginRight: 4 }}>A0</span>
                    {MODULES.filter(m => m.cat === 'a0').map(m => <TBtn key={m.id} id={m.id} label={m.label} />)}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
                    <span style={{ fontFamily: F.mono, fontSize: 10, color: '#555', marginRight: 4 }}>匹配</span>
                    {MODULES.filter(m => m.cat === 'match').map(m => <TBtn key={m.id} id={m.id} label={m.label} />)}
                    <span style={{ flex: 1 }} />
                    <span style={{ fontFamily: F.mono, fontSize: 11, color: '#ADFF00' }}>{charCount.toLocaleString()} 字</span>
                    <button onClick={() => setShowPreview(!showPreview)}
                      style={{ fontFamily: F.mono, fontSize: 10, color: showPreview ? '#ADFF00' : '#555', background: 'transparent', border: '1px solid #333', padding: '4px 12px', cursor: 'pointer', borderRadius: 4, marginLeft: 8 }}>
                      {showPreview ? '收符' : '展符'}
                    </button>
                    <button onClick={handleDecide} disabled={deciding || !assembledText}
                      style={{ fontFamily: F.mono, fontSize: 11, color: deciding ? '#555' : '#050401', background: deciding ? 'transparent' : '#ADFF00', border: deciding ? '1px solid #333' : 'none', padding: '5px 16px', cursor: deciding ? 'not-allowed' : 'pointer', borderRadius: 4 }}>
                      {deciding ? '推演中...' : '发令'}
                    </button>
                  </div>
                </div>
              )}

              {/* 内容区 */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '20px 28px' }} className="av-scroll">
                {!selectedRecord && <div style={{ textAlign: 'center', padding: 80 }}><p style={{ fontFamily: F.body, fontSize: 14, color: '#555' }}>从左侧定数录选择标的</p></div>}
                {selectedRecord && showPreview && (
                  <div style={{ fontFamily: F.body, fontSize: 14, color: '#F2F4F3', lineHeight: 1.8 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(assembledText) || '<p style="color:#555">正在组装...</p>' }} />
                )}
                {selectedRecord && !showPreview && (
                  <div style={{ padding: '20px 24px', background: 'rgba(255,255,255,.02)', border: '1px solid #2A2A2A', borderRadius: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                      <span style={{ fontFamily: F.mono, fontSize: 11, color: '#ADFF00' }}>{selectedRecord.stock_name} ({selectedRecord.stock_code})</span>
                      <span style={{ fontFamily: F.mono, fontSize: 10, color: '#FF5C00' }}>{selectedRecord.trade_tier || ''}</span>
                      <span style={{ flex: 1 }} />
                      <span style={{ fontFamily: F.mono, fontSize: 10, color: '#888' }}>{charCount.toLocaleString()} 字</span>
                    </div>
                    {error && (
                      <div style={{ padding: '12px 16px', marginBottom: 12, background: 'rgba(255,92,0,.06)', border: '1px solid rgba(255,92,0,.15)', borderRadius: 4, fontFamily: F.mono, fontSize: 12, color: '#FF5C00' }}>{error}</div>
                    )}
                    {streamText && <div ref={resultRef} style={{ maxHeight: '60vh', overflowY: 'auto' }} className="av-scroll"><DecisionRender text={streamText} /></div>}
                    {result && !streamText && <div ref={resultRef}><DecisionRender text={result} /></div>}
                    {!streamText && !result && <p style={{ fontFamily: F.body, fontSize: 14, color: '#555' }}>勾选上方模块 → 展符预览上下文 → 点击「发令」唤醒道胎</p>}
                  </div>
                )}
              </div>
            </>
          )}

          {/* 灵光 */}
          {activeTab === 'lingguang' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px' }} className="av-scroll">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ fontFamily: F.mono, fontSize: 14, color: '#AAA', margin: 0 }}>灵光 · {lingguangs.length} 条</h3>
                <button onClick={() => handleSaveLingGuang(`lg-${Date.now()}`, { id: `lg-${Date.now()}`, title: '新灵光', content: '', tags: [], createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() })}
                  style={{ fontFamily: F.mono, fontSize: 11, color: '#ADFF00', background: 'transparent', border: '1px solid rgba(173,255,0,.2)', padding: '6px 14px', cursor: 'pointer' }}>+ 新灵光</button>
              </div>
              {lingguangs.map(lg => <LingGuangCard key={lg.id} lg={lg} onSave={handleSaveLingGuang} onDelete={handleDeleteLingGuang} />)}
            </div>
          )}

          {/* 案例 */}
          {activeTab === 'cases' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px' }} className="av-scroll">
              <h3 style={{ fontFamily: F.mono, fontSize: 14, color: '#AAA', margin: '0 0 16px 0' }}>案例 · {cases.length} 条</h3>
              {cases.map(c => <CaseCard key={c.id} c={c} />)}
            </div>
          )}

          {/* 追踪 */}
          {activeTab === 'tracking' && (
            <div style={{ flex: 1, overflowY: 'auto', padding: '24px 28px' }} className="av-scroll">
              <h3 style={{ fontFamily: F.mono, fontSize: 14, color: '#AAA', margin: '0 0 16px 0' }}>追踪 · {trackings.length} 条</h3>
              {trackings.map(t => <TrackingCard key={t.stockCode} t={t} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
