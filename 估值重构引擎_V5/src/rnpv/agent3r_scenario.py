"""
Agent-3r 情景推演 (PipelineScenario) — rNPV 管线

基于 Agent-2r 的管线估值结果，做 rNPV 专项三情景推演。

rNPV 情景推演和标准管线的关键差异:
  - 参数体系: PoS/峰值销售/折现率 替代 PE/PS/PB
  - bear 有硬底: 现金 + 成熟产品清算价值
  - 概率结构: 创新药天然是 wide_bimodal — 成药或不成药
  - "已发生事实"界限清晰: Ph1/Ph2 已过是事实，Ph3 结果是未知
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from valuation_utils import call_deepseek


# ═══════════════════════════════════════
# System Prompt
# ═══════════════════════════════════════

RNPV_SCENARIO_PROMPT = """你是创新药情景推演分析师。Agent-2r 已完成管线的基础估值，
你的任务是基于管线估值结果，做三情景推演——判断不同情景下管线价值如何变化。

# rNPV 情景框架

创新药管线价值的驱动变量:
- **PoS (成功率)**: 临床数据好坏 → PoS 上调/下调
- **峰值销售**: 竞争格局/定价/医保 → 峰值销售扩张/收缩
- **时间**: 获批加速/延迟 → 折现影响

## Bear: 核心管线失败

触发条件: 关键临床数据不及预期/未达终点/安全性问题
- 该管线 PoS → 0 (或大幅下调)
- 关联管线被波及 (同靶点/同技术平台可能被连带下调)
- 公司估值底 = 现金 + 成熟产品折价估值 + 其余管线折价 PoS
- **已发生事实不可推翻**: Ph1/Ph2 已过是事实，Ph3 失败不等于之前的数据不存在
- 概率: 基于同类靶点历史失败率

## Base: 管线按预期推进

- PoS 维持 Agent-2r 的估计
- 峰值销售取中位预估
- 时间线按当前临床进度推算
- 概率: 100% - bear - bull

## Bull: 管线超预期

触发条件: Ph3 数据显著优于竞品/获批加速/适应症扩展
- 核心管线 PoS 上调 10-15ppt
- 峰值销售上调 20-50% (适应症扩展/定价超预期)
- 早期管线 (Ph1/Ph2) 因平台验证而 PoS 小幅上调
- 概率: 低——创新药的"超预期"是小概率事件

# 输出格式

```json
{
  "scenario_narratives": {
    "bear": "因果剧本 (<=100字)",
    "base": "因果剧本 (<=100字)",
    "bull": "因果剧本 (<=100字)"
  },

  "scenario_valuation": {
    "bear": {
      "probability": 0.XX,
      "key_assumption_changes": ["管线A PoS 0.55→0", "管线B PoS下调10ppt"],
      "pipeline_value_yi": XX,
      "mature_products_value_yi": XX,
      "net_cash_yi": XX,
      "total_value_yi": XX,
      "upside_pct": XX
    },
    "base": {
      "probability": 0.XX,
      "key_assumption_changes": ["维持Agent-2r估计"],
      "pipeline_value_yi": XX,
      "mature_products_value_yi": XX,
      "net_cash_yi": XX,
      "total_value_yi": XX,
      "upside_pct": XX
    },
    "bull": {
      "probability": 0.XX,
      "key_assumption_changes": ["管线A PoS 0.55→0.70", "峰值销售+30%"],
      "pipeline_value_yi": XX,
      "mature_products_value_yi": XX,
      "net_cash_yi": XX,
      "total_value_yi": XX,
      "upside_pct": XX
    }
  },

  "probability_weighted": {
    "weighted_value_yi": XX,
    "weighted_upside_pct": XX,
    "asymmetry_ratio": X.X
  },

  "confidence": {
    "overall_score": 1-10,
    "overall_label": "高|中|低",
    "key_uncertainties": ["数据来源局限", "管线假设敏感性"],
    "note": "rNPV 置信度天然低于标准管线——Ph2/Ph3 数据非一手"
  },

  "monitoring_triggers": {
    "bull_trigger": "触发bull情景的观测指标",
    "bear_trigger": "触发bear情景的观测指标",
    "frequency": "每季度/临床数据读出时"
  }
}
```

# 概率约束

1. bear 概率 ≥ 同类靶点历史失败率 (通常 35-50% for Ph3)
2. bull 概率: 创新药超预期是小概率 (通常 10-20%)
3. base 概率 = 100% - bear - bull
4. 三情景概率之和 = 1.0

