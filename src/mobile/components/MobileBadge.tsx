import { cn } from '@/lib/utils'

export function MobileBadge({
  children,
  variant = 'default',
  className,
}: {
  children: React.ReactNode
  variant?: 'default' | 'green' | 'orange' | 'red' | 'muted'
  className?: string
}) {
  const variants: Record<string, string> = {
    default: 'bg-white/[0.04] text-[#888] border-[#2A2A2A]',
    green:   'bg-[#ADFF00]/[0.06] text-[#ADFF00] border-[#ADFF00]/[0.15]',
    orange:  'bg-[#FF5C00]/[0.06] text-[#FF5C00] border-[#FF5C00]/[0.15]',
    red:     'bg-red-500/[0.06] text-red-400 border-red-500/[0.15]',
    muted:   'bg-white/[0.02] text-[#555] border-transparent',
  }
  return (
    <span className={cn(
      'inline-flex items-center px-1.5 py-0.5 text-[10px] leading-none border rounded-sm font-mono',
      variants[variant],
      className,
    )}>
      {children}
    </span>
  )
}
