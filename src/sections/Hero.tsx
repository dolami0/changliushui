import AsciiCanvas from '../components/AsciiCanvas';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { DingshuluPanel, TianyanPanel, TrackingPanel } from './PanoramicMonitor';

/* ------------------------------------------------------------------ */
/* ------------------------------------------------------------------ */
function MascotSprite() {
  const navigate = useNavigate();
  const [hover, setHover] = useState(false);

  const rings: Array<{ size: number; speed: number; dash: boolean; color: string }> = [
    { size: 100, speed: 22, dash: false, color: 'rgba(173,255,0,0.6)' },
    { size: 130, speed: 16, dash: true,  color: 'rgba(255,92,0,0.5)' },
    { size: 160, speed: 25, dash: false, color: 'rgba(173,255,0,0.4)' },
    { size: 190, speed: 13, dash: true,  color: 'rgba(255,92,0,0.35)' },
    { size: 220, speed: 30, dash: false, color: 'rgba(173,255,0,0.25)' },
    { size: 250, speed: 10, dash: true,  color: 'rgba(255,92,0,0.2)' },
  ];

  return (
    <div
      onClick={(e) => { e.stopPropagation(); navigate('/avatar'); }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title="身外化身 · AI投资推演"
      style={{
        position: 'absolute',
        bottom: '290px',
        right: '48px',
        zIndex: 8,
        cursor: 'pointer',
        transition: 'all 0.55s cubic-bezier(0.22, 0.61, 0.36, 1)',
        transform: hover
          ? 'translateY(-72px) scale(1.15)'
          : 'translateY(40px) scale(0.85)',
        opacity: hover ? 1 : 0.7,
      }}
    >
      {/* 多层旋转光环 — 佛光位，以花头为中心（偏左） */}
      {rings.map((r, i) => (
        <div key={`ring-${i}`} style={{
          position: 'absolute',
          top: '22%', left: '0%',
          width: hover ? `${r.size}px` : `${r.size * 0.45}px`,
          height: hover ? `${r.size * 0.8}px` : `${r.size * 0.36}px`,
          transform: 'translate(-50%, -50%)',
          border: `${hover ? 1.5 : 0.5}px ${r.dash ? 'dashed' : 'solid'} ${r.color}`,
          borderRadius: '50%',
          opacity: hover ? 1 : 0.1,
          transition: 'all 0.55s cubic-bezier(0.22, 0.61, 0.36, 1)',
          animation: `spin ${r.speed}s linear infinite ${i % 2 === 0 ? '' : 'reverse'}`,
          pointerEvents: 'none', zIndex: 0,
        }}>
          {/* 铜钱 — 散布在光环上 */}
          {[0, 72, 144, 216, 288].map((deg) => {
            const rad = (deg * Math.PI) / 180;
            const rx = 50 + Math.cos(rad) * 48;
            const ry = 50 + Math.sin(rad) * 38;
            return (
              <div key={deg} style={{
                position: 'absolute',
                left: `${rx}%`, top: `${ry}%`,
                width: hover ? '16px' : '8px',
                height: hover ? '16px' : '8px',
                transform: 'translate(-50%, -50%)',
                transition: 'all 0.55s cubic-bezier(0.22, 0.61, 0.36, 1)',
                opacity: hover ? 0.9 : 0.2,
              }}>
                <svg viewBox="0 0 20 20" width="100%" height="100%">
                  <circle cx="10" cy="10" r="9" fill="none" stroke="#C88D3A" strokeWidth="1.5" />
                  <circle cx="10" cy="10" r="8" fill="rgba(200,141,58,0.2)" />
                  <rect x="6" y="6" width="8" height="8" fill="rgba(5,4,1,0.8)" stroke="#C88D3A" strokeWidth="0.8" />
                </svg>
              </div>
            );
          })}
        </div>
      ))}
      {/* 根系光 */}
      <div style={{
        position: 'absolute',
        top: '-30px', left: '-40px', right: '-40px', bottom: '-30px',
        background: hover
          ? 'radial-gradient(ellipse at 50% 85%, rgba(173,255,0,0.18) 0%, rgba(255,92,0,0.06) 30%, rgba(173,255,0,0.03) 55%, transparent 75%)'
          : 'radial-gradient(ellipse at 50% 85%, rgba(173,255,0,0.03) 0%, transparent 50%)',
        borderRadius: '40%',
        filter: 'blur(8px)',
        transition: 'all 0.55s',
        pointerEvents: 'none', zIndex: 0,
      }} />
      {/* 暗能量波动 — 黑洞吸光感 */}
      <div style={{
        position: 'absolute',
        top: '-60px', left: '-60px', right: '-60px', bottom: '-60px',
        background: 'radial-gradient(circle at 50% 50%, rgba(0,0,0,0.98) 0%, rgba(0,0,0,0.85) 20%, rgba(0,0,0,0.5) 45%, rgba(0,0,0,0.15) 70%, transparent 100%)',
        borderRadius: '50%',
        animation: 'breathe 2.5s ease-in-out infinite',
        pointerEvents: 'none', zIndex: 1,
      }} />
      <div style={{
        position: 'absolute',
        top: '-80px', left: '-80px', right: '-80px', bottom: '-80px',
        background: 'radial-gradient(circle at 50% 50%, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.3) 30%, transparent 60%)',
        borderRadius: '50%',
        filter: 'blur(4px)',
        animation: 'breathe 3.5s ease-in-out infinite 0.7s',
        pointerEvents: 'none', zIndex: 1,
      }} />
      {/* 有钱花图片 — 辉光（隐藏时呼吸+缩放，长出后收敛） */}
      <div style={{ position: 'relative', zIndex: 2, width: '180px' }}>
        <img src="/images/youqianhua-raw.png" alt="有钱花"
          style={{
            width: '180px', height: 'auto', display: 'block',
            filter: hover
              ? 'drop-shadow(0 0 12px rgba(173,255,0,0.55)) drop-shadow(0 0 30px rgba(173,255,0,0.3)) drop-shadow(0 0 50px rgba(173,255,0,0.15))'
              : 'drop-shadow(0 0 8px rgba(220,255,230,0.55)) drop-shadow(0 0 20px rgba(180,255,200,0.35)) drop-shadow(0 0 36px rgba(140,220,160,0.18))',
            transition: 'filter 0.55s ease',
            animation: hover ? 'none' : 'breatheScale 2.5s ease-in-out infinite',
          }}
        />
        {/* 隐藏时辉光呼吸叠加层 */}
        {!hover && (
          <div style={{
            position: 'absolute', inset: '-16px', zIndex: -1, pointerEvents: 'none',
            borderRadius: '45%',
            background: 'radial-gradient(ellipse at 50% 50%, rgba(200,255,220,0.28) 0%, rgba(180,255,200,0.12) 40%, rgba(140,220,160,0.04) 65%, transparent 80%)',
            filter: 'blur(3px)',
            animation: 'breatheScale 2.5s ease-in-out infinite',
          }} />
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ValuationCorePanel                                                */
/* ------------------------------------------------------------------ */
function MiaoyinPanel({ mobile }: { mobile: boolean }) {
  const [hover, setHover] = useState(false);
  const [input, setInput] = useState('');
  const [stockCode, setStockCode] = useState('');
  const [stockName, setStockName] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    setSending(true);
    try {
      const TOKEN = import.meta.env.VITE_COZE_TOKEN || '';
      await fetch('https://api.coze.cn/v1/databases/7479116110479048754/records', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          records: [{ fields: {
            news_content: input.trim(),
            stock_code: stockCode.trim() || 'USER_INPUT',
            stock_name: stockName.trim() || '用户传讯',
            level: '3', mode: 'manual',
          }}]
        }),
      });
      setSent(true); setInput(''); setStockCode(''); setStockName('');
      setTimeout(() => setSent(false), 3000);
      fetch('/api/trigger', { method: 'POST' }).catch(() => {});
    } catch {}
    setSending(false);
  };

  return (
    <div style={{
      position: 'absolute', bottom: mobile ? '16px' : '16px', right: mobile ? '16px' : '24px', top: mobile ? 'auto' : '53%',
      zIndex: 15, width: mobile ? 'calc(100% - 32px)' : '540px',
      background: 'rgba(5,4,1,0.90)', backdropFilter: 'blur(3px)',
      border: '1px solid rgba(173,255,0,0.1)', padding: mobile ? '16px 20px' : '20px 28px',
      transition: 'all 0.3s ease', overflow: 'hidden', cursor: 'default',
      display: 'flex', flexDirection: 'column',
    }}
      onMouseEnter={(e) => { setHover(true); e.currentTarget.style.boxShadow = '0 0 24px rgba(173,255,0,0.25)'; e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.borderColor = '#ADFF00'; }}
      onMouseLeave={(e) => { setHover(false); e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.1)'; }}
    >
      {['top-left','top-right','bottom-left','bottom-right'].map(pos => {
        const o = hover ? '-3px' : '0px';
        return (<div key={pos} style={{position:'absolute',width:'10px',height:'10px',zIndex:3,pointerEvents:'none',transition:'all 0.3s ease',opacity:hover?1:0.8,
          ...(pos.includes('top')?{top:o}:{bottom:o}),...(pos.includes('left')?{left:o}:{right:o}),
          ...(pos==='top-left'?{borderTop:'2px solid #ADFF00',borderLeft:'2px solid #ADFF00'}:pos==='top-right'?{borderTop:'2px solid #ADFF00',borderRight:'2px solid #ADFF00'}:pos==='bottom-left'?{borderBottom:'2px solid #ADFF00',borderLeft:'2px solid #ADFF00'}:{borderBottom:'2px solid #ADFF00',borderRight:'2px solid #ADFF00'})}} />);
      })}
      {/* 头部 — 固定 */}
      <div style={{ flexShrink: 0 }}>
        <span style={{ fontFamily:"'Space Mono', monospace",fontSize:'14px',color:'#777',letterSpacing:'0.15em' }}>宗门传讯 · 风闻入阵</span>
        <h2 style={{ fontFamily:"'Geist Pixel','Noto Sans SC',monospace",fontSize:mobile?'20px':'24px',fontWeight:400,color:'#ADFF00',letterSpacing:'0.06em',margin:'8px 0 4px 0' }}>风闻入阵</h2>
        <p style={{ fontFamily:"'Noto Sans SC',sans-serif",fontSize:'14px',color:'#888',margin:'0 0 12px 0',lineHeight:1.5 }}>粘贴资讯或分析命题，直送估值引擎炼化</p>
      </div>
      {/* 正文输入 — 弹性填充 */}
      <textarea value={input} onChange={(e)=>setInput(e.target.value)} placeholder="在此输入资讯内容或分析命题…" rows={mobile?2:6}
        style={{ flex:1,minHeight:0,width:'100%',boxSizing:'border-box',background:'rgba(255,255,255,0.04)',border:'1px solid rgba(173,255,0,0.15)',color:'#F2F4F3',padding:'10px 12px',fontFamily:"'IBM Plex Mono','Noto Sans SC',monospace",fontSize:'15px',lineHeight:1.6,resize:'none',outline:'none',borderRadius:'4px',transition:'border-color 0.2s' }}
        onFocus={(e)=>{e.currentTarget.style.borderColor='#ADFF00'}} onBlur={(e)=>{e.currentTarget.style.borderColor='rgba(173,255,0,0.15)'}} />
      {/* 底部 — 固定 */}
      <div style={{ flexShrink: 0 }}>
        <div style={{ display:'flex',gap:'8px',marginTop:'10px' }}>
          <input value={stockCode} onChange={(e)=>setStockCode(e.target.value)} placeholder="代码(可选)"
            style={{ flex:1,background:'rgba(255,255,255,0.04)',border:'1px solid rgba(255,255,255,0.1)',color:'#AAA',padding:'6px 10px',fontFamily:"'Space Mono',monospace",fontSize:'14px',outline:'none',borderRadius:'4px' }}
            onFocus={(e)=>{e.currentTarget.style.borderColor='#ADFF00'}} onBlur={(e)=>{e.currentTarget.style.borderColor='rgba(255,255,255,0.1)'}} />
          <input value={stockName} onChange={(e)=>setStockName(e.target.value)} placeholder="名称(可选)"
            style={{ flex:1,background:'rgba(255,255,255,0.04)',border:'1px solid rgba(255,255,255,0.1)',color:'#AAA',padding:'6px 10px',fontFamily:"'Space Mono','Noto Sans SC',monospace",fontSize:'14px',outline:'none',borderRadius:'4px' }}
            onFocus={(e)=>{e.currentTarget.style.borderColor='#ADFF00'}} onBlur={(e)=>{e.currentTarget.style.borderColor='rgba(255,255,255,0.1)'}} />
        </div>
        <div style={{ display:'flex',alignItems:'center',gap:'10px',marginTop:'10px' }}>
          <button onClick={handleSend} disabled={sending||!input.trim()}
            style={{ flex:1,padding:'8px 16px',background:sending?'rgba(173,255,0,0.05)':'rgba(173,255,0,0.1)',border:'1px solid '+(sending?'rgba(173,255,0,0.2)':'rgba(173,255,0,0.3)'),color:sending?'#888':'#ADFF00',fontFamily:"'Space Mono','Noto Sans SC',monospace",fontSize:'15px',letterSpacing:'0.08em',cursor:sending||!input.trim()?'not-allowed':'pointer',borderRadius:'4px',transition:'all 0.2s',opacity:input.trim()?1:0.5 }}
            onMouseEnter={(e)=>{if(input.trim()&&!sending)e.currentTarget.style.background='rgba(173,255,0,0.18)'}}
            onMouseLeave={(e)=>{if(!sending)e.currentTarget.style.background='rgba(173,255,0,0.1)'}}>
            {sending?'传讯中…':sent?'✓ 已传讯':'⟐ 传讯入阵'}
          </button>
          <span style={{ fontFamily:"'Noto Sans SC',sans-serif",fontSize:'13px',color:'#FF5C00',letterSpacing:'0.06em',whiteSpace:'nowrap',opacity:0.6 }}>⚒ 施工升级中</span>
        </div>
        {sent&&<div style={{marginTop:'8px',fontFamily:"'Space Mono',monospace",fontSize:'13px',color:'#ADFF00',textAlign:'center'}}>传讯已入阵，估值引擎将自动处理</div>}
      </div>
    </div>
  );
}


/* ---/* ------------------------------------------------------------------ */
/*  Hero                                                               */
/* ------------------------------------------------------------------ */
export default function Hero() {
  const mobile = useMobile();

  return (
    <section id="hero" style={{
      position: 'relative', width: '100%',
      height: mobile ? 'auto' : 'calc(100vh - 60px)',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: mobile ? 'column' : 'row',
    }}>

      {/* ====== LEFT PANEL ====== */}
      <div style={{
        position: 'relative',
        width: mobile ? '100%' : '40%',
        minWidth: mobile ? 'auto' : '420px',
        background: '#050401',
        overflow: 'hidden',
        borderRight: mobile ? 'none' : '1px solid #2A2A2A',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header — 左文右卡，flex 横排 */}
        <div style={{
          flexShrink: 0,
          display: 'flex', alignItems: 'stretch', gap: '52px',
          padding: mobile ? '24px 20px 20px' : '32px 40px 20px',
        }}>
          {/* 左列 — 文案 */}
          <div style={{ width: '340px', flexShrink: 0 }}>
            <p style={{
              fontFamily: "'Space Mono', monospace", fontSize: '13px',
              letterSpacing: '0.2em', color: '#555', margin: '0 0 16px 0',
            }}>
              // 长流水 壹号神器估值重构炉，赛博奇技：
            </p>
            <h1 style={{
              fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace",
              fontSize: mobile ? '42px' : 'clamp(48px, 6vw, 84px)',
              fontWeight: 400, lineHeight: 1.0, color: '#ADFF00',
              margin: '0 0 24px 0', letterSpacing: '0.04em',
              textShadow: '0 0 32px rgba(173,255,0,0.28)',
              whiteSpace: 'nowrap',
            }}>
              神机百炼
            </h1>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{
                width: '8px', height: '8px', background: '#ADFF00',
                boxShadow: '0 0 8px rgba(173,255,0,0.5)',
                display: 'inline-block', animation: 'pulse 2s ease-in-out infinite',
                flexShrink: 0,
              }} />
              <p style={{ fontFamily: "'Noto Sans SC', sans-serif", fontSize: '14px', color: '#888', letterSpacing: '0.06em', margin: 0, lineHeight: 1.6 }}>
                AI大阵驱动天眼→估值→追踪全链路
              </p>
            </div>
          </div>
        </div>

        {/* Scroll — 定数录 */}
        <div style={{
          flex: 1, minHeight: 0,
          display: 'flex', flexDirection: 'column',
          padding: '0 16px 16px',
        }}>
          <DingshuluPanel />
        </div>
      </div>

      {/* ====== RIGHT PANEL ====== */}
      {!mobile && (
        <div style={{ position: 'relative', width: '60%', background: '#050401', overflow: 'hidden' }}>
          <AsciiCanvas />
          {/* 天眼 — 上方全宽，与估值炉左侧对齐 */}
          <div style={{ position: 'absolute', top: '8px', left: '24px', right: '24px', height: '49%', zIndex: 5, display: 'flex', flexDirection: 'column', overflow: 'hidden', transition: 'all 0.3s ease' }}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 0 24px rgba(173,255,0,0.3)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            <TianyanPanel />
          </div>
          {/* 跟踪令 — 与风闻入阵上下沿对齐 */}
          <div style={{ position: 'absolute', bottom: '16px', left: '24px', right: '588px', top: '53%', zIndex: 10, display: 'flex', flexDirection: 'column', overflow: 'hidden', transition: 'all 0.3s ease' }}
            onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 0 24px rgba(173,255,0,0.3)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'translateY(0)'; }}
          >
            <TrackingPanel />
          </div>
          {/* 有钱花遮罩 — 盖住吉祥物，边缘羽化 */}
          <div style={{
            position: 'absolute',
            bottom: '230px',
            right: '20px',
            width: '230px',
            height: '230px',
            background: 'radial-gradient(ellipse at center, #050401 55%, transparent 100%)',
            zIndex: 9,
            pointerEvents: 'none',
          }} />
          {/* 有钱花吉祥物 — 面板背后 */}
          <MascotSprite />
          <MiaoyinPanel mobile={false} />
        </div>
      )}
    </section>
  );
}
