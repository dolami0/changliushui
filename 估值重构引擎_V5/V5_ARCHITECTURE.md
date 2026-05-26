# 估值重构引擎 V5 — 系统架构设计文档

> 版本: 2.1 (4Agent精简版)  
> 日期: 2026-05-19  
> 理论基础: 第一性原理 + 钱学森工程控制论  
> 输入源: Coze Agent0(预研语料) + investoday(财务/估值数据) + 火山引擎(联网搜索)

---

## 零、V4 诊断

### 0.1 系统本质

估值重构引擎是一个 **信息变换器**：

```
输入: 事件信号 + 公司财务状态 + 市场定价  (高熵)
  ↓  [4Agent信息变换]
输出: 概率加权估值 + 预期差 + 非对称评分 + 置信度 + 决策建议  (低熵)
```

### 0.2 V4 的结构性缺陷 → V5 解法

| 问题 | 根因 | V5解法 |
|------|------|--------|
| Agent2 1400行单文件 | LLM提示词+搜索+案例+10模型计算全耦合 | 拆为Agent-2(路由+搜索+案例)+Agent-3(推演+裁决) |
| 路由权责不清 | Agent1做路由，Agent2 prompt内嵌范式检查 | Agent-2是唯一路由判官，Agent-0只做数据采购 |
| BS检测器不一致 | DCF用`rf+β×ERP`，非DCF用`rf+7%` | Agent-3统一WACC，模型感知的BS检测方法 |
| LLM认知过载 | Agent2 340行system prompt | 每个Agent prompt单一职责 |
| 研究和估值耦合 | 搜索和参数估计在同一个tool-calling循环 | Agent-2前置搜索→Agent-3专注推演裁决 |
| 评测后置 | eval_mode flag改变生产流程 | 每层frozen数据注入，生产/评测代码一致 |
| Agent4/5无信息增量 | 反向DCF和非对称评分纯属变换计算 | 合并入Agent-3，LLM直接输出完整判决 |

---

## 一、总体架构

### 1.1 架构全景

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     估值重构引擎 V5 (Valuation Reconstruction Engine)         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────────┐    │
│  │ Agent-0  │   │ Agent-1  │   │ Agent-2  │   │      Agent-3         │    │
│  │ 预路由    │ → │ 数据炼器  │ → │ 路由判官  │ → │    推演裁决司命       │    │
│  │PreRouter │   │DataForge │   │RouteJudge│   │ScenarioAsymmetry    │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────────────────┘    │
│   规则引擎        工具调用        LLM+联网搜索      LLM(含计算)+代码校验      │
│   数据采购清单     分层API拉取     唯一路由权        三情景+反向DCF+BS检测     │
│                                 +案例匹配          +非对称评分+置信度+决策   │
│                                 +迁移路径          +KMI+叙事                │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    宗门中枢 (Orchestrator)                             │   │
│  │     状态机 + 缓存层 + 增量补取回退 + 分层评测 + 审计追踪 + 报告生成    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  外部接口: Coze Agent0 / investoday API / 火山引擎联网问答 / V3案例库       │
│  下游输出: Coze输出表 / JSON报告 / Markdown报告 / HTML报告 / 赔率排序       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Agent职责速查

| Agent | 代号 | 核心职责 | 承载方式 | 模型选择权 |
|-------|------|---------|---------|-----------|
| **Agent-0 预路由** | PreRouter | 基于规则生成数据需求清单(core/specialized/validation/optional) | 规则引擎，**无需LLM** | **否** |
| **Agent-1 数据炼器** | DataForge | 按清单分层拉取数据，标注缺失，输出数据包 | API调用，**无需LLM** | **否** |
| **Agent-2 路由判官** | RouteJudge | 独立执行三层路由+联网搜索+案例匹配+迁移路径预判 | LLM + 火山引擎联网 | **是（唯一）** |
| **Agent-3 推演裁决司命** | ScenarioAsymmetry | 三情景估值+反向DCF+BS检测+非对称评分+置信度+交易标注+KMI+叙事 | LLM(含计算) + 代码校验 | **否** |

### 1.3 核心架构原则

> **原则1: 采购员不判案**
> Agent-0只生成数据采购清单，无权决定primary_model。Agent-2基于完整数据独立判决，不受Agent-0 hint影响。

> **原则2: 分层失败不崩溃**
> core_package失败→终止流程(E101)；specialized/validation失败→增量补取或降级处理。

> **原则3: 闭环校验**
> Agent-2的增量补取频率反向度量Agent-0映射表准确率。

> **原则4: 前置搜索、后置推演裁决**
> Agent-2前置完成联网搜索+案例匹配，补齐信息。Agent-3接收完整上下文后一次完成推演+裁决。现代LLM有足够计算能力，参数估计和估值计算无需代码再画蛇添足。

> **原则5: 评测嵌入每层**
> 每层输入可来自frozen数据(评测集预存)或上游实时输出。生产和评测代码一致，无需eval_mode flag。

---

## 二、Agent-0 预路由 (PreRouter)

### 2.1 设计理由

规则引擎而非LLM：毫秒级、零token成本、100%确定性、映射表可版本化管理。

### 2.2 规则映射表

#### 第一层：行业→数据包类型

