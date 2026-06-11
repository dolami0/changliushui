"""第2层: 探针分配 Agent。

根据事件类型和初版语料，为4个字段各动态生成深化探针query和总结格式。
"""

import json
import requests
from typing import TypedDict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_config import DEEPSEEK_API_KEY as DEEPSEEK_KEY
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

from .prompts import PROBE_ALLOCATOR_PROMPT


class ProbeAllocation(TypedDict):
    """单个字段的探针分配"""
    probes: list[str]  # 探针 query 列表
    output_format: str  # 总结格式描述


class AllocationResult(TypedDict):
    """探针分配结果"""
    industry_expert_research: ProbeAllocation
    adversarial_thinking: ProbeAllocation
    future: ProbeAllocation
    event_deduction: ProbeAllocation


# ── 事件类型 → 探针生成指令 ──

EVENT_PROBE_TEMPLATES = {
    "创新药管线": {
        "industry_expert_research": [
            "{stock_name}的{核心管线名称}适应症市场空间(TAM) — 患者基数 × 渗透率 × 定价",
            "{stock_name} {核心管线名称} 峰值销售预测 — 券商一致预期范围",
            "{核心管线} 竞品管线对比 — {竞品1}/{竞品2}/{竞品3}的临床阶段和差异化",
            "同类药物临床成功率参考 — {适应症}从Phase2到获批的历史概率",
        ],
        "adversarial_thinking": [
            "{核心管线} 临床数据风险 — 同类靶点的失败案例和原因",
            "FDA/NMPA 对{适应症}的审批要求 — 临床终点标准",
            "{核心管线} 专利悬崖风险 — 专利到期时间和仿制药威胁",
            "竞品首发优势 — {竞品}是否可能先于{stock_name}获批",
        ],
        "future": [
            "{核心管线} 临床数据读出节点 — 预计时间和会议",
            "{核心管线} NDA/BLA提交时间 — 公司指引和行业惯例",
            "PDUFA日期 / NMPA审批决定日",
            "商业化首年 — 医保谈判窗口和定价策略",
        ],
        "event_deduction": [
            "同类药物审批先例 — {参考药物}的审批时间线和市场反应",
            "上市后放量曲线参考 — {参考药物}首年/次年销售额",
            "医保谈判时间窗口 — 影响定价和放量的关键节点",
        ],
    },
    "大宗商品/供需": {
        "industry_expert_research": [
            "{商品名} 供给端变化因素 — 主要产能、检修计划、进口量变化",
            "{商品名} 需求端变化因素 — 下游行业开工率、新增需求来源",
            "{商品名} 供需缺口量化 — 当前缺口多少吨/月，未来扩大还是缩小",
            "{商品名} 库存周期位置 — 社会库存/港口库存/下游库存天数",
            "{商品名} 替代品经济性分析 — 价差水平和使用比例变化",
        ],
        "adversarial_thinking": [
            "{商品名} 供给恢复的触发条件 — 哪些产能即将投产/复产",
            "{商品名} 需求崩塌的风险 — 下游什么情况下会大幅减少采购",
            "政策干预风险 — 抛储/限价/进出口关税调整的可能性",
            "替代品加速渗透 — 价差达到什么水平会触发大规模替代",
        ],
        "future": [
            "{商品名} 新增产能投产时间表 — 具体项目、产能规模、投产日期",
            "{商品名} 季节性需求变化 — 旺季/淡季的时间和量级",
            "政策干预窗口 — 发改委/商务部可能出手的时间点",
            "替代品商业化节点 — 新技术/新材料何时量产替代",
        ],
        "event_deduction": [
            "{商品名} 历史价格周期参考 — 上一轮涨价的幅度和持续时间",
            "下游补库/去库周期 — 当前处于什么阶段，预计何时反转",
            "期货远期曲线解读 — contango/backwardation 结构含义",
        ],
    },
    "科技突破": {
        "industry_expert_research": [
            "{技术名} 技术壁垒深度 — 专利/工艺/人才/资金门槛",
            "{技术名} 产业化时间表 — 从实验室到量产的关键节点",
            "产业链替代风险 — 新技术对旧技术的替代速度和范围",
            "客户导入周期 — 从验证到批量采购需要多长时间",
        ],
        "adversarial_thinking": [
            "技术路线分歧 — 是否有竞争技术可能颠覆{技术名}",
            "核心专利风险 — 专利归属和到期时间",
            "人才流失风险 — 核心技术团队的稳定性",
            "下游客户自研风险 — 大客户是否有能力自主研发替代",
        ],
        "future": [
            "{技术名} 量产里程碑 — 良率爬坡/产能建设/客户验证节点",
            "行业标准制定节点 — 3GPP/ITU/IEEE等标准组织的讨论时间",
            "竞品技术进展 — 竞争对手的技术路线和量产时间",
            "下游应用爆发节点 — 哪些客户/场景会率先大规模采用",
        ],
        "event_deduction": [
            "技术渗透S曲线 — 类似技术在历史上的渗透速度参考",
            "先发者优势窗口 — 先发优势能保持多长时间",
            "生态建设进度 — 上下游配合和开发者生态的建立速度",
        ],
    },
    "产能扩张": {
        "industry_expert_research": [
            "{stock_name} 产能扩张计划 — 具体项目、投资额、设计产能",
            "产能爬坡节奏 — 从投产到达产的时间和各阶段产能",
            "下游吸收能力 — 新增产能能否被需求消化，行业供需预测",
            "竞争对手响应 — 同行是否也在扩产，行业总产能变化趋势",
        ],
        "adversarial_thinking": [
            "产能过剩风险 — 如果需求增速不及预期，产能利用率会降到什么水平",
            "资金压力风险 — 扩产项目的资金来源、负债率变化",
            "技术换代风险 — 新建产线是否会被新技术淘汰",
            "客户订单匹配风险 — 如果没有足够订单，固定成本如何消化",
        ],
        "future": [
            "产能投产时间表 — 各期项目预计投产日期",
            "产能认证节点 — 客户验厂/产品认证时间",
            "产能利用率跟踪 — 投产后逐月/逐季利用率变化",
            "成本优化节点 — 规模效应何时开始显现",
        ],
        "event_deduction": [
            "产能扩张周期参考 — 同类项目从开工到达产的历史周期",
            "行业供需平衡推演 — 全行业产能 vs 需求的时间线",
            "利润率变化推演 — 产能爬坡期间毛利率的典型走势",
        ],
    },
    "竞争格局变化": {
        "industry_expert_research": [
            "{行业} 市场份额最新排名 — 各玩家份额和变化趋势",
            "进入壁垒分析 — 技术/资金/客户/规模壁垒的高度",
            "定价权变化 — 行业定价模式、价格战的可能性",
            "客户切换成本 — 下游客户换供应商的成本和意愿",
        ],
        "adversarial_thinking": [
            "市场份额被侵蚀的风险 — 哪些竞争对手最具威胁",
            "价格战爆发条件 — 什么情况下行业会开启价格战",
            "新进入者威胁 — 跨界玩家/新技术的威胁程度",
            "客户集中度风险 — 大客户流失的概率和影响",
        ],
        "future": [
            "行业整合节点 — 并购/重组/出清的预期时间",
            "新玩家入场节点 — 跨界玩家的产能/产品发布计划",
            "客户招标节点 — 大客户的下一次招标时间和规模",
            "行业标准变化 — 技术标准更新对竞争格局的影响",
        ],
        "event_deduction": [
            "行业集中度演变趋势 — CR3/CR5的历史变化和未来方向",
            "赢家通吃 vs 分散格局 — 行业最终会走向哪种结构",
            "定价权迁移路径 — 从上游/中游/下游谁的议价力在增强",
        ],
    },
    "政策驱动": {
        "industry_expert_research": [
            "{政策名} 核心条款解读 — 具体内容、实施时间、执行力度",
            "受益标的量化 — 哪些公司受益，收益规模多大",
            "行业影响范围 — 直接影响和间接影响的产业链环节",
        ],
        "adversarial_thinking": [
            "政策执行风险 — 政策落地可能打折扣的地方",
            "政策退出风险 — 补贴/优惠政策何时退出，退出后的影响",
            "政策套利风险 — 企业是否过度依赖政策而非自身竞争力",
        ],
        "future": [
            "政策细节出台时间 — 实施细则/配套政策的发布时间",
            "政策效果验证节点 — 首次能看到政策效果的时点",
            "政策调整窗口 — 政策可能微调或加码的时点",
        ],
        "event_deduction": [
            "历史政策类比 — 类似政策在历史上的实施效果",
            "政策传导链 — 政策→行业→公司业绩的传导周期",
        ],
    },
}


