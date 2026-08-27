# 09-sotp-p2.md 续（2/2）

> 接上一文件，正文连续未删减。

**Baseline（理解起点——告诉你"从哪出发"，不限制"能到哪"）**:
- 财务基线: 当前 ROIC/毛利率/净利率/营收——理解成本结构和经营杠杆。**不是参数上限**。
- 量化锚点: 当前产能/价格/市占率——验证事件的起点对不对。
- 脆弱点: 约束 bear 的下跌空间，不约束 bull 的上限。
- 产业位置: 可比公司是参考不是牢笼。没有可比公司就凭行业知识判断。

**事件锚（变数——告诉你"往哪走、走多远"）**:
- 事件中的新价格/新产能/新客户——变化方向和幅度。
- 按来源置信度打折: 公司公告 <10%，专家纪要 10-30%，分析师测算 20-40%。
- 打折必须显式标注: 锚点原文→来源→置信度→打折幅度→打折后数字→理由。

**两者的关系**: Baseline 让你理解商业模式，事件让你知道基本面变了多少。参数最终位置由你的独立判断决定——baseline 是理解工具，不是约束工具。

赋 CAGR 时——从事件锚点出发，根据来源置信度打折:
a) 从事件锚点提取: 产能/订单×利用率×价格 = 事件隐含收入。分别算各分部。
b) 用事件隐含收入 / 当前该分部收入 = 隐含增长倍数。年化: CAGR = (倍数)^(1/年数)-1。
c) 打折必须显式标注: 锚点原文→来源→置信度→打折幅度→打折后数字→理由。不允许综合一句"更保守"覆盖所有打折。

赋参数的起点是 3d 的因果剧本。事件催化（验证突破、涨价东风、订单翻倍）必须体现在倍数溢价中——增速之外，技术壁垒和行业东风也值钱。参数由你的独立判断决定，不机械对标稳态。

当前叙事分部模型是 {PRIMARY_MODEL} ({MODEL_DESC})，参数模板如下:

{MODEL_PARAM_SCHEMA}

你必须使用的参数体系:
{MODEL_PARAM_NAMES}

**百分比格式铁律——所有带 pct 后缀的字段都使用实际百分比数值,不是小数:**
- ROIC=15% -> roic_assumed_pct: 15 (不是0.15)
- 增速=50% -> earnings_growth_pct: 50 (不是0.5)
- PE=80x -> pe_target: 80
- 概率=30% -> probability: 0.30 (概率字段例外,使用0-1小数)
- 计算公式 ICxROIC%/100xPE 中,ROIC%/100 是把15转为0.15——如果 roic_assumed_pct=0.08,则 ICx0.0008xPE≈0

**参数的经济含义——赋参前必须逐参数过这关:**

**PE/PS 的锚定法则: 用可比公司的实际交易数据,不用现价的缩放。禁止缩放——这是整个估值框架最核心的约束。**

估值倍数的唯一合法来源是**同行业、同生命周期阶段的公司在市场中实际交易的价格**。你给一个公司赋 PE=35x，必须有"这个行业的公司在稳态下确实交易在 30-40x"作为依据。

**缩放是估值里最常见的系统性错误**——"当前 PE 153x 太高了，base 给 35x"、"当前 PS 13x，bull 给 20x"。这些数字看起来合理，但它们的唯一依据是"比现值低/高"——不是任何经济现实。如果你说不出这个 PS/PE 对应的是哪家可比公司在什么时期的实际交易，你就是在缩放。

**赋 PE/PS 的三步法**:
1. **找参照系**: 从火山数据、知识补充、行业研究中找 2-3 家与目标公司业务最接近、处于相似生命周期阶段的 A 股可比公司
2. **读他们的数**: 这些可比公司当前交易的 PE/PS 是多少？它们历史上在稳态期（非泡沫、非危机）交易的区间是多少？
3. **对标赋参**: 你的 bear/base/bull PE/PS 必须落在这个参照系的合理区间内——可以有溢价/折价,但必须有理由（壁垒更强、增速更高、赛道更优等）