| 行业分类 | specialized_package核心字段 |
|---------|---------------------------|
| 医药生物-创新药 | `pipeline_list`, `clinical_phase`, `peak_sales_estimate`, `pos_assumptions`, `net_cash` |
| 有色金属-能源金属 | `proven_reserves`, `probable_reserves`, `commodity_price`, `extraction_cost_rate`, `mine_life` |
| 电子-印制电路板 | `capacity_utilization`, `order_backlog`, `yield_rate`, `customer_concentration` |
| 计算机-软件开发 | `subscribers`, `arpu`, `cac`, `ltv`, `churn_rate` |
| 银行/保险 | `npl_ratio`, `net_interest_margin`, `capital_adequacy_ratio`, `roe_ttm` |
| 房地产/REITs | `nav_breakdown`, `rental_yield`, `occupancy_rate`, `debt_maturity_schedule` |
| 通用工商业 | `peer_median_pe`, `peer_median_ps`, `industry_cycle_position` |

#### 第二层：事件标签Boost

| 事件标签 | 追加字段 |
|---------|---------|
| `产能释放` | `capacity_expansion_plan`, `capex_breakdown`, `depreciation_schedule` |
| `借壳重组` | `control_change_event`, `injection_asset_description`, `shell_value_estimate` |
| `管线推进` | `clinical_trial_updates`, `competitive_pipeline_landscape` |
| `政策催化` | `policy_document_reference`, `subsidy_amount`, `tax_benefit_duration` |
| `困境反转` | `distress_recovery_timeline`, `asset_restructuring_plan`, `cash_burn_rate` |

### 2.3 输出Schema

```json
{
  "request_id": "req_20260519_001",
  "pre_routing_result": {
    "ticker": "300476.SZ",
    "industry_classification": "电子-印制电路板",
    "event_tags_matched": ["产能释放", "AI硬件"],

    "data_requirements": {
      "core_package": {
        "description": "所有估值模型通用，必须100%获取",
        "fields": ["current_price", "total_shares", "market_cap", "revenue_ttm",
                   "eps_ttm", "net_profit_growth_yoy", "bps", "roe_ttm",
                   "ocf_ttm", "capex_ttm", "net_debt", "total_assets", "total_liabilities"],
        "mandatory": true, "failure_action": "terminate"
      },
      "specialized_package": {
        "fields": ["capacity_utilization", "order_backlog", "yield_rate",
                   "capacity_expansion_plan", "capex_breakdown"],
        "mandatory": false, "failure_action": "continue_with_gap"
      },
      "validation_package": {
        "fields": ["peer_median_pe", "peer_median_ps", "historical_pe_range",
                   "beta", "wacc_estimate"],
        "mandatory": false, "failure_action": "skip_validation"
      },
      "optional_package": {
        "fields": ["dividend_yield", "segment_breakdown"],
        "mandatory": false, "failure_action": "ignore"
      }
    },

    "model_category_hint": ["Earnings Multiples"],
    "hint_confidence": "中",
    "warning": "【重要】本hint不决定最终模型。Agent-2将基于实际财务数据独立判决。"
  }
}
```

### 2.4 预路由错误容错

最坏情况不崩溃：Agent-1回退全量拉取，正确性由Agent-2保证。

---

## 三、Agent-1 数据炼器 (DataForge)

### 3.1 职责定义

接收Agent-0的data_requirements，**按包分层并行拉取**，输出结构化数据包。

底层复用V4的 `data_fetcher.py`（investoday CLI封装，14+端点），支持 `event_date` 参数实现评测"时间旅行"。

### 3.2 执行流程

```
Step 1: 接收 pre_routing_result.data_requirements
Step 2: 【并行】获取 core_package（必须100%成功）→ 失败返回E101
Step 3: 【并行】获取 specialized_package（允许部分缺失）
Step 4: 【并行】获取 validation_package（允许缺失）
Step 5: 【条件】获取 optional_package
Step 6: 输出数据包，按package分组，标注每个字段缺失状态
```

### 3.3 错误码

| 错误码 | 场景 | 处理 |
|--------|------|------|
| `E101` | core_package任一字段缺失 | **终止流程** |
| `E102` | 数据时间戳不一致 | 以最新数据为准 |
| `E103` | specialized全部缺失 | Agent-2用core做通用路由 |
| `E104` | 计算字段异常(除零等) | 返回null，不阻塞 |
| `E105` | API限流/超时 | 指数退避重试≤3次 |

---

## 四、Agent-2 路由判官 (RouteJudge)

### 4.1 职责定义

**Agent-2是系统中唯一拥有模型选择权的Agent。** 基于Agent-1完整数据包，独立执行三层路由 + 联网搜索 + V3案例匹配 + 迁移路径预判。**必须无视Agent-0的hint。**

### 4.2 执行流程

```
Step 1: 联网搜索（前置补齐信息）
  ├─ 通用搜索: 市场规模/TAM/竞争格局/风险/催化剂
  ├─ 模型专属搜索: F搜管线/H搜资产公允价/J搜分部收入
  └─ 工具: 火山引擎联网问答(tool-calling loop, 最多2轮)

Step 2: V3案例匹配（纯代码, case_loader.py）
  ├─ 7规则加权匹配: 行业+3/驱动+3/ROIC区间+2/ROIC接近+2/市值量级+2/估值范式+1/催化剂+1
  └─ 输出: Top8案例 + 锚点文本

Step 3: 三层路由决策（LLM, ≤1500 token）
  ├─ 第一层-业务本质 → model_category
  ├─ 第二层-盈利框架 → primary_model
  └─ 第三层-估值水位 → validation_models

Step 4: 冲突仲裁 → 规则1:业务优先 规则2:盈利否决 规则3:增速优先

Step 5: 迁移路径预判
  例: PEG(增速驱动期) → ROIC>10%且增速回落 → A_ROIC-RR(稳态复利)

Step 6: 增量补取检查
  若选定模型的关键字段缺失 → 触发增量补取 → Orchestrator回退Agent-1
```

