# 估值重构引擎开发文档

> 版本: 1.1  
> 基础框架: 估值路由系统 v1.1  
> 核心修正: 引入Agent-0预路由层，明确"采购员不判案"原则，Agent-2拥有独立模型否决权  
> 目标: 将事件驱动的选股信号转化为可量化的估值重构与潜在涨幅判断  
> 架构: 多Agent流水线，每个Agent由独立LLM承载，通过标准化JSON接口通信

---

## 一、系统总览

### 1.1 核心命题

估值重构引擎解决一个问题：**给定一个事件驱动的选股标的，在情景推演下，其合理估值区间是多少？当前市值隐含了什么预期？是否存在非对称收益空间？**

### 1.2 系统边界

| 在边界内 | 在边界外 |
|---------|---------|
| 单标的估值重构与情景推演 | 组合构建与仓位管理 |
| 事件催化剂的量化映射 | 实时行情交易执行 |
| 估值模型的自动路由与计算 | 宏观择时与市场情绪判断 |
| 预期差探测与非对称评分 | 产业链上下游全图谱推导 |
| 输出结构化估值报告 | 非结构化研报撰写 |

### 1.3 架构全景

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        估值重构引擎 (Valuation Reconstruction Engine)         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │ Agent-0  │   │ Agent-1  │   │ Agent-2  │   │ Agent-3  │   │ Agent-4  │ │
│  │ 预路由    │ → │ 数据炼器  │ → │ 路由判官  │ → │ 推演沙盘  │ → │ 预期差镜  │ │
│  │PreRouter │   │DataForge │   │RouteJudge│   │Scenario  │   │GapDetect │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘ │
│       ↓              ↓              ↓              ↓              ↓        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Agent-5 裁决司命 (AsymmetryJudge)                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       ↓                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    宗门中枢 (Orchestrator)                             │   │
│  │              状态管理 + 异常回退 + 报告聚合 + 缓存层                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  外部接口: 事件驱动引擎输出 / 产业链Agent输出 / 案例库检索结果              │
│  下游消费: 选股评分系统 / 仓位建议模块 / 记忆空间归档                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.4 Agent职责速查

| Agent | 代号 | 核心职责 | 承载LLM要求 | 是否拥有模型选择权 |
|-------|------|---------|------------|------------------|
| **Agent-0 预路由** | PreRouter | 基于规则生成数据需求清单，猜测模型类别但不决定 | 规则引擎，**无需LLM** | **否** |
| **Agent-1 数据炼器** | DataForge | 按清单获取并清洗数据，输出分层数据包 | 强工具调用能力，需接入金融数据API | **否** |
| **Agent-2 路由判官** | RouteJudge | 基于完整数据包独立执行三层路由+冲突仲裁，拥有最终模型否决权 | 强规则遵循与分类能力 | **是（唯一）** |
| **Agent-3 推演沙盘** | ScenarioBuilder | 在三情景下分别计算估值 | 强数值推理与财务建模能力 | **否** |
| **Agent-4 预期差镜** | GapDetector | 执行反向DCF，探测市场隐含预期与基本面推演的差距 | 强数学推导与敏感性分析能力 | **否** |
| **Agent-5 裁决司命** | AsymmetryJudge | 综合所有输出，给出非对称评分、置信度与决策建议 | 强综合判断与风险校准能力 | **否** |

### 1.5 核心架构原则

> **原则1: 采购员不判案**  
> Agent-0（预路由）只生成数据采购清单，无权决定primary_model。Agent-2（路由判官）基于完整数据独立判决，不受Agent-0 hint影响。

> **原则2: 分层失败不崩溃**  
> core_package失败→终止流程；specialized/validation失败→触发增量补取或降级处理，系统继续。

> **原则3: 闭环校验**  
> Agent-2的增量补取频率反向度量Agent-0映射表准确率，驱动持续优化。

---

## 二、Agent-0 预路由 (PreRouter)

### 2.1 职责定义

接收标的代码与事件描述，输出一份**数据需求清单（data_requirements）**。清单分层为core/specialized/validation/optional，供Agent-1按需拉取。

**Agent-0无权输出primary_model，无权决定估值模型。它只回答一个问题："为了估值，我们需要采购哪些数据？"**

### 2.2 为什么用规则引擎而非LLM？

| 维度 | 规则引擎 | LLM |
|------|---------|-----|
| **速度** | 毫秒级匹配 | 秒级调用 |
| **成本** | 零token | 每次请求消耗数百token |
| **确定性** | 100%可预期输出 | 存在幻觉风险 |
| **可维护性** | 映射表可版本化管理 | 提示词调优成本高 |
| **高频触发** | 每个标的必经，规则零成本 | LLM成本累积显著 |

### 2.3 输入Schema

```json
{
  "request_id": "req_20260519_001",
  "ticker": "300476.SZ",
  "event_summary": "AI服务器PCB需求爆发，公司产能爬坡，Q1利润同比+200%",
  "event_tags": ["AI硬件", "产能释放", "利润拐点"],
  "trigger_source": "事件驱动引擎",
  "timestamp": "2026-05-19T22:00:00+08:00"
}
```

### 2.4 规则映射表

#### 第一层：行业分类映射

基于 `ticker` 的申万/中信行业分类，映射到**数据包类型**（不是模型类型）：

| 行业分类 | specialized_package核心字段 | 理由 |
|---------|---------------------------|------|
| 医药生物-创新药 | `pipeline_list`, `clinical_phase`, `peak_sales_estimate`, `pos_assumptions`, `net_cash` | 管线数据是核心原料 |
| 医药生物-仿制药 | `generic_revenue_share`, `consistency_evaluation_progress`, `net_cash` | 一致性评价进度影响估值 |
| 有色金属-能源金属 | `proven_reserves`, `probable_reserves`, `commodity_price_assumption`, `extraction_cost_rate`, `mine_life` | 储量与商品价格是核心原料 |
| 电子-印制电路板 | `capacity_utilization`, `order_backlog`, `yield_rate`, `customer_concentration` | 产能/订单/良率是核心原料 |
| 计算机-软件开发 | `subscribers`, `arpu`, `cac`, `ltv`, `churn_rate`, `payback_period` | 用户经济数据是核心原料 |
| 银行/保险 | `npl_ratio`, `net_interest_margin`, `capital_adequacy_ratio`, `roe_ttm` | 监管指标与息差是核心原料 |
| 房地产/REITs | `nav_breakdown`, `rental_yield`, `occupancy_rate`, `debt_maturity_schedule` | 资产重估与现金流是核心原料 |
| 通用工商业 | `peer_median_pe`, `peer_median_ps`, `industry_cycle_position` | 可比估值与周期位置是核心原料 |