**PS 的参照框架**:
- **锚定方法**: 凭行业知识判断同细分赛道的 A 股公司在**非泡沫非危机**的稳态期交易在什么估值水平。baseline 量化锚点和火山数据中的可比公司 PS/PE 是当前时点值——可能整个板块都在泡沫或恐慌中——仅供参考，不能直接照搬。
- **Bull PS** = 行业领导者在稳态下的 PS。不是泡沫峰值。
- **Base PS** = 中等偏上公司在稳态下的 PS。
- **Bear PS** = commoditized 参与者或周期底部的 PS。不是危机恐慌低点——是"故事证伪后,市场在正常情况下持续交易该股票的底部区间"。
- **可以突破参照系——但必须输出理由**: 如果你的 PS 超出了上述可比公司参照系的范围，在 reasoning_trace 中单独写一条"PS突破论证"，说明: (1)这家公司相比参照系中最好的公司，在哪一个维度上形成了降维打击级别的优势？(2)为什么这个优势在 3 年后不会被竞争或技术迭代消解？缺乏回答→禁止突破。

**PE 的参照框架**:
- PE 的锚定逻辑与 PS 相同: 凭行业知识判断同赛道可比公司在**非泡沫非危机**稳态期的 PE。baseline 和火山数据仅供参考。
- **Bull PE** = 行业领导者在稳态下的 PE。
- **Bear PE** = 行业周期底部的 PE。故事证伪不等于公司归零。
- PE > 60x: 只在"盈利低谷+增速即将爆发"的特殊阶段合理——分母(E)暂时被压制。必须注明是过渡期 PE 还是稳态 PE。
- **可以突破参照系——但必须输出理由**: 同上,在 reasoning_trace 中写"PE突破论证"。

**PB**: 与 ROE 匹配。ROE<5% 不应 >2x PB（除非隐蔽资产重估）。

**EV/EBITDA**: 与行业中枢的偏离幅度必须可解释。上行周期可高于中枢，下行周期应低于中枢。

ROIC: 故事里的事件节点驱动 ROIC 改善幅度。从叙事推演 ROIC 路径——毛利率修复到多少？规模效应何时释放？当前财务数据可能是周期底部（ROIC 被产能利用率压制）或转型前夜（旧业务低效、新业务尚未起量）。如果你的叙事指向需求爆发或效率跃迁，forward ROIC 必须反映事件后的改善幅度，不能锚定当前低谷值。滞后财务数据里的低 ROIC 是故事起点，不是终点。

CAGR/增速: 高增速必须匹配高再投资率（RR=g/ROIC）。增速和 RR 不能脱节。

参数联动规则:
- 三情景参数必须逐级递增: bear < base < bull，禁止相同数值
- PE/PS/PB 的升降方向必须与因果剧本一致
- 概率不由模板决定——由因果链条环节数推导。bear 需要 N 个独立环节同时崩塌→联合概率就是小概率，不需要"凑"到某个数字

**参数自检（赋参后逐条过）:**

{MODEL_PARAM_SELF_CHECK}

**注意: 你只输出参数假设。所有估值数字由代码统一计算:**

| 模型 | 代码公式 | 你控制的参数 |
|------|----------|-------------|
| A | `IC x ROIC% x PE` | ROIC、RR(→g)、PE | RR 决定可持续增速 g=ROIC×RR |
| C | `IC x ROIC% x PE x 拐点折扣` | ROIC、PE、距拐点 | 拐点>4Q后每年折6% |
| G | `IC x ROIC% x min(PE, PEGx增速)` | ROIC、PE、PEG、增速 | PE 不能超过 PEGx增速 上限 |
| B | `revenue x (1+cagr)^3 x PS` | 3y CAGR、PS |
| D | `equity x PB` | PB |
| E | `EBITDAx(1+g) x EV/EBITDA - 净负债` | EBITDA增速、EV/EBITDA |
| F | `峰值销售 x 成功率% / (1+折现率)` | 成功率、峰值销售、折现率 |
| H | `equity / (1-NAV折价%)` | NAV折价 |
| I | `投入资本 x 正常化ROIC% x 正常化PE` | 正常化ROIC、正常化PE |
| J | 保留你的估值 | target_mcap |
| K | `sigma[FCFF_t/(1+WACC)^t] + NOPAT_NxPE/(1+WACC)^N` | stage1_growth(高增长NOPAT年增速), stage1_years, ROIC(→RR=g/ROIC→FCFF), terminal_PE | 代码逐年折现,NOPAT逐年复利增长,RR封顶[0.3,0.9] |

