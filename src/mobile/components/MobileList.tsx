import { cn } from '@/lib/utils'
import { PullToRefresh } from './PullToRefresh'

export function MobileList({
  children,
  className,
  onRefresh,
}: {
  children: React.ReactNode
  className?: string
  onRefresh?: () => Promise<void>
}) {
  if (onRefresh) {
    return (
      <PullToRefresh onRefresh={onRefresh} className={cn('flex flex-col', className)}>
        <div className="flex flex-col gap-px">
          {children}
        </div>
      </PullToRefresh>
    )
  }

  return (
    <div className={cn('flex flex-col', className)}>
      <div className="flex flex-col gap-px">
        {children}
      </div>
    </div>
  )
}
