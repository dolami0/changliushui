"""field_node.py — Coze Code节点通用模板 (N1-N5)
================================================
每个字段节点内部流程:
  1. 读前序报告
  2. LLM: 基于前序认知 → 自由设计N个探针 (数量自定, 3-6个)
  3. ThreadPool并行执行所有探针 (每个: 干净上下文, ≤2搜, 4项结论)
  4. LLM: 合并探针结论 → 字段报告
  5. 输出字段报告

部署: 在Coze中为N1-N5各创建一个Code节点, 复制此代码,
      修改顶部的 ==== 节点配置 ==== 部分即可。
"""

import json, requests, time, concurrent.futures, re, sys

# ══════════════════════════════════════════════════════
# ==== 节点配置 (每个节点修改这里) ====
# ══════════════════════════════════════════════════════

# 本节点处理的字段名
FIELD_NAME = "investment_theme"  # ← 修改: industry_expert_research / adversarial_thinking / future / event_deduction

# 本节点依赖的前序字段 (空列表=第一步, 无前序)
# ├─ N1 investment_theme           → PRIOR_FIELDS = []
# ├─ N2 industry_expert_research   → PRIOR_FIELDS = ["investment_theme"]
# ├─ N3 adversarial_thinking       → PRIOR_FIELDS = ["investment_theme", "industry_expert_research"]
# ├─ N4 future                     → PRIOR_FIELDS = ["investment_theme", "industry_expert_research", "adversarial_thinking"]
# └─ N5 event_deduction            → PRIOR_FIELDS = ["investment_theme", "industry_expert_research", "adversarial_thinking", "future"]
PRIOR_FIELDS = []  # ← 修改

# 探针数量范围
PROBE_MIN = 3  # ← 投资主题/产业链建议5, 逆向建议4, 催化/推演建议3
PROBE_MAX = 6  # ← 投资主题/产业链建议6, 逆向建议5, 催化/推演建议4

# ══════════════════════════════════════════════════════
# ==== API 配置 ====
# ══════════════════════════════════════════════════════

DEEPSEEK_KEY = "sk-8f02dfb2f5a44e02b7afea5e2daa5814"
BOCHA_KEY = "sk-090c432b4f5745caa8767ae70f5b348b"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
BOCHA_URL = "https://api.bochaai.com/v1/web-search"

# ══════════════════════════════════════════════════════
# ==== Coze注入变量 (由上游节点或START传入) ====
# ══════════════════════════════════════════════════════
# verified_name, verified_code (N0校验后), is_valid (N0输出)
# news_content, knowledge, step_one (START)
# 以及前序字段报告 (变量名 = 字段名, 如 {{investment_theme}})
#
# 兼容性: 如果 N0 不存在, 回退到 stock_name/stock_code
STOCK_NAME = (verified_name if "verified_name" in dir() and verified_name
             else stock_name if "stock_name" in dir() else "")
STOCK_CODE = (verified_code if "verified_code" in dir() and verified_code
             else stock_code if "stock_code" in dir() else "")
IS_VALID = (is_valid if "is_valid" in dir() else "true")

# ══════════════════════════════════════════════════════
# ==== 工具: 博查搜索 ====
# ══════════════════════════════════════════════════════

def bocha_search(query, count=5):
    try:
        r = requests.post(BOCHA_URL,
            headers={"Authorization": f"Bearer {BOCHA_KEY}", "Content-Type": "application/json"},
            json={"query": query, "count": min(count, 10), "freshness": "oneYear", "summary": True},
            timeout=30)
        data = r.json()
        pages = data.get("data", {}).get("webPages", {}).get("value", [])
        if not pages:
            return "无搜索结果"
        return "\n---\n".join(
            f"[{i+1}] {p.get('name','')}\n来源: {p.get('siteName','')} | {p.get('datePublished','')}\n{p.get('summary', p.get('snippet',''))[:800]}"
            for i, p in enumerate(pages[:count]))
    except Exception as e:
        return f"搜索异常: {e}"

TOOLS_DEF = [{
    "type": "function",
    "function": {
        "name": "bocha_search",
        "description": "搜索中文互联网信息。返回网页标题、来源、日期和摘要。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询，要具体包含公司名/产品名/行业术语"},
                "count": {"type": "integer", "description": "返回结果数，默认5"}
            },
            "required": ["query"]
        }
    }
}]
TOOL_MAP = {"bocha_search": bocha_search}

