"""API 数据全链路验证脚本
覆盖：A. Tushare端点 B. investoday端点 C. 交叉验证 D. 数据传递 E. 前瞻信号
"""
import sys, json, math
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent / 'src'))

from data_fetcher import DataFetcher
from tushare_fetcher import TushareFetcher
from agent1_data_forge import DataForge, _extract_core_fields, _fetch_core_bundle

fetcher = DataFetcher()
tf = TushareFetcher()

STOCKS = [
    ("002428", "云南锗业"),
    ("300726", "宏达电子"),
    ("600188", "兖矿能源"),
]

print("=" * 80)
print("PART A: Tushare API 逐端点验证")
print("=" * 80)

for stock, name in STOCKS:
    print(f"\n{'─'*60}")
    print(f"  {stock} {name}")
    print(f"{'─'*60}")

    # A1: daily
    d = tf.fetch_daily(stock, 1)
    print(f"  [daily] close={d.get('close')} total_mv(万元)={d.get('total_mv')} pe_ttm={d.get('pe_ttm')}")

    # A2: daily_basic
    db = tf.fetch_daily_basic(stock, 1)
    print(f"  [daily_basic] pe_ttm={db.get('pe_ttm')} pb={db.get('pb')} ps_ttm={db.get('ps_ttm')} total_mv(万元)={db.get('total_mv')}")

    # A3: balance sheet quarterly
    bs = tf.fetch_balance_sheet_quarterly(stock, 8)
    if bs.get('periods'):
        n = len(bs['periods'])
        # 检查重复 end_date
        from collections import Counter
        eds = [p.get('end_date','') for p in bs['periods']]
        dup_counts = Counter(eds)
        dup_dates = [d for d, c in dup_counts.items() if c > 1]
        p0 = bs['periods'][0]
        print(f"  [bs_q] {n}期, 重复日期:{dup_dates if dup_dates else '无'}")
        print(f"        最新期 end_date={p0.get('end_date')} report_type={p0.get('report_type')} comp_type={p0.get('comp_type')}")
        print(f"        cip={p0.get('cip')} cip_total={p0.get('cip_total')} contract_liab={p0.get('contract_liab')} adv_receipts={p0.get('adv_receipts')}")
    else:
        print(f"  [bs_q] 无数据")

    # A4: income quarterly
    inc = tf.fetch_income_quarterly(stock, 8)
    if inc.get('periods'):
        p0 = inc['periods'][0]
        print(f"  [income_q] {len(inc['periods'])}期")
        print(f"        最新期 end_date={p0.get('end_date')} report_type={p0.get('report_type')}")
        print(f"        revenue={p0.get('revenue')} operate_profit={p0.get('operate_profit')} n_income={p0.get('n_income')}")

    # A5: cashflow quarterly
    cf = tf.fetch_cashflow_quarterly(stock, 8)
    if cf.get('periods'):
        p0 = cf['periods'][0]
        print(f"  [cf_q] {len(cf['periods'])}期")
        print(f"        n_cashflow_act={p0.get('n_cashflow_act')} c_pay_acq={p0.get('c_pay_acq_const_fiolta')}")

    # A6: fina_indicator
    fi = tf.fetch_fina_indicator(stock)
    if fi:
        print(f"  [fina_ind] end_date={fi.get('end_date')}")
        print(f"        roic={fi.get('roic')} grossprofit_margin={fi.get('grossprofit_margin')} netprofit_margin={fi.get('netprofit_margin')}")
        print(f"        roe={fi.get('roe')} eps={fi.get('eps')}")
    else:
        print(f"  [fina_ind] 无数据")

    # A7: fina_mainbz
    mb = tf.fetch_fina_mainbz(stock)
    if mb:
        by_date = {}
        for m in mb:
            ed = m.get('end_date','')
            by_date.setdefault(ed, []).append(m)
        dates_sorted = sorted(by_date.keys(), reverse=True)
        print(f"  [fina_mainbz] {len(mb)}项, {len(by_date)}个不同报告期: {dates_sorted}")
        if dates_sorted:
            for ed in dates_sorted[:2]:
                items = by_date[ed]
                print(f"    {ed}: {len(items)}产品")
                for it in items[:3]:
                    print(f"      - {str(it.get('bz_item','?'))[:30]} sales={it.get('bz_sales')} profit={it.get('bz_profit')} cost={it.get('bz_cost')}")
    else:
        print(f"  [fina_mainbz] 无数据")

    # A8: forecast
    fc = tf.fetch_forecast(stock)
    if fc:
        print(f"  [forecast] type={fc.get('type')} p_change_min={fc.get('p_change_min')} p_change_max={fc.get('p_change_max')}")
    else:
        print(f"  [forecast] 无数据")

    # A9: express
    ex = tf.fetch_express(stock)
    if ex:
        print(f"  [express] yoy_sales={ex.get('yoy_sales')} yoy_dedu_np={ex.get('yoy_dedu_np')} perf_summary={ex.get('perf_summary','')[:50]}")
    else:
        print(f"  [express] 无数据")

    # A10: shareholder
    sh = tf.fetch_shareholder_count(stock, 4)
    if sh.get('items'):
        nums = [it.get('holder_num') for it in sh['items'][:4]]
        print(f"  [shareholder] {len(sh['items'])}期 holder_nums={nums}")
    else:
        print(f"  [shareholder] 无数据")


