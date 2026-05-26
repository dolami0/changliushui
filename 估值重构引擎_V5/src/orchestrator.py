"""
宗门中枢 (Orchestrator) — V5

状态机 + 缓存 + 增量补取回退 + 评测模式 + 审计追踪。

职责:
  1. 按状态机编排 4-Agent 管线 (Agent-0→1→2→3)
  2. 增量补取闭环 (Agent-2 发现缺失→回退 Agent-1)
  3. 评测模式 (frozen 数据注入，跳过 Agent-0/1 数据拉取)
  4. 故障处理 (DeepSeek/Volcengine/investoday 故障降级)
  5. 审计追踪 (每个 Agent 的输入/输出/耗时/错误)

原则:
  - 唯一硬终止条件: core_package 数据不可用 (E101)
  - 其他一切故障降级处理
  - 增量补取最多1次回退
"""

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent0_pre_router import Agent0
from agent1_data_forge import DataForge, DataForgeError
from agent2_route_judge import RouteJudge
from agent3_scenario_asymmetry import ScenarioAsymmetry, ScenarioError
from env_config import DEEPSEEK_API_KEY


# ═══════════════════════════════════════
# 管线状态
# ═══════════════════════════════════════

@dataclass
class PipelineState:
    """管线执行状态追踪。"""
    stock_code: str
    stock_name: str
    request_id: str = ""
    phase: str = "init"
    status: str = "running"  # running | done | error | terminated

    # 各 Agent 输出
    agent0_output: dict | None = None
    agent1_output: dict | None = None
    agent2_output: dict | None = None
    agent3_output: dict | None = None

    # 增量补取
    incremental_fetch_count: int = 0

    # 审计
    started_at: str = ""
    completed_at: str = ""
    step_times: dict[str, float] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════

