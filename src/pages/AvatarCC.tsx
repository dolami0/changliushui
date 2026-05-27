import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { fetchDingshulu, type DingshuluRecord } from '../services/cozeApi';
import { loadMemory } from '../services/agentMemory';
import { renderMarkdown } from '../lib/utils';

/* ================================================================== */
/*  身外化身 · CC 持久会话 — 模块化上下文组装                            */
/* ================================================================== */

const CC = '#D97706'; const AU = '#FFB347'; const BG = '#0a0806'; const SURFACE = '#100d0a';
const BORDER = '#1f1a12'; const DIM = '#5c4a32'; const TEXT = '#c4b5a0'; const MUTED = '#6b5e4f';
const FONT = "'Noto Sans SC','IBM Plex Sans','Segoe UI',system-ui,sans-serif";
const MONO = "'JetBrains Mono','IBM Plex Mono','Noto Sans SC',monospace";

type ChatMsg = { role: 'user' | 'assistant'; content: string; time: string };
type ModuleId = string;

// ── 模块注册表 ──
interface ContextModule {
  id: ModuleId;
  label: string;
  category: 'core' | 'agent0' | 'match';
  defaultOn: boolean;
}
const MODULES: ContextModule[] = [
  // 核心估值数据 — 逐个勾选
  { id: 'summary',        label: '估值摘要',     category: 'core',   defaultOn: true },
  { id: 'scenarios',      label: '三情景推演',   category: 'core',   defaultOn: true },
  { id: 'bs',             label: 'BS检测器',     category: 'core',   defaultOn: true },
  { id: 'routing',        label: '估值路由',     category: 'core',   defaultOn: false },
  { id: 'financial',      label: '财务全景+WACC', category: 'core',  defaultOn: false },
  { id: 'gap',            label: '预期差',       category: 'core',   defaultOn: false },
  { id: 'confidence',     label: '置信度评分',   category: 'core',   defaultOn: false },
  { id: 'trade',          label: '交易标注',     category: 'core',   defaultOn: false },
  { id: 'signal',         label: '信号审计',     category: 'core',   defaultOn: false },
  { id: 'kpi',            label: '监测KPI',      category: 'core',   defaultOn: false },
  { id: 'triggers',       label: '风险触发器',   category: 'core',   defaultOn: false },
  { id: 'narrative',      label: '叙事诊断',     category: 'core',   defaultOn: true },
  // Agent0 预路由 — 可整组开关
  { id: 'a0_theme',       label: '投资主题',     category: 'agent0', defaultOn: true },
  { id: 'a0_deduction',   label: '事件推演',     category: 'agent0', defaultOn: true },
  { id: 'a0_reasoning',   label: '推理依据',     category: 'agent0', defaultOn: false },
  { id: 'a0_adversarial', label: '对抗思考',     category: 'agent0', defaultOn: false },
  { id: 'a0_knowledge',   label: '知识补充',     category: 'agent0', defaultOn: false },
  { id: 'a0_research',    label: '行业研究',     category: 'agent0', defaultOn: false },
  // 匹配引擎
  { id: 'lingguang',      label: '灵光匹配',     category: 'match',  defaultOn: true },
  { id: 'cases',          label: '案例匹配',     category: 'match',  defaultOn: true },
];

// ── 样式 ──
const GLOBAL_CSS = `
.cc-scroll::-webkit-scrollbar{display:none}.cc-scroll{scrollbar-width:none}
.cc-card{position:relative;cursor:pointer;padding:14px 18px;background:${SURFACE};border:1px solid ${BORDER};border-left:3px solid transparent;transition:all .25s;margin-bottom:1px}
.cc-card:hover{border-color:#352a18;background:#130f0a}
.cc-card.sel{border-left-color:${CC};background:rgba(217,119,6,.06);border-color:rgba(217,119,6,.18)}
.cc-msg-user{border:1px solid ${BORDER};background:${SURFACE};border-left:3px solid transparent;padding:18px 22px}
.cc-msg-cc{border:1px solid rgba(217,119,6,.12);background:rgba(217,119,6,.03);border-left:3px solid ${CC};padding:18px 22px}
.cc-btn{padding:10px 26px;font-family:'${MONO}';font-size:13px;letter-spacing:.1em;border:1px solid rgba(217,119,6,.25);background:transparent;color:${CC};cursor:pointer;transition:all .2s}
.cc-btn:hover{background:rgba(217,119,6,.08)}
.cc-btn.primary{background:${CC};color:#0a0806;border:none}
.cc-btn.primary:hover{box-shadow:0 0 18px rgba(217,119,6,.3)}
.cc-input{border:1px solid ${BORDER};background:${SURFACE};color:${TEXT};font-family:'${FONT}';font-size:15px;padding:12px 16px;outline:none;width:100%;box-sizing:border-box;transition:border-color .2s;line-height:1.6}
.cc-input:focus{border-color:rgba(217,119,6,.35)}
.cc-toggle{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;border:1px solid ${BORDER};border-radius:6px;background:${SURFACE};transition:all .2s;font-family:'${MONO}';font-size:12px;color:${MUTED};flex-shrink:0}
.cc-toggle.on{border-color:${CC}40;background:rgba(217,119,6,.06);color:${CC}}
.cc-toggle .dot{width:8px;height:8px;border-radius:50%;background:${BORDER};transition:all .2s}
.cc-toggle.on .dot{background:${CC};box-shadow:0 0 6px ${CC}60}
.cc-md{font-family:'${FONT}';font-size:14px;line-height:1.9;color:${TEXT}}
.cc-md h1,.cc-md h2{color:${CC};font-size:16px;margin:12px 0 6px}
.cc-md h3{color:#c4b5a0;font-size:14px;margin:10px 0 4px}
.cc-md strong{color:#d97706;font-weight:600}
.cc-md code{background:rgba(217,119,6,.1);color:${CC};padding:1px 6px;font-size:12px}
.cc-md li{margin:4px 0;color:#a89a84;padding-left:8px}
.cc-md table{width:100%;border-collapse:collapse;margin:8px 0;font-size:12px}
.cc-md th{border-bottom:1px solid ${BORDER};padding:6px 10px;text-align:left;color:${CC};font-family:'${MONO}';font-size:11px}
.cc-md td{border-bottom:1px solid rgba(255,255,255,.04);padding:6px 10px}
.cc-md hr{border:none;border-top:1px solid ${BORDER};margin:12px 0}
`;

