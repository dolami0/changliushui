# 万业谱预研管线 — Coze 工作流设计方案 v5.1

## 一、设计理念

### 核心问题

LLM 读完一条 300 字新闻后，不可能一次性设计出 15 个高质量探针。模板化探针只能问泛泛的问题，无法针对具体事件的核心矛盾展开侦查。

### 解决方案：顺序推进 + 信息递归收敛

像人类分析师一样，每一步基于前序认知提出更深的问题：

```
读事件 → 形成初步投资判断 → 搜 → 修正判断 → 
基于新认知提产业链问题 → 搜 → 
基于产业链认知提逆向问题 → 搜 → 
基于全景认知找催化节点 → 搜 → 
基于全部认知推演路径
```

每步产出的报告成为下一步探针设计的输入。后序探针引用前序报告中的具体判断，避免重复搜索已知信息，专注攻克未知方向。

### 探针数动态决定

LLM 根据当前需要覆盖的方向数量，在 3-6 个范围内自主决定。投资主题覆盖面宽可能需要 5 个，催化日历聚焦关键节点可能只需要 2 个。固定 3 个是削足适履。

---

## 二、工作流 DAG

```
                          START
                            │
            stock_name, stock_code, news_content,
            knowledge, step_one
                            │
                            ▼
            ┌───────────────────────────────┐
            │ N1 [Code] 投资主题             │
            │ field_node.py                 │
            │ FIELD_NAME="investment_theme" │
            │ PRIOR_FIELDS=[]               │
            │ PROBE_MIN=3, PROBE_MAX=6      │
            │                               │
            │ ① 无前序，直读原始事件          │
            │ ② LLM设计3-6探针               │
            │ ③ ThreadPool并行执行           │
            │ ④ LLM合并 → 投资主题报告        │
            └──────────────┬────────────────┘
                           │ investment_theme
                           ▼
            ┌───────────────────────────────┐
            │ N2 [Code] 产业链+竞争卡位       │
            │ FIELD_NAME="industry_expert_   │
            │   research"                    │
            │ PRIOR_FIELDS=["investment_     │
            │   theme"]                      │
            │ PROBE_MIN=3, PROBE_MAX=6      │
            │                               │
            │ ① 读入投资主题报告              │
            │ ② LLM基于投资主题的矛盾设计探针   │
            │   (跳过已覆盖的需求方向)          │
            │ ③ ThreadPool并行执行           │
            │ ④ LLM合并 → 产业链报告          │
            └──────────────┬────────────────┘
                           │ investment_theme
                           │ industry_expert_research
                           ▼
            ┌───────────────────────────────┐
            │ N3 [Code] 逆向推演+红蓝对抗     │
            │ FIELD_NAME="adversarial_       │
            │   thinking"                    │
            │ PRIOR_FIELDS=["investment_     │
            │   theme",                      │
            │   "industry_expert_research"]  │
            │ PROBE_MIN=3, PROBE_MAX=5      │
            │                               │
            │ ① 读入投资主题+产业链两份报告     │
            │ ② LLM找最脆弱假设设计攻击探针    │
            │ ③ 每探针要求红蓝对抗+存活强度    │
            │ ④ LLM合并 → 逆向推演报告        │
            └──────────────┬────────────────┘
                           │ 前三份报告
                           ▼
            ┌───────────────────────────────┐
            │ N4 [Code] 催化日历             │
            │ FIELD_NAME="future"           │
            │ PRIOR_FIELDS=["investment_    │
            │   theme",                      │
            │   "industry_expert_research",  │
            │   "adversarial_thinking"]      │
            │ PROBE_MIN=2, PROBE_MAX=4      │
            │                               │
            │ ① 读入前三份报告                │
            │ ② LLM聚焦关键验证节点设计探针    │
            │ ③ ThreadPool并行执行           │
            │ ④ LLM合并 → 催化日历 (P0/P1/P2) │
            └──────────────┬────────────────┘
                           │ 前四份报告
                           ▼
            ┌───────────────────────────────┐
            │ N5 [Code] 事件推演             │
            │ FIELD_NAME="event_deduction"  │
            │ PRIOR_FIELDS=["investment_    │
            │   theme",                      │
            │   "industry_expert_research",  │
            │   "adversarial_thinking",      │
            │   "future"]                    │
            │ PROBE_MIN=2, PROBE_MAX=4      │
            │                               │
            │ ① 读入前四份报告（全景认知）      │
            │ ② LLM设计推演+历史案例探针       │
            │ ③ ThreadPool并行执行           │
            │ ④ LLM合并 → 事件推演报告        │
            └──────────────┬────────────────┘
                           │ 5份字段报告
                           ▼
            ┌───────────────────────────────┐
            │ N6 [LLM] 总装+去重+交叉验证     │
            │ n6_assembler.json             │
            │                               │
            │ 去重: 后序引用前序的段落删除      │
            │ 交叉验证: N1 vs N2, N2 vs N3   │
            │ knowledge_supplement           │
            │ → final_record (JSON)          │
            └──────────────┬────────────────┘
                           │ final_record
                           ▼
            ┌───────────────────────────────┐
            │ N7 [Code] 写入万业谱            │
            │ n7_writer.py                  │
            │                               │
            │ POST 万业谱 + 标记天机卷已处理    │
            └──────────────┬────────────────┘
                           ▼
                          END
```

