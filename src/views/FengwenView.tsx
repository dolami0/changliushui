// ============================================================================
// 第三屏：风闻入阵（§25.6）
// 左栏提交表单（写天机卷） + 右栏我的投喂列表（从天机卷读取）
// 数据源：Coze DB_TIANJIJUAN
// ============================================================================
import { useState } from 'react';
import { fetchTianjijuan, cozeInsert, type TianjijuanRecord } from '../api';
import { usePolling } from '../hooks';
import { toast } from '../toast';

const TIANJIJUAN_DB = '7479116110479048754';
const SOURCES = ['调研', '传闻', '公告', '圈子消息'];
const LEVELS = [3, 4, 5];

export default function FengwenView({ active }: { active: boolean }) {
  const { data: list, reload } = usePolling(() => fetchTianjijuan(20));
  const items = list ?? [];
  const [text, setText] = useState('');
  const [stock, setStock] = useState('');
  const [source, setSource] = useState(SOURCES[0]);
  const [level, setLevel] = useState(3);

  const submit = async () => {
    const content = text.trim();
    if (!content) { toast('先写下风闻内容'); return; }
    try {
      await cozeInsert(TIANJIJUAN_DB, [{
        news_content: content,
        stock_code: stock.trim() || '',
        stock_name: '',
        date: new Date().toISOString().slice(0, 19).replace('T', ' '),
        level: `L${level}`,
        mode: source,
      }]);
      setText(''); setStock('');
      reload();
      toast('已入阵 · 写入天机卷，下轮调度自动拉取');
    } catch { toast('提交失败'); }
  };

  return (
    <section className={`view${active ? ' active' : ''}`}>
      <div className="fw-grid">
        <div className="card">
          <div className="card-title">风闻入阵 · 人工事件入口</div>
          <div className="form-row">
            <label>内容 *（原始描述即可，LLM 负责清洗）</label>
            <textarea id="fw-text" rows={4} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="例：调研中听闻某 HBM 封装厂三季度急单排到年底…" />
          </div>
          <div className="form-row">
            <label>关联股票（选填 · 填=个股模式，空=产业模式）</label>
            <input placeholder="代码或名称" value={stock} onChange={(e) => setStock(e.target.value)} />
          </div>
          <div className="form-row">
            <label>来源类型 *</label>
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              {SOURCES.map((s) => (<option key={s}>{s}</option>))}
            </select>
          </div>
          <div className="form-row">
            <label>自评 level（终评权在系统）</label>
            <div className="seg-mini">
              {LEVELS.map((lv) => (<button key={lv} className={level === lv ? 'on' : ''} onClick={() => setLevel(lv)}>{lv}</button>))}
            </div>
          </div>
          <button className="btn btn-jade" style={{ width: '100%', justifyContent: 'center', padding: 10 }} onClick={submit}>
            入 阵 → 写入天机卷
          </button>
          <div className="dimmer" style={{ fontSize: 10.5, marginTop: 10 }}>
            与 bstudio 自动监控共用天机卷与全部管线。
          </div>
        </div>

        <div className="card">
          <div className="card-title">我的风闻 · 投喂回响</div>
          <div>
            {items.map((f: TianjijuanRecord) => (
              <div className="fw-item" key={f.id}>
                <div className="fw-content">
                  <div className="fw-text">{f.news_content?.slice(0, 100) || '—'}</div>
                  <div className="fw-meta">
                    <span>{f.mode || '—'}</span>
                    <span>{f.stock_code ? `关联 ${f.stock_code}` : '产业模式'}</span>
                    <span>{(f.date || f.bstudio_create_time || '').slice(0, 16)}</span>
                  </div>
                </div>
                <span className={`fw-status ${f.level ? 'fs-done' : 'fs-queue'}`}>
                  {f.level ? '已入卷 ✓' : '排队中'}
                </span>
              </div>
            ))}
            {items.length === 0 && <div className="dimmer" style={{ padding: 20, textAlign: 'center' }}>暂无投喂记录</div>}
          </div>
        </div>
      </div>
    </section>
  );
}
