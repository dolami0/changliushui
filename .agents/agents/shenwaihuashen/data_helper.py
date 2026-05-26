#!/usr/bin/env python
"""身外化身 · 数据助手
优先 tushare，失败降级 investoday。
用法: python data_helper.py <action> <stock_code> [args...]
"""

import sys, json, os, warnings
warnings.filterwarnings("ignore")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_ts_pro():
    """获取 tushare pro 实例"""
    cfg = load_config()
    token = cfg["dataSources"]["tushare"]["token"]
    import tushare as ts
    ts.set_token(token)
    return ts.pro_api()

# ─── 基础信息 ─────────────────────────────────────────

def basic_info(code):
    """公司基本信息 + 上市日期 + 行业"""
    pro = get_ts_pro()
    # 自动补全后缀
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    df = pro.stock_basic(ts_code=code, fields="ts_code,name,industry,area,list_date")
    return df.to_dict("records") if not df.empty else []

def daily(code, start=None, end=None):
    """日线行情"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    df = pro.daily(ts_code=code, start_date=start, end_date=end,
                   fields="ts_code,trade_date,open,high,low,close,vol,amount,pct_chg")
    return df.to_dict("records") if not df.empty else []

def daily_basic(code, start=None, end=None):
    """日线基础指标: PE/PB/总市值/流通市值/换手率"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    df = pro.daily_basic(ts_code=code, start_date=start, end_date=end,
                         fields="ts_code,trade_date,close,pe,pb,total_mv,circ_mv,turnover_rate,turnover_rate_f")
    return df.to_dict("records") if not df.empty else []

# ─── 财务报表 ─────────────────────────────────────────

def income(code, period=None, limit=4):
    """利润表: 营收/营业成本/净利润/毛利率等"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    kwargs = {"ts_code": code, "limit": limit}
    if period: kwargs["end_date"] = period
    df = pro.income(ts_code=code, limit=limit,
                    fields="ts_code,end_date,revenue,oper_cost,manage_exp,total_profit,n_income,basic_eps")
    return df.to_dict("records") if not df.empty else []

def balance_sheet(code, limit=4):
    """资产负债表: 总资产/净资产/负债等"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    df = pro.balancesheet(ts_code=code, limit=limit,
                          fields="ts_code,end_date,total_assets,total_liab,total_hldr_eqy_exc_min_int")
    return df.to_dict("records") if not df.empty else []

def cashflow(code, limit=4):
    """现金流表"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    df = pro.cashflow(ts_code=code, limit=limit,
                      fields="ts_code,end_date,n_cashflow_act")
    return df.to_dict("records") if not df.empty else []

def fina_indicator(code, limit=4):
    """财务指标: ROE/ROA/毛利率/净利率/资产负债率等"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    df = pro.fina_indicator(ts_code=code, limit=limit,
                            fields="ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets,current_ratio,quick_ratio,ocf_to_revenue")
    return df.to_dict("records") if not df.empty else []

# ─── 股东与质押 ───────────────────────────────────────

def top10_holders(code):
    """前十大股东"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    df = pro.top10_holders(ts_code=code,
                           fields="ts_code,holder_name,hold_amount,hold_ratio")
    return df.to_dict("records") if not df.empty else []

def pledge_info(code):
    """股权质押统计"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    df = pro.pledge_stat(ts_code=code,
                         fields="ts_code,pledge_total_ratio,pledge_num")
    return df.to_dict("records") if not df.empty else []

# ─── 分产品/分业务 ────────────────────────────────────

