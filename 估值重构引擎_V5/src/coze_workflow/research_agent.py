"""
Research Agent — Coze Code 节点
===============================
用 DeepSeek Flash 驱动，Bocha 搜索，两阶段完成复杂调研任务。

流程:
  Phase 1 — 规划: DeepSeek 读复杂query → 规划 5-8 个搜索
  Phase 2 — 执行: 并行搜索 + 关键结果点进去读全文
  Phase 3 — 合成: DeepSeek 读所有搜索结果 → 输出完整报告

部署: 复制全部代码到 Coze Code 节点(Python 3.10+ Async)
超时: 建议 Coze 节点超时设 180s

输入: research_task (String) - 复杂调研指令
输出: research_report (String) - 完整调研报告
"""

import json
import time
import asyncio

# ═══════════════════════════════════════
# 配置
# ═══════════════════════════════════════

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# DeepSeek key: Coze Code 节点中通过环境变量或直接硬编码
# 部署到 Coze 时替换为实际 key
import os as _os
DEEPSEEK_KEY = _os.environ.get("DEEPSEEK_API_KEY", "")

# ═══════════════════════════════════════
# 搜索 — 火山 Agent API (feedcoop bot)
# 中文金融搜索质量高, 无需额外部署, Coze Code 节点直调
# ═══════════════════════════════════════

VOLC_URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
VOLC_BOT_ID = "7640524154441156122"
VOLC_KEY = _os.environ.get("VOLC_AGENT_KEY", "")


async def web_search(query: str, count: int = 5) -> str:
    """调用火山 Agent 做结构化知识问答。返回自然语言答案。"""
    if not VOLC_KEY:
        return "[搜索] VOLC_AGENT_KEY 未配置"

    try:
        r = await requests_async.post(
            VOLC_URL,
            json={
                "bot_id": VOLC_BOT_ID,
                "stream": False,
                "messages": [{"role": "user", "content": query}],
            },
            headers={
                "Authorization": f"Bearer {VOLC_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "") or ""
                if content.strip():
                    return f"### 火山: {query[:60]}...\n\n{content}"
        return f"[火山] 空返回 (HTTP {r.status_code})"

    except Exception as e:
        return f"[火山] {str(e)[:150]}"


async def call_deepseek(system: str, user: str, max_tokens: int = 4096, temperature: float = 0) -> str:
    """调用 DeepSeek，返回文本。"""
    resp = await requests_async.post(
        DEEPSEEK_URL,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEEPSEEK_MODEL,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    data = resp.json()
    if "choices" in data:
        return data["choices"][0]["message"]["content"]
    return f"[DeepSeek错误] {json.dumps(data, ensure_ascii=False)[:300]}"


# ═══════════════════════════════════════
# Phase 1: 规划搜索策略
# ═══════════════════════════════════════

PLANNER_PROMPT = """你是搜索策略规划师。把复杂调研指令拆成 3-5 个火山搜索 query。

## 原则

- 火山引擎是一个结构化知识问答系统。query 是自然语言，不是关键词罗列。
- 每个 query 可以覆盖 2-3 个相关的子方向。火山擅长处理 200-400 字的复合查询。
- query 中写清楚：要什么数据、要什么来源、要什么精度。
- 覆盖调研指令的全部子方向，不遗漏也不重复。

## 输出格式

纯 JSON 数组: ["query 1", "query 2", ...]"""


async def plan_searches(research_task: str) -> list[str]:
    """Phase 1: DeepSeek 规划搜索策略。"""
    user = f"请将以下调研指令拆解为搜索query:\n\n{research_task[:3000]}"

    raw = await call_deepseek(PLANNER_PROMPT, user, max_tokens=2048)

    # 提取 JSON
    try:
        queries = json.loads(raw)
        if isinstance(queries, list) and len(queries) > 0:
            return queries[:4]  # 最多 4 个
    except json.JSONDecodeError:
        pass

    # 备用提取: 找方括号
    import re
    m = re.search(r"\[([\s\S]*?)\]", raw)
    if m:
        try:
            return json.loads(f"[{m.group(1)}]")[:4]
        except:
            pass

    # 最后手段: 按行切
    lines = [l.strip().lstrip("0123456789. -•") for l in raw.split("\n") if len(l.strip()) > 10]
    return lines[:4] if lines else ["晶方科技 核心业务 技术壁垒 行业地位"]


# ═══════════════════════════════════════
# Phase 2: 并行搜索 + 点读
# ═══════════════════════════════════════


async def execute_searches(queries: list[str]) -> str:
    """Phase 2: 并行搜索，然后对最重要的结果点进去读全文。"""
    # 并行搜索 (火山 API 每次 30-50s, 最多 3 个并行)
    queries = queries[:3]
    tasks = [web_search(q) for q in queries]
    results = await asyncio.gather(*tasks)
    return "\n\n".join(results)


# ═══════════════════════════════════════
# Phase 3: 合成报告
# ═══════════════════════════════════════

SYNTHESIS_PROMPT = """你是研究合成师。基于搜索材料，完成调研指令要求的完整报告。

## 要求

1. **覆盖全部子方向**: 调研指令中每个编号的子方向都要在报告中体现。用【】标出每个子方向。
2. **有数字有来源**: 每个关键数据必须标注来源（如"来源: 中邮证券2026年3月研报"）。搜索材料中没有来源的 → 标注"[推断]"或"[未找到来源]"
3. **不只是罗列**: 要串联事实、做交叉验证。如果不同来源对同一数据有不同说法 → 标注分歧。
4. **诚实标注缺口**: 搜索材料中确实找不到的信息 → 写"[搜索未覆盖]"而不是编造。
5. **篇幅**: 满足调研指令的要求即可，不要为了长而长。

## 输出

直接输出 Markdown 报告，每个子方向用【】标出。不要用代码块包裹。"""


async def synthesize(research_task: str, search_materials: str) -> str:
    """Phase 3: DeepSeek 合成最终报告。"""
    user = f"""## 调研指令

{research_task[:5000]}

## 搜索材料

{search_materials[:30000]}

请基于以上搜索材料，输出完整调研报告。"""

    return await call_deepseek(SYNTHESIS_PROMPT, user, max_tokens=16384)


# ═══════════════════════════════════════
# 主入口 (Coze Code 节点格式)
# ═══════════════════════════════════════


async def main(args) -> dict:
    """Coze Code 节点入口。

    Args.params:
        research_task: 复杂调研指令（如 p1 的 8 个子方向）
    """
    task = str(args.params.get("research_task", "") or "")

    if not task or len(task) < 50:
        return {
            "research_report": "错误: research_task 为空或太短（需 ≥50 字）",
            "search_count": 0,
            "elapsed_ms": 0,
        }

    t0 = time.time()

    # Phase 1: 规划
    queries = await plan_searches(task)
    n_queries = len(queries)

    # Phase 2: 执行搜索
    search_materials = await execute_searches(queries)

    # Phase 3: 合成
    report = await synthesize(task, search_materials)

    elapsed = int((time.time() - t0) * 1000)

    return {
        "research_report": report,
        "search_count": n_queries,
        "elapsed_ms": elapsed,
    }