#### 第二层：事件标签Boost

`event_tags` 中的关键词会**追加字段**到specialized_package，不改变映射主方向：

| 事件标签 | 追加字段 | 追加到哪个包 |
|---------|---------|------------|
| `产能释放` | `capacity_expansion_plan`, `capex_breakdown`, `depreciation_schedule` | specialized |
| `借壳重组` | `control_change_event`, `injection_asset_description`, `shell_value_estimate` | specialized |
| `管线推进` | `clinical_trial_updates`, `competitive_pipeline_landscape` | specialized |
| `政策催化` | `policy_document_reference`, `subsidy_amount`, `tax_benefit_duration` | validation |
| `困境反转` | `distress_recovery_timeline`, `asset_restructuring_plan`, `cash_burn_rate` | specialized |
| `并购要约` | `offer_price`, `offer_deadline`, `regulatory_approval_status` | core（紧急） |

### 2.5 输出Schema

```json
{
  "request_id": "req_20260519_001",
  "pre_routing_result": {
    "ticker": "300476.SZ",
    "industry_classification": "电子-印制电路板",
    "event_tags_matched": ["产能释放", "AI硬件"],

    "data_requirements": {
      "core_package": {
        "description": "所有估值模型通用，必须100%获取。缺失任一字段即终止流程",
        "fields": [
          "current_price", "total_shares", "market_cap",
          "revenue_ttm", "eps_ttm", "net_profit_growth_yoy",
          "bps", "roe_ttm", "ocf_ttm", "capex_ttm",
          "net_debt", "total_assets", "total_liabilities"
        ],
        "mandatory": true,
        "failure_action": "terminate"
      },

      "specialized_package": {
        "description": "基于行业+事件的专用字段。允许部分缺失，缺失时记录原因并继续",
        "fields": [
          "capacity_utilization", "order_backlog", "yield_rate",
          "customer_concentration", "capacity_expansion_plan",
          "capex_breakdown", "depreciation_schedule"
        ],
        "mandatory": false,
        "failure_action": "continue_with_gap",
        "source_rule": "行业=电子-印制电路板 + 事件标签=[产能释放, AI硬件]"
      },

      "validation_package": {
        "description": "校验模型可能需要的字段。缺失时校验模型降级或跳过",
        "fields": [
          "peer_median_pe", "peer_median_ps",
          "historical_pe_range", "historical_pb_range",
          "beta", "wacc_estimate"
        ],
        "mandatory": false,
        "failure_action": "skip_validation"
      },

      "optional_package": {
        "description": "非必要但有助于提升置信度。API配额紧张时优先跳过",
        "fields": [
          "dividend_per_share", "dividend_yield",
          "segment_breakdown", "gmv_ttm"
        ],
        "mandatory": false,
        "failure_action": "ignore"
      }
    },

    "model_category_hint": ["Earnings Multiples", "Real Options"],
    "hint_confidence": "中",
    "hint_rationale": "基于行业分类（电子制造）+事件标签（产能释放）的统计映射，仅供参考",

    "warning": "【重要】本hint不决定最终模型选择。Agent-2路由判官将基于实际财务数据独立判决，不受本hint影响。若判决与hint不一致，以Agent-2为准。"
  }
}
```

### 2.6 预路由错误的影响分析

| 预路由错误场景 | 实际后果 | 系统是否崩溃 |
|--------------|---------|-----------|
| 把Biotech映射成制造业 | Agent-1少拉pipeline_list；Agent-2发现PE<0，回退第一层，触发rNPV增量补取 | **否**，延迟+1次补取 |
| 把制造业映射成Biotech | Agent-1多拉了pipeline_list（空值）；Agent-2正常判为PEG，浪费少量API | **否**，仅效率损失 |
| 把资源股映射成平台股 | Agent-1拉了subscribers/arpu（空值）；Agent-2发现NAV更合适，触发储量补取 | **否**，延迟+1次补取 |
| 预路由完全失败（无匹配规则） | Agent-1回退到**全量拉取**（core + 所有specialized字段并集）；Agent-2正常判决 | **否**，仅成本增加 |
| core_package字段缺失 | Agent-1终止，返回E101错误 | **是（预期内终止）** |

**最坏情况：系统不会崩溃，只是效率降低。正确性由Agent-2保证。**

---

## 三、Agent-1 数据炼器 (DataForge)

### 3.1 职责定义

接收Agent-0的data_requirements，**按包分层并行拉取**，输出一份结构化数据包。每个字段标注所属包、获取状态、缺失原因。

### 3.2 执行流程

```
Step 1: 接收 pre_routing_result.data_requirements
Step 2: 【并行】获取 core_package（必须100%成功）
   └─ 任一字段失败 → 返回E101，终止流程
Step 3: 【并行】获取 specialized_package（允许部分缺失）
   └─ 缺失字段记录原因，继续流程
Step 4: 【并行】获取 validation_package（允许缺失）
   └─ 缺失字段标记为"校验降级"，继续流程
Step 5: 【条件】获取 optional_package（若有空闲API配额）
   └─ 配额不足则跳过，标记为"资源限制"
Step 6: 输出数据包，按 package 分组，明确标注每个字段的所属包和缺失状态
```

### 3.3 输出Schema