### 4.3 联网搜索策略

Agent-2前置搜索，为自身路由和Agent-3推演提供充分上下文：

- **通用搜索**（所有标的）：分析Agent0语料覆盖，对缺少维度各生成1-2条精准query
- **模型专属搜索**（F/H/J触发）：rNPV搜管线+同类靶点；NAV搜公允价+可比交易；SOTP搜分部收入+可比倍数
- **最多2轮**，每轮≤3条query，每结果≤1000字

### 4.4 输出

```json
{
  "routing_decision": {
    "primary_model": "PEG(增长锚定)",
    "model_category": "盈利乘数",
    "validation_models": ["A_ROIC-RR(改善至稳态)", "正向DCF校验"],
    "routing_reason": "利润增速>50%, PEG=0.45<0.7, 产能利用率92%。触发规则3-增速优先。【基于数据独立判决，未参考hint】",

    "key_assumptions": {
      "primary": "净利润增速维持50%以上",
      "secondary": ["AI服务器PCB需求持续>2年", "良率维持>90%"]
    },

    "model_migration_path": {
      "current_phase": "PEG(增长锚定) — 阶段2-增速驱动期",
      "next_phase_trigger": "ROIC>10%且连续两季稳定 + 增速回落至15-25%",
      "next_phase_model": "A_ROIC-RR(稳态复利)",
      "time_horizon": "预计12-18个月"
    },

    "web_search_summary": {
      "searches_performed": 1,
      "key_findings": "全球AI服务器PCB市场2026年预计$12B, CAGR 35%"
    },

    "case_matches_top3": [
      {"case_code": "300502", "score": 13, "key_anchor": "ROIC改善+15ppt, PE扩张5.8x"}
    ],

    "incremental_fetch_request": {"triggered": false},
    "hint_rejection_note": "hint与判决一致。",
    "reverse_dcf_applicability": "适用"
  }
}
```

---

## 五、Agent-3 推演裁决司命 (ScenarioAsymmetry)

### 5.1 职责定义

**Agent-3是管线的最终产出层**，合并了V4的Agent-3(报告)+Agent-4(反向DCF)+Agent-5(裁决)的全部职责。

接收Agent-2路由判决+Agent-1数据包+联网搜索结果+案例锚点，**由LLM在一次调用中完成**：
- 三情景估值推演（参数估计+估值计算）
- BS检测（市场溢价判断）
- 反向DCF（市场隐含预期反推）
- 预期差计算
- 非对称评分
- 置信度校准
- 交易标注
- KMI生成
- 叙事

**LLM有足够的计算能力，参数估计和估值计算无需代码画蛇添足**——分离反而增加参数传递出错的风险。代码仅做：WACC预计算(注入prompt)、概率和校验、参数单调性校验。

### 5.2 输入

```json
{
  "request_id": "req_20260519_001",
  "data_package": { /* Agent-1 数据包 */ },
  "routing_decision": { /* Agent-2 路由判决 */ },
  "web_search_results": [ /* Agent-2 联网搜索结果 */ ],
  "case_anchors": { /* Agent-2 案例锚点 */ },
  "investment_map": { /* Agent0 投资地图 */ }
}
```

### 5.3 执行流程

```
Step 0: 预计算 (纯代码 → 注入LLM prompt) ★ 白盒先行
  ├─ WACC计算:
  │   rf = fetch_bond_yields().yield_10y
  │   beta = calculate_beta(stock_code)
  │   erp = calculate_erp()                     # 基准6% + 波动率调整
  │   re = rf + beta × erp
  │   rd = rf + 2.0 (仅当有息负债>0)
  │   wacc = re × E/V + rd × (1-t) × D/V
  │
  └─ BS画像预计算 (模型感知，基于Agent-2路由):
      A/C/I: reverse_DCF → implied_g → market_premium_pct
      G:     PEG = PE/增速 → PEG_label + premium_pct
      B:     PS_industry_rank → PS分位 → premium_pct
      D:     PB_industry_rank → PB分位 → premium_pct
      E:     PE_percentile → 分位对比 → premium_pct
      F/H/J: PB_baseline → PB vs 1.0 → premium_pct

      → BS画像是LLM推演的起点——告诉LLM"市场已经定价了什么"
      → LLM不可修改BS画像，但可在输出中补充解读
      → 控制论意义: BS画像是白盒计算的"参考信号"，LLM是黑盒"控制器"

Step 1: LLM综合推演裁决 (单次LLM调用, ≤3500 token prompt)
  Prompt包含（顺序即认知顺序）:
    1. BS画像 (代码预计算的事实——市场当前定价了什么)
    2. WACC参数 (rf/beta/erp/wacc已计算好，不可修改)
    3. 案例锚点 (历史十倍股参数范围——"参照系")
    4. 联网研究结果 (行业TAM/竞争/催化剂——"外部信息")
    5. Agent0投资地图 (事件推演/空头审查/未来催化)
    6. 模型特定参数模板 (取决于primary_model)
    7. 预计算参考矩阵 (ROIC/RR/PS/PB敏感性路径——"数值参考")

  LLM一次性输出完整JSON:
    ├─ scenario_valuation (三情景: base/bull/bear)
    ├─ probability_weighted (概率加权结果)
    ├─ reverse_dcf (反向DCF: 市场隐含g vs 推演隐含g → 预期差)
    ├─ asymmetry_judgment (非对称评分+置信度+交易标注)
    ├─ monitoring_kpis (KMI追踪框架)
    ├─ risk_triggers (风险触发器)
    └─ narrative (≤150字叙事)

  约束:
    ├─ LLM必须输出完整JSON，不能用markdown代码块包裹
    ├─ 三情景概率之和必须严格等于1.0
    ├─ 三情景参数必须逐级递增(bear<base<bull)，禁止相同数值
    └─ WACC/BS画像不可修改——它们是已知事实，不是假设

Step 2: 代码校验 (纯代码，不阻塞)
  ┌─ 概率和校验: |Σprob - 1.0| < 0.03？
  ├─ 单调性校验: bear_upside < base_upside < bull_upside？
  ├─ WACC一致性: LLM输出中是否擅自修改了WACC？
  ├─ BS一致性: LLM输出的bs_level与预计算的premium_pct是否方向一致？
  └─ 校验模型差: |validation_model_mcap - primary_model_mcap| / primary < 50%？
      └─ 不通过 → 标记warning，降置信度，不阻塞流程

Step 3: LLM故障处理
  ┌─ JSON解析失败 → 尝试截取{...}重解析
  ├─ 重解析失败 → 返回E301 + 原始文本，不阻塞
  ├─ API超时(>120s) → 重试1次，仍失败→E302
  ├─ API返回错误 → 重试1次，仍失败→E303
  └─ 任何故障 → Orchestrator写错误日志，标记该标的为"处理失败"
```

