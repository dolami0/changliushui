---
name: shenwaihuashen-data-verify
description: 从 Coze 五大古籍数据库读取并交叉验证个股关键数据。不依赖前端 cozeApi.ts——直接通过 curl 调用 Coze API 读取同一数据源。
tools:
  - Bash
  - Read
---

# 数据验证 Skill

## 触发条件
- 每次投资决策前自动调用
- 用户提供新的个股标的时
- 追踪检查时发现财务数据需要更新

## 数据源（Coze 五大古籍）

Coze API 基址: `https://api.coze.cn/v1/databases`
Token: 通过环境变量 `COZE_TOKEN` 注入

| 数据库 | ID | 内容 |
|--------|-----|------|
| 藏经阁 | 7611455655748304896 | 个股预研报告（背景/分析/高收益机会/综合评分/潜力涨幅/产业链） |
| 天机卷 | 7479116110479048754 | 产业新闻事件（新闻内容/知识库/等级/模式） |
| 万业谱 | 7639784337973477386 | 行业专家研究/投资地图（Agent 0 产出） |
| 定数录 | 7640094415800860724 | 估值报告（情景概率/不对称比/概率加权涨幅/估值锚定） |
| 因果簿 | 7640928034144698374 | 产业链分析结果（top_pick/产业链节点/事件分析） |

## 验证项目

### 1. 藏经阁 — 个股预研
```bash
curl -s -X POST "https://api.coze.cn/v1/databases/7611455655748304896/records/query" \
  -H "Authorization: Bearer $COZE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"page_size":50, "order_by":[{"direction":"desc","field_name":"bstudio_create_time"}]}'
```

验证项：
- `comprehensive_score`: 综合评分是否 >=50
- `potential_increase`: 潜力涨幅是否合理
- `cylfx`: 产业链分类是否正确
- `background` / `analysis_report`: 预研深度是否充分
- `is_analyzed`: 是否已被推演过

### 2. 定数录 — 估值报告（如果有）
```bash
curl -s -X POST "https://api.coze.cn/v1/databases/7640094415800860724/records/query" \
  -H "Authorization: Bearer $COZE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"page_size":200, "order_by":[{"direction":"desc","field_name":"bstudio_create_time"}]}' | python3 -c "import sys,json; data=json.load(sys.stdin); items=[i for i in data.get('data',{}).get('items',[]) if str(i.get('stock_code',''))=='{stock_code}'[:6]]; print(json.dumps(items[:1], ensure_ascii=False, indent=2))"
```

验证项：
- `quality_flag`: HIGH_QUALITY / MEDIUM_QUALITY / LOW_QUALITY
- `asymmetry_ratio`: 不对称比是否 >2.0
- `prob_weighted_upside_pct`: 概率加权涨幅
- `confidence_score`: 置信度评分
- 三情景 (base/bull/bear) 的概率和参数是否合理

### 3. 因果簿 — 产业链分析（如果有）
- `top_pick_score`: 该股票是否是产业链首选
- `chain_analysis_json`: 产业链节点利润截留分析

## 输出

```json
{
  "dataTimestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "cangjingge": {
    "found": true,
    "comprehensiveScore": 0,
    "potentialIncrease": "",
    "cylfx": "",
    "hasFullReport": false
  },
  "dingshulu": {
    "found": false,
    "qualityFlag": "",
    "asymmetryRatio": 0,
    "probWeightedUpsidePct": 0
  },
  "yinguobu": {
    "found": false,
    "isTopPick": false,
    "topPickScore": 0
  },
  "crossValidation": {
    "dataConsistency": "一致/有矛盾",
    "discrepancies": ["如有矛盾，列举"],
    "dataCompleteness": "高/中/低"
  },
  "redFlags": ["质押率过高", "连续亏损", "数据缺失严重"],
  "greenFlags": ["多表数据一致支撑", "定数录评为高质量", "因果簿验证产业链卡位"]
}
```

## 注意事项

- 如果藏经阁数据为空或过旧（>30天），标记 `dataCompleteness: "低"`
- 如果同一股票在多个表中的数据矛盾，标注具体矛盾点
- 不要修改原始数据，只做验证和标注
