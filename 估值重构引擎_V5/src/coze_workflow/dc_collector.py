"""
DC [Code] Tushare Data Collector
Outputs human-readable text for downstream LLM consumption.

P0修复: daily_basic 调前加延迟，防止 Tushare 免费 token 5次/秒限流
"""

import requests_async
import asyncio
import json

TUSHARE_TOKEN = "aab25ecdb29ca0db9964413e9e6cdb29c92d6d15b6a419705889eae9"
TUSHARE_URL = "https://api.tushare.pro"


def to_ts_code(code):
    if code.startswith(("60", "68")):
        return f"{code}.SH"
    elif code.startswith("8"):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


async def call(api_name, params, fields, retries=3):
    for attempt in range(retries):
        try:
            r = await requests_async.post(TUSHARE_URL, json={
                "api_name": api_name,
                "token": TUSHARE_TOKEN,
                "params": params,
                "fields": fields
            }, timeout=15)
            data = r.json()
            code = data.get("code")
            if code == 0:
                flist = data["data"]["fields"]
                items = data["data"]["items"]
                return flist, items
            # 40204 = 限流, 等1秒重试
            if code == 40204 and attempt < retries - 1:
                await asyncio.sleep(1.0)
                continue
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(1.0)
                continue
    return [], []


def getv(row, name, flist):
    if name not in flist:
        return None
    return row[flist.index(name)]


def fval(row, name, flist):
    v = getv(row, name, flist)
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def fmt(v, decimals=2):
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f}"


def fmt_pct(v, decimals=1):
    if v is None:
        return "N/A"
    return f"{round(v, decimals)}%"


def unique_by_date(items, flist):
    seen = set()
    out = []
    for row in items:
        k = str(getv(row, "end_date", flist) or "")
        if k not in seen:
            seen.add(k)
            out.append(row)
    return out


