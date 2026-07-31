"""天机峰管线 — 双源快讯汇聚 + 筛选打标

架构:
  A 管线: 抓取双源快讯 → 写入快讯池中间表 → 四步 LLM → 天机卷
  B 管线: 研报表 step_one 为空的 → 种子探测 → A股验证 → 火山搜索 → 守门员 → 天机卷

CLI:
  python -m src.tianjifeng.pipeline                  # A 管线完整一轮
  python -m src.tianjifeng.pipeline --yanbao         # B 管线研报处理
  python -m src.tianjifeng.pipeline --dry-run        # 不写库，仅打印
  python -m src.tianjifeng.pipeline --title "标题"    # 单条手动测试
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from wanyepu_v2.field_runner import call_deepseek, volc_search
from valuation_app.coze_client import CozeClient

from .config import (
    COZE_SAT_TOKEN,
    DB_TIANJIJUAN,
    DEEPSEEK_MODEL_PRO,
    DEFAULT_FULL_WRITE_LEVEL,
    DEFAULT_MAX_NEWS_PER_CYCLE,
)
from .coze_io import NewsPoolCoze, TianjifengCoze, YanbaoCoze
from .prompts import (
    FILTER_SYSTEM_PROMPT,
    INDUSTRY_GATEKEEPER_SYSTEM_PROMPT,
    SEED_DETECTOR_SYSTEM_PROMPT,
    STOCK_GATEKEEPER_SYSTEM_PROMPT,
)
from .ths_fetcher import fetch_all


def _write_audit_log(log: dict) -> None:
    """写入审计日志到 reports/audit_logs/audit_YYYYMMDD.jsonl"""
    try:
        log_dir = Path(__file__).resolve().parent.parent.parent / "reports" / "audit_logs"
        os.makedirs(log_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        filepath = log_dir / f"audit_{date_str}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(log, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _parse_json_from_llm(text: str) -> dict | None:
    """从 LLM 输出中解析 JSON 对象"""
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


# ══════════════════════════════════════════════════════
# Phase 1: 抓取入池
# ══════════════════════════════════════════════════════

def fetch_and_store(coze_client: CozeClient) -> int:
    """抓取双源快讯，写入快讯池中间表。返回新插入条数。"""
    pool = NewsPoolCoze(coze_client)
    news_list = fetch_all()
    if not news_list:
        print("[pipeline] 未拉到快讯", flush=True)
        return 0
    inserted = pool.insert_news(news_list)
    print(f"[pipeline] 快讯池新增 {inserted} 条（共抓取 {len(news_list)} 条）", flush=True)
    return inserted


# ══════════════════════════════════════════════════════
# 四步 LLM 处理
# ══════════════════════════════════════════════════════

def step1_filter(title: str) -> dict:
    """LLM #1: 初筛 — 0/1 二分类"""
    raw = call_deepseek(system=FILTER_SYSTEM_PROMPT, user=title, max_tokens=500, temperature=0, thinking=True)
    result = _parse_json_from_llm(raw)
    if result is None:
        return {"level": 1, "output": "JSON解析失败默认放行"}
    return result


def step2_seed_detect(title: str, summary: str, prompt: str = "") -> dict:
    """LLM #2: 种子探测（pro 模型）。prompt 可覆盖（研报用专用 prompt）"""
    system = prompt or SEED_DETECTOR_SYSTEM_PROMPT
    user_msg = f"资讯：{summary}\n标题：{title}" if summary else f"资讯：{title}"
    raw = call_deepseek(system=system, user=user_msg, max_tokens=5000, temperature=0, thinking=True, model=DEEPSEEK_MODEL_PRO)
    result = _parse_json_from_llm(raw)
    if result is None:
        return {"pass": False, "company": "", "query": "", "report": "JSON解析失败"}
    return result


def step3_volc_search(query: str, summary: str) -> str:
    """火山搜索背景补充"""
    if not query:
        return ""
    return volc_search(query)


def _verify_a_stock(company_name: str) -> bool:
    """用 tushare 验证公司名是否为 A 股上市公司。
    返回 True = A 股（走个股守门员），False = 非 A 股（跳过）。
    查询失败默认放行（保守策略，避免误杀）。
    """
    try:
        from tushare_fetcher import TushareFetcher
        tf = TushareFetcher()
        if not tf.available:
            return True
        df = tf.pro.stock_basic(name=company_name, fields='ts_code,name,market')
        return df is not None and len(df) > 0
    except Exception:
        return True


