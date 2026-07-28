"""N0.5: 公司前置认知 — 为探针设计提供基本判断

四个数据源:
  1. 火山搜索: 公司叙事认知（做什么/怎么赚钱/最近变化/市场看法）
  2. Tushare daily_basic: 最新市值/PE/PB/换手率
  3. Tushare fina_mainbz: 主营构成（分产品收入/毛利率）
  4. investoday operating-reviews: 最新经营评述原文

输出: 一段结构化的公司基本认知文本，作为探针设计的上下文
"""

import json
import re
import subprocess
import sys
import requests
from pathlib import Path

from .config import VOLC_AGENT_KEY, VOLC_URL, VOLC_BOT_ID, TUSHARE_TOKEN
from .field_runner import volc_search, CURRENT_DATE


# ══════════════════════════════════════════════════════
# Tushare 主营构成
# ══════════════════════════════════════════════════════

TUSHARE_URL = "https://api.tushare.pro"


def to_ts_code(code: str) -> str:
    if code.startswith(("60", "68")):
        return f"{code}.SH"
    elif code.startswith("8"):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


def fetch_tushare_segment(stock_code: str) -> str:
    """获取分产品/分业务的主营构成数据。"""
    ts_code = to_ts_code(stock_code)
    try:
        r = requests.post(TUSHARE_URL, json={
            "api_name": "fina_mainbz",
            "token": TUSHARE_TOKEN,
            "params": {"ts_code": ts_code, "type": "P", "limit": "30"},
            "fields": "end_date,bz_item,bz_sales,bz_profit,bz_cost",
        }, timeout=15)
        data = r.json()
        if data.get("code") != 0 or not data.get("data", {}).get("items"):
            return ""

        fields = data["data"]["fields"]
        items = data["data"]["items"]

        # 按报告期分组
        periods = {}
        for row in items:
            dt = str(row[fields.index("end_date")] if "end_date" in fields else "")
            if dt not in periods:
                periods[dt] = []
            periods[dt].append(row)

        fy_dates = sorted([d for d in periods if d.endswith("1231")], reverse=True)
        if not fy_dates:
            return ""

        cur_fy = fy_dates[0]
        cur_rows = periods[cur_fy]
        cur_total = sum(
            float(row[fields.index("bz_sales")] or 0)
            for row in cur_rows if "bz_sales" in fields
        )

        lines = [f"### 主营构成 ({cur_fy})"]
        cur_rows.sort(key=lambda r: float(r[fields.index("bz_sales")] or 0), reverse=True)

        for row in cur_rows[:10]:
            item = str(row[fields.index("bz_item")] if "bz_item" in fields else "?")
            sales = float(row[fields.index("bz_sales")] or 0) / 1e8
            cost = float(row[fields.index("bz_cost")] or 0) / 1e8 if "bz_cost" in fields else 0
            ratio = float(row[fields.index("bz_sales")] or 0) / cur_total * 100 if cur_total else 0
            # 用 bz_sales - bz_cost 计算毛利率（bz_profit 经常为空）
            gm = (sales - cost) / sales * 100 if sales > 0 and cost > 0 else None

            parts = [f"- {item}: {sales:.2f}亿 ({ratio:.1f}%)"]
            if gm is not None:
                parts.append(f" 毛利率{gm:.1f}%")
            lines.append("".join(parts))

        return "\n".join(lines)

    except Exception as e:
        return f"[Tushare segment 异常: {e}]"


