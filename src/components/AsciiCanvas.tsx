import { useEffect, useRef } from 'react';

// 混合字符集：修仙符文 + 财务术语 + 数字
const XIUXIAN_CHARS = '气丹灵脉阵符诀罡元炁鼎炉神机百炼玄天八卦乾坤震巽坎离艮兑甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥虚实阴阳无极太极归一';
const FINANCE_CHARS = 'PEPBROEEPSPEGMACDKDJRSI成交量市盈率市净率营收净利毛利率负债率现金流估值折价溢价多头空头 bullish bearish ALPHA BETA';
const NUM_CHARS = '0123456789.+-▼▲◆◇■□●○◐◑★☆';

const ALL_CHARS = XIUXIAN_CHARS + FINANCE_CHARS + NUM_CHARS;

// 股票模拟数据
const STOCK_TICKERS = ['000001.SZ', '600519.SH', '300750.SZ', '002594.SZ', '688981.SH', '603259.SH', '000858.SZ'];
const FINANCE_LABELS = ['PE', 'PB', 'ROE', 'EPS', '毛利率', '负债率', '现金流', '估值'];

const hash = (x: number, y: number) => {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453123;
  return s - Math.floor(s);
};

const smooth = (t: number) => t * t * (3 - 2 * t);

const noise2D = (x: number, y: number) => {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = x - ix;
  const fy = y - iy;
  const a = hash(ix, iy);
  const b = hash(ix + 1, iy);
  const c = hash(ix, iy + 1);
  const d = hash(ix + 1, iy + 1);
  const ux = smooth(fx);
  const uy = smooth(fy);
  return (
    a * (1 - ux) * (1 - uy) +
    b * ux * (1 - uy) +
    c * (1 - ux) * uy +
    d * ux * uy
  );
};

const clamp = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value));

function generateStockLine(seed: number): string {
  const ticker = STOCK_TICKERS[Math.floor(Math.abs(hash(seed, 1)) * STOCK_TICKERS.length)];
  const label = FINANCE_LABELS[Math.floor(Math.abs(hash(seed, 2)) * FINANCE_LABELS.length)];
  const val = (Math.abs(hash(seed, 3)) * 100).toFixed(2);
  const change = ((Math.abs(hash(seed, 4)) - 0.5) * 20).toFixed(2);
  const arrow = parseFloat(change) >= 0 ? '▲' : '▼';
  return `${ticker} ${label}:${val} ${arrow}${Math.abs(parseFloat(change)).toFixed(1)}%`;
}

