---
name: shenwaihuashen-quant
description: 计算十倍股核心量化指标：不对称比、ROIC改善潜力、市值弹性、decagenome相似度。纯计算型 skill，不调用外部 API。
tools:
  - Read
  - Bash
---

# 量化指标 Skill

## 触发条件
- 每次投资决策前调用
- 案例匹配后，需要量化锚点来校准直觉

## 输入

从主 Agent 获取：
- 当前标的的估值数据（来自 data-verify skill 的输出）
- 案例匹配结果（来自 case-match skill 的输出）

## 核心指标计算

### 1. 不对称比 (Asymmetry Ratio)

```
asymmetry = |概率加权涨幅| / |概率加权跌幅|

其中：
- 概率加权涨幅 = bull.probability × bull.upside + base.probability × max(base.upside, 0)
- 概率加权跌幅 = bear.probability × |bear.upside| + base.probability × |min(base.upside, 0)|

基准：
- >3.0 → 强不对称（极力推荐）
- >2.0 → 良好不对称（值得关注）
- >1.5 → 尚可（需其他信号支撑）
- <1.5 → 不对称不足
```

### 2. ROIC 改善潜力

```
roicGap = 同行业龙头ROIC中位数 - 当前ROIC
roicImprovementRef = 案例库中同终态案例的ROIC改善幅度中位数

若 roicGap > 5 且 roicImprovementRef > 5:
  roicImprovementPotential = min(roicGap, roicImprovementRef) × 折扣率

折扣率 = 基于事件确定性（硬证据0.9，认证0.7，传闻0.4）
```

### 3. 市值弹性 (Market Cap Elasticity)

```
mcapElasticity = (目标涨幅%) / ln(当前市值(亿) / 案例库起始市值中位数(亿))

基准：
- >8 → 小市值+大产业，弹性极强
- >5 → 良好弹性
- >3 → 弹性一般
- <3 → 市值偏大或产业空间不足
```

### 4. 基因相似度 (Decagenome Similarity)

从 `memory/_index.json` 读取所有案例的标签，计算 Jaccard 相似度：

```
similarity = |当前标签 ∩ 案例标签| / |当前标签 ∪ 案例标签|
```

取相似度最高的 10 个案例，计算：
- 平均回报
- 胜率（正回报比例）
- 最大回撤中位数

### 5. 综合赔率评分

```
compositeScore = (
  normalize(asymmetry, [1, 5], [0, 40]) +
  normalize(roicImprovementPotential, [0, 15], [0, 20]) +
  normalize(mcapElasticity, [2, 10], [0, 20]) +
  normalize(decagenomeAvgReturn, [1, 10], [0, 20])
)

分数区间: 0-100
>80: 顶级赔率
60-80: 高赔率
40-60: 中等
<40: 不足
```

## 输出

```json
{
  "asymmetryRatio": 3.2,
  "asymmetryLabel": "强不对称",
  "roicImprovementPotential": 8.5,
  "roicGapToLeader": 12.0,
  "roicDiscountFactor": 0.7,
  "marketCapElasticity": 6.8,
  "mcapElasticityLabel": "良好弹性",
  "decagenomeSimilarity": {
    "topMatchId": "case-001",
    "topMatchSimilarity": 0.72,
    "top10AvgReturn": 6.5,
    "top10WinRate": 0.70,
    "top10MedianDrawdown": 35
  },
  "compositeScore": 72,
  "compositeVerdict": "高赔率"
}
```

## 注意事项

- 所有计算输出到 stdout，用 Bash 执行 Python 单行脚本完成
- NaN 或 Inf 时返回 null，不阻塞决策流
- 如果定数录已有计算过的指标，优先采信并标注来源
