import { ChevronLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export function MobileBackHeader({
  title,
  action,
}: {
  title: string
  action?: React.ReactNode
}) {
  const navigate = useNavigate()

  return (
    <div className="sticky top-0 z-30 flex items-center justify-between h-12 px-3 border-b border-[#2A2A2A] bg-[#050401]/95 backdrop-blur-sm">
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-1 text-[#888] active:text-[#ADFF00] transition-colors"
      >
        <ChevronLeft size={18} />
        <span className="text-xs tracking-wider">返回</span>
      </button>
      <span className="text-sm text-[#F2F4F3] tracking-wider font-semibold truncate mx-2">
        {title}
      </span>
      <div className="w-16 flex justify-end">{action}</div>
    </div>
  )
}
