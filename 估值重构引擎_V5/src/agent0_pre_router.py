"""
Agent-0 预路由 (PreRouter) — V5

规则引擎: 行业→数据包类型 + 事件标签→追加字段。
纯代码，毫秒级，100% 确定性。无权决定 valuation model。

原则: 采购员不判案 — Agent-2 是唯一的路由判官。
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_fetcher import DataFetcher  # noqa: E402

# ═══════════════════════════════════════
# 第一层：行业→specialized_package 字段
# ═══════════════════════════════════════
INDUSTRY_SPECIALIZED: dict[str, list[str]] = {
    "医药生物-创新药": [
        "pipeline_list", "clinical_phase", "peak_sales_estimate",
        "pos_assumptions", "net_cash",
    ],
    "医药生物": [
        "pipeline_list", "clinical_phase", "peak_sales_estimate",
        "pos_assumptions", "net_cash",
    ],
    "有色金属-能源金属": [
        "proven_reserves", "probable_reserves", "commodity_price",
        "extraction_cost_rate", "mine_life",
    ],
    "有色金属": [
        "proven_reserves", "probable_reserves", "commodity_price",
        "extraction_cost_rate", "mine_life",
    ],
    "电子-印制电路板": [
        "capacity_utilization", "order_backlog", "yield_rate",
        "customer_concentration",
    ],
    "电子": [
        "capacity_utilization", "order_backlog", "yield_rate",
        "customer_concentration",
    ],
    "计算机-软件开发": [
        "subscribers", "arpu", "cac", "ltv", "churn_rate",
    ],
    "计算机": [
        "subscribers", "arpu", "cac", "ltv", "churn_rate",
    ],
    "银行": [
        "npl_ratio", "net_interest_margin", "capital_adequacy_ratio", "roe_ttm",
    ],
    "保险": [
        "npl_ratio", "net_interest_margin", "capital_adequacy_ratio", "roe_ttm",
    ],
    "化工-化学原料": [
        "capacity_utilization", "commodity_price_index", "cost_curve_position",
        "cycle_phase_indicator",
    ],
    "化工": [
        "capacity_utilization", "commodity_price_index", "cost_curve_position",
        "cycle_phase_indicator",
    ],
    "房地产": [
        "nav_breakdown", "rental_yield", "occupancy_rate", "debt_maturity_schedule",
    ],
    "REITs": [
        "nav_breakdown", "rental_yield", "occupancy_rate", "debt_maturity_schedule",
    ],
}

# ═══════════════════════════════════════
# 第二层：事件标签→boost 追加字段
# ═══════════════════════════════════════
EVENT_BOOST: dict[str, list[str]] = {
    "产能释放": [
        "capacity_expansion_plan", "capex_breakdown", "depreciation_schedule",
    ],
    "借壳重组": [
        "control_change_event", "injection_asset_description", "shell_value_estimate",
    ],
    "管线推进": [
        "clinical_trial_updates", "competitive_pipeline_landscape",
    ],
    "政策催化": [
        "policy_document_reference", "subsidy_amount", "tax_benefit_duration",
    ],
    "困境反转": [
        "distress_recovery_timeline", "asset_restructuring_plan", "cash_burn_rate",
    ],
}

# ═══════════════════════════════════════
# 核心字段 — 所有估值模型通用，必须 100% 获取
# ═══════════════════════════════════════
CORE_FIELDS: list[str] = [
    "current_price", "total_shares", "market_cap", "revenue_ttm",
    "eps_ttm", "net_profit_growth_yoy", "bps", "roe_ttm",
    "ocf_ttm", "capex_ttm", "net_debt", "total_assets", "total_liabilities",
    "gross_margin", "net_margin", "interest_bearing_debt",
    "pe_ttm", "pb", "operating_profit_ttm", "net_profit_ttm",
    "profit_before_tax", "income_tax", "interest_expense", "cash",
    "total_equity",
]

VALIDATION_FIELDS: list[str] = [
    "peer_median_pe", "peer_median_ps", "historical_pe_range",
    "beta", "wacc_estimate", "industry_cycle_position",
]

OPTIONAL_FIELDS: list[str] = [
    "dividend_yield", "segment_breakdown",
]


def _match_industry(sw_l1: str, sw_l2: str) -> str:
    """匹配行业分类，返回 matched_key 或空字符串。"""
    candidates = [sw_l1, sw_l2]
    # 优先精确匹配
    for c in candidates:
        if not c:
            continue
        if c in INDUSTRY_SPECIALIZED:
            return c
    # 子串匹配
    for key in INDUSTRY_SPECIALIZED:
        for c in candidates:
            if not c:
                continue
            if key in c or c in key:
                return key
    return ""


def _match_event_tags(event_text: str, event_deduction: str, investment_theme: str) -> list[str]:
    """从事件文本/推演/主题中匹配事件标签。"""
    combined = f"{event_text} {event_deduction} {investment_theme}"
    matched = []
    for tag_key, boost_fields in EVENT_BOOST.items():
        if tag_key in combined:
            matched.append(tag_key)
    return matched


class Agent0:
    """预路由规则引擎。"""

    def __init__(self):
        self.fetcher = DataFetcher()

    def run(self, stock_code: str, event_data: dict[str, Any] | None = None) -> dict:
        """
        执行预路由，返回 data_requirements。

        event_data 字段（来自 Coze Agent0）：
          - raw_event_text, event_deduction, investment_theme
          - preliminary_reasoning, adversarial_thinking 等
        """
        event_data = event_data or {}
        event_text = event_data.get("raw_event_text", "")
        event_deduction = event_data.get("event_deduction", "")
        investment_theme = event_data.get("investment_theme", "")

        # Step 1: 获取行业分类
        try:
            ind = self.fetcher.fetch_industries(stock_code)
            sw_l1 = ind.get("sw_l1_name", "")
            sw_l2 = ind.get("sw_l2_name", "")
        except Exception:
            sw_l1 = ""
            sw_l2 = ""

        # Step 2: 行业→specialized fields
        industry_key = _match_industry(sw_l1, sw_l2)
        specialized_fields = INDUSTRY_SPECIALIZED.get(industry_key, []) if industry_key else []

        # Step 3: 事件标签→boost fields
        event_tags = _match_event_tags(event_text, event_deduction, investment_theme)
        boost_fields: list[str] = []
        for tag in event_tags:
            boost_fields.extend(EVENT_BOOST.get(tag, []))
        boost_fields = list(set(boost_fields))

        # 合并 specialized + boost（去重）
        all_specialized = list(dict.fromkeys(specialized_fields + boost_fields))

        # Step 4: 模型类别 hint（无权决定，Agent-2 最终判决）
        model_hint = self._infer_model_hint(industry_key, event_tags, event_data)
        hint_confidence = "中" if industry_key else "低"

        # ── 组装输出 ──
        request_id = f"req_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{stock_code}"

        return {
            "request_id": request_id,
            "pre_routing_result": {
                "ticker": stock_code,
                "stock_name": event_data.get("stock_name", ""),
                "industry_classification": f"{sw_l1}-{sw_l2}".strip("-"),
                "industry_key_matched": industry_key,
                "event_tags_matched": event_tags,

                "data_requirements": {
                    "core_package": {
                        "description": "所有估值模型通用，必须100%获取",
                        "fields": CORE_FIELDS,
                        "mandatory": True,
                        "failure_action": "terminate",
                    },
                    "specialized_package": {
                        "fields": all_specialized,
                        "mandatory": False,
                        "failure_action": "continue_with_gap",
                    },
                    "validation_package": {
                        "fields": VALIDATION_FIELDS,
                        "mandatory": False,
                        "failure_action": "skip_validation",
                    },
                    "optional_package": {
                        "fields": OPTIONAL_FIELDS,
                        "mandatory": False,
                        "failure_action": "ignore",
                    },
                },

                "model_category_hint": [model_hint] if model_hint else [],
                "hint_confidence": hint_confidence,
                "warning": "【重要】本 hint 不决定最终模型。Agent-2 将基于实际财务数据独立判决。",
            },
        }

    def _infer_model_hint(
        self, industry_key: str, event_tags: list[str], event_data: dict
    ) -> str:
        """基于行业+事件标签给出模型类别 hint（Agent-2 可无视）。"""
        if industry_key in ("医药生物-创新药", "医药生物"):
            if "管线推进" in event_tags:
                return "rNPV/管线估值"
            return "DCF/盈利乘数混合"

        if industry_key in ("有色金属-能源金属", "有色金属"):
            return "NAV/资源储量"

        if industry_key in ("电子-印制电路板", "电子"):
            if "产能释放" in event_tags:
                return "PEG/增长锚定"
            return "盈利乘数"

        if industry_key in ("计算机-软件开发", "计算机"):
            if "困境反转" in event_tags:
                return "PS/订阅估值"
            return "PS/盈利乘数混合"

        if industry_key in ("银行", "保险"):
            return "PB-ROE/净资产估值"

        if industry_key in ("房地产", "REITs"):
            return "NAV/资产净值"

        if industry_key in ("化工-化学原料", "化工"):
            return "周期类(盈利正常化/EV-EBITDA)"

        if "借壳重组" in event_tags:
            return "SOTP/分部加总"

        if "政策催化" in event_tags:
            return "EV-EBITDA/盈利乘数"

        return "盈利乘数"


# ── 便捷函数 ──

def run_pre_router(stock_code: str, event_data: dict[str, Any] | None = None) -> dict:
    """便捷入口：运行预路由，返回完整结果。"""
    router = Agent0()
    return router.run(stock_code, event_data)


def get_data_requirements(stock_code: str, event_data: dict[str, Any] | None = None) -> dict:
    """便捷入口：只返回 data_requirements 部分。"""
    result = run_pre_router(stock_code, event_data)
    return result["pre_routing_result"]["data_requirements"]