# ══════════════════════════════════════════════════════
# ==== 步骤1: 读前序报告 ====
# ══════════════════════════════════════════════════════

def read_prior_reports():
    """收集本节点依赖的前序字段报告"""
    reports = {}
    # Coze上下文中, 前序字段输出就是变量名
    # 例如 {{investment_theme}} 在上游节点输出后可直接引用
    for field in PRIOR_FIELDS:
        try:
            # Coze变量在Python中通过全局命名空间注入
            val = globals().get(field, "")
            if val:
                reports[field] = str(val)[:8000]
        except:
            pass
    return reports

# ══════════════════════════════════════════════════════
# ==== 步骤2: LLM设计探针 ====
# ══════════════════════════════════════════════════════

FIELD_DESIGN_PROMPTS = {
    "investment_theme": """你是投资分析师。你已读完这只股票的原始事件和AI深度研究。

## 你的任务

为这只股票设计侦查探针。每个探针是一个需要上网搜索才能回答的具体问题。

## 你需要覆盖的方向

1. **管理层叙事**: 管理层怎么描述公司战略和变革？年报/季报/投资者交流中有什么关键措辞？
2. **硬数据印证**: 分产品收入结构变化？毛利率趋势？产能利用率？这些数字支持还是反驳管理层叙事？
3. **市场预期**: 券商一致预期是什么？覆盖券商几家？市场偏见在哪？
4. **关注度与信息差**: 机构持仓变化？雪球讨论热度？是否属于"机构不能买(市值<$1B)"或"散户100%负面=反向信号"的情况？
5. **估值锚**: 当前估值隐含什么假设？如果叙事兑现/落空，估值锚会怎么迁移？同环节可比公司市值？(不要用P/E)
6. **核心叙事**: 基于以上，这只股票的if-then命题是什么？

## 探针设计原则

- 每个探针必须引用事件/知识中的**具体细节**（数字、产品名、客户名、时间节点）
- 每个探针是**独立的**——探针之间不知道彼此存在，所以上下文必须自包含
- 不要问"分析竞争格局"这种泛问题——问"中际旭创800G OSFP ASP $800-1200是否可持续，Coherent的价格策略是什么"
- 如果事件内容已经足够回答某个方向，就不要为它设探针——把探针留给真正需要搜索的方向

## 输出格式

纯JSON:
{
  "probes": [
    {"name": "简短标题(≤15字)", "task": "具体侦查问题(50-150字), 包含为什么重要、要搜什么"},
    ...
  ],
  "coverage_note": "简要说明: 哪些方向被探针覆盖了, 哪些方向因事件信息已充分而跳过"
}

生成 {min_probes}-{max_probes} 个探针。不要生成无关方向的探针。""",

    "industry_expert_research": """你是产业链分析师。你已读完投资主题报告，理解了这只股票的核心叙事和关键假设。

## 你的任务

基于投资主题报告中揭示的核心矛盾，为产业链和竞争卡位维度设计侦查探针。

## 你需要覆盖的方向

1. **产业链位置**: 公司在产业链中处于什么位置？紧邻上游是谁、下游是谁？这一层的附加值占比？
2. **供给格局**: 公司所在环节全球CR3？公司在其中排第几？新进入者认证周期？产能扩张需要多久？
3. **需求确定度**: 下游需求确定性来源是什么(合同/政策/物理约束)？能持续多少年？
4. **价值捕获**: 公司定价权——历史涨价频率和幅度？毛利率趋势？客户切换成本多大？
5. **卡点检查(Serenity 4条标准)**:
   (a)人人都需要它的产品吗？
   (b)供给高度集中+多年难扩产？
   (c)公司市值vs下游BOM是否错配？
   (d)会被大客户垂直整合绕过吗(designed-out)？
6. **反方证据**: 哪些事实会让"这家公司地位稳固"的叙事不成立？

## 探针设计原则

- 每个探针必须引用**投资主题报告中的具体判断**，针对最不确定的方向提问
- 投资主题已经搞清楚的事情不要再问——把钱花在刀刃上
- 每个探针是独立的、自包含的

## 输出格式

纯JSON:
{
  "probes": [
    {"name": "简短标题", "task": "具体侦查问题(50-150字)"},
    ...
  ],
  "coverage_note": "哪些方向被覆盖, 哪些方向因投资主题已充分论证而跳过"
}

生成 {min_probes}-{max_probes} 个探针。""",

    "adversarial_thinking": """你是逆向分析师。你已读完投资主题和产业链报告，对这只股票的叙事和风险有了理解。

## 你的任务

找出投资主题和产业链报告中最脆弱的假设和逻辑漏洞，设计红蓝对抗探针。

## 你需要覆盖的方向

1. **核心假设脆弱性**: 投资主题的if-then命题中，最脆弱的假设是哪个？什么证据会证伪它？
2. **两大失效测试(Serenity风控)**:
   (a) 公司的关键产品/地位会被大客户垂直整合绕过吗(designed-out)？
   (b) 公司的"卡点"收入够material吗(体量太小即使卡也拉不动股价)？
3. **利益博弈**: 上游/下游/竞争对手中，谁最有动机和能力挤压公司利润？
4. **外部冲击**: 政策/技术替代/地缘政治/宏观周期，哪个最可能颠覆叙事？
5. **论点破裂条件**: 什么条件发生时，整个投资论点彻底破裂？Serenity: "论点变即砍仓"

## 特殊要求: 红蓝对抗

每个探针的task中，必须要求Agent:
1. 先提出论点和证据
2. 执行"魔鬼代言人挑战"——扮演最恶意的反对者，找出至少2个有数据支撑的反驳点
3. 标注论点在被挑战后的"存活强度"(强/中/弱)

## 输出格式

纯JSON:
{
  "probes": [
    {"name": "简短标题(含🔴)", "task": "侦查问题 + 要求Agent执行: 论据→魔鬼代言人挑战→存活强度"},
    ...
  ],
  "coverage_note": "..."
}

生成 {min_probes}-{max_probes} 个探针。""",

    "future": """你是催化剂分析师。你已读完前序所有报告（投资主题+产业链+逆向推演），对这只股票的关键验证节点有了理解。

## 你的任务

设计探针，找出未来6-12个月的关键催化事件，编制催化日历。

## 你需要覆盖的方向

1. **财报节点**: 下次季报/年报时间？市场一致预期？
2. **产品里程碑**: 关键产品量产/客户验证/产能爬坡节点？
3. **资格认证拐点(Serenity视角)**: 有没有qualification cycle inflection？认证通过会触发什么？
4. **行业催化剂**: 重要展会/客户产品发布/政策节点？
5. **风险节点**: 解禁日/减持窗口/竞品发布日期/客户流失信号？

## 探针设计原则

- 引用前序报告中提到的具体时间节点和产品名
- 优先覆盖P0级别节点（一票确认或一票否决的事件）
- 前序报告已有明确时间的节点不要再搜

## 输出格式

纯JSON:
{
  "probes": [
    {"name": "简短标题", "task": "具体侦查问题(50-150字)"},
    ...
  ],
  "coverage_note": "..."
}

生成 {min_probes}-{max_probes} 个探针。""",

    "event_deduction": """你是推演分析师。你已读完前序所有报告（投资主题+产业链+逆向+催化），对这只股票的叙事全景有了完整理解。

## 你的任务

基于前序报告的发现和未解决的问题，推演三种时间尺度的路径和论点破裂场景。

## 你需要覆盖的方向

1. **T+30推演**: 短期(1月)最可能路径？关键分叉点？什么指标会验证/证伪？
2. **T+90推演**: 中期(3月)业绩验证期的路径？财务指标如何反映？
3. **T+180推演**: 长期(6月)叙事定型或重构方向？估值体系会切换吗？
4. **论点破裂场景**: 如果论点被证伪，传导链如何？T+30/90/180的破裂路径？转移概率？
5. **历史案例**: 类似处境的历史案例——类似事件引发什么传导链？市场如何反应？

## 探针设计原则

- 引用前序报告中的具体判断和数字
- 重点覆盖前序报告标记为"[数据缺失]"或"存在分歧"的方向
- 不要重复前序已经推演过的内容

## 输出格式

纯JSON:
{
  "probes": [
    {"name": "简短标题", "task": "具体侦查问题(50-150字)"},
    ...
  ],
  "coverage_note": "..."
}

生成 {min_probes}-{max_probes} 个探针。""",
}

