import { FileText, Target, Eye, Send, MessageCircle } from 'lucide-react'

export interface TabDef {
  id: string
  label: string
  icon: typeof FileText
  route: string
}

export const TABS: TabDef[] = [
  { id: 'dingshulu', label: '定数录', icon: FileText, route: '/m/dingshulu' },
  { id: 'tracking',  label: '跟踪令', icon: Target, route: '/m/tracking' },
  { id: 'tianyan',   label: '天机峰', icon: Eye, route: '/m/tianyan' },
  { id: 'submit',    label: '风闻入阵', icon: Send, route: '/m/submit' },
  { id: 'avatar',    label: '身外化身', icon: MessageCircle, route: '/m/avatar' },
]
