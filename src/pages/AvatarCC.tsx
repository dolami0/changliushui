import { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { fetchDingshulu, fetchReportFromCoze, type DingshuluRecord } from '../services/cozeApi';
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
  { id: 'routing',        label: '估值路由',     category: 'core',   defaultOn: true },
  { id: 'financial',      label: '财务全景+WACC', category: 'core',  defaultOn: true },
  { id: 'gap',            label: '预期差',       category: 'core',   defaultOn: true },
  { id: 'confidence',     label: '置信度评分',   category: 'core',   defaultOn: true },
  { id: 'trade',          label: '交易标注',     category: 'core',   defaultOn: true },
  { id: 'signal',         label: '信号审计',     category: 'core',   defaultOn: true },
  { id: 'kpi',            label: '监测KPI',      category: 'core',   defaultOn: true },
  { id: 'triggers',       label: '风险触发器',   category: 'core',   defaultOn: true },
  { id: 'baseline',       label: '基线分析',     category: 'core',   defaultOn: true },
  { id: 'narrative',      label: '叙事诊断',     category: 'core',   defaultOn: true },
  // Agent0 预路由 — 可整组开关
  { id: 'a0_theme',       label: '投资主题',     category: 'agent0', defaultOn: true },
  { id: 'a0_deduction',   label: '事件推演',     category: 'agent0', defaultOn: true },
  { id: 'a0_reasoning',   label: '推理依据',     category: 'agent0', defaultOn: true },
  { id: 'a0_adversarial', label: '对抗思考',     category: 'agent0', defaultOn: true },
  { id: 'a0_knowledge',   label: '知识补充',     category: 'agent0', defaultOn: true },
  { id: 'a0_research',    label: '行业研究',     category: 'agent0', defaultOn: true },
  { id: 'a0_raw_event',   label: '原始事件',     category: 'agent0', defaultOn: true },
  { id: 'a0_future',      label: '前瞻',         category: 'agent0', defaultOn: true },
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
