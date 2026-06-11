# 字段节点(N1-N5) Coze 部署配置

每个节点使用相同的 `field_node.py` 代码，修改顶部 `==== 节点配置 ====` 部分即可。

## N1: 投资主题 (第一步，无前序)

```python
FIELD_NAME = "investment_theme"
PRIOR_FIELDS = []
PROBE_MIN = 3
PROBE_MAX = 6
```

输入变量: `stock_name`, `stock_code`, `news_content`, `knowledge`, `step_one`
输出变量: `investment_theme` (字段报告文本)

Coze中N1的输出变量名必须是 `investment_theme`，因为N2会按字段名读取。

---

## N2: 产业链+竞争卡位 (第二步，读投资主题)

```python
FIELD_NAME = "industry_expert_research"
PRIOR_FIELDS = ["investment_theme"]
PROBE_MIN = 3
PROBE_MAX = 6
```

输入变量: `stock_name`, `stock_code`, `news_content`, `knowledge`, `step_one`, `investment_theme` (N1输出)
输出变量: `industry_expert_research`

关键: 探针设计Prompt会收到投资主题全文，要求每个探针**引用投资主题中的具体判断**。

---

## N3: 逆向推演+红蓝对抗 (第三步，读投资主题+产业链)

```python
FIELD_NAME = "adversarial_thinking"
PRIOR_FIELDS = ["investment_theme", "industry_expert_research"]
PROBE_MIN = 3
PROBE_MAX = 5
```

输入变量: 前序 + `investment_theme`, `industry_expert_research`
输出变量: `adversarial_thinking`

关键: 探针设计Prompt会收到投资主题和产业链两份报告，要求**找出两份报告中最脆弱的假设**来设计攻击探针。

---

## N4: 催化日历 (第四步，读前三份)

```python
FIELD_NAME = "future"
PRIOR_FIELDS = ["investment_theme", "industry_expert_research", "adversarial_thinking"]
PROBE_MIN = 2
PROBE_MAX = 4
```

输入变量: 前序 + `investment_theme`, `industry_expert_research`, `adversarial_thinking`
输出变量: `future`

关键: 探针更少，因为催化节点是"证实/证伪前序报告中的判断"，不是凭空搜索。

---

## N5: 事件推演 (第五步，读前四份)

```python
FIELD_NAME = "event_deduction"
PRIOR_FIELDS = ["investment_theme", "industry_expert_research", "adversarial_thinking", "future"]
PROBE_MIN = 2
PROBE_MAX = 4
```

输入变量: 前序 + 全部4份前序报告
输出变量: `event_deduction`

关键: 最"轻"的字段——推演基于已有认知，搜索只补历史案例和特定数据点。

---

## 节点内部流程 (每个N1-N5都一样)

```
┌─ Code节点内部 ─────────────────────────────────┐
│                                                │
│ ① 读前序报告 (PRIOR_FIELDS指定的字段)            │
│    N1跳过此步                                   │
│                                                │
│ ② LLM设计探针                                   │
│    System: FIELD_DESIGN_PROMPTS[field_name]     │
│    User: 原始事件 + 知识 + 前序报告全文           │
│    → 输出JSON: {probes: [...], coverage_note}   │
│    → 探针数由LLM决定(PROBE_MIN~MAX范围内)        │
│                                                │
│ ③ ThreadPool并行执行探针                         │
│    run_single_probe × N                         │
│    每个: 干净上下文, ≤2搜, 4项结论               │
│                                                │
│ ④ LLM合并探针                                   │
│    System: FIELD_MERGE_PROMPTS[field_name]      │
│    → 输出: 字段报告 (Markdown)                   │
│                                                │
│ ⑤ print(字段报告) → Coze读取→传递下游            │
│                                                │
└────────────────────────────────────────────────┘
```