```json
{
  "request_id": "req_20260519_001",
  "status": "success",
  "ticker": "300476.SZ",

  "data_packages": {
    "core": {
      "status": "complete",
      "fields": {
        "current_price": 42.00,
        "total_shares": 850000000,
        "market_cap": 157000000000,
        "revenue_ttm": 4520000000,
        "eps_ttm": 1.85,
        "net_profit_growth_yoy": 2.15,
        "bps": 8.45,
        "roe_ttm": 0.22,
        "ocf_ttm": 620000000,
        "capex_ttm": 210000000,
        "net_debt": -500000000,
        "total_assets": 8500000000,
        "total_liabilities": 3200000000
      },
      "missing_count": 0,
      "quality_score": 1.0
    },

    "specialized": {
      "status": "partial",
      "fields": {
        "capacity_utilization": 0.92,
        "order_backlog": 850000000,
        "yield_rate": 0.91,
        "customer_concentration": null,
        "capacity_expansion_plan": "Q3新增月产能30万平米",
        "capex_breakdown": null,
        "depreciation_schedule": null
      },
      "missing_fields": ["customer_concentration", "capex_breakdown", "depreciation_schedule"],
      "missing_rationale": {
        "customer_concentration": "前五大客户收入占比未在财报中单独披露",
        "capex_breakdown": "在建工程附注未细分到具体产线，需手工拆解",
        "depreciation_schedule": "折旧政策未披露分项schedule"
      },
      "impact_assessment": "中——customer_concentration缺失不影响PEG计算，但影响风险判断；capex_breakdown缺失使产能释放节奏验证受限",
      "quality_score": 0.57
    },

    "validation": {
      "status": "partial",
      "fields": {
        "peer_median_pe": 28.5,
        "peer_median_ps": 3.2,
        "historical_pe_range": [15, 45],
        "historical_pb_range": null,
        "beta": 1.35,
        "wacc_estimate": null
      },
      "missing_fields": ["historical_pb_range", "wacc_estimate"],
      "missing_rationale": {
        "historical_pb_range": "PB区间需本地计算，当前未预计算",
        "wacc_estimate": "WACC需Agent-2根据行业风险假设给出，非纯数据字段"
      },
      "impact_assessment": "低——WACC缺失由Agent-2补假设；PB区间对当前路由影响小",
      "quality_score": 0.67
    },

    "optional": {
      "status": "skipped",
      "reason": "API配额优先级让给specialized_package",
      "fields": {}
    }
  },

  "overall_data_quality_score": 0.82,
  "quality_adjustment_note": "specialized_package缺失3/7字段(quality=0.57)，validation缺失2/6字段(quality=0.67)，core完整(quality=1.0)。加权后整体0.82",

  "raw_notes": "Q1产能利用率92%，AI服务器PCB订单排产至Q3，良率从85%提升至91%",

  "incremental_fetch_ready": true,
  "incremental_fetch_endpoint": "/api/v1/data/incremental"
}
```

### 3.4 错误处理

| 错误码 | 场景 | 处理策略 |
|--------|------|---------|
| `E101` | core_package任一字段缺失 | **终止流程**，返回错误，不进入路由阶段 |
| `E102` | core_package数据时间戳不一致 | 以最新数据为准，标记时效性，继续流程 |
| `E103` | specialized_package全部缺失 | 标记为"无专用数据"，Agent-2需基于core做通用路由 |
| `E104` | 计算字段异常（除以零/负数开方） | 返回null并附说明，不阻塞流程 |
| `E105` | API限流/超时 | 标记为"服务不可用"，触发指数退避重试，最多3次 |

---

## 四、Agent-2 路由判官 (RouteJudge)

### 4.1 职责定义

**Agent-2是系统中唯一拥有模型选择权的Agent。** 它基于Agent-1输出的完整数据包，独立执行估值路由框架v1.1的三层决策 + 冲突仲裁 + 动态迁移预判。

**Agent-2必须无视Agent-0的model_category_hint，独立判决。**

### 4.2 输入Schema

```json
{
  "request_id": "req_20260519_001",
  "data_package": { /* Agent-1 输出 */ },
  "pre_routing_hint": {
    "model_category_hint": ["Earnings Multiples", "Real Options"],
    "hint_confidence": "中",
    "warning": "仅供参考，不决定最终模型"
  },
  "event_context": {
    "event_type": "产能释放",
    "catalyst_timeline": "3-6个月",
    "catalyst_probability": 0.85,
    "business_model_shift": false
  }
}
```

### 4.3 核心约束（提示词中的铁律）

```
【系统角色】
你是宗门路由判官，执掌估值模型的"量天尺"。你的判决决定后续所有推演沙盘的计算方向。

【权力边界】
1. 你是系统中唯一有权决定primary_model的Agent
2. 你必须基于data_package中的实际财务数据独立执行三层路由
3. Agent-0的model_category_hint仅用于解释"为什么Agent-1拉了这些字段"
4. 若你的判决与hint不一致，以你的判决为准，并触发增量补取缺失字段
5. 你必须在routing_reason中明确说明："本判决基于数据独立做出，未参考hint"

【执行流程】
Step 1: 第一层 - 业务本质识别
  └─ 输入: 行业分类 + 收入结构 + 特殊属性(Biotech/资源/平台等)
  └─ 输出: model_category候选列表
  └─ 工具: 行业映射表 + 关键词匹配

Step 2: 第二层 - 盈利状态判断
  └─ 输入: EPS/ROIC/利润增速/亏损时长
  └─ 输出: primary_model候选 + 盈利生命周期标签
  └─ 规则: 见v1.1框架第二层

Step 3: 第三层 - 估值水位校验
  └─ 输入: PE/PB/利润贡献/PE贡献
  └─ 输出: validation_models列表 + 安全边际判断
  └─ 规则: 见v1.1框架第三层

Step 4: 冲突仲裁
  └─ 输入: Step 1-3的候选模型集合
  └─ 输出: 唯一的primary_model + 排序后的validation_models
  └─ 规则: 见v1.1二之一仲裁优先级

Step 5: 迁移路径预判
  └─ 输入: primary_model + 财务趋势 + 事件时间线
  └─ 输出: model_migration_path
  └─ 规则: 见v1.1二之二迁移路径库

Step 6: 反向DCF适用性判定
  └─ 输入: 盈利状态 + 可预测性 + 周期位置
  └─ 输出: reverse_dcf_applicability (适用/不适用/慎用)
```

### 4.4 增量补取机制

Agent-2在判决过程中，若发现数据包中缺少当前primary_model所需的关键字段，触发增量补取：

