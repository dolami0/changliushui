import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { TrendingUp, ArrowUpDown } from 'lucide-react'
import { useMobileData } from '@/mobile/hooks/useMobileData'
import { MobileCard, MobileCardHeader } from '@/mobile/components/MobileCard'
import { MobileBadge } from '@/mobile/components/MobileBadge'
import { MobileLoading } from '@/mobile/components/MobileLoading'
import { MobileEmpty } from '@/mobile/components/MobileEmpty'
import { MobileList } from '@/mobile/components/MobileList'
import { fetchDingshulu, type DingshuluRecord } from '@/services/cozeApi'

type SortMode = 'time' | 'upside'

function tierVariant(tier: string) {
  if (tier?.includes('★★★')) return 'green' as const
  if (tier?.includes('★★')) return 'orange' as const
  return 'muted' as const
}

function RecordCard({ r }: { r: DingshuluRecord }) {
  const navigate = useNavigate()
  const upside = parseFloat(r.prob_weighted_upside_pct || '0')
  const asym = parseFloat(r.asymmetry_ratio || '0')
  const isPositive = upside > 0

  return (
    <MobileCard
      accent={isPositive}
      onClick={() => navigate(`/m/dingshulu/${r.id}`, { state: { record: r } })}
    >
      <MobileCardHeader>
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-[#F2F4F3] truncate">
            {r.stock_name || '—'}
          </span>
          <span className="text-xs text-[#888] flex-shrink-0">{r.stock_code || '—'}</span>
        </div>
        {r.trade_tier && (
          <MobileBadge variant={tierVariant(r.trade_tier)}>{r.trade_tier}</MobileBadge>
        )}
      </MobileCardHeader>

      <div className="flex items-center justify-between">
        <div className="flex items-baseline gap-1">
          <span className={`text-lg font-bold ${isPositive ? 'text-[#ADFF00]' : 'text-[#888]'}`}>
            {isPositive ? '+' : ''}{upside.toFixed(1)}%
          </span>
          <span className="text-xs text-[#888]">概率加权</span>
        </div>
        <div className="flex items-center gap-4 text-right">
          <div>
            <div className="text-xs text-[#888] mb-0.5">不对称比</div>
            <div className="flex items-center gap-1 text-sm">
              <TrendingUp size={12} className={asym > 1.5 ? 'text-[#ADFF00]' : 'text-[#888]'} />
              <span className={asym > 1.5 ? 'text-[#ADFF00] font-semibold' : 'text-[#DDD]'}>
                {asym.toFixed(2)}x
              </span>
            </div>
          </div>
          <div>
            <div className="text-xs text-[#888] mb-0.5">置信度</div>
            <span className="text-sm text-[#DDD]">{r.confidence_score || '—'}</span>
          </div>
        </div>
      </div>

      {r.event_date && (
        <div className="mt-2 pt-2 border-t border-[#1A1A1A] flex items-center gap-2 text-xs text-[#555]">
          <span>{r.event_date}</span>
          {r.quality_flag && (
            <MobileBadge variant={r.quality_flag === 'HIGH_QUALITY' ? 'green' : 'muted'}>
              {r.quality_flag}
            </MobileBadge>
          )}
        </div>
      )}
    </MobileCard>
  )
}

export function DingshuluList() {
  const { data, loading, error, refresh } = useMobileData(() => fetchDingshulu(500))
  const [sortMode, setSortMode] = useState<SortMode>('time')

  const sorted = useMemo(() => {
    if (!data) return []
    const arr = [...data]
    if (sortMode === 'upside') {
      arr.sort((a, b) => parseFloat(b.prob_weighted_upside_pct || '0') - parseFloat(a.prob_weighted_upside_pct || '0'))
    }
    // 'time' is already sorted by bstudio_create_time desc from API
    return arr
  }, [data, sortMode])

  return (
    <div className="flex flex-col h-full">
      <div className="sticky top-0 z-20 bg-[#050401]/95 backdrop-blur-sm border-b border-[#2A2A2A]">
        <div className="flex items-center justify-between h-10 px-4">
          <span className="text-sm font-semibold tracking-wider">定数录</span>
          <span className="text-xs text-[#555]">{data ? `${data.length} 份` : '—'}</span>
        </div>
        {/* Sort toggle */}
        <div className="flex gap-0 px-4 pb-2">
          {([
            { mode: 'time' as SortMode, label: '时间排序' },
            { mode: 'upside' as SortMode, label: '涨幅排序' },
          ]).map(({ mode, label }) => (
            <button
              key={mode}
              onClick={() => setSortMode(mode)}
              className={`px-3 py-1 text-xs border rounded-sm transition-colors ${
                sortMode === mode
                  ? 'text-[#ADFF00] border-[#ADFF00]/30 bg-[#ADFF00]/[0.04]'
                  : 'text-[#555] border-[#2A2A2A]'
              }`}
            >
              {label}
              {sortMode === mode && <ArrowUpDown size={10} className="inline ml-1" />}
            </button>
          ))}
        </div>
      </div>

      {loading && <MobileLoading />}
      {error && (
        <div className="flex flex-col items-center gap-2 py-16">
          <span className="text-sm text-red-400">{error}</span>
          <button onClick={refresh} className="px-4 py-1 border border-[#2A2A2A] text-xs text-[#888]">
            重试
          </button>
        </div>
      )}
      {!loading && !error && !sorted.length && <MobileEmpty message="暂无定数录记录" />}
      {!loading && sorted.length > 0 && (
        <MobileList onRefresh={refresh}>
          {sorted.map((r) => (
            <RecordCard key={r.id} r={r} />
          ))}
        </MobileList>
      )}
    </div>
  )
}