def fetch_tushare_daily(stock_code: str) -> str:
    """获取最新市值/PE/PB/换手率等市场数据。"""
    ts_code = to_ts_code(stock_code)
    try:
        r = requests.post(TUSHARE_URL, json={
            "api_name": "daily_basic",
            "token": TUSHARE_TOKEN,
            "params": {"ts_code": ts_code, "limit": "1"},
            "fields": "trade_date,close,pe_ttm,pb,total_mv,turnover_rate",
        }, timeout=15)
        data = r.json()
        if data.get("code") != 0 or not data.get("data", {}).get("items"):
            return ""

        fields = data["data"]["fields"]
        row = data["data"]["items"][0]

        def gv(name):
            return row[fields.index(name)] if name in fields else None

        close = gv("close")
        pe = gv("pe_ttm")
        pb = gv("pb")
        mv_raw = gv("total_mv")
        mv = round(float(mv_raw) / 10000, 0) if mv_raw else None
        tr = gv("turnover_rate")
        date = str(gv("trade_date") or "")

        lines = [f"### 市场数据 ({date})"]
        lines.append(f"- 收盘价: {close}")
        lines.append(f"- 市值: {mv:.0f}亿")
        lines.append(f"- PE(TTM): {pe}")
        lines.append(f"- PB: {pb}")
        lines.append(f"- 换手率: {tr}%")

        return "\n".join(lines)

    except Exception as e:
        return f"[Tushare daily 异常: {e}]"