```json
{
  "routing_decision": {
    "primary_model": "PEG(增长锚定)",
    "model_category": "盈利乘数",
    "model_family": "Earnings Multiples",
    "validation_models": ["A_ROIC-RR(改善至稳态)", "正向DCF校验"],

    "routing_reason": "利润改善型制造: 利润增速>50%, PEG=0.45, 产能利用率92%, 订单可见度>2季度。触发增速优先仲裁规则(规则3)。【本判决基于数据独立做出，未参考hint】",

    "why_this_model": {
      "value_source": "AI服务器PCB产能释放带来的利润高速增长",
      "why_not_pe": "静态PE=22.6已无法反映增速，PEG直接量化增速与估值匹配度",
      "why_not_dcf": "盈利拐点已确认，但3年远期现金流预测偏差较大，DCF仅作校验",
      "why_not_ps": "公司已盈利，P/S会低估利润改善的价值",
      "why_not_roic": "ROIC正在改善但尚未稳态，ROIC-RR更适合作校验而非主模型"
    },

    "key_assumptions": {
      "primary": "2026年净利润增速维持50%以上",
      "secondary": [
        "AI服务器PCB需求持续性>2年",
        "良率维持90%以上",
        "产能爬坡无重大中断"
      ]
    },

    "model_migration_path": {
      "current_phase_model": "PEG(增长锚定)",
      "current_phase_tag": "阶段2-增速驱动期",
      "next_phase_trigger": {
        "financial_threshold": "ROIC>10%且连续两季稳定 + 增速回落至15-25%",
        "business_milestone": "产能利用率>95%且新增产能投产",
        "time_horizon": "预计12-18个月"
      },
      "next_phase_model": "A_ROIC-RR(稳态复利)",
      "migration_rationale": "当增速从爆发期回落至稳态，资本回报率取代增速成为估值核心驱动力",
      "fallback_trigger": "若AI需求提前见顶，加速迁移至CAPE+EV/EBITDA"
    },

    "reverse_dcf_applicability": "适用",
    "reverse_dcf_rationale": "当前ROIC=22%，FCF连续3年为正，盈利可预测性★★★★，非周期极端位置"
  },

  "incremental_fetch_request": {
    "triggered": false,
    "reason": "数据包已覆盖PEG所需全部字段，无需补取"
  },

  "conflict_log": [
    {
      "conflict": "PEG vs ROIC-RR",
      "arbitration_rule": "规则3-增速优先",
      "winner": "PEG",
      "loser": "ROIC-RR",
      "reason": "PEG=0.45<0.7阈值，利润增速>50%，订单/产能可见度>2季度"
    }
  ],

  "hint_rejection_note": "Agent-0 hint包含'Real Options'，但数据中无实控人变更/资产注入/技术路线竞争信号，故排除实物期权。判决与hint不一致，以数据为准。",

  "timestamp": "2026-05-19T22:02:00+08:00"
}
```

#### 增量补取触发示例

假设Agent-2第一层判定为 **rNPV(管线风险调整)**，但数据包中 `pipeline_list` 为空：

```json
{
  "routing_decision": {
    "primary_model": "rNPV(管线风险调整)",
    "model_category": "管线/项目组合",
    "routing_reason": "Biotech管线型: 起涨ROIC=-32.7%, PE为负, 核心价值=Σ(PoS×峰值销售折现)"
  },

  "incremental_fetch_request": {
    "triggered": true,
    "reason": "第一层判定为管线/项目组合，但specialized_package中pipeline_list为空",
    "missing_from_hint": true,
    "missing_rationale": "预路由hint未包含Pipeline/Portfolio，导致specialized_package未拉取pipeline_list",
    "requested_fields": ["pipeline_list", "clinical_trial_updates"],
    "priority": "high",
    "blocking": true,
    "fallback_if_unavailable": "若pipeline_list无法获取，primary_model降级为'远期P/S+实物期权'，并标记低置信度"
  }
}
```

若 `blocking: true`，Orchestrator暂停Agent-2，等待Agent-1执行增量补取后重新输入。

若 `blocking: false`，Agent-2继续输出路由决策，缺失字段用默认值/估算值填充，并在 `key_assumptions` 中标注不确定性。

### 4.5 错误处理

| 错误码 | 场景 | 处理策略 |
|--------|------|---------|
| `E201` | 三层路由均无法匹配 | fallback到"事件驱动"特殊情景模型，标记低置信度 |
| `E202` | 冲突仲裁后仍有并列 | 选择可预测性更高的模型，另一模型加入validation |
| `E203` | 事件类型与财务数据矛盾 | 触发人工复核标记，但不阻塞流程 |
| `E204` | 迁移路径无法匹配 | 输出空migration_path，标记为"静态估值" |
| `E205` | 增量补取后仍缺失关键字段 | 使用fallback模型，标记"数据不足，置信度降级" |

---

## 五、Agent-3 推演沙盘 (ScenarioBuilder)

### 5.1 职责定义

接收路由判官的决策 + 数据包，构建**基准/乐观/悲观**三情景估值树，分别计算各情景下的估值区间。每个情景使用路由判官指定的primary_model，validation_models用于交叉校验。

### 5.2 输入Schema

```json
{
  "request_id": "req_20260519_001",
  "routing_decision": { /* Agent-2 输出 */ },
  "data_package": { /* Agent-1 输出 */ },
  "scenario_config": {
    "base_case": { "probability": 0.50, "label": "基准情景" },
    "bull_case": { "probability": 0.30, "label": "乐观情景" },
    "bear_case": { "probability": 0.20, "label": "悲观情景" }
  }
}
```

### 5.3 情景构建规则

情景差异不是简单的"增速±10%"，而是基于**事件驱动的不确定性维度**进行结构化调整：

| 不确定性维度 | 基准情景 | 乐观情景 | 悲观情景 |
|------------|---------|---------|---------|
| **需求持续性** | AI需求维持当前增速 | AI需求超预期，客户拓展至海外 | AI需求提前见顶，订单回撤 |
| **产能释放** | 按计划爬坡 | 提前投产，良率超预期 | 设备交付延迟，良率爬坡慢 |
| **竞争格局** | 维持当前份额 | 份额提升，高端产品占比提高 | 新进入者价格战 |
| **利润率** | 毛利率维持32% | 规模效应+产品结构优化，毛利率38% | 价格战导致毛利率回落至25% |
| **估值锚** | PEG=1.0 | PEG=1.3（戴维斯双击） | PEG=0.8（增速证伪） |

### 5.4 模型计算模板

#### PEG 主模型计算模板

```
输入:
  - eps_ttm
  - net_profit_growth_yoy (情景调整后的增速)
  - current_price
  - peer_median_pe (可选，用于校验)

计算:
  pe_current = current_price / eps_ttm
  peg = pe_current / (net_profit_growth_yoy * 100)

  # 情景估值
  target_pe = net_profit_growth_yoy * 100 * target_peg
  target_price = target_pe * eps_forward_y1

  # 校验
  if target_pe > peer_median_pe * 1.5:
    flag = "估值溢价过高，需ROIC-RR校验"
```

#### A_ROIC-RR 计算模板

