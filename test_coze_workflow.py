"""Coze工作流本地测试 v2 — 顺序推进 + 动态探针数
用法:
  python test_coze_workflow.py --mock    # Mock模式
  python test_coze_workflow.py           # 真实API (需要有效KEY)

架构:
  N1投资主题(3-6探针) → N2产业链(3-6探针, 读N1) → N3逆向(3-5探针, 读N1+N2)
  → N4催化(2-4探针, 读前三) → N5推演(2-4探针, 读前四) → N6总装 → N7写入
"""
import json, time, sys, io, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

MOCK_MODE = "--mock" in sys.argv

# ═══════════ 配置 ═══════════
STOCK_CODE, STOCK_NAME = "300308", "中际旭创"
NEWS_CONTENT = """中际旭创2026Q1营收194.96亿同比+192%，800G光模块出货放量，1.6T开始小批量供货。公司在CPO和硅光技术上持续投入研发，预计2026H2 1.6T大规模出货。管理层表示下游AI算力需求强劲。"""
STEP_ONE = "中际旭创是全球光模块龙头，受益AI算力。关注800G→1.6T迭代和CPO技术路线。"
KNOWLEDGE = ""

# ═══════════ 字段配置 ═══════════
FIELD_ORDER = [
    {"field": "investment_theme",         "prior": [],                                 "min_p": 3, "max_p": 6, "label": "投资主题"},
    {"field": "industry_expert_research", "prior": ["investment_theme"],                "min_p": 3, "max_p": 6, "label": "产业链"},
    {"field": "adversarial_thinking",     "prior": ["investment_theme", "industry_expert_research"], "min_p": 3, "max_p": 5, "label": "逆向推演"},
    {"field": "future",                   "prior": ["investment_theme", "industry_expert_research", "adversarial_thinking"], "min_p": 2, "max_p": 4, "label": "催化日历"},
    {"field": "event_deduction",          "prior": ["investment_theme", "industry_expert_research", "adversarial_thinking", "future"], "min_p": 2, "max_p": 4, "label": "事件推演"},
]