def allocate_probes(
    event_type: str,
    stock_name: str,
    stock_code: str,
    ier1_content: str,
    theme_content: str,
    verbose: bool = True,
) -> AllocationResult:
    """根据事件类型和初版语料，为4个字段分配深化探针。

    Args:
        event_type: 事件类型（创新药管线/大宗商品/供需 等）
        stock_name: 股票名称
        stock_code: 股票代码
        ier1_content: industry_expert_research_1 内容
        theme_content: investment_theme 内容
        verbose: 是否打印进度

    Returns:
        AllocationResult — 每个字段的探针列表和总结格式
    """
    # 优先使用预定义模板
    if event_type in EVENT_PROBE_TEMPLATES:
        templates = EVENT_PROBE_TEMPLATES[event_type]

        if verbose:
            print(f"[ProbeAllocator] 使用预定义探针模板: {event_type}")

        # 填充模板中的变量
        def fill_template(probes: list[str]) -> list[str]:
            """用股票名和行业术语填充探针模板"""
            filled = []
            for p in probes:
                p = p.replace("{stock_name}", stock_name)
                p = p.replace("{stock_code}", stock_code)
                filled.append(p)
            return filled

        result = {}
        for field_name, field_templates in templates.items():
            result[field_name] = {
                "probes": fill_template(field_templates),
                "output_format": "按{field_name}的标准格式输出（参见对应System Prompt）",
            }

        return result  # type: ignore

    # 通用事件 → LLM 动态生成探针
    if verbose:
        print(f"[ProbeAllocator] LLM 动态生成探针: {event_type}")

    prompt = PROBE_ALLOCATOR_PROMPT.format(
        event_type=event_type,
        ier1_summary=ier1_content[:2000],
        theme_summary=theme_content[:2000],
    )

    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": (
                f"请为{stock_name}（{stock_code}）分配深化探针。\n"
                f"事件类型: {event_type}\n"
                f"为 industry_expert_research, adversarial_thinking, future, event_deduction "
                f"各生成3-5个具体探针query。"
            ),
        },
    ]

    r = requests.post(
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
        },
        timeout=60,
    )

    data = r.json()
    content = data["choices"][0]["message"]["content"]

    # 简单解析 LLM 输出（后续可改进为严格的 JSON 解析）
    allocation = {}
    current_field = None

    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("## "):
            field_name = line[3:].strip()
            # 映射中文到字段名
            mapping = {
                "industry_expert_research": "industry_expert_research",
                "adversarial_thinking": "adversarial_thinking",
                "future": "future",
                "event_deduction": "event_deduction",
            }
            for key, val in mapping.items():
                if key in field_name.lower() or field_name in ["行业分析", "产业链", "产业"]:
                    current_field = "industry_expert_research"
                elif "逆向" in field_name or "风险" in field_name or "adversarial" in field_name.lower():
                    current_field = "adversarial_thinking"
                elif "催化剂" in field_name or "节点" in field_name or "future" in field_name.lower():
                    current_field = "future"
                elif "推演" in field_name or "event" in field_name.lower():
                    current_field = "event_deduction"

            if current_field:
                allocation[current_field] = {"probes": [], "output_format": ""}

        elif line.startswith(("1.", "2.", "3.", "4.", "5.", "- ")) and current_field:
            allocation[current_field]["probes"].append(line.lstrip("0123456789. -").strip())

    # 确保所有4个字段都有探针
    for field in ["industry_expert_research", "adversarial_thinking", "future", "event_deduction"]:
        if field not in allocation:
            allocation[field] = {"probes": ["未分配探针"], "output_format": "标准格式"}

    if verbose:
        for field, alloc in allocation.items():
            print(f"  [{field}] {len(alloc['probes'])} 个探针")

    return allocation  # type: ignore
