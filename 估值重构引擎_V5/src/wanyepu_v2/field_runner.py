"""N1-N5 通用节点引擎

每个字段节点内部流程:
  1. 读前序报告
  2. LLM: 基于前序认知 → 自由设计N个探针
  3. ThreadPool 并行执行所有探针 (每个: 火山 Agent 结构化搜索)
  4. LLM: 合并探针结论 → 字段报告
"""

import json
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime

from .config import DEEPSEEK_API_KEY, DEEPSEEK_URL, DEEPSEEK_MODEL, VOLC_URL, VOLC_BOT_ID, VOLC_AGENT_KEY, BOCHA_KEY, KIMI_API_KEY, KIMI_URL, KIMI_MODEL
from .probe_prompts import FIELD_DESIGN_PROMPTS, FIELD_DESIGN_PROMPTS_V2, FIELD_MERGE_PROMPTS

BOCHA_URL = "https://api.bochaai.com/v1/web-search"

# 共享 HTTP Session — 复用 TCP 连接，避免批量调用时 socket 耗尽
_http_session = requests.Session()
_http_session.headers.update({"Content-Type": "application/json"})

# 当前日期 — 所有 LLM/火山调用的上下文都注入
CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════
# 字段配置
# ══════════════════════════════════════════════════════

@dataclass
class FieldConfig:
    field_name: str
    prior_fields: list[str]
    probe_min: int
    probe_max: int


FIELD_CONFIGS = {
    "investment_theme": FieldConfig(
        "investment_theme", [], 3, 6,
    ),
    "industry_expert_research": FieldConfig(
        "industry_expert_research", ["investment_theme"], 3, 6,
    ),
    "event_deduction": FieldConfig(
        "event_deduction", ["investment_theme", "industry_expert_research"], 3, 3,
    ),
    "adversarial_thinking": FieldConfig(
        "adversarial_thinking", ["investment_theme", "industry_expert_research", "event_deduction"], 3, 3,
    ),
    "future": FieldConfig(
        "future", ["investment_theme", "industry_expert_research", "event_deduction", "adversarial_thinking"], 2, 4,
    ),
}

# 字段中文名映射
FIELD_CN = {
    "investment_theme": "投资主题",
    "industry_expert_research": "产业链研究",
    "adversarial_thinking": "逆向推演",
    "future": "催化日历",
    "event_deduction": "事件推演",
}


# ══════════════════════════════════════════════════════
# LLM 调用
# ══════════════════════════════════════════════════════

