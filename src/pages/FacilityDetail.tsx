import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { facilitiesConfig, navigationConfig } from '../config';
import GlitchText from '../components/GlitchText';

const statusColorMap = {
  cultivating: '#ADFF00',
  meditating: '#666666',
  alchemy: '#FF5C00',
};

export default function FacilityDetail() {
  const { slug } = useParams<{ slug: string }>();

  const mobile = useMobile();
  const facility = useMemo(
    () => facilitiesConfig.items.find((item) => item.slug === slug) ?? null,
    [slug]
  );

  if (!facility) {
    return (
      <div
        style={{
          minHeight: 'calc(100vh - 58px)',
          background: '#050401',
          color: '#F2F4F3',
          fontFamily: "'IBM Plex Mono', monospace",
          padding: '40px',
        }}
      >
        <p style={{ color: '#A7A7A7' }}>{facilitiesConfig.detailNotFoundText}</p>
        <Link to="/" style={{ color: '#ADFF00', textDecoration: 'underline', fontSize: '12px' }}>
          {facilitiesConfig.detailReturnText}
        </Link>
      </div>
    );
  }

  const statusColor = statusColorMap[facility.status];

  return (
    <div
      style={{
        minHeight: 'calc(100vh - 58px)',
        background: '#050401',
        color: '#F2F4F3',
        fontFamily: "'IBM Plex Mono', monospace",
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Nav */}
      <nav
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: mobile ? '16px 20px' : '24px 40px',
          borderBottom: '1px solid #2A2A2A',
          background: 'rgba(5, 4, 1, 0.9)',
        }}
      >
        <div>
          <span
            style={{
              fontFamily: "'Geist Pixel', 'Noto Serif SC', monospace",
              fontSize: '18px',
              fontWeight: 400,
              color: '#ADFF00',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            {navigationConfig.brandName}
          </span>
        </div>
        <Link
          to="/#facilities"
          style={{
            fontSize: '10px',
            fontWeight: 400,
            textTransform: 'uppercase',
            color: '#A7A7A7',
            textDecoration: 'none',
            borderBottom: '1px solid #2A2A2A',
            paddingBottom: '2px',
            transition: 'border-color 0.2s, color 0.2s',
            letterSpacing: '0.08em',
            fontFamily: "'Space Mono', monospace",
          }}
          onMouseEnter={(e) => {
            (e.target as HTMLElement).style.borderBottomColor = '#ADFF00';
            (e.target as HTMLElement).style.color = '#F2F4F3';
          }}
          onMouseLeave={(e) => {
            (e.target as HTMLElement).style.borderBottomColor = '#2A2A2A';
            (e.target as HTMLElement).style.color = '#A7A7A7';
          }}
        >
          {facilitiesConfig.detailBackText}
        </Link>
      </nav>

      {/* Content */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: mobile ? 'column' : 'row',
        }}
      >
        {/* Left - Text */}
        <div
          style={{
            flex: 1,
            padding: mobile ? '32px 20px' : '60px 48px',
            borderRight: mobile ? 'none' : '1px solid #2A2A2A',
            borderBottom: mobile ? '1px solid #2A2A2A' : 'none',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '24px' }}>
            <span
              style={{
                width: '6px',
                height: '6px',
                background: statusColor,
                boxShadow: `0 0 8px ${statusColor}66`,
                display: 'inline-block',
              }}
            />
            <span
              style={{
                fontFamily: "'Space Mono', monospace",
                fontSize: '9px',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
                color: statusColor,
              }}
            >
              {facility.statusText}
            </span>
          </div>

          <h1
            style={{
              fontSize: '24px',
              fontWeight: 400,
              lineHeight: '32px',
              textTransform: 'uppercase',
              margin: '0 0 8px 0',
              fontFamily: "'IBM Plex Mono', monospace",
              color: '#F2F4F3',
              letterSpacing: '0.02em',
            }}
          >
            <GlitchText text={facility.article.title} />
          </h1>

          <p
            style={{
              fontFamily: "'Space Mono', monospace",
              fontSize: '9px',
              textTransform: 'uppercase',
              letterSpacing: '0.12em',
              color: '#666',
              margin: '0 0 40px 0',
            }}
          >
            {facility.role} · {facility.code} · {facility.nameCN}
          </p>

          <div style={{ maxWidth: '520px' }}>
            {facility.article.paragraphs.map((paragraph, index) => (
              <p
                key={`${facility.slug}-${index}`}
                style={{
                  fontSize: '13px',
                  fontWeight: 400,
                  lineHeight: '24px',
                  margin: '0 0 20px 0',
                  color: '#A7A7A7',
                  fontFamily: "'Noto Serif SC', 'IBM Plex Mono', serif",
                }}
              >
                {paragraph}
              </p>
            ))}
          </div>

          <div
            style={{
              marginTop: '40px',
              padding: '16px',
              border: '1px solid #2A2A2A',
              background: '#0A0A0A',
            }}
          >
            <span
              style={{
                fontFamily: "'Space Mono', monospace",
                fontSize: '9px',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
                color: '#666',
                display: 'block',
                marginBottom: '8px',
              }}
            >
              当前任务
            </span>
            <span
              style={{
                fontFamily: "'Noto Serif SC', serif",
                fontSize: '14px',
                color: '#F2F4F3',
              }}
            >
              {facility.task}
            </span>
          </div>
        </div>

        {/* Right - Image */}
        <div
          style={{
            flex: 1,
            position: 'relative',
            background: '#000',
          }}
        >
          {facility.image ? (
            <img
              src={facility.image}
              alt={facility.name}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                filter: 'grayscale(80%)',
                display: 'block',
                opacity: 0.85,
              }}
            />
          ) : (
            <div
              style={{
                width: '100%',
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '12px',
                textTransform: 'uppercase',
                color: '#666',
              }}
            >
              No Image
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
