"""监控大屏数据聚合 — 从审计日志 + 调度器内存状态生成健康报告

健康判定（红黄绿）：
- green: 调度器 running 且最后活动时间在 interval*2 内
- yellow: running 但最后活动时间在 interval*2~4 之间（可能卡顿）
- red: 未运行 / 最后活动超过 interval*4（疑似卡死）

系统性偏差检测（vs 7日均值）：
- 今日拦截率偏离 7 日均值超过 2σ → 偏差警告
- 望气"无高赔率"率 > 85% → 候选池/评分阈值警告
- 天机峰放行率 < 1% → 种子阈值可能过严
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
AUDIT_DIR = REPORTS_DIR / "audit_logs"
DATA_DIR = REPORTS_DIR / "data"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _load_audit(days: int = 7) -> list[dict]:
    """加载最近 N 天审计日志。"""
    rows = []
    for d in range(days):
        day = (_now_utc() - timedelta(days=d)).strftime("%Y%m%d")
        fp = AUDIT_DIR / f"audit_{day}.jsonl"
        if fp.exists():
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass
    # 清洗 surrogate 字符（GBK 历史数据污染）
    for r in rows:
        for k in list(r.keys()):
            if isinstance(r[k], str):
                try:
                    r[k] = r[k].encode("utf-8", errors="replace").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    r[k] = ""
    return rows


def _health(status_running: bool, last_activity: str | None, interval_sec: int) -> dict:
    """红黄绿健康判定。识别避峰顺延状态（调度器主动跳过高峰时段）。"""
    if not status_running:
        return {"status": "red", "reason": "调度器未运行"}
    last = _parse_ts(last_activity)
    if last is None:
        return {"status": "yellow", "reason": "无活动记录"}
    age_sec = (_now_utc() - last).total_seconds()
    # 避峰顺延：最后活动在 interval*4 内且当前处于北京高峰时段
    if age_sec > interval_sec * 2:
        from valuation_app.offpeak import is_peak_bj
        if is_peak_bj() and age_sec <= interval_sec * 4:
            return {"status": "green", "reason": f"避峰顺延中（{age_sec/60:.0f}min 前活动，等峰时结束）"}
    if age_sec > interval_sec * 4:
        return {"status": "red", "reason": f"最后活动 {age_sec/3600:.1f}h 前（间隔 {interval_sec/60:.0f}min）"}
    if age_sec > interval_sec * 2:
        return {"status": "yellow", "reason": f"最后活动 {age_sec/60:.0f}min 前，可能卡顿"}
    return {"status": "green", "reason": f"活跃（{age_sec/60:.0f}min 前）"}


def _today_str() -> str:
    return _now_utc().strftime("%Y%m%d")


def _is_today(ts: str) -> bool:
    """判断 timestamp 是否为今天（兼容 ISO 带连字符与无连字符格式）。"""
    if not ts:
        return False
    s = str(ts)
    # ISO 格式: 2026-08-15T00:08:36 → 取日期部分去掉连字符
    date_part = s[:10].replace("-", "")
    if len(date_part) != 8 or not date_part.isdigit():
        return False
    return date_part == _today_str()


def build_tianjifeng(rows: list[dict], sched: dict) -> dict:
    """天机峰 A/B 管线聚合。"""
    today_rows = [r for r in rows if r.get("pipeline") == "tianjifeng"
                  and _is_today(r.get("timestamp", ""))]
    all_rows = [r for r in rows if r.get("pipeline") == "tianjifeng"]
    yanbao_today = [r for r in rows if r.get("pipeline") == "tianjifeng_yanbao"
                    and _is_today(r.get("timestamp", ""))]
    yanbao_all = [r for r in rows if r.get("pipeline") == "tianjifeng_yanbao"]

    def _stats(rows_list: list[dict]) -> dict:
        status_c = Counter(r.get("status", "?") for r in rows_list)
        # 拦截原因分类
        reasons = Counter()
        written = 0      # L4+ 真正写入天机卷
        passed_l3 = 0    # L3 流程完成但不写入
        for r in rows_list:
            if r.get("status") == "done":
                try:
                    lv = int(str(r.get("level", "0")))
                except (ValueError, TypeError):
                    lv = 0
                if lv >= 4:
                    written += 1
                else:
                    passed_l3 += 1
            if r.get("status") == "seed_rejected":
                report = str(r.get("seed_report", ""))
                if "弱种子" in report:
                    reasons["种子强度不足"] += 1
                elif "充分定价" in report or "延续" in report or "已定价" in report:
                    reasons["X1延续型"] += 1
                elif "中种子" in report:
                    reasons["中种子(档位外)"] += 1
                else:
                    reasons["其他种子拒绝"] += 1
            elif r.get("status") == "filtered":
                reasons["初筛过滤"] += 1
            elif r.get("status") == "skip":
                reasons["去重/跳过"] += 1
        return {
            "total": len(rows_list),
            "status": dict(status_c),
            "reasons": dict(reasons.most_common(10)),
            "written_l4": written,
            "passed_l3": passed_l3,
        }

    a_today = _stats(today_rows)
    a_all = _stats(all_rows)
    b_today = _stats(yanbao_today)
    b_all = _stats(yanbao_all)

    # 放行率 = L4+ 写入天机卷 / 总量
    rel_today = a_today["written_l4"]
    rel_rate_today = rel_today / a_today["total"] if a_today["total"] else 0
    rel_all = a_all["written_l4"]
    rel_rate_all = rel_all / a_all["total"] if a_all["total"] else 0

    # 最近写入天机卷的（仅 L4+，A/B 合并）
    released = [r for r in (all_rows + yanbao_all) if r.get("status") == "done"
                and int(str(r.get("level", "0") or "0")) >= 4][-5:]
    recent_releases = [{
        "title": str(r.get("title", ""))[:60],
        "level": r.get("level", ""),
        "time": str(r.get("timestamp", ""))[11:19],
    } for r in reversed(released)]

    # 偏差检测
    deviations = []
    if a_today["total"] >= 10 and a_all["total"] >= 50:
        if rel_rate_today < 0.01:
            deviations.append(f"今日放行率 {rel_rate_today:.1%} < 1%，种子阈值可能过严（当前档位：仅强种子）")
        if rel_rate_today > rel_rate_all * 2.5 and rel_rate_today > 0.02:
            deviations.append(f"今日放行率 {rel_rate_today:.1%} 是7日均值 {rel_rate_all:.1%} 的 {rel_rate_today/rel_rate_all:.1f}x，异常放水")
    filter_rate = a_today["reasons"].get("初筛过滤", 0) / a_today["total"] if a_today["total"] else 0
    if filter_rate > 0.7 and a_today["total"] >= 20:
        deviations.append(f"初筛拦截率 {filter_rate:.0%} 过高，检查 FILTER prompt 是否误杀")

    return {
        "pipeline_a": {
            "stats_today": a_today,
            "stats_7d": a_all,
            "release_rate_today": round(rel_rate_today, 4),
            "release_rate_7d": round(rel_rate_all, 4),
            "recent_releases": recent_releases,
        },
        "pipeline_b": {
            "stats_today": b_today,
            "stats_7d": b_all,
            "written_l4_today": b_today["written_l4"],
            "passed_l3_today": b_today["passed_l3"],
        },
        "deviations": deviations,
    }


def build_wangqi(rows: list[dict], sched: dict) -> dict:
    """望气（产业链）聚合。"""
    today_rows = [r for r in rows if r.get("pipeline") == "wangqi"
                  and _is_today(r.get("timestamp", ""))]
    all_rows = [r for r in rows if r.get("pipeline") == "wangqi"]

    done_today = [r for r in today_rows if r.get("status") == "done"]
    no_pick = [r for r in done_today if "无高赔率" in str(r.get("top_pick", ""))]
    done_all = [r for r in all_rows if r.get("status") == "done"]
    no_pick_all = [r for r in done_all if "无高赔率" in str(r.get("top_pick", ""))]

    no_pick_rate = len(no_pick_all) / len(done_all) if done_all else 0
    no_pick_rate_today = len(no_pick) / len(done_today) if done_today else 0

    # 有产出的（top_pick 非空非无高赔率）
    picks = [r for r in done_all if r.get("top_pick") and "无高赔率" not in str(r.get("top_pick"))]
    recent_picks = [{
        "top": str(r.get("top_pick", ""))[:30],
        "time": str(r.get("timestamp", ""))[5:16],
        "elapsed": r.get("elapsed_s", 0),
    } for r in picks[-5:]]

    deviations = []
    if no_pick_rate > 0.85 and len(done_all) >= 10:
        deviations.append(
            f"无高赔率率 {no_pick_rate:.0%}（{len(no_pick_all)}/{len(done_all)}），"
            f"检查候选池召回（Volc节点搜索）或评分阈值6.5是否过严"
        )
    if done_today and no_pick_rate_today > no_pick_rate + 0.1:
        deviations.append(f"今日无高赔率率 {no_pick_rate_today:.0%} 高于7日均值 {no_pick_rate:.0%}")

    return {
        "stats_today": {"total": len(today_rows), "done": len(done_today), "no_pick": len(no_pick),
                         "error": sum(1 for r in today_rows if r.get("status") == "error")},
        "stats_7d": {"total": len(all_rows), "done": len(done_all), "no_pick": len(no_pick_all),
                      "error": sum(1 for r in all_rows if r.get("status") == "error")},
        "no_pick_rate_today": round(no_pick_rate_today, 4),
        "no_pick_rate_7d": round(no_pick_rate, 4),
        "recent_picks": recent_picks,
        "deviations": deviations,
    }


WANYEPU_LOG = Path(__file__).resolve().parent.parent / "wanyepu_scheduler.log"


def build_wanyepu(schedulers: dict) -> dict:
    """万业谱聚合 — 从调度器日志 + 内存状态。"""
    sched = schedulers.get("wanyepu", {})
    today = _today_str()

    # 解析日志统计今日轮询
    polls_a_today = 0
    polls_b_today = 0
    done_a_today = 0
    done_b_today = 0
    no_pending_a = 0
    no_pending_b = 0
    recent_events = []

    try:
        with open(WANYEPU_LOG, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for line in lines:
            if not line.startswith("20"):
                continue
            date_part = line[:10].replace("-", "")
            if date_part != today:
                continue
            if "管线A开始轮询" in line:
                polls_a_today += 1
            elif "管线B开始轮询" in line:
                polls_b_today += 1
            elif "管线A: 无待处理记录" in line:
                no_pending_a += 1
            elif "管线B: 无待处理记录" in line:
                no_pending_b += 1
            elif "管线A完成:" in line:
                m = re.search(r"(\d+) 条", line)
                done_a_today += int(m.group(1)) if m else 0
            elif "管线B完成:" in line:
                m = re.search(r"(\d+) 条", line)
                done_b_today += int(m.group(1)) if m else 0
            elif "异常" in line or "ERROR" in line:
                recent_events.append({"type": "error", "time": line[11:19], "msg": line.strip()[20:120]})
    except OSError:
        pass

    # 待处理计数：天机卷未处理个股 + 产业链输出表未处理
    pending_tianji = 0
    pending_industry = 0
    try:
        from valuation_app.coze_client import CozeClient
        from env_config import COZE_SAT_TOKEN, COZE_WORKSPACE_ID
        coze = CozeClient(token=COZE_SAT_TOKEN, workspace_id=COZE_WORKSPACE_ID)
        records = coze.query_all_records("7479116110479048754")
        pending_tianji = sum(
            1 for r in records
            if str(r.get("is_analyzed", "")).lower() != "true"
            and str(r.get("is_analyzing", "")).lower() != "true"
            and str(r.get("mode", "")) == "个股模式"
            and int(str(r.get("level", "0") or "0")) > 3
        )
    except Exception:
        pass
    try:
        from valuation_app.coze_client import CozeClient
        from env_config import COZE_SAT_TOKEN, COZE_WORKSPACE_ID
        coze = CozeClient(token=COZE_SAT_TOKEN, workspace_id=COZE_WORKSPACE_ID)
        records = coze.query_all_records("7640928034144698374")
        pending_industry = sum(
            1 for r in records
            if str(r.get("is_analyzed", "")).lower() != "true"
            and str(r.get("top_pick_code", "") or "").strip()
        )
    except Exception:
        pass

    completed = (sched or {}).get("completed_jobs", []) if sched else []
    recent_done = [{
        "name": str(j.get("stock_name", j.get("stock_code", ""))),
        "elapsed": j.get("elapsed_s", 0),
        "time": str(j.get("completed_at", ""))[11:19],
    } for j in completed[-5:]]

    return {
        "polls_a_today": polls_a_today,
        "polls_b_today": polls_b_today,
        "done_a_today": done_a_today,
        "done_b_today": done_b_today,
        "no_pending_a": no_pending_a,
        "no_pending_b": no_pending_b,
        "pending_tianji": pending_tianji,
        "pending_industry": pending_industry,
        "recent_done": recent_done,
        "recent_events": recent_events[-3:],
    }


def build_valuation(sched: dict) -> dict:
    """主估值管线聚合（基于报告文件）。"""
    today = _today_str()
    files = list(DATA_DIR.glob("*.json")) if DATA_DIR.exists() else []
    # 按文件修改时间排序（文件名是字典序，不能代表时间）
    files.sort(key=lambda f: f.stat().st_mtime)
    real_files = [f for f in files if "TEST" not in f.stem.upper() and "debug" not in f.stem.lower()]
    today_files = [f for f in real_files if f.stem.split("_")[-1].startswith(today[:8])]
    recent = real_files[-5:] if real_files else []

    recent_reports = []
    for f in reversed(recent):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            a0 = d.get("agent0", {})
            if not isinstance(a0, dict):
                continue
            code = a0.get("stock_code", "") or f.stem[:6]
            name = a0.get("stock_name", "")
            # 名字可能在 event_meta / agent1
            if not name:
                em = d.get("event_meta", {})
                if isinstance(em, dict):
                    name = em.get("stock_name", "")
            if not name:
                a1 = d.get("agent1", {})
                if isinstance(a1, dict):
                    name = a1.get("stock_name", "")
            a3 = d.get("agent3", {})
            summary = a3.get("valuation_summary", {}) if isinstance(a3, dict) else {}
            # 报告时间：文件名 _YYYYMMDD_HHMM
            stem = f.stem
            parts = stem.split("_")
            ts_part = parts[-2] + "_" + parts[-1] if len(parts) >= 3 and parts[-2].isdigit() else (parts[-1] if len(parts) >= 2 and parts[-1].isdigit() else "")
            recent_reports.append({
                "code": code,
                "name": name,
                "upside": summary.get("probability_weighted_upside_pct"),
                "asymmetry": summary.get("asymmetry_ratio", 0),
                "quality": summary.get("quality_flag", ""),
                "time": ts_part,
            })
        except (OSError, json.JSONDecodeError):
            continue

    return {
        "reports_today": len(today_files),
        "total_reports": len(real_files),
        "recent_reports": recent_reports,
        "completed_jobs": (sched or {}).get("completed_jobs", [])[-5:],
    }


def build_dashboard(schedulers: dict) -> dict:
    """聚合所有管线健康 + 偏差 + 调优建议。"""
    rows = _load_audit(days=7)

    tianjifeng = build_tianjifeng(rows, schedulers.get("tianjifeng", {}))
    wangqi = build_wangqi(rows, schedulers.get("wangqi", {}))
    wanyepu = build_wanyepu(schedulers)
    valuation = build_valuation(schedulers.get("main", {}))
    # 健康状态
    health = {
        "tianjifeng_a": _health(
            schedulers.get("tianjifeng", {}).get("running", False),
            schedulers.get("tianjifeng", {}).get("last_poll_at"),
            schedulers.get("tianjifeng", {}).get("interval", 600),
        ),
        "tianjifeng_b": _health(
            schedulers.get("tianjifeng", {}).get("running", False),
            schedulers.get("tianjifeng", {}).get("last_yanbao_at"),
            schedulers.get("tianjifeng", {}).get("yanbao_interval", 1800),
        ),
        "wanyepu_a": _health(
            schedulers.get("wanyepu", {}).get("running", False),
            schedulers.get("wanyepu", {}).get("last_poll_a"),
            schedulers.get("wanyepu", {}).get("interval_a", 1800),
        ),
        "wanyepu_b": _health(
            schedulers.get("wanyepu", {}).get("running", False),
            schedulers.get("wanyepu", {}).get("last_poll_b"),
            schedulers.get("wanyepu", {}).get("interval_b", 2700),
        ),
        "wangqi": _health(
            schedulers.get("wangqi", {}).get("running", False),
            schedulers.get("wangqi", {}).get("last_poll_at"),
            schedulers.get("wangqi", {}).get("interval", 1800),
        ),
        "main": _health(
            schedulers.get("main", {}).get("running", False),
            schedulers.get("main", {}).get("last_poll_at"),
            schedulers.get("main", {}).get("interval", 3600),
        ),
    }

    # 汇总所有偏差 + 调优建议
    all_deviations = []
    all_deviations.extend([{"pipe": "天机峰", "msg": m} for m in tianjifeng["deviations"]])
    all_deviations.extend([{"pipe": "望气", "msg": m} for m in wangqi["deviations"]])

    suggestions = []
    for hk, hv in health.items():
        if hv["status"] != "green":
            suggestions.append(f"【{hk}】{hv['reason']} — 检查对应调度器是否卡死或需要重启")
    for d in all_deviations:
        suggestions.append(f"【{d['pipe']}】{d['msg']}")

    return {
        "generated_at": _now_utc().isoformat(),
        "health": health,
        "tianjifeng": tianjifeng,
        "wangqi": wangqi,
        "wanyepu": wanyepu,
        "valuation": valuation,
        "deviations": all_deviations,
        "suggestions": suggestions,
    }


# ══════════════════════════════════════════════════════
# 数据表直查 — 支持筛选问题/锁死/过线/未过线记录
# ══════════════════════════════════════════════════════

TABLE_DEFS = {
    "tianjijuan": {
        "name": "天机卷",
        "db_id": "7479116110479048754",
        "fields": ["level", "mode", "is_analyzed", "is_analyzing", "error_log", "stock_name", "stock_code", "news_content", "bstudio_create_time"],
    },
    "news_pool": {
        "name": "天机峰快讯池",
        "db_id": "7668348021729476646",
        "fields": ["title", "source", "is_processed", "pipeline_level", "pipeline_status", "fetched_at", "bstudio_create_time"],
    },
    "yanbao": {
        "name": "研报表（棱镜内参）",
        "db_id": "7631166750289051675",
        "fields": ["is_analyzed", "news_content", "bstudio_create_time"],
    },
    "industry_output": {
        "name": "产业链输出表",
        "db_id": "7640928034144698374",
        "fields": ["is_analyzed", "top_pick_name", "top_pick_code", "top_pick_score", "status", "industry_chain", "event_summary", "bstudio_create_time"],
    },
    "wanyepu": {
        "name": "万业谱表",
        "db_id": "7639784337973477386",
        "fields": ["is_complete", "stock_name", "stock_code", "event_source", "bstudio_create_time", "pre_screen_detail"],
    },
}


def _categorize(record: dict, table_key: str) -> str:
    """把记录归入状态桶：锁死/问题/过线/未过线/已处理/待处理"""
    if table_key == "tianjijuan":
        level = int(str(record.get("level", "0") or "0"))
        analyzed = str(record.get("is_analyzed", "")).lower() == "true"
        analyzing = str(record.get("is_analyzing", "")).lower() == "true"
        err = str(record.get("error_log", "") or "").strip()
        if analyzing and not analyzed:
            return "locked"
        if err and not analyzed:
            return "problem"
        if analyzed:
            return "done"
        if level >= 4:
            return "passed"
        return "not_passed"
    if table_key == "news_pool":
        processed = str(record.get("is_processed", "")).lower() == "true"
        status = str(record.get("pipeline_status", "") or "")
        if not processed:
            return "pending"
        if "error" in status or "fail" in status:
            return "problem"
        return "done"
    if table_key == "yanbao":
        analyzed = str(record.get("is_analyzed", "")).lower() == "true"
        return "done" if analyzed else "pending"
    if table_key == "industry_output":
        analyzed = str(record.get("is_analyzed", "")).lower() == "true"
        top = str(record.get("top_pick_name", "") or "")
        status = str(record.get("status", "") or "")
        if "error" in status:
            return "problem"
        if not analyzed:
            return "pending"
        if top and "无高赔率" not in top:
            return "passed"
        return "not_passed"
    if table_key == "wanyepu":
        complete = str(record.get("is_complete", "")).lower() == "true"
        # 语料缺失拦截的记录：complete=true 但 pre_screen_detail 含 corpus_missing 标记，
        # 不能算"已处理"，单列一类让用户看到它没进估值引擎
        detail = str(record.get("pre_screen_detail", "") or "")
        if "corpus_missing" in detail:
            return "corpus_missing"
        return "done" if complete else "pending"
    return "pending"


CATEGORY_LABELS = {
    "locked": ("锁死", "is_analyzing=true 卡住的记录"),
    "problem": ("问题", "error_log 非空 / 状态异常"),
    "passed": ("过线", "L4/L5 放行 / 有产出"),
    "not_passed": ("未过线", "L3 以下 / 无高赔率"),
    "corpus_missing": ("语料缺失", "预研语料不全，未进估值引擎"),
    "pending": ("待处理", "等待下游消费"),
    "done": ("已处理", "正常完成"),
}


def build_tables(coze_client, table_key: str, category: str = "", search: str = "", limit: int = 100) -> dict:
    """直查 Coze 表并按状态桶归类。"""
    if table_key not in TABLE_DEFS:
        return {"error": f"未知表 {table_key}，可选: {list(TABLE_DEFS.keys())}"}

    td = TABLE_DEFS[table_key]
    try:
        records = coze_client.query_all_records(td["db_id"])
    except Exception as e:
        return {"error": f"查询 {td['name']} 失败: {str(e)[:200]}"}

    categorized = defaultdict(list)
    for r in records:
        cat = _categorize(r, table_key)
        categorized[cat].append(r)

    # 过滤
    if category:
        rows = categorized.get(category, [])
    else:
        rows = records

    if search:
        search_low = search.lower()
        rows = [r for r in rows if search_low in json.dumps(r, ensure_ascii=False).lower()]

    # 倒序时间
    rows.sort(key=lambda r: str(r.get("bstudio_create_time", "")), reverse=True)
    total = len(rows)
    rows = rows[:limit]

    summary = {cat: len(v) for cat, v in categorized.items()}
    return {
        "table": table_key,
        "table_name": td["name"],
        "total": len(records),
        "summary": summary,
        "summary_labels": {k: CATEGORY_LABELS.get(k, (k, ""))[0] for k in summary},
        "filtered_total": total,
        "shown": len(rows),
        "records": [
            {k: r.get(k, "") for k in td["fields"] if r.get(k) not in (None, "")}
            for r in rows
        ],
    }
