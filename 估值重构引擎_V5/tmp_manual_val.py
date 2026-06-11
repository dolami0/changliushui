# Manual SOTP+DCF valuation for 688720
mcap = 81.5
cash, debt = 1.1, 1.9
net_cash = cash - debt

# Segment definition
primary_rev = 2.88 + 1.36 + 0.19  # 4.43
primary_gm = (2.88*38.9 + 1.36*35.3 + 0.19*31.6) / primary_rev
secondary_rev = 1.48 + 0.02  # 1.50
secondary_gm = (1.48*3.4 + 0.02*50.0) / secondary_rev

print(f'Market cap: {mcap:.0f}yi | PE 153x | PS 13x | ROIC 3.7%')
print(f'Net debt: {-net_cash:.1f}yi')
print(f'Primary: rev={primary_rev:.2f}yi (~{primary_rev/6.3*100:.0f}%) GM={primary_gm:.1f}%')
print(f'Secondary: rev={secondary_rev:.2f}yi (~{secondary_rev/6.3*100:.0f}%) GM={secondary_gm:.1f}%')
print()

scenarios = {
    'bear': (0.15, 0.15, 3, 0.08, 18, 8,
             'Deceleration continues, competition intensifies, photoresist verification fails'),
    'base': (0.55, 0.32, 5, 0.13, 30, 13,
             'Advanced packaging expansion drives 35-40% electroplating growth, photoresist passes verification, margin expansion'),
    'bull': (0.30, 0.48, 5, 0.20, 40, 18,
             'HBM/3D stacking boom, company becomes TSV electroplating key supplier (>30% share), platform premium'),
}

wacc = 0.10
total_weighted = 0

for sn, (prob, g1, yrs, roic, tpe, nm, desc) in scenarios.items():
    nopat0 = primary_rev * nm / 100
    nopat = nopat0
    pv_s1 = 0.0

    for t in range(1, min(yrs, 10) + 1):
        nopat = nopat * (1 + g1)
        rr = g1 / roic if roic > 0 else 0.5
        rr = max(0.3, min(0.9, rr))
        fcff = nopat * (1 - rr)
        pv_s1 += fcff / (1 + wacc) ** t

    tv = nopat * tpe
    pv_tv = tv / (1 + wacc) ** min(yrs, 10)
    primary_val = round(pv_s1 + pv_tv, 1)

    # Secondary: PE 12x
    secondary_nopat = secondary_rev * 1.5 / 100
    secondary_val = round(secondary_nopat * 12, 1)

    total = primary_val + secondary_val + net_cash
    upside = round((total / mcap - 1) * 100, 1)

    total_weighted += prob * total

    print(f'[{sn}] prob={prob*100:.0f}% g={g1*100:.0f}% yrs={yrs} ROIC={roic*100:.0f}% tPE={tpe} nm={nm}%')
    print(f'  {desc}')
    print(f'  NOPAT0={nopat0:.2f} -> NOPAT_N={nopat:.1f} TV={tv:.0f} PV_TV={pv_tv:.0f} stage1_PV={pv_s1:.1f}')
    print(f'  Primary={primary_val} + Secondary={secondary_val} + NetDebt={net_cash} = {total}yi [{upside:+.1f}%]')
    print()

print(f'Weighted fair value: {total_weighted:.1f}yi')
print(f'vs market {mcap}yi: {((total_weighted/mcap)-1)*100:+.1f}%')
print()
print('--- Cross-check with simple multiples ---')
# If the market is at 81.5yi, what does it imply?
nopat_ttm = 0.46
print(f'Implied PE (NOPAT): {mcap/nopat_ttm:.0f}x (TTM NOPAT={nopat_ttm}yi)')
print(f'Fair PE 30x: {nopat_ttm*30:.0f}yi')
print(f'Fair PE 50x: {nopat_ttm*50:.0f}yi')
print(f'Fair PS 5x: {6.3*5:.0f}yi')
print(f'Fair PS 8x: {6.3*8:.0f}yi')
rev_3y = 6.3 * 1.30**3
print(f'3y rev at 30% CAGR: {rev_3y:.1f}yi -> PS=5x => {rev_3y*5:.0f}yi market cap')