**总节点数**: 7 | **Code节点**: 6 (N1-N5 + N7) | **LLM节点**: 1 (N6)

---

## 三、节点详解

### N1-N5 通用结构

5 个节点使用同一份 `field_node.py` 代码，仅修改顶部 3 行配置。每个节点内部 4 步：

```
┌─ Code 节点内部 ─────────────────────────────────┐
│                                                │
│  ① read_prior_reports()                        │
│     收集 PRIOR_FIELDS 指定的前序报告              │
│     N1 跳过（PRIOR_FIELDS=[]）                   │
│                                                │
│  ② design_probes(prior, field_name)            │
│     LLM读前序 → 自定探针数(3-6) → 输出JSON       │
│     System: FIELD_DESIGN_PROMPTS[field_name]    │
│     User: 原始事件 + 知识 + 前序报告(≤4000字/份)  │
│                                                │
│  ③ ThreadPool 并行执行 N 个探针                  │
│     run_single_probe × N                       │
│     每个: 干净上下文, ≤2次bocha搜索, 输出4项结论  │
│                                                │
│  ④ merge_probes(field_name, results)           │
│     LLM合并N份探针结论 → 字段报告                 │
│     System: FIELD_MERGE_PROMPTS[field_name]     │
│                                                │
│  ⑤ print(字段报告) → Coze传递给下游              │
│                                                │
└────────────────────────────────────────────────┘
```

### N1-N5 配置差异

| 节点 | FIELD_NAME | PRIOR_FIELDS | PROBE_MIN | PROBE_MAX |
|------|-----------|-------------|:---------:|:---------:|
| N1 | `investment_theme` | `[]` | 3 | 6 |
| N2 | `industry_expert_research` | `["investment_theme"]` | 3 | 6 |
| N3 | `adversarial_thinking` | `["investment_theme", "industry_expert_research"]` | 3 | 5 |
| N4 | `future` | `["investment_theme", "industry_expert_research", "adversarial_thinking"]` | 2 | 4 |
| N5 | `event_deduction` | `["investment_theme", "industry_expert_research", "adversarial_thinking", "future"]` | 2 | 4 |

### N1 探针设计 Prompt

```
你是投资分析师。你已读完这只股票的原始事件和AI深度研究。

## 你的任务
为这只股票设计侦查探针。每个探针是一个需要上网搜索才能回答的具体问题。

## 你需要覆盖的方向
1. **管理层叙事**: 管理层怎么描述公司战略和变革？
2. **硬数据印证**: 分产品收入结构变化？毛利率趋势？
3. **市场预期**: 券商一致预期？覆盖券商数？市场偏见？
4. **关注度与信息差**: 机构持仓变化？散户认知？市值<$1B→机构不能买？
5. **估值锚**: 估值隐含假设？叙事兑现/落空的锚迁移？同环节可比市值(不要P/E)
6. **核心叙事**: if-then命题

## 探针设计原则
- 每个探针必须引用事件中的具体细节（数字、产品名、客户名）
- 每个探针是独立的——上下文必须自包含
- 如果事件已足够回答某方向，不为它设探针
- 不要问"分析竞争格局"这种泛问题

## 输出格式
纯JSON:
{
  "probes": [
    {"name": "简短标题(≤15字)", "task": "具体侦查问题(50-150字)"},
    ...
  ],
  "coverage_note": "哪些方向被覆盖, 哪些方向因事件信息已充分而跳过"
}

生成 3-6 个探针。
```

