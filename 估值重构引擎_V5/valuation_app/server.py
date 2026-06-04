"""
FastAPI 服务入口 — SSE 进度推送 + Web 仪表盘 + 报告查看

启动: python server.py
     或 python -m uvicorn valuation_app.server:app --host 0.0.0.0 --port 8080
"""

import sys as _sys
_sys.dont_write_bytecode = True  # 禁止生成 __pycache__，避免旧字节码缓存导致代码不更新
import sys  # 保留 sys 别名供其余代码使用

import asyncio
import json
import os
import queue
import subprocess as sp
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from valuation_app.coze_client import CozeClient
from valuation_app.pipeline_runner import PipelineRunner, ProgressEvent
from valuation_app.scheduler import Scheduler
from valuation_app.industry_chain_coze import IndustryChainCoze
from valuation_app.industry_chain_scheduler import WangqiScheduler

# ── 全局状态 ──────────────────────────────

_progress_queues: list[queue.Queue] = []  # SSE 订阅者列表
_wangqi_queues: list[queue.Queue] = []    # 天机 SSE 订阅者列表
_state = {
    "active_jobs": [],
    "completed_jobs": [],
    "last_poll_at": None,
    "next_poll_at": None,
    "scheduler_running": False,
    "server_started_at": datetime.now(timezone.utc).isoformat(),
    "wangqi": {
        "active_jobs": [],
        "completed_jobs": [],
        "last_poll_at": None,
        "next_poll_at": None,
        "scheduler_running": False,
    },
}
_scheduler: Scheduler | None = None
_wangqi: WangqiScheduler | None = None
_ic_coze: IndustryChainCoze | None = None
_config: dict = {}


