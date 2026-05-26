import { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { manifestoConfig } from '../config';
import GlitchText from '../components/GlitchText';

gsap.registerPlugin(ScrollTrigger);

export default function Manifesto() {
  const sectionRef = useRef<HTMLElement>(null);
  const textRef = useRef<HTMLParagraphElement>(null);
  const videoRef = useRef<HTMLDivElement>(null);

  if (!manifestoConfig.text && !manifestoConfig.videoPath) {
    return null;
  }

  useEffect(() => {
    if (!sectionRef.current || !textRef.current || !videoRef.current) return;

    const ctx = gsap.context(() => {
      gsap.fromTo(
        videoRef.current,
        { opacity: 0, y: 50 },
        {
          opacity: 1,
          y: 0,
          duration: 1.2,
          ease: 'power2.out',
          scrollTrigger: {
            trigger: sectionRef.current,
            start: 'top 70%',
            end: 'top 30%',
            toggleActions: 'play none none reverse',
          },
        }
      );

      gsap.fromTo(
        textRef.current,
        { opacity: 0, y: 60 },
        {
          opacity: 1,
          y: 0,
          duration: 1.2,
          ease: 'power2.out',
          scrollTrigger: {
            trigger: sectionRef.current,
            start: 'top 70%',
            end: 'top 30%',
            toggleActions: 'play none none reverse',
          },
        }
      );
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={sectionRef}
      id="manifesto"
      style={{
        background: '#0A0A0A',
        color: '#F2F4F3',
        padding: '160px 40px',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '60vh',
        borderTop: '1px solid #2A2A2A',
        borderBottom: '1px solid #2A2A2A',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '1360px',
          display: 'grid',
          gridTemplateColumns: 'minmax(320px, 46%) minmax(320px, 1fr)',
          gap: '64px',
          alignItems: 'center',
        }}
      >
        {manifestoConfig.videoPath ? (
          <div
            ref={videoRef}
            style={{
              opacity: 0,
            }}
          >
            <div
              style={{
                position: 'relative',
                width: '100%',
                aspectRatio: '16 / 9',
                overflow: 'hidden',
                background: '#000',
                border: '1px solid #2A2A2A',
              }}
            >
              <video
                autoPlay
                muted
                loop
                playsInline
                preload="metadata"
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover',
                  display: 'block',
                  opacity: 0.8,
                }}
              >
                <source src={manifestoConfig.videoPath} type="video/mp4" />
              </video>
            </div>
          </div>
        ) : (
          <div ref={videoRef} />
        )}

        <div
          ref={textRef}
          style={{
            opacity: 0,
          }}
        >
          <h3
            style={{
              fontFamily: "'Space Mono', monospace",
              fontSize: '11px',
              fontWeight: 400,
              textTransform: 'uppercase',
              letterSpacing: '0.15em',
              color: '#ADFF00',
              margin: '0 0 24px 0',
            }}
          >
            <GlitchText text="SECT DOCTRINE — 宗门训诫" />
          </h3>
          <p
            style={{
              fontFamily: "'Noto Serif SC', 'IBM Plex Mono', serif",
              fontSize: '14px',
              fontWeight: 400,
              lineHeight: '26px',
              maxWidth: '680px',
              textAlign: 'left',
              margin: 0,
              color: '#A7A7A7',
            }}
          >
            {manifestoConfig.text}
          </p>
          <div
            style={{
              marginTop: '32px',
              display: 'flex',
              gap: '24px',
            }}
          >
            {[
              { label: 'AGENTS', value: '04' },
              { label: 'UPTIME', value: '99.9%' },
              { label: 'QI FLUX', value: '87.4' },
            ].map((stat) => (
              <div key={stat.label}>
                <span
                  style={{
                    fontFamily: "'Space Mono', monospace",
                    fontSize: '9px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.12em',
                    color: '#666',
                    display: 'block',
                    marginBottom: '4px',
                  }}
                >
                  {stat.label}
                </span>
                <span
                  style={{
                    fontFamily: "'Geist Pixel', monospace",
                    fontSize: '24px',
                    color: '#F2F4F3',
                  }}
                >
                  {stat.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
