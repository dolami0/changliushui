# 外部 API 与搜索模组

> 长流水项目所有外部 API 集成、搜索模组、数据源的完整规范

---

## 一、全景图

```
                        ┌──────────────────────┐
                        │    长流水 估值引擎    │
                        └──────────┬───────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
   │  LLM 服务    │         │  金融数据    │         │  搜索/联网   │
   ├─────────────┤         ├─────────────┤         ├─────────────┤
   │ DeepSeek    │         │ investoday  │         │ 火山引擎    │
   │  v4-pro     │         │ Tushare Pro │         │ Bocha       │
   │  v4-flash   │         │ 新浪行情    │         │ (搜索+URL)  │
   └─────────────┘         └─────────────┘         └─────────────┘
                                   │                        │
                                   ▼                        ▼
                            ┌─────────────┐         ┌─────────────┐
                            │  存储/平台   │         │  辅助服务    │
                            ├─────────────┤         ├─────────────┤
                            │ Coze 云DB   │         │ Playwright  │
                            │ FastAPI     │         │ (Easter F10)│
                            │ 本地文件系统 │         │             │
                            └─────────────┘         └─────────────┘
```

---

## 二、DeepSeek LLM API

### 2.1 基本信息

| 项目 | 值 |
|------|-----|
| 端点 | `https://api.deepseek.com/chat/completions` |
| 备用端点 | `https://api.deepseek.com/v1/chat/completions` |
| 认证方式 | `Authorization: Bearer {DEEPSEEK_API_KEY}` |
| 超时 | 600s（标准调用）/ 300s（Coze tool-use 调用） |

### 2.2 模型参数

**deepseek-v4-pro**（核心推理模型）：

```json
{
  "model": "deepseek-v4-pro",
  "max_tokens": 40960,
  "temperature": 0.0,
  "stream": false,
  "thinking": {"type": "enabled"},
  "reasoning_effort": "high"
}
```

典型使用场景：Agent-2 统一路由、Agent-3 情景推导与评审、Baseline 投资地图、产业链 LLM-1/2。

变体：
- Agent-3 LLM-1: `temperature=0.1, reasoning_effort="max"`
- Agent-Baseline: `temperature=0.1, reasoning_effort="max", max_tokens=8192`

**deepseek-v4-flash**（轻量过滤模型）：

```json
{
  "model": "deepseek-v4-flash",
  "max_tokens": 4096,
  "temperature": 0.0,
  "stream": false,
  "thinking": {"type": "enabled"}
}
```

典型使用场景：PreScreen 预筛选、Coze 工作流节点、DreamLoop 审计。

### 2.3 调用封装

所有 Agent 通过 `valuation_utils.call_deepseek()` 统一调用（Coze 节点和产业链模块各自直接调用）。

```python
# valuation_utils.py — 标准化调用
def call_deepseek(
    system: str,
    user_message: str,
    max_tokens: int = 40960,
    temperature: float = 0,
    api_key: str | None = None,
    model: str = "deepseek-v4-pro",
    print_usage: bool = True,
) -> dict:
    """调用 DeepSeek API，自动解析 JSON 返回 dict"""
```

### 2.4 JSON 解析容错

`parse_json()` 实现 4 层容错：
1. 提取 Markdown 代码块中的 JSON（```json ... ```）
2. 嵌套括号匹配（从第一个 `{` 到配对的 `}`）
3. `rfind()` 二次尝试
4. `json_repair` 库兜底（修复未转义引号、尾逗号等）

### 2.5 Tool-Use 调用模式

产业链分析和 Coze 工作流使用 DeepSeek 的 Function Calling：
- 前 N-1 轮：传递 `tools` 参数，允许 LLM 调用搜索工具
- 最后一轮：不传 `tools`，强制输出最终 JSON
- V4 Flash 偶发 DSML 格式 tool_call，代码有专门解析逻辑
- 最后一轮若仍输出 DSML，追加"禁止使用工具"指令立即重试一次

---

## 三、investoday API（金融数据主源）

### 3.1 基本信息

| 项目 | 值 |
|------|-----|
| 调用方式 | `npx investoday-api` CLI（本地 Node 进程） |
| 认证 | 环境变量 `INVESTODAY_API_KEY` |
| 重试策略 | 指数退避，最多 3 次 |
| 超时 | 30s/次 |
| 缓存 | 单次运行内存缓存（相同参数不重复请求） |

### 3.2 调用方式

```
GET:  npx investoday-api <path> key=value ...
POST: npx investoday-api <path> --method POST key=value ...
```

底层通过 `subprocess.run()` 调用 Node.js 脚本：
```
node_modules/@investoday/investoday-api/bin/investoday-api.js
```

