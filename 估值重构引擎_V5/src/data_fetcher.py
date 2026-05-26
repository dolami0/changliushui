"""
估值重构引擎 — 数据获取层
封装 investoday-api CLI，将原始 API 输出映射到 5 层上下文字段。

investoday-api 通过 npx 调用，输出为 JSON。本模块负责：
1. 构造 CLI 参数（GET vs POST）
2. 执行调用并解析 JSON
3. 将原始字段映射到语义化字段名
4. 单次运行的查询结果缓存（避免重复请求）
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


class DataFetcher:
    """investoday-api 数据获取封装。所有方法返回 dict 或 list[dict]。"""

    def __init__(self, config_path: str = "config/endpoint_mapping.yaml"):
        self.project_root = Path(__file__).resolve().parent.parent
        self.config = self._load_config(self.project_root / config_path)
        self._cache: dict[str, Any] = {}

        # 默认日期范围：最近 5 个季度（覆盖 TTM 和同比比较）
        now = datetime.now()
        self.default_begin = (now - timedelta(days=730)).strftime("%Y-%m-%d")
        self.default_end = now.strftime("%Y-%m-%d")

    def _load_config(self, path: Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ── CLI 调用核心 ─────────────────────────────────

    def _cli(self, path: str, method: str = "GET", **params: Any) -> dict | list:
        """
        调用 investoday-api CLI 并返回解析后的 JSON。

        GET:  investoday-api <path> key=value ...
        POST: investoday-api <path> --method POST key=value ...
        """
        # 使用 node 直接调用本地 CLI，避免 npx 不在 PATH 的问题
        cli_script = str(
            self.project_root
            / "node_modules"
            / "@investoday"
            / "investoday-api"
            / "bin"
            / "investoday-api.js"
        )
        args = ["node", cli_script, path]
        if method.upper() == "POST":
            args.append("--method")
            args.append("POST")

        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, list):
                # 数组参数重复出现: fundCodes=000001 fundCodes=000004
                for v in value:
                    args.append(f"{key}={v}")
            else:
                args.append(f"{key}={value}")

        cache_key = json.dumps(args, ensure_ascii=False)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 注入环境变量：优先用 INVESTODAY_API_KEY，否则从 config.json 读取，最后 CLI 从凭证文件读取
        env = os.environ.copy()
        api_key = os.environ.get("INVESTODAY_API_KEY", "")
        if not api_key:
            # 尝试从 valuation_app/config.json 读取
            config_json = self.project_root / "valuation_app" / "config.json"
            if config_json.exists():
                try:
                    with open(config_json, encoding="utf-8") as f:
                        cfg = json.load(f)
                    api_key = cfg.get("investoday_api_key", "")
                except Exception:
                    pass
        if api_key:
            env["INVESTODAY_API_KEY"] = api_key

        result = subprocess.run(
            args,
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            env=env,
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(
                f"investoday-api 调用失败: {' '.join(args)}\n{error_msg}"
            )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"investoday-api 返回非 JSON: {result.stdout[:500]}"
            )

        self._cache[cache_key] = data
        return data

    # ── 第 1 层：公司基本面快照 ─────────────────────

    def fetch_realtime_quote(self, stock_code: str) -> dict:
        """实时行情：当前价格、市值、涨跌幅、换手率、行业"""
        raw = self._cli("stock-quote/realtime", stockCode=stock_code)
        item = self._first(raw)
        return {
            "stock_code": item.get("stockCode", stock_code),
            "stock_name": item.get("stockName", ""),
            "current_price": self._num(item.get("currentPrice")),
            "prev_close": self._num(item.get("closePriceYDay")),
            "change_ratio_1d": self._pct(item.get("changeRatio")),
            "change_ratio_1w": self._pct(item.get("changeRatio1W")),
            "change_ratio_1m": self._pct(item.get("changeRatioB1M")),
            "market_cap": self._num(item.get("totalValue")),
            "circulation_value": self._num(item.get("circulationValue")),
            "turnover_rate": self._pct(item.get("turnOverRate")),
            "industry_name": item.get("industryName", ""),
            "industry_code": item.get("industryCode", ""),
        }

    def fetch_valuation(self, stock_code: str) -> dict:
        """估值指标：PE/PB/PS/PEG/EV_EBITDA + 行业排名 + 历史分位

        字段映射依据 investoday API 文档 stock/finance/valuation:
        f2250=市盈率 f2260=预估市盈率 f2270=市盈增长比 f2280=市销率
        f2290=市净率(PB) f2300=股价/每股经营现金流 f2310=EV/EBITDA
        f2320=EV/Revenue f2330=Joel Greenblatt收益率 f2340=扣非市盈率
        f2350=周期调整市盈率(CAPE) f2370=股价/每股有形账面价值
        f2380=股价/FCF f2390=EV/EBIT
        """
        raw = self._cli("stock/finance/valuation", stockCode=stock_code)
        item = self._first(raw)
        return {
            "pe_ttm": self._num(item.get("f2250")),
            "pe_ttm_industry_rank": self._num(item.get("f2250Rk")),
            "pe_ttm_historical_rank": self._num(item.get("f2250RkHist")),
            "pe_forward": self._num(item.get("f2260")),
            "pe_forward_industry_rank": self._num(item.get("f2260Rk")),
            "peg": self._num(item.get("f2270")),
            "peg_industry_rank": self._num(item.get("f2270Rk")),
            "ps_ttm": self._num(item.get("f2280")),
            "ps_industry_rank": self._num(item.get("f2280Rk")),
            "pb": self._num(item.get("f2290")),                       # f2290=市净率(PB标准)
            "pb_industry_rank": self._num(item.get("f2290Rk")),
            "pb_historical_rank": self._num(item.get("f2290RkHist")),
            "ev_ebitda": self._num(item.get("f2310")),                # f2310=企业价值倍数(EV/EBITDA)
            "ev_revenue": self._num(item.get("f2320")),               # f2320=EV/Revenue
            "price_fcf": self._num(item.get("f2380")),                # f2380=股价/自由现金流
            "cape": self._num(item.get("f2350")),                     # f2350=周期调整市盈率(CAPE)
            "price_tangible_bv": self._num(item.get("f2370")),        # f2370=股价/每股有形账面价值
            "ev_ebit": self._num(item.get("f2390")),                  # f2390=EV/EBIT
            "dividend_yield": None,  # 此端点未暴露股息率
        }

    def fetch_income_ttm(self, stock_code: str) -> dict:
        """利润表 TTM 最新一期"""
        raw = self._cli(
            "stock/income-statements-ttm",
            method="POST",
            stockCode=stock_code,
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        return {
            "report_date": item.get("reportDate", ""),
            "revenue_ttm": self._num(item.get("revenue")),
            "cost_of_revenue": self._num(item.get("costOfGoodsSold")),
            "operating_profit": self._num(item.get("operatingProfit")),
            "net_profit_ttm": self._num(item.get("netProfitParent")),
            "eps": self._num(item.get("eps")),
            "profit_before_tax": self._num(item.get("profitBeforeTax")),
            "income_tax": self._num(item.get("incomeTax")),
            "selling_expense": self._num(item.get("sellingExpense")),
            "admin_expense": self._num(item.get("adminExpense")),
            "finance_expense": self._num(item.get("financeExpense")),
            "investment_income": self._num(item.get("investmentIncome")),
            "fair_value_change": self._num(item.get("fairValueChangeIncome")),
        }

    def fetch_balance_ttm(self, stock_code: str) -> dict:
        """资产负债表 TTM 最新一期"""
        raw = self._cli(
            "stock/balance-sheets-ttm",
            method="POST",
            stockCode=stock_code,
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        return {
            "report_date": item.get("reportPeriodEnd", ""),
            "total_assets": self._num(item.get("totalAssets")),
            "current_assets": self._num(item.get("totalCurrentAssets")),
            "cash_equivalents": self._num(item.get("cashAndEquiv")),
            "accounts_receivable": self._num(item.get("accountsReceivable")),
            "prepayments": self._num(item.get("prepayments")),
            "inventory": self._num(item.get("inventory")),
            "non_current_assets": self._num(item.get("totalNonCurrentAssets")),
            "total_liabilities": self._num(item.get("totalLiabilities")),
            "current_liabilities": self._num(item.get("totalCurrentLiabilities")),
            "non_current_liabilities": self._num(item.get("totalNonCurrentLiabilities")),
            "total_equity": self._num(item.get("totalEquity")),
            "equity_parent": self._num(item.get("equityParent")),
        }

    def fetch_cashflow_ttm(self, stock_code: str) -> dict:
        """现金流量表 TTM 最新一期"""
        raw = self._cli(
            "stock/cash-flows-ttm",
            method="POST",
            stockCode=stock_code,
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        op_in = self._num(item.get("cashInflowOperating", 0)) or 0
        op_out = self._num(item.get("cashOutflowOperating", 0)) or 0
        operating_cf = op_in - op_out
        capex = self._num(item.get("cashPaidFixedAssets", 0)) or 0
        inv_in = self._num(item.get("cashInflowInvesting", 0)) or 0
        inv_out = self._num(item.get("cashOutflowInvesting", 0)) or 0
        fin_in = self._num(item.get("cashInflowFinancing", 0)) or 0
        fin_out = self._num(item.get("cashOutflowFinancing", 0)) or 0
        return {
            "report_date": item.get("reportDate", ""),
            "operating_cash_flow": operating_cf,
            "capex_payments": capex,
            "fcf": operating_cf - abs(capex),
            "investing_cash_flow": inv_in - inv_out,
            "financing_cash_flow": fin_in - fin_out,
        }

    def fetch_dupont(self, stock_code: str) -> dict:
        """杜邦分析最新一期"""
        raw = self._cli(
            "stock/dupont-analysis",
            method="POST",
            stockCode=stock_code,
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        return {
            "report_date": item.get("reportPeriodEnd", ""),
            "roe": self._pct(item.get("roe")),
            "net_margin_parent": self._pct(item.get("netMarginParent")),
            "asset_turnover": self._num(item.get("assetTurnover")),
            "equity_multiplier": self._num(item.get("equityMultiplier")),
            "ebit_margin": self._pct(item.get("ebitMargin")),
            "tax_burden": self._pct(item.get("taxBurden")),
            "interest_burden": self._pct(item.get("interestBurden")),
            "net_profit": self._num(item.get("netProfit")),
        }

    def fetch_industries(self, stock_code: str) -> dict:
        """申万行业分类"""
        raw = self._cli(
            "stock/industries",
            method="POST",
            stockCode=stock_code,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        return {
            "sw_l1_name": item.get("industryNameSwL1", ""),
            "sw_l1_code": item.get("industryCodeSwL1", ""),
            "sw_l2_name": item.get("industryNameSwL2", ""),
            "sw_l2_code": item.get("industryCodeSwL2", ""),
            "sw_l3_name": item.get("industryNameSwL3", ""),
            "sw_l3_code": item.get("industryCodeSwL3", ""),
        }

    def fetch_score(self, stock_code: str) -> dict:
        """个股综合得分"""
        raw = self._cli("stock/score", stockCode=stock_code)
        item = self._first(raw)
        return {
            "composite_score": self._num(item.get("score")),
            "composite_score_avg": self._num(item.get("scoreAvg")),
            "finance_score": self._num(item.get("financeScore")),
            "finance_score_avg": self._num(item.get("financeScoreAvg")),
            "sentiment_score": self._num(item.get("emotionScore")),
            "sentiment_score_avg": self._num(item.get("emotionScoreAvg")),
            "industry_score": self._num(item.get("industryScore")),
            "industry_score_avg": self._num(item.get("industryScoreAvg")),
            "technical_score": self._num(item.get("skillScore")),
            "technical_score_avg": self._num(item.get("skillScoreAvg")),
        }

    def fetch_operating_review(self, stock_code: str) -> dict:
        """最新经营评述（管理层讨论）"""
        raw = self._cli(
            "stock/operating-reviews",
            stockCode=stock_code,
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        return {
            "publish_date": item.get("publishDate", ""),
            "report_period": item.get("reportPeriodEnd", ""),
            "operational_review": item.get("operationalReview", ""),
        }

    def fetch_fin_der_inds(self, stock_code: str) -> dict:
        """财务衍生指标: ROIC(小数→×100)/有息负债/EBIT/毛利率/净利率"""
        raw = self._cli(
            "stock/fin-der-inds",
            method="POST",
            stockCode=stock_code,
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        roic_raw = self._num(item.get("roic"))
        gm_raw = self._num(item.get("grossMargin"))
        nm_raw = self._num(item.get("netMargin"))
        return {
            "report_date": item.get("expireDate", ""),
            "interest_bearing_debt": self._num(item.get("interestBearingDebt")),
            "ebit": self._num(item.get("ebit")),
            "ebitda": self._num(item.get("ebitda")),
            "roic": roic_raw * 100 if roic_raw is not None and abs(roic_raw) < 10 else roic_raw,
            "gross_margin": gm_raw if gm_raw and abs(gm_raw) > 1 else (gm_raw * 100 if gm_raw else None),
            "net_margin": nm_raw if nm_raw and abs(nm_raw) > 1 else (nm_raw * 100 if nm_raw else None),
            "roe_diluted": self._num(item.get("roeDiluted")),
            "roa": self._num(item.get("roa")),
            "ebit_interest_coverage": self._num(item.get("ebitInterestCoverage")),
        }

    def fetch_profit_ability(self, stock_code: str) -> dict:
        """盈利能力指标 + 历史排名 — stock/finance/profit-ability (GET)

        字段映射依据 investoday API 文档:
        f2030=毛利率% f2040=营业利润率% f2050=净利率%
        f2060=ROE% f2070=ROA% f2080=资本回报率%
        f2090=Joel Greenblatt ROC f2100=ROCE f2500=盈利能力综合得分
        所有指标均含当前排名(Rk)和历史排名(RkHist) [0-100]
        """
        raw = self._cli("stock/finance/profit-ability", stockCode=stock_code)
        item = self._first(raw)
        return {
            "gross_margin_pct": self._num(item.get("f2030")),
            "gross_margin_rank": self._num(item.get("f2030Rk")),
            "gross_margin_historical_rank": self._num(item.get("f2030RkHist")),
            "operating_margin_pct": self._num(item.get("f2040")),
            "operating_margin_rank": self._num(item.get("f2040Rk")),
            "operating_margin_historical_rank": self._num(item.get("f2040RkHist")),
            "net_margin_pct": self._num(item.get("f2050")),
            "net_margin_rank": self._num(item.get("f2050Rk")),
            "net_margin_historical_rank": self._num(item.get("f2050RkHist")),
            "roe_pct": self._num(item.get("f2060")),
            "roe_rank": self._num(item.get("f2060Rk")),
            "roe_historical_rank": self._num(item.get("f2060RkHist")),
            "roa_pct": self._num(item.get("f2070")),
            "roa_rank": self._num(item.get("f2070Rk")),
            "roa_historical_rank": self._num(item.get("f2070RkHist")),
            "roic_pct": self._num(item.get("f2080")),
            "roic_rank": self._num(item.get("f2080Rk")),
            "roic_historical_rank": self._num(item.get("f2080RkHist")),
            "joel_greenblatt_roc": self._num(item.get("f2090")),
            "joel_greenblatt_roc_rank": self._num(item.get("f2090Rk")),
            "joel_greenblatt_roc_historical_rank": self._num(item.get("f2090RkHist")),
            "roce_pct": self._num(item.get("f2100")),
            "roce_rank": self._num(item.get("f2100Rk")),
            "roce_historical_rank": self._num(item.get("f2100RkHist")),
            "profitability_composite_score": self._num(item.get("f2500")),
        }

    def fetch_daily_prices(self, stock_code: str, begin_date: str, end_date: str) -> list[dict]:
        """个股前复权日行情 — 用于Beta计算"""
        raw = self._cli(
            "stock/adjusted-quotes",
            method="POST",
            stockCode=stock_code,
            beginDate=begin_date,
            endDate=end_date,
            pageNum=1,
            pageSize=300,
        )
        items = self._list(raw)
        return [
            {"date": i.get("tradeDate", i.get("date", "")), "close": self._num(i.get("closePrice"))}
            for i in items if self._num(i.get("closePrice"))
        ]

    def fetch_index_daily_prices(self, index_code: str, begin_date: str, end_date: str) -> list[dict]:
        """指数历史日行情 — 用于Beta计算"""
        raw = self._cli(
            "index/quotes",
            indexCode=index_code,
            beginDate=begin_date,
            endDate=end_date,
            pageNum=1,
            pageSize=300,
        )
        items = self._list(raw)
        return [
            {"date": i.get("date", ""), "close": self._num(i.get("closePrice"))}
            for i in items if self._num(i.get("closePrice"))
        ]

    def fetch_business_themes(self, stock_code: str) -> dict:
        """股票主营业务与投资主题 — 替代Agent 0 投资地图"""
        raw = self._cli("stock/business-investment-themes", method="POST", stockCode=stock_code)
        item = self._first(raw)
        return {
            "business_status": item.get("businessStatus", ""),
            "investment_theme": item.get("investmentTheme", ""),
            "industry_chain_capacity": item.get("industryChainCapacity", ""),
            "tech_path_rd": item.get("techPathRdPipeline", ""),
            "operating_data": item.get("operatingData", ""),
            "development_prospect": item.get("developmentProspect", ""),
            "main_business_conclusion": item.get("mainBusinessConclusion", ""),
            "brand_channel": item.get("brandChannel", ""),
        }

    def fetch_investment_risks(self, stock_code: str) -> dict:
        """股票投资风险分析"""
        raw = self._cli("stock/investment-risks", method="POST", stockCode=stock_code)
        item = self._first(raw)
        return {
            "competition_risk": item.get("competitionRisk", ""),
            "operation_risk": item.get("operationRisk", ""),
            "project_risk": item.get("projectRisk", ""),
            "macro_risk": item.get("macroRisk", ""),
        }

    # ── 第 2 层：行业与可比公司 ─────────────────────

    def fetch_industry_realtime(self, industry_code: str) -> dict:
        """行业实时行情"""
        raw = self._cli("industry-quote/realtime", industryCode=industry_code)
        item = self._first(raw)
        return {
            "industry_name": item.get("industryName", ""),
            "industry_price": self._num(item.get("price")),
            "change_ratio": self._pct(item.get("changeRatio")),
            "change_ratio_1w": self._pct(item.get("changeRatio1W")),
            "total_value": self._num(item.get("totalValue")),
            "constituent_count": item.get("industryAmount", 0),
            "up_count": item.get("stockUpAmount", 0),
            "down_count": item.get("stockDownAmount", 0),
            "lead_stock_code": item.get("leadUpStockCode", ""),
            "lead_stock_name": item.get("leadUpStockName", ""),
            "rank": item.get("ratioRank", 0),
        }

    def fetch_industry_forecast(self, industry_code: str) -> dict:
        """行业增长预测"""
        raw = self._cli("industry/forecasts", industryCode=industry_code)
        item = self._first(raw)
        return {
            "industry_name": item.get("industryName", ""),
            "t_year": item.get("TYear", ""),
            "net_profit_growth_t": self._pct(item.get("tYearNetProfitGrowthRate")),
            "net_profit_growth_t1": self._pct(item.get("tPlus1YNetProfitGrowthRate")),
            "net_profit_growth_t2": self._pct(item.get("tPlus2YNetProfitGrowthRate")),
            "net_profit_growth_t3": self._pct(item.get("tPlus3YNetProfitGrowthRate")),
            "revenue_growth_t": self._pct(item.get("tYearBizIncomeGrowthRatePct")),
            "revenue_growth_t1": self._pct(item.get("tPlus1YBusinessIncomeGrowthRatePct")),
            "revenue_growth_t2": self._pct(item.get("tPlus2YBusinessIncomeGrowthRatePct")),
            "revenue_growth_t3": self._pct(item.get("tPlus3YBusinessIncomeGrowthRatePct")),
            "growth_market_rank_t1": item.get("tPlus1YNetProfitGrowthRateMarketRanking"),
        }

    def fetch_financial_rankings(self, industry_code: str) -> dict:
        """行业内财务指标排名列表"""
        raw = self._cli(
            "stock/fin-ind-sw-rnk-q",
            method="POST",
            industryCode=industry_code,
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=30,
        )
        items = self._list(raw)
        return [
            {
                "stock_code": i.get("stockCode", ""),
                "stock_name": i.get("stockName", ""),
                "roe_rank": i.get("roeRank", 999),
                "roa_rank": i.get("roaRank", 999),
                "revenue_rank": i.get("revenueRank", 999),
                "gross_margin_rank": i.get("grossMarginRank", 999),
                "net_margin_rank": i.get("netMarginRank", 999),
                "net_profit_rank": i.get("netProfitParentRank", 999),
                "net_profit_yoy_rank": i.get("netProfitParentYoyRank", 999),
                "rd_expense_rank": i.get("rdExpenseRank", 999),
            }
            for i in items
        ]

    # ── 第 3 层：事件数据 ──────────────────────────

    def fetch_major_contracts(self, stock_code: str) -> list[dict]:
        """重大合同（最近 1 年）"""
        raw = self._cli(
            "stock/major-contracts",
            method="POST",
            stockCode=stock_code,
            beginDate=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
            endDate=self.default_end,
            pageNum=1,
            pageSize=10,
        )
        items = self._list(raw)
        return [
            {
                "publish_date": i.get("publishDate", ""),
                "subject": i.get("contractSubject", ""),
                "counterparty": i.get("counterpartyName", ""),
                "amount": self._num(i.get("amount")),
                "sign_date": i.get("agreementSignDate", ""),
                "impact": i.get("contractImpact", ""),
                "progress": i.get("eventProgressDesc", ""),
                "content": i.get("eventContent", ""),
            }
            for i in items
        ]

    def fetch_litigation(self, stock_code: str) -> list[dict]:
        """诉讼仲裁（最近 1 年）"""
        raw = self._cli(
            "stock/arbitration-cases",
            method="POST",
            stockCode=stock_code,
            beginDate=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
            endDate=self.default_end,
            pageNum=1,
            pageSize=10,
        )
        items = self._list(raw)
        return [
            {
                "announce_date": i.get("announceDate", ""),
                "content": i.get("eventContent", ""),
                "plaintiff": i.get("litigationPlaintiff", ""),
                "defendant": i.get("litigationDefendant", ""),
                "amount": self._num(i.get("latestLitigationAmount")),
                "progress": i.get("latestProgressDesc", ""),
                "is_terminated": i.get("isTerminated", "0"),
            }
            for i in items
        ]

    def fetch_violations(self, stock_code: str) -> list[dict]:
        """违规处罚"""
        raw = self._cli(
            "stock/violation-penalties",
            method="POST",
            stockCode=stock_code,
            beginDate=(datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d"),
            endDate=self.default_end,
            pageNum=1,
            pageSize=10,
        )
        items = self._list(raw)
        return [
            {
                "date": i.get("date", ""),
                "violation_type": i.get("violationType", ""),
                "penalty_type": i.get("penaltyType", ""),
                "penalty_amount": self._num(i.get("penaltyAmount")),
                "penalty_authority": i.get("penaltyAuthority", ""),
                "action_desc": i.get("violationAction", ""),
            }
            for i in items
        ]

    def fetch_research_reports(self, stock_code: str) -> list[dict]:
        """研究报告（最近 3 个月）"""
        raw = self._cli(
            "report/research",
            method="POST",
            stockCode=stock_code,
            beginDate=(datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
            endDate=self.default_end,
            pageNum=1,
            pageSize=10,
        )
        items = self._list(raw)
        return [
            {
                "title": i.get("title", ""),
                "author": i.get("author", ""),
                "institution": i.get("institutionName", ""),
                "date": i.get("date", ""),
                "content": (i.get("content", "") or ""),
                "keyword": i.get("keyword", ""),
            }
            for i in items
        ]

    def fetch_consultations(self, stock_code: str) -> list[dict]:
        """互动问答（最近 6 个月）"""
        raw = self._cli(
            "stock/consultations",
            stockCode=stock_code,
            beginDate=(datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d"),
            endDate=self.default_end,
            pageNum=1,
            pageSize=10,
        )
        items = self._list(raw)
        return [
            {
                "date": i.get("date", ""),
                "questioner": i.get("questioner", ""),
                "question": i.get("question", ""),
                "reply": i.get("reply", ""),
                "is_rumor_verified": i.get("isRumorTrue", ""),
            }
            for i in items
        ]

    # ── 第 4 层：市场状态 ──────────────────────────

    def fetch_capital_flow(self, stock_code: str) -> dict:
        """实时资金流向"""
        raw = self._cli("stock-quote/capital-flow", stockCode=stock_code)
        item = self._first(raw)
        return {
            "main_net_inflow": self._num(item.get("mainNetInflow")),
            "large_net_inflow": self._num(item.get("largeNetInflow")),
            "super_large_net_inflow": self._num(item.get("superLargeNetInflow")),
            "date": item.get("date", ""),
        }

    def fetch_bond_yields(self) -> dict:
        """最新国债收益率曲线"""
        raw = self._cli(
            "economic/gover-bond-yield",
            method="POST",
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        return {
            "date": item.get("date", ""),
            "yield_3m": self._pct(item.get("bnd3m")),
            "yield_6m": self._pct(item.get("bnd6m")),
            "yield_2y": self._pct(item.get("bnd2y")),
            "yield_10y": self._pct(item.get("bnd10y")),
            "yield_30y": self._pct(item.get("bnd30y")),
        }

    def fetch_money_supply(self) -> dict:
        """最新货币供应量"""
        raw = self._cli(
            "economic/money-supplies",
            method="POST",
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        return {
            "date": item.get("date", ""),
            "m1_yoy": self._pct(item.get("m1YoyPct")),
            "m2_yoy": self._pct(item.get("m2YoyPct")),
            "m1_m2_spread": self._pct(item.get("m1M2Spread")),
        }

    def fetch_social_financing(self) -> dict:
        """最新社融"""
        raw = self._cli(
            "economic/social-financing-sto",
            method="POST",
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=1,
        )
        item = self._first(raw)
        return {
            "date": item.get("date", ""),
            "total_social_financing": self._num(item.get("totalSocialFinStockYoy")),
            "social_financing_yoy": self._pct(item.get("totalSocialFinStockBn")),
        }

    # ── 第 5 层：催化路径 ──────────────────────────

    def fetch_report_schema(self, stock_code: str) -> list[dict]:
        """财报披露日程"""
        raw = self._cli(
            "stock/report-schema",
            method="POST",
            stockCode=stock_code,
            beginDate=self.default_begin,
            endDate=(datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d"),
            pageNum=1,
            pageSize=5,
        )
        items = self._list(raw)
        return [
            {
                "report_period": i.get("reportDate", ""),
                "actual_publish_date": i.get("actualPublishDate", ""),
                "next_report_date": i.get("nextReportPublishDate", ""),
                "prev_report_period": i.get("prevReportPeriod", ""),
                "same_period_last_year": i.get("samePeriodLastYear", ""),
            }
            for i in items
        ]

    # ── 一致预期 ──────────────────────────────────

    def fetch_analyst_consensus(self, stock_code: str) -> dict:
        """
        分析师一致预期——取最近90天内、不同机构的报告，计算平均值。

        数据来源：report/stock-forecast-ratings
        每份报告 = 某家券商在某个时间点对个股的盈利预测+评级+目标价。
        这个端点不是 Bloomberg/Visible Alpha 那种真正的共识数据，
        而是原始报告级别的数据。我们自己做聚合。

        返回：
        - 近3家不同机构的最新预测均值
        - 预测下修趋势（prev → current 的变化方向和幅度）
        - 评级分布
        - 目标价均值（优先用 targetPriceEx 除权调整后价格）
        """
        raw = self._cli(
            "report/stock-forecast-ratings",
            stockCode=stock_code,
            beginDate=(datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
            endDate=self.default_end,
            pageNum=1,
            pageSize=20,
        )
        items = self._list(raw)

        if not items:
            return {"consensus_status": "data_missing", "note": "最近90天无分析师报告"}

        # 按机构去重，每家只保留最新一份
        seen_institutions: set[str] = set()
        unique_reports: list[dict] = []
        for item in items:
            inst = item.get("institutionName", "")
            if inst and inst not in seen_institutions:
                seen_institutions.add(inst)
                unique_reports.append(item)

        # 取最近 3-5 家机构做聚合
        recent_reports = unique_reports[:5]
        if not recent_reports:
            return {"consensus_status": "data_missing"}

        # ── 平均 EPS ──
        eps_t1_list = [self._num(r.get("epsForecastT1")) for r in recent_reports if self._num(r.get("epsForecastT1"))]
        eps_t2_list = [self._num(r.get("epsForecastT2")) for r in recent_reports if self._num(r.get("epsForecastT2"))]
        eps_t3_list = [self._num(r.get("epsForecastT3")) for r in recent_reports if self._num(r.get("epsForecastT3"))]

        avg_eps_t1 = round(sum(eps_t1_list) / len(eps_t1_list), 4) if eps_t1_list else None
        avg_eps_t2 = round(sum(eps_t2_list) / len(eps_t2_list), 4) if eps_t2_list else None
        avg_eps_t3 = round(sum(eps_t3_list) / len(eps_t3_list), 4) if eps_t3_list else None

        # ── 平均净利 ──
        np_t1_list = [self._num(r.get("netProfitForecastT1")) for r in recent_reports if self._num(r.get("netProfitForecastT1"))]
        np_t2_list = [self._num(r.get("netProfitForecastT2")) for r in recent_reports if self._num(r.get("netProfitForecastT2"))]
        np_t3_list = [self._num(r.get("netProfitForecastT3")) for r in recent_reports if self._num(r.get("netProfitForecastT3"))]

        avg_np_t1 = round(sum(np_t1_list) / len(np_t1_list), 0) if np_t1_list else None
        avg_np_t2 = round(sum(np_t2_list) / len(np_t2_list), 0) if np_t2_list else None
        avg_np_t3 = round(sum(np_t3_list) / len(np_t3_list), 0) if np_t3_list else None

        # ── 平均目标价（优先 targetPriceEx，fallback targetPrice）──
        targets = []
        for r in recent_reports:
            tp = self._num(r.get("targetPriceEx")) or self._num(r.get("targetPrice"))
            if tp:
                targets.append(tp)
        avg_target = round(sum(targets) / len(targets), 2) if targets else None

        # ── 评级分布 ──
        rating_counts: dict[str, int] = {}
        for r in recent_reports:
            rd = r.get("ratingDescription", "未知")
            rating_counts[rd] = rating_counts.get(rd, 0) + 1
        dominant_rating = max(rating_counts, key=rating_counts.get) if rating_counts else "N/A"

        # ── 预测修正趋势（prev vs current）──
        revisions: list[dict] = []
        for r in recent_reports:
            prev_eps_t1 = self._num(r.get("epsForecastT1Prev"))
            curr_eps_t1 = self._num(r.get("epsForecastT1"))
            prev_target = self._num(r.get("targetPriceExPrev")) or self._num(r.get("targetPricePrev"))
            curr_target = self._num(r.get("targetPriceEx")) or self._num(r.get("targetPrice"))
            if prev_eps_t1 and curr_eps_t1:
                rev_pct = (curr_eps_t1 / prev_eps_t1 - 1) * 100
                revisions.append({
                    "institution": r.get("institutionName", ""),
                    "date": r.get("date", ""),
                    "eps_t1_change_pct": round(rev_pct, 1),
                    "target_change": f"{prev_target} → {curr_target}" if prev_target and curr_target else "N/A",
                })

        return {
            "consensus_status": "computed_from_individual_reports",
            "num_analysts": len(recent_reports),
            "num_reports_total": len(items),
            "period": "最近90天",
            "report_institutions": [r.get("institutionName", "") for r in recent_reports],

            # 均值
            "eps_forecast_t1": avg_eps_t1,
            "eps_forecast_t2": avg_eps_t2,
            "eps_forecast_t3": avg_eps_t3,
            "net_profit_forecast_t1": avg_np_t1,
            "net_profit_forecast_t2": avg_np_t2,
            "net_profit_forecast_t3": avg_np_t3,
            "avg_target_price": avg_target,

            # 评级
            "dominant_rating": dominant_rating,
            "rating_distribution": rating_counts,

            # 修正趋势（最重要的增量信息）
            "eps_t1_range": [round(min(eps_t1_list), 2), round(max(eps_t1_list), 2)] if eps_t1_list else [],
            "forecast_revisions": revisions,
            "revision_summary": self._summarize_revisions(revisions),
        }

    @staticmethod
    def _summarize_revisions(revisions: list[dict]) -> str:
        """生成预测修正趋势的文字摘要"""
        if not revisions:
            return "无历史预测数据可比较"
        up_count = sum(1 for r in revisions if r["eps_t1_change_pct"] > 1)
        down_count = sum(1 for r in revisions if r["eps_t1_change_pct"] < -1)
        flat_count = len(revisions) - up_count - down_count
        if down_count > up_count:
            return f"{len(revisions)}家机构中{down_count}家下调预测，分析师群体在削减预期——需关注基本面是否恶化"
        elif up_count > down_count:
            return f"{len(revisions)}家机构中{up_count}家上调预测，分析师群体在调高预期——基本面改善趋势确认"
        else:
            return f"{len(revisions)}家机构预测基本持平，分析师预期稳定"

    # ── 第6层: 产业链利润流 (Industry Chain Profit Flow) ──

    def fetch_chain_industry_info(self, industry_name: str | None = None,
                                   industry_code: str | None = None) -> list[dict]:
        """产业链行业分类信息 — 查询产业链上下游行业代码和分类体系"""
        params: dict = {}
        if industry_name:
            params["industryName"] = industry_name
        if industry_code:
            params["industryCode"] = industry_code
        raw = self._cli("chain/industry-info", method="POST", **params)
        items = self._list(raw)
        return [
            {
                "industry_code": i.get("industryCode", ""),
                "industry_name": i.get("industryName", ""),
                "parent_code": i.get("parentCode", ""),
                "ancestors_codes": i.get("ancestorsCodes", ""),
                "industry_system": i.get("industrySystem", ""),
                "industry_level": self._num(i.get("industryLevel")),
                "full_name": i.get("industryFullname", ""),
            }
            for i in items
        ]

    def fetch_chain_product_relations(self, product_code: str | None = None,
                                       product_name: str | None = None,
                                       page_size: int = 50) -> list[dict]:
        """产业链产品上下游关系 — 查询某产品的上游原材料和下游产品"""
        params: dict = {"pageNum": 1, "pageSize": page_size}
        if product_code:
            params["productCode"] = product_code
        if product_name:
            params["productName"] = product_name
        raw = self._cli("chain/pro-relation", method="POST", **params)
        items = self._list(raw)
        return [
            {
                "product_code": i.get("productCode", ""),
                "product_name": i.get("productName", ""),
                "related_code": i.get("relatedCode", ""),
                "related_name": i.get("relatedName", ""),
                "primary_type": i.get("primaryType", ""),    # M=原材料, P=主体产品, A=设备, T=技术, D=渠道
                "related_type": i.get("relatedType", ""),
                "importance": self._num(i.get("importance")),
                "relationship": self._num(i.get("relationship")),  # 1=下游, -1=上游
            }
            for i in items
        ]

    def fetch_chain_product_industry_map(self, stock_codes: list[str],
                                          begin_date: str | None = None,
                                          end_date: str | None = None) -> list[dict]:
        """公司主营产品及其关联产业图谱 — 查询上市公司产品在产业链中的位置"""
        params: dict = {
            "stockCodes": stock_codes,
            "pageNum": 1,
            "pageSize": 100,
        }
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date
        raw = self._cli("chain/pro-ind-maps", method="POST", **params)
        items = self._list(raw)
        return [
            {
                "stock_code": i.get("stockCode", ""),
                "stock_name": i.get("stockName", ""),
                "publish_date": i.get("publishDate", ""),
                "report_date": i.get("reportDateEnd", ""),
                "product_code": i.get("productCode", ""),
                "product_name": i.get("productName", ""),
                "product_type": i.get("productType", ""),
                "related_code": i.get("relatedCode", ""),
                "related_name": i.get("relatedName", ""),
                "related_type": i.get("relatedType", ""),
                "relationship": i.get("relationship", ""),  # "1"=下游, "-1"=上游
            }
            for i in items
        ]

    # ── 第7层: 模型特定数据 (原第6层) ───────────────────

    def fetch_segment_revenue(self, stock_code: str) -> list[dict]:
        """主营产品/分部收入拆分 — 用于 SOTP 分部估值 (模型J)"""
        raw = self._cli(
            "chain/com-main-pro",
            method="POST",
            stockCodes=[stock_code],
            beginDate=self.default_begin,
            endDate=self.default_end,
            pageNum=1,
            pageSize=20,
        )
        items = self._list(raw)
        return [
            {
                "product_name": i.get("productName", ""),
                "product_income": self._num(i.get("productIncome")),
                "income_ratio_pct": self._pct(i.get("productIncomeRatio")),
                "product_profit": self._num(i.get("productProfit")),
                "profit_ratio_pct": self._pct(i.get("productProfitRatio")),
                "report_date": i.get("reportDateEnd", ""),
            }
            for i in items
        ]

    def fetch_val_indicators(self, stock_code: str, begin_date: str | None = None, end_date: str | None = None) -> list[dict]:
        """历史估值指标序列 — 用于 PB/PE 分位计算 (模型D)和市值历史比较"""
        raw = self._cli(
            "stock/val-indicators",
            method="POST",
            stockCode=stock_code,
            beginDate=begin_date or self.default_begin,
            endDate=end_date or self.default_end,
            pageNum=1,
            pageSize=500,
        )
        items = self._list(raw)
        return [
            {
                "date": i.get("date", ""),
                "market_cap": self._num(i.get("marketCap")),
                "pe": self._num(i.get("pe")),
                "pb": self._num(i.get("pb")),
                "ps": self._num(i.get("ps")),
            }
            for i in items
        ]

    def fetch_dividends(self, stock_code: str) -> list[dict]:
        """分红历史 — 用于计算分红率和可持续ROE (模型D)"""
        raw = self._cli(
            "stock/dividends",
            method="POST",
            stockCode=stock_code,
            beginDate=(datetime.now() - timedelta(days=365 * 5)).strftime("%Y-%m-%d"),
            endDate=self.default_end,
            pageNum=1,
            pageSize=20,
        )
        items = self._list(raw)
        return [
            {
                "fiscal_year": i.get("fiscalYearEnd", ""),
                "cash_div_per_share": self._num(i.get("cashDividendPerShare")),
                "stock_div_ratio": self._num(i.get("stockDividendRatio")),
                "record_date": i.get("recordDate", ""),
                "ex_date": i.get("exDate", ""),
            }
            for i in items
        ]

    def fetch_industry_market_stats(self, industry_code: str) -> dict:
        """行业估值统计 — PE/PB/PS 5年历史百分位 (用于模型B/D/G的行业参照)"""
        raw = self._cli("industry/market-stats", industryCode=industry_code)
        item = self._first(raw)
        return {
            "industry_name": item.get("industryName", ""),
            "pe_5y_pct": self._pct(item.get("pePct5y")),
            "pb_5y_pct": self._pct(item.get("pbPct5y")),
            "ps_5y_pct": self._pct(item.get("psPct5y")),
        }

    def fetch_stock_valuation_rank(self, stock_code: str) -> dict:
        """个股估值诊断 — PE/PS/PB的行业排名和历史排名 (0=最便宜, 100=最贵)
        字段映射依据 investoday API 文档 stock/finance/valuation:
        f2250=PE f2280=PS f2290=PB(标准) f2370=股价/每股有形账面价值(近似PB)
        """
        raw = self._cli("stock/finance/valuation", stockCode=stock_code)
        item = self._first(raw)
        return {
            # PS: f2280 = current PS, f2280Rk = industry rank, f2280RkHist = historical rank
            "ps_current": self._num(item.get("f2280")),
            "ps_industry_rank": self._pct(item.get("f2280Rk")),
            "ps_historical_rank": self._pct(item.get("f2280RkHist")),
            # PE: f2250 = current PE, f2250Rk = industry rank, f2250RkHist = historical rank
            "pe_current": self._num(item.get("f2250")),
            "pe_industry_rank": self._pct(item.get("f2250Rk")),
            "pe_historical_rank": self._pct(item.get("f2250RkHist")),
            # PB: f2290=市净率(标准PB), fallback f2370=股价/每股有形账面价值
            "pb_current": self._num(item.get("f2290") or item.get("f2370")),
            "pb_industry_rank": self._pct(item.get("f2290Rk") or item.get("f2370Rk")),
            "pb_historical_rank": self._pct(item.get("f2290RkHist") or item.get("f2370RkHist")),
        }

    def fetch_income_quarterly(self, stock_code: str, begin_date: str | None = None, end_date: str | None = None) -> list[dict]:
        """单季度利润表序列 — 用于盈利趋势分析和拐点判断 (模型C/I)"""
        raw = self._cli(
            "stock/income-statements-q",
            method="POST",
            stockCode=stock_code,
            beginDate=begin_date or self.default_begin,
            endDate=end_date or self.default_end,
            pageNum=1,
            pageSize=20,
        )
        items = self._list(raw)
        return [
            {
                "report_date": i.get("reportDate", ""),
                "report_type": i.get("reportType", ""),
                "revenue": self._num(i.get("revenue")),
                "operating_profit": self._num(i.get("operatingProfit")),
                "net_profit": self._num(i.get("netProfitParent")),
                "eps": self._num(i.get("eps")),
            }
            for i in items
        ]

    # ── 工具方法 ──────────────────────────────────

    @staticmethod
    def _first(data: Any) -> dict:
        """从 API 响应中取第一条记录"""
        if isinstance(data, list):
            return data[0] if data else {}
        if isinstance(data, dict):
            # 有些接口返回 { "data": [...] }
            if "data" in data and isinstance(data["data"], list):
                return data["data"][0] if data["data"] else {}
            return data
        return {}

    @staticmethod
    def _list(data: Any) -> list:
        """从 API 响应中取列表"""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                return data["data"]
            if "items" in data and isinstance(data["items"], list):
                return data["items"]
        return []

    @staticmethod
    def _num(val: Any) -> float | None:
        """安全转换为 float"""
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _pct(val: Any) -> float | None:
        """
        安全转换为百分比表示（0.15 → 15.0）。
        如果原始值已经 >1（如 15.0 表示 15%），保留不变；
        如果原始值 <1（如 0.15 表示 15%），乘以 100。
        """
        if val is None:
            return None
        try:
            f = float(val)
            return f * 100 if abs(f) < 1 else f
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _rank(val: Any) -> int | None:
        """安全转换为排名（0-100 分位）。

        语义: 0=最高位(从未更贵/更高), 50=中位, 100=最低位(从未更便宜/更低)。
        例: PB分位=0 → PB处于历史最高,从未更贵。
        例: ROIC分位=90 → ROIC处于历史低位,只在10%的时间里更差。
        """
        if val is None:
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None
