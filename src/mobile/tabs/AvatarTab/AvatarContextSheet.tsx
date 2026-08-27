import { MobileSheet } from '@/mobile/components/MobileSheet'

export const CONTEXT_MODULES = [
  { id: 'a0_theme', label: 'A0 投资主题', cat: '核心' },
  { id: 'a0_deduction', label: 'A0 事件推演', cat: '核心' },
  { id: 'a0_reasoning', label: 'A0 推理依据', cat: '核心' },
  { id: 'a0_adversarial', label: 'A0 对抗思考', cat: '核心' },
  { id: 'a0_knowledge', label: 'A0 知识补充', cat: '核心' },
  { id: 'a0_research', label: 'A0 行业研究', cat: '核心' },
  { id: 'a0_raw_event', label: 'A0 原始事件', cat: '核心' },
  { id: 'a0_future', label: 'A0 前瞻', cat: '核心' },
  { id: 'agent1', label: 'Agent-1 财务数据', cat: '核心' },
  { id: 'agent2', label: 'Agent-2 路由判决', cat: '核心' },
  { id: 'agent3', label: 'Agent-3 推演裁决', cat: '核心' },
  { id: 'baseline', label: '基线分析', cat: '核心' },
  { id: 'scenarios', label: '三情景估值', cat: '核心' },
  { id: 'bs', label: 'BS 清醒度检测', cat: '匹配' },
  { id: 'confidence', label: '置信度评估', cat: '匹配' },
  { id: 'cases', label: '案例比对', cat: '匹配' },
]

export function AvatarContextSheet({
  open,
  onClose,
  selected,
  onToggle,
}: {
  open: boolean
  onClose: () => void
  selected: Set<string>
  onToggle: (id: string) => void
}) {
  return (
    <MobileSheet open={open} onClose={onClose} title="上下文模块">
      <div className="space-y-3">
        {(['核心', '匹配'] as const).map((cat) => (
          <div key={cat}>
            <div className="text-[10px] font-mono text-[#ADFF00] tracking-wider mb-2">{cat}</div>
            <div className="space-y-1">
              {CONTEXT_MODULES.filter((m) => m.cat === cat).map((m) => {
                const isOn = selected.has(m.id)
                return (
                  <button
                    key={m.id}
                    onClick={() => onToggle(m.id)}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-sm border transition-colors"
                    style={{
                      background: isOn ? 'rgba(173,255,0,0.04)' : 'rgba(255,255,255,0.01)',
                      borderColor: isOn ? 'rgba(173,255,0,0.2)' : '#2A2A2A',
                    }}
                  >
                    <span className={`text-xs font-mono ${isOn ? 'text-[#ADFF00]' : 'text-[#888]'}`}>
                      {m.label}
                    </span>
                    <span className={`text-[10px] font-mono ${isOn ? 'text-[#ADFF00]' : 'text-[#555]'}`}>
                      {isOn ? '✓' : '—'}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}

        {/* Quick actions */}
        <div className="flex gap-2 pt-2 border-t border-[#2A2A2A]">
          <button
            onClick={() => {
              CONTEXT_MODULES.forEach((m) => onToggle(m.id))
            }}
            className="flex-1 py-1.5 border border-[#2A2A2A] rounded-sm text-[10px] font-mono text-[#888] active:text-[#ADFF00] active:border-[#ADFF00]/30 transition-colors"
          >
            全选
          </button>
          <button
            onClick={onClose}
            className="flex-1 py-1.5 border border-[#ADFF00]/25 bg-[#ADFF00]/[0.06] rounded-sm text-[10px] font-mono text-[#ADFF00] active:bg-[#ADFF00]/[0.12] transition-colors"
          >
            确认
          </button>
        </div>
      </div>
    </MobileSheet>
  )
}
