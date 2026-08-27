// 通知中心（§25.9）：通知即入口——每条通知深链到对应视图。
import type { NotificationItem, ViewKey } from '../types';

export default function NotificationPanel({
  open,
  items,
  onGotoView,
}: {
  open: boolean;
  items: NotificationItem[];
  onGotoView: (v: ViewKey) => void;
}) {
  return (
    <div className={`notif-panel${open ? ' open' : ''}`}>
      <div className="notif-head">
        通知中心
        <span className="dimmer" style={{ fontWeight: 400, fontSize: 11 }}>
          全部已读 ✓
        </span>
      </div>
      {items.map((n) => (
        <div className="notif-item" key={n.id} onClick={() => onGotoView(n.view)}>
          <div className="notif-ico" style={{ background: n.iconBg }}>
            {n.icon}
          </div>
          <div>
            <div style={{ fontSize: 12.5 }}>
              {n.stockName ? (
                <>
                  <b>{n.stockName}</b>
                  {n.title}
                </>
              ) : (
                n.title
              )}
            </div>
            <div className="dimmer" style={{ fontSize: 10.5 }}>
              {n.sub}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
