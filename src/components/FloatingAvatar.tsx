import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

const W = 300, H = 380;
const CX = W / 2, CY = H / 2 + 10;

interface Particle {
  x: number; y: number;
  angle: number; dist: number; speed: number;
  life: number; maxLife: number; size: number; armIdx: number;
}

/* ================================================================== */
/*  FloatingAvatar — 黑洞 + 不规则旋臂 + 吸光暗核                        */
/* ================================================================== */
export default function FloatingAvatar() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const navigate = useNavigate();
  const mouse = useRef({ x: CX, y: CY, tx: CX, ty: CY });
  const particles = useRef<Particle[]>([]);

  function spawn(bhX: number, bhY: number): Particle {
    const armIdx = Math.floor(Math.random() * 3);
    const a = Math.random() * Math.PI * 2;
    return {
      x: bhX + Math.cos(a) * (80 + Math.random() * 50),
      y: bhY + Math.sin(a) * (60 + Math.random() * 40),
      angle: a + Math.PI + (Math.random() - 0.5) * 0.5,
      dist: 80 + Math.random() * 50,
      speed: 0.2 + Math.random() * 0.7,
      life: 0,
      maxLife: 40 + Math.random() * 90,
      size: 0.4 + Math.random() * 1.8,
      armIdx,
    };
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    if (!ctx) return;
    let raf = 0;
    const t0 = performance.now();

    // 旋臂形状参数 — 非对称
    const arms = [
      { twist: 2.8, width: 0.7, offset: 0, stretch: 1.1 },
      { twist: 3.5, width: 0.5, offset: 2.4, stretch: 0.85 },
      { twist: 2.2, width: 0.9, offset: 4.5, stretch: 1.0 },
    ];

    function drawArm(
      bhX: number, bhY: number,
      t: number, twist: number, width: number,
      offset: number, stretch: number, alphaMul: number
    ) {
      ctx.save();
      ctx.translate(bhX, bhY);
      // 绘制旋臂 — 对数螺旋
      ctx.beginPath();
      const steps = 80;
      for (let i = 0; i < steps; i++) {
        const frac = i / steps; // 0=外缘, 1=中心
        const r = 12 + (1 - frac) * 90 * stretch;
        const a = offset + frac * twist + Math.sin(t * 0.0006 + frac * 4) * 0.4;
        const x = Math.cos(a) * r;
        const y = Math.sin(a) * r * 0.75;
        const w = 1.5 + width * 6 * (1 - frac) * (0.4 + Math.sin(frac * 8 + t * 0.001) * 0.3);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        // 绘制臂的宽度 (用点状渐变模拟)
        if (i % 2 === 0 && frac < 0.92) {
          const alpha = alphaMul * (1 - frac) * (0.5 + Math.sin(frac * 12 + t * 0.002) * 0.25);
          ctx.fillStyle = 'rgba(173,255,0,' + alpha + ')';
          ctx.shadowColor = 'rgba(173,255,0,' + (alpha * 0.4) + ')';
          ctx.shadowBlur = w * 1.5;
          ctx.beginPath();
          ctx.arc(x, y, w, 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;
        }
      }
      ctx.restore();
    }

    function loop(now: number) {
      const t = now - t0;
      ctx.clearRect(0, 0, W, H);

      // 鼠标平滑追踪
      mouse.current.tx += (mouse.current.x - mouse.current.tx) * 0.05;
      mouse.current.ty += (mouse.current.y - mouse.current.ty) * 0.05;
      const mx = mouse.current.tx;
      const my = mouse.current.ty;
      const bhX = CX + (mx - CX) * 0.04;
      const bhY = CY + (my - CY) * 0.03;

      const distToMouse = Math.sqrt((mx - bhX) ** 2 + (my - bhY) ** 2);
      const proximity = Math.max(0, 1 - distToMouse / 180);

      /* ── 暗晕 — 广阔暗淡的引力场 ── */
      const haloGrad = ctx.createRadialGradient(bhX, bhY, 10, bhX, bhY, 140);
      haloGrad.addColorStop(0, 'rgba(2,1,0,0.6)');
      haloGrad.addColorStop(0.3, 'rgba(2,1,0,0.3)');
      haloGrad.addColorStop(0.7, 'rgba(2,1,0,0.05)');
      haloGrad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = haloGrad;
      ctx.beginPath();
      // 不规则形状
      ctx.ellipse(bhX, bhY, 130 + Math.sin(t * 0.0005) * 12, 110 + Math.cos(t * 0.0007) * 10, t * 0.0002, 0, Math.PI * 2);
      ctx.fill();

      /* ── 旋臂 — 3条不对称 ── */
      const armAlpha = 0.25 + proximity * 0.5;
      for (const arm of arms) {
        drawArm(bhX, bhY, t, arm.twist, arm.width, arm.offset, arm.stretch, armAlpha);
        // 第二条更淡的臂（镜像偏移）
        drawArm(bhX, bhY, t, arm.twist * 0.9, arm.width * 0.6, arm.offset + Math.PI * 0.7, arm.stretch * 0.8, armAlpha * 0.5);
      }

      /* ── 吸积盘 — 不规则扁椭圆 ── */
      const diskAngle = t * 0.0006;
      ctx.save();
      ctx.translate(bhX, bhY);
      ctx.rotate(diskAngle);
      for (let d = 0; d < 3; d++) {
        const rx = 55 + d * 12 + Math.sin(t * 0.001 + d) * 4;
        const ry = 14 + d * 4;
        const g = ctx.createLinearGradient(0, -ry * 2, 0, ry * 2);
        const alpha = (0.22 + proximity * 0.4) * (1 - d * 0.25);
        g.addColorStop(0, 'rgba(0,0,0,0)');
        g.addColorStop(0.25, 'rgba(173,255,0,' + (alpha * 0.7) + ')');
        g.addColorStop(0.45, 'rgba(240,255,230,' + (alpha * 0.9) + ')');
        g.addColorStop(0.55, 'rgba(240,255,230,' + (alpha * 0.9) + ')');
        g.addColorStop(0.75, 'rgba(173,255,0,' + (alpha * 0.7) + ')');
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        // 不规则椭圆
        for (let i = 0; i <= 60; i++) {
          const a = (i / 60) * Math.PI * 2;
          const rr = Math.sqrt((Math.cos(a) * rx) ** 2 + (Math.sin(a) * ry) ** 2);
          const noise = 1 + Math.sin(a * 5 + t * 0.002) * 0.15 + Math.sin(a * 13 + d) * 0.08;
          const x = Math.cos(a) * rr * noise;
          const y = Math.sin(a) * rr * noise;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();

      /* ── 事件视界 — 漆黑不规则核心 ── */
      const ehGrad = ctx.createRadialGradient(bhX, bhY, 2, bhX, bhY, 22);
      ehGrad.addColorStop(0, '#000000');
      ehGrad.addColorStop(0.4, '#020100');
      ehGrad.addColorStop(0.75, 'rgba(4,3,0,0.6)');
      ehGrad.addColorStop(1, 'rgba(8,6,2,0)');
      ctx.fillStyle = ehGrad;
      ctx.beginPath();
      // 不规则视界
      for (let i = 0; i <= 50; i++) {
        const a = (i / 50) * Math.PI * 2;
        const rr = 20 + Math.sin(a * 3 + t * 0.001) * 3 + Math.sin(a * 7) * 2 + Math.cos(a * 11 + t * 0.002) * 1.5;
        const x = bhX + Math.cos(a) * rr;
        const y = bhY + Math.sin(a) * rr * 0.8;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fill();

      // 视界暗晕
      ctx.strokeStyle = 'rgba(0,0,0,0.7)';
      ctx.lineWidth = 8 + proximity * 6;
      ctx.shadowColor = 'rgba(0,0,0,0.6)';
      ctx.shadowBlur = 12;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // 视界内缘微弱光弧（仅部分区域）
      ctx.strokeStyle = 'rgba(173,255,0,' + (0.25 + proximity * 0.4) + ')';
      ctx.lineWidth = 1;
      ctx.shadowColor = 'rgba(173,255,0,' + (0.5 + proximity * 0.3) + ')';
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(bhX, bhY, 21, t * 0.0003, t * 0.0003 + Math.PI * 1.4); // 不完整圆弧
      ctx.stroke();
      ctx.shadowBlur = 0;

      /* ── 粒子 — 沿旋臂螺旋吸入 ── */
      if (particles.current.length < 70 && Math.random() < 0.4 + proximity * 0.3) {
        particles.current.push(spawn(bhX, bhY));
      }
      const survivors: Particle[] = [];
      for (const p of particles.current) {
        p.life++;
        if (p.life >= p.maxLife) continue;
        const prog = p.life / p.maxLife;
        const alpha = prog < 0.15 ? prog / 0.15 : 1 - (prog - 0.15) / 0.85;
        const shrinkRate = 0.4 + proximity * 1.8;
        p.dist -= p.speed * shrinkRate;
        // 旋臂扭曲影响角度
        const arm = arms[p.armIdx % 3];
        const twistEffect = arm.twist * (1 - p.dist / 130) * 0.02;
        p.angle += (0.01 + twistEffect) * (1 + proximity);
        p.x = bhX + Math.cos(p.angle) * p.dist;
        p.y = bhY + Math.sin(p.angle) * p.dist * 0.75;
        if (p.dist < 10) continue;
        // 靠近视界变橙红
        const tVal = Math.max(0, (p.dist - 10) / 120);
        const r = Math.round(173 * tVal + 255 * (1 - tVal));
        const g = Math.round(255 * tVal + 92 * (1 - tVal));
        const b = Math.round(0 * tVal);
        ctx.fillStyle = 'rgba(' + r + ',' + g + ',' + b + ',' + (alpha * 0.7) + ')';
        ctx.shadowColor = ctx.fillStyle;
        ctx.shadowBlur = p.size * 2;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * (0.5 + tVal * 0.5), 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
        survivors.push(p);
      }
      particles.current = survivors;

      /* ── 鼠标靠近光晕 ── */
      if (proximity > 0.25) {
        const bGrad = ctx.createRadialGradient(bhX, bhY, 15, bhX, bhY, 100);
        bGrad.addColorStop(0, 'rgba(0,0,0,0)');
        bGrad.addColorStop(0.6, 'rgba(173,255,0,' + (proximity * 0.08) + ')');
        bGrad.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = bGrad;
        ctx.beginPath();
        ctx.ellipse(bhX, bhY, 100, 80, 0, 0, Math.PI * 2);
        ctx.fill();
      }

      raf = requestAnimationFrame(loop);
    }

    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      onClick={() => navigate('/avatar')}
      onMouseMove={(e) => {
        const r = canvasRef.current?.getBoundingClientRect();
        if (r) {
          mouse.current.x = e.clientX - r.left;
          mouse.current.y = e.clientY - r.top;
        }
      }}
      onMouseLeave={() => {
        mouse.current.x = CX;
        mouse.current.y = CY;
      }}
      title="进入身外化身 · AI投资推演"
      style={{
        position: 'absolute',
        bottom: '10px',
        right: '0px',
        zIndex: 15,
        cursor: 'pointer',
      }}
    >
      <canvas ref={canvasRef} width={W} height={H} style={{ display: 'block' }} />
      <div style={{
        position: 'absolute', bottom: '0px', left: '50%',
        transform: 'translateX(-50%)', textAlign: 'center', pointerEvents: 'none',
      }}>
        <span style={{
          fontFamily: "'Cormorant Garamond', 'Noto Serif SC', 'Georgia', serif",
          fontSize: '15px', fontStyle: 'italic', color: '#ADFF00', fontWeight: 300,
          letterSpacing: '0.1em',
          textShadow: '0 0 12px rgba(173,255,0,0.4)',
        }}>身外化身</span>
        <div style={{
          fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
          fontSize: '9px', color: '#555', letterSpacing: '0.15em', marginTop: '2px',
        }}>AI 投资推演</div>
      </div>
    </div>
  );
}
