"""N5: 事件推演 — 3 层因果递进

第1轮: 事件机理（传导链拆解 + 与 N1/N2 关系 + 不确定性清单）
第2轮: 深度追问（回答第1轮的不确定性 + 量化数据 + 历史参照 + 多方博弈）
第3轮: 终判（断裂点 + 历史证伪 + 预警信号 + 综合报告）
"""

import json
import re
import time

from .field_runner import call_deepseek as _call_deepseek, volc_search, CURRENT_DATE


def call_deepseek(system: str, user: str, max_tokens: int = 4096, **kw) -> str:
    """N5 事件推演统一用 thinking=False — 忠实于搜索结果，避免幻觉。"""
    return _call_deepseek(system, user, max_tokens=max_tokens, thinking=False)


# ══════════════════════════════════════════════════════
# 第1轮: 事件机理
# ══════════════════════════════════════════════════════

ROUND1_SYSTEM = """你是事件推演分析师。N1已讲清楚股票本质和核心叙事。N2已讲清产业链位置。

不要做量化估算。数字留给下一轮。你的输出是下一轮深挖的起点。

## 你的任务：第一轮——事件机理

你的目标是画清楚传导链，不是给出最终结论。

搜这个事件的产业背景和触发原因。只搜索一次，使用火山联网问答。一次性调用覆盖三个问题：

1. 传导链拆解——事件→哪个业务环节先受影响→这个环节受影响的具体机制是什么（搜事实支撑，不是自己推理因果）→下一步传到哪→最终落到什么财务指标上？每一步标注你搜到了什么、没搜到什么。

2. 和已有判断的关系——事件是强化还是动摇了N1的核心叙事？是验证还是挑战了N2的竞争判断？引用N1/N2的具体表述做对比。

3. 关键不确定性——传导链的每一步，最不确定的是什么？哪个环节信息缺口最大？把你的不确定性清单交给下一轮。

## 输出格式

### 传导链
事件 → [环节1] → [环节2] → ... → 财务指标
每一步: 机制是什么 | 搜到了什么 | 没搜到什么

### 与N1/N2的关系
- 对N1核心叙事: 强化/动摇 — [引用N1原文对比]
- 对N2竞争判断: 验证/挑战 — [引用N2原文对比]

### 不确定性清单
1. [最不确定的环节] — 缺什么信息
2. [次不确定的环节] — 缺什么信息
3. ..."""


def run_round1(
    stock_name: str,
    stock_code: str,
    news_content: str,
    n1_report: str,
    n2_report: str,
    extra_context: str = "",
    verbose: bool = True,
) -> dict:
    """第1轮: 事件机理 — 传导链拆解 + 不确定性清单"""
    if verbose:
        print(f"\n[N5 第1轮] 事件机理...")

    # 构建搜索 query
    search_query = f"""[当前日期: {CURRENT_DATE}]

搜索以下事件的产业背景和触发原因，一次性覆盖三个问题：

事件: {news_content}
公司: {stock_name}（{stock_code}）
{extra_context}

问题1: 传导链拆解——这个事件→哪个业务环节先受影响→这个环节受影响的具体机制是什么→下一步传到哪→最终落到什么财务指标上？每一步标注搜到了什么、没搜到什么。

问题2: 这个事件是强化还是动摇了以下投资叙事？引用原文对比:
{n1_report}

问题3: 这个事件是验证还是挑战了以下产业链判断？引用原文对比:
{n2_report}

每个关键数据标注来源（域名+日期），无法追溯来源的数字不得写入。列出相关数据附来源。"""

    # 火山搜索
    search_result = volc_search(search_query)

    # LLM 分析
    analysis = call_deepseek(
        system=ROUND1_SYSTEM,
        user=f"""[当前日期: {CURRENT_DATE}]

## 事件
{news_content}
{extra_context}

## N1 投资主题报告
{n1_report}

## N2 产业链研究报告
{n2_report}

## 搜索结果
{search_result}

请按输出格式完成第1轮分析。""",
        max_tokens=8192,
    )

    if verbose:
        print(f"  [第1轮] 完成: {len(analysis)}c")

    return {
        "search_result": search_result,
        "analysis": analysis,
    }


# ══════════════════════════════════════════════════════
# 第2轮: 深度追问
# ══════════════════════════════════════════════════════

