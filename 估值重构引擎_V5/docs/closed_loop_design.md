# 预研→估值 闭环进化系统设计

## 一、工程控制论四问

```
目标 (Goal):      投资地图覆盖六维，每个维度的信息密度足够支撑下游估值推演
执行 (Execution): Coze预研 → Agent-0 → Baseline → Agent-2a/2b → Agent-3/3s
观测 (Observation): 下游每个 Agent 输出结构化的 gap/loss 信号
纠偏 (Correction):  聚合信号 → 诊断根因 → 改进预研探针/Baseline Prompt → 进入下一周期
```

**核心原则**: 不在管线中打断，不在 Prompt 中堆砌。反馈回路是代码层的、结构化的、可聚合的。

---

## 二、观测层：三个信号源

### 信号源 1: Baseline 自评置信度

Baseline 输出每个维度的置信度，标注信息缺失：

```json
{
  "dimension_confidence": {
    "identity_revenue": 4,     // 一、公司身份与收入结构
    "financial_baseline": 5,   // 二、财务基线  
    "industry_position": 3,    // 三、产业位置
    "growth_milestones": 2,    // 四、增长轨迹与里程碑
    "thesis_vulnerability": 4, // 五、投资主线与脆弱点
    "quantitative_anchors": 2  // 六、量化锚点
  },
  "dimension_gaps": {
    "growth_milestones": "缺少产能利用率和在建产能数据, 原定里程碑时间线仅覆盖产品节点, 未覆盖财务节点",
    "quantitative_anchors": "可比公司PE/PS数据缺失, 火山搜索返回了券商预测但无可比估值倍数"
  }
}
```

**进化信号**: 低分维度 + gap描述 → 对应到预研探针覆盖缺口

### 信号源 2: Agent-2a 叙事诊断的 data_gaps

Agent-2a 在诊断过程中发现地图缺失什么：

```json
{
  "data_gaps": [
    {
      "gap_type": "missing_baseline_dimension",
      "dimension": "quantitative_anchors",
      "specific_missing": "可比公司PS中位数",
      "impact": "无法判断当前PS 8x是否合理, 锚判断置信度下降"
    },
    {
      "gap_type": "insufficient_detail",
      "dimension": "industry_position",
      "specific_missing": "上游原材料成本占比和价格趋势",
      "impact": "经营杠杆方向判断缺乏依据"
    }
  ]
}
```

**进化信号**: gap_type + dimension → 直接指向预研探针设计的盲区

### 信号源 3: Agent-3 推演的 anchor_rejection

Agent-3 赋参数时如果拒绝使用 baseline 的量化锚点，必须记录原因：

```json
{
  "anchor_usage": [
    {"anchor": "可比PE中位数45x", "used": false, "reason": "baseline给出的可比公司是2023年数据, 行业景气已变化, 改用火山搜索中的2024Q3可比数据"},
    {"anchor": "产能利用率95%", "used": true}
  ]
}
```

**进化信号**: rejected anchors → baseline 数据时效性/准确性问题

---

## 三、聚合层：GapAaggregator

管线每次运行后，gap 信号写入结构化日志。周期性运行聚合器：

```python
# gap_aggregator.py — 离线运行, 不嵌入管线
class GapAggregator:
    """从 N 次管线运行的 data_gaps 中提取系统性模式"""
    
    def aggregate(self, run_logs: list[dict]) -> GapReport:
        by_dimension = defaultdict(list)
        for run in run_logs:
            for gap in run.get("data_gaps", []):
                dim = gap.get("dimension", "unknown")
                by_dimension[dim].append(gap)
        
        patterns = []
        for dim, gaps in by_dimension.items():
            if len(gaps) >= 3:  # 至少3次出现才算模式
                gap_types = Counter(g.get("gap_type") for g in gaps)
                top = gap_types.most_common(1)[0]
                patterns.append({
                    "dimension": dim,
                    "frequency": f"{len(gaps)}/{len(run_logs)}",
                    "dominant_gap_type": top[0],
                    "sample_gaps": gaps[:3]
                })
        return GapReport(patterns=patterns)
```

---

## 四、纠偏层：从 Gap 到 Action

每个系统性能的 gap 模式 → 明确的改进动作：

