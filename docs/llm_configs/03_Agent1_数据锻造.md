# Agent-1: 数据锻造 (Data Forge)

> **类型**: 纯代码（无 LLM 调用）
> **文件**: `src/agent1_data_forge.py` (789 行)
> **触发**: Agent-0 完成后

---

## 配置

```python
# 无 LLM 调用 — 纯数据抓取 + 交叉验证
# 并行执行: ThreadPoolExecutor(max_workers=5)
```

## 数据抓取流程

### 第一阶段: investoday 核心数据包（8 个并行请求）

```python
core_bundle = [
    fetch_realtime_quote,       # 实时行情
    fetch_valuation,            # PE/PB/PS/EV_EBITDA + 排名
    fetch_income_ttm,           # 利润表 TTM
    fetch_balance_ttm,          # 资产负债表 TTM
    fetch_cashflow_ttm,         # 现金流量表 TTM
    fetch_fin_der_inds,         # ROIC/EBIT/EBITDA/毛利率/净利率
    fetch_profit_ability,       # 盈利能力指标 + 历史排名
    fetch_industries,           # 申万行业分类
]
```

### 第二阶段: investoday 专项数据包（6 个并行请求）

```python
specialized_bundle = [
    fetch_dupont,               # 杜邦分析
    fetch_segment_revenue,      # 主营产品收入拆分
    fetch_analyst_consensus,    # 分析师一致预期
    fetch_operating_review,     # 经营评述
    fetch_score,                # 综合得分
    fetch_event_window_prices,  # 事件窗口股价
]
```

### 第三阶段: Tushare 补充数据（5 个并行请求，可选）

```python
tushare_bundle = [
    ts_daily,                   # 日线行情
    ts_daily_basic,             # 日线指标（市值/PE/PB）
    ts_bs_q,                    # 资产负债表（季度）
    ts_income_q,                # 利润表（季度）
    ts_cf_q,                    # 现金流量表（季度）
    ts_fina_ind,                # 财务指标
    ts_fina_mainbz,             # 主营构成
    ts_forecast,                # 业绩预告
    ts_express,                 # 业绩快报
    ts_shareholder,             # 股东户数
]
```

## 交叉验证（8 项）

| 验证项 | investoday | Tushare | 容差 |
|--------|-----------|---------|------|
| 毛利率 | `fin-der-inds.gross_margin` | `fina_indicator.grossprofit_margin` | ±3pp |
| 净利率 | `fin-der-inds.net_margin` | `fina_indicator.netprofit_margin` | ±3pp |
| ROE | `dupont.roe` | `fina_indicator.roe` | ±3pp |
| ROIC | `fin-der-inds.roic` | — | — |
| EPS | `income-ttm.eps` | — | — |
| 资产负债率 | `balance-ttm` 计算 | `fina_indicator.debt_to_assets` | ±5pp |
| 营收 TTM | `income-ttm.revenue_ttm` | `income.total_revenue` | ±10% |
| 经营现金流 | `cashflow-ttm.operating_cf` | `cashflow` | ±20% |

## 数据质量评分

```python
overall_data_quality_score = weighted_score([
    (core_completeness, 0.50),
    (cross_validation_pass_rate, 0.30),
    (specialized_completeness, 0.15),
    (tushare_availability, 0.05),
])
```

## 输出结构

```python
{
    "request_id": str,
    "stock_code": str,
    "stock_name": str,
    "industry": str,
    "packages": {
        "core": {"fields": {...}, "quality": str},
        "specialized": {"fields": {...}, "quality": str},
        "optional": {"fields": {...}, "quality": str}
    },
    "cross_validation": {...},
    "overall_data_quality_score": float,  # 0-100
    "fetch_errors": [...],
    "event_date": str,
    "event_window_prices": {...},
    "incremental_fetch_hook": str
}
```

## 错误处理

- **E101**: `core_package` 关键字段缺失 → 硬终止，管线停止
- **E102**: investoday 部分端点超时 → 降级，`quality` 标记为 `partial`
- **E103**: Tushare 不可达 → 跳过，交叉验证标记为 `unavailable`
- **E104**: 交叉验证差异超容差 → 标记但不阻塞