### 3.3 40+ 端点分类

#### P0 优先级 — 公司基本面（10 个端点）

| 端点 | 方法 | 关键返回字段 |
|------|------|-------------|
| `stock-quote/realtime` | GET | current_price, market_cap, turnover_rate, industry_name |
| `stock/finance/valuation` | GET | pe_ttm, pb, ps_ttm, peg, ev_ebitda, cape, price_fcf + 行业/历史排名 |
| `stock/income-statements-ttm` | POST | revenue_ttm, net_profit_ttm, eps, operating_profit |
| `stock/balance-sheets-ttm` | POST | total_assets, cash, receivables, inventory, debt, equity |
| `stock/cash-flows-ttm` | POST | operating_cf, capex, fcf, investing_cf, financing_cf |
| `stock/dupont-analysis` | POST | roe, net_margin, asset_turnover, equity_multiplier |
| `stock/industries` | POST | sw_l1/l2/l3 申万行业分类 |
| `stock/score` | GET | 综合/财务/情绪/行业/技术面得分 |
| `stock/operating-reviews` | GET | 管理层经营评述全文 |
| `stock/fin-der-inds` | POST | roic, ebit, ebitda, gross_margin, net_margin, interest_coverage |
| `stock/finance/profit-ability` | GET | gross_margin/roe/roa/roic/roce 含行业+历史排名 |

#### P1 优先级 — 行业与可比/市场状态（7 个端点）

| 端点 | 关键返回字段 |
|------|-------------|
| `industry-quote/realtime` | 行业指数、涨跌幅、成分股、领涨股 |
| `industry/forecasts` | 行业净利润增速 T~T+3、营收增速 |
| `stock/fin-ind-sw-rnk-q` | 行业内 ROE/ROA/毛利率/净利率排名 |
| `stock-quote/capital-flow` | 主力/超大单/大单净流入 |
| `economic/gover-bond-yield` | 3M/6M/2Y/10Y/30Y 国债收益率 |
| `economic/money-supplies` | M1/M2 同比、M1-M2 剪刀差 |
| `economic/social-financing-sto` | 社融存量同比 |

#### P2 优先级 — 催化路径/一致预期/其他（6+ 端点）

| 端点 | 关键返回字段 |
|------|-------------|
| `stock/report-schema` | 财报披露日程 |
| `report/stock-forecast-ratings` | 分析师 EPS/净利预测、目标价、评级、修正趋势 |
| `stock/major-contracts` | 重大合同（金额/对手方/进展） |
| `stock/arbitration-cases` | 诉讼仲裁 |
| `stock/violation-penalties` | 违规处罚 |
| `report/research` | 券商研究报告 |
| `stock/consultations` | 互动问答（含传闻核实） |
| `stock/business-investment-themes` | 主营/投资主题/产业链/技术路线/前景 |
| `stock/investment-risks` | 竞争/经营/项目/宏观风险 |

#### 产业链利润流（3 个端点）

| 端点 | 关键返回字段 |
|------|-------------|
| `chain/industry-info` | 产业链行业分类体系 |
| `chain/pro-relation` | 产品上下游关系 (M/P/A/T/D) |
| `chain/pro-ind-maps` | 公司主营产品→产业图谱映射 |

#### 辅助端点

| 端点 | 用途 |
|------|------|
| `stock/adjusted-quotes` | 个股前复权日行情（Beta 计算、股价窗口） |
| `index/quotes` | 指数日行情（CSI 300，Beta 计算） |
| `stock/val-indicators` | 历史 PE/PB/PS 序列（分位计算） |
| `stock/dividends` | 分红历史（可持续 ROE、DDM） |
| `industry/market-stats` | 行业 PE/PB/PS 5 年分位 |
| `stock/income-statements-q` | 单季度利润表（拐点判断） |
| `stock/finance/valuation` | 个股 PE/PS/PB 行业排名和历史分位 |
| `chain/com-main-pro` | 主营产品收入/利润拆分（SOTP 分部估值） |

### 3.4 数值处理规则

`DataFetcher` 对 investoday API 返回值做规范化处理：

- `_num()`: `None`/空→`None`，否则→`float`
- `_pct()`: 原值 < 1 → 乘以 100（假设原值是小数），否则保持不变
- `_rank()`: 0=最高位（从未更贵），50=中位，100=最低位（从未更便宜）
- ROIC 特殊处理：原值 < 10 → 视为小数需要 ×100
- 毛利率/净利率特殊处理：绝对值 > 1 → 已是百分比，否则 ×100

---

## 四、Tushare Pro API

### 4.1 基本信息

