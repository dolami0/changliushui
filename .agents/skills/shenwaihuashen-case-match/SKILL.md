---
name: shenwaihuashen-case-match
description: 从过往十倍股案例库中匹配最相似案例，提取经验教训。不是机械比较——你是分析师，案例是你的"追问工具"。
tools:
  - Read
  - Glob
  - Grep
---

# 案例匹配 Skill

## 触发条件
- 每次投资决策前调用
- 用户要求"看看历史上类似的情况"
- evolve skill 做跨案例模式提炼时

## 输入

从主 Agent 获取当前标的的特征画像：
- `stockName`, `stockCode`, `sector` (产业链)
- `tags` (从藏经阁/预研中提取的关键标签)
- `expectedReturnType` (预期的回报类型：渗透率爆发/业绩拐点/周期反转/范式切换)
- `mcapBillion` (当前市值)
- `roicPct` (当前 ROIC)

## 匹配算法（6 维加权）

### 维度 1: 产业链/行业匹配 (权重 30%)
从 `memory/_index.json` 的 `caseIndex` 中，对每个案例计算 `sector` 字段与当前标的产业链的重叠度。

### 维度 2: 终态/回报类型匹配 (权重 20%)
匹配 `returnType` 字段：渗透率爆发型、业绩拐点型、周期反转型、范式切换型、资产重估型。

### 维度 3: decagenome 标签匹配 (权重 15%)
Jaccard 相似度：当前标签集合 vs 案例的 `decagenomeTags` 和 `tags`。

### 维度 4: 催化剂类型匹配 (权重 15%)
从案例的 `catalyst` 字段提取关键词（政策/订单/产能/审批/涨价），与当前标的催化剂做关键词重叠。

### 维度 5: 宏观环境匹配 (权重 10%)
匹配 `macroRegime` 字段：宽松/紧缩/中性。

### 维度 6: 驱动因子匹配 (权重 10%)
匹配 `primaryDriver` 和 `dominantFactor`。

## 工作流

1. 读取 `memory/_index.json` 获取案例索引
2. 对每个案例的摘要字段做粗筛（排除完全不相关的）
3. 对初筛通过的案例（通常 10-15 个），读取完整 JSON 做 6 维评分
4. 返回 Top 5 匹配，对每个做深度比对

## 输出

```json
{
  "matchedAt": "YYYY-MM-DDTHH:MM:SSZ",
  "topMatches": [
    {
      "caseId": "case-001",
      "stockName": "某新能源材料",
      "stockCode": "68xxxx",
      "similarityScore": 0.82,
      "dimensionScores": {
        "sector": 0.9,
        "returnType": 0.8,
        "decagenome": 0.7,
        "catalyst": 0.6,
        "macroRegime": 0.5,
        "driver": 0.8
      },
      "keySimilarities": ["同属新能源上游材料", "都是渗透率拐点驱动", "同样绑定下游龙头"],
      "keyDifferences": ["当前标的市值更小（弹性更大）", "当前竞争格局更分散（卡位确定性弱于案例）"],
      "lessonsApplicable": [
        "渗透率突破拐点后，龙头会享受 6-12 个月的量价齐升窗口期",
        "这个阶段的估值从 PE 切换到 PS 再到 PEG，倍数逐步压缩是正常现象"
      ],
      "referenceMetrics": {
        "gainMultiple": 10.0,
        "roicImprovement": null,
        "peExpansion": null,
        "maxDrawdownPct": null
      },
      "comprehensiveDiscountPct": 70
    }
  ],
  "summaryStats": {
    "avgGainMultiple": 10.0,
    "medianGainMultiple": 10.0,
    "avgMaxDrawdown": "N/A",
    "commonSuccessFactors": ["渗透率拐点", "龙头绑定"],
    "commonFailureModes": ["数据不足"]
  }
}
```

## 6 维判断（对每个匹配案例）

对 Top 5 中的每个案例，从以下 6 个维度判断当前标的是"优于/相似/劣于"案例当时的情景：

1. **驱动强度** — 事件本身的爆发力。硬证据（已签约/已交付）> 预期（有望/规划）
2. **市场空间** — TAM 天花板。万亿全球市场 > 百亿利基市场
3. **卡位壁垒** — 竞争护城河的宽度。唯一供应商 > 多家混战中的一家
4. **范式切换** — 估值体系迁移的彻底度。代工→品牌 > 边际效率改善
5. **催化剂密度** — 未来 3-12 个月可预见的验证节点数量和确定性
6. **失败风险** — 最可能证伪当前逻辑的路径及概率

每个维度输出："优于/相似/劣于" + ≤30 字理由。

综合折扣率 = 基于 6 维判断给出：6 维全优于→85-100%，全劣于→10-25%。

## 注意事项

- 案例不是锚点——你是用案例来追问当前标的，不是让当前标的去拟合案例
- 折扣率必须与 6 维判断的方向一致（不能 6 维全劣于却给 80% 折扣率）
- 如果没有案例匹配（新产业/新模式），标注"NoPrecedent"并说明
- 案例库会随时间增长，定期（每新增 5 个案例）重新审视之前的匹配结果是否仍然成立