# 核心约束
1. bear 的硬底 = 现金 + 成熟产品 (创新药企业的清算底线)
2. 不推翻 Agent-2r 已估计的 base 估值——作为起点微调
3. 已发生事实不可在 bear 中推翻
4. 输出纯 JSON
"""


# ═══════════════════════════════════════
# 用户消息构建
# ═══════════════════════════════════════

def _build_scenario_user_message(
    pipeline_data: dict,
    valuation_result: dict,
    event_data: dict,
) -> str:
    """构建 Agent-3r 用户消息。"""
    fin = pipeline_data.get("company_financials", {})
    sotp = valuation_result.get("sotp_total", {})
    imp = valuation_result.get("implied_pos_check", {})
    pipe_vals = valuation_result.get("pipeline_valuation", [])
    mature = valuation_result.get("mature_products_value", {})
    evp = valuation_result.get("event_profile", {})

    # 管线摘要
    pipe_text = ""
    for p in pipe_vals:
        pipe_text += (
            f"- {p.get('drug','?')}: {p.get('clinical_phase','?')} "
            f"PoS={p.get('pos_estimate',0):.0%} "
            f"峰值={p.get('peak_sales_yi',0)}亿 "
            f"风险调整PV={p.get('risk_adj_pv_yi',0):.1f}亿\n"
        )

    msg = f"""# rNPV 情景推演: {pipeline_data.get('stock_name','?')}({pipeline_data.get('stock_code','?')})

## Agent-2r 估值结果

### 成熟产品
- 估值: {mature.get('total_value_yi','?')}亿 (方法:{mature.get('method','?')})
- 置信度: {mature.get('confidence','?')}

### 在研管线
{pipe_text}

### SOTP 加总
- 成熟产品: {sotp.get('mature_products_yi','?')}亿
- 管线: {sotp.get('pipeline_yi','?')}亿
- 净现金: {sotp.get('net_cash_yi','?')}亿
- 公允价值: {sotp.get('total_fair_value_yi','?')}亿
- 当前市值: {sotp.get('current_mcap_yi','?')}亿
- Base upside: {sotp.get('upside_pct','?')}%

### 市场隐含 PoS
{imp.get('implied_pos_gap','?')}
计价状态: {imp.get('priced_in_assessment','?')}

### 事件光谱
分布形状: {evp.get('distribution_shape','?')}

## 公司财务
- 现金: {fin.get('cash_yi',0)}亿 | 负债: {fin.get('debt_yi',0)}亿 | 净现金: {fin.get('net_cash_yi',0)}亿
- 营收: {fin.get('revenue_ttm_yi',0)}亿 | 净利润: {fin.get('net_profit_ttm_yi',0)}亿

## Coze 预研补充
{event_data.get('investment_theme','')[:1000]}

请基于 Agent-2r 的估值完成三情景推演。注意 bear 的硬底 = 现金 {fin.get('net_cash_yi',0)}亿 + 成熟产品折价。
输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# Agent-3r 主类
# ═══════════════════════════════════════

class PipelineScenario:
    """情景推演 — rNPV Agent-3r。"""

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key

    def run(
        self,
        pipeline_data: dict,
        valuation_result: dict,
        event_data: dict | None = None,
    ) -> dict:
        """
        执行 rNPV 情景推演。

        pipeline_data: Agent-1r 输出
        valuation_result: Agent-2r 输出
        event_data: Coze Agent0 预研

        返回: {scenario_narratives, scenario_valuation, probability_weighted, confidence, monitoring_triggers}
        """
        event_data = event_data or {}
        user_msg = _build_scenario_user_message(pipeline_data, valuation_result, event_data)

        result = call_deepseek(
            RNPV_SCENARIO_PROMPT, user_msg,
            max_tokens=20480, temperature=0.1,
            api_key=self.api_key,
        )

        if "_parse_error" in result:
            result = call_deepseek(
                RNPV_SCENARIO_PROMPT, user_msg,
                max_tokens=20480, temperature=0.1,
                api_key=self.api_key,
            )

        if "_parse_error" in result:
            return {"_error": "LLM调用失败", "_fallback": True}

        # ── 代码修正: net_cash 以 2r/财务数据为准，防止 LLM 幻算 ──
        sotp = valuation_result.get("sotp_total", {})
        actual_nc = sotp.get("net_cash_yi", 0)  # 2r 已被代码修正，此为可靠值
        if not actual_nc:
            actual_nc = pipeline_data.get("company_financials", {}).get("net_cash_yi", 0)
        if actual_nc:
            sv = result.get("scenario_valuation", {})
            if isinstance(sv, dict):
                for sn in ("bear", "base", "bull"):
                    s = sv.get(sn, {})
                    if isinstance(s, dict) and s.get("net_cash_yi"):
                        llm_nc = s.get("net_cash_yi", 0)
                        if abs(llm_nc - actual_nc) > 0.5:
                            s["net_cash_yi"] = actual_nc
                            s["total_value_yi"] = round(
                                s.get("pipeline_value_yi", 0) +
                                s.get("mature_products_value_yi", 0) + actual_nc, 1
                            )
                            result["scenario_valuation"][sn] = s

        return result


# ── 便捷函数 ──

def scenario_rnpv(
    pipeline_data: dict,
    valuation_result: dict,
    event_data: dict | None = None,
) -> dict:
    """便捷入口：运行 rNPV 情景推演。"""
    sc = PipelineScenario()
    return sc.run(pipeline_data, valuation_result, event_data)