| 项目 | 值 |
|------|-----|
| SDK | `tushare` Python 包 |
| 认证 | `ts.pro_api(TUSHARE_TOKEN)` |
| 速率限制 | 0.3s 间隔（`time.sleep(0.3)`） |
| 代码格式 | `{code}.SH` / `{code}.SZ` |

### 4.2 10 个端点

| 端点 | 用途 | 单位转换 |
|------|------|---------|
| `daily` | 日线行情（close/volume） | — |
| `daily_basic` | 日线指标（total_mv/pe_ttm/pb/turnover_rate） | 市值万→亿 ×1e-4，股本万→亿 ×1e-4 |
| `income` | 利润表（revenue/op_profit/net_profit） | 元→亿 /1e8 |
| `balancesheet` | 资产负债表 | 元→亿 /1e8 |
| `cashflow` | 现金流量表 | 元→亿 /1e8 |
| `fina_indicator` | 财务指标（roe/roa/gm/nm/debt_ratio） | 小数→% ×100 |
| `fina_mainbz` | 主营构成（产品级收入/利润/毛利率） | 元→亿 /1e8 |
| `forecast` | 业绩预告 | — |
| `express` | 业绩快报 | — |
| `stk_holdernumber` | 股东户数（筹码集中度趋势） | — |

### 4.3 交叉验证项

Agent-1 对 investoday 和 Tushare 数据做 8 项交叉验证：

| 验证项 | investoday 来源 | Tushare 来源 | 容差 |
|--------|----------------|-------------|------|
| 毛利率 | `fin-der-inds.gross_margin` | `fina_indicator.grossprofit_margin` | ±3pp |
| 净利率 | `fin-der-inds.net_margin` | `fina_indicator.netprofit_margin` | ±3pp |
| ROE | `dupont.roe` | `fina_indicator.roe` | ±3pp |
| ROIC | `fin-der-inds.roic` | —（仅 investoday） | — |
| EPS | `income-ttm.eps` | —（仅 investoday） | — |
| 资产负债率 | `balance-ttm` 计算 | `fina_indicator.debt_to_assets` | ±5pp |
| 营收 TTM | `income-ttm.revenue_ttm` | `income.total_revenue`（最新期） | ±10% |
| 经营现金流 | `cashflow-ttm.operating_cf` | `cashflow`（最新期） | ±20% |

### 4.4 代码校验（产业链分析用）

`IndustryChainWorkflow._resolve_stock_codes()` 使用 Tushare `stock_basic` 全量 A 股名称索引，4 级匹配：
1. **精确名称匹配**：`df['name'] == name`
2. **名称包含匹配**：按名称长度排序取最短
3. **核心词匹配**：去除地名/公司后缀后模糊匹配
4. **关键词匹配**：最后 2-4 字符匹配

含 3 次重试，失败时返回空代码（不阻塞管线）。

---

## 五、火山引擎 Agent API（联网搜索）

### 5.1 基本信息

| 项目 | 值 |
|------|-----|
| 端点 | `https://open.feedcoopapi.com/agent_api/agent/chat/completion` |
| Bot ID | `7640524154441156122` |
| 认证 | `Authorization: Bearer {VOLC_AGENT_KEY}` |
| 超时 | 60-90s |

### 5.2 使用场景

1. **产业链分析 — 轻搜**：2 次并行调用（产业链结构+利润截留 | TAM+进入壁垒）
2. **产业链分析 — 深搜**：每节点 1 次调用（利润/竞争/壁垒/TAM 4 维度）
3. **产业链分析 — 个股投资地图**：每只候选股 1 次调用（主营匹配/竞争壁垒/近期催化/差异化）
4. **Agent-3 LLM-2 搜索**：通过 `agent3s_sotp._call_volc()` 间接调用

### 5.3 请求格式

```json
{
  "bot_id": "7640524154441156122",
  "stream": false,
  "messages": [{"role": "user", "content": "<搜索查询>"}],
  "auto_extract": true
}
```

### 5.4 搜索策略特点

- 使用 Volc Agent 的结构化搜索而非原生搜索引擎——返回的是 Agent 综合后的结构化报告而非原始网页列表
- 信息密度高，但耗时长（60-90s），不适合高频场景
- 每次查询前 500 字符为事件上下文（截断防止 token 爆炸）

---

## 六、Bocha 搜索 API

### 6.1 基本信息

| 项目 | 值 |
|------|-----|
| 端点 | `https://api.bochaai.com/v1/web-search` |
| 认证 | `Authorization: Bearer {BOCHA_KEY}` |
| 用途 | A 股实时信息搜索、URL 全文抓取 |

### 6.2 两个工具函数

定义在 `src/agents/tools.py`：