async def main(args: Args) -> Output:
    params = args.params
    name = params.get("verified_name", "")
    code = params.get("verified_code", "")
    ts_code = to_ts_code(code)

    # Basic info
    f_basic, d_basic = await call("stock_basic",
        {"ts_code": ts_code}, "industry,list_date")
    industry = str(getv(d_basic[0], "industry", f_basic) or "N/A") if d_basic else "N/A"
    list_date = str(getv(d_basic[0], "list_date", f_basic) or "N/A") if d_basic else "N/A"

    # Income: 8 periods for YoY matching
    f_inc, d_inc = await call("income",
        {"ts_code": ts_code, "limit": "8"},
        "end_date,total_revenue,total_cogs,operate_profit,n_income,basic_eps")
    d_inc = unique_by_date(d_inc, f_inc) if d_inc else []

    # Balance sheet
    f_bal, d_bal = await call("balancesheet",
        {"ts_code": ts_code, "limit": "4"},
        "end_date,total_assets,inventories,accounts_receiv,acct_payable,fix_assets,goodwill,total_liab,total_hldr_eqy_exc_min_int")
    d_bal = unique_by_date(d_bal, f_bal) if d_bal else []

    # Cashflow
    f_cf, d_cf = await call("cashflow",
        {"ts_code": ts_code, "limit": "4"},
        "end_date,n_cashflow_act,n_cashflow_inv_act,n_cashflow_fin_act")
    d_cf = unique_by_date(d_cf, f_cf) if d_cf else []

    # Financial indicators: 8 periods for YoY
    f_ind, d_ind = await call("fina_indicator",
        {"ts_code": ts_code, "limit": "8"},
        "end_date,grossprofit_margin,netprofit_margin,roe,roa,roe_dt,ocf_to_revenue,q_gr_yoy,q_netprofit_yoy,q_netprofit_qoq,tr_yoy,or_yoy")
    d_ind = unique_by_date(d_ind, f_ind) if d_ind else []

    # Top 10 holders
    f_hold, d_hold = await call("top10_holders",
        {"ts_code": ts_code}, "end_date,holder_name,hold_num_ratio,hold_num")

    # Daily basic
    f_daily, d_daily = await call("daily_basic",
        {"ts_code": ts_code, "limit": "250"},
        "trade_date,close,pe_ttm,pb,total_mv,turnover_rate")

    # Revenue breakdown
    f_mbz, d_mbz = await call("fina_mainbz",
        {"ts_code": ts_code, "type": "P", "limit": "30"},
        "end_date,bz_item,bz_sales,bz_profit,bz_cost")

    # ---- Find true YoY by matching same quarter ----
    def find_yoy(d_list, flist, field, periods=4):
        if len(d_list) < periods + 1:
            return None
        curr_date = str(getv(d_list[0], "end_date", flist) or "")
        curr_v = fval(d_list[0], field, flist)
        for i in range(1, len(d_list)):
            prev_date = str(getv(d_list[i], "end_date", flist) or "")
            if len(curr_date) >= 6 and len(prev_date) >= 6:
                if curr_date[4:8] == prev_date[4:8]:
                    prev_v = fval(d_list[i], field, flist)
                    if curr_v and prev_v and prev_v != 0:
                        return round((curr_v / prev_v - 1) * 100, 1)
        return None

    out = []

    # ========== Basic Info ==========
    out.append(f"## Basic Info")
    out.append(f"- Name: {name}")
    out.append(f"- Code: {code} ({ts_code})")
    out.append(f"- Industry: {industry}")
    out.append(f"- Listed: {list_date}")

    # ========== Income Statement ==========
    if d_inc:
        r = d_inc[0]
        period = str(getv(r, "end_date", f_inc) or "")
        rev = (fval(r, "total_revenue", f_inc) or 0) / 1e8
        np_val = (fval(r, "n_income", f_inc) or 0) / 1e8
        op = (fval(r, "operate_profit", f_inc) or 0) / 1e8
        eps = fval(r, "basic_eps", f_inc)
        rev_yoy = find_yoy(d_inc, f_inc, "total_revenue")
        np_yoy = find_yoy(d_inc, f_inc, "n_income")
        out.append(f"\n## Income Statement ({period})")
        out.append(f"- Revenue: {fmt(rev)} yi (YoY: {fmt_pct(rev_yoy)})")
        out.append(f"- Operating Profit: {fmt(op)} yi")
        out.append(f"- Net Income: {fmt(np_val)} yi (YoY: {fmt_pct(np_yoy)})")
        out.append(f"- EPS: {fmt(eps, 3)}")

    # ========== Balance Sheet ==========
    if d_bal:
        r = d_bal[0]
        period = str(getv(r, "end_date", f_bal) or "")
        ta = (fval(r, "total_assets", f_bal) or 0) / 1e8
        tl = (fval(r, "total_liab", f_bal) or 0) / 1e8
        eq = (fval(r, "total_hldr_eqy_exc_min_int", f_bal) or 0) / 1e8
        inv = (fval(r, "inventories", f_bal) or 0) / 1e8
        ar_val = (fval(r, "accounts_receiv", f_bal) or 0) / 1e8
        ap = (fval(r, "acct_payable", f_bal) or 0) / 1e8
        fa = (fval(r, "fix_assets", f_bal) or 0) / 1e8
        gw = (fval(r, "goodwill", f_bal) or 0) / 1e8
        dr = round(tl / ta * 100, 1) if ta else None
        out.append(f"\n## Balance Sheet ({period})")
        out.append(f"- Total Assets: {fmt(ta)} yi | Debt Ratio: {fmt_pct(dr)}")
        out.append(f"- Inventory: {fmt(inv)} yi | Receivables: {fmt(ar_val)} yi | Payables: {fmt(ap)} yi")
        out.append(f"- Fixed Assets: {fmt(fa)} yi | Goodwill: {fmt(gw)} yi")
        out.append(f"- Equity: {fmt(eq)} yi")

    # ========== Cash Flow ==========
    if d_cf:
        r = d_cf[0]
        period = str(getv(r, "end_date", f_cf) or "")
        ocf = (fval(r, "n_cashflow_act", f_cf) or 0) / 1e8
        icf = (fval(r, "n_cashflow_inv_act", f_cf) or 0) / 1e8
        fcf = (fval(r, "n_cashflow_fin_act", f_cf) or 0) / 1e8
        out.append(f"\n## Cash Flow ({period})")
        out.append(f"- Operating: +{fmt(ocf)} yi")
        out.append(f"- Investing: {fmt(icf)} yi")
        out.append(f"- Financing: {fmt(fcf)} yi")

    # ========== Financial Ratios ==========
    if d_ind:
        r = d_ind[0]
        period = str(getv(r, "end_date", f_ind) or "")
        out.append(f"\n## Financial Ratios ({period})")
        out.append(f"- Gross Margin: {fmt_pct(fval(r, 'grossprofit_margin', f_ind))}")
        out.append(f"- Net Margin: {fmt_pct(fval(r, 'netprofit_margin', f_ind))}")
        out.append(f"- ROE: {fmt_pct(fval(r, 'roe', f_ind))} | ROA: {fmt_pct(fval(r, 'roa', f_ind))}")
        out.append(f"- Current Ratio: {fmt(fval(r, 'current_ratio', f_ind))}")
        out.append(f"- Revenue YoY (q_single): {fmt_pct(fval(r, 'q_gr_yoy', f_ind))}")
        out.append(f"- Net Income YoY (q_single): {fmt_pct(fval(r, 'q_netprofit_yoy', f_ind))}")
        out.append(f"- Net Income QoQ: {fmt_pct(fval(r, 'q_netprofit_qoq', f_ind))}")
        out.append(f"- OCF / Revenue: {fmt_pct(fval(r, 'ocf_to_revenue', f_ind))}")
        if len(d_ind) >= 2:
            out.append(f"\n## Gross Margin Trend")
            for i in range(min(6, len(d_ind))):
                rt = d_ind[i]
                p = str(getv(rt, "end_date", f_ind) or "")
                g = fval(rt, "grossprofit_margin", f_ind)
                q_yoy = fval(rt, "q_gr_yoy", f_ind)
                out.append(f"- {p}: GM={fmt_pct(g)} | Rev_YoY(Q)={fmt_pct(q_yoy)}")

    # ========== Revenue Breakdown ==========
    if d_mbz:
        mbz_periods = {}
        for row in d_mbz:
            dt = str(getv(row, "end_date", f_mbz) or "")
            if dt not in mbz_periods:
                mbz_periods[dt] = []
            mbz_periods[dt].append(row)

        fy_dates = sorted([d for d in mbz_periods if d.endswith("1231")], reverse=True)
        cur_fy = fy_dates[0] if fy_dates else None
        prev_fy = fy_dates[1] if len(fy_dates) > 1 else None

        if cur_fy and cur_fy in mbz_periods:
            cur_rows = mbz_periods[cur_fy]
            cur_total = sum(fval(r, "bz_sales", f_mbz) or 0 for r in cur_rows)

            out.append(f"\n## Revenue Breakdown ({cur_fy})")
            cur_rows.sort(key=lambda r: fval(r, "bz_sales", f_mbz) or 0, reverse=True)

            for r in cur_rows:
                item = str(getv(r, "bz_item", f_mbz) or "N/A")
                sales = (fval(r, "bz_sales", f_mbz) or 0) / 1e8
                profit = (fval(r, "bz_profit", f_mbz) or 0) / 1e8
                ratio = (fval(r, "bz_sales", f_mbz) or 0) / cur_total * 100 if cur_total else 0
                gm = (fval(r, "bz_profit", f_mbz) or 0) / (fval(r, "bz_sales", f_mbz) or 1) * 100

                parts = [f"- {item}: {fmt(sales)} yi ({fmt_pct(ratio)} of revenue)"]
                if gm > 0:
                    parts.append(f", GM={fmt_pct(gm)}")
                if profit:
                    parts.append(f", profit={fmt(profit)} yi")
                out.append("".join(parts))

            if prev_fy and prev_fy in mbz_periods:
                prev_rows = mbz_periods[prev_fy]
                prev_map = {}
                for r in prev_rows:
                    item = str(getv(r, "bz_item", f_mbz) or "")
                    prev_map[item] = fval(r, "bz_sales", f_mbz) or 0

                out.append(f"\n## Revenue YoY ({prev_fy} -> {cur_fy})")
                for r in cur_rows:
                    item = str(getv(r, "bz_item", f_mbz) or "N/A")
                    cur_sales = fval(r, "bz_sales", f_mbz) or 0
                    prev_sales = prev_map.get(item)
                    if prev_sales and prev_sales > 0:
                        chg = (cur_sales / prev_sales - 1) * 100
                        out.append(f"- {item}: {fmt_pct(chg)}")
                    else:
                        out.append(f"- {item}: new segment (no prior data)")

    # ========== Market Data ==========
    if d_daily:
        r = d_daily[0]
        date = str(getv(r, "trade_date", f_daily) or "")
        close = fval(r, "close", f_daily)
        pe_val = fval(r, "pe_ttm", f_daily)
        pb_val = fval(r, "pb", f_daily)
        mv_raw = fval(r, "total_mv", f_daily)
        mv = round(mv_raw / 10000, 2) if mv_raw else None
        tr = fval(r, "turnover_rate", f_daily)
        closes = [fval(d, "close", f_daily) for d in d_daily if fval(d, "close", f_daily)]
        vols = [fval(d, "turnover_rate", f_daily) for d in d_daily if fval(d, "turnover_rate", f_daily)]
        yh = max(closes) if closes else None
        yl = min(closes) if closes else None
        out.append(f"\n## Market Data ({date})")
        out.append(f"- Close: {fmt(close)} | PE: {fmt(pe_val, 1)} | PB: {fmt(pb_val, 1)}")
        out.append(f"- Market Cap: {fmt(mv, 2)} yi")
        out.append(f"- Year High: {fmt(yh)} | Year Low: {fmt(yl)}")
        out.append(f"- Turnover Rate: {fmt_pct(tr)} | 3M Avg Turnover: {fmt_pct(round(sum(vols[-60:]) / min(60, len(vols[-60:])), 2) if vols else None)}")

    # ========== Top 10 Shareholders ==========
    if d_hold:
        out.append(f"\n## Top 10 Shareholders")
        seen_names = set()
        count = 0
        for h in d_hold:
            if count >= 10:
                break
            h_name = str(getv(h, "holder_name", f_hold) or "N/A")
            if h_name in seen_names:
                continue
            seen_names.add(h_name)
            ratio = fval(h, "hold_num_ratio", f_hold)
            out.append(f"- {h_name} | {fmt_pct(ratio, 2)}")
            count += 1

    ret: Output = {
        "data_pack": "\n".join(out)
    }
    return ret
