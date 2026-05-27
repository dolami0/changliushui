"""
前瞻信号计算引擎 — V5 估值管线

接收 Tushare 原始季度数据 + investoday segment/consensus 数据，
计算衍生信号 + **异常检测**（vs 历史分布），输出结构化 dict。

核心原则:
- LLM 不接收原始表格——只接收标注了异常等级的预计算信号
- 异常检测: 当前值 vs 8期历史均值和标准差，标注 sigma 偏离等级
- 五维度各自独立计算，一个数据源缺失不影响其他类别
"""

from __future__ import annotations

import math
from typing import Any


# ═══════════════════════════════════════
# 异常检测
# ═══════════════════════════════════════

def _anomaly(value: float | None, series: list[float | None]) -> dict:
    """检测当前值在历史序列中的异常程度。

    返回: {level, sigma, direction, mean, std}
      level: 'extreme' (>3σ) | 'significant' (>2σ) | 'elevated' (>1σ) | 'normal'
      direction: 'up' | 'down' | 'flat'
    """
    clean = [v for v in (series or []) if v is not None]
    if value is None or len(clean) < 4:
        return {'level': 'insufficient_data', 'sigma': 0, 'direction': 'flat',
                'mean': None, 'std': None}

    mean = sum(clean) / len(clean)
    # 样本标准差
    if len(clean) > 1:
        variance = sum((v - mean) ** 2 for v in clean) / (len(clean) - 1)
        std = math.sqrt(variance) if variance > 0 else 0.001
    else:
        std = 0.001

    sigma = (value - mean) / std
    abs_sigma = abs(sigma)

    if abs_sigma >= 3:
        level = 'extreme'
    elif abs_sigma >= 2:
        level = 'significant'
    elif abs_sigma >= 1:
        level = 'elevated'
    else:
        level = 'normal'

    direction = 'up' if sigma > 0.5 else ('down' if sigma < -0.5 else 'flat')

    return {
        'level': level,
        'sigma': round(sigma, 1),
        'direction': direction,
        'mean': round(mean, 2),
        'std': round(std, 2),
    }


def _anomaly_label(a: dict) -> str:
    """异常等级 → 可视化标签。"""
    m = {
        'extreme': '',
        'significant': '',
        'elevated': '',
        'normal': '',
        'insufficient_data': '',
    }
    return m.get(a['level'], '')


def _anomaly_text(a: dict, metric_name: str) -> str:
    """异常检测结果 → 一句话解读。"""
    if a['level'] == 'insufficient_data':
        return ''
    if a['level'] == 'normal':
        return f'{metric_name}在历史正常范围内(均值{a["mean"]}, σ={a["std"]})'
    direction = '高于' if a['direction'] == 'up' else '低于' if a['direction'] == 'down' else '持平'
    return f'{metric_name}显著{direction}历史均值(当前偏离{a["sigma"]}σ, 均值{a["mean"]}, σ={a["std"]})'


# ═══════════════════════════════════════
# 基础工具
# ═══════════════════════════════════════

def _qoq(latest: float | None, prev: float | None) -> float | None:
    if latest is None or prev is None or abs(prev) < 0.001:
        return None
    return round((latest - prev) / abs(prev) * 100, 1)


def _trend_classify(values: list[float | None]) -> str:
    """趋势分类: 加速增长 / 稳定增长 / 减速 / 下降 / 波动 / 数据不足"""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return '数据不足'
    diffs = [clean[i] - clean[i - 1] for i in range(1, len(clean))]
    ups = sum(1 for d in diffs if d > 0)
    downs = sum(1 for d in diffs if d < 0)
    if ups > downs and ups > len(diffs) * 0.6:
        if all(d > 0 for d in diffs):
            return '加速增长'
        return '稳定增长'
    elif downs > ups and downs > len(diffs) * 0.6:
        return '下降'
    elif ups == 0 and downs == 0:
        return '持平'
    return '波动'


def _to_pct(val) -> str:
    if val is None:
        return '?'
    return f'{val:+.1f}%'


# ═══════════════════════════════════════
# 主入口
# ═══════════════════════════════════════

