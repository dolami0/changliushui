# 分支管线: SOTP 分部估值 & rNPV 创新药估值

> **触发条件**: Agent-2 统一路由判官选择 primary_model=J (SOTP) 或 primary_model=F (rNPV)
> **设计原则**: 分支管线复用主 Agent-3 的 LLM 配置模式，但替换参数体系和模型公式

---

## 一、SOTP 管线 (primary_model=J)

> **文件**: `src/agent3s_sotp.py` (2475 行)

### 触发条件

Agent-2 判定:
1. 公司有两个或以上业务需不同估值锚（PE vs PS vs PB vs rNPV）
2. 混在一起用单一模型会产生系统性偏差
3. 新业务有可独立估值的锚点

### 架构

```
Agent-3s LLM-1: 分部参数推导
  └── 每个分部独立赋参数（各自的锚类型 + 模型）
       ↓
代码计算: 每个分部独立计算估值 → 加总 + 净现金
       ↓
Agent-3s LLM-2: 多轮搜索审阅
  └── 火山引擎 + Bocha → 验证分部数据 → 修改参数 → 最终报告
```

### LLM 配置（与主 Agent-3 相同）

```json
{
  "model": "deepseek-v4-pro",
  "endpoint": "https://api.deepseek.com/chat/completions",
  "max_tokens": 40960,
  "temperature": 0.1,
  "thinking": {"type": "enabled"},
  "reasoning_effort": "max",
  "stream": false,
  "timeout": 600
}
```

### 5 种分部锚类型

| 分部锚 | 适用场景 | 估值方法 |
|--------|---------|---------|
| earnings | 有稳定盈利的成熟业务 | PE / DCF |
| revenue | 高增长但微利/亏损的新业务 | PS × TAM |
| asset | 重资产/资源型业务 | PB / NAV |
| pipeline | 创新药/在研产品 | rNPV |
| dcf | 有明确现金流预测的业务 | 两阶段 DCF |

### 关键规则

1. 事件驱动的分部 → 锚落在事件改变的那个维度
2. 非事件驱动的分部 → 按自身业务特征独立判定
3. 净现金/净负债最后加总
4. 跨分部重复计算检查（如同一客户收入不能在不同分部重复估值）

---

## 二、rNPV 管线 (primary_model=F)

> **文件**: `src/rnpv/agent1r_pipeline_data.py` (323 行) + `src/rnpv/agent2r_scenario.py` (1121 行)

### 触发条件

Agent-2 判定 primary_model=F（创新药/生物科技，管线驱动估值）

### 架构

```
Agent-1r: PipelineDataAssembler
  └── 火山引擎搜索（通用 + 每药物深入）
       ↓
  Flash 模型提取 → 结构化管线数据
  (药物名称/阶段/适应症/峰值销售/PoS/时间线)
       ↓
Agent-2r: RnpvScenarioValuation (V7)
  ├── LLM-1: 管线参数推导
  │     └── 每药物: 成功率(PoS) + 峰值销售 + 上市时间 + 折现率
  ├── 代码计算: rNPV = Σ(PoS × 峰值 × 专利期倍数 / (1+r)^t)
  │     └── 成熟业务: PE/PS 估值
  │     └── 加总: 成熟业务 + 管线 rNPV + 净现金
  └── LLM-2: 审阅 + 搜索验证
        └── 验证临床数据/竞争格局/定价假设
```

### rNPV 核心公式

```
rNPV = Σ [ PoS_i × Peak_Sales_i × Patent_Multiple / (1 + r)^t_i ]
```

- **PoS** (Probability of Success): 按临床阶段赋值（Phase I ~15%, Phase II ~25%, Phase III ~55%, NDA ~80%）
- **Peak Sales**: 峰值年销售额
- **Patent Multiple**: 固定 3× 峰值销售（专利期内独占价值）
- **r**: 折现率（通常 10-12%，考虑管线失败风险）
- **t**: 到峰值销售的年数

### SOTP 结构（每情景）

```
总估值 = 成熟业务估值 + Σ(管线药物 rNPV) + 净现金
```

### PipelineDataAssembler LLM 配置

```json
{
  "model": "deepseek-v4-flash",
  "max_tokens": 8192,
  "temperature": 0.0,
  "thinking": {"type": "enabled"}
}
```

搜索: 火山引擎 Agent API — 通用搜索 + 每药物深入搜索 (并行)

### RnpvScenarioValuation LLM 配置

与主 Agent-3 完全相同:
- LLM-1: `deepseek-v4-pro`, temp=0.1, thinking=enabled, reasoning_effort=max
- LLM-2: `deepseek-v4-pro`, temp=0.1, thinking=enabled, 多轮搜索审阅

---

## 三、分支管线的代码注入

主编排器 `orchestrator.py` 中的分叉逻辑:

```python
# rNPV 分叉
if routing_decision["primary_model"] == "F":
    if _RNPV_AVAILABLE:
        pipeline_data = PipelineDataAssembler(...).assemble(stock_code)
        result = RnpvScenarioValuation(...).run(pipeline_data, ...)
    else:
        # 降级到主 Agent-3（用简化管线参数）
        result = ScenarioAsymmetry(...).run(data_package, ...)

# SOTP 分叉
elif routing_decision["primary_model"] == "J":
    if _SOTP_AVAILABLE:
        result = SOTPScenarioAsymmetry(...).run(data_package, ...)
    else:
        # 降级到主 Agent-3
        result = ScenarioAsymmetry(...).run(data_package, ...)
```

条件导入设计: 分支模块导入失败时不影响主管线运行。
