# 13-stashed.md 续（2/2）

> 接上一文件，正文连续未删减。

    "step2c_product_restate": "化合物半导体材料: 收入1.38亿(占12.9%,同比+146%),GM=23.2%(vs公司整体20.3%)",
    "step2d_score": 6,
    "score_rationale": "合同负债+在建工程支撑,预告预减(时序错位)不扣分,化合物半导体GM与叙事存在差距但属时序错位"
  },
  "scenario_valuation": {
    "scenario_details": {SCENARIO_PARAMS_EXAMPLE},
    "probability_weighted_mcap_yi": XX,
    "probability_weighted_upside_pct": XX,
    "asymmetry_ratio": X.X
  },
  "reverse_dcf": {
    "applicable": true,
    "market_implied_g_pct": "代码预计算(earnings锚=反向DCF的g, revenue锚=隐含CAGR, asset锚=隐含ROE改善)",
    "my_implied_g_pct": "基于中性情景推演的对应指标(earnings锚=利润增速, revenue锚=收入CAGR, asset锚=ROE改善)",
    "expectation_gap_pct": "market_implied - my_implied 的差距",
    "gap_direction": "市场低估|市场高估|基本公允|无法计算",
    "gap_magnitude": "显著|中等|轻微|不适用",
    "applicable_note": "若 applicable=false，说明原因"
  },
  "validation_crosscheck": {
    "validation_model": "{VALIDATION_MODEL}",
    "validation_paradigm": "盈利视角|收入视角|资产视角|资源视角|管线视角|分拆视角|与主模型相同",
    "base_target_mcap_yi": "代码填充",
    "validation_mcap_yi": "校验模型粗估市值(亿元人民币)",
    "gap_pct": "代码填充",
    "gap_direction": "主模型高估|主模型低估|基本一致",
    "assessment": "互相印证|存在分歧|严重冲突"
  },
  "expectation_gap": {
    "level": "市场显著低估|市场中等低估|基本公允|市场高估|无法计算",
    "note": "预期差说明。level必须与4b分析的结论一致(不硬绑reverse_dcf)",
  "confidence": {
    "overall_score": 1-10,
    "overall_label": "高|中|低",
    "dimensions": {
      "info_quality": {"score": 1-10, "label": "信息质量", "note": "说明评分依据"},
      "financial_feasibility": {"score": 1-10, "label": "财务可行性", "note": "说明评分依据"},
      "valuation_safety": {"score": 1-10, "label": "估值安全边际", "note": "说明评分依据"},
      "historical_precedent": {"score": 1-10, "label": "历史案例匹配", "note": "说明评分依据"}
    }
  },
  "trade_annotation": {
    "tier": "★★★ 高赔率机会|★★☆ 中等赔率|★☆☆ 低赔率机会|☆☆☆ 规避",
    "total_score": "X/10",
    "dimension_scores": {"odds_quality": 0-3, "pricing_headroom": 0-3, "transmission_confidence": 0-3, "model_consistency": 0-3},
    "alignment_signals": ["信号描述"],
    "tier_note": "交易标注核心理由",
    "suggested_action": "建议操作"
  },
  "monitoring_kpis": {
    "financial_verification_kpis": [{"name":"", "baseline":"", "target":"", "frequency":"季度", "verifies":""}],
    "event_milestone_kpis": [{"name":"", "expected_timing":"", "significance":"", "verification_source":""}],
    "competition_signal_kpis": [{"name":"", "current_state":"", "trigger":"", "action_if_triggered":""}],
    "risk_trigger_kpis": [{"name":"", "linked_to":"", "severity":"high|medium|low", "monitor":""}]
  },
  "risk_triggers": {
    "bull_trigger": "触发条件说明",
    "bear_trigger": "触发条件说明",
    "monitoring_frequency": "季度(与财报同步验证)"
  },
  "narrative": "投资叙事",
  "data_gaps": ["无缺口则写空数组[]。有缺口格式: 缺少[具体数据]，导致[具体判断]置信度下降"],
  "probability_rationale": "bear: [环节1(概率X%) + 环节2(概率Y%) + ... → 联合概率Z%]. bull: [超预期事件1(概率X%) + 超预期事件2(概率Y%) + ... → 联合概率Z%]. base: 100% - bear - bull = Z%",
  "preflight_check": ["[OK] 清单项1完成", "[OK] 清单项2a-2d完成", "[OK] 清单项3a-3e完成", "[OK] 概率和=1.00", "[OK] upside单调递增,全参数自检通过", "[OK] WACC未修改", "[OK] 纯JSON输出"]
}
```
