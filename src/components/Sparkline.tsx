// 迷你走势 / 收益曲线（SVG 折线；移植原型 miniSpark 与 d-spark 渲染逻辑）
// 注：仅做展示映射（min-max 归一化），不涉估值计算，不违「LLM 不做算术」。

export function MiniSpark({ data, negative }: { data: number[]; negative: boolean }) {
  const pts = data.slice(-9);
  const max = Math.max(...pts);
  const min = Math.min(...pts);
  const path = pts
    .map((p, i) => `${((i / (pts.length - 1)) * 50).toFixed(1)},${(14 - ((p - min) / (max - min || 1)) * 12).toFixed(1)}`)
    .join(' ');
  const col = negative ? '#f6485c' : '#ADFF00';
  return (
    <svg className="row-spark" viewBox="0 0 52 16">
      <polyline points={path} fill="none" stroke={col} strokeWidth="1.2" strokeLinejoin="round" opacity=".85" />
    </svg>
  );
}

export function SparkArea({ data, negative }: { data: number[]; negative: boolean }) {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const path = data
    .map((p, i) => `${((i / (data.length - 1)) * 600).toFixed(0)},${(58 - ((p - min) / (max - min)) * 50).toFixed(1)}`)
    .join(' ');
  const col = negative ? '#f6485c' : '#2ebd85';
  return (
    <svg className="spark" viewBox="0 0 600 64" preserveAspectRatio="none">
      <defs>
        <linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={col} stopOpacity=".3" />
          <stop offset="1" stopColor={col} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,64 ${path} 600,64`} fill="url(#sg)" />
      <polyline points={path} fill="none" stroke={col} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}
