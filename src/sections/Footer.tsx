import { useEffect, useState } from 'react';
import { footerConfig } from '../config';

export default function Footer() {
  const [time, setTime] = useState('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const h = String(now.getHours()).padStart(2, '0');
      const m = String(now.getMinutes()).padStart(2, '0');
      const s = String(now.getSeconds()).padStart(2, '0');
      setTime(`${h}:${m}:${s}`);
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  if (!footerConfig.copyrightText && !footerConfig.statusText) {
    return null;
  }

  return (
    <footer
      style={{
        background: '#050401',
        color: '#666',
        borderTop: '1px solid #2A2A2A',
        padding: '20px 40px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontFamily: "'Space Mono', monospace",
        fontSize: '9px',
        fontWeight: 400,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
      }}
    >
      <span>{footerConfig.copyrightText}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            style={{
              width: '4px',
              height: '4px',
              background: '#ADFF00',
              boxShadow: '0 0 4px rgba(173, 255, 0, 0.5)',
              display: 'inline-block',
            }}
          />
          {footerConfig.statusText}
        </span>
        <span style={{ color: '#2A2A2A' }}>|</span>
        <span>UTC+8 {time}</span>
      </div>
    </footer>
  );
}
