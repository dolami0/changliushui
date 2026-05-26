"""
Tushare Pro API 薄封装层 — V5 估值管线

职责: token管理、代码转换、频率控制、季度数据拉取。
所有货币值统一转亿(yi)。失败返回 None，不抛异常。
"""

import time
from typing import Any

import pandas as pd
import tushare as ts

from env_config import TUSHARE_TOKEN


class TushareFetcher:
    """Tushare API 封装。Token 缺失时 available=False，所有方法返回 None。"""

    def __init__(self):
        self.token = TUSHARE_TOKEN
        self.available = bool(self.token)
        self._pro = None
        self._last_call = 0.0
        self._min_interval = 0.3

    @property
    def pro(self):
        if self._pro is None and self.available:
            ts.set_token(self.token)
            self._pro = ts.pro_api()
        return self._pro

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.time()

    # ── 代码转换 ──

    _TS_CODE_CACHE: dict[str, str] = {}

    @classmethod
    def to_ts_code(cls, stock_code: str) -> str:
        """investoday 6位代码 → Tushare ts_code (000001.SZ / 600519.SH)"""
        if stock_code in cls._TS_CODE_CACHE:
            return cls._TS_CODE_CACHE[stock_code]
        if stock_code.startswith(('60', '68')):
            code = stock_code + '.SH'
        elif stock_code.startswith('8'):
            code = stock_code + '.BJ'
        else:
            code = stock_code + '.SZ'
        cls._TS_CODE_CACHE[stock_code] = code
        return code

    # ── 内部工具 ──

    @staticmethod
    def _yi(val) -> float | None:
        """原始元 → 亿，保留2位小数。"""
        try:
            v = float(val)
            return round(v / 1e8, 2)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _f(val) -> float | None:
        """安全转 float。"""
        try:
            v = float(val)
            return round(v, 4) if v == v else None
        except (TypeError, ValueError):
            return None

    def _safe_call(self, fn, **kwargs) -> Any:
        """带频率控制的安全调用。失败返回 None。"""
        if not self.available or self.pro is None:
            return None
        try:
            self._rate_limit()
            result = fn(**kwargs)
            if result is None or (hasattr(result, 'empty') and result.empty):
                return None
            return result
        except Exception:
            return None

    # ── 公开 API ──

    def fetch_daily(self, stock_code: str, limit: int = 1) -> dict | None:
        """最新日线行情: close, pe_ttm, pb, total_mv"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.daily, ts_code=tsc, limit=limit)
        if df is None or len(df) == 0:
            return None
        r = df.iloc[0]
        return {
            'close': self._f(r.get('close')),
            'pe_ttm': self._f(r.get('pe_ttm')),
            'pb': self._f(r.get('pb')),
            'total_mv': self._f(r.get('total_mv')),
        }

    def fetch_daily_basic(self, stock_code: str, limit: int = 1) -> dict | None:
        """每日指标: pe_ttm, pb, ps_ttm, total_mv"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.daily_basic, ts_code=tsc, limit=limit)
        if df is None or len(df) == 0:
            return None
        r = df.iloc[0]
        return {
            'pe_ttm': self._f(r.get('pe_ttm')),
            'pb': self._f(r.get('pb')),
            'ps_ttm': self._f(r.get('ps_ttm')),
            'total_mv': self._f(r.get('total_mv')),
            'pe_ttm_nonrecurring': self._f(r.get('pe_ttm_nonrecurring')),
        }

    def fetch_balance_sheet_quarterly(self, stock_code: str, periods: int = 8) -> dict | None:
        """季度资产负债表: 最近 N 期。含 adv_receipts(预收), cip(在建工程) 等前瞻字段。"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.balancesheet, ts_code=tsc, limit=periods)
        if df is None or len(df) == 0:
            return None
        # Tushare 可能返回同一 end_date 的重复行（同一报告期的冗余记录），去重
        df = df.drop_duplicates(subset=['end_date'], keep='first')
        periods_list = []
        for _, r in df.iterrows():
            # cip: 在建工程。新财报用 cip_total, 旧财报用 cip, 优先非空值
            cip_val = r.get('cip_total') if pd.notna(r.get('cip_total')) else r.get('cip')
            # contract_liab: 新收入准则下的合同负债，优先于旧科目 adv_receipts
            contract_liab_val = r.get('contract_liab') if pd.notna(r.get('contract_liab')) else r.get('adv_receipts')
            periods_list.append({
                'end_date': str(r.get('end_date', '')),
                'total_assets': self._yi(r.get('total_assets')),
                'total_equity': self._yi(r.get('total_hldr_eqy_exc_min_int')),
                'total_liabilities': self._yi(r.get('total_liab')),
                'accounts_receiv': self._yi(r.get('accounts_receiv')),
                'prepayments': self._yi(r.get('prepayment')),
                'inventories': self._yi(r.get('inventories')),
                'adv_receipts': self._yi(contract_liab_val),
                'contract_liab': self._yi(r.get('contract_liab')),
                'cip': self._yi(cip_val),
                'fix_assets': self._yi(r.get('fix_assets')),
                'intan_assets': self._yi(r.get('intan_assets')),
                'goodwill': self._yi(r.get('goodwill')),
                'st_borrow': self._yi(r.get('st_borrow')),
                'lt_borrow': self._yi(r.get('lt_borrow')),
                'notes_payable': self._yi(r.get('notes_payable')),
                'acct_payable': self._yi(r.get('acct_payable')),
            })
        return {
            'ts_code': tsc,
            'periods': periods_list,
            'count': len(periods_list),
        }

    def fetch_income_quarterly(self, stock_code: str, periods: int = 8) -> dict | None:
        """季度利润表: 最近 N 期。"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.income, ts_code=tsc, limit=periods)
        if df is None or len(df) == 0:
            return None
        df = df.drop_duplicates(subset=['end_date'], keep='first')
        periods_list = []
        for _, r in df.iterrows():
            periods_list.append({
                'end_date': str(r.get('end_date', '')),
                'revenue': self._yi(r.get('revenue')),
                'operate_profit': self._yi(r.get('operate_profit')),
                'n_income': self._yi(r.get('n_income')),
                'total_profit': self._yi(r.get('total_profit')),
                'income_tax': self._yi(r.get('income_tax')),
                'selling_expense': self._yi(r.get('sell_exp')),
                'admin_expense': self._yi(r.get('admin_exp')),
                'finance_expense': self._yi(r.get('fin_exp')),
                'rd_expense': self._yi(r.get('rd_exp')),
            })
        return {
            'ts_code': tsc,
            'periods': periods_list,
            'count': len(periods_list),
        }

    def fetch_cashflow_quarterly(self, stock_code: str, periods: int = 8) -> dict | None:
        """季度现金流量表: 最近 N 期。"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.cashflow, ts_code=tsc, limit=periods)
        if df is None or len(df) == 0:
            return None
        df = df.drop_duplicates(subset=['end_date'], keep='first')
        periods_list = []
        for _, r in df.iterrows():
            periods_list.append({
                'end_date': str(r.get('end_date', '')),
                'n_cashflow_act': self._yi(r.get('n_cashflow_act')),
                'c_pay_acq_const_fiolta': self._yi(r.get('c_pay_acq_const_fiolta')),
                'free_cashflow': self._yi(r.get('free_cashflow')),
                'c_fr_borrow': self._yi(r.get('c_fr_borrow')),
                'c_fr_issue_share': self._yi(r.get('c_fr_issue_share')),
            })
        return {
            'ts_code': tsc,
            'periods': periods_list,
            'count': len(periods_list),
        }

    def fetch_fina_indicator(self, stock_code: str, periods: int = 8) -> dict | None:
        """财务指标趋势: ROIC/毛利率/净利率 + 预计算好的单季度同比/环比增速。"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.fina_indicator, ts_code=tsc, limit=periods, period='')
        if df is None or len(df) == 0:
            return None
        # 最新一期静态指标
        r = df.iloc[0]
        # 趋势序列（最近 periods 期，按 end_date 降序）
        trend_fields = [
            'end_date', 'roe', 'roic', 'grossprofit_margin', 'netprofit_margin',
            'tr_yoy', 'or_yoy',                          # 营业总收入/营业收入 同比
            'q_sales_yoy', 'q_sales_qoq',                # 营业收入 单季度同比/环比
            'q_op_yoy', 'q_op_qoq',                      # 营业利润 单季度同比/环比
            'q_profit_yoy', 'q_profit_qoq',              # 净利润 单季度同比/环比
            'q_netprofit_yoy', 'q_netprofit_qoq',        # 归母净利润 单季度同比/环比
        ]
        trends = []
        for _, row in df.iterrows():
            period_data = {}
            for f in trend_fields:
                v = row.get(f)
                period_data[f] = self._f(v) if v is not None and v == v else None
            trends.append(period_data)
        return {
            'end_date': str(r.get('end_date', '')),
            'roic': self._f(r.get('roic')),
            'gross_margin': self._f(r.get('grossprofit_margin')),
            'net_margin': self._f(r.get('netprofit_margin')),
            'roe': self._f(r.get('roe')),
            'roa': self._f(r.get('roa')),
            'debt_to_assets': self._f(r.get('debt_to_assets')),
            'current_ratio': self._f(r.get('current_ratio')),
            'quick_ratio': self._f(r.get('quick_ratio')),
            'assets_turn': self._f(r.get('assets_turn')),
            'ebit_margin': self._f(r.get('ebit_margin')),
            'ebitda_debt': self._f(r.get('ebitda_interest_debt')),
            'ocfps': self._f(r.get('ocfps')),
            'eps': self._f(r.get('eps')),
            'bps': self._f(r.get('bps')),
            'trends': trends,
        }

    def fetch_stock_basic(self, stock_code: str) -> dict | None:
        """股票基本信息: 行业、上市日期等。"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.stock_basic, ts_code=tsc, fields='industry,list_date,fullname')
        if df is None or len(df) == 0:
            return None
        r = df.iloc[0]
        return {
            'industry': str(r.get('industry', '')),
            'list_date': str(r.get('list_date', '')),
            'fullname': str(r.get('fullname', '')),
        }

    def fetch_forecast(self, stock_code: str) -> dict | None:
        """最新业绩预告。"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.forecast, ts_code=tsc, limit=2)
        if df is None or len(df) == 0:
            return None
        r = df.iloc[0]
        return {
            'ann_date': str(r.get('ann_date', '')),
            'end_date': str(r.get('end_date', '')),
            'type': str(r.get('type', '')),
            'p_change_min': self._f(r.get('p_change_min')),
            'p_change_max': self._f(r.get('p_change_max')),
            'net_profit_min': self._yi(r.get('net_profit_min')),
            'net_profit_max': self._yi(r.get('net_profit_max')),
            'change_reason': str(r.get('change_reason_expl', '') or r.get('change_reason', '')),
        }

    def fetch_express(self, stock_code: str) -> dict | None:
        """最新业绩快报。"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.express, ts_code=tsc, limit=2)
        if df is None or len(df) == 0:
            return None
        r = df.iloc[0]
        return {
            'ann_date': str(r.get('ann_date', '')),
            'revenue': self._yi(r.get('revenue')),
            'operate_profit': self._yi(r.get('operate_profit')),
            'net_profit': self._yi(r.get('n_income')),
            'total_assets': self._yi(r.get('total_assets')),
            'diluted_eps': self._f(r.get('diluted_eps')),
            'yoy_sales': self._f(r.get('yoy_sales')),
            'yoy_dedu_np': self._f(r.get('yoy_dedu_np')),
            'perf_summary': str(r.get('perf_summary', '')),
        }

    def fetch_shareholder_count(self, stock_code: str, periods: int = 4) -> dict | None:
        """股东人数趋势。"""
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.stk_holdernumber, ts_code=tsc, limit=periods)
        if df is None or len(df) == 0:
            return None
        items = []
        for _, r in df.iterrows():
            items.append({
                'end_date': str(r.get('end_date', '')),
                'holder_num': int(r.get('holder_num', 0)),
            })
        return {'ts_code': tsc, 'items': items, 'count': len(items)}

    def fetch_fina_mainbz(self, stock_code: str, periods: int = 2) -> list[dict] | None:
        """主营产品构成 — 年报 + 对应半年报。

        返回 periods 组年报 + periods 组半年报（合计 2×periods 期）。
        年报用于 YoY 基准对比；半年报用于拆出 H2 实际业绩（年报 − 半年报）。
        """
        tsc = self.to_ts_code(stock_code)
        df = self._safe_call(self.pro.fina_mainbz, ts_code=tsc, type='P', limit=20)
        if df is None or len(df) == 0:
            return None

        all_dates = df['end_date'].drop_duplicates().sort_values(ascending=False)
        annual = [d for d in all_dates if str(d).endswith('1231')]
        semi = [d for d in all_dates if not str(d).endswith('1231')]

        # 年报和半年报各取 periods 期，按日期降序合并
        selected = sorted(annual[:periods] + semi[:periods], reverse=True)

        items = []
        for _, r in df.iterrows():
            ed = str(r.get('end_date', ''))
            if ed not in selected:
                continue
            items.append({
                'end_date': ed,
                'item': str(r.get('bz_item', '')),
                'sales': self._yi(r.get('bz_sales')),
                'profit': self._yi(r.get('bz_profit')),
                'cost': self._yi(r.get('bz_cost')),
            })
        return items
