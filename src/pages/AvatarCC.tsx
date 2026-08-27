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