```
输入:
  - roe_ttm / roic_estimate
  - reinvestment_rate
  - wacc_estimate
  - growth_stage (稳态/改善)

计算:
  # 稳态复利
  if growth_stage == "稳态":
    value = eps_ttm * (roic - g) / (wacc - g)

  # 改善至稳态（两阶段）
  if growth_stage == "改善":
    stage1_years = 3
    stage1_growth = current_growth
    stage2_growth = terminal_g

    value = sum([eps_ttm * (1+stage1_growth)^i / (1+wacc)^i for i in 1..3])           + terminal_value / (1+wacc)^3
```

#### 正向DCF(盈利拐点) 计算模板

```
输入:
  - fcff_ttm (或估算拐点后FCF)
  - inflection_year (拐点年份)
  - pre_inflection_growth
  - post_inflection_growth
  - wacc
  - terminal_g

计算:
  # 拐点前：低/负FCF
  # 拐点后：正常化FCF按增速增长

  explicit_fcf = [estimate_fcf(year) for year in 1..5]
  terminal_value = explicit_fcf[-1] * (1+terminal_g) / (wacc - terminal_g)

  enterprise_value = sum([fcf / (1+wacc)^i for i, fcf in enumerate(explicit_fcf)])                    + terminal_value / (1+wacc)^5
  equity_value = enterprise_value - net_debt
  target_price = equity_value / total_shares
```

#### rNPV 计算模板

```
输入:
  - pipeline_list: [{name, phase, peak_sales, net_margin, pos, pe_terminal}]
  - discount_rate
  - net_cash

计算:
  pipeline_value = sum([
    p.peak_sales * p.net_margin * p.pe * p.pos / (1+discount_rate)^years_to_peak
    for p in pipeline_list
  ])

  total_value = pipeline_value + existing_product_value + net_cash
```

#### NAV 计算模板

```
输入:
  - reserves: {commodity: {proven, probable, unit}}
  - long_term_price: {commodity: price}
  - extraction_cost_rate
  - net_debt

计算:
  nav = sum([
    (r.proven + r.probable * 0.5) * price * (1 - extraction_cost_rate)
    for commodity, r, price in zip(reserves, long_term_price)
  ]) - net_debt
```

### 5.5 输出Schema

```json
{
  "request_id": "req_20260519_001",
  "scenario_valuation": {
    "base_case": {
      "label": "基准情景",
      "probability": 0.50,
      "assumptions": {
        "revenue_growth": 0.55,
        "net_margin": 0.18,
        "target_peg": 1.0,
        "target_roic": 0.15
      },
      "primary_model_result": {
        "model": "PEG(增长锚定)",
        "target_pe": 55.0,
        "target_price": 176.0,
        "upside": 3.19
      },
      "validation_results": [
        {
          "model": "A_ROIC-RR(改善至稳态)",
          "target_price": 165.0,
          "upside": 2.93,
          "variance_from_primary": -0.06
        }
      ],
      "confidence": "中"
    },
    "bull_case": {
      "label": "乐观情景",
      "probability": 0.30,
      "assumptions": {
        "revenue_growth": 0.80,
        "net_margin": 0.22,
        "target_peg": 1.3,
        "target_roic": 0.20
      },
      "primary_model_result": {
        "model": "PEG(增长锚定)",
        "target_pe": 104.0,
        "target_price": 332.8,
        "upside": 6.92
      },
      "validation_results": [],
      "confidence": "低"
    },
    "bear_case": {
      "label": "悲观情景",
      "probability": 0.20,
      "assumptions": {
        "revenue_growth": 0.20,
        "net_margin": 0.12,
        "target_peg": 0.8,
        "target_roic": 0.08
      },
      "primary_model_result": {
        "model": "PEG(增长锚定)",
        "target_pe": 16.0,
        "target_price": 51.2,
        "upside": 0.22
      },
      "validation_results": [],
      "confidence": "中"
    }
  },

  "probability_weighted_valuation": {
    "target_price": 176.0,
    "upside": 3.19,
    "downside": 0.78,
    "expected_return": 1.91
  },

  "sensitivity_matrix": {
    "peg_vs_growth": [
      ["growth=30%", "PEG=0.8→67.2", "PEG=1.0→84.0", "PEG=1.3→109.2"],
      ["growth=50%", "PEG=0.8→112.0", "PEG=1.0→140.0", "PEG=1.3→182.0"],
      ["growth=80%", "PEG=0.8→179.2", "PEG=1.0→224.0", "PEG=1.3→291.2"]
    ]
  },

  "timestamp": "2026-05-19T22:03:00+08:00"
}
```

### 5.6 错误处理

| 错误码 | 场景 | 处理策略 |
|--------|------|---------|
| `E301` | 情景假设导致估值为负 | 强制归零，标记为"价值毁灭" |
| `E302` | 校验模型与主模型偏差>50% | 触发告警，降低整体置信度 |
| `E303` | 概率加权后 upside < 1.0 | 标记为"无重构空间"，提前终止 |
| `E304` | 计算中出现除以零 | 返回null，使用相邻情景插值 |

---

## 六、Agent-4 预期差镜 (GapDetector)

### 6.1 职责定义

执行反向DCF，从当前市值反推市场隐含预期，与Agent-3推演的基本面预期对比，输出**预期差报告**。

### 6.2 适用性判定（前置检查）

若路由判官判定 `reverse_dcf_applicability != "适用"`，则本Agent跳过计算，输出空报告：

```json
{
  "applicability": "不适用",
  "reason": "纯管线型rNPV主导，DCF点估计无意义",
  "fallback": "使用rNPV的获批概率敏感性替代"
}
```

### 6.3 计算逻辑

#### 两阶段反向DCF

```
已知:
  - current_market_cap = current_price * total_shares
  - net_debt
  - enterprise_value = market_cap + net_debt
  - fcff_ttm (或最近可用FCF)
  - wacc
  - explicit_years = 3
  - explicit_growth = 一致预期或Agent-3基准情景增速

求解 g_terminal:

enterprise_value = Σ[fcff_ttm * (1+g_explicit)^i / (1+wacc)^i] for i=1..3
                 + [fcff_ttm * (1+g_explicit)^3 * (1+g_terminal)] / [(wacc - g_terminal) * (1+wacc)^3]

通过数值方法（牛顿迭代或二分法）反解 g_terminal。

market_implied_g = g_terminal
```

#### 预期差计算

```
my_implied_g = Agent-3基准情景中隐含的永续增速
               (或从基本面推演得到的合理永续增速)

expectation_gap = my_implied_g - market_implied_g
gap_direction = expectation_gap > 0 ? "市场低估" : "市场高估"
```

