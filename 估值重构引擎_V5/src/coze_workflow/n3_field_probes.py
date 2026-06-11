"""N3-N7 [Code] 字段探针执行+合并
Coze Code节点 — Python 3

这是5个并行节点的通用代码。每个节点硬编码不同的 field_name:
  N3: field_name = "industry_expert_research"
  N4: field_name = "adversarial_thinking"
  N5: field_name = "investment_theme"
  N6: field_name = "future"
  N7: field_name = "event_deduction"

输入变量: probes_map, stock_name, stock_code, news_content, step_one, knowledge, field_name
输出变量: field_report (print输出)

内部流程: 解析本字段的3个探针 → ThreadPool并行执行 → 合并Agent → 输出
"""

import json
import requests
import time
import concurrent.futures

# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════

DEEPSEEK_KEY = "sk-8f02dfb2f5a44e02b7afea5e2daa5814"
BOCHA_KEY = "sk-090c432b4f5745caa8767ae70f5b348b"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
BOCHA_URL = "https://api.bochaai.com/v1/web-search"


# ═══════════════════════════════════════════════
# 工具: 博查搜索
# ═══════════════════════════════════════════════

def bocha_search(query, count=5):
    """搜索中文互联网，返回格式化文本"""
    try:
        r = requests.post(
            BOCHA_URL,
            headers={
                "Authorization": f"Bearer {BOCHA_KEY}",
                "Content-Type": "application/json",
            },
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
            return "无搜索结果，请换一个更具体的查询重试。"

        results = []
        for i, p in enumerate(pages[:count]):
            results.append(
                f"[{i + 1}] {p.get('name', '无标题')}\n"
                f"来源: {p.get('siteName', '?')} | "
                f"日期: {p.get('datePublished', '?')}\n"
                f"摘要: {p.get('summary', p.get('snippet', ''))[:800]}"
            )
        return "\n---\n".join(results)
    except Exception as e:
        return f"搜索异常: {str(e)}"


# ═══════════════════════════════════════════════
# FC 工具定义
# ═══════════════════════════════════════════════

TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "bocha_search",
            "description": (
                "搜索中文互联网信息（行业数据、券商研报、市场分析、新闻）。"
                "返回网页标题、来源、日期和详细摘要。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询，要具体，包含公司名、产品名、行业术语",
                    },
                    "count": {
                        "type": "integer",
                        "description": "返回结果数，默认5，最大10",
                    },
                },
                "required": ["query"],
            },
        },
    }
]

TOOL_MAP = {"bocha_search": bocha_search}


# ═══════════════════════════════════════════════
# 单个探针执行
# ═══════════════════════════════════════════════