def step4_gatekeeper(title: str, summary: str, knowledge: str, company: str, existing_titles: list[str] | None = None) -> dict:
    """LLM #3/#4: 守门员（pro 模型）"""
    is_stock = bool(company and company.strip())
    prompt = STOCK_GATEKEEPER_SYSTEM_PROMPT if is_stock else INDUSTRY_GATEKEEPER_SYSTEM_PROMPT
    user_msg = f"输入的资讯：{summary}\n标题：{title}\n更多实时的背景资料：{knowledge}"
    if existing_titles:
        recent = "\n".join(f"- {t.split(chr(10), 1)[0][:80]}" for t in existing_titles[:30])
        user_msg += f"\n\n天机卷近期已记录事件（如当前资讯与以下任一条为同一事件的不同表述，视为已充分定价，等级判定降一级）：\n{recent}"
    raw = call_deepseek(system=prompt, user=user_msg, max_tokens=4000, temperature=0, thinking=True, model=DEEPSEEK_MODEL_PRO)
    result = _parse_json_from_llm(raw)
    if result is None:
        return {"mode": "个股模式" if is_stock else "产业模式", "level": 0, "report": "JSON解析失败"}
    return result


# ══════════════════════════════════════════════════════
# 单条处理（A/B 共用核心逻辑）
# ══════════════════════════════════════════════════════

def process_news(
    news: dict,
    tianjifeng_io: TianjifengCoze | None = None,
    dry_run: bool = False,
    full_write_level: int = DEFAULT_FULL_WRITE_LEVEL,
    progress_cb=None,
    skip_filter: bool = False,
    seed_prompt: str = "",
) -> dict:
    """处理单条快讯/研报，返回处理结果。"""
    title = news.get("title", "").strip()
    summary = news.get("summary", "").strip()
    if not title:
        return {"status": "skip", "reason": "empty_title"}

    result = {"title": title, "status": "pending", "steps": {}}

    def _emit(step: str, data: dict):
        result["steps"][step] = data
        if progress_cb:
            progress_cb(step, data)

    # ── 1. 天机卷去重 ────────────────────────
    if tianjifeng_io and tianjifeng_io.is_duplicate(title):
        result["status"] = "skip"
        result["reason"] = "duplicate"
        return result

    # ── 2. 初筛（可跳过）──────────────────────
    if not skip_filter:
        t0 = time.time()
        filter_result = step1_filter(title)
        _emit("filter", {"level": filter_result.get("level"), "output": filter_result.get("output"), "elapsed": round(time.time() - t0, 1)})
        if filter_result.get("level") == 0:
            result["status"] = "filtered"
            result["level"] = "0"
            return result

    # ── 3. 种子探测 ──────────────────────────
    t0 = time.time()
    seed_result = step2_seed_detect(title, summary, prompt=seed_prompt)
    _emit("seed", {"pass": seed_result.get("pass"), "company": seed_result.get("company"), "elapsed": round(time.time() - t0, 1)})

    if not seed_result.get("pass"):
        result["status"] = "seed_rejected"
        result["level"] = "0"
        result["seed_report"] = seed_result.get("report", "")
        return result

    # ── 3.5 A股验证 ──────────────────────────
    company = seed_result.get("company", "").strip()
    if company:
        t0 = time.time()
        is_a_stock = _verify_a_stock(company)
        _emit("stock_verify", {"company": company, "is_a_stock": is_a_stock, "elapsed": round(time.time() - t0, 1)})
        if not is_a_stock:
            result["status"] = "not_a_stock"
            result["level"] = "0"
            result["company"] = company
            return result

    # ── 4. 火山搜索 ──────────────────────────
    query = seed_result.get("query", "").strip()
    t0 = time.time()
    knowledge = step3_volc_search(query, summary)
    _emit("volc", {"query": query, "knowledge_len": len(knowledge), "elapsed": round(time.time() - t0, 1)})

    # ── 5. 守门员 ─────────────────────────────
    t0 = time.time()
    gate_result = step4_gatekeeper(title, summary, knowledge, company, existing_titles=tianjifeng_io._existing_titles if tianjifeng_io else None)
    _emit("gatekeeper", {"mode": gate_result.get("mode"), "level": gate_result.get("level"), "elapsed": round(time.time() - t0, 1)})

    mode = gate_result.get("mode", "个股模式" if company else "产业模式")
    level = int(gate_result.get("level", 0))
    report = gate_result.get("report", "")

    result["status"] = "done"
    result["level"] = str(level)
    result["mode"] = mode
    result["company"] = company
    result["report"] = report

    # ── 6. 写入天机卷（仅 L4/L5）──────────────
    if not dry_run and tianjifeng_io and level >= full_write_level:
        full_content = f"{title}\n{summary}" if summary else title
        tianjifeng_io.insert_record(
            news_content=full_content, level=str(level), step_one=report,
            mode=mode, stock_name=company, knowledge=knowledge,
            date=news.get("publish_time", ""),
        )

    return result