# ═══════════ Mock 探针设计(模拟LLM自由生成的探针) ═══════════
MOCK_PROBE_DESIGNS = {
    "investment_theme": {
        "probes": [
            {"name": "管理层叙事与战略方向", "task": "中际旭创2026Q1营收194.96亿(+192%)，管理层在最新季报/投资者交流中如何描述增长驱动力？800G→1.6T的产品迭代节奏和CPO/硅光技术路线的战略优先级如何？搜索最近季报电话会纪要和管理层公开表态。"},
            {"name": "800G/1.6T产品收入结构", "task": "中际旭创2026Q1的194.96亿营收中，800G和1.6T产品分别贡献多少？传统低速产品是否在萎缩？分产品毛利率趋势如何？搜索季报原文和券商分产品收入拆分。"},
            {"name": "券商覆盖与一致预期", "task": "中际旭创目前有多少家券商覆盖？2026全年营收和利润的一致预期是多少？最新研报的关键评级和逻辑是什么？搜索最近3个月的券商研报摘要。"},
            {"name": "机构持仓与市场关注度", "task": "中际旭创的机构持仓比例变化趋势？北向资金近期动向？雪球/东方财富讨论热度和情绪方向？是否属于Serenity说的'高关注度反而限制了信息差'的情况？"},
            {"name": "同环节可比公司估值", "task": "中际旭创当前市值vs Coherent/Fabrinet/新易盛等同环节可比公司？PS和EV/EBITDA对比？Serenity: 用同环节可比市值，不要用P/E。搜索可比公司最新市值和营收数据。"},
        ],
        "coverage_note": "覆盖管理层叙事/硬数据/市场预期/关注度/估值锚5个方向。事件中已有2026Q1营收数据，跳过纯财报数据验证。"
    },
    "industry_expert_research": {
        "probes": [
            {"name": "上游光芯片供应格局", "task": "投资主题报告指出中际旭创800G/1.6T的BOM中激光器(EML/CW DFB)成本占比最高。英伟达投资LITE和COHR各$2B锁定激光器产能——这是否意味着'瓶颈中的瓶颈'在上游激光器？中际旭创的激光器采购来源和供应安全如何？搜索LITE/COHR的EML产能规划和客户分配。"},
            {"name": "全球800G+光模块竞争格局", "task": "投资主题报告提出中际旭创800G市占率40%+。搜索验证: 全球800G+光模块的准确CR3(中际旭创/Coherent/Fabrinet)市场份额数据？新进入者(如新易盛/剑桥科技)的进展？客户认证壁垒到底有多高？"},
            {"name": "CPO对可插拔光模块的威胁", "task": "投资主题报告提到CPO和硅光是中际旭创面临的技术不确定性。搜索: 英伟达CPO原型进展和时间线、博通/Intel的硅光方案成熟度、CPO如果2028年量产对可插拔光模块市场的影响量化分析。"},
            {"name": "下游客户集中度与议价力", "task": "中际旭创的前五大客户是谁？占营收比例？是否存在单一客户依赖(如英伟达占比>50%)？客户是否有能力向后整合(自研光模块)？搜索年报前五大客户明细和客户集中度分析。"},
        ],
        "coverage_note": "投资主题已覆盖需求确定度方向，跳过。重点覆盖: 供给格局/卡点检查/技术替代风险/客户集中度。"
    },
    "adversarial_thinking": {
        "probes": [
            {"name": "🔴800G毛利率可持续性", "task": "产业链报告指出中际旭创800G OSFP ASP $800-1200高于同行15-20%，但这是否可持续？搜索: Coherent/Fabrinet的定价策略、800G光模块ASP历史趋势、客户(英伟达)是否有压价行为？执行红蓝对抗: 论点'ASP溢价可持续' → 魔鬼代言人挑战 → 存活强度(强/中/弱)。"},
            {"name": "🔴CPO替代时间线风险", "task": "产业链报告和投资主题都提到CPO是最大技术风险。搜索: 英伟达CPO交换机具体量产时间、Marvell/Broadcom的CPO ASIC路线图、可插拔光模块在CPO时代的角色(是否会被完全替代还是共存)。红蓝对抗: 论点'CPO短期内不会威胁可插拔' → 挑战 → 存活强度。"},
            {"name": "🔴论点破裂条件", "task": "综合前序报告，中际旭创的核心if-then命题是'AI算力需求持续 → 800G/1.6T出货放量 → 市占率+定价权维持 → 利润高增'。搜索: 什么条件会导致这个链条断裂？客户转单、技术替代、产能过剩的前兆信号是什么？红蓝对抗: 论点'三年内地位稳固' → 挑战 → 存活强度。"},
        ],
        "coverage_note": "前序报告已经覆盖了大部分风险维度，逆向探针聚焦最脆弱的三条假设。"
    },
    "future": {
        "probes": [
            {"name": "2026H2关键催化节点", "task": "前序报告指出2026H2是1.6T大规模出货的关键验证期。搜索: 中际旭创1.6T产品的具体客户验证进度(NVDA/GOOGL谁在测试)、预计quantification时间、产能从投产到达产的时间线。"},
            {"name": "行业展会与客户发布", "task": "未来6个月有哪些光通信/数据中心行业展会(OFC/CIOE/GTC)？英伟达/谷歌/微软是否有新产品发布计划可能涉及光模块需求？搜索2026年光通信展会日历和主要客户roadmap。"},
        ],
        "coverage_note": "催化节点聚焦前序报告中最关键的验证事件，不做泛泛的行业扫描。"
    },
    "event_deduction": {
        "probes": [
            {"name": "T+90关键验证路径", "task": "基于前序4份报告，中际旭创未来3个月(Q2-Q3 2026)的核心验证点是什么？1.6T客户验证是否通过？800G出货量是否继续环比高增？搜索类似公司(AOI/LITE)在关键产品验证期的股价表现作为历史参考。"},
            {"name": "论点破裂传导链", "task": "如果英伟达在2026 GTC上宣布自研光引擎(类似之前投资LITE/COHR的信号)，中际旭创的股价传导链会怎样？搜索: 历史上光模块公司(SMCI/AAOI)在客户自研传闻后的股价反应模式，作为论点破裂场景参考。"},
        ],
        "coverage_note": "推演基于前序报告的未解决问题，不重复已有的T+30/90/180框架。"
    },
}

