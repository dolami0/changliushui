import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Activity, Pause, Play, Target, Calendar, AlertTriangle, Shield } from 'lucide-react'
import { MobileBackHeader } from '@/mobile/components/MobileBackHeader'
import { MobileCard, MobileCardHeader } from '@/mobile/components/MobileCard'
import { MobileBadge } from '@/mobile/components/MobileBadge'

import { updateTrackStatus, type TrackStatus } from '@/services/cozeApi'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer,
  Tooltip, ReferenceLine,
} from 'recharts'

interface Pillar {
  name: string; expectation: string; status: string
  verificationDate: string; lastChecked: string
}
interface Risk {
  name: string; probability: string; impact: string; monitoring: string
}
interface CatalystEvent {
  date: string; event: string; type: string; impact: string; status?: string
}
interface PriceLogEntry {
  date: string; price: number; return_pct: number; note: string
}
interface TrackingItem {
  id: string; stockCode: string; stockName: string; trackStatus: string; thesis: string
  conviction: number; decisionDate: string; decision: string
  recommendedPosition: number; entryCondition: string
  basePrice: number; baseMarketCap: number; baseDate: string
  pillars: Pillar[]; risks: Risk[]; exitConditions: string[]
  catalystCalendar: CatalystEvent[]; priceLog: PriceLogEntry[]
  aShareTracking?: Record<string, { result: string }>
}

const PILLAR_STATUS: Record<string, string> = {
  verified: 'text-[#ADFF00] bg-[#ADFF00]/[0.06] border-[#ADFF00]/20',
  on_track: 'text-[#ADFF00] bg-[#ADFF00]/[0.03] border-[#ADFF00]/15',
  at_risk: 'text-[#FF5C00] bg-[#FF5C00]/[0.06] border-[#FF5C00]/20',
  pending: 'text-[#888] bg-white/[0.02] border-[#2A2A2A]',
}

