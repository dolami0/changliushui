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
  'fairly_valued': '当前市值与内在价值基本吱合',
  'overvalued': '模型认为当前市值已高于内在价值（警惕追高）',
  'uncertain': '方向不明确，需结合其他信号综合判断',
};