def compute_forward_signals(
    bs_quarterly: dict | None = None,
    income_quarterly: dict | None = None,
    cf_quarterly: dict | None = None,
    forecast_data: dict | None = None,
    express_data: dict | None = None,
    shareholder_data: dict | None = None,
    segment_revenue: list[dict] | None = None,
    tushare_segments: list[dict] | None = None,
    fina_indicator: dict | None = None,
    core_fields: dict | None = None,
) -> dict:
    core = core_fields or {}
    sources_available = []
    sources_missing = []

    def _has(d):
        return d is not None and isinstance(d, dict) and d.get('periods') is not None

    cat1 = _compute_demand_reality(bs_quarterly, core)
    if _has(bs_quarterly):
        sources_available.append('资产负债表季度')
    else:
        sources_missing.append('资产负债表季度')

    cat2 = _compute_supply_readiness(bs_quarterly, cf_quarterly, core)
    if _has(cf_quarterly):
        sources_available.append('现金流季度')
    else:
        sources_missing.append('现金流季度')

    cat3 = _compute_product_structure(tushare_segments, segment_revenue, core, cat1)
    if segment_revenue or tushare_segments:
        sources_available.append('分部收入')
    else:
        sources_missing.append('分部收入')

    cat4 = _compute_cashflow_quality(cf_quarterly, core)

    cat5 = _compute_management_guidance(forecast_data, express_data, shareholder_data, fina_indicator)
    if forecast_data or express_data:
        sources_available.append('业绩预告/快报')
    else:
        sources_missing.append('业绩预告/快报')

    status = 'complete' if len(sources_missing) <= 2 else 'partial'
    if not sources_available:
        status = 'unavailable'

    anomalies = _collect_anomalies(cat1, cat2, cat4, cat5)
    text = _build_text_summary(anomalies) if anomalies else '无显著异常信号，所有前瞻指标在历史正常范围内'

    return {
        'status': status,
        'sources_available': sources_available,
        'sources_missing': sources_missing,
        'categories': {
            'demand_reality': cat1,
            'supply_readiness': cat2,
            'earnings_elasticity': cat3,
            'cashflow_quality': cat4,
            'management_guidance': cat5,
        },
        'anomalies': anomalies,
        'text_summary': text,
    }


def _collect_anomalies(cat1, cat2, cat4, cat5) -> list[dict]:
    """收集所有类别中异常等级 >= 'significant' 的信号。"""
    result = []
    for category, signals in [('需求真实性', cat1), ('供给准备度', cat2),
                                ('现金流质量', cat4), ('管理层预期', cat5)]:
        if not signals or signals.get('_note'):
            continue
        # 提取带 anomaly 标记的子信号
        for key, val in signals.items():
            if isinstance(val, dict) and 'anomaly' in val:
                a = val['anomaly']
                if a.get('level') in ('extreme', 'significant'):
                    result.append({
                        'category': category,
                        'signal': key,
                        'label': val.get('label', key),
                        'value': val.get('value'),
                        'anomaly': a,
                        'interpretation': val.get('interpretation', ''),
                        'story_check': val.get('story_check', ''),
                    })
            elif isinstance(val, dict) and 'flag' in val and val['flag']:
                # 管理层预期等定性信号
                result.append({
                    'category': category,
                    'signal': key,
                    'label': val.get('label', key),
                    'value': val.get('value'),
                    'flag': val['flag'],
                    'interpretation': val.get('interpretation', ''),
                })
    # 按异常等级排序: extreme > significant
    result.sort(key=lambda x: (
        0 if x.get('anomaly', {}).get('level') == 'extreme' else 1,
        -(abs(x.get('anomaly', {}).get('sigma', 0)))
    ))
    return result


def _build_text_summary(anomalies: list[dict]) -> str:
    if not anomalies:
        return ''
    parts = []
    for a in anomalies[:5]:
        direction = '↑' if a.get('anomaly', {}).get('direction') == 'up' else '↓'
        parts.append(f'{a["label"]}{direction}({a.get("anomaly",{}).get("sigma",0)}σ)')
    return '; '.join(parts)


# ═══════════════════════════════════════
# 类别1: 需求真实性
# ═══════════════════════════════════════

def _compute_demand_reality(bs: dict | None, core: dict) -> dict:
    if not bs or not bs.get('periods'):
        return {'_note': '资产负债表季度数据不可用'}
    ps = bs['periods']
    latest, prev = ps[0], ps[1] if len(ps) > 1 else {}
    rev_ttm = core.get('revenue_ttm_yi', 1)

    # ── 合同负债/预收款 ──
    adv_cur = latest.get('adv_receipts')
    adv_prev = prev.get('adv_receipts')
    adv_series = [p.get('adv_receipts') for p in ps]
    adv_qoq = _qoq(adv_cur, adv_prev)
    adv_anomaly = _anomaly(adv_cur, adv_series)

    # ── 应收账款 ──
    ar_cur = latest.get('accounts_receiv')
    ar_series = [p.get('accounts_receiv') for p in ps]
    ar_qoq = _qoq(ar_cur, prev.get('accounts_receiv'))

    # 应收/营收比（季度折算）
    ar_ratio = round(ar_cur / (rev_ttm / 4), 2) if ar_cur and rev_ttm > 1 else None
    ar_ratio_series = [p.get('accounts_receiv') / (rev_ttm / 4)
                       for p in ps if p.get('accounts_receiv') and rev_ttm > 1]
    ar_anomaly = _anomaly(ar_ratio, ar_ratio_series)

    # ── 预付款 ──
    prep_cur = latest.get('prepayments')
    prep_series = [p.get('prepayments') for p in ps]
    prep_qoq = _qoq(prep_cur, prev.get('prepayments'))

    return {
        'contract_liab': {
            'label': '合同负债',
            'value': adv_cur,
            'unit': '亿',
            'qoq_pct': adv_qoq,
            'trend': _trend_classify(adv_series),
            'anomaly': adv_anomaly,
            'anomaly_text': _anomaly_text(adv_anomaly, '合同负债'),
            'interpretation': (
                '预收款跳升→客户用真金白银锁定产能，需求真实增长得到验证'
                if adv_anomaly['direction'] == 'up' and adv_anomaly['level'] in ('extreme', 'significant')
                else '预收款下降→需求可能松动，订单转化率需警惕'
                if adv_anomaly['direction'] == 'down' and adv_anomaly['level'] in ('extreme', 'significant')
                else ''
            ),
            'story_check': (
                '若事件叙事宣称"订单爆发"但合同负债未异常增长→下调营收弹性假设'
                if adv_anomaly['direction'] != 'up'
                else '合同负债异常跳升验证了需求叙事→可支撑更高的近期营收CAGR'
            ),
        },
        'accounts_receivable': {
            'label': '应收账款',
            'value': ar_cur,
            'unit': '亿',
            'qoq_pct': ar_qoq,
            'ar_to_rev_ratio': ar_ratio,
            'anomaly': ar_anomaly,
            'anomaly_text': _anomaly_text(ar_anomaly, '应收/营收比'),
            'interpretation': (
                '应收增速远超营收增速→收入增长未伴随现金回流，利润含金量存疑'
                if ar_ratio and ar_ratio > 1.5 and ar_qoq and ar_qoq > 15
                else ''
            ),
        },
        'prepayments': {'label': '预付账款', 'value': prep_cur, 'unit': '亿', 'qoq_pct': prep_qoq},
    }


