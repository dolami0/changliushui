# Coze 工作流部署指南

## 架构（v5.1）

```
START
  │
  ▼
┌─────────────────────────────────────┐
│ N1 [LLM] 事件消化+探针设计           │
│ n1_probe_designer.json              │
│ 输入: 事件+知识 → 输出: 15个自由探针  │
└──────────────┬──────────────────────┘
               │ probes_map (JSON)
               ▼
    ┌──────────┼──────────┬──────────┬──────────┐
    ▼          ▼          ▼          ▼          ▼
┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐
│ N2-IER│ │ N3-ADV│ │ N4-THM│ │ N5-FUT│ │ N6-DED│
│ Code  │ │ Code  │ │ Code  │ │ Code  │ │ Code  │
│3探针→ │ │3探针→ │ │3探针→ │ │3探针→ │ │3探针→ │
│合并   │ │合并   │ │合并   │ │合并   │ │合并   │
└───┬──┘ └───┬──┘ └───┬──┘ └───┬──┘ └───┬──┘
    └────────┴───────┴───────┴───────┘
                    │ 5份字段报告
                    ▼
         ┌─────────────────────┐
         │ N7 [LLM] 总装+去重    │
         │ n7_assembler.md      │
         └──────────┬──────────┘
                    │ final_record
                    ▼
         ┌─────────────────────┐
         │ N8 [Code] 写入       │
         │ n8_writer.py         │
         └──────────┬──────────┘
                    ▼
                   END
```

**总节点数: 8**（比之前少了 N1-parse 和 N2-code）

## 文件清单

| 文件 | 节点 | 类型 | 说明 |
|------|------|------|------|
| `n1_probe_designer.json` | N1 | LLM | 🆕 事件消化+自由探针设计（合二为一） |
| `n3_field_probes.py` | N2-N6 | Code | 字段探针执行+合并（5个并行节点） |
| `n8_assembler.md` | N7 | LLM | 总装+去重+交叉验证 |
| `n9_writer.py` | N8 | Code | 写入万业谱+标记天机卷 |

### 已废弃

| 文件 | 原因 |
|------|------|
| ~~`n1_event_digest.md`~~ | 被 `n1_probe_designer.json` 替代 — 不再需要单独的事件分类LLM |
| ~~`n2_probe_allocator.py`~~ | 被 `n1_probe_designer.json` 替代 — 不再需要模板查表填充探针 |

## N1 核心变化

| | 旧设计 | 新设计 |
|---|---|---|
| 节点数 | N1(LLM分类)+N1-parse(Code)+N2(Code模板) | N1(LLM自由设计) |
| 探针来源 | Python字典模板，查表填充 | LLM基于事件理解自由生成 |
| 事件类型 | 8种硬分类 → 只有2套模板 | 不需要分类，LLM自然理解 |
| 探针质量 | 通用问题 | 引用事件具体细节的侦查问题 |

## 在 Coze 中搭建

### 1. 工作流变量

```
stock_name, stock_code, news_content, knowledge, step_one,
probes_map (JSON字符串),
ier_report, adv_report, theme_report, fut_report, ded_report,
final_record, source_id, event_date, event_source, raw_text,
uuid, response_level
```

### 2. 节点配置

| 节点 | 配置方式 |
|------|---------|
| N1 LLM | 复制 `n1_probe_designer.json` 中的 `system_prompt` 和 `user_message` |
| N2-N6 Code | 复制 `n3_field_probes.py`，每个节点修改 `field_name` |
| N7 LLM | 复制 `n8_assembler.md` 中的 prompt |
| N8 Code | 复制 `n9_writer.py` |

### 3. N2-N6 field_name 配置

| 节点 | field_name |
|------|-----------|
| N2 | `"industry_expert_research"` |
| N3 | `"adversarial_thinking"` |
| N4 | `"investment_theme"` |
| N5 | `"future"` |
| N6 | `"event_deduction"` |

### 4. N1 输出解析

N1 输出的是纯 JSON 文本（LLM 直接输出的）。如果 LLM 在 JSON 外包了 ```json``` 标签，需要在 N1 后面加一个 Code 节点清洗：

```python
import json, re
raw = """{{N1输出}}"""
match = re.search(r'\{[\s\S]*\}', raw)
if match:
    print(match.group())  # → probes_map
else:
    print(raw)
```

## 本地测试

```bash
python test_coze_workflow.py --mock    # Mock模式，不需要API key
python test_coze_workflow.py           # 真实API调用
```

## 预估性能

| 指标 | 值 |
|------|-----|
| 工作流节点数 | 8 |
| LLM调用数 | ~18次 (N1×1 + 15探针 + 5合并 + N7×1) |
| 搜索次数 | ~25-30次 |
| 总耗时 | 3-5分钟 |
