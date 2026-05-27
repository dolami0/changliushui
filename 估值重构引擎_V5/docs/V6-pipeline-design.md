# V6 估值管线升级设计

## 核心变化

**从"约束驱动路由"升级为"叙事驱动路由"。**

V5 的问题是：Agent-2 先选模型，Agent-3 再做 BS 画像检验定价——顺序倒置。好的估值应该先理解市场在讲什么故事、故事是否已计价，再选择定量工具。

V6 把"市场叙事诊断"从 Agent-3 的子步骤提升为 Agent-2 的主输出，并拆分为两次独立 LLM 调用。

---

## 管线分叉

Agent-0 按行业分类分叉：

```
Agent-0(预路由)
  ├─ 行业=医药生物-创新药 → rNPV 管线 (Agent-1r → Agent-2r → Agent-3r)
  └─ 其他行业 → 标准管线 (Agent-1 → Agent-2a → Agent-2b → Agent-3)
```

---

## 标准管线 (5 步)

```
Agent-0     Agent-1      Agent-2a       Agent-2b       Agent-3
 预路由      数据炼器     叙事诊断        路由判决        情景推演
(规则引擎)  (多层拉取)   (LLM调用1)     (LLM调用2)     (LLM调用3)
   │           │            │              │              │
   │  行业分类 │  财务数据   │ 市场叙事诊断  │ 模型选择      │ 三情景推演
   │  数据需求 │  估值倍数   │ 估值锚识别    │ 校验模型      │ 估值计算
   │           │  历史分位   │ 事件计价判断  │ 迁移路径      │ 置信度评分
   │           │  前瞻信号   │ 信号审核      │              │ 交易标注
   │           │            │ 计价定量锚    │              │ KMI+风险
```

### Agent-2a 输出 → Agent-2b 消费

2a 输出的 `forward_to_routing` 字段对 2b 施加**硬约束**：
- `model_family_constraint`: 2b 只能在此族内选择主模型
- 2b 保留校验模型选择权（受事件性质影响：突发→同类保守校验，延续→跨族校验）

### Agent-2a 输出 → Agent-3 消费

3 信任 2a 的 `signal_audit` 结论，不做重复验证。在 data_gaps 中引用 2a 的结果。

---

## rNPV 管线 (4 步)

```
Agent-0     Agent-1r         Agent-2r              Agent-3r
 预路由      管线数据拉取      两段式估值             情景推演
             ├─ 在研管线明细   ├─ ②-1 成熟产品计价    ├─ bull: 管线获批+
             ├─ 临床阶段       │   分产品收入→选锚     │   超预期销售
             ├─ 峰值销售数据   │   已上市药: PS或PE    ├─ base: 核心管线
             ├─ 可比交易       │   输出: 成熟产品估值   │   按预期推进
             ├─ 成熟产品收入    ├─ ②-2 在研管线计价    └─ bear: 关键管线
             └─ 研发费用       │   PoS×峰值×折现       │   失败→现金值
                               │   可比交易锚定
                               └─ ③ SOTP加总
                                  成熟+管线+现金-负债
```

**和标准管线的差异**：
- 不需要 Agent-2a（叙事即管线本身）
- 不需要 Agent-2b（模型固定为 rNPV/SOTP）
- Agent-2r 直接做估值（两步：成熟产品 + 在研管线）

---

## Agent-2a 输出 Schema

```json
{
  "market_narrative": {
    "primary_anchor": "earnings | revenue | asset | pipeline | sotp",
    "primary_anchor_evidence": "PS=15x(历史95分位), PE因亏损无意义...",
    "secondary_anchors": [
      {
        "segment": "传统业务",
        "anchor": "earnings",
        "revenue_share_pct": 60,
        "evidence": "...",
        "data_confidence": "low"
      }
    ],
    "sotp_triggered": true,
    "sotp_rationale": "新旧业务估值范式不同"
  },

  "event_pricing": {
    "event_classification": "sudden | ongoing | hybrid",
    "classification_rationale": "...",
    "pricing_assessment": {
      "method": "reverse_dcf | implied_revenue_cagr | implied_roe_improvement | qualitative",
      "method_applicable": true,
      "method_limitations": ["NOPAT为负,反向DCF不适用", "..."],

      "quantitative": {
        "current_metric": 15.0,
        "current_metric_name": "PS",
        "implied_expectation": "3y收入CAGR≈35%",
        "narrative_expectation": "事件叙事指向3y收入CAGR≈50%+",
        "gap_assessment": "约70%已计价,剩余30%取决于执行超预期"
      },

      "qualitative_factors": [
        "股价在事件公布前3个月已涨80%,存在预期抢跑",
        "分析师一致预期在事件后上修15%"
      ],

      "overall_priced_in": "partially | fully | not_priced | unknown",
      "priced_in_estimate": "约60-70%",
      "residual_catalyst": "若新业务毛利率超预期(>40%),PS可进一步扩张"
    }
  },

  "signal_audit": {
    "step2a_restate": ["[信号名] 当前值=X (↑/↓Yσ, 均值=Z)"],
    "step2b_match": [
      {
        "signal": "合同负债",
        "match": "支撑 | 时序错位 | 削弱 | 无关",
        "source_level": "L5 | L4 | L3 | L2 | L1",
        "basis": "..."
      }
    ],
    "step2c_product_restate": "产品结构数据复述",
    "step2d_score": 6,
    "score_rationale": "..."
  },

  "forward_to_routing": {
    "model_family_constraint": "revenue_multiples | earnings_multiples | asset_multiples | resource | pipeline | sotp",
    "excluded_families": ["earnings_multiples"],
    "event_nature": "sudden | ongoing",
    "pricing_bias": "undervalued | fairly_valued | overvalued | uncertain",
    "key_risk_for_routing": "成熟产品线仍稳定盈利,传统PE估值可能被忽视"
  }
}
```

---

## Agent-2b 输出 Schema

在现有 V5 routing_decision 基础上做最小改动——增加对 2a 约束的回应：

```json
{
  "routing_decision": {
    "primary_model": "B",
    "model_category": "Revenue Multiples",
    "routing_reason": "...",
    "validation_models": ["C"],
    "validation_rationale": "...",
    "validation_strategy": "conservative_same_family | cross_family | ...",
    "constraint_compliance": {
      "family_constraint_applied": "revenue_multiples",
      "constraint_override": false,
      "override_rationale": ""
    },
    "anchor_shift_warning": "成熟产品线占60%,若新业务失败锚可能回退到earnings",
    "model_migration_path": {}
  }
}
```

---

## 数据改动

**新增拉取**（Tushare 优先，investoday 补充）：

| 数据 | 来源 | 用途 |
|------|------|------|
| PS 历史分位 | investoday f2280RkHist | Phase 1 锚识别 |
| 事件日前后股价 | Tushare daily / investoday daily_prices | Phase 2 计价判断 |
| 同行估值中位数（可选） | investoday financial_rankings 估算 | Phase 1 锚识别 |

**现有 Agent-1 数据不变**，仅补提遗漏字段。

---

## 实施顺序

1. **数据补丁** — PS 历史分位 + 事件日前后股价
2. **Agent-2 拆分** — 创建 agent2a_narrative.py + agent2b_routing.py
3. **Agent-3 瘦身** — 裁掉信号审核和 BS 解读（已迁至 2a）
4. **rNPV 管线** — 创建 agent1r/2r/3r
5. **Orchestrator 升级** — 支持分叉 + 新 Agent 编排
6. **端到端测试** — 用已有 eval set 跑一遍