# ═══════════════════════════════════════
# 类别2: 供给准备度
# ═══════════════════════════════════════

def _compute_supply_readiness(bs: dict | None, cf: dict | None, core: dict) -> dict:
    if not bs or not bs.get('periods'):
        return {'_note': '资产负债表季度数据不可用'}
    ps = bs['periods']
    latest, prev = ps[0], ps[1] if len(ps) > 1 else {}

    cip_cur = latest.get('cip')
    cip_series = [p.get('cip') for p in ps if p.get('cip') is not None]
    cip_qoq = _qoq(cip_cur, prev.get('cip'))
    cip_anomaly = _anomaly(cip_cur, cip_series)

    fix_cur = latest.get('fix_assets')
    cip_ratio = round(cip_cur / fix_cur * 100, 1) if cip_cur and fix_cur and fix_cur > 0 else None

    # CAPEX/折旧
    capex_sum = None
    if cf and cf.get('periods'):
        capex_vals = [p.get('c_pay_acq_const_fiolta') for p in cf['periods'][:4]]
        capex_sum = round(sum(v for v in capex_vals if v), 2) if capex_vals else None

    depr_implied = (core.get('ebitda_ttm_yi', 0) or 0) - (core.get('operating_profit_ttm_yi', 0) or 0)
    capex_depr = round(capex_sum / depr_implied, 2) if capex_sum and depr_implied and depr_implied > 0.01 else None

    # 存货
    inv_cur = latest.get('inventories')
    inv_series = [p.get('inventories') for p in ps]
    inv_anomaly = _anomaly(inv_cur, inv_series)

    # 供给判断
    if capex_depr is not None:
        supply_label = '产能扩张期(CAPEX/折旧>1.5)' if capex_depr > 1.5 else ('维持期' if capex_depr >= 0.8 else '收缩期(CAPEX/折旧<0.8)')
    else:
        supply_label = '数据不足'

    return {
        'cip': {
            'label': '在建工程',
            'value': cip_cur,
            'unit': '亿',
            'qoq_pct': cip_qoq,
            'cip_to_fixed_pct': cip_ratio,
            'anomaly': cip_anomaly,
            'anomaly_text': _anomaly_text(cip_anomaly, '在建工程'),
            'interpretation': (
                '在建工程加速增长→产能扩张进入释放前夜，供给瓶颈即将缓解'
                if cip_anomaly['direction'] == 'up' and cip_anomaly['level'] in ('extreme', 'significant')
                else '在建工程缩减→产能扩张可能推迟，供给兑现风险上升'
                if cip_anomaly['direction'] == 'down' and cip_anomaly['level'] in ('extreme', 'significant')
                else ''
            ),
            'story_check': (
                '若事件叙事假设"产能即将释放"但在建工程未异常增长→推迟业绩兑现窗口，DCF折现期延长'
                if cip_anomaly['direction'] != 'up'
                else '在建工程加速扩张验证了供给准备→可支撑产能释放时间表'
            ),
        },
        'capex_depr_ratio': {
            'label': 'CAPEX/折旧比',
            'value': capex_depr,
            'supply_label': supply_label,
            'ttm_capex': capex_sum,
            'unit': '亿',
            'interpretation': (
                'CAPEX/折旧>1.5→企业在大幅扩张，未来产出弹性充足'
                if capex_depr and capex_depr > 1.5
                else 'CAPEX/折旧<0.8→企业仅在做维持性投入，扩张动力不足'
                if capex_depr is not None and capex_depr < 0.8
                else ''
            ),
        },
        'inventory': {
            'label': '存货',
            'value': inv_cur,
            'unit': '亿',
            'anomaly': inv_anomaly,
            'anomaly_text': _anomaly_text(inv_anomaly, '存货'),
            'interpretation': (
                '存货异常增加→可能主动备货应对需求/也可能滞销积压'
                if inv_anomaly['direction'] == 'up' and inv_anomaly['level'] in ('extreme', 'significant')
                else ''
            ),
        },
    }


