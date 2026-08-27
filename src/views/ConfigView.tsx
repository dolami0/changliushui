// ============================================================================
// 第五屏：配置与通知
// 调度器开关接 valuationApi.fetchStatus/start/stop；其余仅作占位展示，待后续接入真实 API
// ============================================================================
import { useEffect, useState } from 'react';
import { fetchStatus, startScheduler, stopScheduler, type SchedulerState } from '../services/valuationApi';
import { toast } from '../toast';

export default function ConfigView({ active }: { active: boolean }) {
  const [scheduler, setScheduler] = useState<SchedulerState | null>(null);
  const [schedulerError, setSchedulerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dailyInspectOn, setDailyInspectOn] = useState(true);
  const [macroStance, setMacroStance] = useState<'紧' | '中性' | '宽'>('中性');
  const [notifyUiOn, setNotifyUiOn] = useState(true);
  const [notifyWebhookOn, setNotifyWebhookOn] = useState(false);

  const loadStatus = () => {
    fetchStatus()
      .then((s) => { setScheduler(s); setSchedulerError(null); })
      .catch((e) => { setScheduler(null); setSchedulerError(e?.message || '无法连接 /api'); });
  };

  useEffect(() => {
    if (!active) return;
    loadStatus();
    const id = window.setInterval(loadStatus, 30000);
    return () => window.clearInterval(id);
  }, [active]);

  const toggleScheduler = async () => {
    if (busy || !scheduler) return;
    setBusy(true);
    try {
      if (scheduler.scheduler_running) {
        await stopScheduler();
        toast('调度器已停止');
      } else {
        await startScheduler();
        toast('调度器已启动');
      }
      loadStatus();
    } catch (e) {
      toast(`操作失败: ${(e as Error)?.message || '未知错误'}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`view${active ? ' active' : ''}`}>
      <div className="cfg-grid">
        <div className="card">
          <div className="card-title">系统 · 调度</div>
          <div className="cfg-row">
            <span>调度器（天机卷轮询）</span>
            {schedulerError ? (
              <span className="dim" style={{ fontSize: 11 }} title={schedulerError}>● 未连接</span>
            ) : scheduler ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 11, color: scheduler.scheduler_running ? 'var(--jade)' : '#888' }}>
                  {scheduler.scheduler_running ? '● 运行中' : '○ 已停止'}
                </span>
                <div
                  className={`switch${scheduler.scheduler_running ? ' on' : ''}`}
                  style={{ opacity: busy ? 0.5 : 1, cursor: busy ? 'wait' : 'pointer' }}
                  onClick={toggleScheduler}
                />
              </div>
            ) : (
              <span className="dim" style={{ fontSize: 11 }}>加载中…</span>
            )}
          </div>
          {scheduler && (
            <>
              <div className="cfg-row">
                <span>活跃任务</span>
                <b className="num">{scheduler.active_jobs?.length ?? 0}</b>
              </div>
              <div className="cfg-row">
                <span>完成任务</span>
                <b className="num">{scheduler.completed_jobs?.length ?? 0}</b>
              </div>
              {scheduler.next_poll_at && (
                <div className="cfg-row">
                  <span>下次轮询</span>
                  <span className="dim mono" style={{ fontSize: 11 }}>{scheduler.next_poll_at}</span>
                </div>
              )}
            </>
          )}
          <div className="cfg-row">
            <span>每日巡检（收盘后 15:30）</span>
            <div className={`switch${dailyInspectOn ? ' on' : ''}`} onClick={() => { setDailyInspectOn(!dailyInspectOn); toast(dailyInspectOn ? '已关闭' : '已开启'); }} />
          </div>
        </div>

        <div className="card">
          <div className="card-title">追踪 · 资金与中枢</div>
          <div className="cfg-row">
            <span>虚拟总仓资金</span>
            <b className="num">—</b>
          </div>
          <div className="cfg-row">
            <span>宏观仓位中枢</span>
            <div className="seg-mini">
              {(['紧', '中性', '宽'] as const).map((m) => (
                <button key={m} className={macroStance === m ? 'on' : ''} onClick={() => { setMacroStance(m); toast(`宏观中枢已切至「${m}」（本地）`); }}>
                  {m === '紧' ? '紧 · 降 1/3' : m === '宽' ? '宽 · 不变' : '中性'}
                </button>
              ))}
            </div>
          </div>
          <div className="cfg-row">
            <span>推送渠道 · 界面通知中心</span>
            <div className={`switch${notifyUiOn ? ' on' : ''}`} onClick={() => { setNotifyUiOn(!notifyUiOn); toast(notifyUiOn ? '已关闭' : '已开启'); }} />
          </div>
          <div className="cfg-row">
            <span>推送渠道 · 微信 Webhook</span>
            <div className={`switch${notifyWebhookOn ? ' on' : ''}`} onClick={() => { setNotifyWebhookOn(!notifyWebhookOn); toast(notifyWebhookOn ? '已关闭' : '已开启'); }} />
          </div>
        </div>

        <div className="card">
          <div className="card-title">查看 · 版本与运行</div>
          <div className="cfg-row"><span>Prompt 版本</span><span className="dim mono">—</span></div>
          <div className="cfg-row"><span>错误码分布（7d）</span><span className="dim mono">—</span></div>
          <div className="cfg-row"><span>Token 日耗</span><b className="num">—</b></div>
          <div className="cfg-row"><span>单标的耗时 P95</span><b className="num">—</b></div>
        </div>

        <div className="card">
          <div className="card-title">凌烟阁 · DreamLoop 提案审批</div>
          <div className="cfg-row">
            <span className="dim">暂无待审批提案</span>
          </div>
        </div>
      </div>
    </section>
  );
}