def _load_config():
    config_path = Path(__file__).resolve().parent / "config.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def _load_completed_from_disk(scheduler: Scheduler, max_age_days: int = 2):
    """从磁盘报告 JSON 恢复已完成任务列表，只保留最近 N 天。"""
    import time
    data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"
    if not data_dir.exists():
        return
    cutoff = time.time() - max_age_days * 86400
    loaded = []
    for f in sorted(data_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            mtime = f.stat().st_mtime
            if mtime < cutoff:
                continue
            with open(f, encoding="utf-8") as fh:
                payload = json.load(fh)
            a0 = payload.get("agent0", {})
            a3 = payload.get("agent3", {})
            vs = a3.get("valuation_summary", {})
            loaded.append({
                "stock_code": a0.get("stock_code", f.stem),
                "stock_name": a0.get("stock_name", ""),
                "status": "done",
                "completed_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "upside_pct": vs.get("probability_weighted_upside_pct", 0),
            })
        except Exception:
            pass
    scheduler.completed_jobs = loaded


def _broadcast(event: ProgressEvent):
    """向所有 SSE 订阅者推送进度事件"""
    data = json.dumps(event.__dict__, ensure_ascii=False)
    dead = []
    for q in _progress_queues:
        try:
            q.put_nowait(data)
        except queue.Full:
            dead.append(q)
    for q in dead:
        _progress_queues.remove(q)


def _handle_progress(event: ProgressEvent):
    """进度回调：广播到 SSE + 更新内存状态"""
    _broadcast(event)
    _state["active_jobs"] = _scheduler.active_jobs if _scheduler else []
    _state["completed_jobs"] = _scheduler.completed_jobs if _scheduler else []


def _handle_wangqi_progress(data: dict):
    """WangqiScheduler 的 progress_cb：广播 SSE + 更新 _state"""
    payload = json.dumps(data, ensure_ascii=False)
    dead = []
    for q in _wangqi_queues:
        try:
            q.put_nowait(payload)
        except queue.Full:
            dead.append(q)
    for q in dead:
        _wangqi_queues.remove(q)
    if _wangqi:
        _state["wangqi"]["active_jobs"] = _wangqi.active_jobs
        _state["wangqi"]["completed_jobs"] = _wangqi.completed_jobs


# ── 应用生命周期 ──────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _scheduler, _wangqi, _ic_coze
    _config = _load_config()

    # 初始化 CozeClient + PipelineRunner + Scheduler
    coze = CozeClient(
        token=_config["coze_sat_token"],
        workspace_id=_config["coze_workspace_id"],
    )
    runner = PipelineRunner(progress_callback=_handle_progress)
    _scheduler = Scheduler(coze, runner, _config)

    # 启动主调度器（按配置决定是否自动启动）
    if _config.get("scheduler_enabled", True):
        await _scheduler.start()
        _state["scheduler_running"] = True
    else:
        _state["scheduler_running"] = False

    # 从磁盘恢复已完成任务（重启不丢失）
    _load_completed_from_disk(_scheduler, max_age_days=2)

    # 初始化望气 (天机) 调度器 — 独立于主管线，优雅降级
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        _ic_coze = IndustryChainCoze(coze)
        from industry_chain_workflow import IndustryChainWorkflow
        from env_config import DEEPSEEK_API_KEY as _dk
        ic_wf = IndustryChainWorkflow(
            deepseek_key=_dk,
            coze_client=coze,
        )
        _wangqi = WangqiScheduler(coze, ic_wf, _ic_coze, _config, progress_cb=_handle_wangqi_progress)
        await _wangqi.start()
        _state["wangqi"]["scheduler_running"] = True
        _state["wangqi"]["active_jobs"] = _wangqi.active_jobs
        _state["wangqi"]["completed_jobs"] = _wangqi.completed_jobs
    except Exception:
        import logging
        logging.getLogger(__name__).warning("WangqiScheduler 初始化失败，望气调度器不可用", exc_info=True)
        _wangqi = None
        _ic_coze = None

    yield

    # 优雅关闭
    if _scheduler:
        await _scheduler.stop()
    _state["scheduler_running"] = False
    if _wangqi:
        await _wangqi.stop()


app = FastAPI(title="估值重构引擎 V5", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 页面路由 ──────────────────────────────

@app.get("/report/{filename}")
async def view_report(filename: str):
    """服务端渲染 HTML 估值报告。filename = {stock_code}_{timestamp} 如 688805_20260522_1528"""
    from valuation_app.report_builder import build_html_report
    data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"

    def _resolve_report_path(name: str) -> Path | None:
        json_path = data_dir / f"{name}.json"
        if json_path.exists():
            return json_path
        json_path = data_dir / "history" / f"{name}.json"
        if json_path.exists():
            return json_path
        # 含时间戳时，回退到纯代码名 (如 300726_20260522_1505 → 300726.json)
        parts = name.split("_", 1)
        if len(parts) > 1 and parts[1].replace("_", "").isdigit() and len(parts[1].replace("_", "")) >= 12:
            json_path = data_dir / f"{parts[0]}.json"
            if json_path.exists():
                return json_path
        return None

    json_path = _resolve_report_path(filename)
    if not json_path:
        return HTMLResponse(f"<h1>报告未找到</h1><p>{filename} 暂无报告。</p>", status_code=404)
    with open(json_path, encoding="utf-8") as f:
        payload = json.load(f)
    payload = _sanitize(payload)
    agent0 = payload.get("agent0", {})
    a1 = payload.get("agent1", {})
    a2 = payload.get("agent2", {})
    a3 = payload.get("agent3", {})
    a2a = payload.get("agent2a", {})
    html = build_html_report(agent0, a1, a2, a3, a2a)
    return HTMLResponse(html)

@app.get("/api/status")
async def api_status():
    if _scheduler:
        _state["active_jobs"] = _scheduler.active_jobs
        _state["completed_jobs"] = _scheduler.completed_jobs
        _state["last_poll_at"] = _scheduler.last_poll_at
        _state["next_poll_at"] = _scheduler.next_poll_at if _scheduler._running else None
        _state["polling_interval_sec"] = _scheduler.interval
        if getattr(_scheduler, '_latest_review', None):
            _state["latest_review"] = _scheduler._latest_review
    if _wangqi:
        _state["wangqi"]["active_jobs"] = _wangqi.active_jobs
        _state["wangqi"]["completed_jobs"] = _wangqi.completed_jobs
        _state["wangqi"]["last_poll_at"] = _wangqi.last_poll_at
        _state["wangqi"]["next_poll_at"] = _wangqi.next_poll_at if _wangqi._running else None
        _state["wangqi"]["polling_interval_sec"] = _wangqi.interval
    return JSONResponse(_state)


@app.get("/api/progress/stream")
async def sse_stream(request: Request):
    """SSE 实时进度流"""
    q: queue.Queue = queue.Queue(maxsize=100)
    _progress_queues.append(q)

    async def event_generator():
        # 先发一条连接确认
        yield f"event: connected\ndata: {json.dumps({'status':'connected'})}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = q.get(timeout=1)
                    yield f"event: progress\ndata: {data}\n\n"
                except queue.Empty:
                    # 心跳
                    yield f": heartbeat\n\n"
        finally:
            if q in _progress_queues:
                _progress_queues.remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/trigger")
async def api_trigger():
    """手动触发一轮轮询"""
    if not _scheduler:
        return JSONResponse({"error": "调度器未初始化"}, status_code=503)
    try:
        results = await _scheduler.poll_now()
        return JSONResponse({"status": "ok", "processed": len(results)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)[:500]}, status_code=500)


@app.post("/api/scheduler/start")
async def api_scheduler_start():
    """启动调度器"""
    if not _scheduler:
        return JSONResponse({"error": "调度器未初始化"}, status_code=503)
    if _scheduler._running:
        return JSONResponse({"status": "ok", "message": "已在运行"})
    await _scheduler.start()
    _state["scheduler_running"] = True
    # 立即设置下次轮询时间
    from datetime import timedelta
    _scheduler.next_poll_at = (datetime.now(timezone.utc) + timedelta(seconds=_scheduler.interval)).isoformat()
    return JSONResponse({"status": "ok", "message": "已启动"})


@app.post("/api/scheduler/stop")
async def api_scheduler_stop():
    """停止调度器"""
    if not _scheduler:
        return JSONResponse({"error": "调度器未初始化"}, status_code=503)
    if not _scheduler._running:
        return JSONResponse({"status": "ok", "message": "已停止"})
    await _scheduler.stop()
    _state["scheduler_running"] = False
    _scheduler.next_poll_at = None
    return JSONResponse({"status": "ok", "message": "已停止"})


@app.post("/api/scheduler/interval")
async def api_scheduler_interval(request: Request):
    """设置轮询间隔（秒）"""
    if not _scheduler:
        return JSONResponse({"error": "调度器未初始化"}, status_code=503)
    try:
        body = await request.json()
        new_interval = int(body.get("interval_sec", 600))
        if new_interval < 60:
            return JSONResponse({"error": "间隔不能小于60秒"}, status_code=400)
        if new_interval > 86400:
            return JSONResponse({"error": "间隔不能超过86400秒(24小时)"}, status_code=400)
        _scheduler.interval = new_interval
        _config["polling_interval_sec"] = new_interval
        # 同步更新下次轮询时间
        from datetime import timedelta
        _scheduler.next_poll_at = (datetime.now(timezone.utc) + timedelta(seconds=new_interval)).isoformat()
        # 持久化到 config.json
        import json as _json
        config_path = Path(__file__).resolve().parent / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            _json.dump(_config, f, ensure_ascii=False, indent=2)
        return JSONResponse({"status": "ok", "interval_sec": new_interval})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/scheduler/status")
async def api_scheduler_detail():
    """调度器详细状态"""
    if not _scheduler:
        return JSONResponse({"error": "未初始化"}, status_code=503)
    return JSONResponse({
        "running": _scheduler._running,
        "interval_sec": _scheduler.interval,
        "last_poll_at": _scheduler.last_poll_at,
        "next_poll_at": _scheduler.next_poll_at,
        "current_status": _scheduler.current_poll_status,
        "active_jobs": _scheduler.active_jobs,
        "completed_jobs": _scheduler.completed_jobs[-10:],
        "latest_review": getattr(_scheduler, '_latest_review', None),
    })


# ── 报告审阅 API ──────

@app.post("/api/review/trigger")
async def api_review_trigger():
    """手动触发一轮报告审阅（审阅所有已完成的报告）"""
    if not _scheduler:
        return JSONResponse({"error": "调度器未初始化"}, status_code=503)
    try:
        import sys
        from pathlib import Path as _Path
        sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "src"))
        from report_reviewer import review_batch

        # 取已完成的报告数据
        reports_dir = _Path(__file__).resolve().parent.parent / "reports" / "data"
        done_results = []
        for job in _scheduler.completed_jobs:
            code = job.get("stock_code", "")
            data_path = reports_dir / f"{code}.json"
            if data_path.exists():
                import json as _json
                with open(data_path, encoding="utf-8") as f:
                    done_results.append(_json.load(f))

        if not done_results:
            return JSONResponse({"status": "ok", "reviewed": 0, "message": "无已完成报告可审阅"})

        summary = review_batch(done_results)
        _scheduler._latest_review = summary
        _scheduler._write_review_report(summary, done_results)

        return JSONResponse({
            "status": "ok",
            "reviewed": len(done_results),
            "health": summary.get("overall_health", "?"),
            "grade_distribution": summary.get("grade_distribution", {}),
            "top_flags": summary.get("top_systemic_flags", [])[:5],
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(e)[:300]}, status_code=500)


