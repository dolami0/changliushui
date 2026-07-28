"""N4: 催化日历 — 单次搜索 + 直接输出报告

与 N1/N2/N3 的"设计探针→执行→合并"模式不同，
N4 用一次火山搜索覆盖全部维度，LLM 直接输出催化日历。
"""

import time

from .field_runner import call_deepseek, volc_search, CURRENT_DATE


N4_SYSTEM = """你是催化剂分析师。N5已产出事件推演（传导链+证伪条件+瓶颈节点），N3已产出逆向推演（攻击报告+降级条件）。你的任务是编制一份催化日历。

使用火山联网搜索，将以下所有方向整合为一个结构化query，一次搜索覆盖全部维度：

搜索方向：
1. 公司财报节点——下次季报/年报预计时间、市场一致预期数字
2. 产品/技术里程碑——产能爬坡节点、客户认证/导入时间、新产品/技术平台发布时间
3. 行业与政策节点——行业展会/重要会议、政策窗口（审批/补贴/法规变化）
4. 风险节点——限售股解禁日期、大股东减持窗口、竞对产品发布可能冲击的时间
5. N5证伪条件和N3降级条件的触发监测点——把推演报告中的关键验证节点编入日历

最多搜索2次。搜完必须输出。

## 输出格式

### 最重要催化节点

一段话：未来6-12个月最重要的3个催化节点是什么、为什么。

### 催化日历表

| 预计时间 | 事件 | 类型 | 证实条件 | 证伪条件 | 优先级 | 信息来源 |
|----------|------|------|----------|----------|--------|----------|

类型选：财报/产品/行业/风险/验证
P0 = 一票确认或一票否决。P1 = 重要。P2 = 关注。

### 日历风险提示

一段话：最大的日历风险是什么——某个月没有催化、某段时间连续负面事件密集、最关键的节点可能被延迟。"""


def run_future(
    stock_name: str,
    stock_code: str,
    news_content: str = "",
    n1_report: str = "",
    n2_report: str = "",
    n3_report: str = "",
    n5_report: str = "",
    company_profile: str = "",
    verbose: bool = True,
) -> str:
    """N4 催化日历。

    Args:
        stock_name: 股票名称
        stock_code: 股票代码
        news_content: 原始事件
        n1_report: N1 投资主题报告
        n2_report: N2 产业链研究报告
        n3_report: N3 逆向推演报告
        n5_report: N5 事件推演报告
        company_profile: N0.5 公司前置认知
        verbose: 打印进度

    Returns:
        催化日历报告 (Markdown)
    """
    t_start = time.time()

    if verbose:
        print(f"\n[N4 催化日历] 开始...")

    # 构建搜索 query
    search_query = f"""[当前日期: {CURRENT_DATE}]

搜索以下公司的催化日历信息，一次性覆盖全部维度：

公司: {stock_name}（{stock_code}）

搜索方向：
1. 公司财报节点——下次季报/年报预计时间、市场一致预期数字
2. 产品/技术里程碑——产能爬坡节点、客户认证/导入时间、新产品/技术平台发布时间
3. 行业与政策节点——行业展会/重要会议、政策窗口（审批/补贴/法规变化）
4. 风险节点——限售股解禁日期、大股东减持窗口、竞对产品发布可能冲击的时间

公司背景:
{company_profile}

N5 事件推演中的证伪条件和瓶颈节点:
{n5_report}

N3 逆向推演中的降级条件:
{n3_report}

列出相关数据附来源。"""

    # 第1次搜索
    if verbose:
        print(f"  [N4] 第1次搜索...")
    search_result_1 = volc_search(search_query)

    # 第2次搜索（如果第1次结果不足）
    search_result_2 = ""
    if len(search_result_1) < 500 or search_result_1.startswith("[火山]"):
        if verbose:
            print(f"  [N4] 第1次结果不足，补搜...")
        search_result_2 = volc_search(f"""[当前日期: {CURRENT_DATE}]

搜索{stock_name}（{stock_code}）的财报披露日程、产能爬坡时间表、客户认证进展、限售股解禁日期。

列出相关数据附来源。""")

    all_results = search_result_1
    if search_result_2:
        all_results += f"\n\n---\n\n{search_result_2}"

    # LLM 输出报告
    report = call_deepseek(
        system=N4_SYSTEM,
        user=f"""[当前日期: {CURRENT_DATE}]

## 公司: {stock_name}（{stock_code}）

## 原始事件
{news_content}

## N0.5 公司基本认知
{company_profile}

## N1 投资主题报告
{n1_report}

## N2 产业链研究报告
{n2_report}

## N3 逆向推演报告
{n3_report}

## N5 事件推演报告
{n5_report}

## 搜索结果
{all_results}

请输出催化日历报告。""",
        max_tokens=8192,
    )

    elapsed = time.time() - t_start
    if verbose:
        print(f"[N4 催化日历] 完成: {elapsed:.0f}s {len(report)}c")

    return report