# ══════════════════════════════════════════════════════
# A 管线: 从快讯池消费
# ══════════════════════════════════════════════════════

def run_pipeline(
    max_news: int = DEFAULT_MAX_NEWS_PER_CYCLE,
    dry_run: bool = False,
    full_write_level: int = DEFAULT_FULL_WRITE_LEVEL,
    coze_client: CozeClient | None = None,
    progress_cb=None,
) -> dict:
    """A 管线：从快讯池读取未处理快讯，过管线写天机卷。"""

    tianjifeng_io = None
    pool = None
    if not dry_run and coze_client:
        tianjifeng_io = TianjifengCoze(coze_client)
        tianjifeng_io.load_existing_titles()
        pool = NewsPoolCoze(coze_client)

    if pool:
        news_list = pool.query_unprocessed(limit=max_news)
    else:
        news_list = fetch_all()[:max_news]

    if not news_list:
        return {"status": "no_news", "total": 0}

    stats = {
        "total": len(news_list),
        "filtered": 0, "seed_rejected": 0, "done": 0, "skip": 0, "error": 0,
        "results": [],
    }

    for news in news_list:
        try:
            r = process_news(news, tianjifeng_io=tianjifeng_io, dry_run=dry_run, full_write_level=full_write_level, progress_cb=progress_cb)
            stats["results"].append(r)
            status = r.get("status", "error")
            if status in stats:
                stats[status] += 1

            if pool and news.get("id"):
                try:
                    pool.mark_processed(news["id"], level=r.get("level", ""), status=status)
                except Exception:
                    pass

            _write_audit_log({
                "pipeline": "tianjifeng",
                "title": r.get("title", ""),
                "source": news.get("source", ""),
                "status": status,
                "level": r.get("level", ""),
                "mode": r.get("mode", ""),
                "company": r.get("company", ""),
                "timestamp": datetime.now().isoformat(),
            })

        except Exception as e:
            stats["error"] += 1
            stats["results"].append({"title": news.get("title", ""), "status": "error", "error": str(e)})
            if pool and news.get("id"):
                try:
                    pool.mark_processed(news["id"], status="error")
                except Exception:
                    pass
            _write_audit_log({
                "pipeline": "tianjifeng", "title": news.get("title", ""), "status": "error", "error": str(e), "timestamp": datetime.now().isoformat(),
            })

    stats["status"] = "ok"
    return stats


# ══════════════════════════════════════════════════════
# B 管线: 研报（棱镜内参）处理
# ══════════════════════════════════════════════════════

def process_yanbao(
    record: dict,
    tianjifeng_io: TianjifengCoze | None = None,
    dry_run: bool = False,
    full_write_level: int = DEFAULT_FULL_WRITE_LEVEL,
    progress_cb=None,
) -> dict:
    """处理单条研报 — 解析 card 后复用 process_news（跳过初筛，用研报版种子探测）。"""
    news_content = str(record.get("news_content", ""))
    title, summary = YanbaoCoze.parse_news_content(news_content)
    if not title:
        return {"status": "skip", "reason": "empty_title"}

    # 研报用更低的天机卷去重阈值（同一事件不同券商标题差异大）
    if tianjifeng_io and tianjifeng_io.is_duplicate(title, threshold=TianjifengCoze.DEDUP_SIMILARITY_YANBAO):
        return {"status": "skip", "reason": "duplicate_yanbao", "title": title}

    news = {
        "title": title,
        "summary": news_content,
        "publish_time": str(record.get("bstudio_create_time", ""))[:10],
    }
    return process_news(
        news, tianjifeng_io=tianjifeng_io, dry_run=dry_run, full_write_level=full_write_level,
        progress_cb=progress_cb, skip_filter=True,
    )


