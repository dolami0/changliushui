---
name: shenwaihuashen-thesis
description: 论点追踪 — 融合 Anthropic thesis-tracker，适配 A 股。建立/更新投资论点档案、支柱评分卡、催化剂日历、价格追踪日志。触发条件：决策通过或有条件通过后自动调用；后续追踪时独立调用。
---

# 论点追踪

改编自 Anthropic `thesis-tracker`，A 股适配。

## 输入

### 初次建立时

| 来源 | 内容 | 格式 |
|------|------|------|
| decision 输出 | 建议仓位、建仓策略、关键假设、退出条件、催化剂日历 | Markdown 报告 |
| financial 输出 | 支柱相关的量化期望值 | 结构化数据 |
| industry 输出 | 卡位评级、行业阶段 | 文本 |

### 后续更新时

| 来源 | 内容 | 格式 |
|------|------|------|
| memory/tracking/{code}-{name}.json | 已有论点档案 | JSON |
| tushare | 最新价格/PE/市值 | data_helper.py |
| WebSearch | 最新公告/财报/催化剂落地 | 搜索摘要 |

## 输出

| 去向 | 内容 | 格式 |
|------|------|------|
| memory/tracking/ | 论点档案（thesis/pillars/risks/exitConditions/catalystCalendar/priceLog/positionLog） | JSON |
| 用户 | 论点评分卡（pillar 状态 + 趋势 + 行动建议） | Markdown 表格 |

## 核心原则

**论点必须是可证伪的。** 如果没有任何数据可以推翻你的论点，那它不是一个论点——它是一个信念。投资决策需要前者，不需要后者。

## 执行流程

### 1. 论点建立（决策通过后）

**建档时必须拉取当日收盘价作为基准价：**
... (existing) ...

**建档后必须同步到 Coze 追踪令表（强制）**：

```bash
cd D:\长流水\.agents\agents\shenwaihuashen && python sync_coze.py "memory/tracking/{stockCode}-{stockName}.json"
```

> 此脚本读取追踪 JSON → 映射字段 → Coze PUT 更新。Coze 表 ID: `7645332166129287218`。

**建档前必须先拉取当日收盘价（强制·不可跳过）：**

```bash
cd D:\长流水\.agents\agents\shenwaihuashen && python data_helper.py daily <code> <前一交易日> <当日>
# 取最近一个交易日的 close 作为 basePrice
# 同时记录 PE/市值作为 basePE/baseMarketCap
```

**硬闸门：`basePrice` 为 null 或 0 → 禁止写入 JSON。** 必须先执行上述 Bash，拿到真实收盘价，再填入模板。违反此条 → thesis 文件视为无效，前端页面将黑屏。

```json
{
  "stockCode": "300617",
  "stockName": "安靠智电",
  "track_status": "active",
  "thesis": "一句话核心投资逻辑（可证伪）",
  "conviction": 45,
  "decisionDate": "2026-05-28",
  "decision": "有条件通过",
  "recommendedPosition": 8,
  "actualPosition": 0,
  "entryCondition": "进入条件描述",
  "entryPriceTarget": 66.53,
  "pillars": [
    {
      "name": "支柱名称",
      "expectation": "期望发生什么（可量化）",
      "quantifiedTarget": "量化目标（如「H1营收>5亿」）",
      "status": "pending",
      "verificationDate": "2026-08-31",
      "lastChecked": "2026-05-28",
      "history": [
        {"date": "2026-05-28", "actual": "当前实际数据", "trend": "up"}
      ]
    }
  ],
  "risks": [
    {
      "name": "风险名称",
      "probability": "低/中/高",
      "impact": "如果发生会怎样",
      "monitoring": "如何监控"
    }
  ],
  "exitConditions": [
    "条件1 → 行动",
    "条件2 → 行动"
  ],
  "catalystCalendar": [
    {
      "date": "2026-09",
      "event": "事件名称",
      "type": "公司/财报/行业/政策/市场",
      "impact": "H",
      "bull": "看多触发条件",
      "bear": "看空触发条件",
      "sourceLevel": "L4",
      "sourceDetail": "2026-05 机构调研纪要",
      "sourceNote": "口头指引，待公告确认",
      "status": "pending"
    }
  ],
  "basePrice": 66.53,
  "baseMarketCap": 110.25,
  "baseDate": "2026-05-27",
  "priceLog": [
    {"date": "2026-05-27", "price": 66.53, "pe": 149.8, "mv_yi": 110.25, "return_pct": 0.0, "mv_change_pct": 0.0, "note": "建档基准价"}
  ],
  "positionLog": [],
  "valuationComparison": {
    "date": "2026-05-29",
    "method": "闭卷推导→开卷对比",
    "scenarios": {
      "bear": { "myCAGR": 0, "myPS": 0, "myReturn": 0, "upCAGR": 0, "upPS": 0, "upReturn": 0 },
      "base": { "myCAGR": 0, "myPS": 0, "myReturn": 0, "upCAGR": 0, "upPS": 0, "upReturn": 0 },
      "bull": { "myCAGR": 0, "myPS": 0, "myReturn": 0, "upCAGR": 0, "upPS": 0, "upReturn": 0 }
    },
    "myWeightedReturn": 0,
    "upWeightedReturn": 0,
    "myAsymmetry": 0,
    "upAsymmetry": 0,
    "verdict": ""
  },
  "aShareTracking": {
    "pledgeCheck": {"lastChecked": "2026-05-28", "result": "质押率0.88%"},
    "unlockCheck": {"lastChecked": "2026-05-28", "result": "无近期大额解禁"},
    "marginCheck": {"lastChecked": "2026-05-28", "result": "待首次月度专检"},
    "insiderTrading": {"lastChecked": "2026-05-28", "result": "待首次月度专检"}
  },
  "reviewSchedule": {
    "nextFullReview": "2026-08-31(半年报)",
    "nextQuickCheck": "2026-05-29(明日巡检)",
    "lastCheck": "2026-05-28(建档)",
    "patrolFrequency": "每个工作日 9:07"
  }
}
```