def fetch_tushare_financial_baseline(stock_code: str) -> str:
    """获取财务基线：盈利指标 + 费用结构 + 资产负债 + 现金流。"""
    ts_code = to_ts_code(stock_code)
    sections = []

    def _dedup(items, fields):
        seen = set()
        out = []
        for row in items:
            period = str(row[fields.index("end_date")] if "end_date" in fields else "?")
            if period not in seen:
                seen.add(period)
                out.append(row)
        return out

    def _gv(row, fields, name, scale=1):
        v = row[fields.index(name)] if name in fields else None
        try:
            return float(v) / scale if v is not None else None
        except (ValueError, TypeError):
            return None

    def _pct(v):
        return f"{v:.1f}%" if v is not None else "N/A"

    def _yi(v):
        return f"{v:.2f}亿" if v is not None else "N/A"

    # ── 1. 盈利指标（近4期）──
    try:
        r = requests.post(TUSHARE_URL, json={
            "api_name": "fina_indicator",
            "token": TUSHARE_TOKEN,
            "params": {"ts_code": ts_code, "limit": "4"},
            "fields": "end_date,roe,roa,grossprofit_margin,netprofit_margin",
        }, timeout=15)
        data = r.json()
        if data.get("code") == 0 and data.get("data", {}).get("items"):
            fields = data["data"]["fields"]
            items = _dedup(data["data"]["items"], fields)
            lines = ["### 盈利指标趋势"]
            lines.append("| 报告期 | ROE | ROA | 毛利率 | 净利率 |")
            lines.append("|--------|-----|-----|--------|--------|")
            for row in items:
                period = str(row[fields.index("end_date")] if "end_date" in fields else "?")
                lines.append(f"| {period} | {_pct(_gv(row, fields, 'roe'))} | {_pct(_gv(row, fields, 'roa'))} | {_pct(_gv(row, fields, 'grossprofit_margin'))} | {_pct(_gv(row, fields, 'netprofit_margin'))} |")
            sections.append("\n".join(lines))
    except Exception:
        pass

    # ── 2. 利润表核心数据（近4期）──
    try:
        r = requests.post(TUSHARE_URL, json={
            "api_name": "income",
            "token": TUSHARE_TOKEN,
            "params": {"ts_code": ts_code, "limit": "4"},
            "fields": "end_date,total_revenue,operate_profit,n_income,total_cogs,rd_exp,sell_exp,admin_exp,fin_exp",
        }, timeout=15)
        data = r.json()
        if data.get("code") == 0 and data.get("data", {}).get("items"):
            fields = data["data"]["fields"]
            items = _dedup(data["data"]["items"], fields)
            lines = ["### 利润表核心数据"]
            lines.append("| 报告期 | 营收 | 营业利润 | 净利润 | 研发费用 | 研发占比 |")
            lines.append("|--------|------|----------|--------|----------|----------|")
            for row in items:
                period = str(row[fields.index("end_date")] if "end_date" in fields else "?")
                rev = _gv(row, fields, 'total_revenue', 1e8)
                op = _gv(row, fields, 'operate_profit', 1e8)
                ni = _gv(row, fields, 'n_income', 1e8)
                rd = _gv(row, fields, 'rd_exp', 1e8)
                rd_pct = (rd / rev * 100) if rev and rd else None
                lines.append(f"| {period} | {_yi(rev)} | {_yi(op)} | {_yi(ni)} | {_yi(rd)} | {_pct(rd_pct)} |")
            sections.append("\n".join(lines))
    except Exception:
        pass

    # ── 3. 资产负债核心数据（最新期）──
    try:
        r = requests.post(TUSHARE_URL, json={
            "api_name": "balancesheet",
            "token": TUSHARE_TOKEN,
            "params": {"ts_code": ts_code, "limit": "1"},
            "fields": "end_date,total_assets,total_liab,total_hldr_eqy_exc_min_int,inventories,accounts_receiv,acct_payable,money_cap,goodwill",
        }, timeout=15)
        data = r.json()
        if data.get("code") == 0 and data.get("data", {}).get("items"):
            fields = data["data"]["fields"]
            row = data["data"]["items"][0]
            period = str(row[fields.index("end_date")] if "end_date" in fields else "?")
            ta = _gv(row, fields, 'total_assets', 1e8)
            tl = _gv(row, fields, 'total_liab', 1e8)
            eq = _gv(row, fields, 'total_hldr_eqy_exc_min_int', 1e8)
            inv = _gv(row, fields, 'inventories', 1e8)
            ar = _gv(row, fields, 'accounts_receiv', 1e8)
            ap = _gv(row, fields, 'acct_payable', 1e8)
            cash = _gv(row, fields, 'money_cap', 1e8)
            gw = _gv(row, fields, 'goodwill', 1e8)
            dr = (tl / ta * 100) if ta and tl else None
            lines = [f"### 资产负债 ({period})"]
            lines.append(f"- 总资产: {_yi(ta)} | 净资产: {_yi(eq)} | 资产负债率: {_pct(dr)}")
            lines.append(f"- 货币资金: {_yi(cash)} | 存货: {_yi(inv)} | 应收: {_yi(ar)} | 应付: {_yi(ap)}")
            if gw and gw > 0:
                lines.append(f"- 商誉: {_yi(gw)}")
            sections.append("\n".join(lines))
    except Exception:
        pass

    # ── 4. 现金流（近2期）──
    try:
        r = requests.post(TUSHARE_URL, json={
            "api_name": "cashflow",
            "token": TUSHARE_TOKEN,
            "params": {"ts_code": ts_code, "limit": "2"},
            "fields": "end_date,n_cashflow_act,c_pay_acq_const_fiolta,n_cashflow_inv_act,n_cashflow_fin_act",
        }, timeout=15)
        data = r.json()
        if data.get("code") == 0 and data.get("data", {}).get("items"):
            fields = data["data"]["fields"]
            items = _dedup(data["data"]["items"], fields)
            lines = ["### 现金流"]
            for row in items:
                period = str(row[fields.index("end_date")] if "end_date" in fields else "?")
                ocf = _gv(row, fields, 'n_cashflow_act', 1e8)
                capex = _gv(row, fields, 'c_pay_acq_const_fiolta', 1e8)
                icf = _gv(row, fields, 'n_cashflow_inv_act', 1e8)
                fcf_fin = _gv(row, fields, 'n_cashflow_fin_act', 1e8)
                fcf = (ocf - capex) if ocf is not None and capex is not None else None
                lines.append(f"- {period}: OCF {_yi(ocf)} | CAPEX {_yi(capex)} | FCF {_yi(fcf)} | 投资CF {_yi(icf)} | 筹资CF {_yi(fcf_fin)}")
            sections.append("\n".join(lines))
    except Exception:
        pass

    return "\n\n".join(sections)


# ══════════════════════════════════════════════════════
# investoday 经营评述
# ══════════════════════════════════════════════════════

