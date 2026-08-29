# Agent-3 情景估值（3/3）

> 本文件是 [管线提示词全集](../管线提示词全集.md) 的分册。提示词正文均为源码原文，未摘要。

## 本册目录

- [user_msg](#user_msg) — `估值重构引擎_V5/src/agent3_scenario_asymmetry.py`

---
<a id="user_msg"></a>
## user_msg

- **源码**: `估值重构引擎_V5/src/agent3_scenario_asymmetry.py`  · 行 1798-1821
- **符号**: `user_msg`
- **管线阶段**: 管线 C · Agent-3 情景估值
- **类型**: f-string · LLM 推演 + 代码算术
- **说明**: f-string 动态模板

### 提示词正文

```text
# 推演裁决: {stock}({code})
{baseline_section}
## 市场定价数据 (供清单项4b预期差分析参考，非参数输入)

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

## ⚡ 基数异常警示（仅B模型：TTM营收可能不反映真实经营能力）
```