def call_deepseek(system: str, user: str, max_tokens: int = 4096, temperature: float = 0, max_retries: int = 3, thinking: bool = True, model: str = "") -> str:
    """调用 DeepSeek，返回文本。失败重试 max_retries 次。

    thinking=True: 全管线默认（探针设计 + 合并 + N4/N5/N6），Pro 模型 + 思考链产出更严谨
    model: 覆盖默认模型，默认 deepseek-v4-pro
    """
    use_model = model or DEEPSEEK_MODEL
    for attempt in range(max_retries):
        try:
            payload = {
                "model": use_model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            if thinking:
                payload["thinking"] = {"type": "enabled"}
            r = _http_session.post(
                DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                json=payload,
                timeout=120,
            )
            data = r.json()
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            # API 错误 → 重试
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise RuntimeError(f"DeepSeek API错误: {json.dumps(data, ensure_ascii=False)[:300]}")
        except RuntimeError:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            raise RuntimeError(f"DeepSeek 重试3次均失败: {e}")


def call_kimi(system: str, user: str, max_tokens: int = 4096, temperature: float = 1) -> str:
    """调用 Kimi K3 (Kimi For Coding)，返回文本。"""
    r = requests.post(
        KIMI_URL,
        headers={
            "Authorization": f"Bearer {KIMI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": KIMI_MODEL,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=300,
    )
    data = r.json()
    if "choices" not in data:
        raise RuntimeError(f"Kimi API错误: {json.dumps(data, ensure_ascii=False)[:300]}")
    msg = data["choices"][0]["message"]
    # K3 有 reasoning_content（思考过程）和 content（最终输出）
    return msg.get("content", "") or msg.get("reasoning_content", "")


LLM_ENGINES = {
    "deepseek": call_deepseek,
    "kimi": call_kimi,
}


# ══════════════════════════════════════════════════════
# 搜索引擎
# ══════════════════════════════════════════════════════

def volc_search(query: str, timeout: int = 120, max_retries: int = 3) -> str:
    """调用火山 Agent 做结构化知识问答。返回自然语言答案。

    失败重试 max_retries 次，全部失败返回错误标记。
    """
    if not VOLC_AGENT_KEY:
        return "[搜索] VOLC_AGENT_KEY 未配置"

    # 注入当前日期 — 火山不知道今天几号
    dated_query = f"[当前日期: {CURRENT_DATE}] {query}"

    for attempt in range(max_retries):
        try:
            r = _http_session.post(
                VOLC_URL,
                json={
                    "bot_id": VOLC_BOT_ID,
                    "stream": False,
                    "messages": [{"role": "user", "content": dated_query}],
                },
                headers={"Authorization": f"Bearer {VOLC_AGENT_KEY}"},
                timeout=timeout,
            )
            if r.status_code == 200:
                choices = r.json().get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "") or ""
                    if content.strip():
                        return content
                # 空返回 → 重试
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return "[火山] 空返回"

            # HTTP 错误 → 重试
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return f"[火山] HTTP {r.status_code}"

        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return f"[火山] {str(e)[:200]}"

    return "[火山] 重试3次均失败"


def bocha_search(query: str, count: int = 5) -> str:
    """调用博查搜索。返回格式化网页摘要。"""
    try:
        r = _http_session.post(
            BOCHA_URL,
            headers={"Authorization": f"Bearer {BOCHA_KEY}"},
            json={
                "query": query,
                "count": min(count, 10),
                "freshness": "oneYear",
                "summary": True,
            },
            timeout=30,
        )
        data = r.json()
        pages = data.get("data", {}).get("webPages", {}).get("value", [])
        if not pages:
            return "[博查] 无搜索结果"
        return "\n---\n".join(
            f"[{i+1}] {p.get('name','')}\n来源: {p.get('siteName','')} | {p.get('datePublished','')}\n{p.get('summary', p.get('snippet',''))[:800]}"
            for i, p in enumerate(pages[:count]))
    except Exception as e:
        return f"[博查] {str(e)[:200]}"


SEARCH_ENGINES = {
    "volc": volc_search,
    "bocha": bocha_search,
}


# ══════════════════════════════════════════════════════
# Step 2: LLM 设计探针
# ══════════════════════════════════════════════════════

def design_probes(
    field_name: str,
    prior_reports: dict[str, str],
    stock_name: str,
    stock_code: str,
    news_content: str = "",
    knowledge: str = "",
    step_one: str = "",
    company_profile: str = "",
    prompt_version: str = "v1",
    llm_fn=None,
    verbose: bool = True,
) -> tuple[list[dict], str]:
    """LLM: 基于前序报告为本字段设计探针。

    Args:
        prompt_version: "v1"=因果链探针, "v2"=5指令研究指令

    Returns:
        (probes, coverage_note)
        probes: [{"name": "...", "task": "..."}, ...]
    """
    config = FIELD_CONFIGS[field_name]

    if prompt_version == "v2" and field_name in FIELD_DESIGN_PROMPTS_V2:
        design_prompt = FIELD_DESIGN_PROMPTS_V2[field_name]
    else:
        design_prompt = FIELD_DESIGN_PROMPTS[field_name].replace(
            "{min_probes}", str(config.probe_min),
        ).replace(
            "{max_probes}", str(config.probe_max),
        )

    # 构建上下文
    context = f"## 当前日期: {CURRENT_DATE}\n\n"
    context += f"## 股票: {stock_name}（{stock_code}）\n\n"

    if company_profile:
        context += f"## 公司基本认知\n{company_profile}\n\n"

    context += f"## 原始事件\n{news_content if news_content else '无'}\n\n"

    if knowledge and str(knowledge).strip():
        context += f"## AI深度研究\n{str(knowledge)}\n\n"
    if step_one and str(step_one).strip():
        context += f"## 预研分析\n{str(step_one)}\n\n"

    if prior_reports:
        context += "## 前序报告（已完成的深度分析）\n\n"
        for fname, freport in prior_reports.items():
            fn_cn = FIELD_CN.get(fname, fname)
            context += f"### {fn_cn}\n{str(freport)}\n\n"

    if llm_fn is None:
        llm_fn = call_deepseek

    content = llm_fn(
        system=design_prompt,
        user=f"{context}\n\n---\n请基于以上信息设计探针。直接输出JSON。",
        max_tokens=4096,
    )

    # 提取 JSON
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                if verbose:
                    print(f"  [{field_name}] 探针设计JSON解析失败: {content[:200]}")
                return [], "JSON解析失败"
        else:
            if verbose:
                print(f"  [{field_name}] 探针设计JSON解析失败: {content[:200]}")
            return [], "JSON解析失败"

    # p1-p5 格式: {"p1": "...", "p2": "...", ...} → 转为标准 probes 格式
    if "p1" in result:
        probes = []
        for key in sorted(result.keys()):
            if key.startswith("p") and isinstance(result[key], str):
                # 从指令文本中提取简短标题（取前15字）
                task = result[key]
                name = task[:15].replace("\n", " ").strip()
                probes.append({"name": name, "task": task})
        coverage = f"{len(probes)}个研究指令"
        return probes, coverage

    probes = result.get("probes", [])
    coverage = result.get("coverage_note", "")
    return probes, coverage


# ══════════════════════════════════════════════════════
# Step 3: 探针执行 (火山 Agent)
# ══════════════════════════════════════════════════════

def execute_single_probe(
    probe_name: str,
    probe_task: str,
    engine: str = "volc",
    verbose: bool = True,
) -> dict:
    """执行单个探针: 1次搜索引擎调用。

    Args:
        probe_name: 探针名称
        probe_task: 探针任务描述
        engine: 搜索引擎 ("volc" / "bocha")
        verbose: 打印进度

    Returns:
        {"name": str, "conclusion": str, "searches": int, "engine": str, "elapsed": float}
    """
    search_fn = SEARCH_ENGINES.get(engine, volc_search)
    engine_label = "火山" if engine == "volc" else "博查"

    # 追加来源标注要求
    full_task = probe_task + "\n\n要求: 每个关键数据标注来源（域名+日期），无法追溯来源的数字不得写入。"

    if verbose:
        print(f"    [探针:{probe_name[:20]}] {engine_label}搜索中...")

    t0 = time.time()
    result = search_fn(full_task)
    elapsed = time.time() - t0

    if verbose:
        is_fail = result.startswith(f"[{engine_label}]")
        status = "FAIL" if is_fail else "OK"
        print(f"    [探针:{probe_name[:20]}] {status} {elapsed:.0f}s {len(result)}c")

    return {
        "name": probe_name,
        "conclusion": result,
        "searches": 1,
        "engine": engine,
        "elapsed": round(elapsed, 1),
    }


def parallel_execute_probes(
    probes: list[dict],
    engine: str = "volc",
    max_workers: int = 5,
    verbose: bool = True,
) -> list[dict]:
    """ThreadPool 并行执行所有探针。

    max_workers=5: 火山并发限制
    """
    results = []
    name_order = {p["name"]: i for i, p in enumerate(probes)}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(execute_single_probe, p["name"], p["task"], engine, verbose): p
            for p in probes
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                p = futures[future]
                if verbose:
                    print(f"    [探针:{p['name'][:20]}] 异常: {e}")
                results.append({
                    "name": p["name"],
                    "conclusion": f"[执行异常] {e}",
                    "searches": 0,
                    "engine": engine,
                    "elapsed": 0,
                })

    # 按原始顺序排序
    results.sort(key=lambda x: name_order.get(x["name"], 99))
    return results


# ══════════════════════════════════════════════════════
# Step 3.5: 自适应深入探针
# ══════════════════════════════════════════════════════

DEEP_DIVE_SYSTEM = """你是研究策略师。你已读完5份探针结论。你的任务是判断：哪些方向有料值得深入？哪些方向是空的需要换方向？

## 判断规则

1. **有料 → 深入**: 如果某份探针结论包含具体数字、独家信息、或与预期矛盾的发现 → 设计1个深入探针追问细节
2. **空的 → 换方向**: 如果某份探针结论为空、泛泛而谈、或与已知信息重复 → 设计1个新探针换方向搜索
3. **不需要深入的**: 如果所有探针结论都已充分覆盖核心问题 → 输出空数组

## 输出格式

纯JSON:
{
  "analysis": "一句话说明哪些方向有料/哪些是空的",
  "deep_probes": [
    {"name": "简短标题", "task": "深入搜索任务(≤300字), 引用原探针的具体发现"},
    ...
  ]
}

最多2个深入探针。深入探针必须引用原探针的具体发现，不要重复搜索已覆盖的内容。"""


def design_deep_probes(
    field_name: str,
    probe_results: list[dict],
    llm_fn=None,
    verbose: bool = True,
) -> list[dict]:
    """LLM 读第1轮探针结论，设计深入探针。

    Returns:
        深入探针列表（0-2个）
    """
    if llm_fn is None:
        llm_fn = call_deepseek
    # 构建探针结论摘要
    conclusions_text = "\n\n---\n\n".join(
        f"## 探针{i+1}: {p['name']}\n{p['conclusion']}"
        for i, p in enumerate(probe_results)
    )

    try:
        content = llm_fn(
            system=DEEP_DIVE_SYSTEM,
            user=f"[当前日期: {CURRENT_DATE}]\n\n以下是{len(probe_results)}份独立探针结论:\n\n{conclusions_text}",
            max_tokens=2048,
        )

        # 解析 JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                result = json.loads(match.group())
            else:
                if verbose:
                    print(f"  [深入探针] JSON解析失败: {content[:200]}")
                return []

        deep_probes = result.get("deep_probes", [])
        analysis = result.get("analysis", "")

        # 统一格式: 确保每个 probe 都有 name 和 task
        normalized = []
        for p in deep_probes:
            if isinstance(p, dict) and "task" in p:
                normalized.append({"name": p.get("name", p["task"][:15]), "task": p["task"]})
            elif isinstance(p, str):
                normalized.append({"name": p[:15], "task": p})

        if verbose and normalized:
            print(f"  [深入探针] {analysis[:80]}")
            for i, p in enumerate(normalized):
                print(f"    d{i+1}: {p['name'][:40]}")

        return normalized[:2]  # 最多2个

    except Exception as e:
        if verbose:
            print(f"  [深入探针] 设计失败: {e}")
        return []


# ══════════════════════════════════════════════════════
# Step 4: LLM 合并探针 → 字段报告
# ══════════════════════════════════════════════════════

def merge_probes(field_name: str, probe_results: list[dict], llm_fn=None, verbose: bool = True) -> str:
    """将N个独立探针结论合并为字段报告。

    thinking=True：Pro 模型 + 思考模式产出更严谨的交叉验证和数字核对，
    配合 prompt 中的"数字必须原样引用"约束，既保证忠实于探针结论，
    又能利用思考链做单位/数量级自检。
    """
    if llm_fn is None:
        llm_fn = lambda system, user, max_tokens, **kw: call_deepseek(system, user, max_tokens=max_tokens, thinking=True)
    conclusions_text = "\n\n---\n\n".join(
        f"## 探针{i+1}: {p['name']}\n{p['conclusion']}"
        for i, p in enumerate(probe_results)
    )

    merge_prompt = FIELD_MERGE_PROMPTS.get(field_name, FIELD_MERGE_PROMPTS["investment_theme"])

    report = llm_fn(
        system=merge_prompt,
        user=f"[当前日期: {CURRENT_DATE}]\n\n以下是{len(probe_results)}份独立探针结论。请按照系统指令中的格式直接输出最终报告——不要复述指令、不要写过程说明，只输出报告本身:\n\n{conclusions_text}",
        max_tokens=8192,
    )

    if verbose:
        print(f"  [{field_name}] 合并完成: {len(report)}c")

    return report


# ══════════════════════════════════════════════════════
# 主入口: 运行单个字段节点
# ══════════════════════════════════════════════════════

def run_field(
    field_name: str,
    prior_reports: dict[str, str],
    stock_name: str,
    stock_code: str,
    news_content: str = "",
    knowledge: str = "",
    step_one: str = "",
    company_profile: str = "",
    engine: str = "volc",
    llm_engine: str = "deepseek",
    prompt_version: str = "v1",
    max_workers: int = 5,
    verbose: bool = True,
) -> str:
    """运行 N1-N5 中的一个字段节点。

    Args:
        field_name: 字段名 (investment_theme / industry_expert_research / ...)
        prior_reports: 前序报告 dict {field_name: report_text}
        stock_name: 股票名称
        stock_code: 股票代码
        news_content: 原始事件
        knowledge: AI深度研究
        step_one: 预研分析
        company_profile: N0.5 公司前置认知
        engine: 搜索引擎 ("volc" / "bocha")
        llm_engine: LLM 引擎 ("deepseek" / "kimi")
        prompt_version: 探针设计 Prompt 版本 ("v1" / "v2")
        max_workers: 探针并行数
        verbose: 打印进度

    Returns:
        字段报告 (Markdown)
    """
    llm_fn = LLM_ENGINES.get(llm_engine, call_deepseek)
    config = FIELD_CONFIGS[field_name]
    t_start = time.time()

    if verbose:
        n_prior = len([f for f in config.prior_fields if f in prior_reports])
        print(f"\n[{FIELD_CN.get(field_name, field_name)}] 开始 (前序报告: {n_prior}份, prompt={prompt_version})")

    # Step 1: 收集前序报告
    priors = {}
    for f in config.prior_fields:
        if f in prior_reports and prior_reports[f]:
            priors[f] = prior_reports[f]

    # Step 2: 设计探针
    probes, coverage = design_probes(
        field_name, priors, stock_name, stock_code,
        news_content, knowledge, step_one, company_profile, prompt_version, llm_fn, verbose,
    )

    if not probes:
        if verbose:
            print(f"  [{field_name}] 探针设计失败: {coverage}")
        return f"[{FIELD_CN.get(field_name, field_name)}] 探针设计失败: {coverage}"

    if verbose:
        print(f"  [{field_name}] 设计{len(probes)}个探针: {coverage[:80]}")
        for i, p in enumerate(probes):
            print(f"    p{i+1}: {p['name'][:40]}")

    # Step 3: 第1轮并行执行探针
    probe_results = parallel_execute_probes(probes, engine=engine, max_workers=max_workers, verbose=verbose)

    total_searches = sum(p["searches"] for p in probe_results)
    if verbose:
        for i, pr in enumerate(probe_results):
            print(f"    p{i+1}: {pr['searches']}搜 {len(pr['conclusion'])}c")

    # Step 3.5: 自适应深入探针
    deep_probes = design_deep_probes(field_name, probe_results, llm_fn, verbose=verbose)
    deep_results = []

    if deep_probes:
        if verbose:
            print(f"  [{field_name}] 第2轮深入: {len(deep_probes)}个探针")
        deep_results = parallel_execute_probes(deep_probes, engine=engine, max_workers=max_workers, verbose=verbose)
        deep_searches = sum(p["searches"] for p in deep_results)
        total_searches += deep_searches
        if verbose:
            for i, pr in enumerate(deep_results):
                print(f"    d{i+1}: {pr['searches']}搜 {len(pr['conclusion'])}c")

    # Step 4: 合并（广度+深度）
    all_results = probe_results + deep_results
    report = merge_probes(field_name, all_results, llm_fn, verbose=verbose)

    elapsed = time.time() - t_start
    if verbose:
        print(f"[{FIELD_CN.get(field_name, field_name)}] 完成: {len(probes)}探针 {total_searches}搜 {elapsed:.0f}s {len(report)}c")

    return report
