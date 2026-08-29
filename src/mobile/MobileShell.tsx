import type { ReactNode } from 'react'
import { HelpCircle } from 'lucide-react'
import { TabBar } from './navigation/TabBar'

export function MobileShell({ children }: { children: ReactNode }) {
  return (
    <div id="mobile-root" className="flex flex-col h-full bg-[#050401] text-[#F2F4F3]">
      <div className="flex-1 overflow-y-auto min-h-0">
        {children}
      </div>
      <div className="relative flex-shrink-0">
        <a
          href="/mobile-guide.html"
          className="absolute right-3 -top-8 flex items-center gap-1 text-xs text-[#555] hover:text-[#ADFF00] transition-colors z-10"
        >
          <HelpCircle size={14} />
          <span>帮助</span>
        </a>
        <TabBar />
      </div>
    </div>
  )
}
