---
name: shenwaihuashen-data-verify
description: 数据验证 — 三重交叉验证 + 异常检测协议。验证上游报告的关键数据，检测 tushare 数据异常，必要时使用 investoday 和 WebSearch 交叉验证。触发条件：接收标的分析上下文后，Step 1 自动调用。
---

# 数据验证

## 输入

| 来源 | 内容 | 格式 |
|------|------|------|
| 用户消息 | 标的分析上下文：股票代码、定数录公司基座（PE/市值/ROIC/毛利率/营收/净利）、匹配灵光列表、匹配案例列表 | Markdown 文本 |
| config.json | tushare token、investoday token | JSON |

## 输出

| 去向 | 内容 | 格式 |
|------|------|------|
| → 后续 Skill | 验证后的关键数据（PE/市值/毛利率/质押率 采用值）、数据矛盾清单、异常标记及处置结果 | 结构化表格 + 标注 |

## 核心原则

**内部一致性 ≠ 数据正确性。** tushare `bz_profit = bz_sales - bz_cost` 可以通过减法验证，但 `bz_cost` 本身可能是 0——这不是数据一致，是数据缺失。

## 执行流程

### 1. 关键数据拉取

```bash
python data_helper.py valuation <code>     # PE/PB/市值 + ROE/毛利率
python data_helper.py segment <code>       # 分产品拆解（含异常自动标记）
python data_helper.py pledge <code>        # 质押（风控铁律）
```

> **质押强制规则**：tushare pledge 返回 `[]` 视为拉取失败，必须立即切 investoday (`investoday-api stock/pledge-details --method POST stockCode=<code> pageSize=5`) 重试。investoday 也 `[]` 才可认定为「无质押」。不得以 tushare `[]` 直接结案。若 investoday 调用失败（非空），走 WebSearch 兜底。每一步切换都必须记录在 step1 文件中。```

### 2. 上游数据对照

| 指标 | 定数录/藏经阁 | tushare 实测 | 偏差 | 采用 |
|------|-------------|-------------|------|------|
| PE | | | | |
| 市值 | | | | |
| 毛利率 | | | | |
| ROIC | | | | |
| 质押率 | | | | |

- 偏差 <5% → 直接采用
- 偏差 5-20% → 标注，采用 tushare
- 偏差 >20% → 红色标记，investoday 三方验证

### 3. 异常检测协议

`data_helper.py segment` 输出中的 `ANOMALY` 标记自动触发以下协议：

```
ANOMALY 触发
    ↓
Step A: investoday 合并层面验证
    → investoday-api stock/financial-indicators-profitab ...
    → 对比合并毛利率是否一致
    → 如一致但分产品异常 → tushare 分产品成本分配问题
    ↓
Step B: WebSearch 年报附注
    → 搜索「{股票名} {年份}年报 收入构成 分产品 成本」
    → 确认分产品的业务实质
    ↓
Step C: 标注 + 采用修正值
    → 报告中标注「数据源异常/已交叉验证」
    → 给出修正后的合理估计
```

### 4. 常见异常模式（A 股）

| 异常 | 典型表现 | 原因 | 处置 |
|------|---------|------|------|
| 分产品 GM > 90% | 制造业「其他业务」 | tushare bz_cost=0 或废料收入 | WebSearch 年报附注确认业务实质 |
| PE 跳跃 > 100% | 季度间 PE 异常变化 | 非经常性损益或股本变动 | 查扣非净利润 |
| 质押率 > 50% | 大股东高质押 | 真实 | 一票否决 |
| OCF 剧烈波动 | Q4 OCF 突然跳升/跳水 | A 股年末回款/付款集中 | 看全年而非单季 |

### 5. 定数录纠错清单

定数录可能出错的地方——每次验证时重点检查：

- [ ] 分产品毛利率：是否引用了 tushare 的异常高值？（本川案例）
- [ ] 质押率：定数录经常遗漏此项
- [ ] 营收/利润数据：与 tushare 对照
- [ ] BS 检测器输入：NOPAT、WACC 取值是否合理？
- [ ] Bull 情景假设：毛利率、PE 目标是否基于正确数据？

## 数据源优先级

```
tushare (主) → investoday (备) → WebSearch 年报附注 (兜底)
```

凭证在 `config.json` → `dataSources`。

## 质量检查

- [ ] PE/市值/毛利率的 tushare vs 定数录 对照已完成
- [ ] 所有 ANOMALY 标记已触发交叉验证
- [ ] 质押率已验证
- [ ] 定数录数据异常已在报告中标注
