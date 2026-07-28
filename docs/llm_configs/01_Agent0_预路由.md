# Agent-0: 预路由 (Pre-Router)

> **类型**: 规则引擎（无 LLM 调用）
> **文件**: `src/agent0_pre_router.py` (280 行)
> **触发**: 管线第一步

---

## 配置

```python
# 无 LLM 调用 — 纯规则引擎
# 输入: 行业分类 + 事件标签 + 预研语料
# 输出: 数据需求清单 (Agent-1 的输入)
```

## 核心逻辑

### 1. 行业分类 → 专项数据包映射

| 行业 | 专项数据 |
|------|---------|
| 医药/生物 | pipeline（管线进度/临床数据/峰值销售） |
| 有色金属/矿业 | reserves（资源储量/品位/开采成本） |
| 电子/半导体 | capacity（产能/良率/利用率/设备明细） |
| 软件/互联网 | subscribers/ARPU（用户数/付费率/客单价） |
| 银行/金融 | NPL（不良率/拨备覆盖率/净息差） |
| 化工 | capacity/utilization（产能/开工率/价差） |
| 房地产 | NAV（项目储备/土储/净负债） |
| REITs | 物业组合/租金/出租率 |

### 2. 事件标签 → 数据优先级提升

| 事件标签 | 提升的数据包 |
|---------|------------|
| 产能释放 | capacity → core/mandatory |
| 壳重组 | restructuring → core/mandatory |
| 管线进展 | pipeline → core/mandatory |
| 政策催化 | policy → specialized/optional |
| 困境反转 | distress → specialized/optional |

### 3. 模型提示（非绑定）

`_infer_model_hint()` 根据行业+事件给出非绑定模型类别提示：
- 医药+管线 → "rNPV/管线估值"
- 矿业+资源 → "NAV/资源储量"
- 亏损+高增长 → "PS+TAM"

> **注意**: 这只是提示，最终模型选择由 Agent-2 统一路由判官决定。

## 输出结构

```python
{
    "stock_code": str,
    "stock_name": str,
    "industry": str,
    "event_tags": list[str],
    "data_requirements": {
        "core_mandatory": ["quote", "valuation", "income", ...],
        "specialized_optional": ["segment", "consensus", ...],
        "optional_ignore": [...]
    },
    "model_hint": str,  # 非绑定提示
    "research_context": str  # 预研语料摘要
}
```

## 原则

- 不做估值判断 — 只列出"需要什么数据"
- 行业专项数据包尽量减少误配（少抓比多抓好）
- 事件标签来自 Coze 万业谱管线的 N1 节点输出