#### 敏感性分析

```
对以下参数进行±1%扰动，记录implied_g的变化:
- wacc ±1%
- explicit_growth ±5%
- net_debt ±10%
- terminal_roic ±2%
```

### 6.4 输出Schema

```json
{
  "request_id": "req_20260519_001",
  "reverse_dcf_report": {
    "applicability": "适用",
    "applicability_rationale": "当前ROIC=22%，FCF连续3年为正，盈利可预测性★★★★",

    "inputs": {
      "current_market_cap": 157000000000,
      "net_debt": -5000000000,
      "enterprise_value": 152000000000,
      "fcff_ttm": 4100000000,
      "wacc": 0.10,
      "explicit_growth": 0.50,
      "explicit_years": 3
    },

    "market_implied": {
      "g_terminal": 0.085,
      "implied_roic": 0.12,
      "implied_pe_terminal": 15.0,
      "interpretation": "市场隐含永续增速8.5%，对应稳态ROIC=12%，PE=15x"
    },

    "my_implied": {
      "g_terminal": 0.15,
      "source": "Agent-3基准情景推演",
      "rationale": "AI服务器PCB需求持续性>2年，产能释放后稳态ROIC可达15%"
    },

    "expectation_gap": {
      "gap_value": 0.065,
      "gap_direction": "市场低估",
      "gap_magnitude": "显著",
      "gap_threshold_check": "gap>5% → 存在估值重构空间"
    },

    "confidence": "中",
    "confidence_rationale": "WACC假设敏感，g的微小变化会大幅改变implied_g。当前wacc=10%基于行业平均，若公司风险溢价高于同行，实际gap可能收窄",

    "sensitivity_analysis": {
      "wacc_plus_1pct": { "implied_g": 0.055, "gap_change": -0.03 },
      "wacc_minus_1pct": { "implied_g": 0.115, "gap_change": +0.03 },
      "explicit_growth_plus_5pct": { "implied_g": 0.095, "gap_change": +0.01 },
      "explicit_growth_minus_5pct": { "implied_g": 0.075, "gap_change": -0.01 }
    },

    "decision_implication": "预期差6.5%且置信度≥中，存在估值重构空间。若乐观情景兑现，gap可能扩大至12%以上"
  },

  "timestamp": "2026-05-19T22:04:00+08:00"
}
```

### 6.5 错误处理

| 错误码 | 场景 | 处理策略 |
|--------|------|---------|
| `E401` | 数值迭代不收敛 | 放宽精度要求，或改用解析近似 |
| `E402` | implied_g为负 | 标记为"市场定价已包含衰退预期" |
| `E403` | implied_g > wacc | 标记为"市场定价不可持续"，高置信度看空 |
| `E404` | 敏感性分析显示gap在±2%内 | 标记为"无显著预期差"，降低决策权重 |

---

## 七、Agent-5 裁决司命 (AsymmetryJudge)

### 7.1 职责定义

综合前4个Agent的全部输出，进行最终裁决：非对称评分、置信度校准、决策建议、记忆归档建议。

### 7.2 输入Schema

```json
{
  "request_id": "req_20260519_001",
  "data_package_summary": { /* Agent-1 核心数据 */ },
  "routing_decision": { /* Agent-2 输出 */ },
  "scenario_valuation": { /* Agent-3 输出 */ },
  "reverse_dcf_report": { /* Agent-4 输出 */ },
  "case_library_match": {
    "matched_cases": ["300308", "300502"],
    "similarity_score": 0.82
  }
}
```

### 7.3 裁决维度

#### 维度1: 非对称评分 (Asymmetry Score)

评分公式：

```
asymmetry_score = (upside_bull * prob_bull + upside_base * prob_base) / (1 - downside_bear * prob_bear)

其中:
  upside_bull = bull_case_target_price / current_price
  upside_base = base_case_target_price / current_price
  downside_bear = bear_case_target_price / current_price (若<1则取1)

评分区间:
  > 5.0  → 极佳非对称 (十倍股候选)
  3.0-5.0 → 优秀非对称
  1.5-3.0 → 一般非对称
  < 1.5  → 非对称不足
```

#### 维度2: 置信度校准 (Confidence Calibration)

综合以下因子：

| 因子 | 权重 | 评分标准 |
|------|------|---------|
| 数据质量评分 | 0.20 | Agent-1输出 |
| 模型可预测性 | 0.25 | 见v1.1第四章矩阵 |
| 情景概率合理性 | 0.15 | 概率和=1且分布合理 |
| 校验模型一致性 | 0.15 | 主模型与校验模型偏差<30% |
| 预期差置信度 | 0.15 | Agent-4输出 |
| 案例库匹配度 | 0.10 | 相似案例的历史兑现率 |

```
confidence = Σ(factor_score * weight)

区间:
  > 0.80 → 高
  0.60-0.80 → 中
  0.40-0.60 → 低
  < 0.40 → 极低 (建议终止)
```

#### 维度3: 决策建议 (Decision Matrix)

```
if asymmetry_score > 3.0 and confidence >= "中":
  decision = "重构入场"
  position_sizing = f(asymmetry_score, confidence)

elif asymmetry_score > 1.5 and confidence >= "中":
  decision = "跟踪观察"
  trigger_for_upgrade = "等待催化剂确认或数据质量提升"

elif asymmetry_score > 3.0 and confidence < "中":
  decision = "小仓位试探"
  position_sizing = "≤5%"

else:
  decision = "放弃"
  reason = "非对称不足或置信度太低"
```

#### 维度4: 关键监测指标 (KMI)

输出后续跟踪中需要重点监测的指标，一旦偏离假设即触发重新估值：

```json
{
  "key_monitoring_indicators": [
    {
      "indicator": "单季度营收同比增速",
      "current": 0.68,
      "threshold_bear": 0.30,
      "threshold_bull": 0.90,
      "frequency": "季度",
      "action_if_breach": "触发Agent-3重新推演"
    },
    {
      "indicator": "产能利用率",
      "current": 0.92,
      "threshold_bear": 0.80,
      "threshold_bull": 0.95,
      "frequency": "月度",
      "action_if_breach": "触发Agent-2路由复核"
    }
  ]
}
```

### 7.4 输出Schema

