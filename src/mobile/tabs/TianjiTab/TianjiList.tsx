import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMobileData } from '@/mobile/hooks/useMobileData'
import { MobileCard, MobileCardHeader } from '@/mobile/components/MobileCard'
import { MobileBadge } from '@/mobile/components/MobileBadge'
import { MobileLoading } from '@/mobile/components/MobileLoading'
import { MobileEmpty } from '@/mobile/components/MobileEmpty'
import { MobileList } from '@/mobile/components/MobileList'
import {
  fetchTianjijuan, fetchWangqi,
  extractNewsTitle,
  type WangqiResult,
} from '@/services/cozeApi'

const PAGE_SIZE = 50

const LEVEL_CONFIG: Record<string, { label: string; variant: 'green' | 'orange' | 'red' | 'muted' }> = {
  '5': { label: 'L5 道变', variant: 'red' },
  '4': { label: 'L4 天兆', variant: 'orange' },
  '3': { label: 'L3 雷动', variant: 'green' },
  '2': { label: 'L2 风起', variant: 'muted' },
  '1': { label: 'L1 微澜', variant: 'muted' },
  '0': { label: 'L0 尘外', variant: 'muted' },
}

const BJ = 'Asia/Shanghai'
const BJ_FMT: Intl.DateTimeFormatOptions = { timeZone: BJ, hour: '2-digit', minute: '2-digit', hour12: false }
const BJ_DATE: Intl.DateTimeFormatOptions = { timeZone: BJ, month: '2-digit', day: '2-digit' }
const BJ_FULL_UNUSED: Intl.DateTimeFormatOptions = { timeZone: BJ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }
void BJ_FULL_UNUSED

function parseTs(ts: string): Date | null {
  if (!ts) return null
  if (ts.includes('-') || ts.includes('T')) {
    const hasTz = /[Zz]$/.test(ts) || /[+-]\d{2}:\d{2}$/.test(ts) || /[+-]\d{4}$/.test(ts)
    const d = new Date(hasTz ? ts : ts + '+08:00')
    return isNaN(d.getTime()) ? null : d
  }
  const n = parseInt(ts)
  if (isNaN(n)) return null
  if (n > 1e12) { const d = new Date(n); return isNaN(d.getTime()) ? null : d }
  if (n > 1e9) { const d = new Date(n * 1000); return isNaN(d.getTime()) ? null : d }
  return null
}

