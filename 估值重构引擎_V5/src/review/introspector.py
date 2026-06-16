"""
审阅系统 · Introspector 引擎

一次 LLM 调用，审阅两层：
  L1 — 预研语料质量（5份字段报告的深度+一致性+回聲）
  L2 — 估值链推理质量（Baseline 吸收度+推理链自洽+情景可信度）

用法:
  from review.introspector import Introspector
  inspector = Introspector(api_key=DEEPSEEK_API_KEY)
  audit = inspector.audit(
      event_data={...},           # 含 5 份字段报告
      baseline_report="...",      # Agent-Baseline 产出
      agent2_result={...},        # Agent-2 路由判决
      agent3_result={...},        # Agent-3 情景估值
  )
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from env_config import DEEPSEEK_API_KEY
from review.prompts import INTROSPECTOR_SYSTEM
from review.taxonomy import QUALITY_GRADE, ERROR_TYPE, SEVERITY, AUDIT_DIMENSIONS

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
INTROSPECTOR_MODEL = "deepseek-v4-flash"  # 审阅不需要深度推理，Flash 够快够便宜


class Introspector:
    """管线审阅师。一次调用审阅全链。"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.model = INTROSPECTOR_MODEL
        self._last_raw: str = ""
        self._last_usage: dict = {}

    # ── 公开方法 ──────────────────────────────

    def audit(
        self,
        event_data: dict,
        baseline_report: str,
        agent2_result: dict,
        agent3_result: dict,
        *,
        stock_name: str = "",
        stock_code: str = "",
    ) -> dict:
        """
        执行一次完整审阅。

        返回 dict:
          - quality_grade: A|B|C|D|F
          - summary: 一句话总结
          - layer1: {individual_quality, cross_consistency, echoes, blind_spots}
          - layer2: {baseline_absorption, anchor_chain, scenario_coherence, evidence_issues}
          - improvement_suggestions: [...]
          - meta: {model, usage, latency_ms, reviewed_at}
        """

        user_message = self._build_user_message(
            event_data, baseline_report, agent2_result, agent3_result,
            stock_name, stock_code,
        )

        raw, usage, latency = self._call_llm(user_message)
        self._last_raw = raw
        self._last_usage = usage

        parsed = self._parse(raw)

        parsed["meta"] = {
            "model": self.model,
            "usage": usage,
            "latency_ms": latency,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }

        return parsed

    # ── 内部方法 ──────────────────────────────

    def _build_user_message(
        self,
        event_data: dict,
        baseline_report: str,
        agent2_result: dict,
        agent3_result: dict,
        stock_name: str,
        stock_code: str,
    ) -> str:
        """构建发送给审阅 LLM 的 user message。"""

        parts = [
            f"# 审阅对象: {stock_name} ({stock_code})\n",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "## L1 · 预研语料（5份字段报告）\n",
        ]

        fields = [
            ("N1 投资主题", event_data.get("investment_theme", "")),
            ("N2 行业研究", event_data.get("industry_expert_research", "")),
            ("N5 事件推演", event_data.get("event_deduction", "")),
            ("N3 逆向推演", event_data.get("adversarial_thinking", "")),
            ("N4 催化日历", event_data.get("future", "")),
        ]

        for label, content in fields:
            truncated = self._truncate(content, max_chars=8000)
            parts.append(f"### {label} ({len(content)} 字)\n\n{truncated}\n")

        parts.append(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "## L2 · 估值链\n"
        )

        parts.append(
            f"### Agent-Baseline 投资地图 ({len(baseline_report)} 字)\n\n"
            f"{self._truncate(baseline_report, max_chars=8000)}\n"
        )

        parts.append(
            "### Agent-2 路由判决\n\n"
            f"```json\n{json.dumps(self._extract_routing(agent2_result), ensure_ascii=False, indent=2)}\n```\n"
        )

        parts.append(
            "### Agent-3 情景估值\n\n"
            f"```json\n{json.dumps(self._extract_scenarios(agent3_result), ensure_ascii=False, indent=2)}\n```\n"
        )

        parts.append(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "请按审阅清单逐项检查，输出 JSON。"
        )

        return "\n".join(parts)

    def _extract_routing(self, a2: dict) -> dict:
        """从 Agent-2 完整输出中提取审阅需要的关键字段。"""
        rd = a2.get("routing_decision", {})
        return {
            "primary_anchor": rd.get("primary_anchor", ""),
            "primary_model": rd.get("primary_model", ""),
            "event_distribution": rd.get("event_distribution", ""),
            "sotp_triggered": rd.get("sotp_triggered", False),
        }

    def _extract_scenarios(self, a3: dict) -> dict:
        """从 Agent-3 完整输出中提取审阅需要的关键字段。"""
        rt = a3.get("reasoning_trace", {})
        scenarios = a3.get("scenarios", {})

        def _summary(key: str) -> dict:
            s = rt.get(key, {}) if rt else {}
            sc = scenarios.get(key, {}) if scenarios else {}
            return {
                "narrative": s.get("narrative", "")[:300],
                "valuation": sc.get("valuation", s.get("valuation", "")),
                "key_variable": s.get("key_variable", ""),
            }

        return {
            "bull": _summary("bull"),
            "base": _summary("base"),
            "bear": _summary("bear"),
        }

    def _call_llm(self, user_message: str) -> tuple[str, dict, int]:
        """调用 DeepSeek，返回 (content, usage_dict, latency_ms)。"""
        import time
        t0 = time.time()

        resp = requests.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0,
                "max_tokens": 4096,
                "messages": [
                    {"role": "system", "content": INTROSPECTOR_SYSTEM},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        latency = int((time.time() - t0) * 1000)

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return content, usage, latency

    def _parse(self, raw: str) -> dict:
        """从 LLM 返回值中提取 JSON。含迭代转义修复。"""
        raw = raw.strip()

        for attempt in range(5):
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                # 尝试修复未转义的控制字符
                pos = e.pos
                if pos < len(raw):
                    problematic = raw[pos]
                    if problematic == "\n":
                        raw = raw[:pos] + "\\n" + raw[pos + 1:]
                        continue
                    if problematic == "\r":
                        raw = raw[:pos] + "\\r" + raw[pos + 1:]
                        continue
                    if problematic == "\t":
                        raw = raw[:pos] + "\\t" + raw[pos + 1:]
                        continue
                # 不是控制字符问题，尝试去 markdown 代码块
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                    continue
                if "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                    continue
                break

        # 解析失败，返回错误结构
        return {
            "quality_grade": "F",
            "summary": f"审阅 JSON 解析失败: {str(e) if 'e' in dir() else 'unknown'}",
            "layer1": {},
            "layer2": {},
            "improvement_suggestions": [],
            "parse_error": True,
        }

    @staticmethod
    def _truncate(text: str, max_chars: int = 8000) -> str:
        """截断长文本，保留首尾。"""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return (
            text[:half]
            + f"\n\n…[中间省略 {len(text) - max_chars} 字]…\n\n"
            + text[-half:]
        )


# ═══════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════


def quick_audit(
    event_data: dict,
    baseline_report: str,
    agent2_result: dict,
    agent3_result: dict,
    **kwargs,
) -> dict:
    """一行审阅。"""
    return Introspector().audit(event_data, baseline_report, agent2_result, agent3_result, **kwargs)