### 5.4 模型计算参考（嵌入LLM prompt，非强制）

PEG: `target_pe = 稳态增速% × justified_PEG` | `target_mcap = 净利×(1+g)³ × target_pe`

ROIC-RR: `g = ROIC×RR` | `EV = Σ NOPAT×(1+g)ⁿ/(1+wacc)ⁿ + TV`

PS+TAM: `target_mcap = revenue×(1+g)³ × tam_adjustment × target_ps`

rNPV: `value = Σ(峰值销售 × 净利率 × PE × PoS / (1+r)^n) + net_cash`

### 5.5 输出Schema (对应V4 Coze输出表 + JSON报告)

```json
{
  "request_id": "req_20260519_001",
  "status": "complete",

  "report_meta": {
    "stock_code": "300476",
    "stock_name": "胜宏科技",
    "industry": "元器件",
    "report_date": "2026-05-19T22:05:00+08:00",
    "version": "5.0"
  },

  "valuation_routing": {
    "primary_model": "PEG(增长锚定)",
    "secondary_model": "A_ROIC-RR",
    "model_category": "盈利乘数",
    "routing_reason": "利润增速>50%, PEG=0.45<0.7",
    "method_used": "PEG增长锚定",
    "model_migration_path": { /* Agent-2迁移路径 */ }
  },

  "market_sanity": {
    "bs_method": "PEG",
    "bs_level": "折价:市场定价低于当前盈利能力",
    "ev_billion": 155.0,
    "nopat_billion": 7.2,
    "roic_pct": 22.0,
    "wacc_simple_pct": 10.5,
    "implied_g_pct": 8.5,
    "market_premium_pct": -55,
    "pe_ttm": 22.6,
    "pb": 3.2,
    "pe_historical_rank": 35,
    "wacc_params": {
      "rf_pct": 1.75, "beta": 1.35, "erp_pct": 6.5,
      "re_pct": 10.5, "rd_pct": 3.75, "d_ratio_pct": 0
    },
    "warnings": [],
    "market_story": "PEG=0.45, 增速未被充分定价, 折价55%"
  },

  "scenario_valuation": {
    "scenario_details": {
      "base": {
        "probability": 0.50,
        "roic_assumed_pct": 55, "rr_assumed_pct": "—",
        "pe_target": 55, "revenue_growth_pct": 55,
        "target_mcap_billion": 280, "upside_pct": 76,
        "valuation_method": "PEG增长锚定"
      },
      "bull": {
        "probability": 0.30,
        "roic_assumed_pct": 80, "pe_target": 104,
        "target_mcap_billion": 540, "upside_pct": 240,
        "valuation_method": "PEG增长锚定"
      },
      "bear": {
        "probability": 0.20,
        "roic_assumed_pct": 20, "pe_target": 16,
        "target_mcap_billion": 85, "upside_pct": -47,
        "valuation_method": "PEG增长锚定"
      }
    },
    "probability_weighted_mcap_billion": 280,
    "probability_weighted_upside_pct": 76,
    "asymmetry_ratio": 3.2,
    "quality_flag": "HIGH_QUALITY"
  },

  "reverse_dcf": {
    "applicability": "适用",
    "market_implied_g_pct": 8.5,
    "my_implied_g_pct": 15.0,
    "expectation_gap_pct": 6.5,
    "gap_direction": "市场低估",
    "gap_magnitude": "显著"
  },

  "expectation_gap": {
    "level": "显著正向预期差",
    "note": "事件可能带来的价值改善远超市场当前定价所隐含的水平",
    "valuation_model": "路由PEG(增长锚定)→PEG增长锚定",
    "probability_weighted_upside": "+76.0%"
  },

  "confidence": {
    "overall_score": 7,
    "overall_label": "高",
    "dimensions": {
      "info_quality": {"score": 8, "label": "信息质量", "note": "Q1订单环比大幅增长已确认"},
      "financial_feasibility": {"score": 8, "label": "财务可行性", "note": "净现金5亿, OCF=6.2亿"},
      "valuation_safety": {"score": 6, "label": "估值安全边际", "note": "PE=22.6x(分位35), ROIC=22.0% vs WACC=10.5%"},
      "historical_precedent": {"score": 7, "label": "历史案例匹配", "note": "匹配3个相似案例"}
    }
  },

  "trade_annotation": {
    "tier": "★★★ 高赔率机会",
    "total_score": "8/10",
    "dimension_scores": {
      "odds_quality": 3,
      "pricing_headroom": 2,
      "transmission_confidence": 2,
      "model_consistency": 1
    },
    "alignment_signals": [
      "优秀赔率: 概率加权涨幅76%, 不对称比3.2, 等级HIGH_QUALITY",
      "市场显著未定价: 折价55%, PE处35分位",
      "传导链确定性高: 订单已确认,产能爬坡可跟踪"
    ],
    "tier_note": "多信号高度对齐。赔率优秀+市场未充分定价+事件传导确定。",
    "suggested_action": "建议深度研究后纳入核心持仓。跟踪KMI,若bear_trigger触发则重新评估。"
  },

  "monitoring_kpis": {
    "financial_verification_kpis": [
      {"name": "季度营收同比增速", "baseline": "当前68%", "target": "维持>50%",
       "frequency": "季度", "verifies": "事件→收入传导"}
    ],
    "event_milestone_kpis": [
      {"name": "Q3新产能投产", "expected_timing": "Q3", "significance": "验证产能释放逻辑",
       "verification_source": "公司公告/季报"}
    ],
    "competition_signal_kpis": [
      {"name": "行业新进入者产能扩张", "current_state": "胜宏份额~15%",
       "trigger": "新进入者份额>5%", "action_if_triggered": "重新评估竞争格局"}
    ],
    "risk_trigger_kpis": [
      {"name": "AI需求是否提前见顶", "linked_to": "关键假设: AI需求持续>2年",
       "severity": "high", "monitor": "北美云厂商Capex指引"}
    ]
  },

  "risk_triggers": {
    "bull_trigger": "Q2财报营收增速>80%, 新客户突破",
    "bear_trigger": "Q2营收增速<30%, 或大客户流失",
    "monitoring_frequency": "季度(与财报同步验证)"
  },

  "narrative": "胜宏科技: AI服务器PCB放量驱动利润增速>50%, PEG=0.45处于戴维斯双击击球区。主要风险: AI需求持续性存疑,竞争格局变化可能压缩利润率。",

  "case_comparison_summary": {
    "compared_cases": [
      {"case_code": "300502", "comprehensive_discount_pct": 75,
       "six_dimension_judgment": {"driver_strength": "优于", "market_space": "相似"}}
    ]
  }
}
```

