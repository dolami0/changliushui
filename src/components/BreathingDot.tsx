// 活点 / 品牌呼吸点（§25.11：活点只标 AI 驱动的实时元素，静态内容禁用）
export function BreathingDot({ color }: { color?: string }) {
  if (color) {
    return <span className="live-dot" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />;
  }
  return <span className="live-dot" />;
}

/** 顶栏品牌呼吸点（logo 语言，仅顶栏一处） */
export function BrandDot() {
  return (
    <span className="breath-dot">
      <i />
    </span>
  );
}