def run_single_probe(probe_name, probe_task, stock_info, max_searches=2):
    """独立探针: 干净上下文, ≤2次搜索, 只输出4项结论

    Returns:
        {"name": str, "conclusion": str, "searches": int, "queries": [...]}
    """
    system = f"""你是专项分析师。你只有一个任务: {probe_task}

你有 bocha_search 工具。最多搜索 {max_searches} 次。

第1次搜索覆盖面，第2次只补第1次发现的最大缺口。

搜完后立即输出4项结论。不要写报告，只输出4项:

**结论**: [一句话直接回答问题]
**最强证据**: [具体数字，标注来源]
**最大缺口**: [如实写缺什么信息，不要编造]
**一手来源**: [需要补的原始数据/报告名称，如年报/招股书/行业白皮书]"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"请完成探针任务: {probe_task}\n\n标的: {stock_info}"},
    ]

    searches_done = 0
    searches_log = []

    for iteration in range(8):
        # ── 搜满 → 强制输出 ──
        if searches_done >= max_searches:
            resp = requests.post(
                DEEPSEEK_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-v4-flash",
                    "temperature": 0,
                    "max_tokens": 2048,
                    "messages": messages
                    + [
                        {
                            "role": "user",
                            "content": "搜索已达上限。请立即输出4项结论。",
                        }
                    ],
                    "tools": None,
                    "thinking": {"type": "enabled"},
                },
                timeout=60,
            )
            data = resp.json()
            if "choices" in data and data["choices"][0]["message"].get("content"):
                return {
                    "name": probe_name,
                    "conclusion": data["choices"][0]["message"]["content"],
                    "searches": searches_done,
                    "queries": searches_log,
                }
            break

        # ── 正常FC调用 ──
        resp = requests.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-v4-flash",
                "temperature": 0,
                "max_tokens": 4096,
                "messages": messages,
                "tools": TOOLS_DEF,
                "thinking": {"type": "enabled"},
            },
            timeout=60,
        )

        data = resp.json()
        if "choices" not in data:
            break

        msg = data["choices"][0]["message"]
        reasoning = msg.get("reasoning_content", "")

        # Agent调用工具
        if msg.get("tool_calls"):
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": msg["tool_calls"],
                    "reasoning_content": reasoning,
                }
            )
            for tc in msg["tool_calls"]:
                func = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])
                searches_done += 1
                query = list(args.values())[0] if args else "?"
                result = TOOL_MAP[func](**args) if func in TOOL_MAP else "未知工具"
                searches_log.append(
                    {"tool": func, "query": str(query)[:200]}
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    }
                )

            hint = f"数据返回。已搜{searches_done}次"
            if searches_done >= max_searches:
                hint += "，已达上限，请立即输出4项结论。"
            else:
                hint += "，可以再搜1次补缺口，或输出4项结论。"
            messages.append({"role": "user", "content": hint})
        else:
            # Agent输出文本 → 有实质内容就结束
            content = msg.get("content", "")
            if content and len(content) > 100:
                return {
                    "name": probe_name,
                    "conclusion": content,
                    "searches": searches_done,
                    "queries": searches_log,
                }
            elif content:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "请输出4项结论。"})

    return {
        "name": probe_name,
        "conclusion": "",
        "searches": searches_done,
        "queries": searches_log,
        "error": "超时",
    }


# ═══════════════════════════════════════════════
# 字段合并 Agent
# ═══════════════════════════════════════════════

def merge_probes(field_name, probe_results, stock_info):
    """将3个独立探针的结论合并为一份字段报告"""

    conclusions_text = "\n\n---\n\n".join(
        f"## 探针{i + 1}: {p['name']}\n{p['conclusion']}"
        for i, p in enumerate(probe_results)
    )

    merge_prompts = {
        "industry_expert_research": """你是行业分析师。合并3份独立探针结论为一份行业研究报告。

## 合并规则
1. 互相支持的结论 → 标注"**高置信度**（探针X和探针Y独立得出相同结论）"并合并
2. 互相冲突的结论 → 标注"⚠️ **存在分歧**"，不做调和
3. 所有探针都缺的信息 → 标注"**[数据缺失]**"
4. Serenity规则: 如果多个探针独立得出卡点判断，标注"**交叉验证通过**"

## 报告格式

### 一、产业链位置与需求确定度
（来源：探针①核心发现。附交叉验证标记）

### 二、供给格局与价值捕获
（来源：探针②核心发现。附交叉验证标记）

### 三、卡点检查与反方证据
（来源：探针③核心发现。含4条标准的逐条检查结果）""",

        "adversarial_thinking": """你是逆向分析师。合并3份独立探针结论为一份逆向推演报告。

## 合并规则
1. 互相支持的结论 → **高置信度**
2. 互相冲突 → ⚠️ **存在分歧**
3. 🔴 红蓝对抗检查: 每个维度必须包含魔鬼代言人挑战和存活强度标注。
   如某维度缺少，标注"⚠️ 红蓝对抗不完整"

## 报告格式

### 维度1: 核心假设脆弱性
- **论点**: [逆向分析核心判断]
- **魔鬼代言人挑战**: [最有力的反驳，附数据]
- **存活强度**: 强/中/弱 — [理由]

