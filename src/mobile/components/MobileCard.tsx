import { cn } from '@/lib/utils'

export function MobileCard({
  accent = false,
  className,
  children,
  onClick,
}: {
  accent?: boolean
  className?: string
  children: React.ReactNode
  onClick?: () => void
}) {
  return (
    <div
      role={onClick ? 'button' : undefined}
      onClick={onClick}
      className={cn(
        'bg-white/[0.02] border border-[#2A2A2A] px-4 py-3 overflow-visible',
        accent && 'border-l-[3px] border-l-[#ADFF00]/25',
        onClick && 'active:bg-white/[0.04] active:border-[#404040] transition-colors cursor-pointer',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function MobileCardHeader({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('flex items-center justify-between mb-2', className)}>{children}</div>
}

export function MobileCardDivider() {
  return <div className="border-b border-[#1A1A1A] my-2" />
}
