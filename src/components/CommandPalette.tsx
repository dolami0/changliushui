// ⌘K 命令面板（§25.13）：全局唤起（⌘K / Ctrl+K / `/`），三类条目
// （页面 / 追踪令 / 操作），模糊过滤 + ↑↓↵ 全键盘。
import { useEffect, useMemo, useRef, useState } from 'react';
import type { ViewKey } from '../types';

export interface PaletteHandlers {
  gotoView: (v: ViewKey) => void;
  selectStock: (code: string) => void;
  openSync: () => void;
  openNotifications: () => void;
}

export interface PaletteStock {
  stockCode: string;
  stockName: string;
  conviction?: number;
}

interface PalAction {
  k: string;
  t: string;
  sub: string;
  fn: () => void;
}

export default function CommandPalette({
  open,
  onClose,
  stocks,
  handlers,
}: {
  open: boolean;
  onClose: () => void;
  stocks: PaletteStock[];
  handlers: PaletteHandlers;
}) {
  const [query, setQuery] = useState('');
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const actions = useMemo<PalAction[]>(
    () => [
      { k: '页面', t: '追踪令 · 总控台', sub: '第一屏', fn: () => handlers.gotoView('tracking') },
      { k: '页面', t: '藏经云 · 定数录/天机峰', sub: '第二屏', fn: () => handlers.gotoView('archive') },
      {
        k: '页面',
        t: '风闻入阵 · 人工事件入口',
        sub: '投喂线索',
        fn: () => {
          handlers.gotoView('fengwen');
          window.setTimeout(() => document.getElementById('fw-text')?.focus(), 80);
        },
      },
      { k: '页面', t: '身外化身 · 复核工作台', sub: '待复核', fn: () => handlers.gotoView('avatar') },
      { k: '页面', t: '配置 · 调度与审批', sub: '', fn: () => handlers.gotoView('config') },
      ...stocks.map((s) => ({
        k: '追踪令',
        t: `${s.stockName} ${s.stockCode}`,
        sub: s.conviction !== undefined ? `信念 ${s.conviction}` : '',
        fn: () => {
          handlers.gotoView('tracking');
          handlers.selectStock(s.stockCode);
        },
      })),
      {
        k: '操作',
        t: '手动同步实盘持仓',
        sub: '当前标的',
        fn: () => {
          handlers.gotoView('tracking');
          handlers.openSync();
        },
      },
      { k: '操作', t: '打开通知中心', sub: '通知即入口', fn: () => handlers.openNotifications() },
    ],
    [stocks, handlers],
  );

  const filtered = useMemo(
    () => actions.filter((a) => !query || a.t.toLowerCase().includes(query.toLowerCase()) || a.k.includes(query)),
    [actions, query],
  );

  useEffect(() => {
    if (open) {
      setQuery('');
      setIdx(0);
      window.setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  useEffect(() => setIdx(0), [query]);

  const run = (a: PalAction | undefined) => {
    if (!a) return;
    a.fn();
    onClose();
  };

  return (
    <div
      className={`palette-mask${open ? ' open' : ''}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="palette">
        <div className="pal-input-row">
          <span style={{ color: 'rgba(173,255,0,.6)', fontFamily: "'IBM Plex Mono',monospace" }}>//</span>
          <input
            ref={inputRef}
            placeholder="跳转页面、切换追踪令、执行操作…"
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                setIdx((i) => Math.min(i + 1, filtered.length - 1));
              } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setIdx((i) => Math.max(i - 1, 0));
              } else if (e.key === 'Enter') {
                run(filtered[idx]);
              } else if (e.key === 'Escape') {
                onClose();
              }
            }}
          />
          <span className="dimmer" style={{ fontSize: 10, fontFamily: "'IBM Plex Mono',monospace" }}>
            ESC
          </span>
        </div>
        <div>
          {filtered.length === 0 ? (
            <div className="pal-item">
              <span className="pal-k">—</span>无匹配
            </div>
          ) : (
            filtered.map((a, i) => (
              <div key={`${a.k}-${a.t}`} className={`pal-item${i === idx ? ' on' : ''}`} onClick={() => run(a)} onMouseEnter={() => setIdx(i)}>
                <span className="pal-k">{a.k}</span>
                {a.t}
                <span className="pal-sub">{a.sub}</span>
              </div>
            ))
          )}
        </div>
        <div className="pal-foot">↑↓ 选择 · ↵ 执行 · 长流水总控台</div>
      </div>
    </div>
  );
}