@app.get("/api/review/status")
async def api_review_status():
    """获取最新审阅状态。优先内存，fallback磁盘文件解析。"""
    if not _scheduler:
        return JSONResponse({"error": "调度器未初始化"}, status_code=503)

    latest = getattr(_scheduler, '_latest_review', None)
    review_dir = Path(__file__).resolve().parent.parent / "reports" / "reviews"
    files = sorted(review_dir.glob("review_*.md"), reverse=True)

    if not latest and not files:
        return JSONResponse({"has_review": False, "available_files": []})

    # 从磁盘文件解析（fallback）
    if not latest and files:
        import re
        latest_file = files[0]
        with open(latest_file, encoding="utf-8") as f:
            text = f.read()
        # 提取健康度
        health_m = re.search(r'\*\*系统健康度\*\*:\s*(.+)', text)
        health = health_m.group(1).strip() if health_m else "?"
        # 提取审阅数
        count_m = re.search(r'\*\*审阅报告数\*\*:\s*(\d+)', text)
        total = int(count_m.group(1)) if count_m else 0
        # 提取评级分布: 匹配 "- **A**: 2份" 或 "- **A**: ██ (2份)"
        grades = {}
        for m in re.finditer(r'\*\*([A-F])\*\*:?\s*(?:█+\s*)?(\d+)份', text):
            grades[m.group(1)] = int(m.group(2))
        # 提取标记
        flags = []
        flag_section = False
        for line in text.split('\n'):
            if '系统性高频问题' in line:
                flag_section = True
                continue
            if flag_section and line.startswith('- **') and '** (' in line:
                parts = line.split('** (')
                if len(parts) >= 2:
                    code = parts[0].replace('- **', '').replace('**', '').strip()
                    count_part = parts[1].split('次)')[0] if '次)' in parts[1] else '1'
                    try: count = int(count_part)
                    except: count = 1
                    flags.append({"code": code, "count": count, "action": ""})
            elif flag_section and line.startswith('无系统性') or (flag_section and line.strip() == ''):
                break

        return JSONResponse({
            "has_review": True,
            "health": health,
            "total_reports": total,
            "grade_distribution": grades,
            "layer_averages": {},
            "top_flags": flags[:5],
            "_source": "disk",
        })

    return JSONResponse({
        "has_review": True,
        "health": latest.get("overall_health", "?"),
        "total_reports": latest.get("total_reports", 0),
        "grade_distribution": latest.get("grade_distribution", {}),
        "layer_averages": latest.get("layer_averages", {}),
        "top_flags": latest.get("top_systemic_flags", [])[:5],
        "_source": "memory",
    })


@app.get("/api/review/list")
async def api_review_list():
    """列出所有审阅报告文件"""
    review_dir = Path(__file__).resolve().parent.parent / "reports" / "reviews"
    files = sorted(review_dir.glob("review_*.md"), reverse=True)
    return JSONResponse([
        {
            "filename": f.name,
            "date": f.stem.replace("review_", ""),
            "url": f"/api/review/file/{f.name}",
        }
        for f in files
    ])


@app.get("/api/review/file/{filename}")
async def api_review_file(filename: str):
    """返回单篇审阅报告的 Markdown 原文"""
    file_path = Path(__file__).resolve().parent.parent / "reports" / "reviews" / filename
    if not file_path.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    with open(file_path, encoding="utf-8") as f:
        return JSONResponse({"filename": filename, "content": f.read()})


@app.get("/review/view/{filename}")
async def view_review_html(filename: str):
    """以 HTML 页面渲染审阅报告"""
    file_path = Path(__file__).resolve().parent.parent / "reports" / "reviews" / filename
    if not file_path.exists():
        return HTMLResponse("<h1>404 — 文件不存在</h1>", status_code=404)
    with open(file_path, encoding="utf-8") as f:
        md = f.read()

    # 简单 Markdown→HTML
    html = md
    html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # 标题
    import re
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    # 粗体
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    # 表格
    html = re.sub(r'^\|(.+)\|$', r'<tr><td>\1</td></tr>', html, flags=re.MULTILINE)
    html = html.replace("<tr><td>", "<tr><td>", 1)  # keep first
    # 分割线
    html = html.replace("---", "<hr>")
    # 列表
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    # 换行
    html = "<div style='white-space:pre-wrap;'>" + html + "</div>"

    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>审阅报告 — {filename}</title>