### N2 探针设计 Prompt（关键：基于投资主题设计）

```
你是产业链分析师。你已读完投资主题报告，理解了这只股票的核心叙事和关键假设。

## 你的任务
基于投资主题报告中揭示的核心矛盾，为产业链和竞争卡位维度设计侦查探针。

## 你需要覆盖的方向
1. **产业链位置**: 公司处于产业链什么位置？紧邻上下游？
2. **供给格局**: 全球CR3？公司排位？认证周期？扩产需多久？
3. **需求确定度**: 需求确定性来源(合同/政策/物理约束)？能持续多少年？
4. **价值捕获**: 定价权——涨价频率？毛利率趋势？客户切换成本？
5. **卡点检查(Serenity 4条)**:
   (a)人人都需要？(b)供给集中+难扩产？
   (c)市值vsBOM错配？(d)会被designed-out？
6. **反方证据**: 哪些事实会让地位稳固的叙事不成立？

## 探针设计原则
- 每个探针必须引用投资主题报告中的具体判断
- 投资主题已搞清楚的事不要再问
- 每个探针独立、自包含

生成 3-6 个探针。
```

### N3 探针设计 Prompt（关键：基于投资主题+产业链找脆弱点）

```
你是逆向分析师。你已读完投资主题和产业链报告。

## 你的任务
找出两份报告中最脆弱的假设和逻辑漏洞，设计红蓝对抗探针。

## 你需要覆盖的方向
1. **核心假设脆弱性**: if-then命题中最脆弱的假设？什么证据会证伪？
2. **两大失效测试**: (a)会被designed-out？(b)卡点够material？
3. **利益博弈**: 谁最有动机和能力挤压公司利润？
4. **外部冲击**: 政策/技术替代/地缘政治/宏观周期
5. **论点破裂条件**: 什么条件发生时论点彻底破裂？

## 特殊要求: 红蓝对抗
每个探针的task中，必须要求Agent:
1. 先提出论点和证据
2. 执行魔鬼代言人挑战——至少2个有数据支撑的反驳点
3. 标注论点存活强度(强/中/弱)

生成 3-5 个探针。
```

### N4 探针设计 Prompt

```
你是催化剂分析师。你已读完前三份报告。

## 你的任务
找出未来6-12个月的关键催化事件。

覆盖: 财报节点 / 产品里程碑 / 资格认证拐点(Serenity视角) / 行业催化剂 / 风险节点

原则: 引用前序报告的具体时间节点; 优先P0级别; 前序已有明确时间的节点不要再搜。

生成 2-4 个探针。
```

### N5 探针设计 Prompt

```
你是推演分析师。你已读完前四份报告，拥有全景认知。

## 你的任务
推演三种时间尺度路径和论点破裂场景。

覆盖: T+30/90/180推演 / 论点破裂场景 / 历史案例参考

原则: 引用前序具体判断; 重点攻前序[数据缺失]或"存在分歧"的方向; 不重复已有推演。

生成 2-4 个探针。
```

### 单探针执行 Prompt

```
你是专项分析师。你的任务只有一个: {probe_task}

你有 bocha_search 工具。最多搜索 2 次。
第1次搜索覆盖面，第2次只补第1次发现的最大缺口。
搜完立即输出4项结论。不要写报告，只输出4项:

**结论**: [一句话直接回答问题]
**最强证据**: [具体数字, 标注来源]
**最大缺口**: [如实写缺什么信息, 不要编造]
**一手来源**: [需要补的原始数据/报告名称]
```

---

## 四、5 个字段的合并 Prompt（字段报告格式）

