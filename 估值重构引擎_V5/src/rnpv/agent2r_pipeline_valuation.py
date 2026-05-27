"""
Agent-2r 管线估值 (PipelineValuation) — rNPV 管线

一次 LLM 调用完成两段式估值:
  1. 成熟产品估值 (已在销售的产品,用 PS/PE)
  2. 在研管线估值 (临床阶段药品,用 rNPV: PoS × 峰值销售 × 折现)
  3. 市场隐含 PoS 对比 (当前市值反推市场给管线的隐含成功率)

不依赖 10 模型路由——创新药的估值公式只有一个: 成熟产品 + Σ(PoS × 峰值销售折现)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from valuation_utils import call_deepseek


# ═══════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════

RNPV_VALUATION_PROMPT = """你是创新药估值分析师。你的任务是做两段式估值。

# 估值框架

## 第一段: 成熟产品估值

已获批/已上市的产品，根据盈利状态选择:
- 稳定盈利 → 用 PE (参照同类药企或行业中枢)
- 微利/盈亏平衡 → 用 PS (参照同类药企的 PS 中枢)
- 仅有一个产品且数据来自合并报表 → 用合并利润/收入,标注 limitations

## 第二段: 在研管线 rNPV 估值

对每个在研管线药物:
```
风险调整现值 = PoS × 峰值销售 × (1 / (1 + 折现率)^年到峰值) × 成功率调整
```

### PoS 估计基准 (按临床阶段):
| 阶段 | 基准 PoS | 调节因素 |
|------|:------:|------|
| Ph1 | 8-12% | 靶点验证度、同类药物历史 |
| Ph2 | 15-25% | 概念验证数据、ORR/PFS 优劣 |
| Ph3 | 50-65% | 同类靶点历史通过率、竞品进度 |
| NDA | 75-90% | 审评风险、CMC 完备度 |

**调节规则**:
- 同类靶点历史通过率高 → +5-10ppt
- 进度明显落后竞品 → -5-10ppt
- First-in-class 无历史参照 → -5-10ppt
- 已有阳性 Ph2 数据 → +5-10ppt

### 峰值销售估计:
- 从 Volc 搜索结果和 Coze 预研中提取分析师预估
- 参照同类药物的实际销售
- 考虑适应症人群规模、定价、渗透率、竞争格局
- 保守原则: 有分析师预估就用范围中值,没有就自己估算

### 折现率:
- Ph3: 12-15%
- Ph2: 15-18%
- Ph1: 18-22%
- 反映管线风险——比公司 WACC 高

## 第三段: 市场隐含 PoS 对比

```
成熟产品估值 = PE/PS 估值
当前市值 - 成熟产品估值 - 净现金 = 市场给管线的隐含估值
隐含管线估值 / 你的管线估值(未折现) = 市场隐含 PoS
```

- 如果市场隐含 PoS 远高于你的估计 → 事件已充分计价,甚至过度计价
- 如果市场隐含 PoS 远低于你的估计 → 市场尚未充分定价管线
- 如果 PoS 差异在 10-15ppt 内 → 基本公允

# 输出格式

```json
{
  "mature_products_value": {
    "total_value_yi": XX,
    "method": "PE/PS说明",
    "details": [{"product": "产品名", "value_yi": XX, "method": "PE/PS"}],
    "confidence": "high|medium|low",
    "limitations": ["合并报表无法拆分个体产品"]
  },

  "pipeline_valuation": [
    {
      "drug": "药品名/管线代号",
      "target_indication": "靶点-适应症",
      "clinical_phase": "Ph1|Ph2|Ph3|NDA",
      "pos_estimate": 0.XX,
      "pos_rationale": "PoS依据(靶点历史/数据优劣/竞争位置)",
      "peak_sales_yi": XX,
      "peak_sales_rationale": "峰值销售依据(TAM/份额/参照)",
      "time_to_peak_years": X,
      "discount_rate_pct": XX,
      "risk_adj_pv_yi": XX
    }
  ],

  "pipeline_summary": {
    "total_pipeline_count": X,
    "total_risk_adj_pv_yi": XX,
    "key_value_drivers": ["驱动管线价值的核心药品"],
    "key_risks": ["主要管线风险"],
    "confidence": "low (Ph3数据来自Volc搜索,非一手)"
  },

  "sotp_total": {
    "mature_products_yi": XX,
    "pipeline_yi": XX,
    "net_cash_yi": XX,
    "total_fair_value_yi": XX,
    "current_mcap_yi": XX,
    "upside_pct": XX
  },

  "implied_pos_check": {
    "market_implied_pipeline_value_yi": XX,
    "our_pipeline_value_yi": XX,
    "implied_pos_gap": "市场隐含PoS约为XX%,我们的估计为XX%",
    "priced_in_assessment": "fully|partially|not_priced",
    "priced_in_rationale": "说明理由"
  },

  "event_profile": {
    "distribution_shape": "wide_bimodal|wide_bimodal_date_anchored|wide_unimodal",
    "timing_certainty": X,
    "outcome_binaryness": X,
    "precedent_richness": X,
    "shape_rationale": "创新药管线估值天然具备高二元性(批准/拒绝)"
  }
}
```