function formatTs(ts: string): string {
  const d = parseTs(ts)
  if (!d) return ts?.slice(0, 16) || ''
  const now = new Date()
  const todayStr = new Intl.DateTimeFormat('zh-CN', { timeZone: BJ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
  const dateStr = new Intl.DateTimeFormat('zh-CN', BJ_DATE).format(d)
  const isTodayFlag = dateStr === todayStr
  const time = new Intl.DateTimeFormat('zh-CN', BJ_FMT).format(d)
  const date = new Intl.DateTimeFormat('zh-CN', BJ_DATE).format(d)
  return isTodayFlag ? `今天 ${time}` : `${date} ${time}`
}

function isToday(ts: string): boolean {
  const d = parseTs(ts)
  if (!d) return false
  const now = new Date()
  const todayStr = new Intl.DateTimeFormat('zh-CN', { timeZone: BJ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
  const dateStr = new Intl.DateTimeFormat('zh-CN', BJ_DATE).format(d)
  return dateStr === todayStr
}

function TianyanFeed() {
  const navigate = useNavigate()
  const { data, loading, error, refresh } = useMobileData(() => fetchTianjijuan(500))
  const [levelFilter, setLevelFilter] = useState<Set<string>>(new Set())
  const [page, setPage] = useState(0)

  useEffect(() => {
    const id = setInterval(refresh, 10 * 60 * 1000)
    return () => clearInterval(id)
  }, [refresh])

  const toggleLevel = useCallback((level: string) => {
    setLevelFilter((prev) => {
      const next = new Set(prev); if (next.has(level)) next.delete(level); else next.add(level); return next
    })
    setPage(0)
  }, [])

  const hasActiveFilter = levelFilter.size > 0
  const todayImportant = !hasActiveFilter
    ? (data || []).filter((r) => isToday(r.bstudio_create_time) && parseInt(r.level) >= 3)
    : []
  const rest = hasActiveFilter
    ? (data || []).filter((r) => levelFilter.has(r.level))
    : (data || []).filter((r) => !isToday(r.bstudio_create_time) || parseInt(r.level) < 3)

  const totalPages = Math.ceil(rest.length / PAGE_SIZE)
  const paged = rest.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <div className="flex flex-col h-full">
      <div className="flex gap-1.5 px-4 py-2 overflow-x-auto hide-scroll border-b border-[#2A2A2A] flex-shrink-0">
        {Object.entries(LEVEL_CONFIG).map(([level, cfg]) => {
          const active = levelFilter.has(level)
          const count = (data || []).filter((r) => r.level === level).length
          return (
            <button
              key={level}
              onClick={() => toggleLevel(level)}
              className={`flex items-center gap-1 px-2 py-1 text-xs border rounded-sm transition-colors flex-shrink-0 ${
                active ? 'text-[#ADFF00] border-[#ADFF00]/30 bg-[#ADFF00]/[0.04]' : 'text-[#555] border-[#2A2A2A]'
              }`}
            >
              {cfg.label}
              <span className="opacity-60">{count}</span>
            </button>
          )
        })}
        {hasActiveFilter && (
          <button onClick={() => setLevelFilter(new Set())} className="px-2 py-1 text-xs text-[#FF5C00] border border-transparent flex-shrink-0">
            清除
          </button>
        )}
      </div>

      {loading && <MobileLoading />}
      {error && (
        <div className="flex flex-col items-center gap-2 py-16">
          <span className="text-sm text-red-400">{error}</span>
          <button onClick={refresh} className="px-4 py-1 border border-[#2A2A2A] text-xs text-[#888]">重试</button>
        </div>
      )}
      {!loading && !error && !todayImportant.length && !paged.length && <MobileEmpty message="暂无事件" />}

      {!loading && (
        <div className="flex-1 overflow-y-auto">
          <MobileList onRefresh={refresh}>
            {page === 0 && todayImportant.length > 0 && !hasActiveFilter && (
              <>
                <div className="flex items-center gap-2 px-4 py-2">
                  <span className="text-xs text-[#ADFF00] font-semibold tracking-wider">◆ 今日重要</span>
                  <div className="flex-1 h-px bg-[#ADFF00]/15" />
                </div>
                {todayImportant.map((r) => {
                  const cfg = LEVEL_CONFIG[r.level] || LEVEL_CONFIG['0']
                  return (
                    <MobileCard key={r.id} accent onClick={() => navigate(`/m/tianyan/${r.id}`, { state: { event: r } })}>
                      <MobileCardHeader>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <MobileBadge variant={cfg.variant}>{cfg.label}</MobileBadge>
                          {r.stock_code && r.stock_code !== 'USER_INPUT' && <span className="text-xs text-[#AAA]">{r.stock_code}</span>}
                          {r.stock_name && r.stock_name !== '用户传讯' && <span className="text-xs text-[#888]">{r.stock_name}</span>}
                          <span className="text-xs text-[#555] ml-auto flex-shrink-0">{formatTs(r.bstudio_create_time)}</span>
                        </div>
                      </MobileCardHeader>
                      <p className="text-sm text-[#DDD] leading-relaxed break-words">{extractNewsTitle(r.news_content || '', 60)}</p>
                    </MobileCard>
                  )
                })}
                {paged.length > 0 && (
                  <div className="flex items-center gap-2 px-4 py-2 mt-1">
                    <div className="flex-1 h-px bg-[#2A2A2A]" />
                    <span className="text-xs text-[#555]">历史事件</span>
                    <div className="flex-1 h-px bg-[#2A2A2A]" />
                  </div>
                )}
              </>
            )}
            {paged.map((r) => {
              const lvl = parseInt(r.level || '0')
              return (
              <MobileCard key={r.id} onClick={lvl >= 3 ? () => navigate(`/m/tianyan/${r.id}`, { state: { event: r } }) : undefined}>
                <div className="flex items-center gap-1.5 flex-wrap mb-1">
                  <MobileBadge variant={(LEVEL_CONFIG[r.level] || LEVEL_CONFIG['0']).variant}>{(LEVEL_CONFIG[r.level] || LEVEL_CONFIG['0']).label}</MobileBadge>
                  {r.stock_code && r.stock_code !== 'USER_INPUT' && <span className="text-xs text-[#AAA]">{r.stock_code}</span>}
                  <span className="text-xs text-[#555] ml-auto flex-shrink-0">{formatTs(r.bstudio_create_time)}</span>
                </div>
                <p className="text-sm text-[#DDD] leading-relaxed break-words">{extractNewsTitle(r.news_content || '', 60)}</p>
              </MobileCard>
              )
            })}
          </MobileList>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 py-2 border-t border-[#2A2A2A]">
              <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
                className="px-3 py-1 border border-[#2A2A2A] text-xs text-[#888] disabled:opacity-30">上一页</button>
              <span className="text-xs text-[#555]">{page + 1}/{totalPages}</span>
              <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                className="px-3 py-1 border border-[#2A2A2A] text-xs text-[#888] disabled:opacity-30">下一页</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

interface TopNode {
  node_name: string; position: string; profit_retention_score: number
  justification: string; what_to_look_for: string; key_risk: string
}
interface ScoredStock {
  stock_code: string; stock_name: string; node_name: string
  market_cap_yi: number; match_score: number; elasticity_score: number
  space_score: number; moat_score: number; total_score: number
  rationale: string; key_risk: string
}

function parseJSON(s: string) { try { return JSON.parse(s) } catch { return null } }

function WangqiFeed() {
  const { data, loading, error } = useMobileData(() => fetchWangqi(200))
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const items: WangqiResult[] = (data || []) as WangqiResult[]

  function toggle(id: string) {
    setExpanded((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n })
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {loading && <MobileLoading />}
      {error && <div className="flex items-center justify-center py-16 text-sm text-red-400">{error}</div>}
      {!loading && !items.length && <MobileEmpty message="暂无望气数据" />}

      {!loading && items.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {items.map((item, i) => {
            const id = `${i}-${item.source_record_id || '0'}`
            const isOpen = expanded.has(id)
            const nodes: TopNode[] = parseJSON(item.top_nodes_json) || []
            const top5: ScoredStock[] = parseJSON(item.top5_json) || []
            const dateStr = formatTs(item.analysis_date)

            return (
              <MobileCard key={id} accent={!!item.top_pick_score && parseFloat(item.top_pick_score) > 0}>
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  {item.industry_chain && (
                    <span className="text-xs text-[#ADFF00] bg-[#ADFF00]/[0.06] px-2 py-0.5 rounded-sm font-semibold">
                      {item.industry_chain}
                    </span>
                  )}
                  {dateStr && <span className="text-xs text-[#555]">{dateStr}</span>}
                  {item.status === 'error' && <MobileBadge variant="red">异常</MobileBadge>}
                  <span className="flex-1" />
                  <button onClick={() => toggle(id)} className="text-xs text-[#555] active:text-[#ADFF00]">
                    {isOpen ? '收起 ▲' : '展开 ▼'}
                  </button>
                </div>
                <p className="text-sm text-[#AAA] leading-relaxed mb-2">
                  {item.event_summary || item.news_content?.slice(0, 150) || '暂无摘要'}
                </p>
                {nodes.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {nodes.map((n, j) => (
                      <span key={j} className="text-xs text-[#C88D3A] border border-[#C88D3A]/15 px-1.5 py-0.5 rounded-sm">
                        {n.node_name} ({n.profit_retention_score || 0})
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex items-start justify-between pt-2 border-t border-[#1A1A1A]">
                  <div>
                    {item.top_pick_name && item.top_pick_name !== '无高赔率标的' ? (
                      <div className="text-sm text-[#ADFF00] font-semibold">
                        🥇 {item.top_pick_name}
                        <span className="text-xs text-[#888] ml-1.5">{item.top_pick_score}</span>
                      </div>
                    ) : (
                      <div className="text-sm text-[#C88D3A]">无高赔率标的</div>
                    )}
                    {item.runner_up_name && item.runner_up_name !== '无高赔率标的' && (
                      <div className="text-sm text-[#888] mt-0.5">
                        🥈 {item.runner_up_name}
                        <span className="text-xs ml-1.5">{item.runner_up_score}</span>
                      </div>
                    )}
                  </div>
                </div>
                {isOpen && (
                  <div className="mt-3 pt-3 border-t border-[#1A1A1A] space-y-3">
                    {item.top_pick_thesis && (
                      <div>
                        <div className="text-xs text-[#ADFF00] font-semibold mb-1">🥇 榜首逻辑</div>
                        <p className="text-sm text-[#AAA] leading-relaxed">{item.top_pick_thesis}</p>
                      </div>
                    )}
                    {item.runner_up_thesis && (
                      <div>
                        <div className="text-xs text-[#888] font-semibold mb-1">🥈 次选逻辑</div>
                        <p className="text-sm text-[#AAA] leading-relaxed">{item.runner_up_thesis}</p>
                      </div>
                    )}
                    {nodes.map((n, j) => (
                      <div key={j} className="bg-white/[0.02] border border-[#2A2A2A] rounded-sm p-2.5">
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="text-sm font-semibold text-[#F2F4F3]">{n.node_name}</span>
                          <MobileBadge variant="orange">{n.position}</MobileBadge>
                        </div>
                        <table className="rp-table">
                          <tr><td>利润留存分</td><td><b>{n.profit_retention_score || 0}</b></td></tr>
                          {n.justification && <tr><td>判断依据</td><td>{n.justification}</td></tr>}
                          {n.what_to_look_for && <tr><td>观测点</td><td>{n.what_to_look_for}</td></tr>}
                          {n.key_risk && <tr><td>关键风险</td><td className="text-red-400">{n.key_risk}</td></tr>}
                        </table>
                      </div>
                    ))}
                    {top5.length > 0 && (
                      <div>
                        <div className="text-xs text-[#ADFF00] font-semibold mb-2">Top 5 赔率排序</div>
                        <div className="overflow-x-auto">
                          <table className="rp-table text-xs">
                            <thead>
                              <tr className="text-[#888]">
                                <td>#</td><td>标的</td><td>总分</td><td style={{textAlign:'right'}}>匹配</td><td style={{textAlign:'right'}}>弹性</td><td style={{textAlign:'right'}}>空间</td><td style={{textAlign:'right'}}>护城河</td>
                              </tr>
                            </thead>
                            <tbody>
                              {top5.map((s, j) => (
                                <tr key={j}>
                                  <td className="text-[#ADFF00]">{j + 1}</td>
                                  <td className="text-[#F2F4F3]">{s.stock_name}<div className="text-[10px] text-[#555]">{s.stock_code}</div></td>
                                  <td><b>{s.total_score}</b></td>
                                  <td style={{textAlign:'right',color:'#AAA'}}>{s.match_score}</td>
                                  <td style={{textAlign:'right',color:'#AAA'}}>{s.elasticity_score}</td>
                                  <td style={{textAlign:'right',color:'#AAA'}}>{s.space_score}</td>
                                  <td style={{textAlign:'right',color:'#AAA'}}>{s.moat_score}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </MobileCard>
            )
          })}
        </div>
      )}
      <div className="h-20" />
    </div>
  )
}

export function TianjiList() {
  const [subTab, setSubTab] = useState<'tianyan' | 'wangqi'>('tianyan')

  return (
    <div className="flex flex-col h-full">
      <div className="sticky top-0 z-20 bg-[#050401]/95 backdrop-blur-sm border-b border-[#2A2A2A] flex-shrink-0">
        <div className="flex items-center justify-between h-10 px-4">
          <span className="text-sm font-semibold tracking-wider">天机峰</span>
        </div>
        <div className="flex px-4 gap-0">
          {([
            { key: 'tianyan' as const, label: '天眼' },
            { key: 'wangqi' as const, label: '望气' },
          ]).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setSubTab(key)}
              className={`px-5 py-2 text-sm border-b-2 tracking-wider transition-colors ${
                subTab === key
                  ? 'text-[#ADFF00] border-[#ADFF00] font-semibold'
                  : 'text-[#888] border-transparent'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {subTab === 'tianyan' ? <TianyanFeed /> : <WangqiFeed />}
    </div>
  )
}