<style>
  body {{ font-family: 'IBM Plex Mono', 'Noto Sans SC', monospace; background: #050401; color: #F2F4F3; padding: 32px 48px; max-width: 800px; margin: 0 auto; }}
  h1 {{ color: #ADFF00; font-size: 24px; }}
  h2 {{ color: #ADFF00; font-size: 18px; margin-top: 32px; border-bottom: 1px solid #2A2A2A; padding-bottom: 8px; }}
  h3 {{ color: #CCC; font-size: 15px; }}
  strong {{ color: #ADFF00; }}
  hr {{ border: none; border-top: 1px solid #2A2A2A; margin: 24px 0; }}
  li {{ color: #AAA; line-height: 1.8; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  td, th {{ padding: 6px 12px; border: 1px solid #2A2A2A; font-size: 13px; }}
  a {{ color: #ADFF00; }}
</style>
</head>
<body>
{html}
<p style="margin-top:48px;color:#444;font-size:11px;">估值重构引擎 V5 · 报告审阅系统</p>
</body>
</html>""")


def _sanitize(obj):
    """递归清理 NaN/Infinity → None，解决 Python json 无法序列化 NaN 的问题。"""
    if isinstance(obj, float) and (obj != obj or obj in (float('inf'), float('-inf'))):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


@app.get("/api/report/data/{filename}")
async def get_report_data(filename: str):
    """返回估值报告结构化 JSON。filename = {stock_code}_{timestamp}（如 300726_20260522_1004）"""
    data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"
    data_path = data_dir / f"{filename}.json"
    if not data_path.exists():
        data_path = data_dir / "history" / f"{filename}.json"
    if not data_path.exists():
        return JSONResponse({"error": f"未找到 {filename} 的报告数据"}, status_code=404)
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(_sanitize(data))


@app.get("/api/report/{stock_code}/data")
async def get_report_data_legacy(stock_code: str, at: str = ""):
    """兼容旧调用。at=时间戳时返回指定版本；at 为空时返回最新。"""
    data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"
    hist_dir = data_dir / "history"
    # 若 stock_code 含时间戳 (如 "300726_20260522_1505")，拆分为真实 code + at
    parts = stock_code.split("_", 1)
    real_code = parts[0]
    if len(parts) > 1:
        ts_clean = parts[1].replace("_", "")
        if ts_clean.isdigit() and len(ts_clean) >= 12:
            if not at:
                at = parts[1]
            stock_code = real_code

    if at:
        data_path = data_dir / f"{stock_code}_{at}.json"
        if not data_path.exists() and hist_dir.exists():
            data_path = hist_dir / f"{stock_code}_{at}.json"
        if not data_path.exists():
            data_path = data_dir / f"{stock_code}.json"  # 回退: 无时间戳版本
    else:
        files = sorted(list(data_dir.glob(f"{stock_code}_*.json")) + list(hist_dir.glob(f"{stock_code}_*.json")), reverse=True)
        data_path = files[0] if files else data_dir / f"{stock_code}.json"
    if not data_path.exists():
        return JSONResponse({"error": f"未找到 {stock_code} 的报告"}, status_code=404)
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    return JSONResponse(_sanitize(data))


# ── 追踪令 API (兼容 Vite trackingApiPlugin) ──

_TRACKING_DIR = Path(__file__).resolve().parent.parent.parent / ".agents" / "agents" / "shenwaihuashen" / "memory" / "tracking"

# ── Coze 表 ID ──
COZE_TRACKING_TABLE = "7645332166129287218"
COZE_CASES_TABLE = "7645333715039830079"
COZE_LINGGUANG_TABLE = "7645332554400153646"


def _coze_token() -> str:
    """获取 Coze API token"""
    config_path = Path(__file__).resolve().parent / "config.json"
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("coze_sat_token", "") or os.environ.get("COZE_SAT_TOKEN", "")
    except Exception:
        return os.environ.get("COZE_SAT_TOKEN", "")


def _coze_query_all(table_id: str) -> list[dict]:
    """从 Coze 表查询全部记录"""
    import requests as _requests
    token = _coze_token()
    if not token:
        return []
    all_items = []
    page = 1
    s = _requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    while True:
        try:
            r = s.post(f"https://api.coze.cn/v1/databases/{table_id}/records/query",
                       json={"page_num": page, "page_size": 500, "is_async": False}, timeout=30)
            data = r.json()
            if data.get("code") != 0:
                break
            items = data.get("data", {}).get("items", [])
            all_items.extend(items)
            if not data.get("data", {}).get("has_more"):
                break
            page += 1
        except Exception:
            break
    return all_items


def _coze_query_one(table_id: str, filters: list[dict]) -> dict | None:
    """从 Coze 表查询单条记录"""
    import requests as _requests
    token = _coze_token()
    if not token:
        return None
    s = _requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        r = s.post(f"https://api.coze.cn/v1/databases/{table_id}/records/query",
                   json={"page_num": 1, "page_size": 1, "is_async": False,
                         "filter": {"logic": "and", "conditions": filters}}, timeout=30)
        data = r.json()
        items = data.get("data", {}).get("items", [])
        return items[0] if items else None
    except Exception:
        return None


def _coze_insert(table_id: str, rows: list[dict]) -> bool:
    """写入 Coze 表"""
    import requests as _requests
    token = _coze_token()
    if not token:
        return False
    s = _requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        insert_rows = [{k: str(v) if v is not None else "" for k, v in row.items()} for row in rows]
        r = s.post(f"https://api.coze.cn/v1/databases/{table_id}/records",
                   json={"insert_rows": insert_rows, "is_async": False}, timeout=30)
        return r.json().get("code") == 0
    except Exception:
        return False


def _coze_update_by_stock(table_id: str, stock_code: str, fields: dict) -> bool:
    """按 stock_code 更新 Coze 记录"""
    import requests as _requests
    token = _coze_token()
    if not token:
        return False
    s = _requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        update_fields = [{"field_name": k, "value": str(v) if v is not None else ""} for k, v in fields.items()]
        r = s.post(f"https://api.coze.cn/v1/databases/{table_id}/records/update",
                   json={"update_fields": update_fields, "is_async": False,
                         "filter": {"logic": "and", "conditions": [
                             {"left": "stock_code", "operation": "equal", "right": stock_code}]}},
                   timeout=30)
        return r.json().get("code") == 0
    except Exception:
        return False


def _coze_update_by_slug(table_id: str, slug: str, fields: dict) -> bool:
    """按 slug 更新 Coze 记录"""
    import requests as _requests
    token = _coze_token()
    if not token:
        return False
    s = _requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        update_fields = [{"field_name": k, "value": str(v) if v is not None else ""} for k, v in fields.items()]
        r = s.post(f"https://api.coze.cn/v1/databases/{table_id}/records/update",
                   json={"update_fields": update_fields, "is_async": False,
                         "filter": {"logic": "and", "conditions": [
                             {"left": "slug", "operation": "equal", "right": slug}]}},
                   timeout=30)
        return r.json().get("code") == 0
    except Exception:
        return False


# ── 字段映射: Coze 列名 → API JSON 格式 ──

def _map_tracking_from_coze(row: dict) -> dict:
    """将 Coze 追踪令记录转为前端 JSON 格式"""
    def _parse(v):
        if isinstance(v, str) and v:
            try: return json.loads(v)
            except: return v
        return v

    return {
        "stockCode": row.get("stock_code", ""),
        "stockName": row.get("stock_name", ""),
        "direction": row.get("direction", ""),
        "thesis": row.get("thesis", ""),
        "conviction": int(row.get("conviction", 0) or 0),
        "decisionDate": row.get("decision_date", ""),
        "decision": row.get("decision", ""),
        "recommendedPosition": int(row.get("recommended_position", 0) or 0),
        "actualPosition": 0,
        "entryCondition": row.get("entry_condition", ""),
        "entryPriceTarget": float(row.get("base_price", 0) or 0),
        "basePrice": float(row.get("base_price", 0) or 0),
        "baseMarketCap": float(row.get("base_market_cap", 0) or 0),
        "baseDate": row.get("base_date", ""),
        "pillars": _parse(row.get("pillars_json", "[]")),
        "risks": _parse(row.get("risks_json", "[]")),
        "catalystCalendar": _parse(row.get("catalyst_json", "[]")),
        "priceLog": _parse(row.get("price_log_json", "[]")),
        "thesisLog": _parse(row.get("thesis_log_json", "[]")),
        "positionLog": [],
        "exitConditions": (_parse(row.get("meta_json", "{}")) or {}).get("exit_conditions", []),
        "aShareTracking": (_parse(row.get("meta_json", "{}")) or {}).get("a_share_tracking", {}),
        "reviewSchedule": (_parse(row.get("meta_json", "{}")) or {}).get("review_schedule", {}),
        "updatedAt": row.get("updated_at", ""),
        "file_name": row.get("file_name", ""),
    }


def _map_case_from_coze(row: dict) -> dict:
    """将 Coze 案例记录转为前端 JSON 格式"""
    def _parse(v):
        if isinstance(v, str) and v:
            try: return json.loads(v)
            except: return v
        return v
    return {
        "id": f"case-{row.get('stock_code', '')}",
        "stockName": row.get("stock_name", ""),
        "stockCode": row.get("stock_code", ""),
        "sector": row.get("sector", ""),
        "logic": row.get("logic", ""),
        "catalyst": row.get("catalyst", ""),
        "primaryDriver": row.get("primary_driver", ""),
        "startDate": row.get("start_date", ""),
        "startPrice": str(row.get("start_price", "")),
        "entryPrice": str(row.get("entry_price", "")),
        "exitPrice": str(row.get("exit_price", "")),
        "peakPrice": str(row.get("peak_price", "")),
        "peakDate": row.get("peak_date", ""),
        "returnType": row.get("return_type", ""),
        "endState": row.get("end_state", ""),
        "gainMultiple": str(row.get("gain_multiple", "")),
        "actualReturnPct": str(row.get("actual_return_pct", "")),
        "maxDrawdownPct": str(row.get("max_drawdown_pct", "")),
        "peExpansion": str(row.get("pe_expansion", "")),
        "roicImprovement": str(row.get("roic_improvement", "")),
        "tags": _parse(row.get("tags_json", "[]")),
    }


def _map_lingguang_from_coze(row: dict) -> dict:
    """将 Coze 灵光记录转为前端 JSON 格式"""
    def _parse(v):
        if isinstance(v, str) and v:
            try: return json.loads(v)
            except: return v
        return v
    return {
        "id": row.get("slug", ""),
        "slug": row.get("slug", ""),
        "title": row.get("title", ""),
        "content": row.get("content", ""),
        "source": row.get("source", ""),
        "confidence": row.get("confidence", ""),
        "tags": _parse(row.get("tags_json", "[]")),
        "matches": _parse(row.get("matches_json", "[]")),
        "revisionHistory": _parse(row.get("revision_json", "[]")),
        "createdAt": row.get("created_at", ""),
        "updatedAt": row.get("updated_at", ""),
    }


@app.get("/api/tracking")
async def api_tracking_list():
    """返回所有追踪令列表，兼容前端 Tracking 页面的 /api/tracking 调用 — Coze 优先，本地回退"""
    # 优先 Coze
    rows = _coze_query_all(COZE_TRACKING_TABLE)
    if rows:
        return JSONResponse([_map_tracking_from_coze(r) for r in rows])
    # 本地回退
    if not _TRACKING_DIR.exists():
        return JSONResponse([])
    files = [f for f in _TRACKING_DIR.iterdir() if f.suffix == ".json" and f.stem != "_template"]
    stocks = []
    for fp in sorted(files):
        data = _read_json(fp)
        if data:
            stocks.append(data)
    return JSONResponse(stocks)


# ── V5 新增: 赔率排序 API ──────

@app.get("/api/ranking")
async def api_ranking():
    """返回最新赔率排序结果"""
    ranking_dir = Path(__file__).resolve().parent.parent / "reports" / "ranking"
    if not ranking_dir.exists():
        return JSONResponse({"error": "暂无排序数据"}, status_code=404)
    files = sorted(ranking_dir.glob("ranking_*.json"), reverse=True)
    if not files:
        return JSONResponse({"error": "暂无排序数据"}, status_code=404)
    with open(files[0], encoding="utf-8") as f:
        return JSONResponse(json.load(f))


# ── 批量报告摘要 API ────────────────────

@app.get("/api/reports/summaries")
async def get_report_summaries(codes: str = ""):
    """批量获取报告的资讯摘要（从磁盘 JSON 读取 raw_event_text）"""
    if not codes:
        return JSONResponse({})
    data_dir = Path(__file__).resolve().parent.parent / "reports" / "data"
    result = {}
    for code in codes.split(","):
        code = code.strip()
        if not code:
            continue
        f = data_dir / f"{code}.json"
        if f.exists():
            try:
                with open(f, encoding="utf-8") as fh:
                    payload = json.load(fh)
                a0 = payload.get("agent0", {})
                raw = a0.get("raw_event_text") or a0.get("investment_theme") or ""
                result[code] = raw if raw else ""
            except Exception:
                result[code] = ""
        else:
            result[code] = ""
    return JSONResponse(result)


# ── 产业链利润流 API ────────────────────

@app.get("/api/industry-chain/status")
async def api_ic_status():
    """望气调度器状态 + Coze 表统计"""
    result = {
        "scheduler": {
            "initialized": _wangqi is not None,
            "running": _wangqi._running if _wangqi else False,
            "interval_sec": _wangqi.interval if _wangqi else None,
            "last_poll_at": _wangqi.last_poll_at if _wangqi else None,
            "next_poll_at": _wangqi.next_poll_at if _wangqi else None,
            "current_status": _wangqi.current_status if _wangqi else "not_initialized",
            "completed_count": len(_wangqi.completed_jobs) if _wangqi else 0,
            "completed_jobs": (_wangqi.completed_jobs[-20:] if _wangqi else []),
        },
    }
    # Coze 表统计（向后兼容）
    if _ic_coze:
        try:
            output_db = _ic_coze.get_output_db_id()
            if output_db:
                coze = CozeClient(token=_config["coze_sat_token"], workspace_id=_config["coze_workspace_id"])
                records = coze.query_all_records(output_db)
                incomplete = [r for r in records if str(r.get("is_complete", "")).lower() != "true"]
                result["coze_table"] = {
                    "database_id": output_db,
                    "total_records": len(records),
                    "pending_records": len(incomplete),
                    "completed_records": len(records) - len(incomplete),
                    "last_updated": "",
                }
        except Exception as e:
            result["coze_table"] = {"error": str(e)[:200]}
    return JSONResponse(result)


@app.post("/api/industry-chain/trigger")
async def api_ic_trigger():
    """手动触发一轮产业链分析"""
    if not _wangqi:
        return JSONResponse({"error": "产业链调度器未初始化"}, status_code=503)
    results = await _wangqi.poll_now()
    from valuation_app.industry_chain_scheduler import _safe_pick_name
    return JSONResponse({
        "status": "ok",
        "processed": len(results),
        "results": [
            {
                "record_id": r.get("record_id", ""),
                "status": r.get("status", ""),
                "top_pick": _safe_pick_name(r.get("top_pick")),
                "runner_up": _safe_pick_name(r.get("runner_up")),
                "error": r.get("error", ""),
            }
            for r in results
        ],
    })


@app.post("/api/industry-chain/start")
async def api_ic_start():
    """启动产业链调度器"""
    if not _wangqi:
        return JSONResponse({"error": "产业链调度器未初始化"}, status_code=503)
    if _wangqi._running:
        return JSONResponse({"status": "ok", "message": "已在运行"})
    await _wangqi.start()
    return JSONResponse({"status": "ok", "message": "已启动"})


@app.post("/api/industry-chain/stop")
async def api_ic_stop():
    """停止产业链调度器"""
    if not _wangqi:
        return JSONResponse({"error": "产业链调度器未初始化"}, status_code=503)
    if not _wangqi._running:
        return JSONResponse({"status": "ok", "message": "已停止"})
    await _wangqi.stop()
    return JSONResponse({"status": "ok", "message": "已停止"})


@app.post("/api/industry-chain/interval")
async def api_wangqi_interval(request: Request):
    """设置天机轮询间隔（秒），持久化到 config.json"""
    if not _wangqi:
        return JSONResponse({"error": "望气调度器未初始化"}, status_code=503)
    try:
        body = await request.json()
        new_interval = int(body.get("interval_sec", 3600))
        if new_interval < 300:
            return JSONResponse({"error": "间隔不能小于300秒(5分钟)"}, status_code=400)
        if new_interval > 86400:
            return JSONResponse({"error": "间隔不能超过86400秒(24小时)"}, status_code=400)
        _wangqi.set_interval(new_interval)
        _config["tianji_poll_interval_sec"] = new_interval
        import json as _json
        config_path = Path(__file__).resolve().parent / "config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            _json.dump(_config, f, ensure_ascii=False, indent=2)
        return JSONResponse({"status": "ok", "interval_sec": new_interval})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/industry-chain/progress/stream")
async def api_wangqi_sse(request: Request):
    """天机 SSE 实时进度流"""
    q: queue.Queue = queue.Queue(maxsize=100)
    _wangqi_queues.append(q)

    async def event_generator():
        yield f"event: connected\ndata: {json.dumps({'type':'connected'})}\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = q.get(timeout=1)
                    yield f"event: tianji\ndata: {data}\n\n"
                except queue.Empty:
                    yield f": heartbeat\n\n"
        finally:
            if q in _wangqi_queues:
                _wangqi_queues.remove(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/industry-chain/results")
async def api_ic_results():
    """获取产业链分析历史结果"""
    if not _ic_coze:
        return JSONResponse({"status": "error", "results": [], "message": "产业链模块未初始化"}, status_code=503)
    try:
        output_db = _ic_coze.get_output_db_id()
        if not output_db:
            return JSONResponse({"status": "ok", "count": 0, "results": []})
        coze = CozeClient(
            token=_config["coze_sat_token"],
            workspace_id=_config["coze_workspace_id"],
        )
        records = coze.query_all_records(output_db)
        records.sort(key=lambda r: r.get("bstudio_create_time", ""), reverse=True)
        # 转换为前端 IndustryChain.tsx 期望的格式
        results = []
        for r in records[:50]:
            results.append({
                "source_record_id": r.get("source_record_id", r.get("uuid", "")),
                "news_content": str(r.get("news_content", "")),
                "industry_chain": r.get("industry_chain", ""),
                "event_summary": str(r.get("event_summary", "")),
                "top_nodes_json": r.get("top_nodes_json", ""),
                "top_pick_code": r.get("top_pick_code", ""),
                "top_pick_name": r.get("top_pick_name", ""),
                "top_pick_score": r.get("top_pick_score", ""),
                "top_pick_thesis": str(r.get("top_pick_thesis", "")),
                "runner_up_code": r.get("runner_up_code", ""),
                "runner_up_name": r.get("runner_up_name", ""),
                "runner_up_score": r.get("runner_up_score", ""),
                "runner_up_thesis": str(r.get("runner_up_thesis", "")),
                "top5_json": r.get("top5_json", ""),
                "analysis_date": r.get("bstudio_create_time", ""),
                "status": "done" if r.get("status", "pending") else "pending",
            })
        return JSONResponse({"status": "ok", "count": len(results), "results": results})
    except Exception as e:
        return JSONResponse({"status": "error", "results": [], "message": str(e)[:200]}, status_code=500)


@app.post("/api/industry-chain/analyze/{record_id}")
async def api_ic_analyze_one(record_id: str):
    """分析指定的单条产业资讯记录"""
    if not _wangqi:
        return JSONResponse({"error": "望气调度器未初始化"}, status_code=503)
    result = await _wangqi.analyze_one(record_id)
    return JSONResponse(result)


# ── 身外化身 CC 发送 API ──────────────────

# 身外化身 agent 目录
_CC_AVATAR_DIR = Path(__file__).resolve().parent.parent.parent / ".agents" / "agents" / "shenwaihuashen"
_CC_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent  # 长流水前端根目录
_CC_AGENTS_DIR = _CC_PROJECT_DIR / ".agents" / "agents"  # CC 会话所在目录


@app.post("/api/avatar/cc/send")
async def api_cc_send(request: Request):
    """发送上下文到身外化身持久会话。首次用 --session-id 创建，后续用 --continue 续接。"""
    body = await request.json()
    prompt = body.get("prompt", "")
    max_turns = body.get("max_turns", 5)

    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    # 读取固定会话 ID（用户在 CC 中配置好）
    cfg_file = _CC_AVATAR_DIR / "config.json"
    session_id = None
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
            session_id = cfg.get("ccSessionId")
        except Exception:
            pass

    async def generate():
        proc = None
        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            import shutil as _shutil
            claude_bin = _shutil.which("claude")
            if not claude_bin:
                claude_bin = os.path.expandvars(r"%APPDATA%\npm\claude.cmd")
            if not claude_bin or not os.path.exists(claude_bin):
                claude_bin = os.path.expandvars(r"%APPDATA%\npm\claude")

            args = [claude_bin, "-p",
                    "--max-turns", str(max_turns),
                    "--output-format", "stream-json",
                    "--verbose"]

            if session_id:
                args.extend(["--resume", session_id])

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(_CC_AGENTS_DIR),  # 匹配 CC 会话所在目录
            )

            prompt_bytes = prompt.encode("utf-8")
            proc.stdin.write(prompt_bytes)
            await proc.stdin.drain()
            proc.stdin.close()

            yield f"data: {json.dumps({'type': 'start', 'session': session_id})}\n\n"

            buffer = ""
            while True:
                try:
                    chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=300)
                except asyncio.TimeoutError:
                    break
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")
                lines = buffer.split("\n")
                buffer = lines.pop()
                for line in lines:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        msg = json.loads(text)
                        mt = msg.get("type", "")
                        if mt == "assistant":
                            for block in msg.get("message", {}).get("content", []):
                                if block.get("type") == "text":
                                    yield f"data: {json.dumps({'type': 'chunk', 'text': block.get('text', '')}, ensure_ascii=False)}\n\n"
                        elif mt == "result":
                            yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    except json.JSONDecodeError:
                        pass

            await proc.wait()

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)[:500]}, ensure_ascii=False)}\n\n"
        finally:
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── 身外化身 记忆 API ──────────────────────

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / ".agents" / "agents" / "shenwaihuashen" / "memory"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / ".agents" / "agents" / "shenwaihuashen" / "output"


def _read_json(path: Path) -> dict | list | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path: Path, data: dict | list) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _update_index():
    """重新生成 _index.json"""
    ling_dir = MEMORY_DIR / "lingguang"
    case_dir = MEMORY_DIR / "cases"
    track_dir = MEMORY_DIR / "tracking"
    idx = {
        "version": 1,
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "lingguangCount": 0,
        "caseCount": 0,
        "trackingCount": 0,
        "lingguangIndex": {},
        "caseIndex": {},
        "trackingIndex": {},
    }
    if ling_dir.exists():
        for f in sorted(ling_dir.glob("lg-*.json")):
            d = _read_json(f)
            if d:
                idx["lingguangIndex"][f.stem] = {
                    "title": d.get("title", ""),
                    "tags": d.get("tags", []),
                    "updatedAt": d.get("updatedAt", ""),
                }
    idx["lingguangCount"] = len(idx["lingguangIndex"])
    if case_dir.exists():
        for f in sorted(case_dir.glob("case-*.json")):
            d = _read_json(f)
            if d:
                idx["caseIndex"][f.stem] = {
                    "stockName": d.get("stockName", ""),
                    "stockCode": d.get("stockCode", ""),
                    "sector": d.get("sector", ""),
                    "gainMultiple": d.get("gainMultiple", ""),
                    "returnType": d.get("returnType", ""),
                    "tags": d.get("tags", []),
                }
    idx["caseCount"] = len(idx["caseIndex"])
    if track_dir.exists():
        for f in sorted(track_dir.glob("track-*.json")):
            d = _read_json(f)
            if d and d.get("stockCode"):
                idx["trackingIndex"][d["stockCode"]] = {
                    "stockName": d.get("stockName", ""),
                    "status": d.get("status", "active"),
                    "lastUpdated": d.get("updatedAt", ""),
                }
    idx["trackingCount"] = len(idx["trackingIndex"])
    _write_json(MEMORY_DIR / "_index.json", idx)
    return idx


@app.get("/api/avatar/memory/index")
async def api_memory_index():
    """获取记忆总索引 — Coze 优先，本地回退"""
    # 优先从 Coze 三表聚合
    try:
        tracking_rows = _coze_query_all(COZE_TRACKING_TABLE)
        case_rows = _coze_query_all(COZE_CASES_TABLE)
        ling_rows = _coze_query_all(COZE_LINGGUANG_TABLE)
        if tracking_rows or case_rows or ling_rows:
            idx = {
                "version": 2,
                "lastUpdated": datetime.now(timezone.utc).isoformat(),
                "lingguangCount": len(ling_rows),
                "caseCount": len(case_rows),
                "trackingCount": len(tracking_rows),
                "lingguangIndex": {},
                "caseIndex": {},
                "trackingIndex": {},
                "_source": "coze",
            }
            for r in ling_rows:
                idx["lingguangIndex"][r.get("slug", "")] = {
                    "title": r.get("title", ""),
                    "tags": (lambda v: json.loads(v) if isinstance(v, str) and v else [])(r.get("tags_json", "[]")),
                    "updatedAt": r.get("updated_at", ""),
                }
            for r in case_rows:
                idx["caseIndex"][f"case-{r.get('stock_code', '')}"] = {
                    "stockName": r.get("stock_name", ""),
                    "stockCode": r.get("stock_code", ""),
                    "sector": r.get("sector", ""),
                    "gainMultiple": str(r.get("gain_multiple", "")),
                    "returnType": r.get("return_type", ""),
                    "tags": (lambda v: json.loads(v) if isinstance(v, str) and v else [])(r.get("tags_json", "[]")),
                }
            for r in tracking_rows:
                code = r.get("stock_code", "")
                if code:
                    idx["trackingIndex"][code] = {
                        "stockName": r.get("stock_name", ""),
                        "status": "active",
                        "lastUpdated": r.get("updated_at", ""),
                    }
            return JSONResponse(idx)
    except Exception:
        pass
    # 本地回退
    idx = _read_json(MEMORY_DIR / "_index.json")
    if not idx:
        idx = _update_index()
    return JSONResponse(idx)


@app.get("/api/avatar/memory/lingguang")
async def api_list_lingguang():
    """列出所有灵光 — Coze 优先，本地回退"""
    rows = _coze_query_all(COZE_LINGGUANG_TABLE)
    if rows:
        return JSONResponse([_map_lingguang_from_coze(r) for r in rows])
    # 本地回退
    items = []
    d = MEMORY_DIR / "lingguang"
    if d.exists():
        for f in sorted(d.glob("lg-*.json")):
            data = _read_json(f)
            if data:
                items.append(data)
    return JSONResponse(items)


@app.get("/api/avatar/memory/lingguang/{slug}")
async def api_get_lingguang(slug: str):
    """获取单条灵光 — Coze 优先，本地回退"""
    row = _coze_query_one(COZE_LINGGUANG_TABLE, [{"left": "slug", "operation": "equal", "right": slug}])
    if row:
        return JSONResponse(_map_lingguang_from_coze(row))
    # 本地回退
    data = _read_json(MEMORY_DIR / "lingguang" / f"{slug}.json")
    return JSONResponse(data or {"error": "not found"})


@app.put("/api/avatar/memory/lingguang/{slug}")
async def api_save_lingguang(slug: str, request: Request):
    """保存（创建或更新）灵光 — 本地 + Coze 双写"""
    body = await request.json()
    body["id"] = slug
    body["updatedAt"] = datetime.now(timezone.utc).isoformat()
    if "createdAt" not in body:
        body["createdAt"] = body["updatedAt"]
    if "revisionHistory" not in body:
        body["revisionHistory"] = []
    # 本地写入（始终保留）
    local_ok = _write_json(MEMORY_DIR / "lingguang" / f"{slug}.json", body)
    if local_ok:
        _update_index()
    # Coze 同步写入
    try:
        coze_fields = {
            "slug": slug,
            "title": str(body.get("title", "")),
            "content": str(body.get("content", "")),
            "source": str(body.get("source", "")),
            "confidence": str(body.get("confidence", "")),
            "tags_json": json.dumps(body.get("tags", []), ensure_ascii=False),
            "matches_json": json.dumps(body.get("matches", []), ensure_ascii=False),
            "revision_json": json.dumps(body.get("revisionHistory", []), ensure_ascii=False),
            "updated_at": body["updatedAt"],
            "created_at": body.get("createdAt", body["updatedAt"]),
        }
        # 检查是否已存在
        existing = _coze_query_one(COZE_LINGGUANG_TABLE, [{"left": "slug", "operation": "equal", "right": slug}])
        if existing:
            _coze_update_by_slug(COZE_LINGGUANG_TABLE, slug, coze_fields)
        else:
            _coze_insert(COZE_LINGGUANG_TABLE, [coze_fields])
    except Exception:
        pass  # Coze 写失败不影响本地
    if local_ok:
        return JSONResponse({"ok": True, "slug": slug})
    return JSONResponse({"ok": False, "error": "write failed"}, status_code=500)


@app.delete("/api/avatar/memory/lingguang/{slug}")
async def api_delete_lingguang(slug: str):
    """删除灵光"""
    path = MEMORY_DIR / "lingguang" / f"{slug}.json"
    try:
        path.unlink()
        _update_index()
        return JSONResponse({"ok": True})
    except Exception:
        return JSONResponse({"ok": False}, status_code=404)


@app.get("/api/avatar/memory/cases")
async def api_list_cases():
    """列出所有案例 — Coze 优先，本地回退"""
    rows = _coze_query_all(COZE_CASES_TABLE)
    if rows:
        return JSONResponse([_map_case_from_coze(r) for r in rows])
    # 本地回退
    items = []
    d = MEMORY_DIR / "cases"
    if d.exists():
        for f in sorted(d.glob("case-*.json"), reverse=True):
            data = _read_json(f)
            if data:
                items.append(data)
    return JSONResponse(items)


@app.get("/api/avatar/memory/cases/{slug}")
async def api_get_case(slug: str):
    """获取完整案例 — Coze 优先，本地回退"""
    # slug 格式: "case-000408"，提取 stock_code
    code = slug.replace("case-", "").upper()
    row = _coze_query_one(COZE_CASES_TABLE, [{"left": "stock_code", "operation": "equal", "right": code}])
    if row:
        return JSONResponse(_map_case_from_coze(row))
    # 本地回退
    data = _read_json(MEMORY_DIR / "cases" / f"{slug}.json")
    return JSONResponse(data or {"error": "not found"})


@app.put("/api/avatar/memory/cases/{slug}")
async def api_save_case(slug: str, request: Request):
    """保存案例 — 本地 + Coze 双写"""
    body = await request.json()
    body["id"] = slug
    body["updatedAt"] = datetime.now(timezone.utc).isoformat()
    if "createdAt" not in body:
        body["createdAt"] = body["updatedAt"]
    # 本地写入
    local_ok = _write_json(MEMORY_DIR / "cases" / f"{slug}.json", body)
    if local_ok:
        _update_index()
    # Coze 同步写入
    try:
        code = slug.replace("case-", "").upper()
        coze_fields = {
            "stock_code": code,
            "stock_name": str(body.get("stockName", "")),
            "sector": str(body.get("sector", "")),
            "logic": str(body.get("logic", "")),
            "catalyst": str(body.get("catalyst", "")),
            "primary_driver": str(body.get("primaryDriver", "")),
            "start_date": str(body.get("startDate", "")),
            "start_price": str(body.get("startPrice", "")),
            "entry_price": str(body.get("entryPrice", "")),
            "exit_price": str(body.get("exitPrice", "")),
            "peak_price": str(body.get("peakPrice", "")),
            "peak_date": str(body.get("peakDate", "")),
            "return_type": str(body.get("returnType", "")),
            "end_state": str(body.get("endState", "")),
            "gain_multiple": str(body.get("gainMultiple", "")),
            "actual_return_pct": str(body.get("actualReturnPct", "")),
            "max_drawdown_pct": str(body.get("maxDrawdownPct", "")),
            "pe_expansion": str(body.get("peExpansion", "")),
            "roic_improvement": str(body.get("roicImprovement", "")),
            "tags_json": json.dumps(body.get("tags", []), ensure_ascii=False),
        }
        existing = _coze_query_one(COZE_CASES_TABLE, [{"left": "stock_code", "operation": "equal", "right": code}])
        if existing:
            _coze_update_by_stock(COZE_CASES_TABLE, code, coze_fields)
        else:
            _coze_insert(COZE_CASES_TABLE, [coze_fields])
    except Exception:
        pass
    if local_ok:
        return JSONResponse({"ok": True, "slug": slug})
    return JSONResponse({"ok": False, "error": "write failed"}, status_code=500)


@app.put("/api/avatar/memory/cases/{slug}/from-tracking")
async def api_upgrade_tracking_to_case(slug: str):
    """从追踪升级为案例（evolve skill 的终局复盘用）— Coze 优先，本地回退"""
    tracking = None
    # 优先从 Coze 查追踪令
    row = _coze_query_one(COZE_TRACKING_TABLE, [{"left": "stock_code", "operation": "equal", "right": slug.upper()}])
    if row:
        tracking = _map_tracking_from_coze(row)
    # 本地回退
    if not tracking:
        track_dir = MEMORY_DIR / "tracking"
        if track_dir.exists():
            for f in track_dir.glob("track-*.json"):
                d = _read_json(f)
                if d and d.get("stockCode", "").lower() == slug.lower():
                    tracking = d
                    break
    if not tracking:
        return JSONResponse({"ok": False, "error": "tracking not found"}, status_code=404)

    # 从 tracking 构建 case
    dc = tracking.get("decisionCycle", {})
    new_case = {
        "id": f"case-{slug.lower()}",
        "stockName": tracking.get("stockName", ""),
        "stockCode": tracking.get("stockCode", ""),
        "status": "exited",
        "entryPrice": str(dc.get("entryPriceRef", "")),
        "targetPrice": str(dc.get("targetPriceRef", "")),
        "decisionLogic": dc.get("decisionBasis", ""),
        "keyAssumptions": dc.get("keyAssumptions", []),
        "priceTracking": tracking.get("priceTracking", []),
        "eventTracking": tracking.get("eventTracking", []),
        "feedbackLoop": tracking.get("feedbackLoop", {}),
        "createdAt": tracking.get("createdAt", datetime.now(timezone.utc).isoformat()),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    ok = _write_json(MEMORY_DIR / "cases" / f"case-{slug.lower()}.json", new_case)
    if ok:
        _update_index()
        return JSONResponse({"ok": True, "case": new_case})
    return JSONResponse({"ok": False, "error": "write failed"}, status_code=500)


@app.get("/api/avatar/memory/tracking")
async def api_list_tracking():
    """列出所有追踪 — Coze 优先，本地回退"""
    rows = _coze_query_all(COZE_TRACKING_TABLE)
    if rows:
        return JSONResponse([_map_tracking_from_coze(r) for r in rows])
    # 本地回退
    items = []
    d = MEMORY_DIR / "tracking"
    if d.exists():
        for f in sorted(d.glob("track-*.json")):
            data = _read_json(f)
            if data and data.get("stockCode"):
                items.append(data)
    return JSONResponse(items)


@app.get("/api/avatar/memory/tracking/{ticker}")
async def api_get_tracking(ticker: str):
    """获取单条追踪 — Coze 优先，本地回退"""
    row = _coze_query_one(COZE_TRACKING_TABLE, [{"left": "stock_code", "operation": "equal", "right": ticker}])
    if row:
        return JSONResponse(_map_tracking_from_coze(row))
    # 本地回退
    data = _read_json(MEMORY_DIR / "tracking" / f"track-{ticker}.json")
    return JSONResponse(data or {"error": "not found"})


@app.post("/api/avatar/memory/tracking/{ticker}")
async def api_create_or_update_tracking(ticker: str, request: Request):
    """创建或更新追踪 — 本地 + Coze 双写"""
    body = await request.json()
    body["stockCode"] = ticker
    body["updatedAt"] = datetime.now(timezone.utc).isoformat()
    if "createdAt" not in body:
        body["createdAt"] = body["updatedAt"]
    # 本地写入
    local_ok = _write_json(MEMORY_DIR / "tracking" / f"track-{ticker}.json", body)
    if local_ok:
        _update_index()
    # Coze 同步写入
    try:
        coze_fields = {
            "stock_code": ticker,
            "stock_name": str(body.get("stockName", "")),
            "file_name": f"{ticker}-{body.get('stockName', '')}.json",
            "direction": str(body.get("direction", "")),
            "thesis": str(body.get("thesis", "")),
            "conviction": str(body.get("conviction", "")),
            "decision_date": str(body.get("decisionDate", "")),
            "decision": str(body.get("decision", "")),
            "recommended_position": str(body.get("recommendedPosition", "")),
            "entry_condition": str(body.get("entryCondition", "")),
            "base_price": str(body.get("basePrice", "")),
            "base_market_cap": str(body.get("baseMarketCap", "")),
            "base_date": str(body.get("baseDate", "")),
            "pillars_json": json.dumps(body.get("pillars", []), ensure_ascii=False),
            "risks_json": json.dumps(body.get("risks", []), ensure_ascii=False),
            "catalyst_json": json.dumps(body.get("catalystCalendar", []), ensure_ascii=False),
            "price_log_json": json.dumps(body.get("priceLog", []), ensure_ascii=False),
            "thesis_log_json": json.dumps(body.get("thesisLog", []), ensure_ascii=False),
            "meta_json": json.dumps({
                "exitConditions": body.get("exitConditions", []),
                "aShareTracking": body.get("aShareTracking", {}),
                "reviewSchedule": body.get("reviewSchedule", {}),
                "positionLog": body.get("positionLog", []),
            }, ensure_ascii=False),
            "updated_at": body["updatedAt"],
        }
        existing = _coze_query_one(COZE_TRACKING_TABLE, [{"left": "stock_code", "operation": "equal", "right": ticker}])
        if existing:
            _coze_update_by_stock(COZE_TRACKING_TABLE, ticker, coze_fields)
        else:
            _coze_insert(COZE_TRACKING_TABLE, [coze_fields])
    except Exception:
        pass
    if local_ok:
        return JSONResponse({"ok": True, "ticker": ticker})
    return JSONResponse({"ok": False, "error": "write failed"}, status_code=500)


# ── 启动入口 ──────────────────────────────

# ── 前端静态文件 ──────────────────────────

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "dist"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    app.mount("/images", StaticFiles(directory=FRONTEND_DIR / "images"), name="images")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """SPA fallback — 非 API 路由返回 index.html"""
        # API 和已有路由优先匹配，这里只处理前端页面
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    config = _load_config()
    uvicorn.run(
        "valuation_app.server:app",
        host=config.get("server_host", "0.0.0.0"),
        port=config.get("server_port", 8080),
        reload=False,
    )