ROUND2_SYSTEM = """你是事件推演分析师。第1轮已经画出了事件传导链并标出了关键不确定性。你的任务是用一次结构化搜索回答这些不确定性。

你的搜索工具是单次同步搜索——你需要把想搞清楚的所有问题整合成一个结构化的完整query，一次扔进去。不是分散的关键词，而是一份包含所有维度的搜索指令。

你的单次搜索需要同时覆盖：
1. 量化数据——对影响最大的环节，要求返回具体数字
2. 历史参照——要求返回公司或同行面对类似事件的历史结果
3. 多方博弈——要求返回同行反应和上下游动作
4. 不确定性更新——要求标注哪些信息置信度高、哪些仍模糊

基于单次搜索返回的结果，输出你的分析。搜不到就说没搜到，不要补搜。不要重复第1轮已有的内容。

## 输出格式

### 量化数据
[具体数字，注明来源]

### 历史参照
[类似事件的历史结果]

### 多方博弈
[同行反应、上下游动作]

### 不确定性更新
[哪些信息置信度高、哪些仍模糊]"""


def run_round2(
    stock_name: str,
    stock_code: str,
    round1_result: dict,
    extra_context: str = "",
    verbose: bool = True,
) -> dict:
    """第2轮: 深度追问 — 回答不确定性"""
    if verbose:
        print(f"\n[N5 第2轮] 深度追问...")

    # 从第1轮提取不确定性清单
    uncertainty_text = round1_result["analysis"]

    # 构建搜索 query
    search_query = f"""[当前日期: {CURRENT_DATE}]

基于以下不确定性清单，一次性搜索所有维度的数据：

{uncertainty_text}

公司: {stock_name}（{stock_code}）
{extra_context}

要求:
1. 对影响最大的环节，返回具体数字（产能/价格/市占率/营收等）
2. 返回公司或同行面对类似事件的历史结果
3. 返回同行反应和上下游动作
4. 标注哪些信息置信度高、哪些仍模糊

每个关键数据标注来源（域名+日期），无法追溯来源的数字不得写入。列出相关数据附来源。"""

    # 火山搜索
    search_result = volc_search(search_query)

    # LLM 分析
    analysis = call_deepseek(
        system=ROUND2_SYSTEM,
        user=f"""[当前日期: {CURRENT_DATE}]

## 第1轮分析
{round1_result['analysis']}

## 搜索结果
{search_result}

请按输出格式完成第2轮分析。""",
        max_tokens=8192,
    )

    if verbose:
        print(f"  [第2轮] 完成: {len(analysis)}c")

    return {
        "search_result": search_result,
        "analysis": analysis,
    }


# ══════════════════════════════════════════════════════
# 第3轮: 终判
# ══════════════════════════════════════════════════════

ROUND3_SYSTEM = """你是事件推演分析师。前两轮已经完成了传导链拆解和深度追问。你的任务是第三轮终判，输出完整的事件推演报告。

你的搜索工具是单次同步搜索——你需要把想搞清楚的所有问题整合成一个结构化的完整query，一次扔进去：
1. 这个事件驱动逻辑最可能在哪个环节断裂
2. 历史上类似事件→类似叙事被证伪的案例
3. 当前有没有出现类似的早期预警信号

然后综合三轮的发现，输出完整报告。

## 输出格式

### 一、事件传导链

[事件→每个业务环节→财务指标，每一步的机制和依据。标注搜到的信息和仍然缺失的信息。]

### 二、关键发现

[第二轮深挖得到的最重要的发现。量化数据（注明来源）。历史案例。多方博弈的结果。]

### 三、脆弱性与证伪

[最可能断裂的环节。历史证伪案例。当前预警信号。什么条件发生→事件驱动逻辑不成立？]

### 四、与市场共识的对照

[这个事件的分析结论，与当前市场主流叙事和产业竞争判断相比：哪些一致——事件验证了市场已经相信的东西；哪些超出——事件带来了市场尚未充分消化的新信息；哪些矛盾——事件分析指向了和市场共识相反的方向。]

### 五、瓶颈节点

在输出完整报告之前，先审视三轮分析的结论。传导链中如果有某个环节是"不突破就无法兑现"的硬约束——不是增速放缓这种软风险，而是物理层面或结构层面锁死了后续传导——这就是瓶颈节点。
如果存在这样的瓶颈节点，按以下格式输出（直接对接 Baseline 脆弱点分析）：
- **环节名称**: [具体环节]
- **假设内容**: [什么前提成立故事才能继续]
- **反面证据**: [什么事实会动摇这个假设]
- **降级条件**: [观察到什么信号说明脆弱点正在被激活]
- **反身性风险**: [股价本身的涨跌会不会改变基本面]
- **量化边界**: [产能/时间/供应量的具体上限]
- **突破路径**: [有没有可见的突破路径]
如果不存在，写"无明确瓶颈节点"。

## ⚠️ 质量控制规则（必须遵守）

### 规则1: 事实性矛盾必须裁决

当你在多轮搜索中对同一事实问题（如"竞争对手是否已量产""市占率具体数字"）得到矛盾答案时：

- 比较信息来源的**时效性**（更新 > 更旧）、**可靠性**（官方公告 > 媒体报道 > 行业推测）、**具体性**（有数字 > 只有定性描述）
- **选择更可信的版本作为报告的基准判断**
- 在报告中明确写出裁决理由和被否决版本的内容
- 如果两个来源都无法确认为可靠 → 标注"⚠️ 关键事实不确定: [描述矛盾] [需补充: 具体缺什么信息]"

禁止行为: 只写"A来源说X，B来源说Y，存在矛盾"然后跳到下一个话题。这不是裁决，这是把矛盾丢给下游。

### 规则2: 数字必须有源

任何具体数字（百分比/金额/产能/市占率等）必须注明信息来源。
- 来自搜索 → 标注域名+日期
- 来自输入数据 → 标注字段名
- 无法追溯来源的数字 → 不得写入报告

禁止行为: "35%关键设备依赖美国进口""国内市占率约85%"这类无源数字。

### 规则3: 矛盾处理集中化

不要在报告的多个章节重复描写同一个矛盾。所有"信息矛盾与裁决"集中放在"关键发现"章节的"⚠️ 信息矛盾与裁决"小节中。其他章节只陈述裁决后的结论。"""