**字段对齐 Tracking.tsx `TrackingData` 接口。** 所有字段名、类型、嵌套结构与前端严格一致。

### 关键字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| `pillars[].quantifiedTarget` | 可量化验证目标 | `"H1营收>5亿"` |
| `pillars[].verificationDate` | 验证截止日 | `"2026-08-31"` |
| `pillars[].status` | `pending` / `on_track` / `at_risk` / `verified` | — |
| `catalystCalendar[].impact` | `H`(重大) / `M`(中等) / `L`(轻微) | — |
| `catalystCalendar[].sourceLevel` | `L5`(公告) / `L4`(纪要) / `L3`(研报) / `L2`(媒体) / `L1`(传闻) | 来自 catalyst skill §1 信源审计 |
| `catalystCalendar[].status` | `pending` / `triggered`(已触发) / `missed`(已错过) / `verified`(已验证) | — |
| `aShareTracking` | A股专检嵌套对象，每项含 `lastChecked` + `result` | — |
| `reviewSchedule.lastCheck` | 最近一次审查日期 | `"2026-05-28"` |

### 2. 支柱设计规则

**好支柱 vs 坏支柱**：

| 坏支柱 | 好支柱 |
|--------|--------|
| 「CIPB 会成功」 | 「2026 年 H1 无液氦产品收入 >1.5 亿」 |
| 「公司会增长」 | 「2026 年营收增速 >25%，毛利率环比改善」 |
| 「行业前景好」 | 「AI 服务器电源 TAM 在 2027 年前保持 >30% CAGR」 |

每个支柱必须有：可量化的期望值 + 明确的验证时间点 + 当前状态（pending/on_track/behind/broken）

### 3. 更新流程（每次追踪时）

**Step 0 — 过滤暂停标的**：遍历 `memory/tracking/` 下所有 JSON 文件，跳过 `track_status` 为 `"paused"` 的标的。仅对 `track_status` 为 `"active"` 的标的执行后续 Step A-G。

---

#### Step A — 拉取最新行情

```bash
python data_helper.py valuation <code>     # 取当前 PE/PB/市值/GM
```

取最近交易日数据，计算：
- `return_pct = (最新市值 - baseMarketCap) / baseMarketCap × 100`
- `mv_change_pct` 同上
- 对比 priceLog 上一条，计算单日变化

---

#### Step B — 更新价格日志

对每个 active 标的，追加一条 priceLog：

```json
{"date": "2026-06-10", "price": 68.5, "pe": 70.2, "mv_yi": 282.1, "return_pct": 8.4, "mv_change_pct": 8.3, "note": "巡检。简要说明当日变化。"}
```

---

#### Step C — 更新支柱状态（逐柱操作）

对每个 pillar 执行以下三项操作，**一项不可少**：

| 操作 | JSON 字段 | 说明 |
|------|----------|------|
| **C1. 追加 history** | `pillars[].history` | 新增一条 `{date, actual, trend}`。`actual` 写当前实际数据，`trend` 取 `up`/`flat`/`down` |
| **C2. 重评 status** | `pillars[].status` | 对照最新数据判断：`on_track`（达标或超前）、`pending`（数据不足）、`at_risk`（偏离目标） |
| **C3. 更新 lastChecked** | `pillars[].lastChecked` | 设为巡检日期 |

**status 判定标准**：

| 条件 | status |
|------|:---:|
| quantifiedTarget 已达成，或趋势明确向好且距 deadline 尚远 | `on_track` |
| 无新增数据，或距 verificationDate 尚远 | `pending` |
| 趋势恶化、或距 deadline 不足 1 月且未达标、或出现负面催化剂 | `at_risk` |
| quantifiedTarget 已实现且经公告/财报确认 | `verified` |

