import { useEffect, useRef, useState, Component } from 'react';
import { Routes, Route, useLocation, useNavigate, Navigate, Link } from 'react-router-dom';
import { siteConfig, navigationConfig } from './config';

/* ------------------------------------------------------------------ */
/*  ErrorBoundary — 捕获渲染错误，防止白屏无反馈                          */
/* ------------------------------------------------------------------ */
class ErrorBoundary extends Component<{ children: React.ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 24, color: '#FF4444', background: '#111', minHeight: '100vh', fontFamily: 'monospace' }}>
          <h2>渲染错误</h2>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{this.state.error.message}</pre>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, opacity: 0.7 }}>{this.state.error.stack}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}
import Hero from './sections/Hero';
import Facilities from './sections/Facilities';
import CangjingYun from './sections/Archives';
import Footer from './sections/Footer';
import FacilityDetail from './pages/FacilityDetail';
import Dashboard from './pages/Dashboard';
import ValuationReport from './pages/ValuationReport';
import AgentConfig from './pages/AgentConfig';
import AgentAvatar from './pages/AgentAvatar';
import AvatarCC from './pages/AvatarCC';
import TianjiPeak from './pages/TianjiPeak';
import Tracking from './pages/Tracking';
import RedesignDemo from './pages/RedesignDemo';
import { MobileShell } from './mobile/MobileShell';
import { DingshuluList } from './mobile/tabs/DingshuluTab/DingshuluList';
import { DingshuluDetail } from './mobile/tabs/DingshuluTab/DingshuluDetail';
import { TrackingList } from './mobile/tabs/TrackingTab/TrackingList';
import { TrackingDetail } from './mobile/tabs/TrackingTab/TrackingDetail';
import { TianjiList } from './mobile/tabs/TianjiTab/TianjiList';
import { TianjiDetail } from './mobile/tabs/TianjiTab/TianjiDetail';
import { SubmitForm } from './mobile/tabs/SubmitTab/SubmitForm';
import { AvatarChat } from './mobile/tabs/AvatarTab/AvatarChat';
import gsap from 'gsap';

/* ------------------------------------------------------------------ */
/*  PageTransition — 页面切换过渡动画                                  */
/* ------------------------------------------------------------------ */
function PageTransition({ children }: { children: React.ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    gsap.fromTo(containerRef.current,
      { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: 0.35, ease: 'power2.out' }
    );
  }, [children]);

  return (
    <div ref={containerRef}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  NavigationGlow — 跨页面辉光过渡                                    */
/* ------------------------------------------------------------------ */
function NavigationGlow() {
  const location = useLocation();
  const glowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!glowRef.current) return;
    const tl = gsap.timeline();
    tl.fromTo(glowRef.current,
      { opacity: 0, scale: 0.3 },
      { opacity: 0.6, scale: 1, duration: 0.2, ease: 'power2.out' }
    );
    tl.to(glowRef.current,
      { opacity: 0, scale: 1.5, duration: 0.4, ease: 'power2.in', delay: 0.05 }
    );
  }, [location.pathname]);

  return (
    <div ref={glowRef} style={{
      position: 'fixed',
      top: '50%', left: '50%',
      width: '600px', height: '600px',
      borderRadius: '50%',
      background: 'radial-gradient(circle, rgba(173,255,0,0.08) 0%, transparent 60%)',
      pointerEvents: 'none',
      zIndex: 9998,
      transform: 'translate(-50%, -50%)',
    }} />
  );
}

