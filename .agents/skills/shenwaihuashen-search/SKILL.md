---
name: shenwaihuashen-search
description: 联网搜索验证行业动态、公司新闻、政策变化。决策前的"最后信息确认"——确保没有遗漏的最新信息影响判断。
tools:
  - WebSearch
  - WebFetch
---

# 联网搜索 Skill

## 触发条件
- 做投资决策前必须调用
- 用户要求"查一下最新消息"
- evolve skill 检测到需要验证的假设
- 上一次搜索超过 7 天

## 输入

从主 Agent 或 decision skill 获取：
- `stockName`: 股票名称
- `stockCode`: 股票代码
- `sector`: 所属产业链/行业
- `focusAreas`: 重点关注领域（可选，如"政策""竞争""订单""产能"）

## 搜索策略

按以下顺序执行搜索，每条搜索用 WebSearch：

1. `"{stockName}" "{stockCode}" 最新动态 2026` — 最新公司新闻
2. `"{stockName}" 财报 业绩 2026` — 最新财务表现
3. `"{sector}" 行业政策 最新 2026` — 行业政策变化
4. `"{stockName}" 风险 负面 减持 诉讼` — 负面信号
5. `"{stockName}" 订单 签约 客户 产能` — 经营进展

如果某条搜索结果中有高价值链接，用 WebFetch 深入阅读。

## 输出

```json
{
  "searchDate": "YYYY-MM-DD",
  "positiveSignals": ["具体发现，含来源"],
  "negativeSignals": ["具体发现，含来源"],
  "neutralDevelopments": ["值得关注但方向不明"],
  "keyDevelopments": "最重要的1-3条发展，每条≤80字",
  "impactAssessment": "正面/中性/负面/复杂",
  "confidenceInResults": "高/中/低",
  "informationGaps": ["搜索未覆盖到的重要问题"],
  "sources": ["url1", "url2"]
}
```

## 注意事项

- 优先来自公司公告、交易所披露、权威财经媒体的信息
- 对雪球/微博等社区信息标注"低置信"
- 如果搜索结果与已有数据矛盾，标注矛盾点并建议优先采信一手信息源
- 注意区分"预期"和"已发生"——"预计Q3签约"不等于"已签约"
