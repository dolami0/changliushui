"""万业谱预研语料管线 — 主入口。

三层自适应 Agent 架构:
  第1层: 事件消化 (digest_agent) → 判定类型 + 初版语料
  第2层: 探针分配 (probe_allocator) → 深化探针 + 并行执行
  第3层: 总装 (assembler) → 去重 + 写入
"""

import sys
import os
import time
import json
import re
import requests
from datetime import datetime
from typing import Optional

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.tools import TOOL_DEFINITIONS
from agents.field_agent import run_field_agent
from agents.digest_agent import run_digest
from agents.probe_allocator import allocate_probes
from agents.assembler import assemble_and_write, mark_tianji_processed
from agents.prompts import (
    ADVERSARIAL_PROMPT,
    FUTURE_PROMPT,
    EVENT_DEDUCTION_PROMPT,
)

# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════

COZE_TOKEN = "sat_UxIpTimxUFwh0BGedY1yxK7YJbqrqryebdRVyt8AjducYxsH8cFkkso6Orh2RTGc"
COZE_BASE = "https://api.coze.cn/v1/databases"
DB_TIANJIJUAN = "7479116110479048754"


# ═══════════════════════════════════════════════
# 天机卷读取
# ═══════════════════════════════════════════════

def fetch_unprocessed_records(limit: int = 5) -> list[dict]:
    """从天机卷拉取待处理记录。

    筛选: mode="个股模式", level>="4", is_analyzed!="true", is_analyzing!="true"
    """
    url = f"{COZE_BASE}/{DB_TIANJIJUAN}/records/query"

    payload = {
        "page_size": limit,
        "order_by": [{"direction": "desc", "field_name": "bstudio_create_time"}],
        "filter": {
            "logic": "and",
            "conditions": [
                {"left": "mode", "operation": "equal", "right": "个股模式"},
                {"left": "level", "operation": "greater_than_or_equal", "right": "4"},
                {"left": "is_analyzed", "operation": "not_equal", "right": "true"},
                {"left": "is_analyzing", "operation": "not_equal", "right": "true"},
            ],
        },
    }

    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {COZE_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    data = r.json()
    items = data.get("data", {}).get("items", [])
    return items


def lock_record(record_id: str) -> bool:
    """加锁: is_analyzing = "true" """
    try:
        r = requests.post(
            f"{COZE_BASE}/{DB_TIANJIJUAN}/records/{record_id}",
            headers={
                "Authorization": f"Bearer {COZE_TOKEN}",
                "Content-Type": "application/json",
            },
            json={"is_analyzing": "true"},
            timeout=30,
        )
        return r.status_code == 200
    except Exception:
        return False


# ═══════════════════════════════════════════════
# 主管线
# ═══════════════════════════════════════════════

def run_pipeline_record(record: dict, verbose: bool = True) -> Optional[dict]:
    """处理单条天机卷记录。"""
    record_id = record.get("id", "")
    stock_code = record.get("stock_code", "")
    stock_name = record.get("stock_name", "")
    news_content = record.get("news_content", "")
    knowledge = record.get("knowledge", "")
    step_one = record.get("step_one", "")

    # 清洗 news_content
    news_clean = re.sub(r"<[^>]+>", "", news_content)
    news_clean = re.sub(r"&[^;]+;", " ", news_clean)
    news_clean = re.sub(r"\s+", " ", news_clean).strip()

    if not stock_code or not stock_name:
        print(f"[Pipeline] 跳过: stock_code或stock_name为空 (id={record_id})")
        return None

    if verbose:
        print(f"\n{'='*60}")
        print(f"[Pipeline] 处理: {stock_name}({stock_code})")
        print(f"[Pipeline] 记录ID: {record_id}")
        print(f"{'='*60}")

    # 加锁
    if not lock_record(record_id):
        print(f"[Pipeline] 加锁失败，跳过")
        return None

    t_start = time.time()

    # ── 第1层: 事件消化 ──
    if verbose:
        print("\n[第1层] 事件消化...")

    digest = run_digest(
        stock_name=stock_name,
        stock_code=stock_code,
        news_content=news_clean,
        knowledge=knowledge,
        step_one=step_one,
        verbose=verbose,
    )

    event_type = digest["event_type"]
    ier1_content = digest["industry_expert_research_1"]["content"]
    theme_content = digest["investment_theme"]["content"]

    # ── 第2层: 探针分配 ──
    if verbose:
        print(f"\n[第2层] 探针分配 (事件类型: {event_type})...")

    allocation = allocate_probes(
        event_type=event_type,
        stock_name=stock_name,
        stock_code=stock_code,
        ier1_content=ier1_content,
        theme_content=theme_content,
        verbose=verbose,
    )

    # ── 第2层: 并行深化 Agent ──
    if verbose:
        print(f"\n[第2层] 并行深化 Agent...")

    field_results = {
        "industry_expert_research": ier1_content,  # 初始值,可能会被深化版覆盖
        "investment_theme": theme_content,          # 初始值
    }

    # 为每个需要深化的字段运行 Agent
    field_configs = {
        "adversarial_thinking": (ADVERSARIAL_PROMPT, "adversarial"),
        "future": (FUTURE_PROMPT, "future"),
        "event_deduction": (EVENT_DEDUCTION_PROMPT, "deduction"),
    }

    # industry_expert_research 深化（如果有深化探针）
    ier_probes = allocation.get("industry_expert_research", {}).get("probes", [])
    if ier_probes and ier_probes != ["未分配探针"]:
        ier_deep_prompt = _build_deep_prompt(
            "industry_expert_research",
            ier_probes,
            allocation.get("industry_expert_research", {}).get("output_format", ""),
            ier1_content,
        )
        if verbose:
            print(f"  [ier_deep] {len(ier_probes)} 个深化探针")

        ier_deep_result = run_field_agent(
            system_prompt=ier_deep_prompt,
            user_message=_build_user_msg(stock_name, stock_code, news_clean, step_one, knowledge, ier_probes),
            field_name="ier_deep",
            verbose=verbose,
        )
        field_results["industry_expert_research"] = ier_deep_result["content"]

    # 其余字段并行执行 (实际可并发,当前顺序执行)
    for field_name, (prompt, label) in field_configs.items():
        probes = allocation.get(field_name, {}).get("probes", [])
        output_format = allocation.get(field_name, {}).get("output_format", "")

        if probes and probes != ["未分配探针"]:
            deep_prompt = _build_deep_prompt(field_name, probes, output_format, prompt)

            if verbose:
                print(f"  [{label}] {len(probes)} 个深化探针")

            result = run_field_agent(
                system_prompt=deep_prompt,
                user_message=_build_user_msg(stock_name, stock_code, news_clean, step_one, knowledge, probes),
                field_name=label,
                verbose=verbose,
            )
            field_results[field_name] = result["content"]
        else:
            # 无深化探针 → 用通用 Prompt 跑一次
            if verbose:
                print(f"  [{label}] 通用探针")
            result = run_field_agent(
                system_prompt=prompt,
                user_message=_build_user_msg(stock_name, stock_code, news_clean, step_one, knowledge),
                field_name=label,
                verbose=verbose,
            )
            field_results[field_name] = result["content"]

    # ── 第3层: 总装 + 写入 ──
    if verbose:
        print(f"\n[第3层] 总装 + 写入...")

    write_result = assemble_and_write(
        stock_name=stock_name,
        stock_code=stock_code,
        source_record_id=record_id,
        tianji_data=record,
        preliminary_reasoning=step_one,
        industry_expert_research=field_results.get("industry_expert_research", ""),
        adversarial_thinking=field_results.get("adversarial_thinking", ""),
        investment_theme=field_results.get("investment_theme", ""),
        future=field_results.get("future", ""),
        event_deduction=field_results.get("event_deduction", ""),
        verbose=verbose,
    )

    # 标记天机卷
    mark_tianji_processed(record_id, verbose=verbose)

    total_elapsed = time.time() - t_start
    if verbose:
        print(f"\n[Pipeline] 完成: {total_elapsed:.0f}s")
        print(f"{'='*60}")

    return {
        "record_id": record_id,
        "stock_name": stock_name,
        "stock_code": stock_code,
        "event_type": event_type,
        "elapsed": total_elapsed,
        "write_status": write_result.get("status", "unknown"),
    }


def run_pipeline(limit: int = 5, verbose: bool = True) -> list[dict]:
    """运行完整管线: 从天机卷拉取 → 处理 → 写入万业谱。"""
    records = fetch_unprocessed_records(limit)

    if not records:
        print("[Pipeline] 无待处理记录")
        return []

    print(f"[Pipeline] 获取 {len(records)} 条待处理记录")

    results = []
    for i, record in enumerate(records):
        print(f"\n[{i+1}/{len(records)}]")
        try:
            result = run_pipeline_record(record, verbose=verbose)
            if result:
                results.append(result)
        except Exception as e:
            print(f"[Pipeline] 处理失败: {e}")
            # 解锁
            record_id = record.get("id", "")
            if record_id:
                try:
                    requests.post(
                        f"{COZE_BASE}/{DB_TIANJIJUAN}/records/{record_id}",
                        headers={
                            "Authorization": f"Bearer {COZE_TOKEN}",
                            "Content-Type": "application/json",
                        },
                        json={"is_analyzing": "false"},
                        timeout=10,
                    )
                except Exception:
                    pass

    return results


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def _build_deep_prompt(
    field_name: str,
    probes: list[str],
    output_format: str,
    base_prompt: str,
) -> str:
    """构建深化探针的 System Prompt"""
    probes_text = "\n".join(f"{i+1}. {p}" for i, p in enumerate(probes))
    return (
        f"{base_prompt}\n\n"
        f"## 深化探针（除通用探针外，额外研究以下方向）\n"
        f"{probes_text}\n\n"
        f"## 总结格式要求\n{output_format}\n\n"
        f"在完成通用探针后，继续执行上述深化探针。"
    )


def _build_user_msg(
    stock_name: str,
    stock_code: str,
    news_content: str,
    step_one: str = "",
    knowledge: str = "",
    probes: list[str] | None = None,
) -> str:
    """构建 User Message"""
    msg = f"请为{stock_name}（{stock_code}）做分析。"
    if news_content:
        msg += f"\n\n## 事件背景\n{news_content[:1500]}"
    if step_one:
        msg += f"\n\n## 预研分析\n{step_one[:1000]}"
    if knowledge:
        msg += f"\n\n## 知识补充\n{knowledge[:1000]}"
    if probes:
        probes_list = "\n".join(f"- {p}" for p in probes)
        msg += f"\n\n## 深化研究方向\n{probes_list}"
    msg += "\n\n从通用探针开始，然后执行深化探针。"
    return msg


# ═══════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="万业谱预研语料管线")
    parser.add_argument("--test", action="store_true", help="测试模式: 只跑1条")
    parser.add_argument("--limit", type=int, default=1, help="处理的记录数")
    parser.add_argument("--quiet", action="store_true", help="安静模式")
    args = parser.parse_args()

    verbose = not args.quiet
    limit = 1 if args.test else args.limit

    results = run_pipeline(limit=limit, verbose=verbose)

    if results:
        print(f"\n{'='*60}")
        print(f"管线完成: {len(results)} 条记录")
        for r in results:
            print(f"  {r['stock_name']}({r['stock_code']}) — {r['event_type']} — {r['elapsed']:.0f}s")
    else:
        print("\n无处理结果")