# ═══════════ Mock 合并结果 ═══════════
MOCK_MERGE_RESULTS = {
    "investment_theme": """### 一、核心叙事
如果AI算力集群的带宽需求继续每2年翻倍，且中际旭创维持800G/1.6T的40%+/55%+市占率，则营收和利润将在2026-2027年持续高增，当前估值(PS 3.3x)有进一步重估空间。

### 二、变革证据链
- **管理层叙事**: 季报强调"AI算力需求强劲""1.6T下半年大规模出货"，战略优先级: 1.6T>硅光>CPO(来源: 探针①)
- **硬数据印证**: 2026Q1营收194.96亿(+192%), 毛利率35.2%(+4.2pct), 800G ASP高于同行15-20%(来源: 探针②)
- **外部验证(Serenity信息差)**: 英伟达$2B×2投资LITE/COHR锁定激光器 —— 市场尚未充分讨论这对中际旭创意味着什么(来源: 探针②)

### 三、关注度评估
- 机构覆盖: 30+券商覆盖, 属于A股明星股(来源: 探针③)
- 媒体渗透: 高, 主流财经媒体频繁报道
- 散户认知: 高, 雪球/东方财富讨论热度Top100
- 市场偏见: 可能的偏见是"光模块=制造业=低壁垒", 但实际上800G+的认证壁垒和良率门槛极高

### 四、估值锚与信息差
- 当前PS 3.3x, Coherent 2.1x, Fabrinet 1.8x(来源: 探针⑤)
- 溢价逻辑: 更高的增速(+192% vs Coherent ~40%)和更高的市占率
- 信息差: 市场可能低估了1.6T的ASP提升幅度和CPO对可插拔模块的替代时间线

### 五、关键验证节点
1. 2026Q2季报: 1.6T出货量和ASP是否达到预期?
2. 英伟达GTC 2026: 是否发布CPO产品? 是否继续外购光模块?""",

    "industry_expert_research": """### 一、产业链位置与需求确定度
**高置信度**（投资主题已覆盖需求端，产业链探针补充供应端）

中际旭创处于光通信中游光模块环节。上游: EML/CW激光器(LITE/COHR/SIVE)、DSP电芯片(博通/Marvell)、光学元件。下游: 英伟达/谷歌/微软/Meta的AI算力集群。需求确定性: 极高 —— 每代GPU升级(I/O带宽翻倍)强制驱动光模块速率升级(800G→1.6T→3.2T)。

### 二、供给格局与价值捕获
**高置信度**（探针①④交叉验证）

- **光芯片供给**: EML激光器是"瓶颈中的瓶颈"——LITE sold out until 2027, CEO原话。英伟达$2B×2投资LITE/COHR锁定产能(来源: 探针①)
- **光模块竞争**: 800G+全球CR3>80%(中际旭创40%+/Coherent 25%/Fabrinet 15%)。新进入者认证: 3-5年(来源: 探针②)
- **中际旭创地位**: 规模最大 + ASP最高 + 良率最优 → "模块环节的卡点"。但⚠️存在分歧: 探针①认为真正的卡点在上游激光器, 探针②认为模块环节也是卡点。

### 三、卡点检查与反方证据
Serenity 4条:
1. ✅ 必要性 — AI光互连无可替代
2. ✅ 供给集中 — CR3>80% + 3-5年认证
3. ⚠️ 市值vsBOM — PS 3.3x高于可比, 但增速(+192%)远超可比(~40%)
4. (a) designed-out — ⚠️ CPO/硅光可能2028年后绕过可插拔模块(来源: 探针③)
   (b) material — ✅ 年营收近¥200B, 远超material阈值

反方证据:
- CPO替代风险(探针③): 英伟达GTC 2026可能展示CPO原型, 但量产时间线可能在2028+
- 客户集中度(探针④): 前五大客户占比>70%, 英伟达单项可能>40%""",

    "adversarial_thinking": """### 维度1: 核心假设脆弱性 — ASP溢价可持续性
- **论点**: 中际旭创800G ASP高于同行15-20%, 来自良率优势和规模效应
- **魔鬼代言人挑战**: (1)英伟达有强烈动机压价——光模块是BOM大头, NVDA CapEx $45B中光模块~12%, 压价5%就省$270M。(2)Coherent/Fabrinet在拼命追赶良率, 一旦持平则溢价消失
- **存活强度**: 中 — 溢价来自先发优势和规模, 短期可维持, 但随着竞争对手良率提升和下游压价, 2027年后可能收窄

### 维度2: 两大失效测试 — CPO designed-out风险
- **论点**: CPO量产至少到2028年, 短期内不威胁可插拔光模块
- **魔鬼代言人挑战**: (1)英伟达2026 GTC如果展示功能完善的CPO交换机+给出2027量产指引, 时间线将压缩到18个月。(2)博通/Intel硅光方案如果先于预期量产, 无论谁赢都会分流可插拔需求
- **存活强度**: 中 — CPO是确定性方向, 只是时间问题。关键在于2027还是2029年。

### 维度3: 利益博弈与利润挤压
- **论点**: 上游激光器(LITE/COHR)的议价力正在增强, 可能挤压中际旭创毛利率
- **魔鬼代言人挑战**: (1)英伟达直接投资锁定激光器 → LITE/COHR获得定价权 → 中际旭创夹在中间(上游涨价+下游压价)。(2)如果中际旭创无法将上游涨价转嫁给下游, 毛利率35%→30%只是时间问题
- **存活强度**: 强 — 英伟达$2B×2投资行为本身就说明激光器是关键控制点, 模块环节相对议价力弱

### 维度4: 外部冲击
- **论点**: 最大外部风险是中美科技脱钩和出口管制
- **魔鬼代言人挑战**: DSP电芯片由博通/Marvell(美国)控制, 光芯片EML由LITE/COHR(美国)控制。如果美国收紧出口管制, 中际旭创可能面临核心芯片断供
- **存活强度**: 中 — 当前政策环境未指向光模块, 但地缘政治风险不可忽视

### 维度5: 论点破裂条件
论点"三年内地位稳固"在以下条件发生时破裂:
1. 英伟达2026 GTC宣布CPO量产时间线(2027) → 立即重估
2. Coherent/Fabrinet良率突破+大客户转单 → 市占率从40%→30%
3. 核心光芯片被纳入出口管制 → 供应链断裂
Serenity: 以上任一发生即砍仓。""",

    "future": """| 预计时间 | 事件 | 证实条件 | 证伪条件 | 优先级 |
|---------|------|---------|---------|:------:|
| 2026-07 | Q2季报发布 | 营收环比+15%+, 1.6T出货超预期 | 营收环比持平或下滑 | P0 |
| 2026-08 | 英伟达GTC 2026 | 无CPO产品发布, 继续强调外购光模块 | 发布CPO原型+2027量产指引 | P0 |
| 2026-09 | 1.6T客户验证完成 | NVDA/GOOGL确认1.6T通过验证 | 验证延期或未通过 | P0 |
| 2026-10 | OFC 2026 | 中际旭创展示3.2T原型 | 竞品率先展示同等级产品 | P1 |
| 2026-11 | Q3季报 | 1.6T规模化出货, 毛利率稳定 | 1.6T良率低导致毛利率下滑 | P1 |
| 2027-01 | 2026年报 | 全年营收超预期, 1.6T成第一大收入来源 | 全年营收不达预期 | P2 |
| 随时 | 美国出口管制升级 | - | 光芯片/DSP被列入管制清单 | P0 |

P0 = 一票确认或一票否决。关注: 2026-08 GTC是最大单个事件, 可能决定CPO时间线和估值锚。""",

    "event_deduction": """### T+30 (2026-07 ~ 2026-08)
- 最可能路径: Q2季报发布 → 营收符合或略超预期 → 股价温和上涨。等待GTC 2026信号。
- 关键分叉点: Q2季报的1.6T出货数据。如果低于预期→市场开始质疑"1.6T放量"叙事。
- 证实条件: 1.6T出货环比+30%+, 毛利率≥35%
- 证伪条件: 1.6T出货低于指引, 或毛利率<33%

### T+90 (2026-08 ~ 2026-10)
- 最可能路径: GTC 2026是最大变量。如果英伟达无CPO发布 → 股价向上突破。如果发布CPO+2027指引 → 大幅波动。
- 关键分叉点: GTC 2026上英伟达对CPO的态度——路线图还是产品？
- 证实条件: GTC无CPO, 1.6T验证通过
- 证伪条件: GTC发布CPO产品, 或验证延期

### T+180 (2026-10 ~ 2027-01)
- 最可能路径: 1.6T大规模出货成为现实, 2026全年业绩基本锁定。估值锚可能从"高速增长"切换到"成熟龙头"。
- 关键分叉点: 如果2026全年营收不达市场预期(>¥800亿)，估值可能从PS 3.3x下修到2.5x
- 证实条件: 全年营收超¥800亿, 毛利率>34%
- 证伪条件: 营收不达预期, 或竞争格局恶化

### 论点破裂场景
投资主题的if-then命题最可能在以下场景破裂:
1. **T+30-90 CPO冲击**: 英伟达GTC发布CPO+2027量产 → 可插拔光模块的TAM被压缩 → 估值锚从"成长"切换到"被颠覆", PS可能从3.3x压缩到1.5-2.0x (转移概率: 15%)
2. **T+90-180 竞争恶化**: Coherent/Fabrinet良率突破+大幅降价 → 中际旭创市占率从40%→30%, 毛利率从35%→28% (转移概率: 20%)
3. **T+180 需求不达**: AI算力投资增速放缓 → 光模块需求增速从+60%降到+20% → 戴维斯双杀 (转移概率: 10%)

### 历史案例参考
- **AAOI 2024-2025**: 美国最大800G/1.6T光模块产能, 从$30→$13B, 类似中际旭创当前阶段。AAOI在客户自研传闻后曾单日跌15%, 但在验证通过后恢复。启示: CPO类似"客户自研"风险, 但在验证通过前是波动源而非终局。
- **LITE 2025-2026**: EML激光器龙头, $49→$614, CEO"sold out until 2027"给了市场确定性。启示: 激光器才是真正卡点, 模块的价值量可能被上游侵蚀。""",
}

