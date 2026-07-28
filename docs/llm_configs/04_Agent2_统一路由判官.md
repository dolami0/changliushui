# Agent-2: 统一路由判官 (UnifiedRouteJudge)

> **类型**: LLM 单次调用（V8 合并 2a+2b）
> **文件**: `src/agent2_unified.py` (995 行)
> **触发**: Agent-1 + Agent-Baseline 完成后

---

## LLM 配置

```json
{
  "model": "deepseek-v4-pro",
  "endpoint": "https://api.deepseek.com/chat/completions",
  "max_tokens": 40960,
  "temperature": 0.0,
  "thinking": {"type": "enabled"},
  "reasoning_effort": "high",
  "stream": false
}
```

## V8 架构变化

V6/V7 中 Agent-2 拆分为 2a（叙事诊断）+ 2b（模型路由）。V8 合并为单次 LLM 调用：

- **根因**: 2a→2b 拆分制造了职责边界模糊——2b 的 Prompt 不断膨胀叙事分析逻辑，实质上是让两个 LLM 独立判断同一件事
- **收益**: 消除序列化交接损耗（-30s 延迟，-40% tokens），路由更稳定
- **核心设计**: 推理链顺序强制执行（先理解公司→再识别锚→再看事件→最后选模型）。不允许先有模型偏好再反推锚

## 输入

用户消息按以下结构组织:
1. **投资地图** — 事件冲击前的企业全貌（Agent-Baseline 绘制）
2. **估值倍数全矩阵** — PE/PB/PS 当前值 + 历史分位
3. **定量定价工具** — 三个锚各自反推"当前市值隐含什么预期"
4. **事件语料** — 投资主题/事件推演/行业研究/火山搜索
5. **前瞻信号面板** — 合同负债/应收/存货等实时经营数据
6. **代码约束清单** — 各模型的技术可行性观测（非硬性闸门）

## System Prompt

完整 Prompt（340 行）定义了 6 步推理链：

### 第一步: 理解这家公司
消费投资地图（不是重读所有原始数据）。投资地图已完成了"这家公司是谁"的认知工作。建立清晰的"公司画像"，后续所有判断以此为基准。

### 第二步: 识别估值锚
**核心问题: 市场在根据什么给这家公司定价？**

**SOTP 判定（必须最先做）**: 用单一 PE 或单一 PS 给全部业务估值，会不会严重扭曲至少一个业务的价值？→ 会 → primary_anchor=sotp, primary_model=J

**叙事→锚判断**:
- "收入爆发/TAM 扩张/市占率提升" → 锚偏向 revenue
- "盈利拐点/利润率修复/ROIC 改善" → 锚偏向 earnings
- "资产重估/隐蔽资产/NAV" → 锚偏向 asset
- "管线获批/临床数据/峰值销售" → 锚偏向 pipeline

**事件优先法则**: 事件驱动的叙事是默认锚。内部经营叙事不能单独作为切换锚的理由。

**数字验证**: 用定量定价工具验证锚判断。常见误判:
- PE 极高+盈利 → 不一定是"利润锚！高增长！"——周期底部 PE 虚高是分母被压制
- PS 极高 → 可能是收入锚，但也可能是周期底部收入也被压制
- PB 极高 → 当利润/收入/EBITDA 全部被周期压制时，净资产反而最稳定

### 第三步: 事件光谱诊断
三维度打分 (0-10) → 映射到分布形状:

| 维度 | 0 分端 | 10 分端 |
|------|--------|--------|
| timing_certainty | 完全随机 | 精确到日 |
| outcome_binaryness | 连续谱 | 非此即彼 |
| precedent_richness | 史无前例 | 大量参照 |

维度→分布形状映射表:
| timing | binaryness | precedent | → 分布形状 |
|:------:|:---------:|:---------:|------|
| 低(0-3) | 高(7-10) | 低(0-4) | wide_bimodal |
| 高(7-10) | 高(7-10) | 高(7-10) | wide_bimodal_date_anchored |
| 低(0-4) | 低(0-3) | 低(0-4) | wide_unimodal |
| 中(4-7) | 低(0-2) | 高(7-10) | narrow_concentrated |
| 高(7-10) | 低(0-2) | 高(7-10) | narrow_base_dominant |

### 第四步: 模型选择
从全部 10 个模型中按优先级选择:

**优先级 1: 锚匹配**
- earnings → A(ROIC-RR DCF) / K(两阶段DCF) / G(PEG) / I(盈利正常化)
- revenue → B(PS+TAM)
- asset → D(PB-ROE) / H(NAV)
- resource → E(EV/EBITDA+资源)
- pipeline → F(rNPV)
- 多锚冲突且不可调和 → J(SOTP)

**优先级 2: 叙事契合度** — 模型的核心逻辑是否匹配市场在赌的东西？
**优先级 3: 模型-数据兼容性** — 参考代码约束清单

**SOTP 判定**: 不是前置触发器——是模型 J 被选中时的结果。选 J 的条件:
1. 两个或以上业务需要不同估值锚
2. 混在一起用单一模型会产生系统性偏差
3. 新业务有可独立估值的锚点

