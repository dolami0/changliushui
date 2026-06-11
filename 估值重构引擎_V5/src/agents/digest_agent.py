"""第1层: 事件消化 Agent。

读取天机卷数据，生成:
1. 事件类型判定
2. industry_expert_research_1 (通用5探针)
3. investment_theme (通用5探针)
"""

import time
from typing import TypedDict

from .field_agent import run_field_agent
from .prompts import DIGEST_INDUSTRY_PROMPT, DIGEST_THEME_PROMPT
from .tools import TOOL_DEFINITIONS


class DigestResult(TypedDict):
    """事件消化结果"""
    event_type: str
    industry_expert_research_1: dict
    investment_theme: dict
    total_searches: int
    total_elapsed: float


def detect_event_type(news_content: str, knowledge: str) -> str:
    """基于关键词判定事件类型。

    顺序检查，命中即返回。
    """
    text = (news_content + " " + knowledge).lower()

    # 创新药管线
    drug_keywords = [
        "管线", "临床试验", "nda", "bla", "靶点", "适应症", "adc",
        "单抗", "双抗", "car-t", "pd-1", "pdufa", "峰值销售",
        "gfr", "gfr",  # GLP-1 等
    ]
    if any(kw in text for kw in drug_keywords):
        return "创新药管线"

    # 大宗商品/供需
    commodity_keywords = [
        "涨价", "涨价潮", "供不应求", "缺货", "库存低位",
        "供需缺口", "供需矛盾", "产能不足", "供给收缩",
        "石油焦", "锂价", "铜价", "稀土", "电解铝",
    ]
    if any(kw in text for kw in commodity_keywords):
        return "大宗商品/供需"

    # 科技突破
    tech_keywords = [
        "技术突破", "首发", "量产", "制程", "迭代",
        "1.6t", "3.2t", "cpo", "硅光", "800g",
        "芯片", "光模块", "算力",
    ]
    if any(kw in text for kw in tech_keywords):
        return "科技突破"

    # 产能扩张
    capacity_keywords = [
        "扩产", "产能", "投产", "产线", "mwh", "gw",
        "万只", "万片", "吨",
    ]
    if any(kw in text for kw in capacity_keywords):
        return "产能扩张"

    # 竞争格局变化
    competition_keywords = [
        "市占率", "市场份额", "竞争", "格局", "份额",
        "对手", "竞品", "赶超", "反超",
    ]
    if any(kw in text for kw in competition_keywords):
        return "竞争格局变化"

    # 政策驱动
    policy_keywords = [
        "政策", "发改委", "工信部", "补贴", "监管",
        "审批", "国常会", "国务院",
    ]
    if any(kw in text for kw in policy_keywords):
        return "政策驱动"

    return "通用"


def run_digest(
    stock_name: str,
    stock_code: str,
    news_content: str,
    knowledge: str = "",
    step_one: str = "",
    tools: list[dict] | None = None,
    verbose: bool = True,
) -> DigestResult:
    """执行事件消化: 判定类型 + 生成初版语料。

    Args:
        stock_name: 股票名称
        stock_code: 股票代码
        news_content: 原始资讯 (strip HTML 后)
        knowledge: AI 深度研究结果
        step_one: Agent 0 初步分析
        tools: 可用工具定义
        verbose: 是否打印进度

    Returns:
        DigestResult
    """
    if tools is None:
        tools = TOOL_DEFINITIONS

    # 判定事件类型
    event_type = detect_event_type(news_content, knowledge)

    if verbose:
        print(f"[Digest] 事件类型: {event_type} | {stock_name}({stock_code})")
        print(f"[Digest] 开始 industry_expert_research_1 ...")

    # 构建上下文
    context = f"{stock_name}（{stock_code}）"
    if news_content:
        context += f"\n\n## 事件背景\n{news_content[:2000]}"
    if step_one:
        context += f"\n\n## 预研分析\n{step_one[:1000]}"
    if knowledge:
        context += f"\n\n## 知识补充\n{knowledge[:1000]}"

    # ── 生成 industry_expert_research_1 ──
    user_msg = (
        f"请为{context}\n\n"
        f"做行业结构分析。从探针1开始，不要直接写总报告。"
    )

    ier1_result = run_field_agent(
        system_prompt=DIGEST_INDUSTRY_PROMPT,
        user_message=user_msg,
        field_name="ier1",
        tools=tools,
        verbose=verbose,
    )

    if verbose:
        print(f"[Digest] industry_expert_research_1: {ier1_result['searches']}次搜索 {ier1_result['elapsed']:.0f}s {len(ier1_result['content'])}c")
        print(f"[Digest] 开始 investment_theme ...")

    # ── 生成 investment_theme ──
    user_msg_theme = (
        f"请为{context}\n\n"
        f"撰写投资主题报告。从探针1开始，不要直接写总报告。\n\n"
        f"## 参考: 初版行业分析\n{ier1_result['content'][:2000]}"
    )

    theme_result = run_field_agent(
        system_prompt=DIGEST_THEME_PROMPT,
        user_message=user_msg_theme,
        field_name="theme",
        tools=tools,
        verbose=verbose,
    )

    if verbose:
        print(f"[Digest] investment_theme: {theme_result['searches']}次搜索 {theme_result['elapsed']:.0f}s {len(theme_result['content'])}c")

    total_searches = ier1_result["searches"] + theme_result["searches"]
    total_elapsed = ier1_result["elapsed"] + theme_result["elapsed"]

    if verbose:
        print(f"[Digest] 完成: {total_searches}次搜索 {total_elapsed:.0f}s")

    return {
        "event_type": event_type,
        "industry_expert_research_1": ier1_result,
        "investment_theme": theme_result,
        "total_searches": total_searches,
        "total_elapsed": total_elapsed,
    }