// ── 工具 ──
const G = (obj: unknown, ...path: string[]): unknown => {
  let cur = obj;
  for (const k of path) { if (cur == null || typeof cur !== 'object') return undefined; cur = (cur as Record<string,unknown>)[k]; }
  return cur;
};
const N = (v: unknown, d = '—'): string => {
  if (v === null || v === undefined) return d;
  const f = parseFloat(String(v));
  if (isNaN(f)) return String(v);
  return f === Math.round(f) ? String(Math.round(f)) : f.toFixed(1);
};
const Pct = (v: unknown): string => { const s = N(v); return s === '—' ? s : s + '%'; };

function textScore(text: string, keywords: string[]): number {
  const t = text.toLowerCase(); let s = 0;
  for (const k of keywords) if (t.includes(k.toLowerCase())) s += 1;
  return s;
}

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

// ── Record 卡片 ──
function RecordCard({ record, selected, onClick }: { record: DingshuluRecord; selected: boolean; onClick: () => void }) {
  const probWtd = parseFloat(record.prob_weighted_upside_pct || '0');
  return (
    <div onClick={onClick} className={`cc-card${selected ? ' sel' : ''}`}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{ fontFamily: FONT, fontSize: 15, fontWeight: 700, color: selected ? CC : '#d4c8b8' }}>{record.stock_name}</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: MUTED }}>{record.stock_code}</span>
        <span style={{ fontFamily: MONO, fontSize: 10, color: record.trade_tier?.startsWith('★★★') ? CC : MUTED }}>{record.trade_tier || '—'}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ fontFamily: MONO, fontSize: 11, color: probWtd >= 0 ? AU : '#8B4513' }}>{probWtd >= 0 ? '+' : ''}{record.prob_weighted_upside_pct || '—'}%</span>
        <span style={{ fontFamily: MONO, fontSize: 11, color: DIM }}>{'置信'}{record.confidence_score || '—'}</span>
      </div>
    </div>
  );
}

// ── Toggle ──
function Toggle({ label, on, onChange }: { label: string; on: boolean; onChange: () => void }) {
  return (
    <div onClick={onChange} className={`cc-toggle${on ? ' on' : ''}`}>
      <div className="dot" />
      <span>{label}</span>
    </div>
  );
}

