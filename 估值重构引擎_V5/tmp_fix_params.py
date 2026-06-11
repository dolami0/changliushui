"""Quick fix: re-apply baseline_report params to 3 files"""
import re

# === agent2a_narrative.py ===
path = "src/agent2a_narrative.py"
text = open(path, encoding='utf-8').read()

text = text.replace(
    "volc_data: dict | None = None,\n    ) -> dict:\n        \"\"\"\n        执行叙事诊断。",
    "volc_data: dict | None = None,\n        baseline_report: str | None = None,\n    ) -> dict:\n        \"\"\"\n        执行叙事诊断。"
)
text = text.replace(
    "volc_data: V6.5 火山联网搜索预取数据（券商分部拆分+可比估值, 用于锚判断+SOTP判定）\n\n        返回",
    "volc_data: V6.5 火山联网搜索预取数据\n        baseline_report: V7 Agent-Baseline 投资地图报告\n\n        返回"
)
text = text.replace(
    'user_msg = _build_narrative_user_message(\n            data_package, event_data, pricing_all,\n            volc_data=volc_data,\n        )',
    'user_msg = _build_narrative_user_message(\n            data_package, event_data, pricing_all,\n            volc_data=volc_data,\n            baseline_report=baseline_report,\n        )'
)
text = text.replace(
    "def _build_narrative_user_message(\n    data_package: dict,\n    event_data: dict,\n    pricing_all: dict,\n    volc_data: dict | None = None,\n) -> str:\n    \"\"\"构建 Agent-2a 的用户消息",
    "def _build_narrative_user_message(\n    data_package: dict,\n    event_data: dict,\n    pricing_all: dict,\n    volc_data: dict | None = None,\n    baseline_report: str | None = None,\n) -> str:\n    \"\"\"构建 Agent-2a 的用户消息"
)
text = text.replace(
    '    msg = f"""# 叙事诊断: {stock}({code})\n\n## 估值倍数全矩阵',
    '    # V7 baseline\n    bs = ""\n    if baseline_report and len(baseline_report) > 100:\n        bs = f"""\n## 投资地图 - Agent-Baseline (主输入)\n\n{baseline_report}\n\n---\n"""\n\n    msg = f"""# 叙事诊断: {stock}({code})\n{bs}\n## 估值倍数全矩阵'
)
open(path, 'w', encoding='utf-8').write(text)
print(f"OK {path}")

# === agent3_scenario_asymmetry.py ===
path = "src/agent3_scenario_asymmetry.py"
text = open(path, encoding='utf-8').read()

