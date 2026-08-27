import { useState } from 'react'
import { Send, Zap, Info } from 'lucide-react'
import { MobileCard } from '@/mobile/components/MobileCard'

const USAGE_EXAMPLES = [
  {
    title: '催化剂事件',
    text: 'XX公司发布新产品线，预计明年贡献营收20亿。行业空间测算：国内市场规模约500亿，公司当前市占率3%，目标10%。',
  },
  {
    title: '财报解读',
    text: 'XX公司Q3营收同比+45%，毛利率环比+3ppt至38%，经营杠杆开始显现。ROIC从12%提升至18%，超过资本成本。',
  },
  {
    title: '行业拐点',
    text: '新能源车渗透率突破15%，产业链调研显示上游材料供不应求。XX公司产能扩张计划明确，2026年产能翻倍。',
  },
]

export function SubmitForm() {
  const [newsContent, setNewsContent] = useState('')
  const [stockCode, setStockCode] = useState('')
  const [stockName, setStockName] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const [showExamples, setShowExamples] = useState(true)

  const handleSubmit = async () => {
    if (!newsContent.trim() || sending) return
    setSending(true)
    setError('')
    try {
      const TOKEN = import.meta.env.VITE_COZE_TOKEN || ''
      const resp = await fetch('https://api.coze.cn/v1/databases/7479116110479048754/records', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records: [{ fields: { news_content: newsContent.trim(), stock_code: stockCode.trim() || 'USER_INPUT', stock_name: stockName.trim() || '用户传讯', level: '3', mode: 'manual' } }],
        }),
      })
      if (!resp.ok) throw new Error(`Coze HTTP ${resp.status}`)
      setSent(true)
      setNewsContent('')
      setStockCode('')
      setStockName('')
      setTimeout(() => setSent(false), 4000)
      fetch('/api/trigger', { method: 'POST' }).catch(() => {})
    } catch (e) {
      setError(e instanceof Error ? e.message : '传讯失败')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="sticky top-0 z-20 flex items-center h-10 px-4 border-b border-[#2A2A2A] bg-[#050401]/95 backdrop-blur-sm flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tracking-wider">风闻入阵</span>
          <span className="text-[10px] text-[#FF5C00] border border-[#FF5C00]/20 bg-[#FF5C00]/[0.04] px-1.5 py-0.5 rounded-sm">⚒ 施工升级中</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* 说明卡片 */}
        <MobileCard accent>
          <div className="flex items-center gap-2 mb-2">
            <Zap size={14} className="text-[#ADFF00]" />
            <span className="text-sm font-semibold text-[#ADFF00] tracking-wider">宗门传讯</span>
          </div>
          <p className="text-sm text-[#888] leading-relaxed">
            粘贴资讯内容或分析命题，直接送入估值引擎炼化。系统将自动触发 4-Agent 估值重构管线，
            生成完整的定数录报告。
          </p>
        </MobileCard>

        {/* 处理流程说明 */}
        <MobileCard>
          <div className="flex items-center gap-2 mb-3">
            <Info size={14} className="text-[#ADFF00]" />
            <span className="text-sm font-semibold tracking-wider">处理流程</span>
          </div>
          <div className="space-y-2">
            {['Agent-0 预路由 → 行业分类与数据需求', 'Agent-1 数据炼器 → 分层拉取财务数据', 'Agent-2 路由判官 → 模型选择与案例比对', 'Agent-3 推演裁决 → 三情景估值与BS检测'].map((step, i) => (
              <div key={i} className="flex items-center gap-2 text-sm">
                <span className="text-[#ADFF00] font-semibold">{i + 1}.</span>
                <span className="text-[#AAA]">{step}</span>
              </div>
            ))}
          </div>
        </MobileCard>

        {/* 错误提示 */}
        {error && (
          <div className="px-4 py-2">
            <div className="bg-red-500/[0.06] border border-red-500/20 rounded-sm px-3 py-2 text-sm text-red-400">{error}</div>
          </div>
        )}

        {/* 成功提示 */}
        {sent && (
          <div className="px-4 py-2">
            <div className="bg-[#ADFF00]/[0.06] border border-[#ADFF00]/20 rounded-sm px-3 py-2 text-sm text-[#ADFF00]">
              传讯已入阵，估值引擎将自动处理
            </div>
          </div>
        )}

        {/* 表单 */}
        <div className="px-4 py-3 space-y-3">
          <div>
            <label className="block text-sm text-[#888] mb-1.5 tracking-wider">资讯内容 *</label>
            <textarea
              value={newsContent}
              onChange={(e) => setNewsContent(e.target.value)}
              placeholder="在此粘贴资讯内容或分析命题..."
              rows={6}
              className="w-full bg-white/[0.04] border border-[#2A2A2A] rounded-sm px-3 py-2.5 text-sm text-[#F2F4F3] placeholder:text-[#444] resize-none outline-none focus:border-[#ADFF00]/40 transition-colors"
            />
            <div className="text-xs text-[#555] mt-1 text-right">{newsContent.length} 字</div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-[#888] mb-1.5 tracking-wider">股票代码</label>
              <input value={stockCode} onChange={(e) => setStockCode(e.target.value)} placeholder="可选"
                className="w-full bg-white/[0.04] border border-[#2A2A2A] rounded-sm px-3 py-2.5 text-sm text-[#F2F4F3] placeholder:text-[#444] outline-none focus:border-[#ADFF00]/40 transition-colors" />
            </div>
            <div>
              <label className="block text-sm text-[#888] mb-1.5 tracking-wider">股票名称</label>
              <input value={stockName} onChange={(e) => setStockName(e.target.value)} placeholder="可选"
                className="w-full bg-white/[0.04] border border-[#2A2A2A] rounded-sm px-3 py-2.5 text-sm text-[#F2F4F3] placeholder:text-[#444] outline-none focus:border-[#ADFF00]/40 transition-colors" />
            </div>
          </div>

          <button onClick={handleSubmit} disabled={sending || !newsContent.trim()}
            className="w-full flex items-center justify-center gap-2 py-3.5 border rounded-sm text-base tracking-wider transition-all active:scale-[0.98]"
            style={{
              background: sending || !newsContent.trim() ? 'rgba(173,255,0,0.03)' : 'rgba(173,255,0,0.08)',
              borderColor: sending || !newsContent.trim() ? 'rgba(173,255,0,0.1)' : 'rgba(173,255,0,0.25)',
              color: sending || !newsContent.trim() ? '#555' : '#ADFF00',
              opacity: newsContent.trim() ? 1 : 0.5,
            }}>
            {sending ? <><span className="animate-spin">◇</span>传讯中...</> : sent ? <><Send size={16} />已传讯</> : <><Send size={16} />传讯入阵</>}
          </button>
        </div>

        {/* 示例 — fill empty space */}
        <div className="px-4 pb-6">
          <button
            onClick={() => setShowExamples(!showExamples)}
            className="flex items-center gap-1.5 text-xs text-[#555] mb-2"
          >
            <Info size={12} />
            {showExamples ? '收起示例' : '查看输入示例'}
          </button>
          {showExamples && (
            <div className="space-y-2">
              {USAGE_EXAMPLES.map((ex, i) => (
                <MobileCard key={i}>
                  <div className="text-xs text-[#ADFF00] font-semibold mb-1.5">{ex.title}</div>
                  <p className="text-sm text-[#888] leading-relaxed">{ex.text}</p>
                  <button
                    onClick={() => setNewsContent(ex.text)}
                    className="mt-2 text-xs text-[#888] border border-[#2A2A2A] px-2 py-0.5 rounded-sm active:border-[#ADFF00]/40 active:text-[#ADFF00]"
                  >
                    填入
                  </button>
                </MobileCard>
              ))}
            </div>
          )}
        </div>

        <div className="h-10" />
      </div>
    </div>
  )
}