export default function AsciiCanvas({ dense = false, centerX = 0.5, centerY = 0.45, furnace = false, cols: colsProp, noCore = false }: { dense?: boolean; centerX?: number; centerY?: number; furnace?: boolean; cols?: number; noCore?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let cols = 0;
    let rows = 0;
    let time = 0;
    let rafId = 0;
    let mouseX = -1000;
    let mouseY = -1000;
    let isVisible = true;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      width = parent.offsetWidth;
      height = parent.offsetHeight;

      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);

      cols = colsProp ?? (width < 768 ? (dense ? 70 : 50) : (dense ? 110 : 72));
      const cellW = width / cols;
      const cellH = cellW * 1.25;
      rows = Math.ceil(height / cellH);
    };

    const onMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      mouseX = e.clientX - rect.left;
      mouseY = e.clientY - rect.top;
    };

    // 缓存字符以提高性能
    const charCache: string[] = [];
    for (let i = 0; i < ALL_CHARS.length; i++) {
      charCache.push(ALL_CHARS[i]);
    }

    // 缓存股票行
    const stockLines: string[] = [];
    for (let i = 0; i < 50; i++) {
      stockLines.push(generateStockLine(i * 7.3));
    }

    const draw = () => {
      if (!isVisible) {
        rafId = requestAnimationFrame(draw);
        return;
      }

      ctx.fillStyle = '#050401';
      ctx.fillRect(0, 0, width, height);

      time += 0.0018;

      const cellW = width / cols;
      const cellH = cellW * 1.25;

      // 中心区域
      const coreX = width * centerX;
      const coreY = height * (furnace ? 0.55 : centerY);
      const coreRadius = Math.min(width, height) * (furnace ? 0.22 : 0.2);

      ctx.font = `${cellH * 0.78}px "IBM Plex Mono", "Noto Sans SC", monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      for (let r = 0; r < rows; r++) {
        const rowY = r * cellH + cellH / 2;
        const laneNorm = rowY / height;

        for (let c = 0; c < cols; c++) {
          const x = c * cellW + cellW / 2;
          const y = rowY;

          const dxCore = x - coreX;
          const dyCore = y - coreY;
          const distCore = furnace
            ? Math.hypot(dxCore * 0.65, dyCore)  // 炉型：横宽纵短，如鼎炉圆腹
            : Math.hypot(dxCore, dyCore);
          const normCore = distCore / coreRadius;
          const angleCore = Math.atan2(dyCore, dxCore);

          // 鼠标距离 — 200px范围内字符变亮 + 偏移
          const mouseDist = Math.hypot(x - mouseX, y - mouseY);
          const mouseField = mouseDist < 200 ? (1 - mouseDist / 200) : 0;
          const mouseBright = mouseDist < 160 ? (1 - mouseDist / 160) * 0.6 : 0;

          let char = '';
          let opacity = 0;
          let drawX = x;
          let drawY = y;
          let isCore = false;

          // 核心区域：高密度中文+财务混合字符（noCore 时跳过）
          if (!noCore && normCore < 1.0) {
            isCore = true;
            const coreIntensity = 1.0 - normCore;
            const idx = Math.floor(
              Math.abs(hash(c * 0.7 + time * 0.5, r * 0.7)) * ALL_CHARS.length
            );
            char = charCache[idx % charCache.length];

            opacity = clamp(0.3 + coreIntensity * 0.7, 0.15, 0.95);

            const edgeDisturb = Math.exp(-Math.abs(normCore - 1.0) * 6) * 3;
            drawX += -Math.sin(angleCore) * edgeDisturb;
            drawY += Math.cos(angleCore) * edgeDisturb * 0.4;

            // 鼠标：偏移+变亮
            if (mouseField > 0) {
              drawX += mouseField * 8;
              drawY += mouseField * 3;
              opacity = clamp(opacity + mouseBright, 0.15, 1.0);
            }
          } else {
            // 外部流动区域：股票数据瀑布流
            const stockLineIdx = Math.floor(
              Math.abs(hash(r * 13.7 + c * 3.1, Math.floor(time * 2))) * stockLines.length
            );
            const stockLine = stockLines[stockLineIdx];

            // 二维噪声向量场 — 每个网格点有独立的流动方向
            const flowAngle = noise2D(c * 0.08 + time * 0.15, r * 0.08 + time * 0.12) * Math.PI * 2;
            const flowSpeed = 0.6 + laneNorm * 0.4;
            const sampleX = c * 0.12 + Math.cos(flowAngle) * time * flowSpeed;
            const sampleY = r * 0.09 + Math.sin(flowAngle) * time * flowSpeed;

            const flowA = noise2D(sampleX, sampleY);
            const flowB = noise2D(sampleX * 1.6 + 15, sampleY * 0.7 - 10);
            const wave =
              Math.sin(sampleX * 1.7 + laneNorm * 12) * 0.5 +
              Math.cos(sampleY * 2.0 - time * 1.8) * 0.5;

            let density = flowA * 0.40 + flowB * 0.28 + (wave * 0.5 + 0.5) * 0.32;

            // 核心环绕带
            const orbitBand = Math.exp(-Math.pow((normCore - 1.08) * 5.5, 2));
            density += orbitBand * 0.18;

            // 鼠标：环绕带增强 + 外围字符也会变亮
            if (mouseField > 0 && orbitBand > 0.05) {
              density += mouseField * 0.25;
            }
            if (mouseBright > 0 && density > 0.35) {
              opacity = clamp(opacity + mouseBright * 0.5, 0.04, 0.8);
            }

            if (density > 0.35) {
              if (Math.abs(hash(c * 0.3 + r * 0.7, Math.floor(time))) > 0.4) {
                const linePos = Math.floor(Math.abs(hash(c, r + time * 0.3)) * stockLine.length);
                char = stockLine[linePos % stockLine.length];
              } else {
                const idx = Math.floor(
                  Math.abs(hash(c * 1.3 + time * 0.3, r * 1.1 - time * 0.2)) * XIUXIAN_CHARS.length
                );
                char = XIUXIAN_CHARS[idx % XIUXIAN_CHARS.length];
              }

              opacity = 0.04 + density * 0.28;

              drawX += (flowSpeed * 6 + flowB * 12) % (cellW * 3);
              drawY += Math.sin(sampleX * 2.0 + time + laneNorm * 7) * 1.6;

              const swirl = orbitBand * 8;
              drawX += -Math.sin(angleCore) * swirl;
              drawY += Math.cos(angleCore) * swirl * 0.5;
            }
          }

          if (!char || opacity <= 0.02) continue;

          // 配色：荧光绿系
          if (isCore) {
            const t = Math.sin(time * 0.5 + c * 0.05 + r * 0.05) * 0.5 + 0.5;
            const rv = Math.floor(173 * t);
            const gv = Math.floor(255);
            const bv = Math.floor(0 * t + 100 * (1 - t));
            ctx.fillStyle = `rgba(${rv}, ${gv}, ${bv}, ${opacity})`;
          } else {
            const bright = clamp(opacity * 2.2, 0.06, 0.55);
            ctx.fillStyle = `rgba(${Math.floor(120 * bright)}, ${Math.floor(200 * bright)}, ${Math.floor(60 * bright)}, ${opacity})`;
          }

          ctx.fillText(char, drawX, drawY);
        }
      }

      rafId = requestAnimationFrame(draw);
    };

    const observer = new IntersectionObserver(
      ([entry]) => {
        isVisible = entry.isIntersecting;
      },
      { threshold: 0.05 }
    );
    observer.observe(canvas);

    // 启动动画 — 3秒超时兜底，防止 fonts.ready 不 resolve 导致卡死
    const startAnimation = () => {
      resize();
      if (rafId === 0) draw();
    };
    const fontTimeout = setTimeout(startAnimation, 500);
    document.fonts.ready.then(() => {
      clearTimeout(fontTimeout);
      startAnimation();
    });

    window.addEventListener('resize', resize);
    window.addEventListener('mousemove', onMouseMove);

    return () => {
      cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize);
      window.removeEventListener('mousemove', onMouseMove);
      observer.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        display: 'block',
      }}
    />
  );
}