### 5.6 输出到下游系统

Agent-3的输出直接映射到V4兼容的下游消费：

#### Coze输出表 (20字段)

| Coze字段 | Agent-3来源路径 |
|---------|---------------|
| `stock_code` | report_meta.stock_code |
| `stock_name` | report_meta.stock_name |
| `event_date` | Agent0输入透传 |
| `event_source` | Agent0输入透传 |
| `primary_model` | valuation_routing.primary_model |
| `prob_weighted_upside_pct` | scenario_valuation.probability_weighted_upside_pct |
| `asymmetry_ratio` | scenario_valuation.asymmetry_ratio |
| `quality_flag` | scenario_valuation.quality_flag |
| `current_mcap_billion` | Agent-1数据包 market_cap |
| `prob_weighted_mcap_billion` | scenario_valuation.probability_weighted_mcap_billion |
| `bear_prob` / `base_prob` / `bull_prob` | scenario_valuation.scenario_details.{name}.probability |
| `bear_upside_pct` / `base_upside_pct` / `bull_upside_pct` | scenario_valuation.scenario_details.{name}.upside_pct |
| `confidence_score` | confidence.overall_score |
| `trade_tier` | trade_annotation.tier |
| `report_html_url` | Orchestrator生成 |
| `processed_at` | Orchestrator时间戳 |

#### JSON报告

完整Agent-3输出 + Agent-0/1/2产出，存入 `reports/data/{stock_code}.json`，供前端React报告页使用。

#### Markdown报告

由 `report_builder.build_markdown_report()` 生成，存入 `reports/{stock_code}.md`。

#### HTML报告

由 `report_builder.build_html_report()` 生成，CSS内联单文件自包含，存入 `reports/html/{stock_code}.html`。

### 5.7 错误码

| 错误码 | 场景 | 处理 |
|--------|------|------|
| `E301` | LLM输出JSON解析失败 | 尝试截取`{...}`重解析，仍失败→返回E301+原始文本，标记处理失败 |
| `E302` | LLM调用超时(>120s) | 重试1次 |
| `E303` | LLM API返回错误 | 重试1次 |
| `E304` | 概率和偏离>0.03 | 标记warning，降置信度一档 |
| `E305` | 参数单调性违反 | 标记warning |
| `E306` | 校验模型偏差>50% | 标记warning，降置信度一档 |
| `E307` | LLM擅自修改WACC/BS画像 | 标记warning，以代码预计算值为准 |

---

## 六、宗门中枢 (Orchestrator)

### 6.1 状态机（含故障路径）