### investment_theme → 投资主题报告

```markdown
### 一、核心叙事 (if-then命题, ≤50字)

### 二、变革证据链
- 管理层叙事 + 硬数据印证 + 外部验证(含Serenity信息差标注)

### 三、关注度评估
- 机构覆盖 | 媒体渗透 | 散户认知 | 市场偏见
- Serenity: 市值<$1B→机构不能买？散户100%负面→反向信号？

### 四、估值锚与信息差
- 当前估值隐含假设 / 叙事兑现路径 / 下行风险
- Serenity: 同环节可比市值, 不要P/E

### 五、关键验证节点 (2-3个证实/证伪条件)
```

### industry_expert_research → 产业链报告

```markdown
### 一、产业链位置与需求确定度
(公司在哪一层 + 紧邻上下游 + 需求确定性来源与持续性)

### 二、供给格局与价值捕获
(全球CR3 + 公司排位 + 认证/扩产壁垒 + 定价权 + 毛利率 + 切换成本)

### 三、卡点检查与反方证据
Serenity 4条逐条检查 (✅/⚠️/❌):
1. 必要性
2. 供给集中
3. 市值vsBOM
4. 失效测试 (a)designed-out (b)material

反方证据: 技术替代/客户流失/新进入者威胁
```

### adversarial_thinking → 逆向推演报告

```markdown
### 维度1: 核心假设脆弱性
- 论点 / 魔鬼代言人挑战 / 存活强度: 强/中/弱

### 维度2: 两大失效测试
- 论点 / 魔鬼代言人挑战 / 存活强度

### 维度3: 利益博弈与利润挤压
- 论点 / 魔鬼代言人挑战 / 存活强度

### 维度4: 外部冲击
- 论点 / 魔鬼代言人挑战 / 存活强度

### 维度5: 论点破裂条件
Serenity: "论点变即砍仓甚至反手做空"
```

### future → 催化日历

```markdown
| 预计时间 | 事件 | 证实条件 | 证伪条件 | 优先级 |
|---------|------|---------|---------|:------:|
| ...     | ...  | ...     | ...     | P0/P1/P2 |

P0 = 一票确认或一票否决
```

### event_deduction → 事件推演报告

```markdown
### T+30 / T+90 / T+180
每个时间窗口: 最可能路径 / 关键分叉点 / 证实条件 / 证伪条件

### 论点破裂场景
T+30/90/180的破裂路径, 附转移概率

### 历史案例参考
类似事件的传导链和市场反应
```

---

## 五、N6 总装 Prompt

```
你是总编辑。你的任务是把5份顺序生成的语料做去重和交叉验证，输出一条完整的万业谱记录。

## 5份语料的生成顺序
N1(投资主题) → N2(产业链) → N3(逆向推演) → N4(催化日历) → N5(事件推演)
后序报告基于前序写成，已做部分交叉引用。

## 去重规则
1. N2中引用了N1内容的 → 保留在N1, N2中删重
2. N3中的风险判断与N5中的破裂场景重叠 → 保留在N3, N5中删重
3. 识别 knowledge_supplement — 搜索中获取但未被5份语料覆盖的补充信息

## 交叉验证规则
1. N1投资主题 vs N2产业链 → 是否自洽？
2. N2卡点检查 vs N3失效测试 → 逻辑一致？
3. N5推演 vs N1核心假设 → 有逻辑矛盾？
4. 不一致处标注"⚠️存在分歧"，不做调和

## 输出格式
纯JSON:
{
  "industry_expert_research": "...",
  "adversarial_thinking": "...",
  "investment_theme": "...",
  "future": "...",
  "event_deduction": "...",
  "knowledge_supplement": "...",
  "cross_validation": {
    "consistencies": ["一致点1: N1和N2独立得出..."],
    "divergences": ["分歧点1: N2认为...但N3认为..."]
  }
}
```

---

## 六、数据流与变量

### 工作流全局变量

