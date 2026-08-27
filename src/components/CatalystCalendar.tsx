import type { Catalyst } from '../types';

/** 催化剂日历（04 区）：倒计时 / pending / verified 三态，已兑现置灰 */
export default function CatalystCalendar({ items }: { items: Catalyst[] }) {
  return (
    <div>
      {items.map((c) => (
        <div className="cata" key={`${c.date}-${c.name}`} style={c.done ? { opacity: 0.55 } : undefined}>
          <span className="cata-date mono">{c.date}</span>
          <span className="cata-name">{c.name}</span>
          {c.countdown ? (
            <span className="countdown">{c.countdown}</span>
          ) : (
            <span className={`status-chip ${c.status === 'verified' ? 'st-verified' : 'st-pending'}`}>{c.status ?? 'pending'}</span>
          )}
        </div>
      ))}
    </div>
  );
}