| Gap 模式 | 根因 | 纠偏动作 |
|---------|------|---------|
| `quantitative_anchors` 频次 >30% | Coze 探针未系统采集可比估值数据 | N1 探针覆盖方向增加"可比估值锚点" |
| `growth_milestones` 频次 >30% | 事件推演混入地图, 原定轨迹缺失 | event_deduction 输出加 `[当前状态]` vs `[事件后推演]` 标记 |
| `identity_revenue` 频次 >20% | 产品级收入数据缺失 | N1 探针要求构造产品收入表 |
| `industry_position` 中"利润池"缺失 >20% | N2 产业链分析维度不全 | N2 探针增加"产业链利润池分布" |
| 特定行业(如创新药) anchor_rejection 高频 | 行业估值范式特殊, 通用探针不适配 | 按行业分类增加探针模板变体 |
| `financial_baseline` 低分但无 gap 报告 | Agent-1 数据质量下降 | 排查数据源 (tushare/investoday API) |

---

## 五、进化周期

```
┌─────────────────────────────────────────────────────────┐
│                    进化周期（建议按周）                      │
│                                                         │
│  Week N:  管线持续运行, 积累 gap 日志                       │
│           └─→ 每周 20-50 条管线输出                        │
│                                                         │
│  Week N+1: 运行 GapAggregator                            │
│           └─→ 生成 GapReport                             │
│           └─→ 识别 Top 3 系统性缺口                        │
│                                                         │
│           ┌─ 如果 Top 1 是预研探针盲区 ────→ 更新 Coze 探针模板  │
│           ├─ 如果 Top 1 是 baseline 消费问题 ──→ 优化 baseline Prompt │
│           ├─ 如果 Top 1 是下游推理偏差 ────→ 调整 Agent-3 约束     │
│           └─ 如果 Top 1 是数据源问题 ────→ 切换/补充数据源       │
│                                                         │
│  Week N+2: 继续运行, 观测 gap 模式是否改善                    │
│           └─→ 如果改善 → 固化改动                           │
│           └─→ 如果未改善 → 重新诊断根因                       │
└─────────────────────────────────────────────────────────┘
```

---

## 六、实施路线（按优先级）

### Phase 1: 植入观测点（最小改动, 立即可做）

| 改动 | 位置 | 工作量 |
|------|------|--------|
| Baseline 输出 `dimension_confidence` + `dimension_gaps` | agent_baseline.py Prompt 末尾加 JSON 块 | ~20行 |
| Agent-2a data_gaps 结构化为 `{gap_type, dimension, specific_missing, impact}` | agent2a_narrative.py 输出 schema | ~15行 |
| Agent-3 输出 `anchor_usage: [{anchor, used, reason}]` | agent3_scenario_asymmetry.py 输出 schema | ~10行 |
| orchestrator 收集 `run_gaps` 写入 JSON 报告中 | orchestrator.py `_assemble_result` | ~15行 |

### Phase 2: 聚合分析（离线工具）

| 工具 | 功能 |
|------|------|
| `gap_aggregator.py` | 从 reports/data/*.json 中提取 gap 信号, 生成 GapReport |
| `probe_tuner.py` | 基于 GapReport 建议 Coze 探针模板的修改 |

### Phase 3: 闭环自动化（远期）

- 当某个维度的 gap 频次超过阈值时，自动将新的探针方向注入 Coze 工作流
- Baseline Prompt 的缺陷模式自动生成改进建议

---

## 七、关键设计决策

### 为什么不在 Prompt 中做闭环？

Prompt 是静态的。在 Prompt 中要求 LLM "如果上次缺了 X 这次注意补" = 无效。LLM 每次都是全新推理，没有记忆。闭环必须在代码层——信号→聚合→阈值→改代码→部署。

### 为什么用维度级 gap 而不是字段级？

字段级太细（"缺了 PS 中位数"），维度级足够（"量化锚点不够"）。维度级 gap 可以直接对应到 Coze 工作流的一个探针方向。字段级 gap 会碎片化，无法聚合出模式。

### 为什么离线聚合而不是在线学习？

在线学习（每跑一次就调一次）会把噪声当信号。一次管线运行的 gap 可能是偶然的（LLM 那次没搜到）。聚合 20+ 次运行后的频次模式才是真正的系统性缺口。

### 为什么 confidence scoring 是 1-5 而不是 1-10？

1-5 够用——区分"完全空"(1)、"有信息但不够"(3)、"充分"(5)。1-10 的精细度对 LLM 自评没有意义——LLM 区分不了"6 还是 7 的置信度"。