function Home() {
  return (
    <>
      <main>
        <Hero />
        <Facilities />
      </main>
      <Footer />
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  TopNav — 全局灵枢导航（所有页面可见）+ 千里江山长卷                    */
/* ------------------------------------------------------------------ */
function TopNav() {
  const location = useLocation();
  const currentPath = location.pathname;
  const isHome = currentPath === '/'
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  function linkHref(item: { label: string; href: string }) {
    if (item.href.startsWith('#')) return `/${item.href}`
    return item.href
  }

  // 紧凑模式样式变量
  const py = scrolled ? '8px' : '18px'
  const brandSize = scrolled ? '18px' : '22px'
  const linkSize = scrolled ? '14px' : '16px'
  const dotSize = scrolled ? '6px' : '8px'
  const sloganOpacity = scrolled ? 0 : 1

  // 宗门锚点：首页直接用原生锚点跳转，其他页面用 React Router
  function renderNavLink(item: { label: string; href: string }) {
    const href = linkHref(item)
    const isActive = currentPath === href || (href === '/#facilities' && currentPath === '/')
    const isAnchor = item.href.startsWith('#')

    const linkStyle: React.CSSProperties = {
      fontFamily: "'Space Mono', 'Noto Sans SC', monospace",
      fontSize: linkSize,
      color: isActive ? '#ADFF00' : '#AAA',
      textDecoration: 'none',
      letterSpacing: '0.06em',
      transition: 'color 0.25s, font-size 0.35s ease',
      borderBottom: isActive ? '1px solid #ADFF00' : '1px solid transparent',
      paddingBottom: '4px',
      textShadow: isActive ? '0 0 8px rgba(173,255,0,0.35)' : 'none',
    }

    if (isAnchor && isHome) {
      return (
        <a key={item.label} href={item.href} style={linkStyle}
          onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.color = '#ADFF00' }}
          onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.color = '#AAA' }}
        >
          {item.label}
        </a>
      )
    }
    return (
      <Link key={item.label} to={href} style={linkStyle}
        onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.color = '#ADFF00' }}
        onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.color = '#AAA' }}
      >
        {item.label}
      </Link>
    )
  }

  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 60,
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: `${py} 40px`,
      background: 'transparent',
      transition: 'padding 0.35s ease',
    }}>
      {/* 毛玻璃背景层 */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 0,
        backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
        background: 'rgba(5,4,1,0.15)',
      }} />
      {/* 底部羽化 */}
      <div style={{
        position: 'absolute', bottom: '-8px', left: 0, right: 0, height: '12px', zIndex: 0,
        background: 'linear-gradient(180deg, rgba(5,4,1,0.3) 0%, transparent 100%)',
        pointerEvents: 'none',
      }} />
      {/* 左：品牌 + 灵石 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', position: 'relative', zIndex: 2 }}>
        <div style={{ position: 'relative', width: dotSize, height: dotSize, transition: 'width 0.35s ease, height 0.35s ease' }}>
          <span style={{
            position: 'absolute', inset: 0, borderRadius: '50%',
            background: '#ADFF00',
            boxShadow: '0 0 8px rgba(173,255,0,0.6), 0 0 20px rgba(173,255,0,0.2)',
            animation: 'pulse 2.5s ease-in-out infinite',
          }} />
          <span style={{
            position: 'absolute', inset: '-4px', borderRadius: '50%',
            border: '1px solid rgba(173,255,0,0.12)',
            animation: 'pulse 3s ease-in-out infinite 0.5s',
          }} />
        </div>
        <Link
          to="/"
          style={{
            fontFamily: "'Space Mono', 'Noto Sans SC', monospace",
            fontSize: brandSize, fontWeight: 700,
            color: '#ADFF00', letterSpacing: '0.06em', textDecoration: 'none',
            textShadow: '0 0 8px rgba(173,255,0,0.2)',
            transition: 'font-size 0.35s ease',
          }}
        >
          {navigationConfig.brandName}
        </Link>
        <span style={{
          color: 'rgba(255,255,255,0.10)', fontSize: '18px',
          fontWeight: 200, margin: '0 2px',
        }}>|</span>
        <span style={{
          fontFamily: "'Noto Sans SC', sans-serif",
          fontSize: '12px', color: 'rgba(255,255,255,0.25)',
          letterSpacing: '0.08em', whiteSpace: 'nowrap',
          opacity: sloganOpacity, transition: 'opacity 0.35s ease',
        }}>
          {navigationConfig.brandSub}
        </span>
      </div>

      {/* 右：导航链接 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '28px', position: 'relative', zIndex: 2 }}>
        {navigationConfig.links.filter(item => item.label !== '宗门').map(renderNavLink)}
        <Link
          to="/"
          style={{
            fontFamily: "'Space Mono', 'Noto Sans SC', monospace",
            fontSize: linkSize, color: '#AAA', textDecoration: 'none',
            letterSpacing: '0.06em', transition: 'color 0.25s, font-size 0.35s ease',
            paddingBottom: '4px',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.color = '#ADFF00' }}
          onMouseLeave={(e) => { e.currentTarget.style.color = '#AAA' }}
        >
          返回首页
        </Link>
      </div>
    </nav>
  )
}

function isMobileDevice(): boolean {
  if (typeof window === 'undefined') return false
  const ua = navigator.userAgent || ''
  return /Android|iPhone|iPad|iPod|webOS/i.test(ua) || (window.innerWidth < 768 && 'ontouchstart' in window)
}

function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const isMobileRoute = location.pathname === '/m' || location.pathname.startsWith('/m/');

  // 移动端自动重定向到 /m
  useEffect(() => {
    if (isMobileRoute) return; // 已经在移动端路由，不重复跳转
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
      || (window.innerWidth <= 768);
    if (isMobile) {
      navigate('/m', { replace: true });
    }
  }, []); // 仅首次加载检测

  useEffect(() => {
    if (!isMobileRoute && isMobileDevice()) {
      window.location.replace('/m/')
    }
  }, [isMobileRoute])

  useEffect(() => {
    document.title = siteConfig.siteTitle || '长流水';
    document.documentElement.lang = siteConfig.language || 'zh-CN';

    let metaDescription = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (!metaDescription) {
      metaDescription = document.createElement('meta');
      metaDescription.name = 'description';
      document.head.appendChild(metaDescription);
    }
    metaDescription.content = siteConfig.siteDescription || '';
  }, []);

  return (
    <ErrorBoundary>
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {!isMobileRoute && <NavigationGlow />}
      {!isMobileRoute && <TopNav />}
      <div style={{ flex: 1, minHeight: 0 }}>
        <Routes>
          <Route path="/" element={<PageTransition key="home"><Home /></PageTransition>} />
          <Route path="/facility/:slug" element={<PageTransition key="facility"><FacilityDetail /></PageTransition>} />
          <Route path="/report/:code" element={<PageTransition key="report"><ValuationReport /></PageTransition>} />
          <Route path="/report/v4/:code" element={<PageTransition key="v4report"><ValuationReport /></PageTransition>} />
          <Route path="/cangjingyun" element={<PageTransition key="cangjingyun"><CangjingYun /></PageTransition>} />
          <Route path="/dashboard" element={<PageTransition key="dashboard"><Dashboard /></PageTransition>} />
          <Route path="/agent-config" element={<PageTransition key="agentconfig"><AgentConfig /></PageTransition>} />
          <Route path="/avatar" element={<PageTransition key="avatar"><AgentAvatar /></PageTransition>} />
          <Route path="/avatar-cc" element={<PageTransition key="avatarcc"><AvatarCC /></PageTransition>} />
          <Route path="/tianjifeng" element={<PageTransition key="tianjifeng"><TianjiPeak /></PageTransition>} />
          <Route path="/tracking" element={<PageTransition key="tracking"><Tracking /></PageTransition>} />
          <Route path="/redesign" element={<RedesignDemo />} />
          {/* 移动端路由 — 平铺到顶层，避免嵌套 Routes 刷新白屏 */}
          <Route path="/m" element={<Navigate to="/m/dingshulu" replace />} />
          <Route path="/m/dingshulu" element={<MobileShell><DingshuluList /></MobileShell>} />
          <Route path="/m/dingshulu/:id" element={<MobileShell><DingshuluDetail /></MobileShell>} />
          <Route path="/m/tracking" element={<MobileShell><TrackingList /></MobileShell>} />
          <Route path="/m/tracking/:code" element={<MobileShell><TrackingDetail /></MobileShell>} />
          <Route path="/m/tianyan" element={<MobileShell><TianjiList /></MobileShell>} />
          <Route path="/m/tianyan/:id" element={<MobileShell><TianjiDetail /></MobileShell>} />
          <Route path="/m/submit" element={<MobileShell><SubmitForm /></MobileShell>} />
          <Route path="/m/avatar" element={<MobileShell><AvatarChat /></MobileShell>} />
        </Routes>
      </div>
    </div>
    </ErrorBoundary>
  );
}

export default App;