# ═══════════════════════════════════════
# 类别3: 盈利弹性
# ═══════════════════════════════════════


def _compute_product_structure(
    tushare_segments: list[dict] | None,
    segment: list[dict] | None,
    core: dict,
    demand_signals: dict,
) -> dict:
    """产品结构信号包——照妖镜 + 拆解刀。

    照妖镜（叙事推演时）: 产品级毛利率验证叙事真伪
    拆解刀（估值计算时）: SOTP 拆解业务线，分别估值

    数据源优先级: Tushare fina_mainbz (4期: 2年报+2半年报) > investoday segment
    """
    from datetime import datetime

    # ── 提取产品数据（按 end_date 分组） ──
    by_period: dict[str, dict[str, dict]] = {}  # end_date → {product_name: {revenue, cost, gm}}
    periods_sorted: list[str] = []

    if tushare_segments:
        # 按 end_date 分组
        raw_by_period: dict[str, list] = {}
        for s in tushare_segments:
            ed = s.get('end_date', '')
            if ed not in raw_by_period:
                raw_by_period[ed] = []
            raw_by_period[ed].append(s)
        periods_sorted = sorted(raw_by_period.keys(), reverse=True)

        # 为每个期间构建产品字典（GM = bz_profit / bz_sales，直接利润率）
        import math
        for ed in periods_sorted:
            products: dict[str, dict] = {}
            for s in raw_by_period[ed]:
                name = str(s.get('item', ''))[:30]
                sales = s.get('sales')
                profit = s.get('profit')
                # 区分「无利润数据」(None/NaN) 和「利润为0」
                has_profit = (sales is not None and sales > 0
                              and profit is not None
                              and not (isinstance(profit, float) and math.isnan(profit)))
                products[name] = {
                    'revenue': round(sales, 2) if sales else 0,
                    'profit': round(profit, 2) if has_profit else None,
                    'gm': round(profit / sales * 100, 1) if has_profit else None,
                }
            by_period[ed] = products

    elif segment:
        products: dict[str, dict] = {}
        for s in segment[:10]:
            name = str(s.get('product_name', ''))[:30]
            rev = (s.get('product_income') or 0) / 1e8
            profit = (s.get('product_profit') or 0) / 1e8
            margin = s.get('profit_ratio_pct') or (round(profit / rev * 100, 1) if rev > 0 else None)
            if rev > 0:
                products[name] = {'revenue': round(rev, 2), 'gm': margin}
        by_period['investoday'] = products
        periods_sorted = ['investoday']

    if not by_period:
        return {'products': {'label': '产品结构', '_note': '无分产品数据'}}

    # ── 利润数据可用性分级（按产品-期间维度）──
    # fina_mainbz 的 bz_profit 并非所有公司/所有期间都披露。
    # 缺失的产品-期间组合用合并毛利率回退，有数据的保留实际值。
    all_products = []
    for ed_products in by_period.values():
        all_products.extend(ed_products.values())
    gm_avail_count = sum(1 for p in all_products if p.get('gm') is not None)
    gm_total = len(all_products)
    gm_coverage = gm_avail_count / gm_total if gm_total > 0 else 0

    company_gm = core.get('gross_margin_pct', 0)
    gm_source = 'actual' if gm_coverage >= 0.99 else ('mixed' if gm_coverage >= 0.3 else 'blended')

    # 逐产品-期间回退：缺失的填合并毛利率
    for ed_products in by_period.values():
        for p in ed_products.values():
            if p.get('gm') is None:
                p['gm'] = company_gm
                p['gm_source'] = 'blended'
            else:
                p['gm_source'] = 'actual'

    # ── 识别年报和半年报 ──
    annual_periods = [p for p in periods_sorted if p.endswith('1231')]
    semi_periods = [p for p in periods_sorted if not p.endswith('1231') and p != 'investoday']

    # 当前年报 与 上一年报（YoY 基准）
    fy_current = annual_periods[0] if annual_periods else periods_sorted[0]
    fy_prev = annual_periods[1] if len(annual_periods) >= 2 else (
        periods_sorted[1] if len(periods_sorted) >= 2 else None
    )

    products_current = by_period.get(fy_current, {})
    products_prev = by_period.get(fy_prev, {}) if fy_prev else {}

    # ── 半年报匹配：找到每个年报同年的半年报 ──
    def _find_h1(fy_end_date: str) -> str | None:
        """给定年报 end_date (如 20251231)，找到同年半年报 (如 20250630)。"""
        year = fy_end_date[:4]
        h1_candidate = f'{year}0630'
        if h1_candidate in semi_periods:
            return h1_candidate
        # fallback: 同年任意 0630 或最近的非年报
        for sp in semi_periods:
            if sp[:4] == year:
                return sp
        return None

    h1_current = _find_h1(fy_current)
    h1_prev = _find_h1(fy_prev) if fy_prev else None

    # ── 构建产品字典：年报的 + 半年报的（用于 H2 计算） ──
    products_h1_cur = by_period.get(h1_current, {}) if h1_current else {}
    products_h1_prev = by_period.get(h1_prev, {}) if h1_prev else {}

    # ── 公司整体指标 ──
    total_rev_cur = sum(p['revenue'] for p in products_current.values())
    total_rev_prev = sum(p['revenue'] for p in products_prev.values()) if products_prev else 0
    company_gm = core.get('gross_margin_pct', 0)
    company_gm_rank = core.get('gross_margin_historical_rank', 50)

    # ── 维度1: 产品结构变化（年报 YoY + H2 轨迹） ──
    product_mix = []
    for name, cur in products_current.items():
        prev = products_prev.get(name, {})
        h1c = products_h1_cur.get(name, {})
        h1p = products_h1_prev.get(name, {})

        # 年报 YoY
        share_cur = round(cur['revenue'] / total_rev_cur * 100, 1) if total_rev_cur > 0 else 0
        share_prev = round(prev.get('revenue', 0) / total_rev_prev * 100, 1) if total_rev_prev > 0 else None
        share_chg = round(share_cur - share_prev, 1) if share_prev is not None else None
        rev_prev = prev.get('revenue')
        rev_chg = round((cur['revenue'] - rev_prev) / rev_prev * 100, 1) if rev_prev and rev_prev > 0 else None
        gm_cur = cur.get('gm')
        gm_prev = prev.get('gm')
        gm_chg = round(gm_cur - gm_prev, 1) if gm_cur is not None and gm_prev is not None else None

        # H2 拆解（年报 − 半年报 = 下半年实际业绩，GM = H2_profit / H2_revenue）
        h2_revenue = None
        h2_gm = None
        h2_revenue_prev = None
        h2_gm_prev = None
        h2_yoy = None

        h1c_rev = h1c.get('revenue') if h1c else None
        h1c_profit = h1c.get('profit') if h1c else None

        if h1c_rev is not None and h1c_rev > 0:
            h2_revenue = round(cur['revenue'] - h1c_rev, 2)
            if h1c_profit is not None:
                h2_profit = (cur.get('profit') or 0) - h1c_profit
                if h2_revenue > 0.01 and h2_profit >= 0:
                    h2_gm = round(h2_profit / h2_revenue * 100, 1)

        h1p_rev = h1p.get('revenue') if h1p else None
        h1p_profit = h1p.get('profit') if h1p else None

        if h1p_rev is not None and h1p_rev > 0 and h1p_profit is not None:
            h2_revenue_prev = round(prev.get('revenue', 0) - h1p_rev, 2)
            h2_profit_prev = (prev.get('profit') or 0) - h1p_profit
            if h2_revenue_prev > 0.01 and h2_profit_prev >= 0:
                h2_gm_prev = round(h2_profit_prev / h2_revenue_prev * 100, 1)

        # H2 同比
        if h2_revenue and h2_revenue_prev and h2_revenue_prev > 0.01:
            h2_yoy = round((h2_revenue - h2_revenue_prev) / h2_revenue_prev * 100, 1)

        product_mix.append({
            'name': name,
            # 年报 YoY
            'revenue': cur['revenue'],
            'revenue_share_pct': share_cur,
            'revenue_share_prev_pct': share_prev,
            'share_change_ppt': share_chg,
            'revenue_yoy_pct': rev_chg,
            'gross_margin_pct': gm_cur,
            'gm_prev_pct': gm_prev,
            'gm_change_ppt': gm_chg,
            'gm_source': cur.get('gm_source', 'actual'),
            # H2 轨迹
            'h2_revenue': h2_revenue,
            'h2_gross_margin_pct': h2_gm,
            'h2_revenue_prev': h2_revenue_prev,
            'h2_gm_prev_pct': h2_gm_prev,
            'h2_revenue_yoy_pct': h2_yoy,
            'h2_available': h2_revenue is not None,
        })
    product_mix.sort(key=lambda x: -(x.get('revenue', 0)))

    # ── 关键词匹配 ──
    generic_kw = ['半导体', '锗', '电容', '模块', '芯片', '衬底', '光', '红外',
                  '光伏', '光纤', '材料', '设备', '元器件', '组件', '系统', '化合物']
    keyword_matches = {}
    for p in product_mix:
        hints = [kw for kw in generic_kw if kw in p['name']]
        if hints:
            keyword_matches[p['name']] = hints

    # ── 维度2: 毛利率结构性验证 ──
    gms = [p['gross_margin_pct'] for p in product_mix if p['gross_margin_pct'] is not None]
    margin_spread = round(max(gms) - min(gms), 1) if len(gms) >= 2 else 0
    high_gm = [p for p in product_mix if p.get('gross_margin_pct') and p['gross_margin_pct'] > 30]
    low_gm = [p for p in product_mix if p.get('gross_margin_pct') is not None and p['gross_margin_pct'] < 10]
    high_gm_share = round(sum(p['revenue_share_pct'] for p in high_gm), 1)
    high_gm_share_prev = round(sum(p.get('revenue_share_prev_pct', 0) or 0 for p in high_gm), 1) if products_prev else None

    # 毛利率改善来源
    source = '数据不足'
    if products_prev and len(products_prev) >= 2:
        gm_up = sum(1 for p in product_mix if p.get('gm_change_ppt') is not None and p['gm_change_ppt'] > 2)
        share_up = sum(1 for p in product_mix if p.get('share_change_ppt') is not None and p['share_change_ppt'] > 2)
        if gm_up >= len(product_mix) * 0.6:
            source = '全线提价(多数产品GM提升)'
        elif share_up >= 2 and high_gm_share > (high_gm_share_prev or 0):
            source = '产品结构切换(高毛利产品占比上升)'
        else:
            source = '混合驱动'

    margin_structure = {
        'company_blended_gm': company_gm,
        'company_gm_rank': company_gm_rank,
        'max_product_gm': max(gms) if gms else None,
        'min_product_gm': min(gms) if gms else None,
        'gm_spread_ppt': margin_spread,
        'high_gm_products_share_pct': high_gm_share,
        'high_gm_share_prev_pct': high_gm_share_prev,
        'gm_improvement_source': source,
        'low_gm_products': [
            {'name': p['name'], 'gm': p['gross_margin_pct'], 'share': p['revenue_share_pct']}
            for p in low_gm
        ],
    }

    # ── 维度3: 订单-收入交叉验证 ──
    adv_qoq = demand_signals.get('contract_liab', {}).get('qoq_pct') if demand_signals else None
    high_growth = [p for p in product_mix if p.get('revenue_yoy_pct') is not None and p['revenue_yoy_pct'] > 20]
    contract_surge = adv_qoq is not None and adv_qoq > 50

    crosscheck = {
        'contract_liab_qoq_pct': adv_qoq,
        'high_growth_products': [p['name'] for p in high_growth],
        'contract_to_revenue_lag': (
            '合同负债暴增但产品收入尚未同步加速 → 订单在交付周期中, 业绩释放在未来2-3季度'
            if contract_surge and not high_growth
            else '合同负债与产品收入同步增长 → 订单已在转化为收入'
            if contract_surge and high_growth
            else '合同负债无异常 → 需求信号尚未体现在下游预付款中'
            if not contract_surge
            else ''
        ),
    }

    # ── H2 动量判断 ──
    h2_momentum = ''
    if h1_current:
        h2_accel = [p for p in product_mix if p.get('h2_revenue_yoy_pct') is not None and p['h2_revenue_yoy_pct'] > 20]
        h2_decel = [p for p in product_mix if p.get('h2_revenue_yoy_pct') is not None and p['h2_revenue_yoy_pct'] < -10]
        if h2_accel and not h2_decel:
            h2_momentum = f'H2加速: {", ".join(p["name"][:12] for p in h2_accel[:3])}'
        elif h2_decel:
            h2_momentum = f'H2减速: {", ".join(p["name"][:12] for p in h2_decel[:3])}'
        elif any(p.get('h2_revenue') for p in product_mix):
            h2_momentum = 'H2营收可算'

    # ── 时序标注 ──
    vintage_str = ''
    if fy_current and fy_prev:
        c0 = fy_current[:4] + '-' + fy_current[4:6] + '-' + fy_current[6:8]
        c1 = fy_prev[:4] + '-' + fy_prev[4:6] + '-' + fy_prev[6:8]
        vintage_str = f'{c0} vs {c1}'
        if h1_current:
            vintage_str += f' | H2轨迹: {fy_current[:4]}H2 vs {fy_prev[:4]}H2'
    elif fy_current:
        vintage_str = fy_current[:4] + '-' + fy_current[4:6] + '-' + fy_current[6:8]
    try:
        vt = datetime.strptime(fy_current, '%Y%m%d')
        months_ago = (datetime.now() - vt).days / 30
        if months_ago > 6:
            vintage_str += f' (数据滞后{months_ago:.0f}月)'
    except (ValueError, TypeError):
        pass

    # ── 一句话解读 ──
    parts = []
    if margin_spread > 30:
        parts.append(f'毛利率严重分化(极差{margin_spread}ppt)')
    if high_gm_share > 30:
        parts.append(f'高毛利占比{high_gm_share}%')
    if source != '数据不足':
        parts.append(source)
    lag_text = crosscheck.get('contract_to_revenue_lag', '')
    if lag_text:
        parts.append(lag_text)
    if h2_momentum:
        parts.append(h2_momentum)
    interpretation = '; '.join(parts) if parts else '产品结构无显著异常'

    return {
        'products': {
            'label': '产品结构信号',
            'data_vintage': vintage_str,
            'gm_source': gm_source,
            'gm_coverage_pct': round(gm_coverage * 100, 1),
            'periods_available': len(periods_sorted),
            'annual_periods': len(annual_periods),
            'has_h1_data': h1_current is not None,
            'product_mix': product_mix,
            'keyword_matches': keyword_matches,
            'margin_structure': margin_structure,
            'order_fulfillment_crosscheck': crosscheck,
            'h2_momentum': h2_momentum,
            'interpretation': interpretation,
            'story_check': (
                '产品级毛利率 = 叙事推演硬约束。'
                '核心叙事产品毛利率显著低于宣称值 → 区分"数据滞后"与"叙事夸大"。'
            ),
        },
    }