print("\n" + "=" * 80)
print("PART B: investoday API 逐端点验证")
print("=" * 80)

for stock, name in STOCKS:
    print(f"\n{'─'*60}")
    print(f"  {stock} {name}")
    print(f"{'─'*60}")

    # B1: quote
    q = fetcher.fetch_realtime_quote(stock)
    print(f"  [quote] current_price={q.get('current_price')} market_cap(元)={q.get('market_cap')} stock_name={q.get('stock_name','')[:10]}")

    # B2: valuation
    v = fetcher.fetch_valuation(stock)
    print(f"  [valuation] PE={v.get('pe_ttm')} PS={v.get('ps_ttm')} PB={v.get('pb')}")
    print(f"        pe_rank={v.get('pe_ttm_historical_rank')} pb_rank={v.get('pb_historical_rank')}")

    # B3: income TTM
    inc = fetcher.fetch_income_ttm(stock)
    rev = (inc.get('revenue_ttm') or 0) / 1e8
    np = (inc.get('net_profit_ttm') or 0) / 1e8
    op = (inc.get('operating_profit') or 0) / 1e8
    eps = inc.get('eps')
    print(f"  [income_ttm] rev={rev:.2f}亿 op={op:.2f}亿 np={np:.2f}亿 eps={eps} report_date={inc.get('report_date','?')}")

    # B4: balance TTM
    bal = fetcher.fetch_balance_ttm(stock)
    ta = (bal.get('total_assets') or 0) / 1e8
    te = (bal.get('total_equity') or 0) / 1e8
    cash = (bal.get('cash_equivalents') or 0) / 1e8
    print(f"  [balance_ttm] total_assets={ta:.2f}亿 equity={te:.2f}亿 cash={cash:.2f}亿")

    # B5: cashflow TTM
    cf = fetcher.fetch_cashflow_ttm(stock)
    ocf = (cf.get('operating_cash_flow') or 0) / 1e8
    capex = (cf.get('capex_payments') or 0) / 1e8
    print(f"  [cashflow_ttm] ocf={ocf:.2f}亿 capex={capex:.2f}亿 fcf={ocf-capex:.2f}亿")

    # B6: fin_der_inds — 看原始值
    fd = fetcher.fetch_fin_der_inds(stock)
    print(f"  [fin_der] RAW roic={fd.get('roic')} gross_margin={fd.get('gross_margin')} net_margin={fd.get('net_margin')}")
    print(f"        ebitda={fd.get('ebitda')} interest_bearing_debt={fd.get('interest_bearing_debt')}")
    # 注意：data_fetcher 内部可能已做了 ×100 处理！

    # B7: profit_ability
    pa = fetcher.fetch_profit_ability(stock)
    print(f"  [profit_ability] gm_rank={pa.get('gross_margin_historical_rank')} roic_rank={pa.get('roic_historical_rank')}")
    print(f"        composite={pa.get('profitability_composite_score')} gm_pct={pa.get('gross_margin_pct')}")

    # B8: industries
    ind = fetcher.fetch_industries(stock)
    print(f"  [industries] sw_l1={ind.get('sw_l1_name','?')} sw_l2={ind.get('sw_l2_name','?')}")

    # B9: dupont
    dup = fetcher.fetch_dupont(stock)
    print(f"  [dupont] roe={dup.get('roe')}")

    # B10: segment_revenue
    seg = fetcher.fetch_segment_revenue(stock)
    if seg:
        print(f"  [segment] {len(seg)}条")
        for s in seg[:3]:
            pi = (s.get('product_income') or 0) / 1e8
            pr = s.get('profit_ratio_pct', 0) or 0
            print(f"      - {str(s.get('product_name','?'))[:30]}: {pi:.2f}亿 ({pr:.1f}%)")
    else:
        print(f"  [segment] 无数据")

    # B11: consensus
    ac = fetcher.fetch_analyst_consensus(stock)
    print(f"  [consensus] status={ac.get('consensus_status','?')} count={ac.get('report_count','?')}")
    if ac.get('consensus_status') != 'data_missing':
        print(f"        avg_eps_t1={ac.get('avg_eps_t1')} avg_np_t1={(ac.get('avg_np_t1') or 0)/1e8:.2f}亿")
    else:
        print(f"        最近90天无一致预期数据")