def fetch_operating_review(stock_code: str) -> str:
    """获取最新一期年报/半年报的经营评述原文。"""
    try:
        # 用 investoday CLI
        result = subprocess.run(
            ["npx", "investoday-api", "stock/operating-reviews",
             f"stockCode={stock_code}", "pageNum=1", "pageSize=1"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return ""

        data = json.loads(result.stdout)
        items = data if isinstance(data, list) else data.get("data", {}).get("items", [])
        if not items:
            return ""

        item = items[0] if isinstance(items, list) else items
        review = item.get("operationalReview", "")
        period = item.get("reportPeriodEnd", "")

        if not review:
            return ""

        # 完整返回，不截断
        return f"### 经营评述 ({period})\n{review}"

    except FileNotFoundError:
        return "[investoday CLI 未安装]"
    except Exception as e:
        return f"[经营评述异常: {e}]"


# ══════════════════════════════════════════════════════
# 火山公司认知搜索
# ══════════════════════════════════════════════════════

COMPANY_PROFILE_PROMPT = """[当前日期: {current_date}] 查询{stock_name}当季的董事会综述、经营分析、相关资讯研报等，构建投资地图。
覆盖以下内容:

- 这家公司到底是做什么的——核心产品/技术/服务，不是百度百科那种介绍，而是它实际靠什么赚钱
- 最近1-2年最重要的变化或事件——业绩拐点、产品突破、管理层变动、行业转折
- 市场对它的主流看法——看好的人在讲什么故事，看空的人在担心什么
- 关键的不确定性和争议点——哪些问题当前没有被充分回答

写短。信息不充分的地方如实说。不要编造。所有数据以最新可得日期为准。"""


def fetch_company_profile(stock_name: str, stock_code: str) -> str:
    """用火山搜索获取公司基本认知。"""
    query = COMPANY_PROFILE_PROMPT.replace("{stock_name}", stock_name).replace("{current_date}", CURRENT_DATE)
    result = volc_search(query)
    if result.startswith("[火山]"):
        return ""
    return result


# ══════════════════════════════════════════════════════
# 主函数
# ══════════════════════════════════════════════════════

def build_company_profile(
    stock_name: str,
    stock_code: str,
    verbose: bool = True,
) -> str:
    """构建公司前置认知。

    Returns:
        结构化的公司基本认知文本（Markdown）
    """
    if verbose:
        print(f"\n[N0.5] 构建公司前置认知: {stock_name}({stock_code})")

    sections = []

    # 1. 火山公司认知
    if verbose:
        print(f"  [N0.5] 火山搜索中...")
    profile = fetch_company_profile(stock_name, stock_code)
    if profile:
        sections.append(f"### 公司认知（火山搜索）\n{profile}")
        if verbose:
            print(f"  [N0.5] 火山: {len(profile)}c")

    # 2. Tushare 市场数据
    if verbose:
        print(f"  [N0.5] Tushare 市场数据...")
    daily = fetch_tushare_daily(stock_code)
    if daily:
        sections.append(daily)
        if verbose:
            print(f"  [N0.5] 市场数据: {len(daily)}c")

    # 3. Tushare 财务基线
    if verbose:
        print(f"  [N0.5] Tushare 财务基线...")
    baseline = fetch_tushare_financial_baseline(stock_code)
    if baseline:
        sections.append(baseline)
        if verbose:
            print(f"  [N0.5] 财务基线: {len(baseline)}c")

    # 4. Tushare 主营构成
    if verbose:
        print(f"  [N0.5] Tushare 主营构成...")
    segment = fetch_tushare_segment(stock_code)
    if segment:
        sections.append(segment)
        if verbose:
            print(f"  [N0.5] Tushare: {len(segment)}c")

    # 5. 经营评述
    if verbose:
        print(f"  [N0.5] 经营评述...")
    review = fetch_operating_review(stock_code)
    if review:
        sections.append(review)
        if verbose:
            print(f"  [N0.5] 经营评述: {len(review)}c")

    result = "\n\n".join(sections)
    if verbose:
        print(f"  [N0.5] 完成: {len(result)}c")

    return result