FIELD_MERGE_PROMPTS = {
    "investment_theme": """你是投资分析师。将以下N份独立探针结论合并为投资主题报告。

## 合并规则
1. 互相支持的结论 → 标注"**高置信度**（探针X和Y独立得出相同结论）"
2. 互相冲突的结论 → 标注"⚠️ **存在分歧**"
3. 全缺 → 标注"**[数据缺失]**"

## 报告格式

### 一、核心叙事 (if-then命题, ≤50字)

### 二、变革证据链
- 管理层叙事 (来源: 探针X)
- 硬数据印证 (来源: 探针Y)
- 外部验证 (Serenity信息差标注: 机构还没覆盖/散户不知道/媒体没写透)

### 三、关注度评估
- 机构覆盖 | 媒体渗透 | 散户认知 | 市场偏见
- Serenity: 市值<$1B→机构不能买？散户100%负面→反向信号？

### 四、估值锚与信息差
- 当前估值隐含假设
- 叙事兑现→估值锚迁移路径
- 叙事落空→下行风险
- Serenity: 同环节可比市值, 不要P/E

### 五、关键验证节点 (2-3个证实/证伪条件)""",

    "industry_expert_research": """你是产业链分析师。将以下N份独立探针结论合并为产业链研究报告。

## 合并规则
1. 互相支持 → "**高置信度**"
2. 互相冲突 → "⚠️ **存在分歧**"
3. 全缺 → "**[数据缺失]**"
4. Serenity规则: 多探针独立得出相同卡点判断 → "**交叉验证通过**"

## 报告格式

### 一、产业链位置与需求确定度
(公司在产业链哪一层 + 紧邻上下游 + 需求确定性来源与持续性)

### 二、供给格局与价值捕获
(全球竞争格局 + 公司排位 + 认证/扩产壁垒 + 定价权 + 毛利率趋势 + 客户切换成本)

### 三、卡点检查与反方证据
Serenity 4条逐条检查 (✅/⚠️/❌):
1. 必要性 —
2. 供给集中 —
3. 市值vsBOM —
4. 失效测试(a)designed-out — (b)material —

反方证据: 技术替代/客户流失/新进入者威胁""",

    "adversarial_thinking": """你是逆向分析师。合并N份独立探针结论为逆向推演报告。

## 合并规则
1. 互相支持 → "**高置信度**"
2. 互相冲突 → "⚠️ **存在分歧**"
3. 🔴 红蓝对抗检查: 每维度必须有魔鬼代言人挑战和存活强度。缺少则标注"⚠️ 红蓝对抗不完整"

## 报告格式

### 维度1: 核心假设脆弱性
- **论点**: [逆向分析核心判断]
- **魔鬼代言人挑战**: [最有力反驳, 附数据]
- **存活强度**: 强/中/弱 — [理由]

### 维度2: 两大失效测试
- **论点**: ...
- **魔鬼代言人挑战**: ...
- **存活强度**: 强/中/弱

### 维度3: 利益博弈与利润挤压
- **论点**: ...
- **魔鬼代言人挑战**: ...
- **存活强度**: 强/中/弱

### 维度4: 外部冲击
- **论点**: ...
- **魔鬼代言人挑战**: ...
- **存活强度**: 强/中/弱

### 维度5: 论点破裂条件
- 什么条件发生时整个投资论点彻底破裂？
- Serenity: "论点变即砍仓甚至反手做空" """,

    "future": """你是催化剂分析师。合并N份独立探针结论为催化日历。

## 报告格式

| 预计时间 | 事件 | 证实条件 | 证伪条件 | 优先级 |
|---------|------|---------|---------|:------:|
| ... | ... | ... | ... | P0/P1/P2 |

P0 = 一票确认或一票否决

覆盖: 财报节点 / 产品里程碑 / 行业催化剂 / 产能节点 / 风险节点""",

    "event_deduction": """你是推演分析师。合并N份独立探针结论为事件推演报告。

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
- T+30/90/180的破裂路径, 附转移概率

### 历史案例参考
- 类似事件的传导链和市场反应""",
}