```json
{
  "request_id": "req_20260519_001",
  "final_judgment": {
    "ticker": "300476.SZ",
    "current_price": 42.00,

    "valuation_summary": {
      "base_case_target": 176.00,
      "bull_case_target": 332.80,
      "bear_case_target": 51.20,
      "probability_weighted": 176.00,
      "upside_base": 3.19,
      "upside_bull": 6.92,
      "downside_bear": 0.22
    },

    "asymmetry_score": 4.85,
    "asymmetry_rating": "优秀非对称",
    "ten_bagger_potential": true,

    "confidence": 0.72,
    "confidence_level": "中",

    "decision": "重构入场",
    "position_sizing": "10-15%",
    "position_rationale": "非对称评分4.85接近十倍门槛，置信度中，数据质量高，可重仓",

    "time_horizon": "12-18个月",
    "expected_catalyst_path": [
      "Q2财报验证产能爬坡",
      "Q3新产能投产",
      "2027年AI需求持续性验证"
    ],

    "key_monitoring_indicators": [
      {
        "indicator": "单季度营收同比增速",
        "current": 0.68,
        "threshold_bear": 0.30,
        "threshold_bull": 0.90,
        "frequency": "季度",
        "action_if_breach": "触发Agent-3重新推演"
      },
      {
        "indicator": "产能利用率",
        "current": 0.92,
        "threshold_bear": 0.80,
        "threshold_bull": 0.95,
        "frequency": "月度",
        "action_if_breach": "触发Agent-2路由复核"
      },
      {
        "indicator": "PEG水位",
        "current": 0.45,
        "threshold_bear": 1.5,
        "threshold_bull": 0.3,
        "frequency": "实时",
        "action_if_breach": "触发估值锚迁移评估"
      }
    ],

    "risk_factors": [
      {
        "risk": "AI需求提前见顶",
        "probability": 0.20,
        "impact": "高",
        "mitigation": "跟踪北美云厂商Capex指引"
      },
      {
        "risk": "新进入者价格战",
        "probability": 0.25,
        "impact": "中",
        "mitigation": "跟踪行业产能扩张计划"
      }
    ],

    "memory_archive_suggestion": {
      "should_archive": true,
      "archive_tags": ["PEG主模型", "AI硬件", "产能释放", "十倍候选"],
      "archive_reason": "高非对称评分+中置信度，具备案例库价值"
    }
  },

  "full_report_digest": {
    "primary_model": "PEG(增长锚定)",
    "model_category": "盈利乘数",
    "market_implied_g": 0.085,
    "expectation_gap": 0.065,
    "routing_path": "PreRouter → DataForge → RouteJudge → ScenarioBuilder → GapDetector → AsymmetryJudge",
    "processing_time_ms": 4500,
    "pre_router_hint_rejected": false
  },

  "timestamp": "2026-05-19T22:05:00+08:00"
}
```

### 7.5 错误处理

| 错误码 | 场景 | 处理策略 |
|--------|------|---------|
| `E501` | 前序Agent输出不一致 | 以数据炼器为基准，标记冲突点供人工复核 |
| `E502` | 非对称评分计算异常 | fallback到简单upside/downside比值 |
| `E503` | 置信度<0.4但用户强制要求评分 | 输出评分但标记"极低置信度，决策权重归零" |
| `E504` | 案例库匹配失败 | 不影响评分，仅缺失历史平行参考 |

---

## 八、宗门中枢 (Orchestrator)

### 8.1 职责定义

协调6个Agent的执行顺序、状态管理、异常回退、缓存与报告聚合。

### 8.2 状态机

```
[INIT] → 接收请求
  ↓
[PRE_ROUTER] → Agent-0执行（规则引擎，毫秒级）
  ↓
[DATA_FORGE] → Agent-1执行
  ↓ success
[ROUTE_JUDGE] → Agent-2执行
  ↓ success (若触发incremental_fetch则回退到DATA_FORGE)
[SCENARIO_BUILD] → Agent-3执行
  ↓ success
[GAP_DETECT] → Agent-4执行 (若适用性=不适用则SKIP)
  ↓ success
[ASYMMETRY_JUDGE] → Agent-5执行
  ↓ success
[COMPLETE] → 输出最终报告

异常回退:
  任意Agent返回error → 根据错误码决定:
    - E0xx (预路由层) → 回退到全量拉取模式，继续
    - E1xx (数据层) → 终止，返回错误
    - E2xx (路由层) → 尝试fallback模型，重试1次；若触发incremental_fetch则回退Agent-1
    - E3xx (推演层) → 跳过该校验模型，继续
    - E4xx (预期差层) → SKIP Agent-4，标记为"无预期差数据"
    - E5xx (裁决层) → 使用前序Agent输出做简化裁决
```

### 8.3 缓存策略

| 缓存层级 | 内容 | TTL | 刷新触发条件 |
|---------|------|-----|------------|
| L0 - 预路由 | Agent-0输出 | 24小时 | 行业分类变更 |
| L1 - 数据包 | Agent-1输出 | 1小时 | 财报日/价格变动>5% |
| L2 - 路由决策 | Agent-2输出 | 24小时 | 财务数据重大变化/增量补取后 |
| L3 - 情景估值 | Agent-3输出 | 6小时 | 价格变动>5%/新催化剂 |
| L4 - 预期差 | Agent-4输出 | 12小时 | 价格变动>5% |
| L5 - 最终裁决 | Agent-5输出 | 1小时 | 任意前序Agent刷新 |

### 8.4 接口定义

#### 输入接口

```http
POST /api/v1/valuation/reconstruct
Content-Type: application/json

{
  "ticker": "300476.SZ",
  "event_summary": "AI服务器PCB需求爆发...",
  "event_tags": ["AI硬件", "产能释放"],
  "trigger_source": "事件驱动引擎",
  "priority": "high",
  "bypass_cache": false
}
```

#### 输出接口

```http
200 OK
Content-Type: application/json

{
  "request_id": "req_20260519_001",
  "status": "complete",
  "final_judgment": { /* Agent-5输出 */ },
  "agent_outputs": {
    "pre_router": { /* Agent-0 */ },
    "data_forge": { /* Agent-1 */ },
    "route_judge": { /* Agent-2 */ },
    "scenario_builder": { /* Agent-3 */ },
    "gap_detector": { /* Agent-4 */ }
  },
  "processing_meta": {
    "total_time_ms": 4500,
    "cache_hit": false,
    "retry_count": 0,
    "incremental_fetch_count": 0
  }
}
```

---

## 九、闭环校验与持续优化

### 9.1 预路由准确率度量

通过Agent-2的增量补取频率反向度量Agent-0映射表质量：