**赋参数时反向验证: 用上表公式心算一遍，你的参数产出的数字和你因果剧本应得的估值是否匹配？**

**SOTP 特殊规则:**

**其他业务** (is_primary=false): 事件催化剂只驱动叙事主线，不影响传统业务。因此其他业务不需要推演三情景——只需要判断它的合理估值是多少（一组 base 参数），bear/base/bull 三个情景都用这同一个估值。具体来说：
  - 如果火山数据或产品结构数据中有该分部的实际净利率 -> 引用为 segment_net_margin_pct
  - 如果没有 -> 用公司整体净利率 ± 该分部调整（毛利率高于公司平均→净利率也应高于平均），在 segment_rationale 中标注[估算]
  - PE/PS/PB 的锚定法则与主锚分部相同: 凭行业知识判断同赛道可比公司在**非泡沫非危机**稳态期的估值水平。baseline 和火山数据中的当前倍数仅供参考——行业间估值中枢天然不同，你自行判断。
  - 这不是精确估值——其他业务的作用是提供一个稳定的基准锚，防止叙事锚把整家公司高估或低估
  - **关键**: 取"这个业务如果单独上市，市场在稳态下会给什么估值"，不取当前可能泡沫化的市场价

### 禁止事项
- 禁止三个情景共用同一套假设数字微调
- 禁止 bear 使用"宏观经济衰退"作为触发条件（除非传导链明确依赖宏观）
- 禁止对所有标的使用相同概率分布模板
- **禁止在叙事文本中写具体估值数字**：`scenario_narrative`、`expectation_gap.note`、`segment_rationale`、`gap_rationale`、`narrative` 等文本字段中，只写因果方向和逻辑推理，禁止写"市值 XX 亿"、"上行 XX%"、"PE XXx"、"PS XXx"等具体数字。具体数字由代码计算后填入表格。你写的数字只会跟代码计算结果冲突，产生矛盾的报告。

## 清单项 4: 校验与评分

**4a. 一致性校验**
- [增长-ROIC] 高增速低ROIC→是烧钱换增长还是效率驱动？narrative 必须明确
- [再投资率] 高增速必须匹配高 RR (RR=g/ROIC)
- [估值-增长] 估值倍数与增长阶段不能错配（平台期+50x PE=错配）
- [全参数] ROIC改善幅度/PS增速匹配/PB-ROE匹配/EV-EBITDA行业中枢——逐项自检
- [概率自洽] 三情景概率之和=1.0

**4b. 计价验证→预期差（根据估值锚选择工具）**

根据 2a 的 primary_anchor 选择对应的反向推算工具做预期差分析:

| 锚 | 工具 | 反解的问题 |
|----|------|-----------|
| **earnings** | 反向 DCF (g vs WACC) | 当前市值隐含 NOPAT 需要多高永续增速？ |
| **revenue** | 隐含收入 CAGR (PS→增速) | 当前 PS 隐含 3 年收入需要多高 CAGR？ |
| **asset** | 隐含 ROE 改善 (PB→ROE) | 当前 PB 隐含 ROE 需要改善到多少？ |

**收入锚公司禁止使用反向DCF**——NOPAT 是利润锚的工具。收入锚公司应分析: 当前 PS 隐含的收入 CAGR 与 base 情景推演的 CAGR 之间的差距。

聚焦"差距意味着什么"，不重复 applicable 状态。

如果隐含 CAGR 与 base CAGR 差距 >30%，必须在 expectation_gap.note 中解释：这个差距是因为你对终点倍数的判断不同于市场吗？你的 terminal PS/PE 假设的依据是什么？不同的 terminal 假设会产生截然不同的"市场预期"。

`expectation_gap.level` 必须与你 4b 分析的结论一致（不硬绑 reverse_dcf——收入锚走隐含 CAGR，资产锚走隐含 ROE）:
- 隐含期望远高于推演 → level="市场高估"
- 隐含期望远低于推演 → level="市场显著低估"
- 基本接近 → level="基本公允"
- 工具不适用 → level="无法计算"

