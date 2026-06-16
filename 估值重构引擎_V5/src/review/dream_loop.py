"""
审阅系统 · Dream Loop 自进化引擎

灵感来源：觀瀾 (jesson-hh/financial-analyst) 的 Dream Loop

核心原则：
  - 不自动合入改进 — 提案写入 _proposed/，人工审阅后合入
  - 累积审计日志 → 跨运行模式发现 → 生成具体改进提案
  - 提案需注明改什么、为什么、预期效果、潜在副作用

用法：
  from review.dream_loop import DreamLoop

  dl = DreamLoop()
  dl.accumulate(audit)          # 每次管线运行后调用
  proposals = dl.dream(since_days=7)  # 定期触发，生成提案
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from env_config import DEEPSEEK_API_KEY
from review.prompts import DREAM_LOOP_SYSTEM
from review.taxonomy import ERROR_TYPE

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DREAM_MODEL = "deepseek-v4-flash"

# 目录
_REVIEW_DIR = Path(__file__).resolve().parent
_LOG_DIR = _REVIEW_DIR / "audit_logs"
_PROPOSED_DIR = _REVIEW_DIR / "_proposed"
_ARCHIVE_ACCEPTED = _PROPOSED_DIR / "archive" / "accepted"
_ARCHIVE_REJECTED = _PROPOSED_DIR / "archive" / "rejected"

# 确保目录存在
for _d in [_LOG_DIR, _PROPOSED_DIR, _ARCHIVE_ACCEPTED, _ARCHIVE_REJECTED]:
    _d.mkdir(parents=True, exist_ok=True)


class DreamLoop:
    """自进化引擎。"""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.model = DREAM_MODEL

    # ── 公开方法 ──────────────────────────────

    def accumulate(self, audit: dict, *, stock_code: str = "") -> str:
        """
        将一次审阅结果写入审计日志。

        返回日志文件路径。
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{stock_code or 'unknown'}.json"
        path = _LOG_DIR / filename

        with open(path, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)

        return str(path)

    def dream(self, *, since_days: int = 7) -> dict:
        """
        触发一次 Dream Loop：聚合近期审计日志，生成改进提案。

        since_days: 回溯天数。

        返回 dict:
          - patterns: 重复出现的模式列表
          - proposals_written: 已写入 _proposed/ 的提案文件名列表
          - logs_scanned: 扫描的日志数量
        """
        logs = self._load_recent_logs(since_days)

        if len(logs) < 3:
            return {
                "patterns": [],
                "proposals_written": [],
                "logs_scanned": len(logs),
                "note": f"日志不足（{len(logs)} 条），至少需要 3 条才能做模式发现",
            }

        # 微聚合：先用代码做简单的频率统计，帮 LLM 省 token
        hints = self._micro_aggregate(logs)

        # LLM 聚合
        patterns = self._call_dream_llm(logs, hints)

        # 写入提案
        written = []
        for p in patterns:
            fname = self._write_proposal(p)
            if fname:
                written.append(fname)

        return {
            "patterns": patterns,
            "proposals_written": written,
            "logs_scanned": len(logs),
        }

    def list_proposals(self) -> list[str]:
        """列出 _proposed/ 中待审阅的提案文件。"""
        return sorted(
            str(p) for p in _PROPOSED_DIR.glob("*.md")
            if p.name not in ("PROPOSALS.md", "README.md")
        )

    def accept(self, proposal_filename: str) -> str:
        """将提案移至 accepted/。"""
        return self._move_proposal(proposal_filename, _ARCHIVE_ACCEPTED)

    def reject(self, proposal_filename: str) -> str:
        """将提案移至 rejected/。"""
        return self._move_proposal(proposal_filename, _ARCHIVE_REJECTED)

    # ── 内部方法 ──────────────────────────────

    def _load_recent_logs(self, since_days: int) -> list[dict]:
        """加载最近 N 天的审计日志。"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
        logs = []

        for f in sorted(_LOG_DIR.glob("*.json"), reverse=True):
            try:
                # 从文件名提取时间戳
                ts_str = f.stem[:15]  # YYYYMMDD_HHMMSS
                ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
                with open(f, "r", encoding="utf-8") as fh:
                    logs.append(json.load(fh))
            except (ValueError, json.JSONDecodeError):
                continue

        return logs

    def _micro_aggregate(self, logs: list[dict]) -> str:
        """
        代码层预先统计高频问题，生成提示给 LLM 节省 token。

        返回自然语言摘要。
        """
        grades = {}
        dims = {}
        types = {}

        for log in logs:
            g = log.get("quality_grade", "?")
            grades[g] = grades.get(g, 0) + 1

            # L1 issues
            l1 = log.get("layer1", {})
            for e in l1.get("echoes", []):
                k = f"回聲: {e.get('claim', '')[:60]}"
                types[k] = types.get(k, 0) + 1
            for b in l1.get("blind_spots", []):
                k = f"盲区: {b[:60]}"
                types[k] = types.get(k, 0) + 1

            # individual quality
            iq = l1.get("individual_quality", {})
            for field, q in iq.items():
                if isinstance(q, dict) and q.get("depth") == "shallow":
                    k = f"浅层报告: {field}"
                    types[k] = types.get(k, 0) + 1

            # L2 issues
            l2 = log.get("layer2", {})
            ba = l2.get("baseline_absorption", {})
            if isinstance(ba, dict) and ba.get("status") in ("partial", "poor"):
                k = f"吸收度不足: {ba.get('status')}"
                types[k] = types.get(k, 0) + 1

            ac = l2.get("anchor_chain", {})
            if isinstance(ac, dict) and ac.get("drift"):
                k = "锚定漂移"
                types[k] = types.get(k, 0) + 1

        # 只保留出现 3+ 次的高频项
        frequent = {k: v for k, v in types.items() if v >= 3}

        if not frequent:
            return "近期无高频问题模式。"

        lines = ["## 代码层预聚合（高频问题）\n"]
        lines.append(f"质量分布: {grades}\n")
        for k, v in sorted(frequent.items(), key=lambda x: -x[1]):
            lines.append(f"- [{v}次] {k}")

        return "\n".join(lines)

    def _call_dream_llm(self, logs: list[dict], hints: str) -> list[dict]:
        """调用 LLM 做模式发现。"""
        # 每条日志只传关键字段，减少 token
        slim_logs = []
        for log in logs:
            slim_logs.append({
                "quality_grade": log.get("quality_grade"),
                "summary": log.get("summary", ""),
                "layer1": {
                    "individual_quality": log.get("layer1", {}).get("individual_quality", {}),
                    "cross_consistency": log.get("layer1", {}).get("cross_consistency", {}),
                    "echoes": log.get("layer1", {}).get("echoes", []),
                    "blind_spots": log.get("layer1", {}).get("blind_spots", []),
                },
                "layer2": {
                    "baseline_absorption": log.get("layer2", {}).get("baseline_absorption", {}),
                    "anchor_chain": log.get("layer2", {}).get("anchor_chain", {}),
                    "scenario_coherence": log.get("layer2", {}).get("scenario_coherence", {}),
                },
                "improvement_suggestions": log.get("improvement_suggestions", []),
            })

        user_msg = (
            f"以下是过去 {len(logs)} 次管线运行的审阅记录（已压缩关键字段）。\n\n"
            f"{hints}\n\n"
            f"## 审阅记录\n\n"
            f"```json\n{json.dumps(slim_logs, ensure_ascii=False, indent=2)}\n```\n\n"
            f"请找出重复出现的模式，生成改进提案。"
        )

        try:
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
                        {"role": "system", "content": DREAM_LOOP_SYSTEM},
                        {"role": "user", "content": user_msg},
                    ],
                },
                timeout=120,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()

            # 简单 JSON 提取
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()

            return json.loads(raw).get("patterns", [])

        except Exception:
            return []

    def _write_proposal(self, pattern: dict) -> str | None:
        """将单个模式写成提案 Markdown 文件。"""
        proposal = pattern.get("proposal", {})
        title = proposal.get("title", pattern.get("pattern_name", "未命名"))
        if not title:
            return None

        # 安全文件名
        safe_title = "".join(c for c in title if c.isalnum() or c in "._- ")
        safe_title = safe_title[:50].strip()
        date_str = datetime.now().strftime("%Y-%m-%d")
        fname = f"{date_str}_{safe_title}.md"

        content = f"""# [提案] {title}