---

#### Step D — 更新催化剂日历（逐条操作）

对每条 catalyst 执行：

| 操作 | JSON 字段 | 说明 |
|------|----------|------|
| **D1. 标记已触发的** | `catalystCalendar[].status` | `pending` → `triggered`（事件已发生）或 `missed`（窗口期已过未发生） |
| **D2. 添加新发现的** | `catalystCalendar[]` | 新增事件，含 date/event/type/impact/bull/bear/sourceLevel/sourceDetail/status |
| **D3. 更新 lastChecked** | `catalystCalendar[].lastChecked` | 设为巡检日期 |

**触发判定**：如果催化剂的事件已经实际发生（如"6/8 新规发布"、"Q1 GM 公布"），将 status 从 `pending` 改为 `triggered`。

---

#### Step E — 更新 thesisLog

追加一条论点版本记录：

```json
{
  "version": <上一条+1>,
  "date": "<巡检时间ISO>",
  "thesis": "<当前thesis原文>",
  "conviction": <当前conviction>,
  "delta": "<本轮巡检发现的关键变化，1-2句话>",
  "trigger": "每日巡检",
  "narrative": "<delta 同内容>",
  "verifiedAssumptions": ["<本轮确认的假设>"],
  "invalidatedAssumptions": ["<本轮推翻的假设>"],
  "newUnknowns": ["<本轮新增的不确定性>"],
  "narrativeTension": "<rising|stable|easing|breaking>"
}
```

**narrativeTension 判定**：基于支柱分布自动判断

| 条件 | tension |
|------|:---:|
| 全部 on_track/verified，无非 pending | `rising` |
| on_track 占多数，1-2 个 pending | `stable` |
| 出现 1 个 at_risk | `easing` |
| ≥2 个 at_risk 或 1 个 broken | `breaking` |

---

#### Step F — 输出论点评分卡

对每个 active 标的输出表格：

```
| Pillar | 期望 | 实际 | 状态 | 趋势 |
|--------|------|------|:---:|:---:|
| 支柱名 | quantifiedTarget | history最新条actual | on_track/at_risk/pending | ↑/→/↓ |
```

**行动建议**（逐标的）：
- 维持 → 论点完好，继续持有/等待
- 加仓 → 论点强化 + 催化剂正面
- 减仓 → 某个支柱弱化但论点尚未破裂
- 清仓 → 核心支柱 broken 或 exit condition 触发

---

#### Step G — 同步 Coze（强制·不可跳过）

**每个标的执行完 A-F 后立即同步，不同步 = 巡检白做。**

```bash
cd D:\长流水\.agents\agents\shenwaihuashen && python sync_coze.py "memory/tracking/{stockCode}-{stockName}.json"
```

> Coze 表 ID: `7645332166129287218`。前端读取 Coze，不同步 = 前端看不到巡检结果。

---

#### 巡检自检矩阵（写入巡检报告末尾·硬闸门）

```
## 巡检自检
| # | 步骤 | 状态 | 备注 |
|---|------|:---:|------|
| A | 拉取最新行情 | ✅ | python data_helper.py valuation × N codes |
| B | 更新 priceLog | ✅ | N active stocks, 各追加 1 条 |
| C | 支柱 history + status 重评 | ✅ | C1/C2/C3 三项，N 条 status 变更 |
| D | 催化剂触发 + 新增 | ✅ | N 条触发，N 条新增 |
| E | 更新 thesisLog + tension | ✅ | N stocks, tension 基于支柱分布 |
| F | 论点评分卡 + 行动建议 | ✅ | 见上表 |
| G | 同步 Coze | ✅ | N/N sync_coze.py 全部 OK |
```

**矩阵缺任一项 → 巡检未完成，不得结束。**

### 4. 论点审查（每季度）

**核心问题**：我的论点还成立吗？

审查清单：
- [ ] 每个 pillar 的状态更新了吗？
- [ ] 有新的数据点可能推翻某个 pillar 吗？
- [ ] 退出条件是否仍然合理？（市场环境可能已变）
- [ ] 催化剂日历是否需要调整？
- [ ] 仓位是否仍符合风控铁律（≤20%）？

### 5. A 股特有追踪项

| 追踪项 | 频率 | 数据源 |
|--------|------|--------|
| 大股东质押率 | 每月 | investoday pledge-details |
| 限售解禁 | 每季 | tushare share_float |
| 两融余额异常 | 每月 | tushare margin |
| 业绩预告/快报 | 随公告 | 公司公告 + WebSearch |
| 机构调研 | 随公告 | WebSearch |
| 股东户数变化 | 每季 | tushare `stk_holdernumber` |

## 质量检查

- [ ] 论点是一句话且可证伪
- [ ] 每个 pillar 有可量化的期望值
- [ ] 至少有 1 个明确的退出条件
- [ ] A 股特有追踪项已纳入 review schedule