def _compute_cashflow_quality(cf: dict | None, core: dict) -> dict:
    if not cf or not cf.get('periods'):
        return {'_note': '现金流季度数据不可用'}

    cfs = cf['periods']
    seen = set()
    cf_4q = []
    for p in cfs:
        ed = p.get('end_date', '')
        if ed not in seen:
            seen.add(ed)
            cf_4q.append(p)
        if len(cf_4q) >= 4:
            break

    ocf_vals = [p.get('n_cashflow_act') for p in cf_4q if p.get('n_cashflow_act') is not None]
    capex_vals = [p.get('c_pay_acq_const_fiolta') for p in cf_4q if p.get('c_pay_acq_const_fiolta') is not None]
    ocf_ttm = round(sum(ocf_vals), 2) if ocf_vals else None
    capex_ttm = round(sum(capex_vals), 2) if capex_vals else None
    fcf_ttm = round((ocf_ttm or 0) - (capex_ttm or 0), 2)

    ni_ttm = core.get('net_profit_ttm_yi', 0)
    ocf_ni = round(ocf_ttm / ni_ttm, 2) if ocf_ttm and ni_ttm and abs(ni_ttm) > 0.01 else None

    # OCF/NI 异常检测: 用季度 OCF/NI_q 序列
    ocf_ni_series = []
    for p in cf_4q:
        ni_q = ni_ttm / 4 if ni_ttm else 0.001
        ocf_q = p.get('n_cashflow_act')
        if ocf_q and abs(ni_q) > 0.001:
            ocf_ni_series.append(round(ocf_q / ni_q, 2))
    ocf_ni_anomaly = _anomaly(ocf_ni, ocf_ni_series) if ocf_ni is not None else {'level': 'insufficient_data', 'sigma': 0, 'direction': 'flat', 'mean': None, 'std': None}

    # FCF 拐点
    fcf_turning = False
    if len(cf_4q) >= 3:
        fcf_q = []
        for p in cf_4q[:4]:
            o = p.get('n_cashflow_act') or 0
            c = p.get('c_pay_acq_const_fiolta') or 0
            fcf_q.append(round(o - c, 2))
        if len(fcf_q) >= 3 and fcf_q[0] > 0 and fcf_q[2] < 0:
            fcf_turning = True

    # 质量标签
    if ocf_ni is not None:
        if ocf_ni >= 1.0:
            qual = '现金奶牛(OCF≥NI)'
        elif ocf_ni >= 0.5:
            qual = '正常(0.5≤OCF/NI<1.0)'
        elif ocf_ni >= 0:
            qual = '纸面富贵(OCF/NI<0.5)'
        else:
            qual = '现金流为负(OCF<0)'
    else:
        qual = '数据不足'

    return {
        'ocf_to_ni': {
            'label': 'OCF/净利润',
            'value': ocf_ni,
            'ocf_ttm': ocf_ttm,
            'ni_ttm': ni_ttm,
            'unit': '倍',
            'quality_label': qual,
            'anomaly': ocf_ni_anomaly,
            'anomaly_text': _anomaly_text(ocf_ni_anomaly, 'OCF/NI比'),
            'interpretation': (
                '利润含金量极低(OCF/NI<0.5)→净利润可能包含大量非现金项目，需警惕"纸面利润"'
                if ocf_ni is not None and ocf_ni < 0.5
                else '利润含金量充足(OCF/NI>1.0)→利润有真金白银支撑'
                if ocf_ni is not None and ocf_ni >= 1.0
                else ''
            ),
            'story_check': (
                '若事件叙事强调"业绩爆发"但OCF持续为负→利润未转化为现金，估值需打折扣'
                if ocf_ni is not None and ocf_ni < 0
                else ''
            ),
        },
        'fcf': {
            'label': '自由现金流',
            'value': fcf_ttm,
            'unit': '亿',
            'turning_positive': fcf_turning,
            'fcf_yield_pct': round(fcf_ttm / core.get('market_cap_yi', 100) * 100, 2) if fcf_ttm and core.get('market_cap_yi', 0) > 0 else None,
            'interpretation': 'FCF由负转正→企业进入自我造血阶段，可下调资本成本' if fcf_turning else '',
        },
    }


