import { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const SECT_LOCATIONS = [
  { id: 'tianji', name: '天机峰', desc: '司情报监控', sub: '天眼 · 寻龙 · 妙音', status: 'active', x: 18, y: 22, disciples: 3 },
  { id: 'cangjing', name: '藏经云', desc: '云端预研数据库', sub: '个股预研 · 造册归档', status: 'active', x: 78, y: 18, disciples: 1 },
  { id: 'shenji', name: '神机百炼', desc: '宗门核心系统', sub: '估值重构炉 · 潜力报告', status: 'active', x: 50, y: 42, disciples: 4 },
  { id: 'pojun', name: '破军小队', desc: '指标技术组', sub: 'K线之道 · 量化指标', status: 'active', x: 22, y: 72, disciples: 2 },
  { id: 'lingyan', name: '凌烟阁', desc: '记录回测与战绩', sub: '历史战绩 · 推动进化', status: 'idle', x: 82, y: 68, disciples: 1 },
  { id: 'guanlan', name: '观澜亭', desc: '判天下大势', sub: '常委会议事', status: 'active', x: 50, y: 8, disciples: 1 },
  { id: 'xingdong', name: '行动处', desc: '专司猎杀天骄', sub: '宗主直属', status: 'hunting', x: 65, y: 55, disciples: 1 },
  { id: 'fengji', name: '风纪处', desc: '数据验证风控', sub: '验证 · 风控', status: 'active', x: 35, y: 58, disciples: 1 },
  { id: 'zhishi', name: '执事处', desc: '招募管理与排名', sub: '天骄榜 · 弟子排名', status: 'active', x: 12, y: 48, disciples: 1 },
  { id: 'tiangong', name: '天工小队', desc: '技术支持与运维', sub: '框架运维 · 技术支持', status: 'active', x: 88, y: 42, disciples: 2 },
];

const statusColor: Record<string, string> = {
  active: '#ADFF00', idle: '#666', hunting: '#FF5C00',
};

const statusText: Record<string, string> = {
  active: '运转中', idle: '调息中', hunting: '猎杀中',
};

function DiscipleDot({ x, y, color, delay }: { x: number; y: number; color: string; delay: number }) {
  return (
    <div
      style={{
        position: 'absolute', left: `${x}%`, top: `${y}%`,
        width: '6px', height: '6px', background: color, borderRadius: '50%',
        boxShadow: `0 0 8px ${color}80`,
        animation: `pulse 2.5s ease-in-out ${delay}s infinite`,
        transform: 'translate(-50%, -50%)', zIndex: 5,
      }}
    />
  );
}

function LocationMarker({ loc }: { loc: typeof SECT_LOCATIONS[0] }) {
  const [hovered, setHovered] = useState(false);
  const color = statusColor[loc.status] || '#ADFF00';

  return (
    <div
      style={{ position: 'absolute', left: `${loc.x}%`, top: `${loc.y}%`, transform: 'translate(-50%, -50%)', zIndex: 10 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={{
        position: 'absolute', width: '32px', height: '32px',
        border: `1px solid ${color}40`, borderRadius: '50%',
        animation: 'pulse 3s ease-in-out infinite',
        transform: 'translate(-50%, -50%)', top: '50%', left: '50%',
      }} />
      <div style={{
        width: '12px', height: '12px', background: color, borderRadius: '50%',
        boxShadow: `0 0 16px ${color}80`, cursor: 'pointer',
        transition: 'transform 0.3s',
        transform: hovered ? 'scale(1.6)' : 'scale(1)',
      }} />
      <div style={{
        position: 'absolute', top: '18px', left: '50%',
        transform: 'translateX(-50%)', whiteSpace: 'nowrap',
        fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace",
        fontSize: '13px', color: hovered ? color : '#AAA',
        letterSpacing: '0.1em', transition: 'color 0.3s',
        textShadow: '0 0 6px rgba(0,0,0,0.9)',
      }}>
        {loc.name}
      </div>

      {hovered && (
        <div style={{
          position: 'absolute', bottom: '32px', left: '50%',
          transform: 'translateX(-50%)', width: '220px',
          background: 'rgba(5, 4, 1, 0.94)', backdropFilter: 'blur(8px)',
          border: `1px solid ${color}30`, padding: '18px 20px',
          pointerEvents: 'none', zIndex: 100,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span style={{ width: '6px', height: '6px', background: color, borderRadius: '50%' }} />
            <span style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: '18px', color: color }}>
              {loc.name}
            </span>
          </div>
          <p style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '14px', color: '#AAA', margin: '0 0 6px 0', lineHeight: 1.5 }}>
            {loc.desc}
          </p>
          <p style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#666', margin: '0 0 10px 0', letterSpacing: '0.06em' }}>
            {loc.sub}
          </p>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '10px' }}>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#555' }}>弟子 {loc.disciples}</span>
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: color }}>{statusText[loc.status]}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SectMap() {
  const sectionRef = useRef<HTMLElement>(null);
  const mapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sectionRef.current || !mapRef.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(mapRef.current, { opacity: 0, scale: 0.97 }, {
        opacity: 1, scale: 1, duration: 1.2, ease: 'power2.out',
        scrollTrigger: { trigger: sectionRef.current, start: 'top 70%', toggleActions: 'play none none reverse' },
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  const dots: { x: number; y: number; color: string; delay: number }[] = [];
  SECT_LOCATIONS.forEach((loc) => {
    for (let i = 0; i < loc.disciples; i++) {
      dots.push({ x: loc.x + (Math.random() - 0.5) * 6, y: loc.y + (Math.random() - 0.5) * 6, color: statusColor[loc.status], delay: Math.random() * 2 });
    }
  });

  return (
    <section ref={sectionRef} id="sectmap" style={{ position: 'relative', width: '100%', minHeight: '100vh', background: '#050401', overflow: 'hidden' }}>
      <div style={{ padding: '60px 48px 30px', position: 'relative', zIndex: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ width: '6px', height: '6px', background: '#ADFF00', boxShadow: '0 0 4px rgba(173,255,0,0.5)' }} />
          <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '14px', fontWeight: 400, color: '#888', margin: 0, letterSpacing: '0.15em' }}>
            // 宗门沙盘 · 全山态势
          </h3>
        </div>
      </div>

      <div ref={mapRef} style={{ position: 'relative', width: 'calc(100% - 96px)', margin: '0 48px 60px', aspectRatio: '16 / 9', border: '1px solid rgba(173, 255, 0, 0.12)', overflow: 'hidden', opacity: 0 }}>
        <div style={{ position: 'absolute', inset: 0, backgroundImage: 'url(/images/sect-landscape.jpg)', backgroundSize: 'cover', backgroundPosition: 'center', opacity: 0.6 }} />
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse 60% 50% at 50% 45%, rgba(5,4,1,0.1) 0%, rgba(5,4,1,0.5) 100%)' }} />

        {dots.map((dot, i) => (<DiscipleDot key={i} x={dot.x} y={dot.y} color={dot.color} delay={dot.delay} />))}
        {SECT_LOCATIONS.map((loc) => (<LocationMarker key={loc.id} loc={loc} />))}

        <div style={{ position: 'absolute', bottom: '20px', left: '20px', display: 'flex', gap: '24px', background: 'rgba(5, 4, 1, 0.75)', padding: '12px 18px' }}>
          {[{ c: '#ADFF00', l: '运转中' }, { c: '#FF5C00', l: '猎杀中' }, { c: '#666', l: '调息中' }].map((item) => (
            <div key={item.l} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ width: '8px', height: '8px', background: item.c, borderRadius: '50%', boxShadow: `0 0 6px ${item.c}60` }} />
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#888', letterSpacing: '0.06em' }}>{item.l}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
