// ============================================================================
// 长流水位尺（§25.11 签名 #1）
// bear-base-bull 三色河道 + 4.5s 流动水光 + 呼吸灯珠指针——
// 估值区间呈现的唯一形态，禁止用普通进度条 / 刻度尺替代。
// ============================================================================

export interface RulerAnno {
  label: string;
  value: string;
  /** 荧光数：全站只给「概率加权空间」（§25.11 荧光数规则） */
  glow?: boolean;
  tone?: 'up' | 'down';
}

export default function WaterLevelRuler({
  bear,
  base,
  bull,
  pointerPct,
  hint,
  annos,
  compact = false,
  formatValue,
}: {
  bear: number;
  base: number;
  bull: number;
  /** 现价水位 0-100；切换标的时指针 .7s 滑动（CSS transition） */
  pointerPct: number;
  hint?: string;
  annos: RulerAnno[];
  compact?: boolean;
  /** 自定义三端标签格式化；默认 `(v) => ¥X.X`（价格）。定数录详情传 `(v) => v%` 显示 upside 百分比。 */
  formatValue?: (v: number) => string;
}) {
  const fmt = formatValue ?? ((v: number) => `¥${v.toFixed(1)}`);
  return (
    <div className="ruler-wrap" style={compact ? { paddingTop: 18 } : { paddingTop: 14 }}>
      <div className="ruler">
        <div className="seg-bear" />
        <div className="seg-base" />
        <div className="seg-bull" />
        <div className="ruler-pointer" style={{ left: `${pointerPct}%` }}>
          <span className="wp-dot" />
        </div>
      </div>
      <div className="ruler-labels">
        <span>bear {fmt(bear)}</span>
        <span>base {fmt(base)}</span>
        <span>bull {fmt(bull)}</span>
      </div>
      <div className="ruler-anno">
        {hint ? (
          <span className="dimmer" style={{ fontSize: 10.5 }}>
            {hint}
          </span>
        ) : null}
        {annos.map((a) => (
          <span key={a.label}>
            {a.label}{' '}
            <b className={`${a.tone === 'up' ? 'up' : a.tone === 'down' ? 'down' : ''}${a.glow ? ' glow-num' : ''}`.trim()}>
              {a.value}
            </b>
          </span>
        ))}
      </div>
    </div>
  );
}