def run_yanbao_pipeline(
    max_records: int = 10,
    dry_run: bool = False,
    full_write_level: int = DEFAULT_FULL_WRITE_LEVEL,
    coze_client: CozeClient | None = None,
    progress_cb=None,
    parallel: int = 5,
) -> dict:
    """B 管线：从研报表读取未处理研报，并行过管线写天机卷。"""

    tianjifeng_io = None
    yanbao = None
    if coze_client:
        tianjifeng_io = TianjifengCoze(coze_client)
        tianjifeng_io.load_existing_titles()
        yanbao = YanbaoCoze(coze_client)

    if yanbao:
        records = yanbao.query_unprocessed(limit=max_records)
    else:
        return {"status": "no_client", "total": 0}

    if not records:
        return {"status": "no_news", "total": 0}

    # 批次内去重：同一事件的多个券商版本只保留第一条
    # 阈值 0.25：同事件研报标题相似度通常 0.25-0.62，不相关标题 <0.22
    from .coze_io import _title_similarity
    deduped = []
    seen_titles = []
    skipped_dup = 0
    for r in records:
        title, _ = YanbaoCoze.parse_news_content(str(r.get("news_content", "")))
        if not title:
            deduped.append(r)
            continue
        is_dup = False
        for st in seen_titles:
            if _title_similarity(title, st) >= 0.25:
                is_dup = True
                break
        if is_dup:
            skipped_dup += 1
            if yanbao and r.get("id"):
                try:
                    yanbao.mark_analyzed(r["id"])
                except Exception:
                    pass
        else:
            seen_titles.append(title)
            deduped.append(r)

    if skipped_dup:
        print(f"[yanbao] 批次内去重: 跳过 {skipped_dup} 条同事件研报", flush=True)

    if not deduped:
        return {"status": "no_news", "total": 0, "batch_dedup": skipped_dup}

    records = deduped

    stats = {
        "total": len(records),
        "filtered": 0, "seed_rejected": 0, "done": 0, "skip": 0,
        "not_a_stock": 0, "error": 0,
        "results": [],
    }
    stats_lock = Lock()

    def _handle_one(record: dict) -> None:
        try:
            r = process_yanbao(record, tianjifeng_io=tianjifeng_io, dry_run=dry_run, full_write_level=full_write_level, progress_cb=progress_cb)
        except Exception as e:
            r = {"title": str(record.get("news_content", ""))[:80], "status": "error", "error": str(e)}

        status = r.get("status", "error")

        if yanbao and record.get("id"):
            try:
                yanbao.mark_analyzed(record["id"])
            except Exception:
                pass

        _write_audit_log({
            "pipeline": "tianjifeng_yanbao",
            "title": r.get("title", ""),
            "status": status,
            "level": r.get("level", ""),
            "mode": r.get("mode", ""),
            "company": r.get("company", ""),
            "timestamp": datetime.now().isoformat(),
        })

        with stats_lock:
            stats["results"].append(r)
            if status in stats:
                stats[status] += 1
            else:
                stats["error"] += 1

    with ThreadPoolExecutor(max_workers=min(parallel, len(records))) as ex:
        futures = {ex.submit(_handle_one, r): r for r in records}
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    stats["status"] = "ok"
    return stats


# ══════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="天机峰管线 — 双源快讯筛选打标")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_NEWS_PER_CYCLE, help="单轮最大处理条数")
    parser.add_argument("--dry-run", action="store_true", help="不写库，仅打印")
    parser.add_argument("--yanbao", action="store_true", help="B 管线：处理研报表")
    parser.add_argument("--title", type=str, default="", help="单条手动测试")
    parser.add_argument("--full-write-level", type=int, default=DEFAULT_FULL_WRITE_LEVEL, help="完整写入的最低等级")
    args = parser.parse_args()

    coze_client = None
    if not args.dry_run:
        coze_client = CozeClient(token=COZE_SAT_TOKEN, workspace_id="7470107954512379931")

    if args.yanbao:
        stats = run_yanbao_pipeline(max_records=args.max, dry_run=args.dry_run, full_write_level=args.full_write_level, coze_client=coze_client)
        print(json.dumps({k: v for k, v in stats.items() if k != "results"}, ensure_ascii=False, indent=2))
        for r in stats.get("results", []):
            print(f"  [{r.get('status')}] {r.get('title', '')} level={r.get('level', '-')}")
    elif args.title:
        news = {"title": args.title, "summary": "", "publish_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        tj_io = TianjifengCoze(coze_client) if coze_client else None
        r = process_news(news, tianjifeng_io=tj_io, dry_run=args.dry_run, full_write_level=args.full_write_level)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        if coze_client:
            fetch_and_store(coze_client)
        stats = run_pipeline(max_news=args.max, dry_run=args.dry_run, full_write_level=args.full_write_level, coze_client=coze_client)
        print(json.dumps({k: v for k, v in stats.items() if k != "results"}, ensure_ascii=False, indent=2))
        for r in stats.get("results", []):
            print(f"  [{r.get('status')}] {r.get('title', '')} level={r.get('level', '-')}")


if __name__ == "__main__":
    main()