```python
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "bocha_search",
            "description": "搜索A股实时信息",
            "parameters": {"query": "搜索关键词"}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "读取URL全文（HTML→纯文本）",
            "parameters": {"url": "目标URL"}
        }
    }
]
```

### 6.3 使用场景

- **产业链分析 LLM-1**：在信息不足或摘要太短（<300 字）时，LLM 自主调用 `fetch_url` 读取原文（最多 2 个 URL）
- **Agent-3 LLM-2**：最多 3 轮多轮对话，每轮最多 2 次并行搜索
- **Coze 工作流 N2-N6**：每个探针最多 2 次 `bocha_search`

### 6.4 硬编码位置

Coze 工作流节点 `n3_field_probes.py` 中硬编码了 Bocha Key：
```python
BOCHA_KEY = "sk-090c432b4f5745caa8767ae70f5b348b"
```
> 重构时建议统一从环境变量读取。

---

## 七、Coze 云数据库 API

### 7.1 基本信息

| 项目 | 值 |
|------|-----|
| 端点 | `https://api.coze.cn/v1/databases` |
| 认证 | `Authorization: Bearer {COZE_SAT_TOKEN}` |
| 操作 | POST（创建记录）、PUT（更新记录） |

### 7.2 数据库写入操作

**万业谱写入**（`n9_writer.py`）：
```python
POST https://api.coze.cn/v1/databases/{DB_WANYEPU}/records
```
14 个字段：stock_code, stock_name, event_date, event_source, raw_event_text, response_level, preliminary_reasoning, industry_expert_research, adversarial_thinking, investment_theme, future, event_deduction, knowledge_supplement, uuid, source_record_id, is_complete, created_at

每个字段截断限制：10000-15000 字符。

**天机卷标记**（`n9_writer.py`）：
```python
PUT https://api.coze.cn/v1/databases/{DB_TIANJI}/records/{record_id}
```
设置 `is_analyzed=true`。

---

## 八、新浪行情 API（股票代码验证）

### 8.1 基本信息

| 项目 | 值 |
|------|-----|
| 行情端点 | `http://hq.sinajs.cn/list={code}` |
| 建议端点 | `http://suggest3.sinajs.cn/suggest/` |
| 用途 | Coze N0 节点股票代码验证 |

### 8.2 使用方式

N0 节点（`n0_stock_validator.py`）使用新浪 API 验证用户输入的股票代码是否真实存在：

- 精确代码查询：`hq.sinajs.cn/list=sh{code},sz{code}`
- 模糊名称搜索：`suggest3.sinajs.cn/suggest/name={keyword}`
- 支持 A 股（沪市/深市）代码和名称验证
- 输出：`is_valid`, `verified_name`, `stock_code`, `stock_market`

---

## 九、Playwright（东方财富 F10 数据）

### 9.1 基本信息

| 项目 | 值 |
|------|-----|
| 工具名 | `playwright_jyps` |
| 用途 | 读取东方财富 F10 经营评述 |
| 定义位置 | `src/agents/tools.py` |

### 9.2 使用方式

```python
def playwright_jyps(url: str) -> str:
    """用 Playwright 打开东方财富 F10 页面，提取经营评述文本"""
```

仅用于 Agent-3 LLM-2 的深度研究场景（SOTP 管线），非标准管线必需。

---

## 十、搜索模组汇总

| 模组 | 类型 | 返回格式 | 延迟 | 适用场景 |
|------|------|---------|------|---------|
| 火山引擎 Agent | 结构化 Agent 搜索 | Markdown 报告 | 60-90s | 产业链深度分析、个股投资地图 |
| Bocha Search | 传统搜索引擎 | 网页摘要列表 | 3-10s | A 股实时信息、Coze 探针、事件验证 |
| Bocha fetch_url | URL 全文抓取 | 纯文本 | 5-15s | 关键来源全文阅读（数字/详情核实） |
| Playwright | 浏览器自动化 | 页面文本 | 10-30s | 东方财富 F10 经营评述 |

---

## 十一、API 故障降级策略

| 服务 | 故障处理 | 影响范围 |
|------|---------|---------|
| DeepSeek | Agent-2: 代码 Fallback（纯规则路由）；Agent-3: LLM-1 代码修正模式 | 估值质量下降，但不阻塞 |
| investoday | E101 核心数据不可用→终止；其他→部分数据缺失 | 数据质量评分反映 |
| Tushare | 交叉验证缺失，仅 investoday 单源 | 无交叉验证标记 |
| 火山引擎 | 搜索失败→跳过，LLM 使用自有知识 | 产业链/个股分析信息密度下降 |
| Bocha | 搜索失败→跳过，后续轮不再分配搜索 | 实时信息缺失 |
| Coze | 写入失败→本地文件兜底 | 不影响估值，语料不入库 |
