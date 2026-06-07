"""
宗门中枢 (Orchestrator) — V6

V6 变化: Agent-2 拆分为 Agent-2a(叙事诊断) + Agent-2b(路由判决)。
管线从 4 步变为 5 步: Agent-0→1→2a→2b→3。2a 输出约束 2b 和 3。

职责:
  1. 按状态机编排 5-Agent 管线 (Agent-0→1→2a→2b→3)
  2. rNPV 分叉 (Agent-0 行业判定→标准/rNPV管线, rNPV 延后实现)
  3. 增量补取闭环 (Agent-2b 发现缺失→回退 Agent-1)
  4. 评测模式 (frozen 数据注入，跳过 Agent-0/1 数据拉取)
  5. 故障处理 (DeepSeek/Volcengine/investoday 故障降级)
  6. 审计追踪 (每个 Agent 的输入/输出/耗时/错误)

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
from agent2a_narrative import NarrativeDiagnosis
from agent2b_routing import RouteJudgeV6
from agent3_scenario_asymmetry import ScenarioAsymmetry, ScenarioError, precompute_wacc
from data_fetcher import DataFetcher
from env_config import DEEPSEEK_API_KEY
from pre_screen_gate import PreScreenGate, PreScreenResult  # V6.2 灵光预筛

# rNPV 管线 (条件导入，避免缺失依赖时阻塞标准管线)
try:
    from rnpv.agent1r_pipeline_data import PipelineDataAssembler
    from rnpv.agent2r_scenario import RnpvScenarioValuation
    _RNPV_AVAILABLE = True
except ImportError:
    _RNPV_AVAILABLE = False

# SOTP 管线 (V6.1: 分部估值分叉)
try:
    from agent3s_sotp import SOTPScenarioAsymmetry
    _SOTP_AVAILABLE = True
except ImportError:
    _SOTP_AVAILABLE = False


# ═══════════════════════════════════════
# 管线状态
# ═══════════════════════════════════════

@dataclass
class PipelineState:
    """管线执行状态追踪 (V6)。"""
    stock_code: str
    stock_name: str
    request_id: str = ""
    phase: str = "init"
    status: str = "running"  # running | done | error | terminated
    pipeline_type: str = "standard"  # standard | rnpv (rNPV延后)

    # 各 Agent 输出
    agent0_output: dict | None = None
    agent1_output: dict | None = None
    agent2a_output: dict | None = None   # V6 新增: 叙事诊断
    agent2b_output: dict | None = None   # V6 改名: 路由判决
    pre_screen_result: PreScreenResult | None = None  # V6.2 灵光预筛
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
# Orchestrator V6
# ═══════════════════════════════════════

class Orchestrator:
    """V6 管线编排器 — 5-Agent 状态机 + 缓存 + 评测模式。"""

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key or DEEPSEEK_API_KEY
        self._cache: dict[str, Any] = {}
        self._eval_mode = False
        self._frozen_data: dict | None = None

    def enable_eval_mode(self, frozen_data: dict | None = None):
        self._eval_mode = True
        self._frozen_data = frozen_data

    def disable_eval_mode(self):
        self._eval_mode = False
        self._frozen_data = None

    def run(
        self,
        stock_code: str,
        event_data: dict | None = None,
        progress_cb: Callable[[str, int, int, str, str], None] | None = None,
    ) -> dict:
        """
        执行 V6 5-Agent 管线: Agent-0 → 1 → 2a → 2b → 3

        progress_cb(stage, step, total, status, message)
        """
        cb = progress_cb or (lambda *a: None)
        event_data = event_data or {}
        stock_name = event_data.get("stock_name", stock_code)
        state = PipelineState(
            stock_code=stock_code,
            stock_name=stock_name,
        )

        try:
            # ── Agent-0: 预路由 ──
            cb("agent0", 1, 1, "running", "预路由(行业+数据清单)")
            t0 = time.time()
            state.agent0_output = self._run_agent0(stock_code, event_data)
            state.step_times["agent0"] = round(time.time() - t0, 2)
            pr = state.agent0_output.get("pre_routing_result", {})
            industry = pr.get("industry_classification", "?")
            cb("agent0", 1, 1, "done", f"行业:{industry}")

            # ── Agent-1: 数据炼器 (必须在 rNPV 分叉前——rNPV 管线也需要财务数据) ──
            if self._eval_mode and self._frozen_data:
                cb("agent1", 1, 1, "running", "注入frozen数据(评测模式)")
                state.agent1_output = self._normalize_frozen(
                    self._frozen_data.get("frozen_agent1", {}),
                    stock_code, event_data.get("stock_name", ""),
                )
                cb("agent1", 1, 1, "done", "frozen数据已注入")
            else:
                cb("agent1", 1, 1, "running", "数据拉取(investoday+Tushare)")
                t0 = time.time()
                state.agent1_output = self._run_agent1(pr)
                state.step_times["agent1"] = round(time.time() - t0, 2)
                quality = state.agent1_output.get("overall_data_quality_score", "?")
                cb("agent1", 1, 1, "done", f"quality={quality}")

            # ── Agent-1 数据完整性检查 (防止全零数据通过; 对标准/rNPV两条管线均生效) ──
            core = (state.agent1_output or {}).get("packages", {}).get("core", {}).get("fields", {})
            if not core:
                core = (state.agent1_output or {}).get("clean_financials", {})
            critical_missing = [
                k for k in ["market_cap_yi", "revenue_ttm_yi", "total_assets_yi"]
                if not core.get(k)
            ]
            if critical_missing:
                raise DataForgeError(
                    "E101", f"Agent-1 关键字段为零或缺失: {critical_missing}",
                    {"missing": critical_missing, "stock_code": stock_code},
                )

            # ── 灵光预筛 (V6.2): Flash模型4维快速评估（评测模式跳过）──
            t0 = time.time()
            if self._eval_mode:
                cb("pre_screen", 1, 1, "done", "评测模式跳过预筛")
                state.pre_screen_result = PreScreenResult(total_score=40, passed=True, summary="评测模式跳过")
            else:
                cb("pre_screen", 1, 1, "running", "灵光预筛(标的-事件匹配)")
                _gate = PreScreenGate(api_key=self.api_key)
                state.pre_screen_result = _gate.run(
                    event_data, state.agent1_output, stock_code,
                )
            state.step_times["pre_screen"] = round(time.time() - t0, 2)
            ps = state.pre_screen_result
            if ps.passed:
                cb("pre_screen", 1, 1, "done",
                   f"PASS {ps.total_score}/40 "
                   f"同源{ps.homology} 暴露{ps.exposure} 弹性{ps.elasticity} 地位{ps.position}")
            else:
                state.status = "pre_screened_out"
                state.completed_at = datetime.now(timezone.utc).isoformat()
                cb("pre_screen", 1, 1, "done",
                   f"BLOCK: {ps.cut_reason[:60]}")
                return self._assemble_result(state)

            # ── WACC 预计算 (Agent-2a 定价工具需要) ──
            fetcher = DataFetcher()
            wacc_params = precompute_wacc(fetcher, stock_code, state.agent1_output)

            # ── 火山联网搜索 (移到2a之前: 券商分部拆分+可比估值→2a做锚判断用) ──
            volc_data_std = {}
            try:
                from agent3s_sotp import _call_volc
                import requests as _r

                a0_full = '\n\n'.join([
                    f'## 事件变量\n{event_data.get("raw_event_text", "")}',
                    f'## 事件研判\n{event_data.get("preliminary_reasoning", "")}',
                    f'## 投资主题\n{event_data.get("investment_theme", "")}',
                    f'## 发展推演\n{event_data.get("event_deduction", "")}',
                    f'## 催化节点\n{event_data.get("future", "")}',
                    f'## 逆向风险\n{event_data.get("adversarial_thinking", "")}',
                    f'## 行业全貌\n{event_data.get("industry_expert_research", "")}',
                    f'## 背景知识\n{event_data.get("knowledge_supplement", "")}',
                ])

                sysprompt = f'''你是估值数据补充助手。当前管线对 {stock_name}({stock_code}) 做估值推演。

火山引擎是一个结构化知识问答系统。给它一个清晰的查询，它会从券商研报、公司公告、行业数据中提取结构化的答案。

请审阅以下 Agent-0 完整研究资料，找出研究资料中缺失的量化锚点，然后生成一个火山搜索query来补足这些缺失。重点关注：产能/出货量/订单（用于判断增速物理上限）、产品级毛利率（用于判断ROIC改善路径）、券商未来2-3年营收/利润预测。

你应该覆盖但不限于：券商对未来2-3年营收/利润的一致预期、各业务线收入拆分及增速、可比A股公司当前PE/PS估值倍数、产能/出货量/订单等运营数据。

query要求：自由格式，不需要关键词罗列。明确告诉火山你需要什么数据。尽可能覆盖多的维度。

---
{stock_name}({stock_code}) Agent-0 研究资料:
{a0_full}
---

直接输出query，不要引号、不要解释、不要复述资料。'''

                query = ""
                for attempt in range(2):
                    qresp = _r.post(
                        'https://api.deepseek.com/v1/chat/completions',
                        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {self.api_key}'},
                        json={'model': 'deepseek-v4-pro', 'temperature': 0.0, 'max_tokens': 300,
                              'messages': [
                                  {'role': 'system', 'content': sysprompt},
                                  {'role': 'user', 'content': '生成query'},
                              ]},
                        timeout=90,
                    )
                    if qresp.status_code == 200:
                        choices = qresp.json().get('choices', [])
                        if choices:
                            query = (choices[0].get('message', {}).get('content', '') or '').strip()
                            if query and len(query) >= 30 and stock_code in query:
                                break
                            if query:
                                print(f'  [Volc] query不合格 len={len(query)} 尝试{attempt+1}/2', flush=True)
                    if attempt == 0:
                        time.sleep(2)

                if query:
                    volc_result = _call_volc(query)
                    if volc_result:
                        volc_data_std = {'volc_text': volc_result}
                        print(f'  [Volc] query({len(query)}c) → volc {len(volc_result)} chars', flush=True)
            except Exception as e:
                print(f'  [Volc] 跳过: {e}', flush=True)

            # ── Agent-2a: 叙事诊断 (火山数据已注入, 用于锚判断+SOTP判定) ──
            cb("agent2a", 1, 2, "running", "叙事诊断(锚+计价+信号审核)")
            t0 = time.time()
            state.agent2a_output = self._run_agent2a(
                state.agent1_output, event_data, wacc_params,
                volc_data=volc_data_std,
            )
            state.step_times["agent2a"] = round(time.time() - t0, 2)
            a2a_mn = state.agent2a_output.get("market_narrative", {})
            a2a_ep = state.agent2a_output.get("event_pricing", {})
            a2a_pr = a2a_ep.get("event_profile", {})
            cb("agent2a", 1, 2, "done",
               f"锚:{a2a_mn.get('primary_anchor','?')} "
               f"光谱:{a2a_pr.get('distribution_shape','?')} "
               f"计价:{a2a_ep.get('pricing_assessment',{}).get('overall_priced_in','?')}")

            # ── rNPV 分叉: Agent-2a 判锚为 pipeline → 走 rNPV 专用管线 ──
            if a2a_mn.get("primary_anchor") == "pipeline" and _RNPV_AVAILABLE:
                state.pipeline_type = "rnpv"
                return self._run_rnpv_pipeline(state, event_data, cb)

            # ── Agent-2b: 路由判决 ──
            cb("agent2b", 2, 2, "running", "路由判决(受2a约束)")
            t0 = time.time()
            state.agent2b_output = self._run_agent2b(
                state.agent1_output, state.agent2a_output, event_data,
                volc_data=volc_data_std,
            )
            state.step_times["agent2b"] = round(time.time() - t0, 2)
            rd = state.agent2b_output.get("routing_decision", {})
            cc = rd.get("constraint_compliance", {})
            override_str = "(override)" if cc.get("constraint_override") else ""
            cb("agent2b", 2, 2, "done",
               f"主:{rd.get('primary_model','?')} 校验:{rd.get('validation_models',[])} {override_str}")

            # ── SOTP 分叉 (V6.4): Agent-2a 判 sotp_triggered → 走 SOTP 分部估值 ──
            # 移到2b之后：2b已跑完，sotp_primary_segment_model可用
            if a2a_mn.get("sotp_triggered") and _SOTP_AVAILABLE:
                state.pipeline_type = "sotp"
                sotp_result = self._run_sotp_pipeline(state, event_data, cb, wacc_params, volc_data_std)
                return sotp_result

            # ── Agent-3: 推演裁决 ──
            cb("agent3", 1, 1, "running", "推演裁决(三情景)")
            t0 = time.time()
            state.agent3_output = self._run_agent3(
                state.agent1_output, state.agent2b_output,
                event_data, state.agent2a_output,
                volc_data=volc_data_std,
            )
            state.step_times["agent3"] = round(time.time() - t0, 2)
            vs = state.agent3_output.get("valuation_summary", {})
            cb("agent3", 1, 1, "done",
               f"upside={vs.get('probability_weighted_upside_pct',0):+.1f}% "
               f"asym={vs.get('asymmetry_ratio',0):.1f}x")

            state.status = "done"
            state.completed_at = datetime.now(timezone.utc).isoformat()

        except DataForgeError as e:
            state.status = "terminated"
            state.errors.append({"code": e.code, "message": e.message, "details": e.details})
            cb("agent1", 1, 1, "error", f"E101:{e.message}")

        except Exception as e:
            state.status = "error"
            state.errors.append({"code": "UNKNOWN", "message": str(e)})
            cb("agent3", 1, 1, "error", str(e)[:100])

        return self._assemble_result(state)

    # ── Agent 运行器 ──

    def _run_agent0(self, stock_code: str, event_data: dict) -> dict:
        a0 = Agent0()
        try:
            return a0.run(stock_code, event_data)
        except Exception:
            return {
                "pre_routing_result": {
                    "ticker": stock_code,
                    "industry_classification": "未知",
                    "event_tags_matched": [],
                    "data_requirements": {
                        "core_package": {"fields": [], "mandatory": True, "failure_action": "terminate"},
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
        forge = DataForge()
        return forge.run(pre_routing)

    def _run_agent2a(self, data_package: dict, event_data: dict,
                     wacc_params: dict, volc_data: dict | None = None) -> dict:
        a2a = NarrativeDiagnosis(deepseek_key=self.api_key)
        try:
            return a2a.run(data_package, event_data, wacc_params, volc_data=volc_data)
        except Exception as e:
            print(f"  [Orchestrator] Agent-2a 异常, fallback: {e}", flush=True)
            return a2a._fallback_diagnosis(
                data_package.get("packages", {}).get("core", {}).get("fields", {}),
            )

    def _run_agent2b(self, data_package: dict, agent2a_output: dict,
                     event_data: dict, volc_data: dict | None = None) -> dict:
        a2b = RouteJudgeV6(deepseek_key=self.api_key)
        try:
            return a2b.run(data_package, agent2a_output, event_data, volc_data)
        except Exception as e:
            print(f"  [Orchestrator] Agent-2b 异常, fallback: {e}", flush=True)
            return {
                "routing_decision": a2b._fallback_routing(data_package, agent2a_output),
                "_fallback": True,
            }

    def _run_agent3(self, data_package: dict, agent2b_output: dict,
                    event_data: dict, agent2a_output: dict,
                    volc_data: dict | None = None) -> dict:
        a3 = ScenarioAsymmetry(deepseek_key=self.api_key)
        rd = agent2b_output.get("routing_decision", {})

        try:
            return a3.run(
                data_package, rd, event_data,
                agent2a_output=agent2a_output,
                volc_data=volc_data,
            )
        except ScenarioError as e:
            if e.code in ("E301", "E302", "E303"):
                try:
                    return a3.run(
                        data_package, rd, event_data,
                        agent2a_output=agent2a_output,
                    )
                except ScenarioError:
                    pass
            raise

    # ── rNPV 管线 ──

    def _run_rnpv_pipeline(self, state: PipelineState, event_data: dict, cb) -> dict:
        """执行 rNPV 专用管线: Agent-1r → Agent-2r (V7: 合并旧 2r+3r, 单次LLM)"""
        stock_code = state.stock_code
        stock_name = state.stock_name

        # Agent-1r: 管线数据组装 + Volc 搜索（无 LLM）
        cb("agent1r", 1, 2, "running", "管线数据+Volc搜索")
        t0 = time.time()
        a1r = PipelineDataAssembler(deepseek_key=self.api_key)
        a1_std = state.agent1_output  # 复用标准管线的财务数据
        pipeline_data = a1r.run(stock_code, stock_name, event_data, a1_std)
        state.step_times["agent1r"] = round(time.time() - t0, 2)
        drugs_found = pipeline_data.get("extracted_from_pre_research", {}).get("drug_count", 0)
        cb("agent1r", 1, 2, "done", f"识别管线:{drugs_found}条")

        # Agent-2r: 情景推演 + 代码估值（单次 LLM, 合并旧 2r+3r）
        cb("agent2r", 2, 2, "running", "rNPV参数推演+代码估值")
        t0 = time.time()
        a2r = RnpvScenarioValuation(deepseek_key=self.api_key)
        scenario_output = a2r.run(
            pipeline_data, event_data,
            agent2a_output=state.agent2a_output,
        )
        state.step_times["agent2r"] = round(time.time() - t0, 2)
        vs = scenario_output.get("valuation_summary", {})
        cb("agent2r", 2, 2, "done",
           f"upside={vs.get('probability_weighted_upside_pct',0):+.1f}% "
           f"asym={vs.get('asymmetry_ratio',0):.1f}x")

        state.status = "done"
        state.completed_at = datetime.now(timezone.utc).isoformat()

        return {
            "agent0": state.agent0_output or {},
            "agent1": state.agent1_output or {},
            "agent1r": pipeline_data,
            "agent2r": scenario_output,                # Agent-2r 完整输出（含 valuation_summary/scenarios）
            "agent2": scenario_output,                 # scheduler 兼容: agent2 = agent2r
            "agent3": scenario_output,                 # Agent-3 兼容: 已组装为 Agent-3 格式
            "agent2a": state.agent2a_output or {},     # V7 修复: 保留 Agent-2a 叙事诊断
            "routing_decision": {                      # V7 修复: 构造路由信息
                "primary_model": "F",
                "model_category": "rNPV",
                "routing_reason": "Agent-2a判定pipeline锚→分叉至rNPV管线",
                "validation_models": [],
            },
            "status": "done",
            "pipeline_version": "7.0-rnpv",
            "pipeline_type": "rnpv",
            "audit": {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "started_at": state.started_at,
                "completed_at": state.completed_at,
                "step_times": state.step_times,
                "errors": state.errors,
            },
        }

    # ── SOTP 管线 (V6.1) ──

    def _run_sotp_pipeline(
        self, state: PipelineState, event_data: dict, cb, wacc_params: dict,
        volc_data: dict | None = None,
    ) -> dict:
        """执行 SOTP 专用管线: Agent-3s（单次 LLM 调用完成分部估值+情景推演）。"""
        stock_code = state.stock_code
        stock_name = state.stock_name

        # Agent-3s: SOTP 分部估值 + 情景推演（单次LLM调用）
        cb("agent3s", 1, 1, "running", "SOTP分部估值+情景推演")
        t0 = time.time()
        a3s = SOTPScenarioAsymmetry(deepseek_key=self.api_key)

        sotp_output = a3s.run(
            data_package=state.agent1_output,
            agent2a_output=state.agent2a_output,
            agent2b_output=state.agent2b_output,
            event_data=event_data,
            wacc_params=wacc_params,
            volc_data=volc_data,  # orchestrator预取
            progress_cb=lambda step, msg: cb("agent3s", 1, 1, "running", msg),
        )

        state.agent3_output = sotp_output  # 复用 agent3_output 字段保存
        state.step_times["agent3s"] = round(time.time() - t0, 2)

        vs = sotp_output.get("valuation_summary", {})
        cb("agent3s", 1, 1, "done",
           f"upside={vs.get('probability_weighted_upside_pct',0):+.1f}% "
           f"asym={vs.get('asymmetry_ratio',0):.1f}x")

        state.status = "done"
        state.completed_at = datetime.now(timezone.utc).isoformat()

        # 组装结果（复用标准管线格式，兼容前端）
        return {
            "agent0": state.agent0_output or {},
            "agent1": state.agent1_output or {},
            "agent2": state.agent2b_output or {},   # 2b 路由决策, scheduler 提取 routing_decision
            "agent2a": state.agent2a_output or {},
            "agent3": sotp_output,
            "status": "done",
            "pipeline_version": "6.1-sotp",
            "pipeline_type": "sotp",
            "audit": {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "started_at": state.started_at,
                "completed_at": state.completed_at,
                "step_times": state.step_times,
                "errors": state.errors,
            },
        }

    # ── 结果组装 ──

    def _assemble_result(self, state: PipelineState) -> dict:
        """组装最终结果 dict（兼容 scheduler + server V5/V6 格式）。"""
        a2b = dict(state.agent2b_output or {})
        a3 = state.agent3_output or {}

        result = {
            "agent0": state.agent0_output or {},
            "agent1": state.agent1_output or {},
            "agent2": a2b,   # 保持 agent2 键名向后兼容
            "agent2a": state.agent2a_output or {},  # V6 新增
            "agent3": state.agent3_output or {},
            "status": state.status,
            "pre_screen": {
                "total_score": ps.total_score,
                "passed": ps.passed,
                "homology": ps.homology,
                "exposure": ps.exposure,
                "elasticity": ps.elasticity,
                "position": ps.position,
                "discretionary_adjustment": ps.discretionary_adjustment,
                "cut_reason": ps.cut_reason,
                "summary": ps.summary,
            } if (ps := state.pre_screen_result) else {},
            "pipeline_version": "6.2",
            "pipeline_type": state.pipeline_type,
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

    # ── Frozen 数据规范化 ──

    @staticmethod
    def _normalize_frozen(frozen: dict, stock_code: str, stock_name: str) -> dict:
        """将评测集 flat frozen 格式转为标准 data_package 格式。"""
        cf = frozen.get("clean_financials", {})
        va = frozen.get("valuation_anchor", {})
        sanity = frozen.get("market_sanity", {})

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


# ═══════════════════════════════════════
# 缓存辅助
# ═══════════════════════════════════════

CACHE_DIR = Path(__file__).resolve().parent.parent / "reports" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_cache(stock_code: str, layer: str) -> dict | None:
    path = CACHE_DIR / f"{stock_code}_{layer}.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_cache(stock_code: str, layer: str, data: dict):
    path = CACHE_DIR / f"{stock_code}_{layer}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


# ── 便捷函数 ──

def run_pipeline(stock_code: str, event_data: dict | None = None) -> dict:
    orch = Orchestrator()
    return orch.run(stock_code, event_data)


def run_eval_pipeline(stock_code: str, frozen_data: dict,
                      event_data: dict | None = None) -> dict:
    orch = Orchestrator()
    orch.enable_eval_mode(frozen_data)
    return orch.run(stock_code, event_data)
