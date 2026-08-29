import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Copy, ChevronDown, ChevronUp, Settings, Check, Sparkles, BookOpen } from 'lucide-react'
import { AvatarContextSheet, CONTEXT_MODULES } from './AvatarContextSheet'
import { MobileCard } from '@/mobile/components/MobileCard'
import { MobileBadge } from '@/mobile/components/MobileBadge'
import { MobileLoading } from '@/mobile/components/MobileLoading'
import { MobileEmpty } from '@/mobile/components/MobileEmpty'
import { useMobileData } from '@/mobile/hooks/useMobileData'
import {
  fetchDingshulu, fetchReportFromCoze, fetchLingguang, fetchCases,
  type DingshuluRecord, type LingguangItem, type CaseItem, type CozeRecord,
} from '@/services/cozeApi'
import { loadMemory, callAgentAI } from '@/services/agentMemory'
import type { DecisionContext } from '@/services/agentMemory'
import { renderMarkdown } from '@/lib/utils'

interface ChatMessage { role: 'user' | 'assistant' | 'system'; content: string; id: number }

function renderSmart(d: unknown): string {
  if (!d) return ''
  if (typeof d === 'string') {
    if (d.trim().startsWith('<')) return d
    try { return renderSmart(JSON.parse(d)) } catch { return renderMarkdown(d) }
  }
  if (Array.isArray(d)) {
    const items = d.map((v) => typeof v === 'object' ? renderSmart(v) : `<div class="rp-item">${String(v)}</div>`).filter(Boolean).join('')
    return items ? `<div>${items}</div>` : ''
  }
  if (typeof d === 'object') return renderObj(d as Record<string, unknown>)
  return String(d)
}

