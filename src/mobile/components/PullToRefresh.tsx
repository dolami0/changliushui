import { useRef, useState, useCallback } from 'react'
import { cn } from '@/lib/utils'

interface PullToRefreshProps {
  children: React.ReactNode
  onRefresh: () => Promise<void>
  className?: string
  threshold?: number
}

export function PullToRefresh({
  children,
  onRefresh,
  className,
  threshold = 60,
}: PullToRefreshProps) {
  const [pulling, setPulling] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [pullDistance, setPullDistance] = useState(0)
  const startY = useRef(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    // 只在滚动到顶部时触发
    const el = containerRef.current
    if (!el || el.scrollTop > 0) return
    startY.current = e.touches[0].clientY
    setPulling(true)
  }, [])

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!pulling || refreshing) return
      const el = containerRef.current
      if (!el || el.scrollTop > 0) {
        setPullDistance(0)
        return
      }
      const diff = e.touches[0].clientY - startY.current
      if (diff > 0) {
        // 阻尼效果：越拉越难拉
        const dampened = Math.min(diff * 0.4, threshold * 1.5)
        setPullDistance(dampened)
      }
    },
    [pulling, refreshing, threshold]
  )

  const handleTouchEnd = useCallback(async () => {
    if (pullDistance >= threshold && !refreshing) {
      setRefreshing(true)
      try {
        await onRefresh()
      } finally {
        setRefreshing(false)
      }
    }
    setPullDistance(0)
    setPulling(false)
  }, [pullDistance, threshold, refreshing, onRefresh])

  const progress = Math.min(pullDistance / threshold, 1)

  return (
    <div
      ref={containerRef}
      className={cn('relative overflow-y-auto', className)}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      style={{ overscrollBehaviorY: 'contain' }}
    >
      {/* 下拉指示器 */}
      <div
        className="flex items-center justify-center transition-all duration-200 overflow-hidden"
        style={{
          height: refreshing ? 36 : pullDistance,
          opacity: pullDistance > 0 || refreshing ? 1 : 0,
        }}
      >
        {refreshing ? (
          <span className="text-[11px] text-[#ADFF00] font-mono tracking-wider animate-pulse">
            刷新中...
          </span>
        ) : (
          <span
            className={cn(
              'text-[11px] font-mono tracking-wider transition-colors',
              progress >= 1 ? 'text-[#ADFF00]' : 'text-[#888]'
            )}
          >
            {progress >= 1 ? '释放刷新' : '下拉刷新'}
          </span>
        )}
      </div>

      {children}
    </div>
  )
}