**4c. 校验交叉验证**
主模型 {PRIMARY_MODEL} ({MODEL_FAMILY}) vs 校验模型 {VALIDATION_MODEL} ({VALIDATION_MODEL_DESC})。
用校验模型范式粗估 base 估值，与主模型 base 目标市值对比:
- 差异<20%: 互相印证
- 差异20-40%: 存在分歧，需在置信度中反映
- 差异>40%: 严重冲突，必须在 assessment 中解释原因

**自校验降级规则**: 若主模型=校验模型（即所有其他校验候选均被硬约束排除），意味着无法获得独立范式交叉验证。此时:
- 交叉验证仅能检验"参数自洽性"而非"范式独立性"
- assessment 必须降一档: "互相印证"→"存在分歧(同模型自校验)", "存在分歧"→"严重冲突(同模型自校验)", "严重冲突"→"严重冲突(同模型自校验,缺乏独立验证)"
- assessment 中必须包含短语"同模型自校验——缺乏独立范式验证，本次交叉验证价值有限"
- validation_paradigm 设为"与主模型相同({MODEL_FAMILY})"

**4d. 非对称评分**
asymmetry_ratio = bull_upside / |bear_upside|

**4e. 置信度(4维, 每维1-10)**
- info_quality: 信息来源可靠性。硬证据≥2环(订单/产能/专利/政策)→≥7; 纯主题无锚点→1-3。**强制降级: 清单项2c标注"事件-产品映射失败"→info_quality≤5**
- financial_feasibility: 财务假设可行性。参数改善幅度有逻辑支撑→≥7; 凭空跳变→≤5
- valuation_safety: 估值安全边际。bear 下行≤50%→≥7; bear 下行>90%→≤4。注意: valuation_safety 的结论必须与 4b 的 expectation_gap.level 逻辑一致。如果 expectation_gap 说"基本公允"但 valuation_safety≤3，在 note 中解释为什么一个"公允"的东西同时"不安全"。
- historical_precedent: 参照 2a 的 precedent_richness。先例丰富(P≥8)→≥7; 史无前例(P≤3)→≤4

## 清单项 5: 交易标注 + KMI + 风险触发器
- 交易标注: 4维(每维0-3) — odds_quality/pricing_headroom/transmission_confidence/model_consistency
- 监测KPI: financial_verification/event_milestone/competition_signal/risk_trigger 四类
- 风险触发器: bull_trigger/bear_trigger + 监测频率
- 投资叙事: 1-2句总结

## 清单项 6: 输出

- reasoning_trace 按清单项顺序组织。清单项3 必须包含以下子项（各写一条 trace，不可合并）: "清单项3a-分布形状+投资命题: ..." "清单项3a+-事件冲击量级→分部参数幅度: 对每个分部: 事件冲击了什么/幅度估算/打折理由/0→1分部写出TAM→市占率→forward_revenue推导链" "清单项3b-计价天花板: ..." "清单项3c-风险映射: ..." "清单项3d-因果剧本(bear/base/bull各一段): ..." "清单项3e-约束确认: ..." "清单项3e-赋参数: 对0→1分部明确使用forward_revenue_3y_yi而非CAGR..." "清单项3e-叙事一致性检查: ..."
- `signal_audit`: **直接复制 2a 的 signal_audit 结论**（你不再做信号审核，只透传）
- `data_gaps` 标注缺失的数据，引用 2a 已标注的数据异常。格式: "缺少[具体数据]→影响[参数]→搜索建议:[精确搜索词]"——把搜索词写进字段，让LLM-2直接拿来搜
- `preflight_check` 逐项自检格式: ["[OK] 清单项1素材吸收完成", "[OK] 清单项2引用2a审核结论完成", "[OK] 清单项3a-3e完成(含风险映射+约束确认+叙事一致性检查)", "[OK] 概率和=1.00", "[OK] upside单调递增,全参数经济含义自检通过", "[OK] WACC未修改", "[OK] 纯JSON输出"]
- 输出纯 JSON，不要用 markdown 代码块包裹

# 参数锚定法则

你的 PE/PS/PB 锚定的是【可比公司 + 行业稳态中枢】，不是当前市值。当前市值只是一个事实标签，不是你赋参数的靶子。赋完参数后不要心算估值——代码会算。

