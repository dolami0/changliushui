import type { Pillar, PillarStatus } from '../types';

const STATUS_CLS: Record<PillarStatus, string> = {
  verified: 'st-verified',
  on_track: 'st-ontrack',
  at_risk: 'st-atrisk',
  pending: 'st-pending',
};

function scoreColor(s: number): string {
  return s >= 7 ? 'var(--down)' : s >= 5 ? 'var(--gold)' : 'var(--up)';
}

/** 支柱评分卡（03 区）：细条 + 分数 + status，只读；人工修正走 07 区 */
export default function PillarCard({ pillars }: { pillars: Pillar[] }) {
  return (
    <div>
      {pillars.map((p) => {
        const col = scoreColor(p.score);
        return (
          <div className="pillar" key={p.name}>
            <span className="pillar-name">{p.name}</span>
            <span className="pillar-bar">
              <i style={{ width: `${p.score * 10}%`, background: col }} />
            </span>
            <span className="pillar-score num" style={{ color: col }}>
              {p.score}
            </span>
            <span className={`status-chip ${STATUS_CLS[p.status]}`}>{p.status}</span>
          </div>
        );
      })}
    </div>
  );
}
