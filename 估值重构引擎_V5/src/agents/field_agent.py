"""通用 Function Calling Agent 循环引擎。

每个字段的 Agent 使用此引擎执行: search → 自检 → 补搜 → 输出报告
"""

import json
import time
import requests
from typing import Optional, Callable

from .tools import TOOL_DEFINITIONS, TOOL_MAP

# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_config import DEEPSEEK_API_KEY as DEEPSEEK_KEY
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-v4-flash"


def call_deepseek_fc(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 8192,
    temperature: float = 0,
) -> dict:
    """调用 DeepSeek Function Calling API（思考模式）。"""
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
        "thinking": {"type": "enabled"},
        "reasoning_effort": "low",
    }
    if tools:
        payload["tools"] = tools

    r = requests.post(
        DEEPSEEK_URL,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    return r.json()


def run_field_agent(
    system_prompt: str,
    user_message: str,
    field_name: str = "unknown",
    max_search_rounds: int = 20,
    tools: Optional[list[dict]] = None,
    model: str = DEFAULT_MODEL,
    verbose: bool = True,
) -> dict:
    """运行一个字段的探针式 Agent 研究循环。

    工作流程:
        1. 从探针1开始，Agent 自主搜索
        2. 每次搜索后，强制输出 [自检: 收获/缺口/决策]
        3. 缺口填满 → 输出最终报告
        4. 后续探针 → 重复以上流程
        5. 所有探针完成 → 合并输出

    Args:
        system_prompt: Agent 的 System Prompt（包含字段结构要求）
        user_message: 用户指令（包含 stock_name / stock_code / 背景）
        field_name: 字段名（用于日志）
        max_search_rounds: 最大搜索轮次
        tools: 可用工具定义列表（默认使用标准三 tool）
        model: DeepSeek 模型名
        verbose: 是否打印进度

    Returns:
        {
            "content": str,           # 最终报告文本
            "searches": int,          # 搜索次数
            "elapsed": float,         # 耗时（秒）
            "field": str,             # 字段名
            "error": str | None,      # 错误信息
        }
    """
    if tools is None:
        tools = TOOL_DEFINITIONS

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    start_time = time.time()
    searches = 0
    probe_count = 0
    last_output = ""

    for iteration in range(max_search_rounds * 3):  # 每轮可能搜索+自检+输出
        resp = call_deepseek_fc(messages, tools=tools, model=model)

        if "choices" not in resp:
            error_msg = json.dumps(resp, ensure_ascii=False)[:300]
            if verbose:
                print(f"  [{field_name}] API Error: {error_msg}")
            return {
                "content": last_output,
                "searches": searches,
                "elapsed": time.time() - start_time,
                "field": field_name,
                "error": error_msg,
            }

        msg = resp["choices"][0]["message"]
        reasoning = msg.get("reasoning_content", "")

        # ── Agent 调用 Tool ──
        if msg.get("tool_calls"):
            # 添加 assistant 消息（含所有 tool_calls）
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": msg["tool_calls"],
                "reasoning_content": reasoning,
            })

            # 执行每个 tool call
            for tc in msg["tool_calls"]:
                func_name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                searches += 1

                if func_name in TOOL_MAP:
                    result = TOOL_MAP[func_name](**args)
                else:
                    result = f"未知工具: {func_name}"

                if verbose:
                    arg_preview = str(list(args.values())[0])[:80] if args else "?"
                    print(f"  [{field_name}][搜{searches}][{func_name}] {arg_preview}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            # 强制暂停：要求 Agent 自检缺口
            messages.append({
                "role": "user",
                "content": (
                    "数据已返回。请输出自检:\n"
                    "**收获**: 本轮获得的关键数据(3-5条，附数字)\n"
                    "**缺口**: 还有哪些维度缺数据？\n"
                    "**决策**: 缺口>0 → 写下一轮搜索query; 缺口=0 → 输出报告"
                ),
            })
            continue

        # ── Agent 输出文本 ──
        content = msg.get("content", "")
        if not content:
            continue

        messages.append({"role": "assistant", "content": content})
        last_output = content

        # 检测输出类型
        is_selfcheck = any(
            kw in content[:500] for kw in ["收获", "缺口", "决策", "自检"]
        )
        is_probe_output = (
            "结论" in content[:300] and "最强证据" in content[:500]
        )
        is_final_report = not is_selfcheck and not is_probe_output and len(content) > 500

        if is_selfcheck:
            # 检查 Agent 是否决定继续搜索
            if any(kw in content[:1000] for kw in ["继续搜索", "继续搜", "下一轮", "补搜"]):
                if verbose:
                    print(f"  [{field_name}] 自检: 继续搜索")
                continue
            elif any(kw in content[:1000] for kw in ["研究完成", "信息齐全", "信息充足", "输出报告", "撰写报告"]):
                if verbose:
                    print(f"  [{field_name}] 自检: 研究完成，等待输出")
                messages.append({
                    "role": "user",
                    "content": "信息已齐全。请输出最终报告。",
                })
                continue

        if is_probe_output:
            probe_count += 1
            if verbose:
                print(f"  [{field_name}][探针{probe_count}] {len(content)}c")

            # 判断是否所有探针完成（通过 system_prompt 中的探针数量判断）
            # 如果 system_prompt 中有 5 个探针且已完成 5 个
            expected_probes = system_prompt.count("探针")
            # 粗略判断：如果探针输出 > 预期数量，可能已完成
            if probe_count >= 5 or "合并" in content[:500]:
                messages.append({
                    "role": "user",
                    "content": "所有探针完成。请基于探针结果做合并，输出最终报告。",
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"继续下一个探针。",
                })
            continue

        if is_final_report:
            elapsed = time.time() - start_time
            if verbose:
                print(f"  [{field_name}] 最终报告: 搜{searches}次 {elapsed:.0f}s {len(content)}c")
            return {
                "content": content,
                "searches": searches,
                "elapsed": elapsed,
                "field": field_name,
                "error": None,
            }

    # 超时
    elapsed = time.time() - start_time
    return {
        "content": last_output,
        "searches": searches,
        "elapsed": elapsed,
        "field": field_name,
        "error": f"超过最大搜索轮次 ({max_search_rounds})",
    }
