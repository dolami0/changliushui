# stashed 旧稿（2/3）

> 本文件是 [管线提示词全集](../管线提示词全集.md) 的分册。提示词正文均为源码原文，未摘要。

## 本册目录

- [user_msg](#user_msg) — `估值重构引擎_V5/src/agent3_scenario_asymmetry_stashed.py`
- [VOLC_QUERY_GEN_PROMPT](#volc_query_gen_prompt) — `估值重构引擎_V5/src/agent3s_sotp_stashed.py`

---
<a id="user_msg"></a>
## user_msg

- **源码**: `估值重构引擎_V5/src/agent3_scenario_asymmetry_stashed.py`  · 行 1337-1360
- **符号**: `user_msg`
- **管线阶段**: stashed 旧稿（已被现行文件替代）
- **类型**: f-string · LLM 推演 + 代码算术
- **说明**: f-string 动态模板

### 提示词正文

```text
# 推演裁决: {stock}({code})
{baseline_section}
## 当前市值隐含假设 (Implied Story) — 根据估值锚({anchor_2a})选择工具

{bs_section}{bs_warning}
- PE: {bs_profile['pe_ttm']}x PB: {bs_profile['pb']}x
- 警告: {json.dumps(bs_profile.get('warnings', []), ensure_ascii=False)}
{bs_profile.get('note_to_llm', '')}

## WACC参数 (代码预计算,不可修改)
- rf: {wacc_params['rf_pct']}% (来源: {wacc_params.get('rf_source', '')})
- beta: {wacc_params['beta']} (来源: {wacc_params.get('beta_source', '')})
- ERP: {wacc_params['erp_pct']}% ({wacc_params.get('erp_method', '')})
- WACC: {wacc_params['wacc_pct']}% (re={wacc_params['re_pct']}% rd={wacc_params['rd_pct']}% D/E={wacc_params['d_ratio_pct']}%)
- 注: {wacc_params.get('note', '')}

## 路由判决
- 主模型: {primary} ({category})
- 路由理由: {reason}
- 校验模型: {routing.get('validation_models', [])}
- 迁移路径: {json.dumps(routing.get('model_migration_path', {}), ensure_ascii=False)}

## Agent-2a 叙事诊断结论（已审核，可直接信任）
```

<a id="volc_query_gen_prompt"></a>
## VOLC_QUERY_GEN_PROMPT

- **源码**: `估值重构引擎_V5/src/agent3s_sotp_stashed.py`  · 行 83-97
- **符号**: `VOLC_QUERY_GEN_PROMPT`
- **管线阶段**: stashed 旧稿（已被现行文件替代）
- **类型**: str · LLM + 算术

### 提示词正文

```text
你是 SOTP 分部估值的数据获取助手。当前管线需要对 {stock_name}({stock_code}) 做分部估值（Sum of the Parts）：拆成不同业务线，各自独立估值后加总。

火山引擎是一个结构化知识问答系统。给它一个清晰的 query，它会从券商研报、公司公告、行业数据中提取结构化的答案。

根据以下叙事背景，生成一个查询该公司的 query。你想获取每个业务线的：
- 收入规模和增速
- 毛利率或净利率
- 未来2-3年券商收入预测
- 可比A股公司及估值倍数
- 产能、出货量等运营数据

叙事背景:
{context}

直接输出query，不要引号、不要解释。
```
