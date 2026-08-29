# Agent-0 / Agent-1（无 LLM）

> 本文件是 [管线提示词全集](../管线提示词全集.md) 的分册。提示词正文均为源码原文，未摘要。

## 本册目录

- [Agent-0 预路由（无 LLM prompt）](#agent-0-预路由-无-llm-prompt) — `估值重构引擎_V5/src/agent0_pre_router.py`
- [Agent-1 数据锻造（无 LLM prompt）](#agent-1-数据锻造-无-llm-prompt) — `估值重构引擎_V5/src/agent1_data_forge.py`

---
<a id="agent-0-预路由-无-llm-prompt"></a>
## Agent-0 预路由（无 LLM prompt）

- **源码**: `估值重构引擎_V5/src/agent0_pre_router.py`  · 行 模块
- **符号**: `Agent-0 预路由（无 LLM prompt）`
- **管线阶段**: 管线 C · Agent-0
- **类型**: str · 算术/规则（无 LLM）
- **说明**: 无提示词。列入以免被误认为遗漏。

### 提示词正文

```text
本模块为纯规则引擎，无 system/user prompt，无 call_deepseek。
输入：行业分类 + 事件标签 + 预研语料；输出：data_requirements + 非绑定 model_hint。
详见 docs/llm_configs/01_Agent0_预路由.md。
```

<a id="agent-1-数据锻造-无-llm-prompt"></a>
## Agent-1 数据锻造（无 LLM prompt）

- **源码**: `估值重构引擎_V5/src/agent1_data_forge.py`  · 行 模块
- **符号**: `Agent-1 数据锻造（无 LLM prompt）`
- **管线阶段**: 管线 C · Agent-1
- **类型**: str · 算术/规则（无 LLM）
- **说明**: 无提示词。

### 提示词正文

```text
本模块从 Tushare/investoday 拉财务包并做清洗/异常标记，无 LLM 调用。
下游 Agent-Baseline / 2 / 3 消费其 packages.core.fields。
```