print("\n" + "=" * 80)
print("PART C: 交叉验证 — 重叠字段一致性")
print("=" * 80)

for stock, name in STOCKS:
    print(f"\n{'─'*60}")
    print(f"  {stock} {name}")
    print(f"{'─'*60}")

    # Tushare
    d = tf.fetch_daily(stock, 1)
    db = tf.fetch_daily_basic(stock, 1)
    fi = tf.fetch_fina_indicator(stock)

    # investoday
    q = fetcher.fetch_realtime_quote(stock)
    v = fetcher.fetch_valuation(stock)
    fd = fetcher.fetch_fin_der_inds(stock)
    dup = fetcher.fetch_dupont(stock)
    inc = fetcher.fetch_income_ttm(stock)

    checks = []

    # C1: PE
    t_pe = db.get('pe_ttm') or d.get('pe_ttm')
    i_pe = v.get('pe_ttm')
    if t_pe and i_pe:
        diff = abs(t_pe - i_pe) / max(abs(i_pe), 1) * 100
        checks.append(('PE', t_pe, i_pe, diff, 5))

    # C2: PB
    t_pb = db.get('pb') or d.get('pb')
    i_pb = v.get('pb')
    if t_pb and i_pb:
        diff = abs(t_pb - i_pb) / max(abs(i_pb), 0.01) * 100
        checks.append(('PB', t_pb, i_pb, diff, 5))

    # C3: PS
    t_ps = db.get('ps_ttm')
    i_ps = v.get('ps_ttm')
    if t_ps and i_ps:
        diff = abs(t_ps - i_ps) / max(abs(i_ps), 0.01) * 100
        checks.append(('PS', t_ps, i_ps, diff, 10))

    # C4: 总市值
    t_mcap_raw = db.get('total_mv') or d.get('total_mv')
    if t_mcap_raw:
        t_mcap = t_mcap_raw / 1e4  # 万元→亿
    else:
        t_mcap = None
    i_mcap = (q.get('market_cap') or 0) / 1e8  # 元→亿
    if t_mcap and i_mcap > 0.1:
        diff = abs(t_mcap - i_mcap) / max(abs(i_mcap), 0.01) * 100
        checks.append(('总市值(亿)', t_mcap, i_mcap, diff, 5))

    # C5: ROIC
    t_roic = fi.get('roic') if fi else None
    i_roic = fd.get('roic')
    # investoday ROIC 可能在 data_fetcher 中已经 ×100
    if t_roic and i_roic:
        # 尝试匹配：如果 i_roic < 1，说明没有×100
        i_roic_adj = i_roic if i_roic > 1 else i_roic * 100
        diff1 = abs(t_roic - i_roic) / max(abs(i_roic), 0.01) * 100
        diff2 = abs(t_roic - i_roic_adj) / max(abs(i_roic_adj), 0.01) * 100
        use_adj = diff2 < diff1
        diff = min(diff1, diff2)
        checks.append(('ROIC(%)', t_roic, i_roic_adj if use_adj else i_roic, diff, 30))
        if use_adj:
            print(f"  [INFO] investoday ROIC={i_roic}需要×100才与Tushare={t_roic}匹配")

    # C6: 毛利率
    t_gm = fi.get('grossprofit_margin') if fi else None
    i_gm = fd.get('gross_margin')
    if t_gm and i_gm:
        i_gm_adj = i_gm if i_gm > 1 else i_gm * 100
        diff1 = abs(t_gm - i_gm) / max(abs(i_gm), 0.01) * 100
        diff2 = abs(t_gm - i_gm_adj) / max(abs(i_gm_adj), 0.01) * 100
        use_adj = diff2 < diff1
        diff = min(diff1, diff2)
        checks.append(('毛利率(%)', t_gm, i_gm_adj if use_adj else i_gm, diff, 10))
        if use_adj:
            print(f"  [INFO] investoday 毛利率={i_gm}需要×100")

    # C7: 净利率
    t_nm = fi.get('netprofit_margin') if fi else None
    i_nm = fd.get('net_margin')
    if t_nm and i_nm:
        i_nm_adj = i_nm if i_nm > 1 else i_nm * 100
        diff1 = abs(t_nm - i_nm) / max(abs(i_nm), 0.01) * 100
        diff2 = abs(t_nm - i_nm_adj) / max(abs(i_nm_adj), 0.01) * 100
        diff = min(diff1, diff2)
        checks.append(('净利率(%)', t_nm, i_nm_adj if (diff2<diff1) else i_nm, diff, 10))

    # C8: ROE
    t_roe = fi.get('roe') if fi else None
    i_roe = dup.get('roe')
    if t_roe and i_roe:
        diff = abs(t_roe - i_roe) / max(abs(i_roe), 0.01) * 100
        checks.append(('ROE(%)', t_roe, i_roe, diff, 10))

    # C9: EPS
    t_eps = fi.get('eps') if fi else None
    i_eps = inc.get('eps')
    if t_eps and i_eps:
        diff = abs(t_eps - i_eps) / max(abs(i_eps), 0.01) * 100
        checks.append(('EPS', t_eps, i_eps, diff, 10))

    for label, tv, iv, diff, threshold in checks:
        status = 'PASS' if diff <= threshold else ('WARN' if diff <= threshold * 2 else 'FAIL')
        print(f"  [{status}] {label}: Tushare={tv:.3f} investoday={iv:.3f} 偏差={diff:.2f}% (阈值{threshold}%)")


