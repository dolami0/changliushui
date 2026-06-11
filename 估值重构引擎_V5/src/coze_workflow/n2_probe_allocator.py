"""N2 [Code] 探针分配
Coze Code节点 — Python 3

输入变量: event_type, bottleneck_flag, stock_name, stock_code
输出变量: probes_map (JSON字符串)

5字段 × 3探针 = 15个探针。通用事件用默认模板，瓶颈事件用特化模板。
"""

import json

# ═══════════════════════════════════════════════
# 探针模板库
# {stock} 会被替换为 "stock_name（stock_code）"
# ═══════════════════════════════════════════════

PROBE_TEMPLATES = {
    "通用": {
        "industry_expert_research": [
            {
                "name": "产业链位置+需求确定度",
                "task": (
                    "{stock}在产业链的哪一层？紧邻上游供应商是谁？下游客户是谁？"
                    "下游需求确定性多高——有长期合同/政策锁定/物理约束吗？"
                    "终端需求来自哪个已验证的大趋势？"
                ),
            },
            {
                "name": "供给格局+价值捕获",
                "task": (
                    "{stock}所在环节，全球有几家能做？公司在其中排第几？"
                    "新进入者需要多少年？认证周期多长？公司涨过价吗？"
                    "毛利率趋势怎样？客户切换成本多大？"
                ),
            },
            {
                "name": "卡点检查+反方证据",
                "task": (
                    "用4条标准检查{stock}是不是卡点："
                    "(1)人人都需要它的产品吗？"
                    "(2)供给高度集中+多年难扩产？"
                    "(3)公司市值vs下游BOM是否错配？"
                    "(4)会被大客户垂直整合绕过吗？"
                    "同时找反方证据：技术替代/客户流失/新进入者威胁。"
                ),
            },
        ],
        "adversarial_thinking": [
            {
                "name": "核心假设脆弱性(红蓝对抗)",
                "task": (
                    "市场对{stock}最乐观的预期是什么？建立在什么假设上？"
                    "这个假设最容易被什么证伪？"
                    "🔴执行魔鬼代言人挑战：扮演最恶意的反对者，"
                    "找出至少2个有数据支撑的反驳点。标注论点存活强度(强/中/弱)。"
                ),
            },
            {
                "name": "两大失效测试(红蓝对抗)",
                "task": (
                    "测试{stock}的论点是否可能失效："
                    "(a)会被大客户垂直整合绕过吗(designed-out)？参考POET案例——MRVL取消采购跌46%。"
                    "(b)卡点收入够material吗(体量太小即使卡也带动不了股价)？"
                    "🔴魔鬼代言人挑战→标注存活强度。"
                ),
            },
            {
                "name": "外部冲击+论点破裂(红蓝对抗)",
                "task": (
                    "哪些不可控因素可能颠覆{stock}的叙事？政策/技术替代/地缘政治/宏观周期？"
                    "什么条件发生时投资论点彻底破裂？"
                    "Serenity原话：'论点变即砍仓甚至反手做空'。"
                    "🔴魔鬼代言人挑战→标注存活强度。"
                ),
            },
        ],
        "investment_theme": [
            {
                "name": "管理层叙事+硬数据",
                "task": (
                    "{stock}管理层怎么描述变革和战略？"
                    "分产品收入结构变化和毛利率趋势如何印证管理层叙事？"
                ),
            },
            {
                "name": "市场预期+关注度评估",
                "task": (
                    "{stock}覆盖券商几家？主流媒体报道频率？雪球讨论热度？"
                    "券商一致预期是什么？市场偏见在哪？"
                    "是否属于Serenity说的'机构不能买(市值<$1B)'"
                    "或'散户100%负面=反向信号'的情况？"
                ),
            },
            {
                "name": "估值锚+信息差",
                "task": (
                    "{stock}当前估值隐含什么假设？"
                    "如果叙事兑现/落空，估值锚会怎么迁移？"
                    "有什么信息是市场还没充分消化的？"
                    "Serenity: '用同环节可比市值，不要用P/E。'"
                ),
            },
        ],
        "future": [
            {
                "name": "财报+产品里程碑",
                "task": (
                    "{stock}下次季报/年报预估时间？市场一致预期？"
                    "关键产品的量产时间表/客户验证进度/产能爬坡节点？"
                ),
            },
            {
                "name": "催化剂(Serenity视角)",
                "task": (
                    "{stock}有没有资格认证周期拐点(qualification cycle inflection)？"
                    "产能从投产到达产要多长时间？什么时候规模效应开始显现？"
                    "行业展会/客户产品发布/政策节点？"
                    "Serenity: 'Nobody cares about current earnings — watch the qualification cycle.'"
                ),
            },
            {
                "name": "风险节点",
                "task": (
                    "{stock}未来6-12个月可能打断叙事的负面事件？"
                    "解禁日？减持窗口？竞品发布日期？客户流失信号？"
                ),
            },
        ],
        "event_deduction": [
            {
                "name": "T+30/T+90推演",
                "task": (
                    "基于当前事件，{stock}短期(1月)和中期(3月)最可能的市场路径？"
                    "关键分叉点在哪？什么财务指标会验证/证伪叙事？"
                ),
            },
            {
                "name": "T+180推演+历史案例",
                "task": (
                    "{stock}长期(6月)叙事定型或重构方向？估值体系会切换吗？"
                    "搜索类似处境的历史案例——类似事件引发了什么传导链？市场如何反应？"
                ),
            },
            {
                "name": "论点破裂推演(Serenity)",
                "task": (
                    "如果{stock}的投资论点被证伪，传导链会怎样？"
                    "推演论点破裂的T+30/90/180场景。"
                    "参考Serenity风控：'如果卡点被设计绕过→清仓或反手做空'。"
                    "标注转移概率。"
                ),
            },
        ],
    },
    "瓶颈发现": {
        "industry_expert_research": [
            {
                "name": "需求确定度(瓶颈视角)",
                "task": (
                    "{stock}的下游需求来自哪个已验证的大趋势？"
                    "确定性来源是什么(已签合同/政策强制/物理定律约束)？"
                    "下游客户的CapEx计划和订单可见度如何？这个需求能持续多少年？"
                ),
            },
            {
                "name": "供给刚性(瓶颈视角)",
                "task": (
                    "{stock}所处环节的全球CR3集中度？新进入者认证要多少年？良率水平？"
                    "有没有'唯一供应商'或'不可替代'的情况？"
                    "这个环节是不是全产业链最短的那块板？"
                ),
            },
            {
                "name": "卡点量化检查",
                "task": (
                    "定量检查{stock}：(1)全球市占率？(2)认证周期多少年？"
                    "(3)同环节可比公司市值对比？(4)下游BOM占比？"
                    "(5)产能扩张需要多少年？给出真瓶颈/伪瓶颈的判断和理由。"
                ),
            },
        ],
        "adversarial_thinking": [
            {
                "name": "伪瓶颈风险(红蓝对抗)",
                "task": (
                    "{stock}的瓶颈地位可能是伪命题吗？替代技术路线是否存在？"
                    "客户有没有自研能力和动机？新产能会不会超预期释放？"
                    "🔴魔鬼代言人挑战→存活强度。"
                ),
            },
            {
                "name": "两大失效测试(红蓝对抗)",
                "task": (
                    "(a){stock}会被大客户垂直整合绕过吗？"
                    "(b)卡点够material吗——即使卡住，对股价的拉动够大吗？"
                    "参考Serenity做的POET(designed-out)和HIMX(not material)。"
                    "🔴魔鬼代言人挑战→存活强度。"
                ),
            },
            {
                "name": "瓶颈演变+外部冲击(红蓝对抗)",
                "task": (
                    "{stock}的瓶颈在变紧还是变松？观察指标是什么？"
                    "政策(出口管制/补贴)、技术路线切换、地缘政治，"
                    "哪个最可能动摇瓶颈地位？🔴魔鬼代言人挑战→存活强度。"
                ),
            },
        ],
    },
}

# ═══════════════════════════════════════════════
# 主逻辑
# ═══════════════════════════════════════════════

# Coze Code节点中，这些变量由上游节点注入
# event_type, bottleneck_flag, stock_name, stock_code

# 1. 选模板
templates = PROBE_TEMPLATES.get(event_type, PROBE_TEMPLATES["通用"]).copy()
# 深拷贝，避免修改原始模板
templates = {k: [dict(p) for p in v] for k, v in templates.items()}

# 2. 瓶颈事件 → 覆盖 industry 和 adversarial
bottleneck_templates = PROBE_TEMPLATES.get("瓶颈发现", {})
if bottleneck_flag == "true" or event_type == "瓶颈发现":
    for field in ["industry_expert_research", "adversarial_thinking"]:
        if field in bottleneck_templates:
            templates[field] = [dict(p) for p in bottleneck_templates[field]]

# 3. 填充变量
stock = f"{stock_name}（{stock_code}）"
probes_map = {}
for field, probes in templates.items():
    probes_map[field] = []
    for p in probes:
        probes_map[field].append({
            "name": p["name"],
            "task": p["task"].replace("{stock}", stock),
        })

# 4. 输出
output = json.dumps(probes_map, ensure_ascii=False)
print(output)