```
[INIT] → 接收请求(stock_code + event_data)
  ↓
[PRE_ROUTER] → Agent-0执行（规则引擎，毫秒级）
  ├─ 无匹配规则 → 回退全量拉取模式，跳过specialized优化
  └─ ↓
[DATA_FORGE] → Agent-1执行
  ├─ core_package失败 → E101，终止，标记"数据不可用"
  └─ success ↓
[ROUTE_JUDGE] → Agent-2执行
  ├─ DeepSeek API故障 → 重试1次 → 仍失败 → 使用fallback规则路由(纯代码)
  ├─ Volcengine API故障 → 跳过联网搜索，仅基于Agent0+案例库路由
  ├─ 增量补取触发 → 回退DATA_FORGE(仅补拉缺失字段，不复拉全部)
  │   └─ 补取完成后Agent-2从Step 3重新开始（不重复联网搜索）
  └─ success ↓
[SCENARIO_ASYMMETRY] → Agent-3执行
  ├─ DeepSeek API故障 → 重试1次 → 仍失败 → E302/E303，标记处理失败
  ├─ JSON解析失败 → E301，标记处理失败
  └─ success ↓ (warning不阻塞)
[COMPLETE] → 生成报告 + 审计日志 + 排序更新

关键: 增量补取回退时只补拉缺失字段，Agent-2不重复联网搜索（搜索结果已缓存）。
```

### 6.2 故障模式与扰动分析（工程控制论）

系统在以下扰动下的行为：

| 扰动源 | 影响范围 | 系统响应 | 是否崩溃 |
|--------|---------|---------|---------|
| investoday API故障 | Agent-1 | E105指数退避重试3次。仍失败→E101终止 | **是（预期内）** |
| DeepSeek API故障 | Agent-2, Agent-3 | Agent-2→fallback规则路由；Agent-3→重试1次，仍失败→标记失败 | **否** |
| 火山引擎API故障 | Agent-2 | 跳过联网搜索，路由质量降级但不阻塞 | **否** |
| Coze Agent0表无数据 | Agent-2 | investment_map全空，Agent-2仅基于财务数据路由 | **否** |
| LLM输出非JSON | Agent-2, Agent-3 | 截取`{...}`重解析；仍失败→Agent-2用fallback，Agent-3标记E301 | **否** |
| 三情景概率和≠1 | Agent-3 | E304 warning，不阻塞 | **否** |
| 增量补取死循环 | Agent-2↔Agent-1 | 最多1次回退。补取后仍缺失→Agent-2用fallback模型 | **否** |
| 缓存过期+API同时故障 | 全部 | 返回上次缓存结果+过期标记 | **否** |

核心设计原则：**唯一硬终止条件是core_package数据不可用（E101）。其他一切故障降级处理。**

### 6.3 缓存策略

| 缓存层级 | 内容 | TTL | 刷新触发 |
|---------|------|-----|---------|
| L0 预路由 | Agent-0输出 | 24h | 行业分类变更 |
| L1 数据包 | Agent-1输出 | 1h | 财报日/价格变动>5% |
| L2 路由 | Agent-2输出 | 24h | 财务重大变化/增量补取后 |
| L3 裁决 | Agent-3输出 | 1h | 任前序Agent刷新 |

### 6.4 评测模式

评测时Orchestrator从评测集注入frozen数据：

```
eval_mode下每层评测:
  输入 = frozen_upstream + 实时本层
  对比 = 本层输出 vs ground_truth (评测集标注)
  输出 = layer_score + 偏差分析

评测数据: evals/pipeline_eval_set.json (11条, 版本3.1)
评测入口: evals/eval_runner.py
```

### 6.5 闭环校验

```
pre_router_accuracy = 1 - (incremental_fetch_count / total_requests)
评测集verification数据 → 路由规则权重调优 + 置信度因子校准
```

---

## 七、与V4的接口兼容

### 7.1 输入兼容

V5完全兼容V4的Coze Agent0输入格式：

```
Coze Agent0表字段 → V5映射:
  stock_code, stock_name           → Agent-0 ticker
  raw_event_text                   → Agent-2 事件原文(联网搜索上下文)
  event_deduction                  → Agent-2 事件推演框架
  investment_theme                 → Agent-2 投资主题
  adversarial_thinking             → Agent-2 空头审查
  preliminary_reasoning            → Agent-2 响应等级依据
  knowledge_supplement             → Agent-2 知识补充
  industry_expert_research         → Agent-2 行业研究
  future                           → Agent-2 未来催化节点
  response_level                   → Agent-2 L1-L5响应等级
  event_date, event_source         → 透传到输出
```

### 7.2 输出兼容

V5的Agent-3输出结构与V4的Agent3输出**字段级兼容**：

- `report_meta` / `valuation_routing` / `market_sanity` / `scenario_valuation` / `expectation_gap` / `confidence` / `trade_annotation` / `monitoring_kpis` / `risk_triggers` / `narrative` / `case_comparison_summary` — 全部保持与V4相同的字段名和结构
- V4的 `scheduler._write_result_to_coze()` 和 `report_builder` 无需修改即可消费V5输出

### 7.3 新增字段（向下兼容）

V5在V4基础上新增的字段，V4消费者忽略即可：

| 新增字段 | 路径 | 用途 |
|---------|------|------|
| `model_migration_path` | valuation_routing | 模型迁移路径预判 |
| `reverse_dcf` | 顶层 | 反向DCF完整报告 |
| `wacc_params` | market_sanity | WACC参数溯源(rf/beta/erp) |
| `routing_reason_hint_rejection` | valuation_routing | hint拒绝记录 |

---

### 8.1 开发文件（V5新建/重构）