print("\n" + "=" * 80)
print("PART D: 数据传递验证 (_extract_core_fields)")
print("=" * 80)

for stock, name in STOCKS:
    print(f"\n{'─'*60}")
    print(f"  {stock} {name}")
    print(f"{'─'*60}")

    bundle = _fetch_core_bundle(fetcher, stock)
    fields = _extract_core_fields(bundle, stock)

    # D1: 来源标记
    print(f"  current_price={fields.get('current_price')} source={fields.get('current_price_source')}")
    print(f"  market_cap={fields.get('market_cap_yi')}亿 source={fields.get('market_cap_source')}")

    # D2: 估值指标
    print(f"  PE={fields.get('pe_ttm')} PB={fields.get('pb')} PS={fields.get('ps_ttm')}")

    # D3: 利润相关
    print(f"  rev={fields.get('revenue_ttm_yi')}亿 op={fields.get('operating_profit_ttm_yi')}亿 np={fields.get('net_profit_ttm_yi')}亿")
    print(f"  ebitda={fields.get('ebitda_ttm_yi')}亿 (D=A估算)")

    # D4: 资产负债
    print(f"  total_assets={fields.get('total_assets_yi')}亿 equity={fields.get('total_equity_yi')}亿")
    print(f"  invested_capital={fields.get('invested_capital_yi')}亿")
    print(f"  interest_bearing_debt={fields.get('interest_bearing_debt_yi')}亿 net_debt={fields.get('net_debt_yi')}亿")
    print(f"  ocf_ttm={fields.get('ocf_ttm_yi')}亿 capex={fields.get('capex_ttm_yi')}亿")

    # D5: 比率
    print(f"  roic={fields.get('roic_pct')}% (计算:NOPAT/IC)")
    print(f"  gross_margin={fields.get('gross_margin_pct')}% net_margin={fields.get('net_margin_pct')}%")
    print(f"  effective_tax_rate={fields.get('effective_tax_rate')}")

    # D6: 历史排名
    print(f"  gm_rank={fields.get('gross_margin_historical_rank')} roic_rank={fields.get('roic_historical_rank')}")
    print(f"  profitability_composite={fields.get('profitability_composite_score')}")

    # D7: 行业
    print(f"  industry={fields.get('industry_sw_l1')} / {fields.get('industry_sw_l2')}")

    # D8: 前瞻信号
    fw = fields.get('_forward_looking', {})
    print(f"  forward: status={fw.get('status')} sources_avail={fw.get('sources_available')}")
    print(f"        sources_missing={fw.get('sources_missing')}")
    if fw.get('text_summary'):
        print(f"        text_summary={fw.get('text_summary')[:150]}")

    # D9: 前向信号详情
    cats = fw.get('categories', {})
    for cat_name in ['demand_reality', 'supply_readiness', 'earnings_elasticity', 'cashflow_quality', 'management_guidance']:
        cat = cats.get(cat_name, {})
        if cat.get('_note'):
            print(f"        [{cat_name}] {cat['_note']}")
        elif cat_name == 'earnings_elasticity':
            products = cat.get('products', {})
            if products.get('_note'):
                print(f"        [{cat_name}] {products['_note']}")
            else:
                mix = products.get('product_mix', [])
                print(f"        [{cat_name}] {len(mix)}产品, vintage={products.get('data_vintage','?')}")
                for p in mix[:5]:
                    print(f"          {p['name'][:20]}: rev={p['revenue']} share={p['revenue_share_pct']}% gm={p['gross_margin_pct']}% yoy={p.get('revenue_yoy_pct','?')}")
        elif cat_name == 'demand_reality':
            cl = cat.get('contract_liab', {})
            if cl:
                print(f"        [{cat_name}] 合同负债={cl.get('value')} QoQ={cl.get('qoq_pct')}% anomaly={cl.get('anomaly',{}).get('level')}")