/* ================================================================== */
/*  Main                                                                */
/* ================================================================== */
export default function AvatarCC() {
  const navigate = useNavigate();
  const mobile = useMobile();
  const [navHeight, setNavHeight] = useState(64)
  useEffect(() => { const nav = document.querySelector('nav'); if (nav) setNavHeight(nav.offsetHeight) }, [])
  const MSG_KEY = 'cc_chat_messages';

  const [records, setRecords] = useState<DingshuluRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRecord, setSelectedRecord] = useState<DingshuluRecord | null>(null);

  // 模块开关
  const [toggles, setToggles] = useState<Record<ModuleId, boolean>>(() => {
    const t: Record<ModuleId, boolean> = {};
    MODULES.forEach(m => t[m.id] = m.defaultOn);
    return t;
  });

  // 报告数据 & 组装上下文
  const [reportJSON, setReportJSON] = useState<Record<string,unknown> | null>(null);
  const [assembledText, setAssembledText] = useState('');
  const [previewHTML, setPreviewHTML] = useState('');
  const [showPreview, setShowPreview] = useState(false);
  const [charCount, setCharCount] = useState(0);

  // Chat
  const [messages, setMessages] = useState<ChatMsg[]>(() => {
    try { return JSON.parse(localStorage.getItem(MSG_KEY) || '[]'); } catch { return []; }
  });
  const [sending, setSending] = useState(false);
  const [chatInput, setChatInput] = useState('');
  const [noteOn, setNoteOn] = useState(false);
  const [cultivatorNote, setCultivatorNote] = useState('');
  const [noteExpanded, setNoteExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => { fetchDingshulu(200).then(setRecords).catch(() => setRecords([])).finally(() => setLoading(false)); }, []);
  useEffect(() => { localStorage.setItem(MSG_KEY, JSON.stringify(messages)); }, [messages]);

  // Load report when record selected
  useEffect(() => {
    if (!selectedRecord) { setReportJSON(null); setAssembledText(''); setPreviewHTML(''); return; }
    fetch(`/api/report/${selectedRecord.stock_code}/data`)
      .then(r => r.ok ? r.json() : null)
      .then(json => { setReportJSON(json); })
      .catch(() => setReportJSON(null));
  }, [selectedRecord]);

  // Re-assemble whenever toggles or report changes
  useEffect(() => {
    if (!reportJSON || !selectedRecord) { setAssembledText(''); setPreviewHTML(''); setCharCount(0); return; }
    assemble();
  }, [reportJSON, toggles]);

  const assemble = useCallback(() => {
    if (!reportJSON || !selectedRecord) return;
    const memory = loadMemory();
    const a0 = (reportJSON.agent0 || {}) as Record<string,unknown>;
    const a3 = (reportJSON.agent3 || {}) as Record<string,unknown>;
    const a2a = (reportJSON.agent2a || {}) as Record<string,unknown>;
    const routing = (reportJSON.routing_decision || {}) as Record<string,unknown>;
    const cf = (G(reportJSON, 'agent1', 'packages', 'core', 'fields') || G(reportJSON, 'agent1', 'clean_financials') || {}) as Record<string,unknown>;
    const sections: string[] = [];

    const add = (title: string, body: string) => {
      if (body.trim()) sections.push(`## ${title}\n${body}`);
    };

    // ── 核心模块 ──
    const ms = (G(a3, 'market_sanity') || {}) as Record<string,unknown>;
    const vs = (G(a3, 'valuation_summary') || G(a3, 'scenario_valuation') || {}) as Record<string,unknown>;
    const gap = (G(a3, 'expectation_gap') || {}) as Record<string,unknown>;
    const conf = (G(a3, 'confidence') || {}) as Record<string,unknown>;
    const ta = (G(a3, 'trade_annotation') || {}) as Record<string,unknown>;
    const kpis = (G(a3, 'monitoring_kpis') || {}) as Record<string,unknown>;
    const triggers = (G(a3, 'risk_triggers') || {}) as Record<string,unknown>;
    const signalAudit = (G(a2a, 'signal_audit') || {}) as Record<string,unknown>;
    const mn = (G(a2a, 'market_narrative') || {}) as Record<string,unknown>;
    const narrative = String(G(mn, 'narrative_summary') || '');
    const scenarios = (Array.isArray(G(a3, 'scenarios')) ? G(a3, 'scenarios') as Array<Record<string,unknown>> : []);

    if (toggles['summary']) add('估值摘要', [
      `- 股票: ${selectedRecord.stock_name} (${selectedRecord.stock_code})`,
      `- 当前市值: ${N(cf?.market_cap_yi || cf?.market_cap_billion)}亿`,
      `- 概率加权市值: ${N(vs?.probability_weighted_mcap_yi || vs?.probability_weighted_mcap_billion)}亿`,
      `- 概率加权涨幅: ${Pct(vs?.probability_weighted_upside_pct)}`,
      `- 不对称比: ${N(vs?.asymmetry_ratio)}`,
      `- 质量标记: ${String(vs?.quality_flag || '?')}`,
    ].join('\n'));

    if (toggles['scenarios'] && scenarios.length > 0) {
      const header = '| 情景 | 概率 | 目标市值 | 涨跌幅 | 因果逻辑 |\n|------|------|----------|--------|----------|';
      const rows = scenarios.map(s => {
        const u = parseFloat(String(s?.upside_pct ?? 0));
        const nar = String(s?.scenario_narrative || '');
        return `| ${String(s?.name || '?')} | ${Pct(s?.probability_pct || N(s?.probability))} | ${N(s?.target_mcap_yi || s?.target_mcap_billion)}亿 | ${u>=0?'+':''}${u.toFixed(1)}% | ${nar} |`;
      }).join('\n');
      add('三情景推演', `${header}\n${rows}`);
    }

    if (toggles['bs']) add('BS检测器', [
      `- 判别: ${String(ms?.bs_level || '?')}`,
      `- EV: ${N(ms?.ev_yi || ms?.ev_billion)}亿 | NOPAT: ${N(ms?.nopat_yi || ms?.nopat_billion)}亿`,
      `- ROIC: ${Pct(ms?.roic_pct)} | WACC: ${Pct(ms?.wacc_simple_pct)}`,
      `- 隐含g: ${Pct(ms?.implied_g_pct)} | 市场溢价: ${Pct(ms?.market_premium_pct)}`,
      `- PE: ${N(ms?.pe_ttm)}x (分位${String(ms?.pe_historical_rank || '?')}) | PB: ${N(ms?.pb)}x`,
    ].join('\n'));

    if (toggles['routing']) {
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

    if (toggles['financial']) {
      const waccParams = (G(ms, 'wacc_params') || {}) as Record<string,unknown>;
      add('财务全景+WACC', [
        '**财务**:',
        `营收TTM ${N(cf?.revenue_ttm_yi || cf?.revenue_ttm_billion)}亿 | 净利TTM ${N(cf?.net_profit_ttm_yi || cf?.net_profit_billion)}亿`,
        `ROIC ${Pct(cf?.roic_pct)} | 毛利率 ${Pct(cf?.gross_margin_pct)} | 净利率 ${Pct(cf?.net_margin_pct)} | ROE ${Pct(cf?.roe_ttm_pct)}`,
        `OCF ${N(cf?.ocf_ttm_yi || cf?.operating_cf_ttm_billion)}亿 | CAPEX ${N(cf?.capex_ttm_yi || cf?.capex_ttm_billion)}亿 | EBITDA ${N(cf?.ebitda_ttm_yi || cf?.ebitda_ttm_billion)}亿`,
        `总资产 ${N(cf?.total_assets_yi || cf?.total_assets_billion)}亿 | 净资产 ${N(cf?.total_equity_yi || cf?.total_equity_billion)}亿`,
        `有息负债 ${N(cf?.interest_bearing_debt_yi || cf?.interest_bearing_debt_billion)}亿 | 净负债 ${N(cf?.net_debt_yi || cf?.net_debt_billion)}亿`,
        '',
        '**WACC**:',
        `Rf ${Pct(waccParams?.rf_pct)} | Beta ${N(waccParams?.beta)} | ERP ${Pct(waccParams?.erp_pct)}`,
        `Re ${Pct(waccParams?.re_pct)} | Rd ${Pct(waccParams?.rd_pct)} | WACC ${Pct(waccParams?.wacc_pct)}`,
      ].join('\n'));
    }

    if (toggles['gap']) add('预期差', `- 等级: ${String(gap?.level || '?')}\n- 说明: ${String(gap?.note || '—')}`);

    if (toggles['confidence']) {
      const dims = (G(conf, 'dimensions') || {}) as Record<string, Record<string,unknown>>;
      const rows = Object.entries(dims).map(([, d]) => `- ${String(d?.label || '?')}: ${String(d?.score || '?')}/10 — ${String(d?.note || '')}`).join('\n');
      add(`置信度: ${confOverall(conf)}/10 (${String(conf?.overall_label || '?')})`, rows);
    }

    if (toggles['trade']) add(`交易标注: ${String(ta?.tier || '?')} (${String(ta?.total_score || '?')})`, [
      `- 建议: ${String(ta?.suggested_action || ta?.tier_note || '—')}`,
      (G(ta, 'alignment_signals') as string[] || []).map((s: string) => `- ${s}`).join('\n'),
    ].join('\n'));

    if (toggles['signal'] && G(signalAudit, 'step2b_match')) {
      const matches = (G(signalAudit, 'step2b_match') as Array<Record<string,unknown>> || []).map(m =>
        `- **${String(m?.match)}** ${String(m?.signal)} (${String(m?.source_level)}) — ${String(m?.basis)}`
      ).join('\n');
      add(`信号审计: 评分${String(G(signalAudit, 'step2d_score') || '?')}`, matches);
    }

    if (toggles['kpi']) {
      const cats = ['financial_verification_kpis', 'event_milestone_kpis', 'competition_signal_kpis', 'risk_trigger_kpis'] as const;
      const labels = ['财务验证', '事件里程碑', '竞争信号', '风险触发'];
      cats.forEach((cat, ci) => {
        const items = (G(kpis, cat) || []) as Array<Record<string,unknown>>;
        if (!items.length) return;
        const lines = items.map((k: Record<string,unknown>) => {
          const name = String(k.name || k.kpi || k.milestone || k.signal || k.trigger || '?');
          const target = String(k.target || k.threshold || k.expected_timing || '—');
          const bl = String(k.baseline || k.current_state || '');
          return `- **${name}**: ${target}${bl && bl !== '—' ? ` (基线: ${bl})` : ''}`;
        }).join('\n');
        add(`KPI \xB7 ${labels[ci]}`, lines);
      });
    }

    if (toggles['triggers']) add('风险触发器', [
      `- 牛触发: ${String(triggers?.bull_trigger || '—')}`,
      `- 熊触发: ${String(triggers?.bear_trigger || '—')}`,
    ].join('\n'));

    if (toggles['narrative']) {
      const ep = (G(a2a, 'event_pricing') || {}) as Record<string,unknown>;
      const epr = (G(ep, 'event_profile') || {}) as Record<string,unknown>;
      const pa = (G(ep, 'pricing_assessment') || {}) as Record<string,unknown>;
      const fwd = (G(a2a, 'forward_to_routing') || {}) as Record<string,unknown>;
      const anchor = String(G(mn, 'primary_anchor') || '?');
      const shape = String(epr?.distribution_shape || '?');
      const bias = String(fwd?.pricing_bias || 'uncertain');
      const pricedIn = String(pa?.overall_priced_in || '?');
      const pricedEst = String(pa?.priced_in_estimate || '');
      const timing = String(epr?.timing_certainty || '?');
      const binary = String(epr?.outcome_binaryness || '?');
      const precedent = String(epr?.precedent_richness || '?');
      const lines = [
        `- ★ 主锚: **${anchor}** — ${ANCHOR_FOCUS[anchor] || '关注锚定对应指标'}`,
        narrative ? `- 锚叙事: ${narrative.slice(0, 300)}` : '',
        `- 事件分布: ${shape}（${SHAPE_EXPLAIN[shape] || '分布形态反映市场共识度与不确定性'}）`,
        `- 定价偏向: ${bias} — ${BIAS_EXPLAIN[bias] || '需结合情景推演判断'}`,
        pricedIn !== '?' ? `- 市场计价: ${pricedIn}${pricedEst ? ' / ' + pricedEst : ''}${pa?.residual_catalyst ? ' | 剩余催化: ' + String(pa.residual_catalyst) : ''}` : '',
        `- 3D光谱: 时点确定性${timing}/10 | 结果二元性${binary}/10 | 先例丰富度${precedent}/10`,
        G(mn, 'anchor_conflict') ? `- ⚠️ 锚冲突: ${String(G(mn, 'anchor_conflict'))}` : '',
        G(mn, 'sotp_triggered') ? '- ⚠️ SOTP已触发 — 需分部估值，不同业务不能混用一个锚' : '',
      ].filter(Boolean);
      if (lines.length) add('叙事诊断（Agent-2a V6）', lines.join('\n'));
    }

    // ── Agent0 模块 ──
    const a0Fields: [ModuleId, string, number][] = [
      ['a0_theme', '投资主题', 2500], ['a0_deduction', '事件推演', 1500], ['a0_reasoning', '推理依据', 1500],
      ['a0_adversarial', '对抗思考', 1000], ['a0_knowledge', '知识补充', 1000], ['a0_research', '行业研究', 1500],
    ];
    const a0Map: Record<string,string> = { a0_theme: 'investment_theme', a0_deduction: 'event_deduction', a0_reasoning: 'preliminary_reasoning', a0_adversarial: 'adversarial_thinking', a0_knowledge: 'knowledge_supplement', a0_research: 'industry_expert_research' };
    a0Fields.forEach(([id, label, _max]) => {
      if (!toggles[id]) return;
      const text = String(G(a0, a0Map[id]) || '');
      if (!text || text === '—') return;
      add(`A0 \xB7 ${label}`, text);
    });

    // ── 匹配模块 ──
    const kw = [selectedRecord.stock_name, selectedRecord.stock_code].filter(Boolean) as string[];

    if (toggles['lingguang']) {
      const lgs = memory.lingguangs
        .map(lg => ({ ...lg, score: textScore(lg.content + lg.title, kw) }))
        .sort((a, b) => b.score - a.score);
      if (lgs.length > 0) add('灵光匹配', lgs.map(lg => `- **${lg.title}**: ${lg.content}`).join('\n'));
    }

    if (toggles['cases']) {
      const cases = memory.cases.map(c => {
        const ct = [c.sector, c.logic, c.primaryDriver, ...(c.tags || [])].filter(Boolean).join(' ');
        let s = 0;
        for (const k of kw) if (ct.toLowerCase().includes(k.toLowerCase())) s += 2;
        return { ...c, score: s };
      }).sort((a, b) => b.score - a.score);
      if (cases.length > 0) {
        const table = '| # | 案例 | 代码 | 回报 | 行业 | 驱动 |\n|---|------|------|------|------|------|\n'
          + cases.map((c, i) => `| ${i + 1} | ${c.stockName} | ${c.stockCode} | ${c.gainMultiple}x | ${c.sector || '—'} | ${c.primaryDriver || '—'} |`).join('\n');
        add('案例匹配', table);
      }
    }

    // 修者注
    if (noteOn && cultivatorNote.trim()) {
      sections.push(`## 修者注\n${cultivatorNote.trim()}`);
    }
    const text = sections.join('\n\n---\n\n');
    setAssembledText(text);
    setPreviewHTML(renderMarkdown(text));
    setCharCount(text.length);
  }, [reportJSON, toggles, selectedRecord, noteOn, cultivatorNote]);

  // ── Chat ──
  const sendMessage = (text: string) => {
    if (!text.trim()) return;
    const now = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    const idx = messages.length + 1;
    setMessages(prev => [...prev, { role: 'user', content: text, time: now }, { role: 'assistant', content: '', time: now }]);
    setSending(true);

    fetch('/api/avatar/cc/send', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: text, max_turns: 5 }),
    }).then(async resp => {
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body?.getReader();
      if (!reader) throw new Error('No stream');
      const dec = new TextDecoder(); let full = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of dec.decode(value, { stream: true }).split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const m = JSON.parse(line.slice(6));
            if (m.type === 'chunk') full += m.text;
          } catch {}
        }
        setMessages(prev => { const n = [...prev]; if (n[idx]) n[idx] = { ...n[idx], content: full }; return n; });
      }
    }).catch(err => {
      setMessages(prev => { const n = [...prev]; if (n[idx]) n[idx] = { ...n[idx], content: `**错误**: ${err.message}` }; return n; });
    }).finally(() => setSending(false));
  };

  const handleSend = () => {
    if (!assembledText) return;
    const systemPrompt = `你是长流水宗门的"身外化身"——一位专精十倍股猎杀的 AI 投资决策 Agent。

## 核心信念
1. 十倍股 = 产业趋势 x 企业生命周期。小市值+大产业+强卡位
2. 风控铁律：单票<=20%，破逻辑止损，质押>50%不碰，两季连滑重评
3. 抓主要矛盾：每只股票的核心逻辑能一句话说清

## 输出格式
# 投资决策报告
## 推演结论: **{通过/有条件通过/否决}** (Conviction: {0-100})
## 核心逻辑（<=3条）
## 产业位置
## 财务快照
## 估值锚定
## 催化剂时间表
## 风险清单
## 建议

---
请基于上述上下文严格执行六步框架，用中文输出完整决策报告。`;
    sendMessage(`${systemPrompt}\n\n---\n\n# 标的分析上下文\n\n${assembledText}`);
  };

  const handleChatSend = () => {
    if (!chatInput.trim()) return;
    sendMessage(chatInput);
    setChatInput('');
  };

  // ── UI ──
  const a0ToggleIds = MODULES.filter(m => m.category === 'agent0').map(m => m.id);
  const a0AllOn = a0ToggleIds.every(id => toggles[id]);
  const toggleA0 = () => {
    setToggles(prev => {
      const next = { ...prev };
      const on = !a0AllOn;
      a0ToggleIds.forEach(id => next[id] = on);
      return next;
    });
  };

  return (
    <>
    <style>{GLOBAL_CSS}</style>
    <div style={{ height: `calc(100vh - ${navHeight}px)`, background: BG, color: TEXT, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Toolbar — 身外化身功能按钮 */}
      <div style={{ flexShrink: 0, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '10px 48px', background: 'rgba(5,4,1,.6)', borderBottom: `1px solid ${BORDER}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ width: '6px', height: '6px', background: '#ADFF00', boxShadow: '0 0 8px rgba(173,255,0,0.5)', animation: 'pulse 2s ease-in-out infinite', display: 'inline-block' }} />
          <span style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: '18px', color: '#ADFF00', letterSpacing: '0.06em' }}>身外化身</span>
          <span style={{ fontFamily: MONO, fontSize: '12px', color: MUTED }}>道胎 · CC 上下文模式</span>
        </div>
        <button onClick={() => navigate('/avatar')} className="cc-btn" style={{ color: '#ADFF00', borderColor: 'rgba(173,255,0,.2)' }}>← 器灵直连</button>
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: mobile ? 'column' : 'row', overflow: 'hidden' }}>
        {/* ── LEFT ── */}
        <div style={{ width: mobile ? '100%' : '310px', minWidth: mobile ? 'auto' : '310px', borderRight: `1px solid ${BORDER}`, display: 'flex', flexDirection: 'column', background: BG, overflow: 'hidden' }}>
          <div style={{ padding: '16px 18px', borderBottom: `1px solid ${BORDER}`, flexShrink: 0, background: SURFACE }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <span style={{ color: CC, fontFamily: 'serif', fontSize: 12 }}>◇</span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: MUTED, letterSpacing: '0.15em' }}>定 数 录</span>
              <span style={{ flex: 1 }} />
              <span style={{ fontFamily: MONO, fontSize: 11, color: DIM }}>{records.length}<span style={{ color: MUTED }}> 录</span></span>
            </div>
            <div style={{ fontFamily: FONT, fontSize: 11, color: DIM }}>择录 → 组符 → 发令</div>
          </div>
          <div className="cc-scroll" style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '4px' }}>
            {loading ? <div style={{ padding: 40, textAlign: 'center', color: DIM }}>翻阅定数录...</div> :
              records.map(r => <RecordCard key={r.id} record={r} selected={r.id === selectedRecord?.id} onClick={() => { setSelectedRecord(r); }} />)}
          </div>
        </div>

        {/* ── RIGHT ── */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
          {/* ── 修者注面板 ── */}
          {selectedRecord && <div onClick={()=>setNoteExpanded(!noteExpanded)} style={{ cursor:'pointer',padding:'12px 20px',borderBottom:`1px solid ${BORDER}`,background:noteOn?`linear-gradient(90deg,${CC}18 0%,${CC}06 50%,transparent 100%)`:'rgba(255,255,255,.01)',transition:'all .4s',position:'relative',overflow:'hidden' }}>
            {/* 阵纹 + 符文瀑布 */}
            <div className="note-array-bg" style={{ backgroundImage:noteOn?`url("data:image/svg+xml,%3Csvg width='40' height='40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M20 2L38 20L20 38L2 20Z' fill='none' stroke='${CC.replace('#','%23')}' stroke-width='0.3'/%3E%3C/svg%3E")`:'none',opacity:noteOn?.25:.06 }}/>
            <div style={{ position:'absolute',inset:0,pointerEvents:'none',opacity:noteOn?.15:.04,transition:'opacity .4s',background:`radial-gradient(ellipse at 15% 50%,${CC}40 0%,transparent 70%)` }}/>
            <div className="note-runes" />

            <div style={{ display:'flex',alignItems:'center',gap:12,position:'relative',zIndex:1 }}>
              <span style={{ fontFamily:'serif',fontSize:22,color:noteOn?CC:'#555',transition:'all .4s',textShadow:noteOn?`0 0 16px ${CC}60`:`0 0 4px ${CC}12`,filter:noteOn?'brightness(1.3)':'grayscale(0.4)' }}>◇</span>
              <span style={{ fontFamily:MONO,fontSize:15,fontWeight:700,color:noteOn?CC:'#BBB',letterSpacing:'0.16em',textShadow:noteOn?`0 0 8px ${CC}30`:'' ,transition:'all .3s' }}>修 者 注</span>
              <button onClick={e=>{e.stopPropagation();setNoteOn(!noteOn);}} style={{ fontFamily:MONO,fontSize:13,fontWeight:700,padding:'5px 16px',borderRadius:6,border:`2px solid ${noteOn?CC:'rgba(200,160,100,.25)'}`,background:noteOn?`${CC}16`:'rgba(100,70,40,.1)',color:noteOn?CC:'#AAA',cursor:'pointer',letterSpacing:'0.1em',textShadow:noteOn?`0 0 12px ${CC}50`:'' ,boxShadow:noteOn?`0 0 16px ${CC}20,inset 0 0 8px ${CC}10`:`0 0 4px rgba(200,160,100,.08)`,transition:'all .3s',animation:noteOn?'pulse 2s ease-in-out infinite':'none' }}
                onMouseEnter={e=>{if(!noteOn){e.currentTarget.style.borderColor=CC+'80';e.currentTarget.style.color=CC;}}}
                onMouseLeave={e=>{if(!noteOn){e.currentTarget.style.borderColor='rgba(200,160,100,.25)';e.currentTarget.style.color='#AAA';}}}>{noteOn?'已采纳':'采纳'}</button>
              <span style={{ flex:1 }}/>
              <span style={{ fontFamily:MONO,fontSize:11,color:noteOn?'#DDD':'#888' }}>{cultivatorNote?`${cultivatorNote.length}字`:'空'}</span>
              <span style={{ fontFamily:MONO,fontSize:10,color:noteOn?CC:'#666',transition:'transform .3s',transform:noteExpanded?'rotate(180deg)':'rotate(0deg)' }}>▼</span>
            </div>
            {noteExpanded&&<div style={{ position:'relative',zIndex:1,marginTop:12 }} onClick={e=>e.stopPropagation()}><textarea value={cultivatorNote} onChange={e=>setCultivatorNote(e.target.value)} rows={6} placeholder="独有资讯、另类数据、个人见解…" style={{ width:'100%',background:'rgba(0,0,0,.3)',border:`1px solid ${noteOn?`${CC}30`:'#2a1f10'}`,color:noteOn?TEXT:'#6b5e4f',fontFamily:MONO,fontSize:14,padding:'12px 16px',outline:'none',borderRadius:6,resize:'vertical',lineHeight:1.8,transition:'all .3s' }}
            onFocus={e=>{e.currentTarget.style.borderColor=`${CC}60`;e.currentTarget.style.boxShadow=`0 0 16px ${CC}20`;}}
            onBlur={e=>{e.currentTarget.style.borderColor=`${noteOn?`${CC}30`:'#2a1f10'}`;e.currentTarget.style.boxShadow='none';}}/></div>}
          </div>}

          {/* ── 模块选择栏 ── */}
          {selectedRecord && (
            <div style={{ flexShrink: 0, borderBottom: `1px solid ${BORDER}`, background: SURFACE, padding: '10px 20px' }}>
              {/* 核心字段 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
                <span style={{ fontFamily: MONO, fontSize: 10, color: DIM, marginRight: 4 }}>核心</span>
                {MODULES.filter(m => m.category === 'core').map(m => (
                  <Toggle key={m.id} label={m.label} on={toggles[m.id]} onChange={() => setToggles(prev => ({ ...prev, [m.id]: !prev[m.id] }))} />
                ))}
              </div>
              {/* Agent0 字段 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
                <span style={{ fontFamily: MONO, fontSize: 10, color: DIM, marginRight: 4 }}>A0</span>
                <Toggle label={a0AllOn ? '全部ON' : '全部OFF'} on={a0AllOn} onChange={toggleA0} />
                {MODULES.filter(m => m.category === 'agent0').map(m => (
                  <Toggle key={m.id} label={m.label} on={toggles[m.id]} onChange={() => setToggles(prev => ({ ...prev, [m.id]: !prev[m.id] }))} />
                ))}
              </div>
              {/* 匹配 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: MONO, fontSize: 10, color: DIM, marginRight: 4 }}>匹配</span>
                {MODULES.filter(m => m.category === 'match').map(m => (
                  <Toggle key={m.id} label={m.label} on={toggles[m.id]} onChange={() => setToggles(prev => ({ ...prev, [m.id]: !prev[m.id] }))} />
                ))}
                <span style={{ flex: 1 }} />
                <span style={{ fontFamily: MONO, fontSize: 11, color: CC }}>{charCount.toLocaleString()}字</span>
                <button onClick={() => setShowPreview(!showPreview)} className="cc-btn" style={{ fontSize: 11, padding: '5px 14px', color: showPreview ? CC : MUTED }}>
                  {showPreview ? '收符' : '展符'}
                </button>
                <button onClick={() => { navigator.clipboard.writeText(assembledText).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); }).catch(() => {}); }} className="cc-btn" style={{ fontSize: 11, padding: '5px 14px', color: copied ? CC : MUTED }}>
                  {copied ? '已誊抄' : '誊抄'}
                </button>
                <button onClick={handleSend} disabled={sending || !assembledText} className="cc-btn primary" style={{ opacity: (sending || !assembledText) ? 0.4 : 1 }}>
                  {sending ? '推演中...' : '◇ 发符令'}
                </button>
              </div>
            </div>
          )}

          {/* ── 预览 / 对话 ── */}
          {selectedRecord && showPreview ? (
            <div className="cc-scroll cc-md" style={{ flex: 1, overflowY: 'auto', padding: '20px 28px', background: BG }}
              dangerouslySetInnerHTML={{ __html: previewHTML || '<p style="color:#5c4a32">正在组装符箓...</p>' }} />
          ) : (
            <>
              <div ref={chatContainerRef} className="cc-scroll" style={{ flex: 1, overflowY: 'auto', padding: messages.length > 0 ? '20px 28px' : '28px' }}>
                {messages.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '80px 20px' }}>
                    <div style={{ fontSize: 48, opacity: 0.03, color: CC, fontFamily: 'serif', marginBottom: 20, letterSpacing: '0.3em' }}>道 胎 等 待</div>
                    <p style={{ fontFamily: FONT, fontSize: 15, color: DIM, lineHeight: 2.2 }}>
                      {selectedRecord ? `符箓已备 · ${charCount.toLocaleString()} 字\n勾选上方模块 → 展符预览 → 发符令唤醒道胎` : '择录 → 组符 → 发令唤道胎\n元神不灭 · 会话永续'}
                    </p>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {messages.map((m, i) => (
                      <div key={i} className={m.role === 'user' ? 'cc-msg-user' : 'cc-msg-cc'}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <span style={{ fontFamily: MONO, fontSize: 10, color: m.role === 'user' ? MUTED : CC, letterSpacing: '0.12em' }}>{m.role === 'user' ? '— 修者 —' : '— 道胎 —'}</span>
                          <span style={{ flex: 1 }} />
                          <span style={{ fontFamily: MONO, fontSize: 10, color: DIM }}>{m.time}</span>
                        </div>
                        <div style={{ fontFamily: FONT, fontSize: 14, color: m.role === 'user' ? '#a89a84' : '#d4c8b8', lineHeight: 1.85, whiteSpace: 'pre-wrap' }}>
                          {m.content || (m.role === 'assistant' && <span style={{ color: DIM }}>道胎冥思中...</span>)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* 发令台 */}
              <div style={{ flexShrink: 0, padding: '10px 20px', borderTop: `1px solid ${BORDER}`, display: 'flex', gap: 10, alignItems: 'center', background: SURFACE }}>
                <span style={{ color: CC, fontFamily: 'serif', fontSize: 14, opacity: selectedRecord ? 0.5 : 0.15 }}>◇</span>
                <input value={chatInput} onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleChatSend(); } }}
                  className="cc-input" placeholder={selectedRecord ? '续写符令...' : '先择录方可言道'} disabled={sending || !selectedRecord} />
                <button onClick={handleChatSend} disabled={sending || !chatInput.trim()} className="cc-btn primary" style={{ opacity: (!chatInput.trim() || sending) ? 0.35 : 1, padding: '9px 20px' }}>敕令</button>
              </div>
            </>
          )}

          {/* 状态栏 */}
          <div style={{ flexShrink: 0, padding: '7px 28px', background: BG, borderTop: `1px solid ${BORDER}`, display: 'flex', alignItems: 'center', gap: 10, fontFamily: MONO, fontSize: 11 }}>
            <span style={{ color: CC, fontSize: 10 }}>◆</span>
            {selectedRecord ? (
              <span style={{ color: AU }}>{selectedRecord.stock_name} ({selectedRecord.stock_code}) · {charCount.toLocaleString()}字</span>
            ) : <span style={{ color: DIM }}>待择录</span>}
            <span style={{ flex: 1 }} />
            {messages.length > 0 && (
              <span onClick={() => { setMessages([]); localStorage.removeItem(MSG_KEY); }} style={{ color: DIM, cursor: 'pointer', fontSize: 10, border: `1px solid ${BORDER}`, padding: '2px 8px', borderRadius: 4, marginRight: 8 }}
                onMouseEnter={e => { e.currentTarget.style.color = '#FF5C00'; e.currentTarget.style.borderColor = '#FF5C0040'; }}
                onMouseLeave={e => { e.currentTarget.style.color = DIM; e.currentTarget.style.borderColor = BORDER; }}>清空</span>
            )}
            <span style={{ color: DIM, fontSize: 10 }}>75afed56</span>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}

function confOverall(conf: Record<string,unknown>): string {
  return String(G(conf, 'overall_score') || 5);
}