```
估值重构引擎_V5/
├── src/
│   ├── env_config.py              # 密钥集中管理 (已有) ✓
│   ├── data_fetcher.py            # investoday API封装 (从V4迁移，不改)
│   ├── case_loader.py             # V3案例库加载器 (已有) ✓
│   │
│   ├── agent0_pre_router.py       # [新] 规则引擎: 行业映射+事件boost
│   ├── agent1_data_forge.py       # [新] 分层拉取+缺失标注+增量补取
│   ├── agent2_route_judge.py      # [新] 三层路由+联网搜索+案例匹配+迁移路径
│   ├── agent3_scenario_asymmetry.py # [新] LLM推演裁决(WACC/BS预计算+校验)
│   └── orchestrator.py            # [新] 状态机+缓存+增量补取回退+评测模式
│
├── evals/
│   ├── pipeline_eval_set.json     # 评测集 (已有) ✓
│   ├── eval_runner.py             # [新] 分层评测入口
│   ├── eval_reports/              # 评测报告输出
│   └── v3/
│       ├── valuation_routing_framework.md
│       └── case_library_v3.json
│
├── valuation_app/
│   ├── pipeline_runner.py         # 管线编排器 (重构为4Agent+Orchestrator)
│   ├── scheduler.py               # Coze轮询调度 (兼容V5输出)
│   ├── server.py                  # FastAPI服务 (兼容V5输出)
│   ├── report_builder.py          # HTML/MD报告生成 (兼容V5输出)
│   └── coze_client.py             # Coze API封装 (不变)
│
├── ranking/
│   └── ranking_engine.py          # 赔率排序器 (已有) ✓
│
├── reports/
│   ├── ranking/                   # 赔率排序输出
│   ├── data/                      # 结构化JSON报告
│   ├── html/                      # HTML报告
│   └── audit/                     # 审计追踪
│
├── config/
│   └── endpoint_mapping.yaml      # investoday API映射
│
├── .env.example
├── V5_ARCHITECTURE.md
└── valuation_reconstruction_engine_v1.1.md
```

### 8.2 不触碰文件（产业链分析模块，独立子系统）

以下文件属于产业链利润流分析子系统，V5开发**不读取、不修改、不重构**：

```
src/industry_chain_workflow.py          # 产业链LLM工作流
valuation_app/industry_chain_coze.py    # 产业链Coze数据表
valuation_app/industry_chain_scheduler.py # 产业链轮询调度
evals/industry_chain_eval.json          # 产业链评测数据
```

这些模块在 `server.py` 中已有独立 try/except 保护（注释: "产业链模块加载失败不影响主系统"），与估值重构主管线无耦合。V5重构 `pipeline_runner.py` 和 `scheduler.py` 时保持 `server.py` 中的产业链导入和API端点不变。

---

## 九、构建顺序与评测目标

```
Phase 1: 基础设施 (已就绪) ✓
  env_config.py / data_fetcher.py / case_loader.py / ranking_engine.py

Phase 2: Agent-0 + Agent-1 (2天)
  agent0_pre_router.py + agent1_data_forge.py + 联合测试

Phase 3: Agent-2 路由判官 (3天)
  agent2_route_judge.py + 增量补取闭环 + 路由准确度评测

Phase 4: Agent-3 推演裁决司命 (3天)
  agent3_scenario_asymmetry.py + LLM prompt工程 + 方向准确度+信心校准度评测

Phase 5: Orchestrator + 管线集成 (2天)
  orchestrator.py + pipeline_runner重构 + eval_runner + 端到端集成

Phase 6: 评测集验证 (2天)
  11条评测集全管线运行 + V4基线对比
```

| 评测指标 | 目标 |
|---------|------|
| Agent-0 增量补取率 | < 20% |
| Agent-2 路由准确度 vs V3标注 | ≥ 80% |
| Agent-2 案例匹配最高分 | ≥ 10/16 |
| Agent-3 方向准确度 | ≥ 60% |
| Agent-3 情景覆盖率 | ≥ 50% |
| Agent-3 信心校准度 | ≥ 50% |
| core_package成功率 | 100% |

---

## 十、工程控制论完整审视

### 10.1 系统控制论定位

估值重构引擎在控制论框架中的位置：

```
┌──────────────────────────────────────────────────────────┐
│                    控制装置 (Controller)                   │
│  Agent-0 → Agent-1 → Agent-2 → Agent-3                   │
│  规则引擎   数据采集   路由判决   推演裁决                   │
└────────────┬──────────────────────────────┬──────────────┘
             │ 控制信号                      │ 观测信号
             ▼                              ▼
┌────────────────────────┐    ┌────────────────────────────┐
│  执行器 (Actuator)      │    │  传感器 (Sensor)            │
│  输出: 估值报告+交易标注  │    │  输入: 事件信号+财务数据+   │
│  下游: 选股系统/仓位建议  │    │       市场定价+V3案例库     │
└────────────────────────┘    └────────────────────────────┘
```

### 10.2 开环 vs 闭环的诚实承认

**V5管线的单次执行是开环系统。** 每个Agent的输出单向流入下一个Agent，无实时反馈回路。这不是设计缺陷——"被估值的公司"在管线执行的95秒内不会变化，实时反馈对象不存在。

真正的反馈发生在两个时间尺度上：

| 时间尺度 | 反馈回路 | 作用 |
|---------|---------|------|
| **秒级** (单次执行内) | 无 | 不适用——被控对象不变 |
| **小时级** (增量补取) | Agent-2 → Agent-1 → Agent-2 | 纠正数据采购错误 |
| **日级** (预路由校准) | `pre_router_accuracy` → Agent-0映射表 | 优化数据采购效率 |
| **周/月级** (评测驱动) | verification数据 → 规则权重+置信度因子 | 优化决策质量 |
| **长期** (案例库进化) | 新案例入库 → Agent-2匹配空间扩大 | 扩展参照系 |

