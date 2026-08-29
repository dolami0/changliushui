import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchTracking, updateTrackStatus, type TrackingItem } from '@/services/cozeApi'
import { MobileEmpty } from '@/mobile/components/MobileEmpty'
import { MobileBadge } from '@/mobile/components/MobileBadge'

export function TrackingList() {
  const [data, setData] = useState<TrackingItem[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const items = await fetchTracking()
      setData(items)
    } catch { setData([]) }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleToggle = async (e: React.MouseEvent, item: TrackingItem) => {
    e.stopPropagation()
    const newStatus = item.trackStatus === 'paused' ? 'active' : 'paused'
    setData(prev => prev.map(d => d.id === item.id ? { ...d, trackStatus: newStatus } : d))
    try { await updateTrackStatus(item.id, newStatus) } catch { load() }
  }

  const visibleItems = data.filter((t) => t.trackStatus !== 'paused')
  const pausedCount = data.filter((t) => t.trackStatus === 'paused').length

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32 text-[#555] text-sm">加载中...</div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {pausedCount > 0 && (
        <div className="flex-shrink-0 px-4 py-2 text-xs text-[#888] border-b border-[#2A2A2A] bg-[#050401]">
          已暂停 {pausedCount} 条记录
        </div>
      )}

      {visibleItems.length === 0 ? (
        <MobileEmpty message="暂无追踪记录" />
      ) : (
        <div className="p-4 space-y-3">
          {visibleItems.map((t, idx) => {
            const convictionPct = Math.min(100, Math.max(0, (t.conviction || 0) * 100))
            return (
              <div
                key={t.id || idx}
                className="bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl p-4"
                onClick={() => navigate(`/m/tracking/${t.id || idx}`, { state: { tracking: t } })}
              >
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-1.5 h-1.5 rounded-full bg-[#ADFF00]" />
                  <span className="text-sm font-semibold text-[#F2F4F3] flex-1 truncate">{t.stockName}</span>
                  <span className="text-xs text-[#555]">{t.stockCode}</span>
                  <MobileBadge variant="green">跟踪中</MobileBadge>
                </div>
                <p className="text-xs text-[#888] line-clamp-2">{t.thesis || '暂无论点'}</p>
                <div className="flex items-center gap-3 mt-2 text-xs text-[#555]">
                  <span>确信度: <span className="text-[#ADFF00]">{convictionPct.toFixed(0)}%</span></span>
                  <span>仓位: {t.recommendedPosition || '—'}%</span>
                </div>
                <button
                  onClick={(e) => handleToggle(e, t)}
                  className="w-full mt-3 py-2 rounded-lg bg-yellow-400/15 border border-yellow-400/30 text-yellow-400 text-sm font-medium hover:bg-yellow-400 hover:text-black transition-colors"
                >
                  ⏸ 暂停跟踪
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
