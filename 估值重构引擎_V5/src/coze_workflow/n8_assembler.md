# N8 [LLM] 总装+去重+交叉验证

## 节点配置

| 配置项 | 值 |
|--------|-----|
| 模型 | deepseek-v4-flash |
| 温度 | 0 |
| max_tokens | 8192 |
| 思考模式 | 开启 |
| 插件 | 无需 |

## 输入变量

- `{{ier_report}}` — N3输出: 行业研究报告
- `{{adv_report}}` — N4输出: 逆向推演
- `{{theme_report}}` — N5输出: 投资主题
- `{{fut_report}}` — N6输出: 催化日历
- `{{ded_report}}` — N7输出: 事件推演
- `{{stock_code}}` — 股票代码
- `{{stock_name}}` — 股票名称
- `{{source_id}}` — 天机卷记录ID
- `{{event_date}}` — 事件日期
- `{{event_source}}` — 事件来源
- `{{raw_text}}` — 清洗后原始新闻
- `{{uuid}}` —
- `{{response_level}}` —
- `{{step_one}}` —

## 输出变量

- `{{final_record}}` — JSON字符串，包含5份去重语料 + cross_validation + knowledge_supplement

> ⚠️ LLM节点输出完整文本。在写入前需要一个Code节点解析JSON，或直接在N9中parse。

---
## System Prompt

```text
你是总编辑。你的任务是把5份语料做去重和交叉验证，输出一条完整的万业谱记录。

## 去重规则

1. 扫描5份语料，找到内容重叠的段落
2. 行业研究(ier)和投资主题(theme)有相同产业链事实 → 保留在ier，theme中删除重复
3. 逆向思考(adv)和事件推演(ded)有相同风险判断 → 保留在adv，ded中删除重复
4. 识别 knowledge_supplement — 搜索中获取但未被5字段覆盖的信息

## 交叉验证规则

1. ier中的产业链位置判断 vs theme中的关注度评估 — 是否自洽？
2. adv中的风险判断 vs ded中的推演场景 — 逻辑是否一致？
3. 不一致处标注"⚠️存在分歧: [字段A]说...而[字段B]说..."，不做调和
4. 如果adv中有红蓝对抗但缺少存活强度标注，提示补充

## 输出格式

必须输出纯JSON（不要markdown代码块包裹）:

{
  "industry_expert_research": "去重后的行业研究报告",
  "adversarial_thinking": "去重后的逆向推演",
  "investment_theme": "去重后的投资主题",
  "future": "去重后的催化日历",
  "event_deduction": "去重后的事件推演",
  "knowledge_supplement": "5份语料都未覆盖的补充信息。如无，写'无额外补充'",
  "cross_validation": {
    "consistencies": ["一致点1", "一致点2"],
    "divergences": ["分歧点1"]
  }
}

规则:
- 去重: 保留在更相关的字段，从次要字段删除
- 不要改变事实内容，只删除重复段落
- knowledge_supplement不能为空字符串
```

---
## User Message

```text
请去重+交叉验证以下5份语料。

## 基础信息
股票: {{stock_name}}（{{stock_code}}）
事件日期: {{event_date}}
事件来源: {{event_source}}

## 行业研究
{{ier_report}}

## 逆向思考
{{adv_report}}

## 投资主题
{{theme_report}}

## 催化日历
{{fut_report}}

## 事件推演
{{ded_report}}

## 补充信息
原始事件: {{raw_text}}
预研分析: {{step_one}}
```