### 10.3 白盒/黑盒分离

```
Agent-0: 白盒 (规则映射表——完全可观测、可控制)
Agent-1: 白盒 (API调用——输入/输出确定)
Agent-2: 混合
  ├─ 白盒: case_loader 7规则匹配 (确定性的)
  ├─ 黑盒: 三层路由LLM (不可观测推理过程)
  └─ 白盒: 增量补取逻辑 (确定性的)
Agent-3: 混合 ★ 关键设计
  ├─ 白盒: WACC计算 (rf→beta→erp→wacc，完全可追溯)
  ├─ 白盒: BS画像预计算 (模型感知的反推方法)
  ├─ 黑盒: LLM推演裁决 (参数估计+估值计算+评分+KMI+叙事)
  └─ 白盒: 一致性校验 (概率和/单调性/WACC一致性/BS一致性)
```

**设计原则**: 白盒计算"事实"（WACC、BS画像），注入黑盒作为"约束"。黑盒在约束下做判断，输出再由白盒校验。这是工程控制论中"前馈+反馈"复合控制的具体实现。

### 10.4 BS画像的"前馈控制"设计

BS画像预计算是整个管线最关键的前馈信号：

```
模型感知的BS检测 (代码白盒) → market_premium_pct → 注入LLM prompt
                                                          ↓
                                     LLM基于BS画像推演: "市场已经定价了X%的改善，
                                     我的bull情景需要超越X%才有upside"
```

BS画像不是LLM可修改的假设——它是代码计算的**已知事实**。LLM只能解读它、围绕它构建情景，不能否定它。Agent-3 Step 2的BS一致性校验专门检查这一点。

### 10.5 可观测性矩阵

| 观测点 | 观测方式 | 时机 |
|--------|---------|------|
| Agent-0 映射命中率 | `pre_router_accuracy` 统计 | 每100次执行 |
| Agent-0 各行业补取率 | 按行业分类的 `incremental_fetch_rate` | 每周 |
| Agent-1 数据质量 | `overall_data_quality_score` | 每次执行 |
| Agent-2 路由hint不一致率 | `hint_rejection_note` 统计 | 每次执行 |
| Agent-2 搜索轮次分布 | `web_search_summary.searches_performed` | 每次执行 |
| Agent-3 一致性警告率 | E304/E305/E306/E307 频率 | 每次执行 |
| Agent-3 方向准确度 | eval_runner vs verification | 评测时 |
| Agent-3 信心校准度 | confidence vs actual_return 相关性 | 评测时 |

### 10.6 可控制性矩阵

| 控制参数 | 位置 | 调优方式 |
|---------|------|---------|
| 行业→数据包映射表 | Agent-0 | 手动更新YAML/JSON |
| 事件标签→boost字段 | Agent-0 | 手动更新映射表 |
| 案例匹配7规则权重 | Agent-2 case_loader | 评测驱动调优 |
| 三层路由仲裁优先级 | Agent-2 LLM prompt | 评测驱动调优 |
| WACC参数(rf/beta/erp) | Agent-3 Step 0 | 代码级调整算法 |
| BS检测方法参数 | Agent-3 Step 0 | 代码级调整 |
| 置信度因子权重 | Agent-3 LLM prompt | 评测驱动调优 |
| LLM temperature/model | Agent-2, Agent-3 | 配置文件 |

### 10.7 信息熵递减追踪

```
输入层:
  原始事件文本 (自由文本, ~500 tokens, 最高熵)
  + 未清洗财务数据 (14+ API端点, ~50字段)
  + 市场定价 (PE/PB/市值, 3个数值)
  → 总信息量: ~5000 tokens, 高冗余度

Agent-0:
  行业分类 + 事件标签 → 数据需求清单 (4个包, ~30字段)
  → 信息压缩比: 50字段→30字段, 去除了不相关维度

Agent-1:
  原始API返回 → 标准化数据包 (每个字段标注来源+质量+缺失)
  → 熵减: 非结构化→结构化, 模糊→可量化

Agent-2:
  数据包 + 联网搜索 + 案例 → 单一模型路由 + 迁移路径
  → 熵减: 10种可能模型→1个确定模型, 自由文本→结构化判决

Agent-3:
  完整上下文 → 三情景+概率+非对称评分+交易标注
  → 熵减: 多维输入→3个情景, 不确定性→概率分布, 模糊→单一评分
  → 最终输出: 约5000 tokens → 1个核心判断(概率加权涨幅+置信度+决策)
```

信息熵在每层单调递减。没有任何一层产生比其输入更高熵的输出（不"重新模糊化"）。

### 10.8 冗余校验设计

系统在两个层面有独立校验：

| 冗余类型 | 具体实现 | 触发条件 |
|---------|---------|---------|
| 模型交叉验证 | primary vs validation model target_mcap | Agent-3 Step 2 |
| BS方向验证 | 代码BS_level vs LLM输出的BS解读 | Agent-3 Step 2 |
| WACC不可修改 | 代码WACC vs LLM输出中是否篡改 | Agent-3 Step 2 |
| 概率自洽 | Σprob ≈ 1.0 | Agent-3 Step 2 |
| 增量补取 | Agent-2发现→Agent-1补拉→Agent-2重判 | Agent-2 Step 6 |
| 评测集独立验证 | frozen数据→实时Agent→vs ground_truth | 评测时 |

这些冗余不是重复劳动——每个校验维度不同，防止不同类型的错误。