export function TrackingDetail() {
  const location = useLocation()
  const t = (location.state as { tracking?: TrackingItem })?.tracking
  const [section, setSection] = useState('thesis')

  const [currentStatus, setCurrentStatus] = useState<TrackStatus>(t?.trackStatus === 'paused' ? 'paused' : 'active')

  if (!t) {
    return (
      <div className="flex flex-col h-full">
        <MobileBackHeader title="追踪详情" />
        <div className="flex items-center justify-center flex-1 text-[#888] text-sm">未找到追踪记录</div>
      </div>
    )
  }

  const isPaused = currentStatus === 'paused'
  const convictionPct = Math.min(100, Math.max(0, (t.conviction || 0) * 100))
  const SECTIONS = ['论点', '走势', '支柱', '催化剂', '风险']

  const handleToggle = async () => {
    const newStatus: TrackStatus = isPaused ? 'active' : 'paused'
    setCurrentStatus(newStatus)
    try {
      await updateTrackStatus(t.id, newStatus)
    } catch {
      setCurrentStatus(isPaused ? 'paused' : 'active')
    }
  }

  return (
    <div className="flex flex-col h-full">
      <MobileBackHeader title={t.stockName || '追踪详情'} />

      {/* Section tabs — bigger text */}
      <div className="flex border-b border-[#2A2A2A] bg-[#050401] overflow-x-auto hide-scroll flex-shrink-0">
        {SECTIONS.map((s) => {
          const key = s === '论点' ? 'thesis' : s === '走势' ? 'chart' : s === '支柱' ? 'pillars' : s === '催化剂' ? 'catalysts' : 'risks'
          return (
            <button
              key={s}
              onClick={() => setSection(key)}
              className={`flex-shrink-0 px-3 py-2 text-xs tracking-wider transition-colors ${
                section === key
                  ? 'text-[#ADFF00] border-b-2 border-[#ADFF00] font-semibold'
                  : 'text-[#888] border-b-2 border-transparent'
              }`}
            >
              {s}
            </button>
          )
        })}
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* === 论点 === */}
        {section === 'thesis' && (
          <div>
            <MobileCard accent={!isPaused}>
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                {isPaused ? <Pause size={16} className="text-yellow-400" /> : <Activity size={16} className="text-[#ADFF00]" />}
                <span className="text-base font-semibold text-[#F2F4F3]">{t.stockName}</span>
                <span className="text-sm text-[#888]">{t.stockCode}</span>
                <MobileBadge variant={isPaused ? 'orange' : 'green'}>{isPaused ? '已暂停' : '跟踪中'}</MobileBadge>
              </div>

              {/* Toggle button — standalone row, impossible to miss */}
              <button
                onClick={handleToggle}
                className={`w-full flex items-center justify-center gap-2 py-2.5 text-sm font-bold rounded-lg shadow-lg mt-1 ${
                  isPaused
                    ? 'text-black bg-[#ADFF00] hover:bg-[#8ECC00]'
                    : 'text-black bg-yellow-400 hover:bg-yellow-300'
                }`}
              >
                {isPaused ? <><Play size={16} /> 恢复跟踪</> : <><Pause size={16} /> 暂停跟踪</>}
              </button>

              <div className="flex items-center gap-4 py-3">
                <div className="relative w-16 h-16 flex-shrink-0">
                  <svg viewBox="0 0 64 64" className="w-full h-full -rotate-90">
                    <circle cx="32" cy="32" r="28" fill="none" stroke="#1A1A1A" strokeWidth="4" />
                    <circle cx="32" cy="32" r="28" fill="none" stroke="#ADFF00" strokeWidth="4"
                      strokeDasharray={`${convictionPct * 1.76} 176`} strokeLinecap="round" />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-sm font-bold text-[#ADFF00]">{convictionPct.toFixed(0)}%</span>
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-[#DDD] leading-relaxed">{t.thesis || '暂无论点'}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-[#1A1A1A] text-sm">
                <div><span className="text-[#555]">决策: </span><span className="text-[#DDD]">{t.decision || '—'}</span></div>
                <div><span className="text-[#555]">日期: </span><span className="text-[#DDD]">{t.decisionDate || '—'}</span></div>
                <div><span className="text-[#555]">建议仓位: </span><span className="text-[#DDD]">{t.recommendedPosition || '—'}%</span></div>
                <div><span className="text-[#555]">入场条件: </span><span className="text-[#DDD]">{t.entryCondition || '—'}</span></div>
              </div>
            </MobileCard>

            {t.basePrice > 0 && (
              <MobileCard>
                <div className="flex items-center justify-around">
                  <div className="text-center">
                    <div className="text-xl font-bold text-[#F2F4F3]">{t.basePrice.toFixed(2)}</div>
                    <div className="text-xs text-[#555] mt-1">基准价格</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xl font-bold text-[#ADFF00]">{(t.baseMarketCap / 1e8).toFixed(0)}亿</div>
                    <div className="text-xs text-[#555] mt-1">基准市值</div>
                  </div>
                </div>
              </MobileCard>
            )}

            {t.aShareTracking && (
              <MobileCard>
                <h3 className="text-sm font-semibold text-[#ADFF00] mb-3 flex items-center gap-1.5">
                  <Shield size={14} /> A股监控
                </h3>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {Object.entries(t.aShareTracking).map(([k, v]) => {
                    const labels: Record<string, string> = { pledgeCheck: '质押', unlockCheck: '解禁', marginCheck: '融券', insiderTrading: '内部交易' }
                    return (
                      <div key={k} className="flex justify-between border-b border-[#1A1A1A] pb-1.5">
                        <span className="text-[#888]">{labels[k] || k}</span>
                        <span className="text-[#DDD]">{v?.result || '—'}</span>
                      </div>
                    )
                  })}
                </div>
              </MobileCard>
            )}
          </div>
        )}

        {/* === 走势 === */}
        {section === 'chart' && (
          <div>
            <MobileCard>
              <MobileCardHeader>
                <span className="text-sm font-semibold text-[#ADFF00]">价格走势</span>
                <span className="text-xs text-[#888]">{t.baseDate || ''}</span>
              </MobileCardHeader>
              {Array.isArray(t.priceLog) && t.priceLog.length > 1 ? (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={t.priceLog}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1A1A1A" />
                      <XAxis dataKey="date" tick={{ fill: '#555', fontSize: 10 }} />
                      <YAxis tick={{ fill: '#555', fontSize: 10 }} domain={['auto', 'auto']} />
                      <Tooltip contentStyle={{ backgroundColor: '#0A0A0A', border: '1px solid #2A2A2A', borderRadius: 8 }} labelStyle={{ color: '#DDD' }} />
                      <ReferenceLine y={t.basePrice} stroke="#ADFF00" strokeDasharray="4 4" label={{ value: `基准 ${t.basePrice}`, fill: '#ADFF00', fontSize: 10 }} />
                      <Line type="monotone" dataKey="price" stroke="#ADFF00" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="flex items-center justify-center h-32 text-[#555] text-sm">暂无走势数据</div>
              )}
            </MobileCard>
            {Array.isArray(t.priceLog) && t.priceLog.length > 0 && (
              <MobileCard>
                <MobileCardHeader><span className="text-sm font-semibold text-[#ADFF00]">价格记录</span></MobileCardHeader>
                <div className="space-y-2 text-sm">
                  {t.priceLog.map((log, idx) => (
                    <div key={idx} className="flex items-center justify-between border-b border-[#1A1A1A] pb-1.5">
                      <div>
                        <span className="text-[#888]">{log.date}</span>
                        <span className="text-[#DDD] ml-2">¥{log.price.toFixed(2)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={log.return_pct >= 0 ? 'text-[#ADFF00]' : 'text-red-400'}>
                          {log.return_pct >= 0 ? '+' : ''}{log.return_pct.toFixed(2)}%
                        </span>
                        <span className="text-[#666] text-xs">{log.note || ''}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </MobileCard>
            )}
          </div>
        )}

        {/* === 支柱 === */}
        {section === 'pillars' && (
          <div className="p-4 space-y-3">
            {Array.isArray(t.pillars) && t.pillars.length > 0 ? t.pillars.map((p, i) => (
              <MobileCard key={i}>
                <MobileCardHeader>
                  <span className="text-xs font-semibold text-[#ADFF00]">{p.name}</span>
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${PILLAR_STATUS[p.status] || PILLAR_STATUS.pending}`}>
                    {p.status === 'verified' ? '已验证' : p.status === 'on_track' ? '正常' : p.status === 'at_risk' ? '风险' : '待定'}
                  </span>
                </MobileCardHeader>
                <p className="text-sm text-[#DDD]">{p.expectation}</p>
                <div className="flex gap-4 mt-2 text-xs text-[#555]">
                  <span>验证: {p.verificationDate || '—'}</span>
                  <span>上次: {p.lastChecked || '—'}</span>
                </div>
              </MobileCard>
            )) : <div className="text-center text-sm text-[#555] py-8">暂无支柱数据</div>}
          </div>
        )}

        {/* === 催化剂 === */}
        {section === 'catalysts' && (
          <div className="p-4 space-y-3">
            {Array.isArray(t.catalystCalendar) && t.catalystCalendar.length > 0 ? (
              <>
                {/* 未来事件 */}
                {t.catalystCalendar.filter(e => e.type === 'future').length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-[#ADFF00] mb-2 flex items-center gap-1"><Calendar size={12} /> 未来催化剂</h3>
                    {t.catalystCalendar.filter(e => e.type === 'future').map((e, i) => (
                      <MobileCard key={i}>
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-sm font-semibold text-[#DDD]">{e.event}</div>
                            <div className="text-xs text-[#555]">{e.date}</div>
                          </div>
                          <div className="text-right">
                            <div className="text-xs text-[#ADFF00]">{e.impact}</div>
                            <div className="text-xs text-[#888]">{e.status || ''}</div>
                          </div>
                        </div>
                      </MobileCard>
                    ))}
                  </div>
                )}
                {/* 已发生事件 */}
                {t.catalystCalendar.filter(e => e.type === 'past').length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-[#ADFF00] mb-2 flex items-center gap-1"><Target size={12} /> 已实现</h3>
                    {t.catalystCalendar.filter(e => e.type === 'past').map((e, i) => (
                      <MobileCard key={i}>
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-sm text-[#DDD]">{e.event}</div>
                            <div className="text-xs text-[#555]">{e.date}</div>
                          </div>
                          <div className="text-xs text-[#ADFF00]">{e.impact}</div>
                        </div>
                      </MobileCard>
                    ))}
                  </div>
                )}
              </>
            ) : <div className="text-center text-sm text-[#555] py-8">暂无催化剂数据</div>}
          </div>
        )}

        {/* === 风险 === */}
        {section === 'risks' && (
          <div className="p-4 space-y-3">
            {Array.isArray(t.risks) && t.risks.length > 0 ? t.risks.map((r, i) => (
              <MobileCard key={i}>
                <MobileCardHeader>
                  <span className="text-xs font-semibold text-red-400 flex items-center gap-1"><AlertTriangle size={12} /> {r.name}</span>
                </MobileCardHeader>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div><span className="text-[#555]">概率: </span><span className="text-[#DDD]">{r.probability}</span></div>
                  <div><span className="text-[#555]">影响: </span><span className="text-[#DDD]">{r.impact}</span></div>
                  <div><span className="text-[#555]">监控: </span><span className="text-[#DDD]">{r.monitoring}</span></div>
                </div>
              </MobileCard>
            )) : <div className="text-center text-sm text-[#555] py-8">暂无风险数据</div>}
            {Array.isArray(t.exitConditions) && t.exitConditions.length > 0 && (
              <MobileCard>
                <MobileCardHeader><span className="text-xs font-semibold text-red-400">退出条件</span></MobileCardHeader>
                <ul className="list-disc list-inside text-sm text-[#DDD] space-y-1">
                  {t.exitConditions.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
              </MobileCard>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
