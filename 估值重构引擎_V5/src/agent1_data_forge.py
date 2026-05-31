"""
Agent-1 数据炼器 (DataForge) — V5

接收 Agent-0 的 data_requirements，按包分层拉取数据，标注每个字段的来源和质量。
支持增量补取（Agent-2 发现缺失→Orchestrator 回退 Agent-1 补拉）。

Core bundle: investoday (7端点) + Tushare (7端点) 并行调用（ThreadPoolExecutor）。

原则: 分层失败不崩溃 — 只有 core_package 缺失才终止流程 (E101)。
"""

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_fetcher import DataFetcher  # noqa: E402
from env_config import DEEPSEEK_API_KEY  # noqa: E402, F401 — 供下游使用

try:
    from tushare_fetcher import TushareFetcher
    from forward_indicator_computer import compute_forward_signals
    _TUSHARE_AVAILABLE = True
except ImportError:
    _TUSHARE_AVAILABLE = False


# ═══════════════════════════════════════
# 错误码
# ═══════════════════════════════════════
class DataForgeError(Exception):
    """数据炼器异常，含错误码。"""
    def __init__(self, code: str, message: str, details: dict | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"[{code}] {message}")


# ═══════════════════════════════════════
# 核心字段 → API 拉取函数映射
# ═══════════════════════════════════════