def segment(code, period=None):
    """分产品/分业务收入、利润、毛利率。
    用于拆解新业务vs传统业务，验证事件驱动下的产品纯度。
    period: 财报期，默认最新两期年报做同比
    自动标记异常毛利率（>90%或bz_cost=0）"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    if not period:
        periods = ["20251231", "20241231"]
    else:
        periods = [period]

    results = []
    anomalies = []
    for p in periods:
        df = pro.fina_mainbz(ts_code=code, period=p,
                             fields="ts_code,end_date,bz_item,bz_sales,bz_profit,bz_cost")
        if df is not None and not df.empty:
            for _, r in df.iterrows():
                sales = r.get("bz_sales", 0) or 0
                profit = r.get("bz_profit", 0) or 0
                cost = r.get("bz_cost", 0) or 0
                gm = (profit / sales * 100) if sales and sales > 0 else 0
                item_name = str(r.get("bz_item", ""))

                # 异常检测
                flags = []
                if gm > 90:
                    flags.append(f"ANOMALY:GM={gm:.1f}%>90%")
                if cost == 0 or (sales > 1e6 and cost < sales * 0.01):
                    flags.append(f"ANOMALY:bz_cost near zero (cost={cost:.0f})")
                if flags:
                    anomalies.append({"period": p, "item": item_name, "flags": flags})

                results.append({
                    "period": p,
                    "item": item_name,
                    "sales_yuan": float(sales),
                    "sales_yi": round(float(sales) / 1e8, 4),
                    "gross_profit_yuan": float(profit),
                    "gross_profit_yi": round(float(profit) / 1e8, 4),
                    "cost_yuan": float(cost),
                    "gross_margin_pct": round(gm, 2),
                    "flags": flags
                })
    if anomalies:
        results.append({"__ANOMALIES_DETECTED__": anomalies,
                        "__ACTION__": "交叉验证: investoday + WebSearch 年报附注"})
    return results

# ─── 估值相关 ─────────────────────────────────────────

def valuation_snapshot(code):
    """估值快照: PE/PB/PS/市值 + 行业均值对比"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
        elif code.startswith("8") or code.startswith("4"): code += ".BJ"
    # 最新估值
    df_basic = pro.daily_basic(ts_code=code,
                                fields="ts_code,trade_date,pe,pb,total_mv,circ_mv")
    # 最新财务指标
    df_fina = pro.fina_indicator(ts_code=code, limit=1,
                                  fields="ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets")
    result = {
        "valuation": df_basic.to_dict("records")[0] if not df_basic.empty else {},
        "fundamentals": df_fina.to_dict("records")[0] if not df_fina.empty else {}
    }
    return result

def margin_detail(code, start=None, end=None):
    """融资融券明细"""
    pro = get_ts_pro()
    if "." not in code:
        if code.startswith("6"):   code += ".SH"
        elif code.startswith("0") or code.startswith("3"): code += ".SZ"
    kwargs = {"ts_code": code, "limit": 30}
    if start: kwargs["start_date"] = start
    if end:   kwargs["end_date"] = end
    df = pro.margin_detail(**kwargs,
                           fields="ts_code,trade_date,rzye,rqye,rzmre,rqyl")
    return df.to_dict("records") if not df.empty else []

# ─── CLI 入口 ─────────────────────────────────────────

ACTIONS = {
    "basic":        basic_info,
    "daily":        daily,
    "daily_basic":  daily_basic,
    "income":       income,
    "balance":      balance_sheet,
    "cashflow":     cashflow,
    "fina":         fina_indicator,
    "top10":        top10_holders,
    "pledge":       pledge_info,
    "segment":    segment,
    "valuation":    valuation_snapshot,
    "margin":       margin_detail,
}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "用法: python data_helper.py <action> <stock_code> [arg1] [arg2]",
                          "actions": list(ACTIONS.keys())}, ensure_ascii=False, indent=2))
        sys.exit(1)

    action = sys.argv[1]
    code   = sys.argv[2]
    args   = sys.argv[3:]

    if action not in ACTIONS:
        print(json.dumps({"error": f"未知操作: {action}", "actions": list(ACTIONS.keys())}, ensure_ascii=False))
        sys.exit(1)

    try:
        if action in ["daily", "daily_basic"] and len(args) >= 1:
            start, end = args[0], (args[1] if len(args) > 1 else None)
            result = ACTIONS[action](code, start, end)
        elif action in ["income"] and len(args) >= 1:
            result = ACTIONS[action](code, args[0])
        elif action in ["margin"] and len(args) >= 1:
            start, end = args[0], (args[1] if len(args) > 1 else None)
            result = ACTIONS[action](code, start, end)
        else:
            result = ACTIONS[action](code)

        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e), "action": action, "code": code}, ensure_ascii=False))
        sys.exit(1)
