import type { CSSProperties } from 'react';
import type { SignalGrade } from '../types';

const CLS: Record<SignalGrade, string> = {
  S: 'sigS',
  A: 'sigA',
  B: 'sigB',
  C: 'sigC',
  D: 'sigD',
};

/** 信号徽章（§25.12 信号色：S #ADFF00 · A #ff7a00 · B #4cc2ff · C #8a93a5 · D #a78bfa） */
export default function SignalBadge({
  grade,
  size = 'md',
  style,
}: {
  grade: SignalGrade;
  size?: 'md' | 'lg';
  style?: CSSProperties;
}) {
  const sz = size === 'lg' ? { minWidth: 34, height: 30, fontSize: 15 } : undefined;
  return (
    <span className={`sig ${CLS[grade]}`} style={{ ...sz, ...style }}>
      {grade}
    </span>
  );
}

export function sigCls(grade: SignalGrade): string {
  return CLS[grade];
}