def run_round3(
    stock_name: str,
    stock_code: str,
    round1_result: dict,
    round2_result: dict,
    extra_context: str = "",
    verbose: bool = True,
) -> dict:
    """第3轮: 终判 — 断裂点 + 历史证伪 + 综合报告"""
    if verbose:
        print(f"\n[N5 第3轮] 终判...")

    # 构建搜索 query
    search_query = f"""[当前日期: {CURRENT_DATE}]

基于以下分析，搜索三个问题：

1. 这个事件驱动逻辑最可能在哪个环节断裂？
2. 历史上类似事件→类似叙事被证伪的案例
3. 当前有没有出现类似的早期预警信号

公司: {stock_name}（{stock_code}）
{extra_context}

前两轮分析摘要:
{round1_result['analysis']}
{round2_result['analysis']}

每个关键数据标注来源（域名+日期），无法追溯来源的数字不得写入。列出相关数据附来源。"""

    # 火山搜索
    search_result = volc_search(search_query)

    # LLM 综合报告
    report = call_deepseek(
        system=ROUND3_SYSTEM,
        user=f"""[当前日期: {CURRENT_DATE}]

## 第1轮分析
{round1_result['analysis']}

## 第2轮分析
{round2_result['analysis']}

## 第3轮搜索结果
{search_result}

请综合三轮发现，输出完整的事件推演报告。""",
        max_tokens=8192,
    )

    if verbose:
        print(f"  [第3轮] 完成: {len(report)}c")

    return {
        "search_result": search_result,
        "report": report,
    }


# ══════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════

def run_event_deduction(
    stock_name: str,
    stock_code: str,
    news_content: str,
    n1_report: str,
    n2_report: str,
    n3_report: str = "",
    knowledge: str = "",
    step_one: str = "",
    company_profile: str = "",
    verbose: bool = True,
) -> str:
    """N5 事件推演 — 3 层因果递进。

    Args:
        stock_name: 股票名称
        stock_code: 股票代码
        news_content: 原始事件
        n1_report: N1 投资主题报告
        n2_report: N2 产业链研究报告
        n3_report: N3 逆向推演报告（可选）
        knowledge: 知识补充
        step_one: 初步分析
        company_profile: N0.5 公司前置认知
        verbose: 打印进度

    Returns:
        事件推演报告 (Markdown)
    """
    t_start = time.time()

    if verbose:
        print(f"\n[N5 事件推演] 3层因果递进...")

    # 构建补充上下文
    extra_context = ""
    if company_profile:
        extra_context += f"\n\n## 公司基本认知\n{company_profile}"
    if knowledge and str(knowledge).strip():
        extra_context += f"\n\n## 知识补充\n{str(knowledge)}"
    if step_one and str(step_one).strip():
        extra_context += f"\n\n## 初步分析\n{str(step_one)}"

    # 第1轮: 事件机理
    r1 = run_round1(stock_name, stock_code, news_content, n1_report, n2_report, extra_context, verbose)

    # 第2轮: 深度追问
    r2 = run_round2(stock_name, stock_code, r1, extra_context, verbose)

    # 第3轮: 终判
    r3 = run_round3(stock_name, stock_code, r1, r2, extra_context, verbose)

    elapsed = time.time() - t_start
    if verbose:
        print(f"\n[N5 事件推演] 完成: {elapsed:.0f}s {len(r3['report'])}c")

    return r3["report"]