print("\n" + "=" * 80)
print("PART E: 特定字段深度检查")
print("=" * 80)

# E1: ebitda 原始值 vs 年化值
print("\n[E1] EBITDA: fin_der_inds 原始值 vs _extract_core_fields 年化")
for stock, name in STOCKS:
    fd = fetcher.fetch_fin_der_inds(stock)
    bundle = _fetch_core_bundle(fetcher, stock)
    fields = _extract_core_fields(bundle, stock)
    raw_ebitda = fd.get('ebitda') or 0
    raw_ebitda_yi = raw_ebitda / 1e8
    computed_ebitda = fields.get('ebitda_ttm_yi', 0)
    # 看是否做了 ×4
    would_be_annual = raw_ebitda_yi * 4
    print(f"  {name}: raw={raw_ebitda} (={raw_ebitda_yi:.3f}亿) → ×4={would_be_annual:.3f}亿 | computed={computed_ebitda:.3f}亿 | matches ×4={abs(would_be_annual-computed_ebitda)<0.05}")

# E2: investoday ROIC 是否需要 ×100
print("\n[E2] investoday ROIC/毛利率 ×100 逻辑")
for stock, name in STOCKS:
    fd = fetcher.fetch_fin_der_inds(stock)
    raw_roic = fd.get('roic', 0) or 0
    raw_gm = fd.get('gross_margin', 0) or 0
    raw_nm = fd.get('net_margin', 0) or 0
    bundle = _fetch_core_bundle(fetcher, stock)
    fields = _extract_core_fields(bundle, stock)
    computed_roic = fields.get('roic_pct', 0)
    computed_gm = fields.get('gross_margin_pct', 0)
    computed_nm = fields.get('net_margin_pct', 0)

    # investoday 内部处理逻辑：roic < 10 时 ×100
    print(f"  {name}:")
    print(f"    ROIC: raw={raw_roic:.4f} → core={computed_roic:.2f}% (core是自己算NOPAT/IC)")
    print(f"    GM: raw={raw_gm:.4f} → core_gm={computed_gm:.2f}%")
    print(f"    NM: raw={raw_nm:.4f} → core_nm={computed_nm:.2f}%")
    # 如果 raw_gm < 1，说明 API 返回的是小数需要 ×100
    if raw_gm and raw_gm < 1:
        print(f"      ⚠ investoday 毛利率原始值={raw_gm}(<1)→需要×100后={raw_gm*100:.1f}%")
    if raw_nm and raw_nm < 1:
        print(f"      ⚠ investoday 净利率原始值={raw_nm}(<1)→需要×100后={raw_nm*100:.1f}%")

# E3: 市值单位转换验证
print("\n[E3] 市值单位转换验证")
for stock, name in STOCKS:
    q = fetcher.fetch_realtime_quote(stock)
    d = tf.fetch_daily(stock, 1)
    db = tf.fetch_daily_basic(stock, 1)
    bundle = _fetch_core_bundle(fetcher, stock)
    fields = _extract_core_fields(bundle, stock)

    i_mcap_raw = q.get('market_cap', 0) or 0  # investoday: 元
    ts_mcap_raw = db.get('total_mv') or d.get('total_mv')  # Tushare: 万元

    i_mcap_yi = i_mcap_raw / 1e8 if i_mcap_raw else 0
    ts_mcap_yi = ts_mcap_raw / 1e4 if ts_mcap_raw else 0
    computed_mcap = fields.get('market_cap_yi', 0)

    print(f"  {name}:")
    print(f"    investoday raw={i_mcap_raw:.0f}元 → /1e8={i_mcap_yi:.2f}亿")
    print(f"    Tushare raw={ts_mcap_raw:.2f}万元 → /1e4={ts_mcap_yi:.2f}亿")
    print(f"    _extract_core_fields = {computed_mcap:.2f}亿 (应=Tushare值)")
    match = abs(computed_mcap - ts_mcap_yi) < 0.1
    print(f"    {"✓ 匹配" if match else "✗ 不匹配！"}")

print("\n" + "=" * 80)
print("验证完成")
print("=" * 80)