class Orchestrator:
    """V5 管线编排器 — 状态机 + 缓存 + 评测模式。"""

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key or DEEPSEEK_API_KEY
        self._cache: dict[str, Any] = {}  # 按 stock_code 缓存各层输出
        self._eval_mode = False
        self._frozen_data: dict | None = None

    def enable_eval_mode(self, frozen_data: dict | None = None):
        """启用评测模式：跳过 Agent-0/Agent-1，注入 frozen 数据。"""
        self._eval_mode = True
        self._frozen_data = frozen_data

    def disable_eval_mode(self):
        """关闭评测模式，恢复正常管线。"""
        self._eval_mode = False
        self._frozen_data = None

    def run(
        self,
        stock_code: str,
        event_data: dict | None = None,
        progress_cb: Callable[[str, int, int, str, str], None] | None = None,
    ) -> dict:
        """
        执行完整 4-Agent 管线。

        progress_cb(stage, step, total, status, message)
          stage: agent0|agent1|agent2|agent3
          step: 当前步骤序号
          total: 总步骤数
          status: running|done|error
          message: 步骤描述
        """
        cb = progress_cb or (lambda *a: None)
        event_data = event_data or {}
        state = PipelineState(
            stock_code=stock_code,
            stock_name=event_data.get("stock_name", stock_code),
        )

        try:
            # ── Agent-0: 预路由 ──
            cb("agent0", 1, 1, "running", "预路由")
            t0 = time.time()
            state.agent0_output = self._run_agent0(stock_code, event_data)
            state.step_times["agent0"] = round(time.time() - t0, 2)
            cb("agent0", 1, 1, "done", f"行业:{state.agent0_output.get('pre_routing_result',{}).get('industry_classification','?')}")

            # ── Agent-1: 数据炼器 ──
            if self._eval_mode and self._frozen_data:
                cb("agent1", 1, 1, "running", "注入frozen数据(评测模式)")
                frozen = self._frozen_data.get("frozen_agent1", {})
                # 规范化 frozen 数据为标准 data_package 格式
                state.agent1_output = self._normalize_frozen(frozen, stock_code,
                                                             event_data.get("stock_name", ""))
                cb("agent1", 1, 1, "done", "frozen数据已注入")
            else:
                cb("agent1", 1, 1, "running", "数据拉取")
                t0 = time.time()
                state.agent1_output = self._run_agent1(
                    state.agent0_output.get("pre_routing_result", {}))
                state.step_times["agent1"] = round(time.time() - t0, 2)
                cb("agent1", 1, 1, "done",
                   f"quality={state.agent1_output.get('overall_data_quality_score','?')}")

            # ── Agent-2: 路由判官 ──
            cb("agent2", 1, 1, "running", "路由判决")
            t0 = time.time()
            state.agent2_output = self._run_agent2(state.agent1_output, event_data)

            # 增量补取检查（评测模式跳过）
            inc = state.agent2_output.get("incremental_fetch_request", {})
            if inc.get("triggered") and state.incremental_fetch_count < 1 and not self._eval_mode:
                state.incremental_fetch_count += 1
                cb("agent2", 1, 3, "running", f"增量补取:{inc.get('missing_fields')}")
                # 仅补取缺失字段
                forge = DataForge()
                forge.run(state.agent0_output.get("pre_routing_result", {}))  # re-init
                extra = forge.fetch_incremental(inc["missing_fields"])
                # 合并到数据包
                core = state.agent1_output.get("packages", {}).get("core", {}).get("fields", {})
                core.update(extra)
                # 重新路由
                state.agent2_output = self._run_agent2(state.agent1_output, event_data)
            state.step_times["agent2"] = round(time.time() - t0, 2)
            rd = state.agent2_output.get("routing_decision", {})
            cb("agent2", 1, 1, "done", f"模型:{rd.get('primary_model','?')}")

            # ── Agent-3: 推演裁决 ──
            cb("agent3", 1, 1, "running", "推演裁决")
            t0 = time.time()
            state.agent3_output = self._run_agent3(
                state.agent1_output, state.agent2_output, event_data)
            state.step_times["agent3"] = round(time.time() - t0, 2)
            sv = state.agent3_output.get("valuation_summary", {})
            cb("agent3", 1, 1, "done",
               f"upside={sv.get('probability_weighted_upside_pct',0):.1f}% asym={sv.get('asymmetry_ratio',0):.1f}")

            state.status = "done"
            state.completed_at = datetime.now(timezone.utc).isoformat()

        except DataForgeError as e:
            state.status = "terminated"
            state.errors.append({"code": e.code, "message": e.message, "details": e.details})
            cb("agent1", 1, 1, "error", f"E101:{e.message}")

        except Exception as e:
            state.status = "error"
            state.errors.append({"code": "UNKNOWN", "message": str(e)})
            cb("agent1", 1, 1, "error", str(e)[:100])

        return self._assemble_result(state)

    # ── 各 Agent 运行器 ──

    def _run_agent0(self, stock_code: str, event_data: dict) -> dict:
        """运行 Agent-0，含 fallback（无匹配时全量拉取）。"""
        a0 = Agent0()
        try:
            return a0.run(stock_code, event_data)
        except Exception:
            # fallback: 最小预路由
            return {
                "pre_routing_result": {
                    "ticker": stock_code,
                    "industry_classification": "未知",
                    "event_tags_matched": [],
                    "data_requirements": {
                        "core_package": {
                            "fields": [], "mandatory": True, "failure_action": "terminate",
                        },
                        "specialized_package": {"fields": [], "mandatory": False},
                        "validation_package": {"fields": [], "mandatory": False},
                        "optional_package": {"fields": [], "mandatory": False},
                    },
                    "model_category_hint": [],
                    "hint_confidence": "低",
                },
                "_fallback": True,
            }

    def _run_agent1(self, pre_routing: dict) -> dict:
        """运行 Agent-1。"""
        forge = DataForge()
        return forge.run(pre_routing)

    def _run_agent2(self, data_package: dict, event_data: dict) -> dict:
        """运行 Agent-2，含 DeepSeek 故障时 fallback 规则路由。"""
        judge = RouteJudge(deepseek_key=self.api_key)

        # 注入 pre_routing_result（用于 hint 参考）
        enriched = dict(data_package)
        if "pre_routing_result" not in enriched:
            enriched["pre_routing_result"] = event_data.get("_pre_routing", {})

        try:
            return judge.run(enriched, event_data)
        except Exception as e:
            print(f"  [Orchestrator] Agent-2 异常, 重试: {e}", flush=True)
            try:
                return judge.run(enriched, event_data)
            except Exception as e2:
                print(f"  [Orchestrator] Agent-2 重试仍失败, fallback路由: {e2}", flush=True)
                rd = judge._fallback_routing(enriched)
            return {
                "routing_decision": rd,
                "case_matches_top3": [],
                "case_matches_all": [],
                "case_anchors_text": "",
                "incremental_fetch_request": {"triggered": False},
                "hint_rejection_note": "LLM故障,fallback路由",
                "_fallback": True,
            }

    def _run_agent3(self, data_package: dict, agent2_output: dict,
                    event_data: dict) -> dict:
        """运行 Agent-3，含重试+故障处理。"""
        a3 = ScenarioAsymmetry(deepseek_key=self.api_key)
        rd = agent2_output.get("routing_decision", {})
        case_anchors = self._build_case_anchors_text(agent2_output)

        try:
            return a3.run(
                data_package, rd, event_data,
                case_anchors=case_anchors,
            )
        except ScenarioError as e:
            if e.code in ("E301", "E302", "E303"):
                # 重试1次: JSON解析/超时/API故障
                try:
                    return a3.run(
                        data_package, rd, event_data,
                        case_anchors=case_anchors,
                    )
                except ScenarioError:
                    pass
            raise

    def _build_case_anchors_text(self, a2_output: dict) -> str:
        """从 Agent-2 输出构建案例锚点文本。包含可靠性评估。"""
        # 优先: Agent-2 已构建的丰富锚点（含 catalyst/logic/routing_reason/end_state）
        rich = a2_output.get("case_anchors_text", "")
        if rich:
            text = rich
        else:
            top3 = a2_output.get("case_matches_top3", [])
            if not top3:
                return ""
            lines = ["## 案例锚点"]
            for cm in top3:
                lines.append(f"  {cm['case_code']} score={cm['score']} — {cm['key_anchor']}")
            text = "\n".join(lines)

        # 附加锚点可靠性评估
        ar = a2_output.get("anchor_reliability", {})
        if ar:
            text += f"\n\n## 案例锚点可靠性: {ar.get('reliability', '?')} (top={ar.get('top_score', 0)}/20)\n"
            text += f"{ar.get('note', '')}\n"

        return text

    # ── Frozen 数据规范化 ──

    @staticmethod
    def _normalize_frozen(frozen: dict, stock_code: str, stock_name: str) -> dict:
        """将评测集 flat frozen 格式转为标准 data_package 格式。"""
        cf = frozen.get("clean_financials", {})
        va = frozen.get("valuation_anchor", {})
        sanity = frozen.get("market_sanity", {})

        # 合并 flat 字段到 packages.core.fields
        fields = dict(cf)
        fields.update({
            "pe_ttm": va.get("pe_ttm", cf.get("pe_ttm", 0)),
            "pb": va.get("pb", cf.get("pb", 0)),
            "pe_historical_rank": va.get("pe_historical_rank", cf.get("pe_historical_rank", 30)),
            "nopat_yi": va.get("nopat_yi", cf.get("nopat_yi", 0.01)),
            "roic_pct": va.get("roic_pct", cf.get("roic_pct", 0)),
            "stock_name": cf.get("stock_name", stock_name),
            "ps_ttm": sanity.get("ps_ttm", 0),
            "effective_tax_rate": 0.15,
        })

        # 确保缺失字段有默认值
        defaults = {
            "market_cap_yi": 50, "revenue_ttm_yi": 1,
            "net_profit_ttm_yi": 0, "ebitda_ttm_yi": 0, "operating_profit_ttm_yi": 0,
            "invested_capital_yi": 1, "roic_pct": 0, "gross_margin_pct": 0, "net_margin_pct": 0,
            "pe_ttm": 0, "pb": 0, "ps_ttm": 0,
            "total_equity_yi": 1, "total_assets_yi": 1,
            "interest_bearing_debt_yi": 0, "cash_yi": 0,
            "ocf_ttm_yi": 0, "capex_ttm_yi": 0,
            "nopat_yi": 0.01, "pe_historical_rank": 30,
            "pb_historical_rank": 50, "roic_historical_rank": 50,
            "gross_margin_historical_rank": 50, "net_margin_historical_rank": 50,
            "roe_historical_rank": 50, "profitability_composite_score": 50,
            "caution_flags": [], "data_quality_score": 7,
            "stock_name": stock_name,
        }
        for k, v in defaults.items():
            if k not in fields or fields[k] is None:
                fields[k] = v

        # 旧版 frozen 数据缺失新字段时，从已有字段推导
        if fields.get("invested_capital_yi", 0) <= 1:
            eq = fields.get("total_equity_yi", 1)
            debt = fields.get("interest_bearing_debt_yi", 0)
            fields["invested_capital_yi"] = round(eq + debt, 1)
        if fields.get("ebitda_ttm_yi", 0) <= 0:
            op = fields.get("operating_profit_ttm_yi", 0)
            fields["ebitda_ttm_yi"] = round(op * 1.15, 2) if op > 0 else 0

        return {
            "request_id": f"eval_{stock_code}",
            "stock_code": stock_code,
            "stock_name": stock_name,
            "industry": cf.get("industry", ""),
            "packages": {
                "core": {
                    "fields": fields,
                    "status": "complete",
                    "quality_score": cf.get("data_quality_score", 7),
                    "missing_fields": [],
                },
                "specialized": {"fields": {}, "status": "empty", "quality_score": 0},
                "validation": {"fields": {}, "status": "empty", "quality_score": 0},
                "optional": {"fields": {}, "status": "empty", "quality_score": 0},
            },
            "overall_data_quality_score": cf.get("data_quality_score", 7),
            "fetch_errors": [],
            "_source": "eval_frozen",
        }

    # ── 结果组装 ──

    def _assemble_result(self, state: PipelineState) -> dict:
        """组装最终结果 dict（兼容 scheduler + server）。"""
        # 将 Agent-3 的案例比对数据合入 Agent-2 的 case_matches_top3
        # （Agent-3 产出完整的 comprehensive_discount_pct + six_dimension_judgment，
        #   前端从 Agent-2 取案例数据，需要合并才能正确展示）
        a2 = dict(state.agent2_output or {})
        a3 = state.agent3_output or {}
        a3_ccs = a3.get("case_comparison_summary", {})
        a3_cases = a3_ccs.get("compared_cases", [])
        if a3_cases:
            a3_case_map = {c.get("case_code", ""): c for c in a3_cases}
            enriched_top3 = []
            for cm in a2.get("case_matches_top3", []):
                code = cm.get("case_code", "")
                rich = a3_case_map.get(code, {})
                enriched_top3.append({
                    **cm,
                    "comprehensive_discount_pct": rich.get("comprehensive_discount_pct"),
                    "six_dimension_judgment": rich.get("six_dimension_judgment", {}),
                })
            a2["case_matches_top3"] = enriched_top3

        result = {
            "agent0": state.agent0_output or {},
            "agent1": state.agent1_output or {},
            "agent2": a2,
            "agent3": state.agent3_output or {},
            "status": state.status,
            "audit": {
                "stock_code": state.stock_code,
                "stock_name": state.stock_name,
                "phase": state.phase,
                "started_at": state.started_at,
                "completed_at": state.completed_at,
                "step_times": state.step_times,
                "incremental_fetch_count": state.incremental_fetch_count,
                "eval_mode": self._eval_mode,
                "errors": state.errors,
            },
        }

        if state.errors:
            result["error"] = state.errors[0]["message"]

        return result


# ═══════════════════════════════════════
# 缓存辅助
# ═══════════════════════════════════════

CACHE_DIR = Path(__file__).resolve().parent.parent / "reports" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_cache(stock_code: str, layer: str) -> dict | None:
    """加载指定层的缓存。"""
    path = CACHE_DIR / f"{stock_code}_{layer}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_cache(stock_code: str, layer: str, data: dict):
    """保存指定层的缓存。"""
    path = CACHE_DIR / f"{stock_code}_{layer}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


# ── 便捷函数 ──

def run_pipeline(stock_code: str, event_data: dict | None = None) -> dict:
    """便捷入口：运行完整管线。"""
    orch = Orchestrator()
    return orch.run(stock_code, event_data)


def run_eval_pipeline(stock_code: str, frozen_data: dict,
                      event_data: dict | None = None) -> dict:
    """便捷入口：评测模式运行。"""
    orch = Orchestrator()
    orch.enable_eval_mode(frozen_data)
    return orch.run(stock_code, event_data)
