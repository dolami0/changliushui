export function MobileEmpty({ message = '暂无数据' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-[#555]">
      <span className="text-3xl mb-3 opacity-30">◇</span>
      <span className="text-xs font-mono tracking-wider">{message}</span>
    </div>
  )
}