text = text.replace(
    "def _call_llm_scenario(\n    bs_profile: dict,\n    wacc_params: dict,\n    data_package: dict,\n    routing: dict,\n    event_data: dict,\n    agent2a_output: dict | None = None,\n    volc_data: dict | None = None,\n) -> dict:\n    \"\"\"单次 LLM 调用：完整推演裁决（V6: 信任 Agent-2a 诊断结论）。\"\"\"",
    "def _call_llm_scenario(\n    bs_profile: dict,\n    wacc_params: dict,\n    data_package: dict,\n    routing: dict,\n    event_data: dict,\n    agent2a_output: dict | None = None,\n    volc_data: dict | None = None,\n    baseline_report: str | None = None,\n) -> dict:\n    \"\"\"单次 LLM 调用：完整推演裁决（V7: 投资地图 + V6: 信任 Agent-2a 诊断结论）。\"\"\""
)
text = text.replace(
    '    user_msg = f"""# 推演裁决: {stock}({code})\n\n## 当前市值隐含假设',
    '    # V7 baseline\n    bs = ""\n    if baseline_report and len(baseline_report) > 100:\n        bs = f"""\n## 投资地图 - Agent-Baseline (主输入)\n\n{baseline_report}\n\n---\n"""\n\n    user_msg = f"""# 推演裁决: {stock}({code})\n{bs}\n## 当前市值隐含假设'
)
text = text.replace(
    "def run(\n        self,\n        data_package: dict,\n        routing_decision: dict,\n        event_data: dict | None = None,\n        progress_cb: Callable[[int, str], None] | None = None,\n        agent2a_output: dict | None = None,\n        volc_data: dict | None = None,\n    ) -> dict:",
    "def run(\n        self,\n        data_package: dict,\n        routing_decision: dict,\n        event_data: dict | None = None,\n        progress_cb: Callable[[int, str], None] | None = None,\n        agent2a_output: dict | None = None,\n        volc_data: dict | None = None,\n        baseline_report: str | None = None,\n    ) -> dict:"
)
# Pass baseline_report in _call_llm_scenario calls
text = text.replace(
    "llm_output = _call_llm_scenario(\n                bs_profile, wacc_params, data_package,\n                routing_decision, event_data,\n                agent2a_output=agent2a_output,\n                volc_data=volc_data,\n            )",
    "llm_output = _call_llm_scenario(\n                bs_profile, wacc_params, data_package,\n                routing_decision, event_data,\n                agent2a_output=agent2a_output,\n                volc_data=volc_data,\n                baseline_report=baseline_report,\n            )"
)
# Retry block
text = text.replace(
    "llm_output = _call_llm_scenario(\n                        bs_profile, wacc_params, data_package,\n                        routing_decision, event_data,\n                        agent2a_output=agent2a_output,\n                        volc_data=volc_data,\n                    )",
    "llm_output = _call_llm_scenario(\n                        bs_profile, wacc_params, data_package,\n                        routing_decision, event_data,\n                        agent2a_output=agent2a_output,\n                        volc_data=volc_data,\n                        baseline_report=baseline_report,\n                    )"
)
open(path, 'w', encoding='utf-8').write(text)
print(f"OK {path}")

# === agent3s_sotp.py ===
path = "src/agent3s_sotp.py"
text = open(path, encoding='utf-8').read()

text = text.replace(
    "def run(\n        self,\n        data_package: dict,\n        agent2a_output: dict,\n        agent2b_output: dict | None = None,\n        event_data: dict | None = None,\n        wacc_params: dict | None = None,\n        volc_data: dict | None = None,\n        progress_cb=None,\n    ) -> dict:",
    "def run(\n        self,\n        data_package: dict,\n        agent2a_output: dict,\n        agent2b_output: dict | None = None,\n        event_data: dict | None = None,\n        wacc_params: dict | None = None,\n        volc_data: dict | None = None,\n        baseline_report: str | None = None,\n        progress_cb=None,\n    ) -> dict:"
)
text = text.replace(
    "user_msg = _build_sotp_user_message(\n            data_package, agent2a_output, agent2b_output, event_data, wacc_params,\n            volc_data=volc_data,\n        )",
    "user_msg = _build_sotp_user_message(\n            data_package, agent2a_output, agent2b_output, event_data, wacc_params,\n            volc_data=volc_data,\n            baseline_report=baseline_report,\n        )"
)
text = text.replace(
    "def _build_sotp_user_message(\n    data_package: dict,\n    agent2a_output: dict,\n    agent2b_output: dict | None,\n    event_data: dict,\n    wacc_params: dict,\n    volc_data: dict | None = None,\n) -> str:\n    \"\"\"构建 SOTP Agent 用户消息",
    "def _build_sotp_user_message(\n    data_package: dict,\n    agent2a_output: dict,\n    agent2b_output: dict | None,\n    event_data: dict,\n    wacc_params: dict,\n    volc_data: dict | None = None,\n    baseline_report: str | None = None,\n) -> str:\n    \"\"\"构建 SOTP Agent 用户消息"
)
text = text.replace(
    '    msg = f"""# SOTP 分部估值: {stock}({code})\n\n## 一、前置裁决',
    '    # V7 baseline\n    bs = ""\n    if baseline_report and len(baseline_report) > 100:\n        bs = f"""\n## 投资地图 - Agent-Baseline (主输入)\n\n{baseline_report}\n\n---\n"""\n\n    msg = f"""# SOTP 分部估值: {stock}({code})\n{bs}\n## 一、前置裁决'
)
open(path, 'w', encoding='utf-8').write(text)
print(f"OK {path}")

print("\nDone")