# ═══════════ 主流程 ═══════════

print("=" * 60)
print("Coze工作流 v2 测试 — 顺序推进 + 动态探针")
print(f"标的: {STOCK_NAME}({STOCK_CODE}) | Mock: {MOCK_MODE}")
print("=" * 60)

reports = {}  # {field_name: report_text}
all_searches = 0
all_elapsed = 0

for step, cfg in enumerate(FIELD_ORDER):
    field_name = cfg["field"]
    label = cfg["label"]
    prior_fields = cfg["prior"]
    min_p, max_p = cfg["min_p"], cfg["max_p"]

    print(f"\n{'─' * 60}")
    print(f"N{step+1}: {label} ({field_name})")
    print(f"  前序: {prior_fields if prior_fields else '(无, 第一步)'}")
    print(f"  探针范围: {min_p}-{max_p}")

    # 读前序报告
    prior_texts = ""
    for pf in prior_fields:
        if pf in reports:
            prior_texts += f"\n\n### {pf}\n{reports[pf][:3000]}"

    # 设计探针
    if MOCK_MODE:
        design = MOCK_PROBE_DESIGNS.get(field_name, {"probes": [], "coverage_note": "无"})
        probes = design["probes"]
        coverage = design.get("coverage_note", "")
    else:
        # TODO: 调用 DeepSeek API 设计探针
        print("  [真实模式需要有效API Key]")
        probes = []
        coverage = ""

    n_probes = len(probes)
    print(f"  设计探针: {n_probes}个 → {coverage[:100]}")

    if n_probes == 0:
        print(f"  ⚠️ 无探针, 跳过")
        continue

    for i, p in enumerate(probes):
        print(f"    探针{i+1}: {p['name'][:50]}")

    # 模拟搜索次数 (mock=2次/探针)
    searches = n_probes * 2 if MOCK_MODE else 0
    all_searches += searches

    # 合并
    if MOCK_MODE:
        report = MOCK_MERGE_RESULTS.get(field_name, f"[Mock] {label}合并报告")
    else:
        report = f"[真实模式] {label}合并报告"

    reports[field_name] = report
    elapsed = 15.0 if MOCK_MODE else 0  # mock固定15s
    all_elapsed += elapsed

    print(f"  → {searches}搜 {elapsed:.0f}s {len(report)}c")
    # 预览
    preview = report[:200].replace("\n", " ")
    print(f"  {preview}...")

