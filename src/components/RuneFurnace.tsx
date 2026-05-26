import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBackendHealth } from '../hooks/useBackendHealth';
import { fetchDingshulu } from '../services/cozeApi';

/* ------------------------------------------------------------------ */
/*  RuneFurnace — 符文炉 Canvas 动画 + HTML 指标层                       */
/*  SVG-free 纯 Canvas 炼丹炉：外八卦阵 → 符文环 → 炉体 → 阵眼核心         */
/* ------------------------------------------------------------------ */

const FURNACE_W = 520;
const FURNACE_H = 520;
const CX = FURNACE_W / 2;
const CY = FURNACE_H / 2;

const TRIGRAMS = ['☰', '☱', '☲', '☳', '☴', '☵', '☶', '☷'];
const RUNE_CHARS = '乾坤震巽坎离艮兑丹气灵脉阵符诀罡元炁鼎炉神机百炼估值天机追踪炼化';

interface Ember {
  x: number; y: number;
  vx: number; vy: number;
  life: number; maxLife: number;
  size: number; alpha: number;
}

interface RuneParticle {
  angle: number;
  radius: number;
  speed: number;
  char: string;
  alpha: number;
  phase: number;
}

/* ================================================================== */
/*  RuneFurnaceCore — canvas 动画                                      */
/* ================================================================== */
function RuneFurnaceCore({ active, totalReports }: { active: boolean; totalReports: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouse = useRef({ x: CX, y: CY, tx: CX, ty: CY });
  const embers = useRef<Ember[]>([]);
  const runeParticles = useRef<RuneParticle[]>([]);
  const rafRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    if (!ctx) return;

    let t0 = performance.now();
    let time = 0;

    /* ---- 初始化符文粒子 ---- */
    if (runeParticles.current.length === 0) {
      for (let i = 0; i < 40; i++) {
        const angle = (i / 40) * Math.PI * 2;
        runeParticles.current.push({
          angle,
          radius: 155 + Math.random() * 30,
          speed: 0.08 + Math.random() * 0.15,
          char: RUNE_CHARS[Math.floor(Math.random() * RUNE_CHARS.length)],
          alpha: 0.15 + Math.random() * 0.35,
          phase: Math.random() * Math.PI * 2,
        });
      }
    }

    function spawnEmber(): Ember {
      const a = (Math.random() - 0.5) * 1.2;
      return {
        x: CX + Math.sin(a) * (20 + Math.random() * 50),
        y: CY - 50 + Math.random() * 30,
        vx: (Math.random() - 0.5) * 0.4,
        vy: -(0.3 + Math.random() * 1.2),
        life: 0,
        maxLife: 40 + Math.random() * 80,
        size: 0.5 + Math.random() * 2.0,
        alpha: 0,
      };
    }

    function drawOctagonFrame(t: number) {
      const r = 165;
      const sides = 8;
      ctx.save();
      ctx.translate(CX, CY);
      ctx.rotate(t * 0.0001);
      ctx.strokeStyle = 'rgba(173,255,0,0.12)';
      ctx.lineWidth = 0.8;
      ctx.shadowColor = 'rgba(173,255,0,0.08)';
      ctx.shadowBlur = 6;
      ctx.beginPath();
      for (let i = 0; i <= sides; i++) {
        const a = (i / sides) * Math.PI * 2 - Math.PI / 2;
        const x = Math.cos(a) * r;
        const y = Math.sin(a) * r;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;

      // 八卦符号
      ctx.fillStyle = 'rgba(173,255,0,0.2)';
      ctx.font = '18px "Noto Sans SC", serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      for (let i = 0; i < 8; i++) {
        const a = (i / 8) * Math.PI * 2 - Math.PI / 2;
        const x = Math.cos(a) * (r + 18);
        const y = Math.sin(a) * (r + 18);
        const alpha = 0.12 + Math.sin(t * 0.0008 + i) * 0.06;
        ctx.fillStyle = `rgba(173,255,0,${alpha})`;
        ctx.fillText(TRIGRAMS[i], x, y);
      }
      ctx.restore();
    }

    function drawRuneRing(t: number) {
      ctx.save();
      ctx.translate(CX, CY);
      const ringRadius = 135;
      ctx.strokeStyle = 'rgba(173,255,0,0.08)';
      ctx.lineWidth = 0.5;
      ctx.setLineDash([4, 8]);
      ctx.lineDashOffset = t * 0.02;
      ctx.beginPath();
      ctx.arc(0, 0, ringRadius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);

      // 符文粒子沿环旋转
      for (const p of runeParticles.current) {
        p.angle += p.speed * 0.003;
        const wobble = Math.sin(t * 0.001 + p.phase) * 8;
        const r = p.radius + wobble;
        const x = Math.cos(p.angle) * r;
        const y = Math.sin(p.angle) * r;
        const alphaWave = p.alpha * (0.6 + Math.sin(t * 0.002 + p.phase) * 0.4);
        ctx.fillStyle = `rgba(173,255,0,${alphaWave.toFixed(2)})`;
        ctx.font = '11px "IBM Plex Mono", "Noto Sans SC", monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(p.char, x, y);
      }
      ctx.restore();
    }

    function drawFurnaceBody(t: number) {
      ctx.save();
      ctx.translate(CX, CY);
      const breathe = 1 + Math.sin(t * 0.0008) * 0.03;

      // 炉体外轮廓 — 三层渐变
      for (let layer = 0; layer < 3; layer++) {
        const radii = [78, 68, 54][layer];
        const alphas = [0.06, 0.1, 0.16][layer];
        ctx.beginPath();
        // 不规则炉体
        for (let i = 0; i <= 60; i++) {
          const a = (i / 60) * Math.PI * 2;
          const rr = radii * breathe + Math.sin(a * 3 + t * 0.001) * 3 + Math.sin(a * 7 + t * 0.0007) * 2;
          const x = Math.cos(a) * rr;
          const y = Math.sin(a) * rr * 0.85;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        const grad = ctx.createRadialGradient(0, 0, radii[layer] * 0.4, 0, 0, radii[layer] * 1.1);
        grad.addColorStop(0, `rgba(173,255,0,${alphas * 2})`);
        grad.addColorStop(0.5, `rgba(173,255,0,${alphas})`);
        grad.addColorStop(1, 'rgba(173,255,0,0)');
        ctx.fillStyle = grad;
        ctx.fill();
      }

      // 炉体边框
      ctx.beginPath();
      for (let i = 0; i <= 60; i++) {
        const a = (i / 60) * Math.PI * 2;
        const rr = 80 * breathe + Math.sin(a * 3 + t * 0.001) * 3;
        const x = Math.cos(a) * rr;
        const y = Math.sin(a) * rr * 0.85;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.strokeStyle = 'rgba(173,255,0,0.2)';
      ctx.lineWidth = 1.2;
      ctx.shadowColor = 'rgba(173,255,0,0.15)';
      ctx.shadowBlur = 10;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // 炉耳 (两侧把手)
      for (const side of [-1, 1]) {
        ctx.beginPath();
        const earX = side * 82;
        ctx.arc(earX, -10, 22, side * 0.8, side * 2.4);
        ctx.strokeStyle = 'rgba(173,255,0,0.2)';
        ctx.lineWidth = 2.5;
        ctx.stroke();
      }

      ctx.restore();
    }

    function drawCore(t: number) {
      ctx.save();
      ctx.translate(CX, CY);
      const pulse = active
        ? 0.7 + Math.sin(t * 0.003) * 0.3 + Math.sin(t * 0.007) * 0.1
        : 0.3 + Math.sin(t * 0.001) * 0.1;

      // 阵眼核心光晕
      for (let i = 3; i >= 0; i--) {
        const r = [40, 25, 12, 4][i];
        const alphas = [0.04, 0.12, 0.35, 0.7];
        const grad = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
        const a = alphas[i] * pulse;
        grad.addColorStop(0, `rgba(173,255,0,${a})`);
        grad.addColorStop(0.5, `rgba(173,255,0,${a * 0.5})`);
        grad.addColorStop(1, 'rgba(173,255,0,0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(0, 0, r, 0, Math.PI * 2);
        ctx.fill();
      }

      // 内核亮点
      const coreGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, 8);
      coreGrad.addColorStop(0, `rgba(240,255,220,${0.9 * pulse})`);
      coreGrad.addColorStop(0.3, `rgba(173,255,0,${0.6 * pulse})`);
      coreGrad.addColorStop(1, 'rgba(173,255,0,0)');
      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(0, 0, 8, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    function drawEmbers(t: number) {
      const spawnRate = active ? 0.5 : 0.08;
      if (embers.current.length < 55 && Math.random() < spawnRate) {
        embers.current.push(spawnEmber());
      }
      const survivors: Ember[] = [];
      for (const e of embers.current) {
        e.life++;
        if (e.life >= e.maxLife) continue;
        const prog = e.life / e.maxLife;
        e.alpha = prog < 0.15 ? prog / 0.15 : 1 - (prog - 0.15) / 0.85;
        e.x += e.vx + Math.sin(t * 0.003 + e.life * 0.1) * 0.15;
        e.y += e.vy;
        e.vy -= 0.003; // 上升加速

        const progColor = prog;
        const r = Math.floor(173 + (1 - progColor) * 82);
        const g = Math.floor(255 * (1 - progColor * 0.6));
        const b = Math.floor(200 * progColor);
        ctx.fillStyle = `rgba(${r},${g},${b},${(e.alpha * 0.6).toFixed(2)})`;
        ctx.shadowColor = ctx.fillStyle;
        ctx.shadowBlur = e.size * 2;
        ctx.beginPath();
        ctx.arc(e.x, e.y, e.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        survivors.push(e);
      }
      embers.current = survivors;
    }

    function drawBasePlatform(t: number) {
      ctx.save();
      ctx.translate(CX, CY + 95);
      const w = 140;
      // 炉基座
      const grad = ctx.createLinearGradient(-w, 0, w, 0);
      grad.addColorStop(0, 'rgba(173,255,0,0)');
      grad.addColorStop(0.3, 'rgba(173,255,0,0.08)');
      grad.addColorStop(0.5, 'rgba(173,255,0,0.12)');
      grad.addColorStop(0.7, 'rgba(173,255,0,0.08)');
      grad.addColorStop(1, 'rgba(173,255,0,0)');
      ctx.fillStyle = grad;
      ctx.fillRect(-w, -4, w * 2, 8);

      // 基座线
      ctx.strokeStyle = 'rgba(173,255,0,0.15)';
      ctx.lineWidth = 0.6;
      ctx.beginPath();
      ctx.moveTo(-w, 0);
      ctx.lineTo(w, 0);
      ctx.stroke();

      // 阵法刻线
      for (let i = -3; i <= 3; i++) {
        const x = i * 28;
        ctx.strokeStyle = 'rgba(173,255,0,0.06)';
        ctx.lineWidth = 0.4;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x + (i > 0 ? -8 : 8), 14);
        ctx.stroke();
      }
      ctx.restore();
    }

    function loop(now: number) {
      const t = now - t0;
      time = t;
      ctx.clearRect(0, 0, FURNACE_W, FURNACE_H);

      // 鼠标平滑追踪
      mouse.current.tx += (mouse.current.x - mouse.current.tx) * 0.03;
      mouse.current.ty += (mouse.current.y - mouse.current.ty) * 0.03;

      // 整体氛围光
      const bgGrad = ctx.createRadialGradient(CX, CY, 30, CX, CY, 280);
      bgGrad.addColorStop(0, 'rgba(5,4,1,0.3)');
      bgGrad.addColorStop(0.5, 'rgba(5,4,1,0.7)');
      bgGrad.addColorStop(1, '#050401');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, FURNACE_W, FURNACE_H);

      drawOctagonFrame(t);
      drawBasePlatform(t);
      drawRuneRing(t);
      drawFurnaceBody(t);
      drawEmbers(t);
      drawCore(t);

      rafRef.current = requestAnimationFrame(loop);
    }

    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [active, totalReports]);

  return (
    <canvas
      ref={canvasRef}
      width={FURNACE_W}
      height={FURNACE_H}
      onMouseMove={(e) => {
        const r = canvasRef.current?.getBoundingClientRect();
        if (r) {
          const scale = FURNACE_W / r.width;
          mouse.current.x = (e.clientX - r.left) * scale;
          mouse.current.y = (e.clientY - r.top) * scale;
        }
      }}
      onMouseLeave={() => {
        mouse.current.x = CX;
        mouse.current.y = CY;
      }}
      style={{
        display: 'block',
        width: '100%',
        height: '100%',
        cursor: 'pointer',
      }}
    />
  );
}

/* ================================================================== */
/*  RuneFurnace — 对外组件 = Canvas + HTML 覆盖层                        */
/* ================================================================== */
export default function RuneFurnace({ mobile }: { mobile: boolean }) {
  const navigate = useNavigate();
  const online = useBackendHealth();
  const [totalReports, setTotalReports] = useState(0);
  const [engineStatus, setEngineStatus] = useState<{
    running: boolean; activeJobs: number; completedJobs: number;
  }>({ running: false, activeJobs: 0, completedJobs: 0 });
  const [hover, setHover] = useState(false);

  useEffect(() => {
    fetchDingshulu().then((ds) => setTotalReports(ds.length)).catch(() => setTotalReports(-1));
    const check = () => {
      fetch('/api/status')
        .then((r) => r.json())
        .then((s) => setEngineStatus({
          running: s.scheduler_running,
          activeJobs: (s.active_jobs || []).length,
          completedJobs: (s.completed_jobs || []).length,
        }))
        .catch(() => {});
    };
    check();
    const id = setInterval(check, 15_000);
    return () => clearInterval(id);
  }, []);

  const isBurning = engineStatus.activeJobs > 0;
  const statusColor = !online ? '#FF5C00' : isBurning ? '#FF5C00' : '#ADFF00';
  const statusText = !online ? '离线' : isBurning ? '炼化中' : '运转中';

  return (
    <div
      onClick={() => navigate('/dashboard')}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title="进入估值重构仪表盘"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {/* Canvas 层 */}
      <div style={{ position: 'absolute', inset: 0 }}>
        <RuneFurnaceCore active={isBurning} totalReports={totalReports} />
      </div>

      {/* HTML 覆盖层 — 中心指标 */}
      <div style={{
        position: 'relative', zIndex: 5,
        textAlign: 'center', pointerEvents: 'none',
        transform: hover ? 'scale(1.04)' : 'scale(1)',
        transition: 'transform 0.4s cubic-bezier(0.22, 0.61, 0.36, 1)',
        filter: hover
          ? 'drop-shadow(0 0 18px rgba(173,255,0,0.4))'
          : 'drop-shadow(0 0 8px rgba(173,255,0,0.2))',
      }}>
        {/* 状态指示 */}
        <div style={{ marginBottom: '10px' }}>
          <span style={{
            display: 'inline-block',
            width: '8px', height: '8px', borderRadius: '50%',
            background: statusColor,
            boxShadow: `0 0 12px ${statusColor}80`,
            animation: isBurning ? 'pulse 1.2s ease-in-out infinite' : 'pulse 2.5s ease-in-out infinite',
            marginRight: '8px',
          }} />
          <span style={{
            fontFamily: "'Space Mono', monospace",
            fontSize: '11px', color: statusColor,
            letterSpacing: '0.15em',
          }}>
            {statusText}
          </span>
        </div>

        {/* 主标题 */}
        <h2 style={{
          fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace",
          fontSize: mobile ? '20px' : '26px', fontWeight: 400,
          color: '#ADFF00', letterSpacing: '0.1em', margin: '0 0 8px 0',
          textShadow: isBurning
            ? '0 0 28px rgba(173,255,0,0.6), 0 0 60px rgba(255,92,0,0.25)'
            : '0 0 16px rgba(173,255,0,0.3)',
        }}>
          符文炉
        </h2>

        {/* 指标数字 */}
        <div style={{
          display: 'flex', gap: '20px', justifyContent: 'center',
          marginBottom: '10px',
          padding: '10px 20px',
          background: 'rgba(5,4,1,0.6)',
          border: '1px solid rgba(173,255,0,0.1)',
        }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#F2F4F3' }}>
              {engineStatus.completedJobs.toLocaleString()}
            </div>
            <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', marginTop: '2px' }}>
              已炼化
            </div>
          </div>
          <div style={{ width: '1px', background: 'rgba(255,255,255,0.06)' }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: '#F2F4F3' }}>
              {totalReports < 0 ? '—' : totalReports.toLocaleString()}
            </div>
            <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', marginTop: '2px' }}>
              定数录
            </div>
          </div>
          <div style={{ width: '1px', background: 'rgba(255,255,255,0.06)' }} />
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '18px', color: isBurning ? '#FF5C00' : '#ADFF00' }}>
              {engineStatus.activeJobs}
            </div>
            <div style={{ fontFamily: "'Space Mono', monospace", fontSize: '9px', color: '#555', marginTop: '2px' }}>
              炼化中
            </div>
          </div>
        </div>

        {/* 进入提示 */}
        <div style={{
          fontFamily: "'Space Mono', monospace", fontSize: '10px',
          color: '#ADFF00', letterSpacing: '0.1em', opacity: hover ? 0.9 : 0.4,
          transition: 'opacity 0.3s',
        }}>
          → 进入仪表盘
        </div>
      </div>

      {/* hover 外光晕 */}
      <div style={{
        position: 'absolute', inset: '-40px', zIndex: 0, pointerEvents: 'none',
        borderRadius: '50%', opacity: hover ? 0.6 : 0,
        transition: 'opacity 0.5s',
        background: 'radial-gradient(ellipse at center, rgba(173,255,0,0.08) 0%, transparent 70%)',
      }} />
    </div>
  );
}
