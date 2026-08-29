export function MobileLoading() {
  return (
    <div className="flex flex-col gap-3 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="bg-white/[0.02] border border-[#2A2A2A] rounded-sm p-3 animate-pulse">
          <div className="h-3 w-24 bg-white/[0.04] rounded mb-2" />
          <div className="h-4 w-48 bg-white/[0.03] rounded" />
        </div>
      ))}
    </div>
  )
}