function humanLabel(k: string): string {
  const m: Record<string, string> = {
    actualReturnPct:'实际涨幅', gainMultiple:'回报倍数', sector:'行业', logic:'投资逻辑',
    catalyst:'催化剂', endState:'终态', roicImprovement:'ROIC改善', peExpansion:'PE扩张',
    maxDrawdownPct:'最大回撤', startDate:'入场日期', peakDate:'峰值日期',
    primaryDriver:'主驱动', returnType:'回报类型', title:'标题', content:'内容',
    tags:'标签', source:'来源', confidence:'置信度', createdAt:'创建时间',
    prob_weighted_upside_pct:'概率加权upside', asymmetry_ratio:'不对称比',
    base_upside_pct:'基准涨幅', bull_upside_pct:'乐观涨幅', bear_upside_pct:'悲观涨幅',
    confidence_score:'置信度', quality_flag:'质量评级', primary_model:'路由模型',
    stock_code:'代码', stock_name:'名称', trade_tier:'交易等级', event_date:'事件日期',
  }
  return m[k] || k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function isText(s: string) { return s.length > 50 || s.includes('\n') || s.includes('。') || s.includes('，') }

function renderObj(obj: Record<string, unknown>): string {
  const texts: string[] = []
  const rows: string[] = []
  for (const [k, v] of Object.entries(obj)) {
    if (v === null || v === undefined || v === '') continue
    if (typeof v === 'string' && isText(v)) {
      texts.push(`<div class="rp-text">${renderMarkdown(v)}</div>`)
    } else if (typeof v === 'number') {
      const s = Number.isInteger(v) ? String(v) : v.toFixed(2)
      rows.push(`<tr><td>${humanLabel(k)}</td><td><b>${s}</b></td></tr>`)
    } else if (typeof v === 'string') {
      rows.push(`<tr><td>${humanLabel(k)}</td><td>${v}</td></tr>`)
    } else if (Array.isArray(v) && v.length > 0) {
      texts.push(renderSmart(v))
    } else if (typeof v === 'object' && v !== null) {
      texts.push(renderObj(v as Record<string, unknown>))
    }
  }
  const out: string[] = []
  if (rows.length > 0) out.push(`<table class="rp-table">${rows.join('')}</table>`)
  out.push(...texts)
  return out.join('')
}

function RecordList({ records, loading, error, refresh, onSelect }: {
  records: DingshuluRecord[]; loading: boolean; error: string | null; refresh: () => void; onSelect: (r: DingshuluRecord) => void
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between h-10 px-4 border-b border-[#2A2A2A] flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tracking-wider">身外化身</span>
          <span className="text-[10px] text-[#C88D3A] border border-[#C88D3A]/20 bg-[#C88D3A]/[0.04] px-1.5 py-0.5 rounded-sm">试用模式</span>
        </div>
        <span className="text-xs text-[#555]">{records.length} 份</span>
      </div>
      <div className="px-4 py-2.5 bg-[#ADFF00]/[0.02] border-b border-[#2A2A2A] text-xs text-[#888] leading-relaxed flex-shrink-0">
        <p>选择定数录后查看完整报告数据，使用<b className="text-[#AAA]">展符</b>组装上下文 prompt，<b className="text-[#AAA]">复制</b>后黏贴给投资决策 Agent，或在网页端配置 API Key 后直接发令调用。</p>
      </div>
      {loading && <MobileLoading />}
      {error && <div className="flex flex-col items-center gap-2 py-16"><span className="text-sm text-red-400">{error}</span><button onClick={refresh} className="px-4 py-1 border border-[#2A2A2A] text-xs text-[#888]">重试</button></div>}
      {!loading && !records.length && <MobileEmpty message="暂无定数录" />}
      {!loading && (
        <div className="flex-1 overflow-y-auto">
          <div className="flex flex-col gap-px">
            {records.map((r) => {
              const up = parseFloat(r.prob_weighted_upside_pct || '0')
              return (
                <button key={r.id} onClick={() => onSelect(r)} className="w-full text-left bg-white/[0.02] border-b border-[#1A1A1A] px-4 py-3 active:bg-white/[0.04] transition-colors">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2 min-w-0"><span className="text-sm font-semibold text-[#F2F4F3] truncate">{r.stock_name || '—'}</span><span className="text-xs text-[#888] flex-shrink-0">{r.stock_code}</span></div>
                    {r.trade_tier && <MobileBadge variant={up > 0 ? 'green' : 'muted'} className="flex-shrink-0">{r.trade_tier}</MobileBadge>}
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3"><span className={`text-sm font-bold ${up > 0 ? 'text-[#ADFF00]' : 'text-[#888]'}`}>{up > 0 ? '+' : ''}{up.toFixed(1)}%</span><span className="text-xs text-[#555]">不对称比 {parseFloat(r.asymmetry_ratio || '0').toFixed(2)}x</span></div>
                    <span className="text-xs text-[#555]">{r.quality_flag || ''}</span>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

type SubView = 'report' | 'lingguang' | 'cases'

function AvatarDetail({ record, onBack }: { record: DingshuluRecord; onBack: () => void }) {
  const [contextOpen, setContextOpen] = useState(false)
  const [enabledModules, setEnabledModules] = useState<Set<string>>(() => new Set(CONTEXT_MODULES.map((m) => m.id)))
  const [showPrompt, setShowPrompt] = useState(false)
  const [assembledPrompt, setAssembledPrompt] = useState('')
  const [copied, setCopied] = useState(false)
  const [report, setReport] = useState<Record<string, unknown> | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [subView, setSubView] = useState<SubView>('report')
  const msgEndRef = useRef<HTMLDivElement>(null)
  const memory = useRef(loadMemory())

  useEffect(() => {
    setReportLoading(true)
    fetchReportFromCoze(record.stock_code || record.id).then(setReport).finally(() => setReportLoading(false))
  }, [record])
  useEffect(() => { msgEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const toggleModule = useCallback((id: string) => {
    setEnabledModules((prev) => {
      const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next
    })
  }, [])

  const handleShowPrompt = async () => {
    if (!showPrompt) {
      const parts: string[] = []
      parts.push(`【定数录】${record.stock_name}(${record.stock_code})`)
      parts.push(`upside: ${record.prob_weighted_upside_pct || '—'}% | 不对称比: ${record.asymmetry_ratio || '—'} | 路由: ${record.primary_model || '—'}`)
      parts.push('')
      if (report) {
        const labels: Record<string, string> = { agent1: 'Agent-1', agent2: 'Agent-2', agent3: 'Agent-3', agent2a: 'Agent-2a', routing_decision: '路由判决', baseline_report: '基线分析' }
        for (const [k, label] of Object.entries(labels)) {
          const modId = k.startsWith('routing') ? 'agent2' : k === 'baseline_report' ? 'baseline' : k; if (!enabledModules.has(modId)) continue
          const d = report[k]; if (!d) continue
          parts.push(`--- ${label} ---`); parts.push(typeof d === 'string' ? d.slice(0, 3000) : JSON.stringify(d, null, 2).slice(0, 3000)); parts.push('')
        }
        const a0 = report.agent0 as Record<string, unknown> | undefined
        if (a0) {
          const a0Map: Record<string, { key: string; label: string }> = {
            a0_theme: { key: 'investment_theme', label: '投资主题' },
            a0_deduction: { key: 'event_deduction', label: '事件推演' },
            a0_reasoning: { key: 'preliminary_reasoning', label: '推理依据' },
            a0_adversarial: { key: 'adversarial_thinking', label: '对抗思考' },
            a0_knowledge: { key: 'knowledge_supplement', label: '知识补充' },
            a0_research: { key: 'industry_expert_research', label: '行业研究' },
            a0_raw_event: { key: 'raw_event_text', label: '原始事件' },
            a0_future: { key: 'future', label: '前瞻' },
          }
          for (const [modId, { key, label }] of Object.entries(a0Map)) {
            if (!enabledModules.has(modId)) continue
            const d = a0[key]; if (!d) continue
            parts.push(`--- A0 · ${label} ---`); parts.push(typeof d === 'string' ? d.slice(0, 3000) : JSON.stringify(d, null, 2).slice(0, 3000)); parts.push('')
          }
        }
      }
      setAssembledPrompt(parts.join('\n'))
    }
    setShowPrompt(!showPrompt)
  }

  const handleCopy = async () => {
    if (!assembledPrompt) return
    try { await navigator.clipboard.writeText(assembledPrompt); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* */ }
  }

  const handleSend = async () => {
    if (!input.trim() || streaming) return
    const question = input.trim(); setInput('')
    setMessages((p) => [...p, { role: 'user', content: question, id: Date.now() }])
    setStreaming(true)
    try {
      let prompt = assembledPrompt
      if (!prompt && report) {
        prompt = `【定数录】${record.stock_name}(${record.stock_code})\n\n` + ['agent1','agent2','agent3'].map((k) => report[k] ? (typeof report[k] === 'string' ? (report[k] as string).slice(0, 2000) : JSON.stringify(report[k]).slice(0, 2000)) : '').filter(Boolean).join('\n\n')
        const a0Fb = report.agent0 as Record<string, unknown> | undefined
        if (a0Fb) { const a0K = ['investment_theme','event_deduction','preliminary_reasoning','adversarial_thinking','knowledge_supplement','industry_expert_research','raw_event_text','future']; const a0T = a0K.map(k => a0Fb[k] ? `--- A0 · ${k} ---\n${String(a0Fb[k]).slice(0, 2000)}` : '').filter(Boolean).join('\n\n'); if (a0T) prompt += '\n\n' + a0T }
        if (report.baseline_report) prompt += '\n\n--- 基线分析 ---\n' + String(report.baseline_report).slice(0, 2000)
        setAssembledPrompt(prompt)
      }
      const ctx: DecisionContext = { record: record as unknown as CozeRecord, matchedLingguangs: [], matchedCases: [], systemPrompt: memory.current.config.systemPrompt, workflowSteps: [], assembledPrompt: prompt + '\n\n【用户问题】\n' + question }
      const aidId = Date.now() + 1; setMessages((p) => [...p, { role: 'assistant', content: '', id: aidId }])
      await callAgentAI(ctx, (chunk) => { setMessages((p) => p.map((m) => (m.id === aidId ? { ...m, content: m.content + chunk } : m))) })
    } catch (e) {
      setMessages((p) => [...p, { role: 'system', content: `错误: ${e instanceof Error ? e.message : '调用失败'}`, id: Date.now() }])
    } finally { setStreaming(false) }
  }

  const upside = parseFloat(record.prob_weighted_upside_pct || '0')

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center h-10 px-3 border-b border-[#2A2A2A] flex-shrink-0 gap-2">
        <button onClick={onBack} className="text-sm text-[#888] active:text-[#ADFF00] flex-shrink-0">← 返回</button>
        <span className="text-sm font-semibold text-[#F2F4F3] truncate flex-1">{record.stock_name || record.stock_code}</span>
        <button onClick={() => setContextOpen(true)} className="flex items-center gap-1 px-2 py-1 border border-[#2A2A2A] rounded-sm text-xs text-[#888] active:border-[#ADFF00]/40 active:text-[#ADFF00] flex-shrink-0"><Settings size={13} />{enabledModules.size}</button>
      </div>
      <div className="flex border-b border-[#2A2A2A] flex-shrink-0">
        {([
          { k: 'report' as const, label: '报告', icon: <BookOpen size={12} /> },
          { k: 'lingguang' as const, label: '灵光', icon: <Sparkles size={12} /> },
          { k: 'cases' as const, label: '案例', icon: <BookOpen size={12} /> },
        ]).map(({ k, label, icon }) => (
          <button key={k} onClick={() => setSubView(k)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm border-b-2 tracking-wider transition-colors ${
              subView === k ? 'text-[#ADFF00] border-[#ADFF00] font-semibold' : 'text-[#888] border-transparent'}`}>
            {icon}{label}
          </button>
        ))}
      </div>
      {subView === 'lingguang' && <LingguangPanel />}
      {subView === 'cases' && <CasesPanel />}
      {subView === 'report' && (
        <>
          <div className="flex-shrink-0 px-4 py-2.5 border-b border-[#1A1A1A] bg-white/[0.01]">
            <div className="flex items-center gap-4">
              <div><span className={`text-base font-bold ${upside > 0 ? 'text-[#ADFF00]' : 'text-[#888]'}`}>{upside > 0 ? '+' : ''}{upside.toFixed(1)}%</span><span className="text-xs text-[#555] ml-1">upside</span></div>
              <div><span className="text-base font-bold text-[#DDD]">{parseFloat(record.asymmetry_ratio || '0').toFixed(2)}x</span><span className="text-xs text-[#555] ml-1">不对称比</span></div>
              {record.primary_model && <span className="text-xs text-[#888] ml-auto">{record.primary_model}</span>}
            </div>
            <div className="flex gap-2 mt-2">
              <button onClick={handleShowPrompt} className="flex items-center gap-1.5 px-3 py-1.5 border rounded-sm text-sm transition-colors" style={{ borderColor: showPrompt ? 'rgba(173,255,0,0.35)' : '#2A2A2A', color: showPrompt ? '#ADFF00' : '#888', background: showPrompt ? 'rgba(173,255,0,0.04)' : 'transparent' }}>{showPrompt ? <ChevronUp size={14} /> : <ChevronDown size={14} />}展符</button>
              <button onClick={handleCopy} disabled={!assembledPrompt} className="flex items-center gap-1.5 px-3 py-1.5 border border-[#2A2A2A] rounded-sm text-sm text-[#888] active:border-[#ADFF00]/40 active:text-[#ADFF00] disabled:opacity-30 transition-colors">{copied ? <Check size={14} className="text-[#ADFF00]" /> : <Copy size={14} />}{copied ? '已复制' : '复制'}</button>
            </div>
          </div>
          {showPrompt && (
            <div className="flex-shrink-0 max-h-48 overflow-y-auto border-b border-[#1A1A1A]">
              <pre className="px-4 py-3 text-sm text-[#AAA] leading-relaxed whitespace-pre-wrap select-all">{assembledPrompt || '暂无内容'}</pre>
            </div>
          )}
          <div className="flex-1 overflow-y-auto">
            {reportLoading ? <MobileLoading /> : report && messages.length === 0 ? (
              <div className="px-4 py-3 space-y-2">
                <div className="text-xs text-[#ADFF00] font-semibold tracking-wider mb-1">完整报告数据</div>
                {Object.entries(report).map(([agentKey, data]) => {
                  if (!data) return null
                  const labels: Record<string, string> = { agent0: 'Agent-0 事件分析', agent1: 'Agent-1 财务数据', agent2: 'Agent-2 路由判决', agent3: 'Agent-3 推演裁决', agent2a: 'Agent-2a 案例比对', routing_decision: '路由判决详情', baseline_report: '基线分析' }
                  const html = renderSmart(data)
                  if (!html) return null
                  return (
                    <MobileCard key={agentKey}>
                      <div className="text-xs text-[#ADFF00] font-semibold mb-2 tracking-wider uppercase">{labels[agentKey] || agentKey}</div>
                      <div className="text-sm text-[#DDD] leading-relaxed report-content" dangerouslySetInnerHTML={{ __html: html }} />
                    </MobileCard>
                  )
                })}
              </div>
            ) : null}
            {messages.length === 0 && !reportLoading && <div className="flex flex-col items-center justify-center py-10 text-[#555]"><span className="text-2xl mb-2 opacity-20">◇</span><span className="text-sm">输入问题推演</span></div>}
            <div className="px-3 py-3 space-y-3">
              {messages.map((m) => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[88%] rounded-sm px-3 py-2 ${m.role === 'user' ? 'bg-[#ADFF00]/[0.08] border border-[#ADFF00]/20' : m.role === 'system' ? 'bg-red-500/[0.06] border border-red-500/20' : 'bg-white/[0.02] border border-[#2A2A2A]'}`}>
                    {m.role === 'assistant' ? <div className="text-sm leading-relaxed [&_p]:my-1 [&_strong]:text-[#ADFF00]" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) || '<span class="text-[#555]">等待...</span>' }} /> : <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">{m.content}</p>}
                  </div>
                </div>
              ))}
              {streaming && <div className="flex justify-start"><div className="bg-white/[0.02] border border-[#2A2A2A] rounded-sm px-3 py-2"><span className="text-sm text-[#ADFF00] animate-pulse">◈ 推演中...</span></div></div>}
              <div ref={msgEndRef} />
            </div>
          </div>
          <div className="flex-shrink-0 border-t border-[#2A2A2A] bg-[#050401]/95 p-2">
            <div className="flex items-center gap-2">
              <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }} placeholder="输入问题，Enter 发送..." disabled={streaming} className="flex-1 bg-white/[0.04] border border-[#2A2A2A] rounded-sm px-3 py-2.5 text-sm text-[#F2F4F3] placeholder:text-[#444] outline-none focus:border-[#ADFF00]/40 disabled:opacity-50" />
              <button onClick={handleSend} disabled={streaming || !input.trim()} className="flex-shrink-0 w-10 h-10 flex items-center justify-center border rounded-sm transition-all active:scale-95" style={{ background: streaming ? 'rgba(255,92,0,0.08)' : 'rgba(173,255,0,0.08)', borderColor: streaming ? 'rgba(255,92,0,0.25)' : input.trim() ? 'rgba(173,255,0,0.3)' : '#2A2A2A', color: input.trim() ? '#ADFF00' : '#555', opacity: input.trim() || streaming ? 1 : 0.4 }}><Send size={16} /></button>
            </div>
          </div>
        </>
      )}
      <AvatarContextSheet open={contextOpen} onClose={() => setContextOpen(false)} selected={enabledModules} onToggle={toggleModule} />
    </div>
  )
}

function LingguangPanel() {
  const { data, loading, error } = useMobileData(() => fetchLingguang())
  const items = data || []
  return (
    <div className="flex-1 overflow-y-auto">
      {loading && <MobileLoading />}
      {error && <div className="flex items-center justify-center py-16 text-sm text-red-400">{error}</div>}
      {!loading && !items.length && <MobileEmpty message="暂无灵光笔记" />}
      {!loading && items.length > 0 && (
        <div className="flex flex-col gap-px">
          {items.map((item: LingguangItem) => (
            <MobileCard key={item.id}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-semibold text-[#F2F4F3]">{item.title}</span>
                {item.confidence > 0 && <MobileBadge variant="green">{item.confidence}</MobileBadge>}
              </div>
              {item.content && <p className="text-sm text-[#AAA] leading-relaxed mb-2">{item.content.slice(0, 300)}</p>}
              <div className="flex items-center gap-2 flex-wrap">
                {item.tags?.map((t: string) => <span key={t} className="text-xs text-[#555] border border-[#2A2A2A] px-1.5 py-0.5 rounded-sm">{t}</span>)}
                {item.source && <span className="text-xs text-[#555] ml-auto">{item.source}</span>}
              </div>
            </MobileCard>
          ))}
        </div>
      )}
    </div>
  )
}

function CasesPanel() {
  const { data, loading, error } = useMobileData(() => fetchCases())
  const items = data || []
  return (
    <div className="flex-1 overflow-y-auto">
      {loading && <MobileLoading />}
      {error && <div className="flex items-center justify-center py-16 text-sm text-red-400">{error}</div>}
      {!loading && !items.length && <MobileEmpty message="暂无案例数据" />}
      {!loading && items.length > 0 && (
        <div className="flex flex-col gap-px">
          {items.map((c: CaseItem, i: number) => (
            <MobileCard key={i} accent={parseFloat(c.gainMultiple || '0') > 3}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-[#F2F4F3]">{c.stockName}</span>
                  <span className="text-xs text-[#888]">{c.stockCode}</span>
                </div>
                <MobileBadge variant={parseFloat(c.gainMultiple || '0') > 3 ? 'green' : 'orange'}>{c.gainMultiple}x</MobileBadge>
              </div>
              <div className="flex items-center gap-3 text-sm mb-2">
                <span className="text-[#888]">{c.sector}</span>
                <span className="text-[#ADFF00]">+{c.actualReturnPct}%</span>
                {c.maxDrawdownPct > 0 && <span className="text-red-400">-{c.maxDrawdownPct}%</span>}
              </div>
              {c.logic && <p className="text-sm text-[#AAA] leading-relaxed mb-2">{c.logic.slice(0, 200)}</p>}
              <div className="flex items-center gap-2 flex-wrap text-xs">
                {c.catalyst && <span className="text-[#888]">催化: {c.catalyst}</span>}
                {c.primaryDriver && <span className="text-[#888]">驱动: {c.primaryDriver}</span>}
                {c.endState && <span className="text-[#888]">终态: {c.endState}</span>}
                {c.tags?.slice(0, 3).map((t: string) => <span key={t} className="text-[#555] border border-[#2A2A2A] px-1 py-0.5 rounded-sm">{t}</span>)}
              </div>
            </MobileCard>
          ))}
        </div>
      )}
    </div>
  )
}

export function AvatarChat() {
  const { data, loading, error, refresh } = useMobileData(() => fetchDingshulu(500))
  const [selected, setSelected] = useState<DingshuluRecord | null>(null)
  if (selected) return <AvatarDetail record={selected} onBack={() => setSelected(null)} />
  return <RecordList records={data || []} loading={loading} error={error} refresh={refresh} onSelect={setSelected} />
}