def design_probes(prior_reports, field_name):
    """LLM: 基于前序报告(如有)为本字段设计探针"""
    design_prompt = FIELD_DESIGN_PROMPTS[field_name].format(
        min_probes=PROBE_MIN, max_probes=PROBE_MAX)

    # 构建上下文
    context = f"## 股票: {STOCK_NAME}（{STOCK_CODE}）\n\n"
    context += f"## 原始事件\n{news_content[:2000] if news_content else '无'}\n\n"

    if knowledge and str(knowledge).strip():
        context += f"## AI深度研究\n{str(knowledge)[:1500]}\n\n"
    if step_one and str(step_one).strip():
        context += f"## 预研分析\n{str(step_one)[:1000]}\n\n"

    if prior_reports:
        context += "## 前序报告（已完成的深度分析）\n\n"
        for fname, freport in prior_reports.items():
            fn_cn = {"investment_theme": "投资主题", "industry_expert_research": "产业链研究",
                     "adversarial_thinking": "逆向推演", "future": "催化日历"}.get(fname, fname)
            context += f"### {fn_cn}\n{str(freport)[:4000]}\n\n"

    messages = [
        {"role": "system", "content": design_prompt},
        {"role": "user", "content": f"{context}\n\n---\n请基于以上信息设计探针。直接输出JSON。"},
    ]

    resp = requests.post(DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        json={"model": "deepseek-v4-flash", "temperature": 0, "max_tokens": 4096,
              "messages": messages, "thinking": {"type": "enabled"}},
        timeout=90)

    data = resp.json()
    if "choices" not in data:
        print(f"[{field_name}] 探针设计API错误: {json.dumps(data, ensure_ascii=False)[:300]}", file=sys.stderr)
        return [], "API错误"

    content = data["choices"][0]["message"]["content"]
    # 提取JSON
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try: result = json.loads(match.group())
            except: return [], "JSON解析失败: " + content[:200]
        else:
            return [], "JSON解析失败: " + content[:200]

    probes = result.get("probes", [])
    coverage = result.get("coverage_note", "")
    return probes, coverage