# 核心约束
1. WACC 不可修改（代码预计算）
2. 三情景概率之和 = 1.0
3. bear 参数 < base 参数 < bull 参数（逐级递增）
4. 输出纯 JSON，不要用 markdown 代码块包裹

# LLM-1 SOTP 输出 Schema（仅参数，不含市值/upside）:

{
  "reasoning_trace": ["清单项1-素材吸收(引用2a锚+计价): ...", "清单项2-引用2a审核结论(step2d=X): ...", "清单项3a-分布形状+投资命题: ...", "清单项3b-计价天花板(还剩下多少没计价): ...", "清单项3d-因果剧本(bear/base/bull各一段): ...", "清单项3e-赋参数: ...", "清单项4a-一致性校验: ...", "清单项4b-计价验证(按锚选工具): ...", "清单项4c-校验交叉: ...", "清单项4d-非对称: ...", "清单项4e-置信度: ..."],
  "signal_audit": {
    "step2a_restate": ["[合同负债] 当前值=0.13亿 (↑1.1σ, 历史均值=0.08亿)", "..."],
    "step2b_match": [
      {"signal": "【示例-必须用实际信号替换】", "match": "支撑/削弱/时序错位", "source_level": "L1-L5", "basis": "<=50字，说明判断依据。必须引用产品结构数据中的实际产品名和数字，禁止照抄此示例"},
      {"signal": "【示例-必须替换】", "match": "时序错位", "source_level": "L3", "basis": "<=50字，说明判断依据。必须引用当前标的的实际产品线，禁止照抄示例文本"},
      {"signal": "【示例-必须替换】", "match": "削弱", "source_level": "L5", "basis": "<=50字，说明判断依据"}
    ],
    "step2c_product_restate": "【必填-从用户消息'产品结构数据'表中逐产品抄录: 产品名: 收入XX(占X%, 同比±X%), GM=X%。禁止照抄此示例文本】",
    "step2d_score": null,
    "score_rationale": "【必填-基于实际信号判断写评分理由】"
  },
  "segments": [
    {
      "segment": "叙事主锚分部",
      "anchor": "{SEGMENT_ANCHOR}", "segment_revenue_yi": 14.2, "is_primary": true,
      "segment_rationale": "<=60字，说明收入来源依据（火山搜索/产品结构/占比估算）",
      {SEGMENT_PARAMS_EXAMPLE}
    },
    {
      "segment": "其他稳态业务(副锚)",
      "anchor": "earnings", "segment_revenue_yi": 4.9, "is_primary": false,
      "segment_rationale": "<=60字，说明收入来源依据",
      "base": {"pe_target": 15, "segment_net_margin_pct": 12}
    }
  ],
  // ⚠️ 分部数量: 默认1个叙事主锚+1个副锚。只有当剩余业务的经济特征确实无法合并(如一条盈利一条亏损、或锚类型不同)时，才拆为2个副锚。禁止超过2个副锚。
  "scenario_valuation": {
    "scenario_details": {SCENARIO_PARAMS_EXAMPLE},
    "probability_weighted_mcap_yi": XX,
    "probability_weighted_upside_pct": XX,
    "asymmetry_ratio": X.X
  },
  "data_gaps": ["格式: 缺少[具体数据]→影响[参数/分部]→搜索建议:[精确搜索词]。每个分部一个缺口——半导体/AR/传统各搜各的"],
  "change_request": [{"query": "搜索查询", "purpose": "填补什么数据缺口"}],
  "preflight_check": ["[OK] 清单项1完成", "[OK] 清单项2a-2d完成", "[OK] 清单项3a-3e完成", "[OK] 概率和=1.00", "[OK] 参数逐级递增,全参数自检通过", "[OK] WACC未修改", "[OK] 纯JSON输出", "[OK] 所有分部参数完整: 主锚分部有bear+base+bull三情景完整参数; 副锚分部有base完整参数; 每个分部的参数与anchor类型匹配(earnings→pe_target+segment_net_margin_pct; revenue→target_ps+revenue_growth_3y_cagr_pct或forward_revenue_3y_yi; asset→target_pb; dcf→stage1_growth_pct+roic_assumed_pct+terminal_pe+segment_net_margin_pct)"]
}
````
