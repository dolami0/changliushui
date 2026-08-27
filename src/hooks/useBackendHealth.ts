import { useEffect, useState } from 'react';

/**
 * 后端存活检测 — 每 30s ping /api/status
 * 组件内调用: const online = useBackendHealth();
 * online===false 时展示离线提示
 */
export function useBackendHealth(): boolean {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const check = () => {
      fetch('/api/status')
        .then((r) => {
          if (!cancelled) setOnline(r.ok);
        })
        .catch(() => {
          if (!cancelled) setOnline(false);
        });
    };
    check();
    const id = setInterval(check, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return online;
}