# ══════════════════════════════════════════════════════
# ==== 步骤3: 单个探针执行 ====
# ══════════════════════════════════════════════════════

def run_single_probe(probe_name, probe_task, stock_info, max_searches=2):
    """独立探针: 干净上下文, ≤2次搜索, 只输出4项结论"""
    system = f"""你是专项分析师。你的任务只有一个: {probe_task}

你有 bocha_search 工具。最多搜索 {max_searches} 次。
第1次搜索覆盖面，第2次只补第1次发现的最大缺口。
搜完立即输出4项结论。不要写报告，只输出4项:

**结论**: [一句话直接回答问题]
**最强证据**: [具体数字, 标注来源]
**最大缺口**: [如实写缺什么信息, 不要编造]
**一手来源**: [需要补的原始数据/报告名称]"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"请完成探针任务: {probe_task}\n\n标的: {stock_info}"},
    ]

    sd, log = 0, []
    for iteration in range(8):
        if sd >= max_searches:
            resp = requests.post(DEEPSEEK_URL,
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
                json={"model": "deepseek-v4-flash", "temperature": 0, "max_tokens": 2048,
                      "messages": messages + [{"role": "user", "content": "搜索已达上限。立即输出4项结论。"}],
                      "tools": None, "thinking": {"type": "enabled"}}, timeout=60)
            data = resp.json()
            if "choices" in data and data["choices"][0]["message"].get("content"):
                return {"name": probe_name, "conclusion": data["choices"][0]["message"]["content"], "searches": sd, "queries": log}
            break

        resp = requests.post(DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-v4-flash", "temperature": 0, "max_tokens": 4096,
                  "messages": messages, "tools": TOOLS_DEF, "thinking": {"type": "enabled"}}, timeout=60)
        data = resp.json()
        if "choices" not in data: break

        msg = data["choices"][0]["message"]
        reasoning = msg.get("reasoning_content", "")

        if msg.get("tool_calls"):
            messages.append({"role": "assistant", "content": "", "tool_calls": msg["tool_calls"], "reasoning_content": reasoning})
            for tc in msg["tool_calls"]:
                func, args = tc["function"]["name"], json.loads(tc["function"]["arguments"])
                sd += 1
                query = list(args.values())[0] if args else "?"
                result = TOOL_MAP[func](**args) if func in TOOL_MAP else "未知工具"
                log.append({"tool": func, "query": str(query)[:200]})
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
            hint = f"已搜{sd}次。" + ("已达上限，立即输出4项结论。" if sd >= max_searches else "可再搜1次补缺口，或输出结论。")
            messages.append({"role": "user", "content": hint})
        else:
            content = msg.get("content", "")
            if content and len(content) > 100:
                return {"name": probe_name, "conclusion": content, "searches": sd, "queries": log}
            elif content:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "请立即输出4项结论。"})

    return {"name": probe_name, "conclusion": "", "searches": sd, "queries": log, "error": "超时"}

# ══════════════════════════════════════════════════════
# ==== 步骤4: 合并探针 ====
# ══════════════════════════════════════════════════════

def merge_probes(field_name, probe_results):
    """将N个独立探针结论合并为字段报告"""
    conclusions_text = "\n\n---\n\n".join(
        f"## 探针{i+1}: {p['name']}\n{p['conclusion']}"
        for i, p in enumerate(probe_results))

    merge_prompt = FIELD_MERGE_PROMPTS.get(field_name, FIELD_MERGE_PROMPTS["investment_theme"])

    messages = [
        {"role": "system", "content": merge_prompt},
        {"role": "user", "content": f"合并以下{len(probe_results)}份独立探针结论为最终报告:\n\n{conclusions_text}"},
    ]

    resp = requests.post(DEEPSEEK_URL,
        headers={"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"},
        json={"model": "deepseek-v4-flash", "temperature": 0, "max_tokens": 8192,
              "messages": messages, "thinking": {"type": "enabled"}},
        timeout=120)

    data = resp.json()
    if "choices" not in data:
        return f"[合并失败] {data.get('error', {}).get('message', '?')}"
    return data["choices"][0]["message"]["content"]

# ══════════════════════════════════════════════════════
# ==== 主流程 ====
# ══════════════════════════════════════════════════════

def main():
    start = time.time()

    # 0. N0校验拦截: 如果股票无效则直接跳过
    if IS_VALID == "false":
        print(f"[{FIELD_NAME}] ⛔ N0校验未通过, 跳过本节点", file=sys.stderr)
        print("")
        return

    if not STOCK_NAME or not STOCK_CODE:
        print(f"[{FIELD_NAME}] ⛔ 股票信息缺失", file=sys.stderr)
        print("")
        return

    # 1. 读前序
    prior = read_prior_reports()
    n_prior = len(prior)
    if n_prior > 0:
        print(f"[{FIELD_NAME}] 读入{n_prior}份前序报告: {', '.join(prior.keys())}", file=sys.stderr)

    # 2. 设计探针
    probes, coverage = design_probes(prior, FIELD_NAME)
    n_probes = len(probes)

    if n_probes == 0:
        print(f"[{FIELD_NAME}] ⚠️ 探针设计失败: {coverage}", file=sys.stderr)
        print("")
        return

    print(f"[{FIELD_NAME}] 设计{n_probes}个探针: {coverage[:100]}", file=sys.stderr)
    for i, p in enumerate(probes):
        print(f"  探针{i+1}: {p['name'][:40]}", file=sys.stderr)

    # 3. 并行执行
    stock_info = f"{STOCK_NAME}（{STOCK_CODE}）\n事件: {str(news_content)[:1500]}"
    probe_results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_probes) as executor:
        futmap = {executor.submit(run_single_probe, p["name"], p["task"], stock_info): p for p in probes}
        for future in concurrent.futures.as_completed(futmap):
            probe_results.append(future.result())

    # 按原始顺序排序
    name_order = {p["name"]: i for i, p in enumerate(probes)}
    probe_results.sort(key=lambda x: name_order.get(x["name"], 99))

    for i, pr in enumerate(probe_results):
        print(f"  探针{i+1}: {pr['searches']}搜 {len(pr['conclusion'])}c", file=sys.stderr)

    # 4. 合并
    field_report = merge_probes(FIELD_NAME, probe_results)
    total_searches = sum(p["searches"] for p in probe_results)
    elapsed = time.time() - start

    print(f"[{FIELD_NAME}] 完成: {total_searches}搜 {elapsed:.0f}s {len(field_report)}c", file=sys.stderr)

    # 5. 输出 (Coze读取此输出传递给下游)
    print(field_report)

# Coze Code节点入口
main()
