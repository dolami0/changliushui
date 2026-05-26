---
name: shenwaihuashen-evolve
description: 复盘决策与实际结果的偏差，更新灵光和案例库，驱动 Agent 自我进化。这是身外化身最重要的 skill——没有进化能力的 Agent 只是重复犯错的机器。
tools:
  - Read
  - Write
  - Bash
  - Glob
---

# 进化学习 Skill

## 触发条件
1. 用户显式要求"复盘"或"进化"
2. 追踪文件中的 `nextReviewDate` 到期
3. 追踪中的股票价格触及预警线（回撤 >15% 或 涨幅 >50%）
4. 追踪中的标的到达退出条件（清仓后触发终局复盘）
5. 案例库新增 5+ 案例后（触发跨案例模式提炼）

## 工作流

### Step 1: 读取当前状态

- 读取指定 tracking 文件（或所有 active tracking）
- 读取相关 decision 报告
- 读取 `memory/_index.json` 获取案例库概况

### Step 2: 偏差分析

对比决策时的预测 vs 当前实际：

| 维度 | 预测 | 实际 | 偏差 | 评级 |
|------|------|------|------|------|
| 价格表现 | +X% | +Y% | | 超预期/符合/低于 |
| 关键事件 | 预计Q2签约 | 实际Q3才签约 | 延迟 | 部分成立 |
| ROIC改善 | +5ppt | +2ppt | -3ppt | 低于预期 |
| 最大回撤 | <20% | -35% | 超预期 | 更差 |

### Step 3: 归因分析

对每个重大偏差，判断原因：
- **逻辑错误**：核心投资逻辑本身就是错的（如行业判断错误）
- **时间错判**：逻辑对但节奏错（来得太早或太晚）
- **外生冲击**：不可预见的外部事件（政策突变/黑天鹅）
- **信息不足**：决策时缺乏的关键信息，现在补上了

### Step 4: 更新记忆

#### 更新追踪文件
在 tracking 文件中追加 `reassessmentNotes`、更新 `assumptionValidation`、记录 `priceTracking`。

#### 更新/新增灵光
如果发现了可复用的规律：
- 新规律 → 创建新的灵光文件
- 修正已有认知 → 更新灵光的 `content` + 追加 `revisionHistory`

#### 升级案例（终局复盘时）
如果追踪标的已退出：
1. 将 tracking 文件中的完整数据转换为 case 格式
2. 补充 `memory/cases/case-{slug}.json` 的 50+字段
3. 将 tracking 文件移到归档目录或标记 `status: "exited"`
4. 更新 `memory/_index.json`

### Step 5: 跨案例模式提炼（条件触发）

当案例库 ≥ 10 个案例时，运行统计分析：
```bash
# 从所有案例中提取模式
python3 -c "
import json, os, glob
from collections import Counter
...
"
```

统计：
- 各 `returnType` 的平均回报和胜率
- 各 `primaryDriver` 的出现频率和平均回报
- 高频 `decagenomeTags` 组合的胜率
- `failureMode` 中出现最多的失败原因

输出模式报告 → `output/pattern-report-{date}.md`

### Step 6: 输出进化摘要

将本次进化的发现和记忆更新输出到 `output/journals/journal-{date}.md`。

## 输出

```json
{
  "evolvedAt": "YYYY-MM-DDTHH:MM:SSZ",
  "triggerType": "定期复盘 / 偏差触发 / 退出复盘 / 显式请求",
  "ticker": "",
  "decisionAge": "决策至今 X 天",
  "performance": {
    "actualReturnPct": 0,
    "predictedUpsidePct": 0,
    "deviation": 0
  },
  "attribution": {
    "logicCorrect": true,
    "timingCorrect": false,
    "externalShock": false,
    "informationGap": true,
    "mainError": "一句话总结主要偏差原因"
  },
  "learnings": ["新学到的规律 1", "新学到的规律 2"],
  "memoryUpdates": {
    "lingguangAdded": [],
    "lingguangModified": [],
    "caseUpgraded": "",
    "trackingUpdated": true
  },
  "compositeEvolveScore": {
    "predictionAccuracy": 0-100,
    "learningQuality": 0-100,
    "note": "预测准确率+学习质量综合评估"
  }
}
```

## 注意事项

- 进化不是为了证明"我当初是对的"——诚实面对偏差，宁可推翻自己的判断
- 外生冲击不归因于逻辑错误，不要在随机事件中找规律
- 灵光的修订要谨慎——一次失败不足以推翻一条经过多次验证的铁律
- 案例升级时确保数据完整——一个残缺的案例比没有案例更危险