## 触发数据
- 模式: {pattern.get('pattern_name', '')}
- 频率: {pattern.get('frequency', '')}
- 受影响维度: {pattern.get('affected_dimension', '')}

## 问题诊断
{pattern.get('description', '')}

## 根因
{pattern.get('root_cause', '')}

## 建议修改
- **目标**: {proposal.get('target', '')}
- **改动**: {proposal.get('change', '')}
- **风险**: {proposal.get('risk', '无')}

## 影响评估
- 如果合入，哪些管线节点受影响？
- 是否需要两端同步修改（Coze + Python）？

---

*由 Dream Loop 自动生成 — 待人工审阅。*
*审阅后: 移动到 archive/accepted/ 或 archive/rejected/*
"""
        path = _PROPOSED_DIR / fname
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return fname

    def _move_proposal(self, filename: str, target_dir: Path) -> str:
        """将提案文件移动到指定目录。"""
        src = _PROPOSED_DIR / filename
        if not src.exists():
            raise FileNotFoundError(f"提案文件不存在: {filename}")
        dst = target_dir / filename
        # 如果目标已存在，加后缀
        if dst.exists():
            dst = target_dir / f"{src.stem}_{datetime.now().strftime('%H%M%S')}{src.suffix}"
        src.rename(dst)
        return str(dst)


# ═══════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════

def quick_dream(since_days: int = 7) -> dict:
    """一行触发 Dream Loop。"""
    return DreamLoop().dream(since_days=since_days)