def _fetch_core_bundle(fetcher: DataFetcher, stock_code: str) -> dict:
    """并行拉取核心数据源: investoday(7端点) + Tushare(7端点, 可选)。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, Any] = {}
    errors: list[dict] = []

    def _safe_fetch(name: str, fn, *args):
        try:
            return name, fn(*args), None
        except Exception as e:
            return name, {}, str(e)

    # investoday 任务
    is_beijiao = stock_code.startswith("92") or stock_code.startswith("87")
    tasks = [
        ("quote",           fetcher.fetch_realtime_quote, stock_code),
        ("valuation",       fetcher.fetch_valuation, stock_code),
        ("income",          fetcher.fetch_income_ttm, stock_code),
        ("balance",         fetcher.fetch_balance_ttm, stock_code),
        ("cashflow",        fetcher.fetch_cashflow_ttm, stock_code),
        ("fin_der",         fetcher.fetch_fin_der_inds, stock_code),
        ("profit_ability",  fetcher.fetch_profit_ability, stock_code),
        ("industries",      fetcher.fetch_industries, stock_code),
        ("dupont",          fetcher.fetch_dupont, stock_code),
        # 一致预期和分部收入（为前瞻信号面板提供数据）
        ("segment",         fetcher.fetch_segment_revenue, stock_code),
        ("consensus",       fetcher.fetch_analyst_consensus, stock_code),
    ]

    # Tushare 任务（替代行情+估值，提供季度趋势和前瞻字段）
    # 北交所/新三板股票 Tushare 不覆盖，跳过避免污染 investoday 数据
    if _TUSHARE_AVAILABLE and not is_beijiao:
        try:
            tf = TushareFetcher()
            if tf.available:
                tasks.extend([
                    ("ts_daily",      tf.fetch_daily, stock_code, 1),
                    ("ts_daily_basic", tf.fetch_daily_basic, stock_code, 1),
                    ("ts_bs_q",       tf.fetch_balance_sheet_quarterly, stock_code, 8),
                    ("ts_income_q",   tf.fetch_income_quarterly, stock_code, 8),
                    ("ts_cf_q",       tf.fetch_cashflow_quarterly, stock_code, 8),
                    ("ts_fina_ind",   tf.fetch_fina_indicator, stock_code),
                    ("ts_fina_mainbz", tf.fetch_fina_mainbz, stock_code),
                    ("ts_forecast",   tf.fetch_forecast, stock_code),
                    ("ts_express",    tf.fetch_express, stock_code),
                    ("ts_shareholder", tf.fetch_shareholder_count, stock_code, 4),
                ])
        except Exception:
            pass  # Tushare 不可用不阻塞

    with ThreadPoolExecutor(max_workers=5) as pool:
        wraps = [(name, fn, *(args if args else ())) for name, fn, *args in tasks]
        futures = {pool.submit(_safe_fetch, name, fn, *args): name
                   for name, fn, *args in wraps}
        for f in as_completed(futures):
            name, data, err = f.result()
            results[name] = data
            if err and name not in ('ts_forecast', 'ts_express', 'ts_shareholder',
                                     'ts_bs_q', 'ts_income_q', 'ts_cf_q', 'ts_fina_ind',
                                     'ts_daily', 'ts_daily_basic'):
                errors.append({"source": name, "error": err})

    # 股本信息（CLI 线程安全）
    try:
        raw = fetcher._cli("stock/basic-info", stockCode=stock_code)
        results["basic_info"] = fetcher._first(raw)
    except Exception as e:
        errors.append({"source": "basic_info", "error": str(e)})
        results["basic_info"] = {}

    return {"raw": results, "errors": errors}


def _extract_core_fields(raw_bundle: dict, stock_code: str) -> dict[str, Any]:
    """从原始 API 结果中提取核心字段，单位统一为亿（比率除外）。"""
    r = raw_bundle["raw"]
    q = r.get("quote", {})
    v = r.get("valuation", {})
    inc = r.get("income", {})
    bal = r.get("balance", {})
    cf = r.get("cashflow", {})
    fd = r.get("fin_der", {})
    pa = r.get("profit_ability", {})
    ind = r.get("industries", {})
    dup = r.get("dupont", {})
    basic = r.get("basic_info", {})

    # Tushare 数据源（替代 investoday 行情/估值，提供前瞻字段）
    ts_d = r.get("ts_daily", {}) or {}
    ts_db = r.get("ts_daily_basic", {}) or {}
    ts_fi = r.get("ts_fina_ind", {}) or {}

    # ── 数据源策略 ──
    # Tushare 做主源 (行情+比率数据更稳定)，investoday 补充 Tushare 没有的 (历史分位/行业/绝对值TTM)
    # 字段注释标注来源: [TS] = Tushare主源, [IO] = investoday主源, [TS→IO] = Tushare优先回退investoday

    # 原始值提取 — Tushare 优先
    current_price = ts_d.get("close") or _num(q.get("current_price"))
    total_shares = _num(basic.get("sharesTotal")) / 1e8 if _num(basic.get("sharesTotal")) else 0
    ts_mcap = ts_db.get("total_mv") or ts_d.get("total_mv")
    if ts_mcap:
        market_cap = ts_mcap / 1e4  # 万元 → 亿
    else:
        mcap_raw = _num(q.get("market_cap"))
        market_cap = mcap_raw / 1e8 if mcap_raw else 0

    # investoday 绝对值 (TTM直出, Tushare需季度聚合→保留investoday做主源)
    revenue_ttm = _num(inc.get("revenue_ttm")) / 1e8 if _num(inc.get("revenue_ttm")) else 0

    # ── 比率字段: Tushare fina_indicator 做主源 ──
    # 交叉验证已确认 Tushare/investoday 的毛利率/净利率/ROE/EPS 值完全一致
    # Tushare 更稳定(HTTP 直连,无 subprocess), investoday 做 fallback
    ts_gm = ts_fi.get("gross_margin")       # Tushare 毛利率
    ts_nm = ts_fi.get("net_margin")          # Tushare 净利率
    ts_roe = ts_fi.get("roe")                # Tushare ROE
    ts_roic = ts_fi.get("roic")             # Tushare ROIC
    ts_eps = ts_fi.get("eps")               # Tushare EPS
    ts_bps = ts_fi.get("bps")               # Tushare BPS

    # investoday fallback (仅 Tushare 缺失时使用)
    io_gm = fd.get("gross_margin")
    io_nm = fd.get("net_margin")
    io_roe_raw = dup.get("roe")
    io_roe = io_roe_raw / 100 if io_roe_raw and io_roe_raw > 10 else io_roe_raw  # 单位修正(Q1单季)
    io_roic = fd.get("roic")
    io_eps = inc.get("eps")

    # TTM ROE: Tushare fina_ind 和 investoday dupont 都给最近单期(如Q1), 不能直接用
    # 代码从 TTM 数据计算: ROE = TTM净利润 / 最新净资产 × 100
    np_roe = _num(inc.get("net_profit_ttm"))        # TTM 净利润 (元)
    eq_roe = _num(bal.get("total_equity"))           # 最新净资产 (元)
    calc_roe_ttm = round(np_roe / eq_roe * 100, 2) if eq_roe > 0 else 0.0

    # TTM EPS: 同理——fina_indicator EPS 是单期值, 不能冒充 TTM
    # 代码计算: EPS TTM = TTM净利润 / 总股本, 与 ROE 修复逻辑一致
    np_ttm_raw = _num(inc.get("net_profit_ttm"))     # TTM 净利润 (元)
    shares_raw = _num(basic.get("sharesTotal"))       # 总股本 (股)
    if shares_raw > 0 and np_ttm_raw > 0:
        calc_eps_ttm = round(np_ttm_raw / shares_raw, 2)
    elif current_price and market_cap > 0:
        # fallback: 从市值/股价反推股本 → 再算 EPS
        shares_implied = market_cap * 1e8 / current_price  # 折算为股
        calc_eps_ttm = round(np_ttm_raw / shares_implied, 2) if shares_implied > 0 else 0
        if shares_implied > 0 and shares_raw == 0:
            total_shares = round(shares_implied / 1e8, 2)  # 补填 total_shares (亿股)
    else:
        calc_eps_ttm = 0

    # 交叉验证 (差异>15%告警)
    _warn_divergence(stock_code, "gross_margin", ts_gm, io_gm)
    _warn_divergence(stock_code, "net_margin", ts_nm, io_nm)
    _warn_divergence(stock_code, "roe", ts_roe, io_roe)
    _warn_divergence(stock_code, "roic", ts_roic, io_roic)
    _warn_divergence(stock_code, "eps", ts_eps, io_eps)

    fields: dict[str, Any] = {
        # [TS] 行情 — Tushare 主源
        "current_price": current_price,
        "current_price_source": "tushare_daily" if ts_d else "realtime_quote",
        "total_shares_yi": round(total_shares, 2),
        "market_cap_yi": round(market_cap, 1),
        "market_cap_source": "tushare_daily_basic" if ts_db else "realtime_quote",

        # [IO] 绝对值 — investoday TTM主源
        "revenue_ttm_yi": round(revenue_ttm, 1),

        # [TS→IO] 比率 — Tushare fina_indicator 主源
        "eps_ttm": calc_eps_ttm or ts_eps or io_eps or 0,  # TTM计算值优先(避免单季EPS冒充TTM)
        "net_profit_growth_yoy": _calc_yoy_growth(r, stock_code),
        "bps": ts_bps or round(_num(bal.get("total_equity")) / 1e8 / total_shares, 2) if total_shares > 0 else 0,
        "roe_ttm_pct": calc_roe_ttm or ts_roe or io_roe or 0,  # TTM计算值优先 (Tushare/investoday均为单季)
        "roic_pct": ts_roic or io_roic or 0,

        # [IO] 现金流/资产负债表绝对值 — investoday TTM
        "ocf_ttm_yi": round(_num(cf.get("operating_cash_flow")) / 1e8, 2),
        "capex_ttm_yi": round(_num(cf.get("capex_payments")) / 1e8, 2),
        "net_debt_yi": round(
            (_num(fd.get("interest_bearing_debt")) - _num(bal.get("cash_equivalents"))) / 1e8, 1
        ),
        "total_assets_yi": round(_num(bal.get("total_assets")) / 1e8, 1),
        "total_liabilities_yi": round(_num(bal.get("total_liabilities")) / 1e8, 1),

        # [TS→IO] 盈利比率 — Tushare 主源
        "gross_margin_pct": ts_gm or io_gm or 0,
        "net_margin_pct": ts_nm or io_nm or 0,

        "interest_bearing_debt_yi": round(_num(fd.get("interest_bearing_debt")) / 1e8, 1),
        "interest_expense_yi": round(_calc_interest_expense(inc), 2),

        # [IO] investoday 独有: 历史排名
        "gross_margin_historical_rank": pa.get("gross_margin_historical_rank"),
        "net_margin_historical_rank": pa.get("net_margin_historical_rank"),
        "roe_historical_rank": pa.get("roe_historical_rank"),
        "roic_historical_rank": pa.get("roic_historical_rank"),
        "profitability_composite_score": pa.get("profitability_composite_score"),

        # [TS→IO] 估值倍数 — Tushare daily_basic优先 (无周期问题)
        "pe_ttm": ts_db.get("pe_ttm") or v.get("pe_ttm") or 0,
        "pb": ts_db.get("pb") or v.get("pb") or 0,
        "ps_ttm": ts_db.get("ps_ttm") or v.get("ps_ttm") or 0,

        # [IO] investoday 独有: 历史分位
        "ps_historical_rank": v.get("ps_historical_rank"),
        "pe_historical_rank": v.get("pe_ttm_historical_rank") or 30,
        "pb_historical_rank": v.get("pb_historical_rank"),

        # [IO] 绝对值 (investoday TTM)
        "operating_profit_ttm_yi": round(_num(inc.get("operating_profit")) / 1e8, 2),
        "net_profit_ttm_yi": round(_num(inc.get("net_profit_ttm")) / 1e8, 2),
        "profit_before_tax_yi": round(_num(inc.get("profit_before_tax")) / 1e8, 2),
        "income_tax_yi": round(_num(inc.get("income_tax")) / 1e8, 2),
        "cash_yi": round(_num(bal.get("cash_equivalents")) / 1e8, 1),
        "total_equity_yi": round(_num(bal.get("total_equity")) / 1e8, 1),

        # [IO] investoday 独有: 行业分类
        "industry_sw_l1": ind.get("sw_l1_name", ""),
        "industry_sw_l2": ind.get("sw_l2_name", ""),
        "stock_name": q.get("stock_name", ""),
        "report_period": inc.get("report_date", ""),

        # [TS] Tushare 补充字段 (investoday 不提供)
        "roa_pct": ts_fi.get("roa"),
        "debt_to_assets_pct": ts_fi.get("debt_to_assets"),
    }

    # 衍生计算

    # EBITDA 估算: fin_der_inds 返回最新单季数据，年化×4；API 不拆分 ebit 和 ebitda 时二者相等
    raw_ebitda_q = _num(fd.get("ebitda")) / 1e8  # 单季，亿
    ebitda_annual = raw_ebitda_q * 4
    op = fields["operating_profit_ttm_yi"]
    if ebitda_annual < op and op > 0:
        # 年化后仍小于经营利润=数据异常(可能不是单季)，用经营利润×1.15保守估计D&A
        ebitda_annual = round(op * 1.15, 2)
    fields["ebitda_ttm_yi"] = round(ebitda_annual, 2)

    pbt = _num(inc.get("profit_before_tax")) / 1e8
    tax = _num(inc.get("income_tax")) / 1e8
    eir = tax / pbt if pbt > 0 else 0.25
    eir = max(0.10, min(0.25, eir))
    ebit = fields["operating_profit_ttm_yi"] + fields["interest_expense_yi"]
    nopat = ebit * (1 - eir)
    ic = fields["total_equity_yi"] + fields["interest_bearing_debt_yi"]
    fields["invested_capital_yi"] = round(ic, 1)
    fields["roic_pct"] = round(nopat / ic * 100, 2) if ic > 0 else 0
    fields["nopat_yi"] = round(nopat, 2)
    fields["effective_tax_rate"] = round(eir, 2)

    # 异常标记
    flags = []
    if fields["net_profit_ttm_yi"] <= 0:
        flags.append("TTM净利润为负")
    if fields["total_equity_yi"] <= 0:
        flags.append("资不抵债")
    if fields["roic_pct"] > 50:
        flags.append(f"ROIC异常高({fields['roic_pct']:.1f}%)")
    if fields["roic_pct"] < -20:
        flags.append("ROIC深度为负")
    if market_cap < 20:
        flags.append("微盘股(<20亿)")
    fields["caution_flags"] = flags
    fields["is_loss_making"] = fields["net_profit_ttm_yi"] <= 0
    fields["is_negative_equity"] = fields["total_equity_yi"] <= 0
    fields["data_quality_score"] = max(1, 10 - len(flags))

    # ── 前瞻信号面板 ──
    fields["_forward_looking"] = {"status": "unavailable", "categories": {}, "text_summary": ""}
    try:
        fw = compute_forward_signals(
            bs_quarterly=r.get("ts_bs_q"),
            income_quarterly=r.get("ts_income_q"),
            cf_quarterly=r.get("ts_cf_q"),
            forecast_data=r.get("ts_forecast"),
            express_data=r.get("ts_express"),
            shareholder_data=r.get("ts_shareholder"),
            segment_revenue=r.get("segment"),
            tushare_segments=r.get("ts_fina_mainbz"),
            fina_indicator=ts_fi,
            core_fields=fields,
        )
        if fw.get("status") != "unavailable":
            fields["_forward_looking"] = {
                "status": fw.get("status", "partial"),
                "categories": {
                    "demand_reality": fw["categories"].get("demand_reality", {}),
                    "supply_readiness": fw["categories"].get("supply_readiness", {}),
                    "earnings_elasticity": fw["categories"].get("earnings_elasticity", {}),
                    "cashflow_quality": fw["categories"].get("cashflow_quality", {}),
                    "management_guidance": fw["categories"].get("management_guidance", {}),
                },
                "text_summary": fw.get("text_summary", ""),
                "sources_available": fw.get("sources_available", []),
                "sources_missing": fw.get("sources_missing", []),
            }
    except Exception:
        pass  # 前瞻信号不是关键路径

    # ── OCF TTM 双源同步: forward_looking 使用 Tushare 4季加总(更准确),
    #     回填 core.ocf_ttm_yi 消除与 investoday 单值 TTM 的不一致 ──
    fw_cf = fields.get("_forward_looking", {}).get("categories", {}).get("cashflow_quality", {})
    fw_ocf = fw_cf.get("ocf_to_ni", {}).get("ocf_ttm")
    if fw_ocf is not None and isinstance(fw_ocf, (int, float)) and fw_ocf > 0:
        core_ocf = fields.get("ocf_ttm_yi", 0)
        if abs(fw_ocf - core_ocf) > 0.01:  # 差异>0.01亿时同步
            fields["ocf_ttm_yi"] = round(fw_ocf, 2)

    return fields


def _calc_interest_expense(income: dict) -> float:
    fe = _num(income.get("finance_expense"))
    return fe / 1e8 if fe and fe > 0 else 0


def _calc_yoy_growth(raw_bundle: dict, stock_code: str) -> float | None:
    """尝试计算净利润同比增速，依赖最近两期数据。"""
    try:
        inc = raw_bundle["raw"].get("income", {})
        np1 = _num(inc.get("net_profit_ttm"))
        return None  # TTM 单期无法算同比，需要另外的 API
    except Exception:
        return None


# ═══════════════════════════════════════
# 增量补取字段 → API 映射
# ═══════════════════════════════════════

# 可增量补取的字段及其数据源
INCREMENTAL_FIELD_SOURCES: dict[str, str] = {
    "peer_median_pe": "financial_rankings",
    "peer_median_ps": "financial_rankings",
    "historical_pe_range": "valuation",
    "beta": "daily_prices",
    "wacc_estimate": "bond_yields",
    "industry_cycle_position": "industry_forecast",
    "dividend_yield": "valuation",
    "segment_breakdown": "business_themes",
    "subscribers": "business_themes",
    "arpu": "business_themes",
    "capacity_utilization": "business_themes",
}


# ═══════════════════════════════════════
# DataForge 主类
# ═══════════════════════════════════════

@dataclass
class PackageResult:
    """单个数据包的结果。"""
    name: str
    fields: dict[str, Any] = field(default_factory=dict)
    status: str = "empty"        # complete | partial | empty
    missing_fields: list[str] = field(default_factory=list)
    quality_score: int = 10
    errors: list[str] = field(default_factory=list)


class DataForge:
    """分层数据拉取引擎。"""

    def __init__(self):
        self.fetcher = DataFetcher()
        self._raw_bundle: dict | None = None
        self._fetched_packages: dict[str, PackageResult] = {}

    def run(self, pre_routing_result: dict) -> dict:
        """
        按 Agent-0 的 data_requirements 分层拉取数据。

        pre_routing_result: Agent-0.run() 的返回值（或至少含 data_requirements）
        返回完整数据包。
        """
        pr = pre_routing_result.get("pre_routing_result", pre_routing_result)
        dr = pr.get("data_requirements", {})

        request_id = pr.get("request_id", pr.get("ticker", ""))
        ticker = (pr.get("ticker", "") or
                  pre_routing_result.get("stock_code", ""))
        stock_name = pr.get("stock_name", "")
        # bstudio_create_time 是 Coze 系统字段，始终存在；event_date 常为空
        event_date = pr.get("bstudio_create_time", "") or pr.get("event_date", "")

        # ── Step 0.5: 事件窗口价格（Phase 2 计价判断用）──
        event_window_prices = None
        if event_date:
            try:
                event_window_prices = self.fetcher.fetch_event_window_prices(
                    ticker, event_date
                )
            except Exception:
                pass

        # ── Step 1: 并行拉取核心数据源（一次调用获取全部 raw） ──
        self._raw_bundle = _fetch_core_bundle(self.fetcher, ticker)

        # ── Step 2: 提取 core_package 字段 ──
        core_pkg = PackageResult(name="core")
        core_pkg.fields = _extract_core_fields(self._raw_bundle, ticker)

        # 检查 core 关键字段是否全部存在且非零
        core_required = [
            "market_cap_yi", "revenue_ttm_yi", "net_profit_ttm_yi",
            "total_assets_yi", "total_equity_yi", "pe_ttm", "pb",
        ]
        # 市值/营收/净资产/PE 为零或 None 均视为数据拉取失败
        for k in core_required:
            v = core_pkg.fields.get(k)
            if v is None or v == 0:
                core_pkg.missing_fields.append(k)

        if core_pkg.missing_fields:
            raise DataForgeError(
                "E101", "core_package 关键字段缺失",
                {"missing": core_pkg.missing_fields, "stock_code": ticker},
            )

        core_pkg.status = "complete"
        core_pkg.quality_score = core_pkg.fields.get("data_quality_score", 10)
        self._fetched_packages["core"] = core_pkg

        # 如果 raw_bundle 有 API 错误，记录但不终止
        raw_errors = self._raw_bundle.get("errors", [])
        if raw_errors:
            core_pkg.errors = [e["error"] for e in raw_errors]

        # ── Step 3: specialized_package（允许部分缺失） ──
        sp_pkg = self._fetch_specialized(dr.get("specialized_package", {}), ticker)
        self._fetched_packages["specialized"] = sp_pkg

        # ── Step 4: validation_package（允许缺失） ──
        vp_pkg = self._fetch_validation(dr.get("validation_package", {}), ticker)
        self._fetched_packages["validation"] = vp_pkg

        # ── Step 5: optional_package（忽略失败） ──
        op_pkg = self._fetch_optional(dr.get("optional_package", {}), ticker)
        self._fetched_packages["optional"] = op_pkg

        # ── Step 6: 组装输出 ──
        all_errors = []
        for pkg in self._fetched_packages.values():
            all_errors.extend(pkg.errors)

        # 计算整体数据质量
        weights = {"core": 0.5, "specialized": 0.25, "validation": 0.15, "optional": 0.10}
        overall_q = sum(
            weights.get(name, 0.1) * pkg.quality_score
            for name, pkg in self._fetched_packages.items()
        )

        return {
            "request_id": request_id,
            "stock_code": ticker,
            "stock_name": stock_name or core_pkg.fields.get("stock_name", ""),
            "industry": core_pkg.fields.get("industry_sw_l1", ""),
            "packages": {
                "core": {
                    "fields": core_pkg.fields,
                    "status": core_pkg.status,
                    "quality_score": core_pkg.quality_score,
                    "missing_fields": core_pkg.missing_fields,
                },
                "specialized": {
                    "fields": sp_pkg.fields,
                    "status": sp_pkg.status,
                    "quality_score": sp_pkg.quality_score,
                    "missing_fields": sp_pkg.missing_fields,
                },
                "validation": {
                    "fields": vp_pkg.fields,
                    "status": vp_pkg.status,
                    "quality_score": vp_pkg.quality_score,
                    "missing_fields": vp_pkg.missing_fields,
                },
                "optional": {
                    "fields": op_pkg.fields,
                    "status": op_pkg.status,
                    "quality_score": op_pkg.quality_score,
                    "missing_fields": op_pkg.missing_fields,
                },
            },
            "overall_data_quality_score": round(overall_q),
            "fetch_errors": all_errors,
            "event_date": event_date,
            "event_window_prices": event_window_prices or {},
            "incremental_fetch_hook": {
                "available": True,
                "description": "调用 DataForge.fetch_incremental(fields) 补取缺失字段",
            },
        }

    def fetch_incremental(self, fields_to_fetch: list[str]) -> dict:
        """
        增量补取：仅拉取指定字段（不复拉已获取的）。

        供 Orchestrator 在 Agent-2 发现缺失时调用。
        返回 {field_name: value}。
        """
        if self._raw_bundle is None:
            return {}

        result: dict[str, Any] = {}
        r = self._raw_bundle["raw"]

        for field in fields_to_fetch:
            source = INCREMENTAL_FIELD_SOURCES.get(field)
            if not source:
                result[field] = None
                continue

            try:
                # 大部分增量字段来自已有 raw_bundle 的子项或可通过已有 API 补充
                if source == "valuation":
                    val = r.get("valuation", {})
                    if field == "dividend_yield":
                        result[field] = val.get("dividend_yield")
                    elif field == "historical_pe_range":
                        result[field] = val.get("pe_ttm_historical_rank")
                elif source == "business_themes":
                    themes = self.fetcher.fetch_business_themes(
                        self._raw_bundle["raw"].get("quote", {}).get("stock_code", "")
                    )
                    result[field] = themes.get(field, "")
                elif source == "financial_rankings":
                    ind = r.get("industries", {})
                    ind_code = ind.get("sw_l1_code", "")
                    if ind_code:
                        rankings = self.fetcher.fetch_financial_rankings(ind_code)
                        result["peer_data"] = rankings
                elif source == "bond_yields":
                    result[field] = None  # 通过 CLI 独立获取
                else:
                    result[field] = None
            except Exception:
                result[field] = None

        return result

    # ── 内部方法 ──

    def _fetch_specialized(self, spec_req: dict, stock_code: str) -> PackageResult:
        """拉取 specialized_package 字段。"""
        pkg = PackageResult(name="specialized")
        requested_fields = spec_req.get("fields", [])
        if not requested_fields:
            pkg.status = "empty"
            return pkg

        # 大部分 specialized 字段来自 business_themes 或需要第三方数据
        try:
            themes = self.fetcher.fetch_business_themes(stock_code)
        except Exception:
            themes = {}

        for field in requested_fields:
            val = themes.get(field) or _fetch_extra_field(self.fetcher, stock_code, field)
            if val is not None:
                pkg.fields[field] = val
            else:
                pkg.missing_fields.append(field)

        fetched_count = len(pkg.fields)
        total = len(requested_fields)
        if fetched_count == 0:
            pkg.status = "empty"
            pkg.quality_score = 0
        elif fetched_count < total:
            pkg.status = "partial"
            pkg.quality_score = max(1, 10 - len(pkg.missing_fields))
        else:
            pkg.status = "complete"
            pkg.quality_score = 10

        return pkg

    def _fetch_validation(self, val_req: dict, stock_code: str) -> PackageResult:
        """拉取 validation_package 字段。"""
        pkg = PackageResult(name="validation")
        requested_fields = val_req.get("fields", [])
        if not requested_fields:
            pkg.status = "empty"
            return pkg

        # 同行比较数据
        try:
            ind = self.fetcher.fetch_industries(stock_code)
            ind_code = ind.get("sw_l1_code", "")
            if ind_code:
                rankings = self.fetcher.fetch_financial_rankings(ind_code)
                if rankings:
                    pkg.fields["peer_rankings"] = rankings
                    # 从排名中提取中位数 PE/PS
                    try:
                        pes = [item.get("net_profit_parent_rank", 0) for item in rankings]
                        pkg.fields["peer_median_pe"] = _median(pes)
                    except Exception:
                        pkg.fields["peer_median_pe"] = None
            if ind_code:
                forecast = self.fetcher.fetch_industry_forecast(ind_code)
                pkg.fields["industry_forecast"] = forecast
        except Exception:
            pass

        for field in requested_fields:
            if field not in pkg.fields:
                pkg.missing_fields.append(field)

        fetched_count = len([f for f in requested_fields if f in pkg.fields])
        total = len(requested_fields)
        if fetched_count == 0:
            pkg.status = "empty"
            pkg.quality_score = 0
        elif fetched_count < total:
            pkg.status = "partial"
            pkg.quality_score = max(1, 10 - len(pkg.missing_fields))
        else:
            pkg.status = "complete"
            pkg.quality_score = 10

        return pkg

    def _fetch_optional(self, opt_req: dict, stock_code: str) -> PackageResult:
        """拉取 optional_package 字段。"""
        pkg = PackageResult(name="optional")
        requested_fields = opt_req.get("fields", [])
        if not requested_fields:
            pkg.status = "empty"
            return pkg

        try:
            themes = self.fetcher.fetch_business_themes(stock_code)
        except Exception:
            themes = {}

        for field in requested_fields:
            val = themes.get(field)
            if val is not None:
                pkg.fields[field] = val
            else:
                pkg.missing_fields.append(field)

        fetched_count = len(pkg.fields)
        total = len(requested_fields)
        if fetched_count == 0:
            pkg.status = "empty"
            pkg.quality_score = 0
        elif fetched_count < total:
            pkg.status = "partial"
            pkg.quality_score = max(1, 10 - len(pkg.missing_fields))
        else:
            pkg.status = "complete"
            pkg.quality_score = 10

        return pkg


# ═══════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════

def _num(v: Any) -> float:
    """安全转数值。"""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _pct(v: Any) -> float:
    """安全转百分比（保持原值，不乘100）。"""
    if v is None:
        return 0.0
    try:
        val = float(v)
        return val if abs(val) < 10 else val
    except (ValueError, TypeError):
        return 0.0


def _warn_divergence(stock_code: str, field: str,
                     ts_val: float | None, io_val: float | None,
                     threshold: float = 0.15):
    """交叉验证: Tushare vs investoday 数据差异超过阈值时打印警告。"""
    if ts_val is None or io_val is None:
        return
    if ts_val == 0 or io_val == 0:
        return  # 一边为0不算差异(可能是数据不可用)
    diff = abs(ts_val - io_val) / max(abs(ts_val), abs(io_val))
    if diff > threshold:
        print(f"  [数据差异] {stock_code} {field}: Tushare={ts_val:.2f} investoday={io_val:.2f} "
              f"差异={diff:.1%}", flush=True)


def _median(values: list) -> float:
    """计算中位数。"""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    return sorted_vals[n // 2]


def _fetch_extra_field(fetcher: DataFetcher, stock_code: str, field: str) -> Any:
    """尝试通过特定 API 获取单个特殊字段。"""
    try:
        if field in ("pipeline_list", "clinical_phase", "clinical_trial_updates",
                     "competitive_pipeline_landscape", "pos_assumptions", "peak_sales_estimate"):
            themes = fetcher.fetch_business_themes(stock_code)
            return themes.get("tech_path_rd", "") or themes.get("business_status", "")
        if field in ("capacity_utilization", "order_backlog", "yield_rate",
                     "customer_concentration", "capacity_expansion_plan", "capex_breakdown"):
            themes = fetcher.fetch_business_themes(stock_code)
            return themes.get("operating_data", "") or themes.get("industry_chain_capacity", "")
        if field in ("subscribers", "arpu", "cac", "ltv", "churn_rate"):
            themes = fetcher.fetch_business_themes(stock_code)
            return themes.get("operating_data", "") or themes.get("business_status", "")
        if field in ("proven_reserves", "probable_reserves", "commodity_price",
                     "extraction_cost_rate", "mine_life"):
            themes = fetcher.fetch_business_themes(stock_code)
            return themes.get("operating_data", "")
        if field in ("npl_ratio", "net_interest_margin", "capital_adequacy_ratio"):
            dup = fetcher.fetch_dupont(stock_code)
            return dup.get("roe", "")
        if field in ("nav_breakdown", "rental_yield", "occupancy_rate",
                     "debt_maturity_schedule", "control_change_event",
                     "injection_asset_description", "shell_value_estimate",
                     "policy_document_reference", "subsidy_amount", "tax_benefit_duration",
                     "distress_recovery_timeline", "asset_restructuring_plan",
                     "cash_burn_rate", "depreciation_schedule"):
            themes = fetcher.fetch_business_themes(stock_code)
            return themes.get("business_status", "") or themes.get("development_prospect", "")
    except Exception:
        pass
    return None


# ── 便捷函数 ──

def forge_data(pre_routing_result: dict) -> dict:
    """便捷入口：运行完整数据炼器。"""
    forge = DataForge()
    return forge.run(pre_routing_result)