# 核心约束
1. PoS 和峰值销售必须有依据(引用 Volc 搜索结果或 Coze 预研)
2. 不虚构管线——仅使用搜索结果和预研中明确提到的药物
3. 成熟产品估值保守——不给没有分拆数据的业务过高估值
4. 输出纯 JSON
"""


# ═══════════════════════════════════════
# 用户消息构建
# ═══════════════════════════════════════

def _build_rnpv_user_message(
    pipeline_data: dict,
    event_data: dict,
) -> str:
    """构建 Agent-2r 用户消息。"""
    fin = pipeline_data.get("company_financials", {})
    mature = pipeline_data.get("mature_products", [])
    volc = pipeline_data.get("volc_search_results", {})
    drugs = pipeline_data.get("pipeline_drugs_hint", [])

    stock_code = pipeline_data.get("stock_code", "")
    stock_name = pipeline_data.get("stock_name", "")

    # Volc 搜索结果
    volc_text = ""
    for k, v in volc.items():
        if v:
            volc_text += f"\n### {k}\n{v[:3000]}\n"

    # 成熟产品
    mature_text = ""
    for mp in mature:
        mature_text += f"- {mp.get('name','?')}: 营收{mp.get('revenue_ttm_yi',0)}亿 净利{mp.get('profit_ttm_yi',0)}亿 ({mp.get('valuation_hint','?')})\n"

    msg = f"""# 管线估值: {stock_name}({stock_code})

## 公司财务概况
- 市值: {fin.get('market_cap_yi',0)}亿
- 现金: {fin.get('cash_yi',0)}亿 | 负债: {fin.get('debt_yi',0)}亿 | 净现金: {fin.get('net_cash_yi',0)}亿
- 营收TTM: {fin.get('revenue_ttm_yi',0)}亿 | 净利润: {fin.get('net_profit_ttm_yi',0)}亿
- 烧钱状态: {fin.get('burn_rate_hint','?')}

## 成熟产品 (已上市)
{mature_text if mature_text else '合并报表层面有收入,但无分产品拆分数据'}

## 管线信息 (从 Coze 预研提取)
识别到的管线药物: {drugs if drugs else '未提取到具体药名,请从预研文本中识别'}

## Volc 知识搜索结果
{volc_text if volc_text else '(无搜索结果——可能公司不在火山知识库覆盖范围)'}

## Coze 预研原文 (补充信息)
### 投资主题
{event_data.get('investment_theme','')[:2000]}

### 行业研究/知识补充
{event_data.get('knowledge_supplement','')[:1500]}

### 事件原文
{event_data.get('raw_event_text','')[:1500]}

请按两段式估值框架完成分析。输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# Agent-2r 主类
# ═══════════════════════════════════════

class PipelineValuation:
    """管线估值 — rNPV Agent-2r。"""

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key

    def run(
        self,
        pipeline_data: dict,
        event_data: dict | None = None,
    ) -> dict:
        """
        执行两段式管线估值。

        pipeline_data: Agent-1r 输出
        event_data: Coze Agent0 预研

        返回: {mature_products_value, pipeline_valuation, sotp_total, implied_pos_check, event_profile}
        """
        event_data = event_data or {}
        user_msg = _build_rnpv_user_message(pipeline_data, event_data)

        result = call_deepseek(
            RNPV_VALUATION_PROMPT, user_msg,
            max_tokens=30720, temperature=0.1,
            api_key=self.api_key,
        )

        if "_parse_error" in result:
            result = call_deepseek(
                RNPV_VALUATION_PROMPT, user_msg,
                max_tokens=30720, temperature=0.1,
                api_key=self.api_key,
            )

        if "_parse_error" in result:
            return {"_error": "LLM调用失败,无法完成管线估值", "_fallback": True}

        return result


# ── 便捷函数 ──

def value_pipeline(pipeline_data: dict, event_data: dict | None = None) -> dict:
    """便捷入口：运行管线估值。"""
    val = PipelineValuation()
    return val.run(pipeline_data, event_data)
