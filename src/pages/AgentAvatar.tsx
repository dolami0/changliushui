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
