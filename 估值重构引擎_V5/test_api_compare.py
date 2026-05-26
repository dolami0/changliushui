"""investoday vs Tushare API 数据对比测试"""
import os, sys, traceback
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent / 'src'))
from data_fetcher import DataFetcher
import tushare as ts
import pandas as pd

TOKEN = os.environ.get("TUSHARE_TOKEN", "")
ts.set_token(TOKEN)
pro = ts.pro_api()
fetcher = DataFetcher()

def ts_code(s):
    return s + '.SZ' if s.startswith(('00','30')) else s + '.SH'

def safe_tushare(fn, **kw):
    try:
        df = fn(**kw)
        return df if df is not None and len(df) > 0 else None
    except Exception as e:
        return f'ERR:{str(e)[:80]}'

def fval(df, col, idx=0):
    try:
        v = float(df.iloc[idx][col])
        return round(v, 4) if pd.notna(v) else None
    except:
        return None

def try_section(label, fn):
    try:
        fn()
    except Exception as e:
        print(f'  [{label}] 错误: {str(e)[:150]}')
        traceback.print_exc()

for stock, name in [('002428','云南锗业'), ('600188','兖矿能源'), ('300726','宏达电子')]:
    tsc = ts_code(stock)
    print(f'\n{"="*70}')
    print(f'### {stock} {name} ###')
    print(f'{"="*70}')

    # --- 行情 ---
    def test_quote():
        iq = fetcher.fetch_realtime_quote(stock)
        td = safe_tushare(pro.daily, ts_code=tsc, limit=1)
        tdb = safe_tushare(pro.daily_basic, ts_code=tsc, limit=1)
        ip = iq.get('current_price')
        imc = (iq.get('market_cap') or 0) / 1e8
        tc = fval(td, 'close') if isinstance(td, pd.DataFrame) else None
        tpe = fval(tdb, 'pe_ttm') if isinstance(tdb, pd.DataFrame) else None
        tpb = fval(tdb, 'pb') if isinstance(tdb, pd.DataFrame) else None
        print(f'  行情:  inv price={ip} mcap={imc:.1f}亿')
        print(f'         tush close={tc} pe={tpe} pb={tpb}')
        if ip and tc:
            d = abs(ip-tc)/ip*100
            print(f'         >> 价差={d:.2f}% {"OK" if d<0.5 else "!!"}')
    try_section('行情', test_quote)

    # --- 估值 ---
    def test_val():
        iv = fetcher.fetch_valuation(stock)
        tdb = safe_tushare(pro.daily_basic, ts_code=tsc, limit=1)
        ipe, ipb, ips = iv.get('pe_ttm'), iv.get('pb'), iv.get('ps_ttm')
        tpe = fval(tdb, 'pe_ttm') if isinstance(tdb, pd.DataFrame) else None
        tpb = fval(tdb, 'pb') if isinstance(tdb, pd.DataFrame) else None
        print(f'  估值:  inv PE={ipe} PB={ipb} PS={ips}')
        print(f'         tush PE={tpe} PB={tpb}')
        if ipe and tpe:
            dpe = abs(ipe-tpe)/max(abs(ipe),1)*100
            dpb = abs(ipb-tpb)/max(abs(ipb),1)*100 if ipb and tpb else 0
            print(f'         >> PE差={dpe:.2f}% {"OK" if dpe<2 else "!!"} | PB差={dpb:.2f}% {"OK" if dpb<2 else "!!"}')
    try_section('估值', test_val)

    # --- 利润表 TTM (investoday) vs 年报 (Tushare) ---
    def test_income():
        io = fetcher.fetch_income_ttm(stock)
        # Tushare: try latest annual period (20251231), then fall back to sum of last 4 quarters
        ti_annual = safe_tushare(pro.income, ts_code=tsc, period='20251231', limit=1)
        ti_4q = safe_tushare(pro.income, ts_code=tsc, limit=4)
        i_rev = (io.get('revenue_ttm') or 0)
        i_np = (io.get('net_profit_ttm') or 0)
        i_op = (io.get('operating_profit') or 0)
        print(f'  利润:  inv TTM rev={i_rev/1e8:.2f}亿 op={i_op/1e8:.2f}亿 np={i_np/1e8:.2f}亿')
        if isinstance(ti_annual, pd.DataFrame) and len(ti_annual) > 0:
            ta = ti_annual.iloc[0]
            t_rev = float(ta['revenue'])
            t_np = float(ta['n_income'])
            rd = abs(i_rev - t_rev) / max(abs(i_rev), 1) * 100
            print(f'         tush FY24 rev={t_rev/1e8:.2f}亿 np={t_np/1e8:.2f}亿 (年报, 差={rd:.2f}%)')
        if isinstance(ti_4q, pd.DataFrame) and len(ti_4q) > 0:
            t_rev4 = float(ti_4q['revenue'].astype(float).sum())
            t_np4 = float(ti_4q['n_income'].astype(float).sum())
            rd4 = abs(i_rev - t_rev4) / max(abs(i_rev), 1) * 100
            print(f'         tush 4Q sum rev={t_rev4/1e8:.2f}亿 np={t_np4/1e8:.2f}亿 (4季合计, 差={rd4:.2f}%)')
            periods = ti_4q['end_date'].tolist()
            print(f'         可用期间: {periods}')
    try_section('利润表', test_income)

    # --- 资产负债表 ---
    def test_bs():
        bo = fetcher.fetch_balance_ttm(stock)
        tb = safe_tushare(pro.balancesheet, ts_code=tsc, period='20251231', limit=1)
        if isinstance(tb, pd.DataFrame) and len(tb) > 0:
            tr = tb.iloc[0]
            pairs = [
                ('总资产', 'total_assets', 'total_assets'),
                ('净资产', 'total_equity', 'total_hldr_eqy_exc_min_int'),
                ('应收款', 'accounts_receivable', 'accounts_receiv'),
                ('存货', 'inventory', 'inventories'),
                ('预收款', None, 'adv_receipts'),
                ('在建工程', None, 'cip'),
            ]
            print(f'  负债表:')
            for label, ik, tk in pairs:
                iv = ((bo.get(ik) or 0) / 1e8) if ik else None
                tv = fval(tb, tk)
                tv_yi = tv / 1e8 if tv else None
                if iv and tv_yi:
                    d = abs(iv-tv_yi)/max(abs(iv),0.01)*100
                    print(f'    {label}: inv={iv:.2f}亿 tush={tv_yi:.2f}亿 差={d:.2f}%')
                elif iv:
                    print(f'    {label}: inv={iv:.2f}亿 tush=N/A')
                elif tv_yi:
                    print(f'    {label}: inv=N/A       tush={tv_yi:.2f}亿 [Tushare独有]')
        else:
            print(f'  负债表: Tushare无数据')
    try_section('负债表', test_bs)

    # --- 现金流 ---
    def test_cf():
        co = fetcher.fetch_cashflow_ttm(stock)
        tc_annual = safe_tushare(pro.cashflow, ts_code=tsc, period='20251231', limit=1)
        tc_4q = safe_tushare(pro.cashflow, ts_code=tsc, limit=4)
        i_ocf = (co.get('operating_cash_flow') or 0) / 1e8
        i_cpx = (co.get('capex_payments') or 0) / 1e8
        print(f'  现金流:inv TTM ocf={i_ocf:.2f}亿 capex={i_cpx:.2f}亿 fcf={i_ocf-i_cpx:.2f}亿')
        if isinstance(tc_annual, pd.DataFrame) and len(tc_annual) > 0:
            ta = tc_annual.iloc[0]
            ta_ocf = float(ta['n_cashflow_act'])/1e8
            ta_cpx = float(ta['c_pay_acq_const_fiolta'])/1e8
            print(f'         tush FY24 ocf={ta_ocf:.2f}亿 capex={ta_cpx:.2f}亿 fcf={ta_ocf-ta_cpx:.2f}亿')
        if isinstance(tc_4q, pd.DataFrame) and len(tc_4q) > 0:
            t_ocf4 = float(tc_4q['n_cashflow_act'].astype(float).sum())/1e8
            t_cpx4 = float(tc_4q['c_pay_acq_const_fiolta'].astype(float).sum())/1e8
            print(f'         tush 4Q  ocf={t_ocf4:.2f}亿 capex={t_cpx4:.2f}亿 fcf={t_ocf4-t_cpx4:.2f}亿')
    try_section('现金流', test_cf)

    # --- 财务衍生指标 ---
    def test_finder():
        fd = fetcher.fetch_fin_der_inds(stock)
        tf = safe_tushare(pro.fina_indicator, ts_code=tsc, period='20251231', limit=1)
        i_roic = fd.get('roic', 0) or 0
        i_gm = fd.get('gross_margin', 0) or 0
        i_nm = fd.get('net_margin', 0) or 0
        i_ebitda = (fd.get('ebitda', 0) or 0) / 1e8
        i_debt = (fd.get('interest_bearing_debt', 0) or 0) / 1e8
        print(f'  衍生:  inv roic={i_roic:.2f}% gm={i_gm:.2f}% nm={i_nm:.2f}% ebitda={i_ebitda:.2f}亿 debt={i_debt:.2f}亿')
        if isinstance(tf, pd.DataFrame) and len(tf) > 0:
            t_roic = fval(tf, 'roic')
            t_gm = fval(tf, 'grossprofit_margin')
            t_nm = fval(tf, 'netprofit_margin')
            t_roe = fval(tf, 'roe')
            t_debt = fval(tf, 'debt_to_assets')
            print(f'         tush roic={t_roic}% gm={t_gm}% nm={t_nm}% roe={t_roe}% debt_ratio={t_debt}%')
    try_section('衍生指标', test_finder)

    # --- 分析师一致预期 ---
    def test_cons():
        ac = fetcher.fetch_analyst_consensus(stock)
        trc = safe_tushare(pro.report_rc, ts_code=tsc, start_date='20260401', end_date='20260522', limit=20)
        if ac.get('consensus_status') != 'data_missing':
            ac_eps = ac.get('avg_eps_t1', '?')
            ac_np = (ac.get('avg_np_t1', 0) or 0) / 1e8
            print(f'  预期:  inv eps_t1={ac_eps} np_t1={ac_np:.2f}亿 n={ac.get("report_count","?")}')
        else:
            print(f'  预期:  inv 最近90天无数据')
        if isinstance(trc, pd.DataFrame) and len(trc) > 0:
            eps_vals = trc['eps'].dropna().astype(float)
            # Get unique orgs
            orgs = trc['org_name'].nunique() if 'org_name' in trc.columns else len(trc)
            print(f'         tush report_rc: {len(trc)}行({orgs}机构) eps均值={float(eps_vals.mean()):.4f}')
        else:
            print(f'         tush report_rc: 无数据(权限不足或无覆盖)')
    try_section('预期', test_cons)

    # --- 分部收入 ---
    def test_seg():
        seg = fetcher.fetch_segment_revenue(stock)
        tm = safe_tushare(pro.fina_mainbz, ts_code=tsc, type='P', period='20231231', limit=10)
        print(f'  分部:  inv {len(seg)}条')
        for s in seg[:2]:
            si = (s.get('product_income') or 0) / 1e8
            sr = s.get('income_ratio_pct', 0) or 0
            print(f'         - {str(s.get("product_name","?"))[:30]}: {si:.2f}亿 ({sr:.1f}%)')
        if isinstance(tm, pd.DataFrame) and len(tm) > 0:
            print(f'         tush fina_mainbz: {len(tm)}项')
            for _, r in tm.head(2).iterrows():
                print(f'         - {str(r["bz_item"])[:35]}: {float(r["bz_sales"])/1e8:.2f}亿')
        else:
            print(f'         tush fina_mainbz: 无数据(权限或数据空白)')
    try_section('分部', test_seg)

print('\n' + '='*70)
print('对比测试完成')
print('='*70)
