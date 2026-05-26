import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMobile } from '../hooks/useMobile';
import { fetchRecordById, type CozeRecord } from '../services/cozeApi';

function cleanMd(text: string): string {
  if (!text) return '';
  return text.replace(/\*\*/g, '').replace(/#{1,6}\s?/g, '').replace(/\n{3,}/g, '\n\n').trim();
}

function getSignal(score: string): { label: string; color: string } {
  const n = parseFloat(score) || 0;
  if (n >= 80) return { label: '强', color: '#ADFF00' };
  if (n >= 50) return { label: '中', color: '#FF5C00' };
  return { label: '弱', color: '#666' };
}

function getRating(score: string): string {
  const n = parseFloat(score) || 0;
  if (n >= 85) return 'A+';
  if (n >= 70) return 'A';
  if (n >= 55) return 'A-';
  if (n >= 40) return 'B+';
  return 'B';
}

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: '16px', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#555', letterSpacing: '0.1em', minWidth: '140px', flexShrink: 0 }}>
        {label}
      </span>
      <span style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: highlight ? '18px' : '15px', fontWeight: highlight ? 600 : 400, color: highlight ? '#ADFF00' : '#CCC', lineHeight: 1.6 }}>
        {value || '—'}
      </span>
    </div>
  );
}

function Block({ label, content }: { label: string; content: string }) {
  const text = cleanMd(content);
  if (!text) return null;
  const lines = text.split('\n').filter((l) => l.trim());
  if (lines.length === 0) return null;

  return (
    <div style={{ marginBottom: '32px' }}>
      <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#555', letterSpacing: '0.2em', margin: '0 0 12px 0', paddingBottom: '8px', borderBottom: '1px solid rgba(173,255,0,0.1)' }}>
        {label}
      </h3>
      <div style={{ fontFamily: "'IBM Plex Mono', 'Noto Sans SC', monospace", fontSize: '14px', lineHeight: 2.0, color: '#AAA', whiteSpace: 'pre-wrap' }}>
        {lines.map((line, i) => <p key={i} style={{ margin: '0 0 8px 0' }}>{line}</p>)}
      </div>
    </div>
  );
}

export default function ReportDetail() {
  const { id } = useParams<{ id: string }>();
  const [record, setRecord] = useState<CozeRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) { setError('无效记录ID'); setLoading(false); return; }
    fetchRecordById(id)
      .then((data) => {
        if (data) setRecord(data);
        else setError('未找到该记录');
        setLoading(false);
      })
      .catch((err) => { console.error(err); setError('加载失败'); setLoading(false); });
  }, [id]);

  const mobile = useMobile();
  const score = record?.comprehensive_score || '0';
  const signal = getSignal(score);
  const rating = getRating(score);

  return (
    <div style={{ minHeight: 'calc(100vh - 58px)', background: '#050401', color: '#F2F4F3' }}>

      <div style={{ maxWidth: '960px', margin: '0 auto', padding: mobile ? '24px 20px' : '48px' }}>
        {loading && <div style={{ padding: '80px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#555' }}>加载报告中...</div>}
        {error && !loading && <div style={{ padding: '80px', textAlign: 'center', fontFamily: "'Space Mono', monospace", fontSize: '14px', color: '#FF5C00' }}>{error}</div>}

        {record && !loading && (
          <>
            <div style={{ marginBottom: '40px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '16px' }}>
                <h1 style={{ fontFamily: "'Geist Pixel', 'Noto Sans SC', monospace", fontSize: '36px', fontWeight: 400, color: '#ADFF00', letterSpacing: '0.06em', margin: 0, textShadow: '0 0 20px rgba(173,255,0,0.25)' }}>
                  {record.stock_name || '未命名'}
                </h1>
                <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '16px', color: '#777' }}>{record.stock_code || ''}</span>
              </div>
              <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                <span style={{ fontFamily: "'Geist Pixel', monospace", fontSize: '24px', color: '#ADFF00' }}>{rating}</span>
                <span style={{ width: '6px', height: '6px', background: signal.color, borderRadius: '50%', boxShadow: `0 0 8px ${signal.color}60` }} />
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '13px', color: signal.color, letterSpacing: '0.1em' }}>信号 {signal.label}</span>
                <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#444', letterSpacing: '0.08em' }}>ID: {record.id.slice(-8)}</span>
              </div>
            </div>

            {/* 报告链接 · 置顶 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '28px', flexWrap: 'wrap' }}>
              <span style={{ fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#555', letterSpacing: '0.12em' }}>来源</span>
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: '14px', color: '#ADFF00' }}>
                {record.source || '综合'}
              </span>
              <span style={{ flex: 1, height: '1px', background: 'rgba(173,255,0,0.06)' }} />
              <a
                href={`https://www.coze.cn/space/${record.uuid || ''}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontFamily: "'Space Mono', monospace", fontSize: '12px', color: '#ADFF00',
                  letterSpacing: '0.1em', textDecoration: 'none', border: '1px solid rgba(173,255,0,0.25)',
                  padding: '6px 16px', transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(173,255,0,0.08)'; e.currentTarget.style.borderColor = '#ADFF00'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'rgba(173,255,0,0.25)'; }}
              >
                → 查看完整报告
              </a>
            </div>

            {/* 核心指标 · 单列紧凑排布 */}
            <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(173,255,0,0.1)', padding: '20px 24px', marginBottom: '28px' }}>
              <h3 style={{ fontFamily: "'Space Mono', monospace", fontSize: '11px', color: '#555', letterSpacing: '0.2em', margin: '0 0 12px 0' }}>核心指标</h3>
              <Field label="综合评分" value={record.comprehensive_score} highlight />
              <Field label="潜力涨幅" value={record.potential_increase} highlight />
              <Field label="来源" value={record.source} />
              <Field label="产业链" value={record.cylfx} />
            </div>

            <Block label="公司背景" content={record.background} />
            <Block label="分析报告" content={record.analysis_report} />
            <Block label="高收益投资机会" content={record.high_yield_investment_opportunity} />
            <Block label="知识库" content={record.knowledge} />
          </>
        )}
      </div>
    </div>
  );
}
