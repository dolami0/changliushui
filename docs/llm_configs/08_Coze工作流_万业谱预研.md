# Coze 工作流: 万业谱预研管线

> **类型**: Coze 平台 DAG 工作流（7-8 个节点，LLM + Code 混合）
> **目录**: `src/coze_workflow/`
> **触发**: 天机卷（原始资讯库）有新记录时自动触发
> **设计版本**: v5.1

---

## 架构总览

```
START → N0(Code:股票验证) → N1(LLM:事件消化+探针设计)
  → N2(Code:投资主题探针) ┐
  → N3(Code:行业研究探针) │
  → N4(Code:逆向推演探针) ├─ 5个并行节点
  → N5(Code:催化日历探针) │
  → N6(Code:事件推演探针) ┘
  → N7(LLM:总装+去重+交叉验证) → N8(Code:写Coze DB) → END
```

---

## N0: 股票代码验证

- **类型**: Code 节点
- **文件**: `n0_stock_validator.py` (195 行)
- **LLM**: 无
- **API**: 新浪行情 API (`hq.sinajs.cn`), 新浪建议 API (`suggest3.sinajs.cn`)

输入: 用户输入的股票代码或名称
输出: `is_valid`, `verified_name`, `stock_code`, `stock_market`

---

## N1: 事件消化 + 探针设计

- **类型**: LLM 节点
- **文件**: `n1_probe_designer.json` (33 行)

### LLM 配置

```json
{
  "model": "deepseek-v4-flash",
  "max_tokens": 4096,
  "temperature": 0.0,
  "thinking": {"type": "enabled"}
}
```

### 职责

1. 读取产业资讯，消化事件核心要点
2. 设计 15 个研究探针（5 维度 × 3 个），自由格式（不再用模板填充）
3. 输出 JSON: `{"probes_map": {"industry_expert_research": ["p1","p2","p3"], "adversarial_thinking": [...], "investment_theme": [...], "future": [...], "event_deduction": [...]}}`

### 5 个字段维度

| 字段 | 分析师视角 | 核心问题 |
|------|-----------|---------|
| investment_theme | 投资主题 | 市场在讲什么故事？变革证据链？ |
| industry_expert_research | 产业链专家 | 利润流向哪里？供给格局如何？ |
| adversarial_thinking | 逆向思考者 | 核心假设哪里最脆弱？ |
| future | 催化日历 | 什么事件会触发股价变动？ |
| event_deduction | 事件推演 | T+30/90/180 路径？ |

---

## N2-N6: 5 个并行字段探针节点

- **类型**: Code 节点（5 个并行，统一代码不同配置）
- **文件**: `field_node.py` (671 行)

### 每个节点的 4 步流程

```
Step 1: read_prior_reports   — 读取前序节点的字段报告
Step 2: design_probes         — LLM(Flash) 基于前序认知设计 3-6 个探针
Step 3: ThreadPool 并行执行   — 每个探针 ≤2 次 bocha_search
Step 4: merge_probes          — LLM(Flash) 合并为字段报告
```

### 节点配置差异

| 节点 | FIELD_NAME | PRIOR_FIELDS | PROBE_MIN | PROBE_MAX |
|------|-----------|-------------|-----------|-----------|
| N2 | investment_theme | [] | 3 | 6 |
| N3 | industry_expert_research | [investment_theme] | 3 | 6 |
| N4 | adversarial_thinking | [investment_theme, industry_expert_research] | 3 | 5 |
| N5 | future | [investment_theme, industry_expert_research, adversarial_thinking] | 2 | 4 |
| N6 | event_deduction | [前4个全部] | 2 | 4 |

### 单探针执行 LLM 配置

```json
{
  "model": "deepseek-v4-flash",
  "endpoint": "https://api.deepseek.com/chat/completions",
  "max_tokens": 8192,
  "temperature": 0.0,
  "thinking": {"type": "enabled"}
}
```

搜索工具: bocha_search (最多 2 次/探针)

### 5 个字段的合并 Prompt

每个字段有独立的合并 Prompt，定义在 `DESIGN.md` 和 `coze_llm_prompts.md`:

- **investment_theme**: 5 章（核心叙事、变革证据链、关注度评估、估值锚与信息差、关键验证节点）
- **industry_expert_research**: 4 章（产业链位置与需求确定度、供给格局与价值捕获、卡点检查与反方证据、天花板量化）
- **adversarial_thinking**: 5 维度（核心假设脆弱性、两大失效测试、利益博弈、外部冲击、论点破裂条件）
- **future**: 催化日历表格（P0/P1/P2，含证实/证伪条件）
- **event_deduction**: T+30/90/180 路径 + 论点破裂 + 历史案例

---

## N7: 总装 + 去重 + 交叉验证

- **类型**: LLM 节点
- **文件**: `n6_assembler.json` (39 行)

### LLM 配置

```json
{
  "model": "deepseek-v4-flash",
  "max_tokens": 8192,
  "temperature": 0.0,
  "thinking": {"type": "enabled"}
}
```

### 职责

1. **去重**: 行业研究和投资主题有相同产业链事实 → 保留在 ier；逆向思考和事件推演有相同风险判断 → 保留在 adv
2. **交叉验证**: ier vs theme 是否自洽；adv vs ded 逻辑是否一致
3. **补充**: 识别 5 份报告共同遗漏的信息

### 输出 JSON

```json
{
  "industry_expert_research": "...",
  "adversarial_thinking": "...",
  "investment_theme": "...",
  "future": "...",
  "event_deduction": "...",
  "knowledge_supplement": "...",
  "cross_validation": {
    "consistencies": [...],
    "divergences": [...]
  }
}
```

---

## N8: 写入 Coze 数据库

- **类型**: Code 节点
- **文件**: `n9_writer.py` (99 行)
- **LLM**: 无

### API

```python
COZE_BASE = "https://api.coze.cn/v1/databases"
DB_WANYEPU = "7639784337973477386"  # 万业谱（语料库）
DB_TIANJI = "7479116110479048754"   # 天机卷（原始资讯库）
```

### 操作

1. **POST** 万业谱: 14 个字段（stock_code, stock_name, event_date, event_source, raw_event_text, 5 个分析字段, knowledge_supplement, uuid, source_record_id, is_complete, created_at）
2. **PUT** 天机卷: 标记 `is_analyzed=true`

每个字段截断限制: 10000-15000 字符。

---

## 硬编码密钥（需在重构时解决）

| 文件 | 硬编码密钥 |
|------|-----------|
| `n3_field_probes.py` | `DEEPSEEK_KEY`, `BOCHA_KEY` |
| `n9_writer.py` | `COZE_TOKEN`, `DB_WANYEPU`, `DB_TIANJI` |

> Coze Code 节点无法读取 `.env` 文件。重构时建议将密钥配置为 Coze 工作流变量。

---

## 性能预估

| 指标 | 值 |
|------|-----|
| 节点数 | 8 |
| LLM 调用 | ~18 次 |
| 搜索调用 | ~25-30 次 |
| 总耗时 | 3-5 分钟 |
| 日均处理 | ~200-300 条 |