# ═══════════════════════════════════════
# 类别5: 管理层预期
# ═══════════════════════════════════════

_FORECAST_TYPE_MAP = {
    '1': '预增', '2': '预减', '3': '略增', '4': '略减',
    '5': '扭亏', '6': '首亏', '7': '续亏', '8': '续盈',
}


def _extract_trend(fina_indicator: dict | None) -> dict:
    """从 fina_indicator 预计算趋势中提取最近 4 期间数据，结构化输出。"""
    if not fina_indicator or not fina_indicator.get('trends'):
        return {'_note': 'fina_indicator 趋势数据不可用'}
    trends = fina_indicator['trends']
    # 取最近 4 期
    items = []
    for t in trends[:4]:
        items.append({
            'period': t.get('end_date', ''),
            'revenue_yoy': t.get('tr_yoy'),
            'revenue_q_yoy': t.get('q_sales_yoy'),
            'revenue_q_qoq': t.get('q_sales_qoq'),
            'op_q_yoy': t.get('q_op_yoy'),
            'op_q_qoq': t.get('q_op_qoq'),
            'profit_q_yoy': t.get('q_profit_yoy'),
            'profit_q_qoq': t.get('q_profit_qoq'),
            'roic': t.get('roic'),
            'gm': t.get('grossprofit_margin'),
        })
    # 最新一期摘要
    latest = items[0] if items else {}
    accel = ''
    if latest.get('revenue_q_yoy') is not None and len(items) >= 2:
        prev = items[1].get('revenue_q_yoy')
        if prev is not None and latest['revenue_q_yoy'] > prev + 5:
            accel = '加速'
        elif prev is not None and latest['revenue_q_yoy'] < prev - 5:
            accel = '减速'
    return {
        'label': '盈利趋势(单季度)',
        'latest_revenue_q_yoy': latest.get('revenue_q_yoy'),
        'latest_op_q_yoy': latest.get('op_q_yoy'),
        'latest_profit_q_yoy': latest.get('profit_q_yoy'),
        'latest_revenue_q_qoq': latest.get('revenue_q_qoq'),
        'latest_roic': latest.get('roic'),
        'latest_gm': latest.get('gm'),
        'trend_direction': accel or '平稳',
        'recent_4q': items,
    }