### 维度2: 两大失效测试
- **论点**: ...
- **魔鬼代言人挑战**: ...
- **存活强度**: 强/中/弱

### 维度3: 外部冲击与论点破裂
- **论点**: ...
- **魔鬼代言人挑战**: ...
- **存活强度**: 强/中/弱""",

        "investment_theme": """你是投资分析师。合并3份独立探针结论为一份投资主题报告。

## 合并规则: 同前

## 报告格式
### 一、核心叙事 (if-then命题, 50字以内)
### 二、变革证据链 (管理层叙事 + 硬数据印证 + 外部验证。含Serenity信息差标注)
### 三、关注度评估 (机构覆盖/媒体渗透/散户认知/市场偏见)
### 四、估值锚与信息差 (含Serenity: '用同环节可比市值，不要用P/E')
### 五、关键验证节点 (2-3个证实/证伪条件)""",

        "future": """你是催化剂分析师。合并3份独立探针结论为一份催化日历。

## 报告格式

| 预计时间 | 事件 | 证实条件 | 证伪条件 | 优先级 |
|---------|------|---------|---------|:------:|
| ... | ... | ... | ... | P0/P1/P2 |

P0 = 一票确认或一票否决

覆盖: 财报节点/产品里程碑/行业催化剂/产能节点/风险节点""",

        "event_deduction": """你是推演分析师。合并3份独立探针结论为一份事件推演报告。

## 报告格式

### T+30 (1个月)
- 最可能路径:
- 关键分叉点:
- 证实条件:
- 证伪条件:

### T+90 (3个月)
- 最可能路径:
- 关键分叉点:
- 证实条件:
- 证伪条件:

### T+180 (6个月)
- 最可能路径:
- 关键分叉点:
- 证实条件:
- 证伪条件:

### 论点破裂场景
- T+30/90/180的破裂路径，附转移概率

### 历史案例参考
- 类似事件的传导链和市场反应""",
    }

    merge_prompt = merge_prompts.get(field_name, merge_prompts["industry_expert_research"])

    messages = [
        {"role": "system", "content": merge_prompt},
        {
            "role": "user",
            "content": f"请基于3份独立探针结论，合并输出最终报告:\n\n{conclusions_text}",
        },
    ]

    resp = requests.post(
        DEEPSEEK_URL,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "deepseek-v4-flash",
            "temperature": 0,
            "max_tokens": 8192,
            "messages": messages,
            "thinking": {"type": "enabled"},
        },
        timeout=120,
    )

    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def main():
    start = time.time()

    # 1. 解析本字段的探针
    probes_map = json.loads(probes_map_raw)  # Coze注入
    field_probes = probes_map.get(field_name, [])

    if not field_probes:
        print("")  # 空输出
        return

    stock_info = (
        f"{stock_name}（{stock_code}）\n"
        f"事件背景: {news_content[:1500] if news_content else '无'}"
    )

    # 2. 并行执行3个探针
    probe_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                run_single_probe, p["name"], p["task"], stock_info
            ): p
            for p in field_probes
        }
        for future in concurrent.futures.as_completed(futures):
            probe_results.append(future.result())

    # 按原始顺序排序
    name_order = {p["name"]: i for i, p in enumerate(field_probes)}
    probe_results.sort(key=lambda x: name_order.get(x["name"], 99))

    # 3. 合并
    field_report = merge_probes(field_name, probe_results, stock_info)
    total_searches = sum(p["searches"] for p in probe_results)
    elapsed = time.time() - start

    # 4. 输出
    print(field_report)

    # 附加统计信息到stderr（Coze中不可见，仅调试用）
    import sys
    print(
        f"[{field_name}] 探针: {len(probe_results)} | "
        f"搜索: {total_searches} | "
        f"耗时: {elapsed:.0f}s | "
        f"报告: {len(field_report)}c",
        file=sys.stderr,
    )


# Coze Code节点入口
main()
