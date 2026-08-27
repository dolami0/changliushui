// ============================================================================
// 第四屏：身外化身复核工作台（§25.7）
// 数据源：Coze DB_DINGSHULU（已复核=定数录中 quality_flag A/B 的记录）
// ============================================================================
import { useState } from 'react';
import { fetchDingshuluAll, type DingshuluRecord } from '../api';
import { usePolling } from '../hooks';
import { toast } from '../toast';

const SCORE_LABELS = ['报告质量', '赔率判断', '风险认知', '操作可行'] as const;

import type { ViewKey } from '../types';

export default function AvatarView({ active, gotoView }: { active: boolean; gotoView: (v: ViewKey) => void }) {
  const { data: allRecords } = usePolling(() => fetchDingshuluAll());
  const reviewed = (allRecords ?? []).filter((r) => r.quality_flag === 'A' || r.quality_flag === 'B');
  const [selCode, setSelCode] = useState<string | null>(null);

  const review = reviewed.find((r) => r.stock_code === selCode) ?? reviewed[0];

  const decide = (d: 'pass' | 'cond' | 'reject') => {
    if (!review) return;
    toast(d === 'pass' ? '✓ 已加入追踪令' : d === 'cond' ? '⚠ 有条件加入' : '已放弃');
    if (d !== 'reject') gotoView('tracking');
  };

  return (
    <section className={`view${active ? ' active' : ''}`}>
      <div style={{ maxWidth: 1720, margin: '0 auto 14px', padding: '10px 14px', border: '1px dashed rgba(200,141,58,0.35)', background: 'rgba(200,141,58,0.04)', fontSize: 12, color: 'var(--gold)' }}>
        ⚠ 待施工 · 当前页面四维评分、红线检查、介入按钮均为占位展示，未接入真实复核数据；仅"待复核队列"（quality_flag A/B）来自定数录 API。后续将接入 valuationApi.review 接口与四维评分真实数据。
      </div>
      <div className="av-grid">
        <div>
          <div className="card" style={{ padding: 14 }}>
            <div className="card-title">待复核队列 · {reviewed.length}</div>
            {reviewed.map((r) => (
              <div key={r.stock_code} className={`queue-item spot${review?.stock_code === r.stock_code ? ' sel' : ''}`}
                onClick={() => setSelCode(r.stock_code)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <b>{r.stock_name}</b>
                  <span className="dimmer mono" style={{ fontSize: 10.5 }}>{r.stock_code}</span>
                  <span className={`avatar-verdict av-${r.quality_flag === 'A' ? 'pass' : 'cond'}`} style={{ position: 'static', marginLeft: 'auto' }}>
                    {r.quality_flag === 'A' ? '✓ 通过' : '⚠ 有条件'}
                  </span>
                </div>
                <div className="dimmer" style={{ fontSize: 10.5, marginTop: 4 }}>{r.processed_at?.slice(0, 16) || ''} · {r.primary_model || ''}</div>
              </div>
            ))}
            {reviewed.length === 0 && <div className="dimmer" style={{ padding: 20, textAlign: 'center' }}>暂无待复核记录</div>}
          </div>
          <div className="card section-gap" style={{ padding: 14 }}>
            <div className="card-title">近 7 天历史复核</div>
            {reviewed.slice(0, 7).map((r) => (
              <div key={r.stock_code} style={{ fontSize: 12, padding: '4px 0', display: 'flex', justifyContent: 'space-between' }}>
                <span>{r.stock_name}({r.stock_code})</span>
                <span className={r.quality_flag === 'A' ? 'up' : ''} style={{ color: r.quality_flag === 'B' ? 'var(--gold)' : undefined }}>
                  {r.quality_flag === 'A' ? '✓ 通过' : r.quality_flag === 'B' ? '⚠ 有条件' : ''}
                </span>
              </div>
            ))}
          </div>
        </div>

        {review && (
          <div>
            <div className="card spot">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <b style={{ fontSize: 16 }}>{review.stock_name}</b>
                <span className="dimmer mono" style={{ fontSize: 11 }}>{review.stock_code}</span>
                <span className="tag-chip" style={{ marginLeft: 'auto' }}>四维评分</span>
              </div>
              {SCORE_LABELS.map((label, i) => (
                <div className="avatar-score" key={label}>
                  <span className="ascore-k">{label}</span>
                  <div className="ascore-bar"><i style={{ width: `${(7 - i) * 12}%` }} /></div>
                  <span className="ascore-v">{7 - i}</span>
                </div>
              ))}
              <div className="prose" style={{ fontSize: 12, marginTop: 10 }}>
                <p>{review.news_summary || '—'}</p>
              </div>
            </div>

            <div className="redflag section-gap">
              未发现叙事-参数矛盾、赔率方向相反或流动性不可交易。
            </div>

            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <button className="btn" onClick={() => toast('已下发重新检视指令')}>重新检视</button>
              <button className="btn" onClick={() => toast('追问模式已激活')}>追问核查</button>
              <button className="btn btn-ghost-danger" onClick={() => toast('申诉已记录（需填原因）')}>申诉覆盖</button>
            </div>

            <div className="decide-bar" style={{ marginTop: 14, display: 'flex', gap: 10, alignItems: 'center', padding: '12px 0' }}>
              <span className="dimmer" style={{ fontSize: 11 }}>人工决策关口</span>
              <span style={{ marginLeft: 'auto' }} />
              <button className="btn btn-ghost-danger" onClick={() => decide('reject')}>✕ 放弃</button>
              <button className="btn btn-gold" onClick={() => decide('cond')}>⚠ 有条件加入</button>
              <button className="btn btn-jade" onClick={() => decide('pass')}>✓ 加入追踪令</button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