```
pre_router_accuracy = 1 - (incremental_fetch_count / total_requests)

阈值:
  > 0.90 → 优秀，映射表无需调整
  0.80-0.90 → 良好，定期review
  0.70-0.80 → 预警，需排查高频补取的行业分类
  < 0.70 → 严重，需重构映射表
```

### 9.2 数据包质量趋势

记录每次请求的 `overall_data_quality_score`，追踪Agent-1的数据获取能力：

```
weekly_quality_trend = moving_average(data_quality_score, 7d)

若连续3周下降 → 排查数据源接口稳定性
```

### 9.3 模型选择回测

每月抽取10%的历史案例，人工review Agent-2的模型选择是否与事后验证一致：

```
routing_accuracy = (correct_primary_model / total_reviewed_cases)

"正确"定义: 事后看，所选模型在该案例起涨阶段确实是最有效的估值语言
```

---

## 十、与现有系统的衔接

### 10.1 上游输入

| 来源系统 | 输出内容 | 映射到引擎 |
|---------|---------|-----------|
| **事件驱动引擎** | 事件类型 + 催化剂时间线 + 概率 | Agent-0 event_tags + Agent-2 催化优先仲裁 |
| **产业链Agent** | 行业定位 + 竞争格局 + 供需判断 | Agent-0 行业分类 + Agent-3 情景假设 |
| **案例库检索** | 相似案例列表 + 历史兑现率 | Agent-5 案例库匹配 + 置信度校准 |
| **记忆空间** | 该标的历史估值记录 | Agent-1 数据校验 + Agent-2 迁移路径参考 |

### 10.2 下游消费

| 消费系统 | 需要的引擎输出 |
|---------|--------------|
| **选股评分系统** | asymmetry_score + confidence + decision |
| **仓位建议模块** | position_sizing + risk_factors |
| **记忆空间归档** | memory_archive_suggestion |
| **监控告警系统** | key_monitoring_indicators |
| **案例库更新** | full_report_digest + 实际后续走势（闭环） |

### 10.3 数据闭环

```
估值重构引擎输出 → 交易执行 → 实际走势跟踪 → 与引擎预测对比
                           ↓
                    偏差分析 → 反馈至:
                      - Agent-0: 映射表修正（通过补取频率）
                      - Agent-1: 数据需求修正
                      - Agent-2: 路由规则修正
                      - Agent-3: 情景假设修正
                      - Agent-5: 置信度校准修正
```

---

## 十一、开发里程碑

| 阶段 | 目标 | 交付物 | 预计工期 |
|------|------|--------|---------|
| **M0** | **Agent-0 预路由** | 行业→数据包映射表 + 事件标签boost规则 + 输出Schema | **3天** |
| M1 | Agent-1 数据炼器 | 按包分层拉取逻辑 + 缺失标注 + 质量评分 + 增量补取接口 | 1周 |
| M2 | Agent-2 路由判官 | 三层路由逻辑 + 冲突仲裁 + 迁移路径 + hint隔离协议 + 增量补取触发 | 1周 |
| M3 | Agent-3 推演沙盘 | 4条迁移路径模板 + 5个主模型计算模板 + 敏感性矩阵 | 2周 |
| M4 | Agent-4 预期差镜 | 反向DCF算法 + 适用性判定 + 敏感性分析 | 1周 |
| M5 | Agent-5 裁决司命 | 非对称评分公式 + 置信度校准 + 决策矩阵 | 1周 |
| M6 | 宗门中枢 | 状态机 + 缓存层 + API接口 + 异常回退 + 闭环校验 | 1周 |
| M7 | 集成测试 | 10个历史案例回测 + 偏差分析 + 规则调优 + 预路由准确率验证 | 2周 |
| M8 | 上线部署 | Coze工作流映射 / 独立API部署 | 1周 |

---

## 十二、附录

### 附录A: 估值模型快速参考卡

| 模型 | 公式 | 关键变量 | 适用信号 |
|------|------|---------|---------|
| PEG | PE / g | PE, 利润增速 | 正盈利, 增速>10%, PEG<1 |
| A_ROIC-RR | EPS × (ROIC-g)/(WACC-g) | ROIC, g, WACC | 稳态复利或改善至稳态 |
| 正向DCF | ΣFCF/(1+WACC)^t + TV | FCF, WACC, g | 亏损但拐点可见 |
| 反向DCF | 从市值反解g | 市值, FCF, WACC | 适用性判定通过后 |
| rNPV | Σ(PoS×峰值销售×净利率×PE×折现) | 管线清单, PoS | Biotech管线型 |
| NAV | Σ(储量×价格×(1-成本率))-净债务 | 储量, 价格, 成本 | 资源/矿业 |
| 实物期权 | 注入概率×注入价值 | 事件概率, 注入资产 | 借壳/重组/转型 |

### 附录B: 错误码全集

| 错误码 | 所属Agent | 含义 |
|--------|----------|------|
| E0xx | Agent-0 | 预路由映射错误 |
| E1xx | Agent-1 | 数据获取与清洗错误 |
| E2xx | Agent-2 | 路由决策错误 |
| E3xx | Agent-3 | 情景推演计算错误 |
| E4xx | Agent-4 | 反向DCF计算错误 |
| E5xx | Agent-5 | 裁决评分错误 |

### 附录C: 与估值路由框架v1.1的映射

| v1.1章节 | 映射到引擎模块 |
|---------|--------------|
| 一、估值模型全集 | Agent-3 模型计算模板库 |
| 二、三层路由决策 | Agent-2 核心逻辑 |
| 二之一、冲突仲裁 | Agent-2 Step 4 |
| 二之二、迁移路径 | Agent-2 Step 5 + Agent-3 路径模板 |
| 三、8大模型路由规则 | Agent-2 触发条件表 |
| 四、可预测性矩阵 | Agent-5 置信度校准因子 |
| 五、案例修正清单 | Agent-5 案例库匹配 |
| 六、字段扩展 | 全系统Schema定义 |
| 反向DCF升级 | Agent-4 完整实现 |

### 附录D: 核心架构原则重申

> **原则1: 采购员不判案**  
> Agent-0只生成数据采购清单，无权决定primary_model。Agent-2基于完整数据独立判决，不受Agent-0 hint影响。

> **原则2: 分层失败不崩溃**  
> core_package失败→终止流程；specialized/validation失败→触发增量补取或降级处理，系统继续。

> **原则3: 闭环校验**  
> Agent-2的增量补取频率反向度量Agent-0映射表准确率，驱动持续优化。
