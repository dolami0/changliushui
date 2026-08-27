// ==============================================================================
// 长流水前端 · 通用 hooks
// usePolling：30s setInterval 轮询（§25.10：系统节拍日/周级，无需 WebSocket）
// useTween：关键数字 450ms 三次方缓出滚动（§25.13 数字滚动）
// ==============================================================================
import { useEffect, useRef, useState } from 'react';

export function usePolling<T>(loader: () => Promise<T>, intervalMs = 30000, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [tick, setTick] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let dead = false;
    const run = () => {
      loaderRef.current()
        .then((d) => {
          if (!dead) setData(d);
        })
        .catch(() => {
          /* 轮询失败保持旧数据，下轮再试 */
        });
    };
    run();
    const id = window.setInterval(run, intervalMs);
    return () => {
      dead = true;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, tick, ...deps]);

  return { data, reload: () => setTick((t) => t + 1) };
}

/** 数字滚动：target 变化时从当前显示值 450ms 缓动滚至新值 */
export function useTween(target: number, duration = 450): number {
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(target);

  useEffect(() => {
    const from = displayRef.current;
    if (from === target) return;
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min((now - t0) / duration, 1);
      const e = 1 - Math.pow(1 - k, 3);
      const v = from + (target - from) * e;
      displayRef.current = v;
      setDisplay(v);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);

  return display;
}