# ═══════════ 管道完整性检查 ═══════════
print(f"\n{'=' * 60}")
print("管道完整性检查")
print(f"总搜索: {all_searches}次 | 总耗时: {all_elapsed:.0f}s")

checks = [
    ("5字段全部生成", len(reports) == 5),
    ("N1投资主题优先", list(reports.keys())[0] == "investment_theme"),
    ("N2产业链第二", list(reports.keys())[1] == "industry_expert_research"),
    ("N3逆向第三", list(reports.keys())[2] == "adversarial_thinking"),
    ("N4催化第四", list(reports.keys())[3] == "future"),
    ("N5推演第五", list(reports.keys())[4] == "event_deduction"),
    ("投资主题含if-then", "if-then" in reports.get("investment_theme", "").lower() or "如果" in reports.get("investment_theme", "")),
    ("产业链含卡点检查", any(kw in reports.get("industry_expert_research", "") for kw in ["卡点", "Serenity", "✅", "瓶颈"])),
    ("逆向含存活强度", any(kw in reports.get("adversarial_thinking", "") for kw in ["存活强度", "强/中/弱", "魔鬼代言人"])),
    ("催化含P0节点", "P0" in reports.get("future", "")),
    ("推演含T+时间锚", any(kw in reports.get("event_deduction", "") for kw in ["T+30", "T+90", "T+180"])),
    ("探针数动态变化(非固定3)", len({len(MOCK_PROBE_DESIGNS[f]["probes"]) for f in MOCK_PROBE_DESIGNS}) > 1),
]
all_ok = True
for name, result in checks:
    status = "✅" if result else "❌"
    if not result: all_ok = False
    print(f"  {status} {name}")

print(f"\n{'全部通过!' if all_ok else '存在失败项'}")

# ═══════════ 保存 ═══════════
report_path = f"D:/长流水/tmp_coze_v2_test_{STOCK_CODE}.md"
with open(report_path, "w", encoding="utf-8") as f:
    f.write(f"# Coze v2 测试: {STOCK_NAME}\n\n> Mock: {MOCK_MODE} | 总搜索: {all_searches} | 总耗时: {all_elapsed:.0f}s\n\n---\n\n")
    for field_name, report in reports.items():
        f.write(f"## {field_name}\n\n{report}\n\n---\n\n")
print(f"\n报告: {report_path}")
