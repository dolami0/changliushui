import { useLocation } from 'react-router-dom'
import { MobileBackHeader } from '@/mobile/components/MobileBackHeader'
import { MobileCard } from '@/mobile/components/MobileCard'
import { MobileBadge } from '@/mobile/components/MobileBadge'
import { stripHtml, type TianjijuanRecord } from '@/services/cozeApi'

const LEVEL_LABELS: Record<string, string> = {
  '5': 'L5 · 道变',
  '4': 'L4 · 天兆',
  '3': 'L3 · 雷动',
  '2': 'L2 · 风起',
  '1': 'L1 · 微澜',
  '0': 'L0 · 尘外',
}

export function TianjiDetail() {
  const location = useLocation()
  const event = (location.state as { event?: TianjijuanRecord })?.event

  if (!event) {
    return (
      <div className="flex flex-col h-full">
        <MobileBackHeader title="事件详情" />
        <div className="flex items-center justify-center flex-1 text-[#888] text-sm font-mono">
          未找到事件
        </div>
      </div>
    )
  }

  const levelLabel = LEVEL_LABELS[event.level] || '未知等级'
  const dateStr = event.date || (event.bstudio_create_time
    ? new Date(parseInt(event.bstudio_create_time)).toLocaleString('zh-CN')
    : '')

  return (
    <div className="flex flex-col h-full">
      <MobileBackHeader title="事件详情" />

      <div className="flex-1 overflow-y-auto">
        {/* Level badge + meta */}
        <MobileCard accent={parseInt(event.level) >= 4}>
          <div className="flex items-center gap-2 mb-2">
            <MobileBadge
              variant={parseInt(event.level) >= 4 ? 'red' : parseInt(event.level) >= 3 ? 'green' : 'muted'}
            >
              {levelLabel}
            </MobileBadge>
            {event.mode && (
              <span className="text-[10px] text-[#555] font-mono">{event.mode}</span>
            )}
          </div>
          {event.stock_code && (
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-semibold text-[#F2F4F3]">{event.stock_name || ''}</span>
              <span className="text-xs text-[#888]">{event.stock_code}</span>
            </div>
          )}
          {dateStr && (
            <div className="text-[10px] text-[#555] font-mono">{dateStr}</div>
          )}
        </MobileCard>

        {/* News content */}
        <div className="px-4 py-3">
          <h2 className="text-xs font-mono text-[#ADFF00] tracking-wider mb-3">
            // 事件内容
          </h2>
          <MobileCard>
            <div
              className="text-sm text-[#DDD] leading-relaxed whitespace-pre-wrap break-words"
            >
              {stripHtml(event.news_content || '暂无内容')}
            </div>
          </MobileCard>
        </div>

        {/* Knowledge analysis */}
        {event.knowledge && (
          <div className="px-4 py-2">
            <h2 className="text-xs font-mono text-[#ADFF00] tracking-wider mb-3">
              // 知识分析
            </h2>
            <MobileCard>
              <div
                className="text-xs text-[#AAA] leading-relaxed [&_p]:my-1 [&_strong]:text-[#DDD] [&_h1]:text-base [&_h2]:text-sm"
                dangerouslySetInnerHTML={{ __html: stripHtml(event.knowledge) }}
              />
            </MobileCard>
          </div>
        )}

        {/* Metadata footer */}
        <MobileCard className="mt-2">
          <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
            <div>
              <span className="text-[#555]">是否分析:</span>
              <span className="ml-1 text-[#DDD]">{event.is_analyzed || '—'}</span>
            </div>
            <div>
              <span className="text-[#555]">UUID:</span>
              <span className="ml-1 text-[#888] truncate block">{event.uuid || '—'}</span>
            </div>
          </div>
        </MobileCard>

        <div className="h-20" />
      </div>
    </div>
  )
}