| 变量名 | 来源 | 消费者 |
|--------|------|--------|
| `stock_name` | START | 所有节点 |
| `stock_code` | START | 所有节点 |
| `news_content` | START | N1-N5 (探针设计上下文) |
| `knowledge` | START | N1-N5 |
| `step_one` | START | N1-N5 |
| `investment_theme` | N1输出 | N2, N3, N4, N5, N6 |
| `industry_expert_research` | N2输出 | N3, N4, N5, N6 |
| `adversarial_thinking` | N3输出 | N4, N5, N6 |
| `future` | N4输出 | N5, N6 |
| `event_deduction` | N5输出 | N6 |
| `final_record` | N6输出 | N7 |
| `source_id` | START | N7 |
| `event_date` | START | N6, N7 |
| `event_source` | START | N6, N7 |
| `raw_text` | START | N6, N7 |
| `uuid` | START | N7 |
| `response_level` | START | N7 |

### 每个 N1-N5 节点的输入输出

输入: `stock_name`, `stock_code`, `news_content`, `knowledge`, `step_one` + 前序字段报告
输出: 一个 Markdown 格式的字段报告 + 统计信息(stderr)

---

## 七、工具配置

### bocha_search

```
POST https://api.bochaai.com/v1/web-search
参数: query, count(1-10), freshness("oneYear"), summary(true)
返回: 网页标题/来源/日期/摘要
```

### DeepSeek API

```
POST https://api.deepseek.com/chat/completions
模型: deepseek-v4-flash
参数: temperature=0, thinking={type:"enabled"}
```

探针设计调用: max_tokens=4096 | 探针执行调用: max_tokens=4096(FC模式), 2048(强制输出) | 合并调用: max_tokens=8192

---

## 八、在 Coze 中搭建

### 步骤 1: 创建工作流变量

在 Coze 工作流设置中创建上述全局变量。

### 步骤 2: 添加节点

1. **N1**: Code 节点，复制 `field_node.py`，修改顶部配置为 N1 参数
2. **N2**: Code 节点，复制 `field_node.py`，修改为 N2 参数
3. **N3**: Code 节点，复制 `field_node.py`，修改为 N3 参数
4. **N4**: Code 节点，复制 `field_node.py`，修改为 N4 参数
5. **N5**: Code 节点，复制 `field_node.py`，修改为 N5 参数
6. **N6**: LLM 节点，复制 `n6_assembler.json` 的 prompt
7. **N7**: Code 节点，复制 `n7_writer.py`

### 步骤 3: 配置依赖关系

在 Coze 画布中按 DAG 连接节点：
```
START → N1 → N2 → N3 → N4 → N5 → N6 → N7 → END
```

Coze 会自动处理顺序——每个节点只有在前序节点完成后才执行。

### 步骤 4: N1-N5 输出变量映射

在 Coze 中，每个 Code 节点的 `print()` 输出需要映射到正确的变量名：
- N1 输出 → `investment_theme`
- N2 输出 → `industry_expert_research`
- N3 输出 → `adversarial_thinking`
- N4 输出 → `future`
- N5 输出 → `event_deduction`

### 步骤 5: 配置 API Key

在 Coze 工作流的环境变量中设置:
- `DEEPSEEK_KEY`
- `BOCHA_KEY`

或者直接在 `field_node.py` 顶部的常量中硬编码。

---

## 九、文件清单

```
估值重构引擎_V5/src/coze_workflow/
├── DESIGN.md              ← 本文件（完整设计方案）
├── field_node.py          ← N1-N5 通用 Code 节点代码
├── node_configs.md        ← N1-N5 参数配置速查表
├── n6_assembler.json      ← N6 LLM 节点（可导入 Coze）
├── n7_writer.py           ← N7 Code 节点
└── README.md              ← 部署快速指南

测试脚本:
D:/长流水/test_coze_workflow.py   ← --mock 模式 12 项全通过
```

---

## 十、预估性能

| 指标 | 值 |
|------|-----|
| 工作流节点数 | 7 |
| LLM 调用数 | ~17-23 次（N1-N5 各含: 1次探针设计 + N次探针执行 + 1次合并） |
| 搜索次数 | ~16-28 次（8-14 个探针 × ≤2 次搜索） |
| 总耗时 | 3-5 分钟（取决于最慢探针） |
| 日均处理量 | ~200-300 条记录（24h 持续运行估算） |
