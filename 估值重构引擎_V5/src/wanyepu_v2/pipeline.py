"""万业谱预研管线 V2 — 两条独立管线

管线 A (天机卷): 个股事件 → N0-N7 → 万业谱
管线 B (产业链): 产业分析 → 关联天机卷 → N0-N7 → 万业谱

两条管线独立运行，错开轮询时间。
"""

import re
import os
import json
import time
import requests
from datetime import datetime

from .config import COZE_SAT_TOKEN, COZE_BASE, DB_TIANJIJUAN
from .n0_validator import validate_stock
from .field_runner import run_field, FIELD_CONFIGS, FIELD_CN
from .n5_event_deduction import run_event_deduction
from .n4_future import run_future
from .n7_writer import write_wanyepu, mark_tianji_processed, unlock_tianji

DB_INDUSTRY = "7640928034144698374"


# ══════════════════════════════════════════════════════
# 审计日志
# ══════════════════════════════════════════════════════

AUDIT_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports", "audit_logs")


def _write_audit_log(log: dict) -> None:
    try:
        os.makedirs(AUDIT_LOG_DIR, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        filepath = os.path.join(AUDIT_LOG_DIR, f"audit_{date_str}.jsonl")
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(log, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ══════════════════════════════════════════════════════
# 管线核心: 处理单条记录 (两条管线共用)
# ══════════════════════════════════════════════════════

def _process_stock(
    stock_name: str,
    stock_code: str,
    news_content: str,
    knowledge: str = "",
    step_one: str = "",
    uuid: str = "",
    level: str = "",
    mode: str = "",
    bstudio_time: str = "",
    record_id: str = "",
    industry_context: str = "",
    verbose: bool = True,
) -> dict | str | None:
    """处理单只股票的完整管线 (N0→N0.3→N0.5→N1→N2→N5→N3→N4→N7)。

    Returns:
        dict: 处理成功
        None: 处理失败（调用方需判断原因）
        ("skip", error_msg): N0 验证失败或非A股，调用方应标记已处理而非重试
    """

    news_clean = re.sub(r"<[^>]+>", "", news_content)
    news_clean = re.sub(r"&[^;]+;", " ", news_clean)
    news_clean = re.sub(r"\s+", " ", news_clean).strip()

    # N0: 股票代码验证
    n0 = validate_stock(stock_name=stock_name, stock_code=stock_code)
    if not n0["is_valid"]:
        print(f"[N0] [FAIL] 验证失败: {n0['error']}")
        return ("skip", f"N0验证失败: {n0['error']}")

    verified_name = n0["verified_name"]
    verified_code = n0["verified_code"]

    if verbose:
        print(f"[N0] [OK] {verified_name}({verified_code}) [{n0['stock_market']}]")

    # N0.3: A股主板复核
    if not verified_code.startswith(("60", "00", "68", "30")):
        if verbose:
            print(f"[N0.3] [SKIP] 非A股主板标的({verified_code})")
        return ("skip", f"非A股主板标的({verified_code})，跳过分析")

    t_start = time.time()

    # N0.5: 公司前置认知
    from .n05_company_profile import build_company_profile

    company_profile = build_company_profile(
        stock_name=verified_name,
        stock_code=verified_code,
        verbose=verbose,
    )

    # 如果有产业链上下文，追加到 company_profile
    if industry_context:
        company_profile += f"\n\n### 产业链分析上下文\n{industry_context}"

    # N1-N2: 串行字段执行
    field_reports = {}

    for field_name in ["investment_theme", "industry_expert_research"]:
        report = run_field(
            field_name=field_name,
            prior_reports=field_reports,
            stock_name=verified_name,
            stock_code=verified_code,
            news_content=news_clean,
            knowledge=knowledge,
            step_one=step_one,
            company_profile=company_profile,
            verbose=verbose,
        )
        field_reports[field_name] = report

    # N5: 事件推演 (3层因果递进)
    n5_report = run_event_deduction(
        stock_name=verified_name,
        stock_code=verified_code,
        news_content=news_clean,
        n1_report=field_reports.get("investment_theme", ""),
        n2_report=field_reports.get("industry_expert_research", ""),
        n3_report="",
        knowledge=knowledge,
        step_one=step_one,
        company_profile=company_profile,
        verbose=verbose,
    )
    field_reports["event_deduction"] = n5_report

    # N3: 逆向推演
    report = run_field(
        field_name="adversarial_thinking",
        prior_reports=field_reports,
        stock_name=verified_name,
        stock_code=verified_code,
        news_content=news_clean,
        knowledge=knowledge,
        step_one=step_one,
        company_profile=company_profile,
        verbose=verbose,
    )
    field_reports["adversarial_thinking"] = report

    # N4: 催化日历
    report = run_future(
        stock_name=verified_name,
        stock_code=verified_code,
        news_content=news_clean,
        n1_report=field_reports.get("investment_theme", ""),
        n2_report=field_reports.get("industry_expert_research", ""),
        n3_report=field_reports.get("adversarial_thinking", ""),
        n5_report=field_reports.get("event_deduction", ""),
        company_profile=company_profile,
        verbose=verbose,
    )
    field_reports["future"] = report

    # N7: 写入万业谱
    event_date = bstudio_time[:10] if bstudio_time else ""
    event_source = "天机" if mode == "个股模式" else mode

    write_result = write_wanyepu(
        stock_name=verified_name,
        stock_code=verified_code,
        event_date=event_date,
        event_source=event_source,
        raw_event_text=news_clean,
        response_level=level,
        preliminary_reasoning=step_one,
        industry_expert_research=field_reports.get("industry_expert_research", ""),
        adversarial_thinking=field_reports.get("adversarial_thinking", ""),
        investment_theme=field_reports.get("investment_theme", ""),
        future=field_reports.get("future", ""),
        event_deduction=field_reports.get("event_deduction", ""),
        knowledge_supplement=knowledge,
        uuid=uuid,
        source_record_id=record_id,
        verbose=verbose,
    )

    total_elapsed = time.time() - t_start

    # 审计日志
    _write_audit_log({
        "record_id": record_id,
        "stock_name": verified_name,
        "stock_code": verified_code,
        "elapsed_s": round(total_elapsed, 1),
        "write_status": write_result.get("status", "unknown"),
        "field_lengths": {k: len(v) for k, v in field_reports.items()},
        "timestamp": datetime.now().isoformat(),
    })

    if verbose:
        print(f"\n[Pipeline] 完成: {total_elapsed:.0f}s")

    return {
        "record_id": record_id,
        "stock_name": verified_name,
        "stock_code": verified_code,
        "elapsed": total_elapsed,
        "write_status": write_result.get("status", "unknown"),
        "fields": field_reports,
    }


# ══════════════════════════════════════════════════════
# 管线 A: 天机卷轮询
# ══════════════════════════════════════════════════════

def fetch_tianji_records(limit: int = 5) -> list[dict]:
    """从天机卷拉取待处理记录。"""
    url = f"{COZE_BASE}/{DB_TIANJIJUAN}/records/query"
    payload = {
        "page_size": limit,
        "order_by": [{"direction": "desc", "field_name": "bstudio_create_time"}],
        "filter": {
            "logic": "and",
            "conditions": [
                {"left": "mode", "operation": "equal", "right": "个股模式"},
                {"left": "level", "operation": "greater_than", "right": "3"},
                {"left": "is_analyzed", "operation": "not_equal", "right": "true"},
                {"left": "is_analyzing", "operation": "not_equal", "right": "true"},
            ],
        },
    }
    r = requests.post(url, headers={
        "Authorization": f"Bearer {COZE_SAT_TOKEN}",
        "Content-Type": "application/json",
    }, json=payload, timeout=30)
    return r.json().get("data", {}).get("items", [])


def _update_coze_record(db_id: str, record_id: str, fields: dict) -> bool:
    """更新 Coze DB 记录。Coze 要求 update_fields + filter 格式，不是 REST 风格。

    sync_coze.py 验证过的正确格式：
      PUT /records  {"update_fields": [{"field_name":"...","value":"..."}],
                     "filter": {"logic":"and","conditions":[{"left":"id","operation":"equal","right":"..."}]}}
    所有 value 必须为字符串。
    """
    try:
        update_fields = [
            {"field_name": k, "value": str(v)}
            for k, v in fields.items()
        ]
        r = requests.put(
            f"{COZE_BASE}/{db_id}/records",
            headers={
                "Authorization": f"Bearer {COZE_SAT_TOKEN}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "update_fields": update_fields,
                "filter": {
                    "logic": "and",
                    "conditions": [
                        {"left": "id", "operation": "equal", "right": record_id},
                    ],
                },
            },
            timeout=30,
        )
        result = r.json() if r.text else {}
        return result.get("code") == 0
    except Exception:
        return False


def lock_tianji(record_id: str) -> bool:
    return _update_coze_record(DB_TIANJIJUAN, record_id, {"is_analyzing": "true"})


def run_tianji_pipeline(limit: int = 5, verbose: bool = True) -> list[dict]:
    """管线 A: 天机卷轮询 → 处理 → 写入万业谱。"""
    records = fetch_tianji_records(limit)
    if not records:
        print("[管线A-天机卷] 无待处理记录")
        return []

    print(f"[管线A-天机卷] 获取 {len(records)} 条待处理记录")

    results = []
    for i, record in enumerate(records):
        record_id = record.get("id", "")
        print(f"\n[管线A] [{i+1}/{len(records)}] {record.get('stock_name', '?')}({record.get('stock_code', '?')})")

        if not lock_tianji(record_id):
            print(f"[管线A] 加锁失败，跳过")
            continue

        try:
            result = _process_stock(
                stock_name=record.get("stock_name", ""),
                stock_code=record.get("stock_code", ""),
                news_content=record.get("news_content", ""),
                knowledge=record.get("knowledge", ""),
                step_one=record.get("step_one", ""),
                uuid=record.get("uuid", ""),
                level=record.get("level", ""),
                mode=record.get("mode", ""),
                bstudio_time=record.get("bstudio_create_time", ""),
                record_id=record_id,
                verbose=verbose,
            )
            if isinstance(result, tuple) and result[0] == "skip":
                # N0 验证失败 / 非A股 → 标记已处理 + 写入 error_log
                _update_coze_record(DB_TIANJIJUAN, record_id, {
                    "is_analyzed": "true",
                    "is_analyzing": "false",
                    "analysis_time": datetime.now().isoformat(),
                    "error_log": result[1],
                })
            elif result:
                mark_tianji_processed(record_id, verbose=verbose)
                results.append(result)
            else:
                unlock_tianji(record_id)
        except Exception as e:
            print(f"[管线A] 处理异常: {e}")
            unlock_tianji(record_id)
            _write_audit_log({
                "record_id": record_id,
                "pipeline": "tianji",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })

    return results


# ══════════════════════════════════════════════════════
# 管线 B: 产业链轮询
# ══════════════════════════════════════════════════════

def fetch_industry_records(limit: int = 5) -> list[dict]:
    """从产业链表格拉取待处理记录 (is_analyzed=false 且 top_pick_code 不为空)。"""
    url = f"{COZE_BASE}/{DB_INDUSTRY}/records/query"
    payload = {
        "page_size": limit,
        "order_by": [{"direction": "desc", "field_name": "bstudio_create_time"}],
        "filter": {
            "logic": "and",
            "conditions": [
                {"left": "is_analyzed", "operation": "equal", "right": "false"},
                {"left": "top_pick_code", "operation": "not_equal", "right": "null"},
            ],
        },
    }
    r = requests.post(url, headers={
        "Authorization": f"Bearer {COZE_SAT_TOKEN}",
        "Content-Type": "application/json",
    }, json=payload, timeout=30)
    return r.json().get("data", {}).get("items", [])


def fetch_tianji_by_source_id(source_record_id: str) -> dict | None:
    """通过 source_record_id 拉取天机卷关联记录。"""
    url = f"{COZE_BASE}/{DB_TIANJIJUAN}/records/query"
    payload = {
        "page_size": 1,
        "filter": {
            "logic": "and",
            "conditions": [
                {"left": "id", "operation": "equal", "right": source_record_id},
            ],
        },
    }
    r = requests.post(url, headers={
        "Authorization": f"Bearer {COZE_SAT_TOKEN}",
        "Content-Type": "application/json",
    }, json=payload, timeout=30)
    items = r.json().get("data", {}).get("items", [])
    return items[0] if items else None


def lock_industry(record_id: str) -> bool:
    return _update_coze_record(DB_INDUSTRY, record_id, {"is_analyzed": "true"})


def run_industry_pipeline(limit: int = 5, verbose: bool = True) -> list[dict]:
    """管线 B: 产业链轮询 → 关联天机卷 → 处理 → 写入万业谱。"""
    records = fetch_industry_records(limit)
    if not records:
        print("[管线B-产业链] 无待处理记录")
        return []

    print(f"[管线B-产业链] 获取 {len(records)} 条待处理记录")

    results = []
    for i, record in enumerate(records):
        record_id = record.get("id", "")
        top_pick_code = record.get("top_pick_code", "")
        top_pick_name = record.get("top_pick_name", "")
        source_record_id = record.get("source_record_id", "")

        print(f"\n[管线B] [{i+1}/{len(records)}] {top_pick_name}({top_pick_code})")

        # 拉取关联天机卷记录
        tianji = fetch_tianji_by_source_id(source_record_id) if source_record_id else None
        knowledge = tianji.get("knowledge", "") if tianji else ""
        step_one = tianji.get("step_one", "") if tianji else ""

        # 构建产业链上下文
        industry_parts = []
        chain = record.get("chain_analysis_json", "")
        if chain:
            industry_parts.append(f"### 产业链全景分析\n{chain}")
        nodes = record.get("top_nodes_json", "")
        if nodes:
            industry_parts.append(f"### 最优节点分析\n{nodes}")
        industry_context = "\n\n".join(industry_parts)

        if not lock_industry(record_id):
            print(f"[管线B] 加锁失败，跳过")
            continue

        try:
            result = _process_stock(
                stock_name=top_pick_name,
                stock_code=top_pick_code,
                news_content=record.get("news_content", ""),
                knowledge=knowledge,
                step_one=step_one,
                uuid=record.get("uuid", ""),
                level=tianji.get("level", "") if tianji else "",
                mode="产业模式",
                bstudio_time=record.get("bstudio_create_time", ""),
                record_id=record_id,
                industry_context=industry_context,
                verbose=verbose,
            )
            if isinstance(result, tuple) and result[0] == "skip":
                # N0 验证失败 / 非A股 → 标记已处理 + 写入 error_log
                _update_coze_record(DB_INDUSTRY, record_id, {
                    "is_analyzed": "true",
                    "error_log": result[1],
                })
            elif result:
                results.append(result)
        except Exception as e:
            print(f"[管线B] 处理异常: {e}")
            _write_audit_log({
                "record_id": record_id,
                "pipeline": "industry",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })

    return results


# ══════════════════════════════════════════════════════
# 单股票直接调用（不经过轮询）
# ══════════════════════════════════════════════════════

def run_single(
    stock_name: str,
    stock_code: str,
    news_content: str = "",
    knowledge: str = "",
    step_one: str = "",
    verbose: bool = True,
) -> dict | None:
    """直接对单只股票运行预研管线（不经过轮询）。用于测试或手动触发。"""
    return _process_stock(
        stock_name=stock_name,
        stock_code=stock_code,
        news_content=news_content,
        knowledge=knowledge,
        step_one=step_one,
        verbose=verbose,
    )


# ══════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="万业谱预研管线 V2")
    parser.add_argument("--test", action="store_true", help="测试模式: 只跑1条")
    parser.add_argument("--limit", type=int, default=1, help="处理的记录数")
    parser.add_argument("--quiet", action="store_true", help="安静模式")
    parser.add_argument("--stock", type=str, help="直接指定股票代码运行")
    parser.add_argument("--name", type=str, default="", help="股票名称（配合--stock）")
    parser.add_argument("--pipeline", choices=["tianji", "industry", "both"], default="tianji", help="选择管线")
    args = parser.parse_args()

    verbose = not args.quiet

    if args.stock:
        result = run_single(
            stock_name=args.name,
            stock_code=args.stock,
            verbose=verbose,
        )
        if result:
            print(f"\n完成: {result['stock_name']}({result['stock_code']}) {result['elapsed']:.0f}s")
    else:
        limit = 1 if args.test else args.limit

        if args.pipeline in ("tianji", "both"):
            results_a = run_tianji_pipeline(limit=limit, verbose=verbose)
            if results_a:
                print(f"\n管线A完成: {len(results_a)} 条记录")

        if args.pipeline in ("industry", "both"):
            results_b = run_industry_pipeline(limit=limit, verbose=verbose)
            if results_b:
                print(f"\n管线B完成: {len(results_b)} 条记录")