**G(PEG) 使用约束**:
1. 增长驱动必须是结构性的，不是周期性的
2. 周期行业默认范式是 EV/EBITDA 或盈利正常化

### 第五步: 计价判断
定量参照 + 定性因子 → 综合判定:
- not_priced: 突发事件，股价未反应
- partially: 部分定价，剩余取决于执行
- fully: 全部反映，上行空间有限
- unknown: 数据不足

同时填写 `priced_in_estimate`: 定量百分比估计。

### 第六步: 信号审核（轻量级）
从前瞻信号面板提取关键信号，与叙事方向对比。给出 0-10 匹配度评分。

## 模型目录

| 模型 | 锚类型 | 一句话描述 | 典型场景 |
|------|--------|-----------|---------|
| A | earnings | ROIC-RR DCF: ROIC 驱动再投资率→永续增长 | 成熟期、ROIC>WACC、稳态盈利 |
| K | earnings | 两阶段 DCF: 高增长→终值 PE | 成长型、终局可见、NOPAT 可支撑 DCF |
| G | earnings | PEG: 增速锚定 PE | 结构性高增长(新产品/新市场驱动) |
| I | earnings | 盈利正常化: 周期中值利润替代 TTM | 周期股(化工/航运/养殖) |
| B | revenue | PS+TAM: 收入×PS | 亏损/微利、收入高增长、TAM 扩张 |
| D | asset | PB-ROE: ROE 改善→PB 扩张 | 重资产+ROE 改善逻辑 |
| H | asset | NAV: 资产重估 | 隐蔽资产、投资性房地产 |
| E | resource | EV/EBITDA+资源: 储量价值 | 矿业/油气、不可复制资源 |
| F | pipeline | rNPV: 概率加权现金流折现 | 创新药/biotech、管线驱动 |
| J | sotp | SOTP: 分部独立估值后加总 | 多业务不同锚、混估产生系统性偏差 |

## 代码约束清单（Code Advisory）

代码层分析财务数据，为每个模型生成技术可行性观测。这是**观测不是闸门**——LLM 可以不同意代码的判断，但必须给出理由。

```python
# 例: K 模型 NOPAT 检查
if nopat < 0.5:
    advisories["K"].append("NOPAT<0.5亿，两阶段DCF终值占比过高风险")
```

## 输出 JSON Schema

```json
{
  "market_narrative": {
    "core_bet": "一句话: 市场在押注什么",
    "narrative_lifecycle": "导入期|成长期|成熟期|转型期",
    "primary_anchor": "earnings|revenue|asset|pipeline|sotp",
    "primary_anchor_evidence": "双向证据 ≥60字",
    "anchor_conflict": "矛盾解释或空",
    "narrative_summary": "完整叙事总结 ≥80字",
    "secondary_anchors": "[{segment, anchor, revenue_share_pct, data_confidence}]",
    "anchor_shift_potential": {
      "shift_possible": "true/false",
      "shift_timing": "已发生/进行中/尚未开始",
      "from_anchor": "当前锚",
      "to_anchor": "可能切换到的锚"
    }
  },
  "event_profile": {
    "distribution_shape": "wide_unimodal|wide_bimodal|wide_bimodal_date_anchored|narrow_concentrated|narrow_base_dominant",
    "shape_rationale": "维度打分→分布形状的推导",
    "timing_certainty": 5,
    "outcome_binaryness": 2,
    "precedent_richness": 8
  },
  "routing_decision": {
    "primary_model": "A-K单字母",
    "model_category": "估值家族",
    "routing_reason": "≥80字，引用锚判断+财务数据+事件光谱",
    "validation_models": ["A"],
    "validation_rationale": "校验策略理由",
    "validation_strategy": "cross_family|conservative_same_family|self_validation",
    "code_constraints_discussion": ["对代码约束的回应"],
    "sotp_primary_segment_model": "仅J时填",
    "event_driven_segment": "仅J时填"
  },
  "pricing_assessment": {
    "overall_priced_in": "not_priced|partially|fully|unknown",
    "priced_in_rationale": "≥60字",
    "priced_in_estimate": "约XX-YY%",
    "residual_catalyst": "剩余催化因素"
  },
  "signal_audit": {
    "key_supporting_signals": [],
    "key_conflicting_signals": [],
    "match_score": 6,
    "score_rationale": "1-2句"
  }
}
```

## 核心约束

1. **推理链不可跳步** — 先锚→再事件→后模型。不允许先有模型偏好再反推锚
2. **叙事驱动指标** — 锚识别从叙事出发，估值数据用于验证而非替代叙事判断
3. **代码约束清单是观测不是闸门** — LLM 可以不同意但必须给理由
4. **SOTP 是模型选择的结果** — 选 J 的条件是"混在一起会产生系统性偏差"
5. **输出纯 JSON**

## Fallback 机制

当 LLM 不可用时，`_fallback()` 提供纯代码路由:
```python
FALLBACK_HARD_CONSTRAINTS = {
    "A": {"min_roic": 10, "min_nopat": 1.0},
    "K": {"min_nopat": 0.5},
    "G": {"min_growth": 15},
    # ...
}
```