def _compute_management_guidance(
    forecast: dict | None,
    express: dict | None,
    shareholder: dict | None,
    fina_indicator: dict | None = None,
) -> dict:
    # 业绩预告
    fc_type = '无预告'
    fc_range = None
    fc_flag = False
    fc_interp = ''
    if forecast:
        fc_type = _FORECAST_TYPE_MAP.get(str(forecast.get('type', '')), str(forecast.get('type', '无预告')))
        lo = forecast.get('p_change_min')
        hi = forecast.get('p_change_max')
        if lo is not None and hi is not None:
            fc_range = f'{lo:.0f}%~{hi:.0f}%'
        # 异常标记: 预告方向与事件方向矛盾
        if fc_type in ('预减', '首亏', '续亏'):
            fc_flag = True
            fc_interp = '业绩预告方向为负面→若事件叙事看多，需审视事件是否尚未转化为业绩，或在reasoning_trace中解释预告窗口与事件窗口的时序差异'

    # 业绩快报
    express_ok = express is not None
    express_growth = express.get('yoy_sales') if express else None

    # 股东人数
    holder_trend = '数据不足'
    holder_flag = False
    holder_interp = ''
    if shareholder and shareholder.get('items'):
        nums = [it['holder_num'] for it in shareholder['items'] if it.get('holder_num')]
        if len(nums) >= 2:
            if nums[0] < nums[-1] * 0.9:
                holder_trend = '加速集中'
                holder_interp = '股东人数大幅下降→筹码向机构集中，往往是股价启动前的信号'
            elif nums[0] < nums[-1]:
                holder_trend = '缓慢集中'
            elif nums[0] > nums[-1] * 1.1:
                holder_trend = '显著分散'
                holder_flag = True
                holder_interp = '股东人数大幅增加→筹码分散，可能是主力出货信号'
            elif nums[0] > nums[-1]:
                holder_trend = '略分散'
            else:
                holder_trend = '稳定'

    return {
        'forecast': {
            'label': '业绩预告',
            'type': fc_type,
            'np_change_range': fc_range,
            'flag': fc_flag,
            'interpretation': fc_interp,
        },
        'express': {
            'label': '业绩快报',
            'available': express_ok,
            'revenue_growth_pct': express_growth,
        },
        'shareholder': {
            'label': '股东人数',
            'trend': holder_trend,
            'flag': holder_flag,
            'interpretation': holder_interp,
        },
        'earnings_trend': _extract_trend(fina_indicator),
    }
