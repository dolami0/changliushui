import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { fetchTracking, isDemo, subscribeDemo } from './api';
import { usePolling } from './hooks';
import { ToastHost } from './toast';
import type { ViewKey } from './types';
import type { TrackingItem } from './services/cozeApi';
import { BrandDot, BreathingDot } from './components/BreathingDot';
import CommandPalette from './components/CommandPalette';
import NotificationPanel from './components/NotificationPanel';
import ArchiveView from './views/ArchiveView';
import AvatarView from './views/AvatarView';
import ConfigView from './views/ConfigView';
import FengwenView from './views/FengwenView';
import TrackingView from './views/TrackingView';

const NAV: { key: ViewKey; label: string }[] = [
  { key: 'tracking', label: '追踪令' },
  { key: 'archive', label: '藏经云' },
  { key: 'fengwen', label: '风闻入阵' },
  { key: 'avatar', label: '身外化身' },
  { key: 'config', label: '配置' },
];

function useClock(): string {
  const [now, setNow] = useState('--:--:--');
  useEffect(() => {
    const tick = () => {
      const d = new Date();
      const p = (n: number) => String(n).padStart(2, '0');
      setNow(`${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())} CST`);
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}

export default function App() {
  const [view, setView] = useState<ViewKey>('tracking');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [syncOpen, setSyncOpen] = useState(false);
  const [selectedCode, setSelectedCode] = useState('688820');
  const clock = useClock();
  const demo = useSyncExternalStore(subscribeDemo, isDemo);

  const trackingPoll = usePolling(() => fetchTracking().then((arr) => arr || []), 30000);
  const stocks: Pick<TrackingItem, 'stockCode' | 'stockName' | 'conviction'>[] = trackingPoll.data ?? [];

  const gotoView = useCallback((v: ViewKey) => {
    setView(v);
    setNotifOpen(false);
  }, []);

  const selectStock = useCallback((code: string) => setSelectedCode(code), []);

  const paletteHandlers = useMemo(
    () => ({
      gotoView,
      selectStock,
      openSync: () => {
        gotoView('tracking');
        setSyncOpen(true);
      },
      openNotifications: () => setNotifOpen(true),
    }),
    [gotoView, selectStock],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (e.key === '/' && !(e.target as HTMLElement).closest('input,textarea')) {
        e.preventDefault();
        setPaletteOpen(true);
      } else if (e.key === 'Escape') {
        setPaletteOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const t = (e.target as HTMLElement).closest('.spot') as HTMLElement | null;
      document.querySelectorAll<HTMLElement>('.spot').forEach((c) => {
        if (c !== t) c.style.removeProperty('--mx');
      });
      if (t) {
        const r = t.getBoundingClientRect();
        t.style.setProperty('--mx', `${e.clientX - r.left}px`);
        t.style.setProperty('--my', `${e.clientY - r.top}px`);
      }
    };
    document.addEventListener('mousemove', onMove);
    return () => document.removeEventListener('mousemove', onMove);
  }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const el = e.target as HTMLElement;
      if (!el.closest('.notif-panel') && !el.closest('#bell-btn')) setNotifOpen(false);
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, []);

  useEffect(() => {
    const content = document.getElementById('content');
    if (content) content.scrollTop = 0;
    const raf = requestAnimationFrame(() => {
      document.querySelectorAll<HTMLElement>('.view.active .card').forEach((c, i) => {
        c.style.animation = 'none';
        void c.offsetHeight;
        c.style.animation = `cardIn .5s cubic-bezier(.16,1,.3,1) ${Math.min(i * 0.045, 0.4)}s both`;
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [view]);

  useEffect(() => {
    const mobileTabs: ViewKey[] = ['tracking', 'archive'];
    let startX = 0, startY = 0, tracking = false;
    const isMobile = () => window.innerWidth < 768;
    const onTouchStart = (e: TouchEvent) => {
      if (!isMobile()) return;
      if (document.querySelector('.drawer.open, .modal-mask.open, .palette-mask.open')) return;
      const t = e.touches[0];
      startX = t.clientX;
      startY = t.clientY;
      tracking = true;
    };
    const onTouchEnd = (e: TouchEvent) => {
      if (!tracking || !isMobile()) return;
      tracking = false;
      const t = e.changedTouches[0];
      const dx = t.clientX - startX;
      const dy = t.clientY - startY;
      if (Math.abs(dx) < 60) return;
      if (Math.abs(dx) < Math.abs(dy) * 1.5) return;
      const idx = mobileTabs.indexOf(view);
      if (idx === -1) return;
      if (dx < 0 && idx < mobileTabs.length - 1) gotoView(mobileTabs[idx + 1]);
      else if (dx > 0 && idx > 0) gotoView(mobileTabs[idx - 1]);
    };
    const content = document.getElementById('content');
    if (!content) return;
    content.addEventListener('touchstart', onTouchStart, { passive: true });
    content.addEventListener('touchend', onTouchEnd, { passive: true });
    return () => {
      content.removeEventListener('touchstart', onTouchStart);
      content.removeEventListener('touchend', onTouchEnd);
    };
  }, [view, gotoView]);

  const badgeCount = (key: ViewKey): number | null => {
    if (key === 'tracking') return stocks.length || null;
    return null;
  };

  return (
    <>
      <div className="aurora aur-1" />
      <div className="aurora aur-2" />
      <div className="app">
        <div className="main">
          <div className="topbar">
            <div className="tb-brand">
              <BrandDot />
              <span className="brand-word">长流水</span>
              <span style={{ color: 'rgba(255,255,255,.1)', fontSize: 18, fontWeight: 200, margin: '0 2px' }}>|</span>
              <span className="tb-slogan">青山长流水，天天有钱花</span>
            </div>
            <nav className="tb-nav">
              {NAV.map((n) => {
                const cnt = badgeCount(n.key);
                return (
                  <button key={n.key} className={`tb-link${view === n.key ? ' active' : ''}`} onClick={() => gotoView(n.key)}>
                    {n.label}
                    {cnt !== null && <span className="nav-badge">{cnt}</span>}
                  </button>
                );
              })}
            </nav>
            <div className="topbar-right">
              <span className={`demo-ribbon${demo ? '' : ' live'}`} style={{ marginLeft: 0 }}>
                {demo ? '\u25C8 演示数据' : '\u25CF 已连接 /api'}
              </span>
              <span className="pill mono" style={{ letterSpacing: 1 }}>
                {clock}
              </span>
              <button className="pill" style={{ cursor: 'pointer', fontFamily: "'IBM Plex Mono',monospace" }} onClick={() => setPaletteOpen(true)}>
                \u2318K
              </button>
              <button
                className="icon-btn"
                id="bell-btn"
                title="通知"
                onClick={(e) => {
                  e.stopPropagation();
                  setNotifOpen((v) => !v);
                }}
              >
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8M10.3 21a2 2 0 0 0 3.4 0" />
                </svg>
                <span className="nub" />
              </button>
              <div className="avatar">掌</div>
            </div>
          </div>
          <div className="content" id="content">
            <TrackingView
              active={view === 'tracking'}
              selectedCode={selectedCode}
              onSelect={selectStock}
              syncOpen={syncOpen}
              setSyncOpen={setSyncOpen}
              onDataChange={trackingPoll.reload}
            />
            <ArchiveView active={view === 'archive'} gotoView={gotoView} />
            <FengwenView active={view === 'fengwen'} />
            <AvatarView active={view === 'avatar'} gotoView={gotoView} />
            <ConfigView active={view === 'config'} />
          </div>
        </div>
      </div>

      <NotificationPanel open={notifOpen} items={[]} onGotoView={gotoView} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} stocks={stocks} handlers={paletteHandlers} />
      <ToastHost />
    </>
  );
}
