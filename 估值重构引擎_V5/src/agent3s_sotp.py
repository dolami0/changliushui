"""
Agent-3s SOTP 分部估值 (SOTPScenarioAsymmetry) — V6.1

在 Agent-2a 判定 sotp_triggered=true 后分叉进入此管线。
替代标准 Agent-3，专门处理多业务线估值范式冲突的场景。

职责:
  1. 为每个分部在 bear/base/bull 下赋估值参数（LLM）
  2. 代码按各分部对应锚的公式计算价值并加总（代码）
  3. 复用 Agent-3 的校验、交易标注修正、输出组装框架

设计原则:
  - LLM 控制参数（有经济含义），代码控制算术（确定性计算）
  - 单次 LLM 调用完成分部推演 + 情景判断
  - 输出格式与标准 Agent-3 完全兼容，前端无需修改
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

from valuation_utils import call_deepseek, build_forward_signal_panel, fmt_pct
from agent3_scenario_asymmetry import (
    ScenarioError,
    _validate_output,
    _mandatory_cross_validation,
    MODEL_PARAM_TEMPLATES,
    PARAM_SELF_CHECK_MAP,
    SCENARIO_PARAMS_MAP,
    _fix_trade_annotation,
    _assemble_final_output,
    _augment_trace_with_fixes,
    MODEL_NAMES,
    MODEL_FAMILIES,
    MODEL_PARAM_NAMES_MAP,
    # V8: LLM-2 基础设施
    _call_llm2,
    _call_volc_search,
    _extract_search_queries,
    _merge_llm_outputs,
    LLM2_SYSTEM_PROMPT as SHARED_LLM2_PROMPT,
)

# Volcengine 知识问答 (用于 SOTP 分部数据后备)
try:
    from env_config import VOLC_AGENT_KEY
except ImportError:
    VOLC_AGENT_KEY = ""

VOLC_URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
VOLC_BOT_ID = "7640524154441156122"


def _call_volc(query: str, timeout: int = 120) -> str:
    """调用火山引擎知识问答。失败返回空字符串。"""
    if not VOLC_AGENT_KEY:
        return ""
    try:
        r = requests.post(
            VOLC_URL,
            json={
                "bot_id": VOLC_BOT_ID,
                "stream": False,
                "messages": [{"role": "user", "content": query}],
            },
            headers={
                "Authorization": f"Bearer {VOLC_AGENT_KEY}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "") or ""
        return ""
    except Exception:
        return ""


# SOTP 火山搜索 query 模板：用产品名做关键词，指向券商研报（比年报拆分更细）
SOTP_VOLC_QUERY = """{stock_name}({stock_code}) {product_keywords}。券商研报中各产品2025年收入/毛利率、最新季度增速、2026-2027年券商收入预测、可比公司PE/PS估值、在建产能投产进度。仅列数字。"""

# Flash 模型生成火山 query 的 prompt — SOTP 分部数据获取
VOLC_QUERY_GEN_PROMPT = """你是 SOTP 分部估值的数据获取助手。当前管线需要对 {stock_name}({stock_code}) 做分部估值（Sum of the Parts）：拆成不同业务线，各自独立估值后加总。

火山引擎是一个结构化知识问答系统——不是关键词搜索引擎。给它一个结构化的自然语言query，它会从券商研报、公司公告、行业数据中提取答案。query的信息密度直接决定答案质量。

根据以下叙事背景，生成一个查询该公司的query。要求:

1. **编号结构**: 每个业务线一个编号，子问题用字母编号。格式:
   "请提供{stock_name}各业务分部的以下数据，标注数据来源和时间:
   1. [业务线A名称]
      a) 2023-2025年各年收入、同比增速
      b) 最新季度毛利率/净利率
      c) 券商对未来2-3年的收入预测(注明是哪家券商的预测)
      d) 核心客户/订单/出货量——如果有公告或研报提及
      e) A股可比公司及当前估值水平(不要PE/PB数字,只要公司名称)
   2. [业务线B名称] ..."

2. **要求量化**: 每个问题都要具体数字。不要"增长良好"这种——要"同比增速X%"。

3. **要求来源标注**: 让火山标注每个数据来自年报/券商研报/公司公告/行业报告。如果没有确切来源，让火山标注"推断"。

4. **覆盖关键估值参数**: 收入/增速(定CAGR)、毛利率净利率(定盈利能力)、可比公司(定PE/PS参照系)、订单/出货(验证增长)、产能/扩产进度(验证供给)。

叙事背景:
{context}

直接输出query，不要引号、不要解释。"""


def _gen_volc_query(
    stock_name: str,
    stock_code: str,
    agent2a_output: dict,
    api_key: str | None = None,
) -> str:
    """用 Flash 模型从叙事中提取产品名，生成优化的火山搜索 query。"""
    if not api_key:
        try:
            from env_config import DEEPSEEK_API_KEY
            api_key = DEEPSEEK_API_KEY
        except Exception:
            pass
    if not api_key:
        return ""

    if not isinstance(agent2a_output, dict):
        print(f"  [SOTP Flash] agent2a_output不是dict, type={type(agent2a_output)}", flush=True)
        return ""

    # 构建上下文：Agent-2a 完整叙事诊断（不截断，Flash 需要充分理解业务线）
    mn = agent2a_output.get("market_narrative", {}) if isinstance(agent2a_output, dict) else {}
    sas = mn.get("secondary_anchors", [])
    context_parts = []
    context_parts.append(f"投资主题: {mn.get('core_bet', '')}")
    context_parts.append(f"叙事详情: {mn.get('narrative_summary', '')}")
    context_parts.append(f"估值锚: primary={mn.get('primary_anchor', '')}")
    if mn.get('sotp_rationale'):
        context_parts.append(f"SOTP理由: {mn.get('sotp_rationale', '')[:300]}")
    for sa in (sas or [])[:5]:
        context_parts.append(f"分部: {sa.get('segment', '')} | 锚={sa.get('anchor', '')} | 收入占比≈{sa.get('revenue_share_pct', '?')}%")

    prompt = VOLC_QUERY_GEN_PROMPT.format(
        stock_name=stock_name,
        stock_code=stock_code,
        context="\n".join(context_parts),
    )

    DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"
    for attempt in range(2):
        try:
            resp = requests.post(
                DEEPSEEK_API,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": "deepseek-v4-pro",
                    "temperature": 0.0,
                    "max_tokens": 300,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": "生成query"},
                    ],
                },
                timeout=15,
            )
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    result = (choices[0].get("message", {}).get("content", "") or "").strip()
                    # 校验: 自然语言query应覆盖多个业务线，通常>50字
                    has_id = (stock_code in result) or (stock_name in result)
                    if result and len(result) >= 50 and has_id:
                        print(f"  [SOTP Flash] query={result[:120]}", flush=True)
                        return result
                    if result:
                        has = ('300811' in result) or (stock_name in result)
                        print(f"  [SOTP Flash] query不合格 len={len(result)} has_id={has}, 重试...", flush=True)
            if attempt == 0:
                print(f"  [SOTP Flash] 第1次失败 status={resp.status_code}, 重试...", flush=True)
                import time; time.sleep(2)
        except Exception as e:
            if attempt == 0:
                print(f"  [SOTP Flash] 第1次异常: {e}, 重试...", flush=True)
                import time; time.sleep(2)
            else:
                print(f"  [SOTP Flash] 第2次也失败: {e}", flush=True)
    return ""


def _search_segment_data(
    stock_name: str,
    stock_code: str,
    data_package: dict,
    agent2a_output: dict | None = None,
) -> dict:
    """火山联网搜索分部数据。

    用 Flash LLM 从叙事中提取产品名生成 query，替代手工关键词拼接。

    Returns: {"volc_text": str} — 搜索失败返回空 dict。
    """
    if not VOLC_AGENT_KEY:
        return {}

    # 用 Flash LLM 生成优化 query
    query = _gen_volc_query(stock_name, stock_code, agent2a_output or {})
    if not query:
        # 回退: 从叙事中提取产品名拼关键词
        mn = (agent2a_output or {}).get("market_narrative", {}) if isinstance(agent2a_output, dict) else {}
        keywords = [stock_name, stock_code, "券商研报"]
        # 从副锚和核心赌注提取产品名
        for sa in (mn.get("secondary_anchors", []) or []):
            seg = (sa.get("segment", "") if isinstance(sa, dict) else "").split("(")[0].split("（")[0].strip()
            if seg and len(seg) <= 12:
                keywords.append(seg)
        core_bet = mn.get("core_bet", "")
        for word in ["芯片电感", "AI电感", "电感元件", "半导体", "新能源", "机器人", "丝杠", "储能", "光伏"]:
            if word in core_bet and word not in keywords:
                keywords.append(word)
                break
        query = " ".join(keywords) + " 各产品收入 毛利率 增速 预测 可比公司 产能。仅列数字。"
        print(f"  [SOTP Flash] 回退query={query[:120]}", flush=True)

    result = _call_volc(query)
    if result:
        print(f"  [SOTP Volc] 联网搜索完成 ({len(result)} chars)", flush=True)
    else:
        print(f"  [SOTP Volc] 联网搜索无结果", flush=True)

    return {"volc_text": result} if result else {}


# ═══════════════════════════════════════
# System Prompt — SOTP 分部估值
# ═══════════════════════════════════════

SOTP_SYSTEM_PROMPT = """# 你是达摩达兰式的估值重构师

你的核心能力不是计算，而是用故事驾驭数字，用数字检验故事。

## 数据+故事双螺旋

没有故事的数字是尸体，没有数字的故事是童话。

任何公司的价值建立在两个不可拆分的维度上：
- **叙事层**: 这家公司如何赚钱？增长引擎是什么？护城河有多宽？行业终局里它扮演什么角色？
- **数字层**: 增长率、利润率、再投资率、资本成本、终值假设。

铁律：叙事决定数字的输入，数字反推叙事的可信度。二者必须严丝合缝，任何裂缝都是估值错误的根源。

## 思维禁区

- 禁止使用行业平均数据作为默认输入。如果叙事说"这家公司不一样"，数字就必须不一样。
- 禁止模板化估值：不允许不经思考就套用行业默认值。
- 禁止数字脱离叙事：每个输入假设必须能追溯"这来自叙事的哪一部分"。
- 禁止忽视反向验证：只做正向估值是半成品，必须用对应锚的工具检验市场定价（earnings→反向DCF, revenue→隐含CAGR, asset→隐含ROE改善）。
- 禁止对收入锚公司使用反向DCF——NOPAT是利润锚工具，收入锚应分析当前PS隐含的收入CAGR。
- 禁止假装精确：承认不确定性是估值的一部分。
- 禁止混淆价格与价值：当前股价是事实，内在价值是判断。你的任务是判断二者差距，而非解释股价为什么涨。
- 关键：拒绝所有已发生的、已验证的事实在bear中被推翻——Bear的证伪空间在未发生的推测上。

你的职责: 基于已被验证的叙事框架，做**三情景的参数推演和估值计算**。

你掌握 A/B/C/D/E/F/G/H/I/J/K 共 11 种估值模型。

# 执行清单（层层递进的推演过程）

以下清单项不是独立任务——它们是同一条推理链上的递进步骤。清单项必须按顺序执行，不可跳过、不可调换。

## 清单项 1: 素材吸收 — 三件东西

Agent-2a 已完成叙事诊断，你必须信任其结论。从用户消息中的 "Agent-2a 叙事诊断结论" 提取估值锚、计价程度、事件分布形状。

你的 SOTP 推演建立在三件东西的交汇点上：

**① 投资地图 — 事件冲击前的企业全貌（Agent-Baseline 预合成）**

直接信任它——不要重做地图的工作。你消费它的方式:
- **维度一（产品结构）→ 产品→分部映射。** 地图已正确区分各产品线。完成 3d+ 映射步骤时，产品表中的收入数字是 segment_revenue_yi 的直接来源——不需要从火山搜索或事件素材推算。注意名称相似的产品不是同一业务（"功能性薄膜材料"≠"高分子薄膜材料"）。
- **量化锚点 → 赋 CAGR/PS/PE 的起点。**
- **里程碑时间线 → 事件冲击的靶子。**
- **脆弱点 → bear 情景的方向和概率。**

**② 市场在计价什么（从 "Agent-2a 叙事诊断结论" 和 "当前市值隐含假设" 中提取）**

- 计价程度（overall_priced_in）: 事件已被消化了多少？
- 隐含假设（Implied Story）: 当前市值隐含了什么增速/利润率？这设定了 SOTP 加总的起点参照。
- 估值锚（primary_anchor）: 锚冲突触发 SOTP。

**③ 事件 — 冲击投资地图的变量**

三份事件分析报告:

- **事件推演 (event_deduction)**: 事件→传导链→财务指标的完整路径。含: 每步传导机制与量化依据、关键发现(量化数字+历史案例+多方博弈)、脆弱性与证伪条件、市场共识对照表(一致/超出/矛盾)、瓶颈节点(硬约束性质/量化边界/突破路径)。

- **逆向推演 (adversarial_thinking)**: 对投资逻辑的攻击测试。含: 每个关键假设的存活强度(强/中/弱)、降级条件、击穿逻辑链的信号组合。

- **催化日历 (future)**: 结构化时间表。每行含P0/P1/P2优先级+证实/证伪条件。日历风险提示标注催化真空期和负面密集期。

三者与 baseline 的关系: baseline 是事件前的静态画像。事件推演告诉你"变了多少"、逆向推演告诉你"最可能在哪断"、催化日历告诉你"什么时候验证"。

**⚠️ 事件量化锚点——赋值前必须提取并回应:**

读完事件素材后，从两个来源提取量化锚点: ①事件原文 ②baseline。在 reasoning_trace 的"清单项1"末尾列出:
```
[事件量化锚点 — 含来源标注]
- 收入/产能/时间: (来源, 如 19.77亿Q1订单/公司公告)
- 价格: (来源)
- 利润率: (来源)
- 估值倍数: (来源)
```
这些数字是你赋各分部参数时必须显式回应的。偏离必须说明理由和打折幅度。

**操作化——防止滞后财务数据覆盖事件新数据**:
1. 赋 PS 时: 以事件改善后的毛利率/净利率为基准，不以当前滞后财务的低毛利为基准。
2. 赋 CAGR 时: 从事件的产能/订单/价格推算收入路径，不以上一年的历史增速做外推。
3. 对每个分部参数自问: "这个数字反映的是事件冲击前还是冲击后的状态？"

**关键**: 估值锚和计价程度以 2a 为准（不可推翻）。

**baseline 六维度消费路由——每个维度必须在 SOTP 推演中显式使用:**

| 地图维度 | 消费步骤 | SOTP 具体用途 |
|---------|:---:|------|
| 公司身份与收入结构 | 3d+ | 产品线→分部映射的直接输入；收入拆分决定哪些分部是事件催动、哪些是稳态 |
| 财务基线 | 3e | 各分部 segment_revenue_yi 的**起点值** + 公司整体净利率/ROIC 基线 → segment_net_margin_pct 的参照 |
| 产业位置 | 3e | 每个分部的可比公司+市占率+竞争位势→各分部 PE/PS/PB 锚定的参照系来源 |
| 增长轨迹与里程碑 | 3d | 产能节点/产品管线/客户认证时间线→bear"哪个分部崩塌"/bull"哪个分部加速"的分叉点 |
| 投资主线与脆弱点 | 3d | **直接输入风险映射**——脆弱点=约束各分部 base/bull 的已知风险，主线=事件加强了哪个分部 |
| 量化锚点 | 3e | 各分部可比 PE/PS/PB 中位数+历史 PE band→赋各分部参数的**起点**，赋完后交叉校验（见3e末尾） |

**消费闭环要求**: reasoning_trace 的每个分部参数必须能追溯到"这个判断来自地图哪个维度"。如果某个维度在整条推理链中从未出现，re-trace 你的步骤——你漏了东西。

## SOTP 分部估值规则

本标的触发 SOTP 分部估值。公司将业务拆为两段：

**关键约束——主锚内部异质性与参数混合:**

SOTP 把多个副锚按锚类型合并。当主锚分部(revenue锚)内部混入了「事件催动」和「非事件催动」的子业务时——**你不能用同一套激进参数覆盖所有子业务**。

查看用户消息中「分部定义」表的"事件催动"列。若主锚分部的子业务中同时有 ✅是 和 ❌否：

**参数必须按收入占比加权，不允许事件催动的7%业务绑定非事件催动的53%业务一起享受溢价:**

1. **事件催动的子业务**: 增速/PS可以从事件信息推导，允许可比公司溢价
2. **非事件催动的子业务**: 增速≤行业基线，PS≤行业可比中位数，**不得享受事件溢价**
3. **加权计算**: 最终主锚的CAGR和PS = Σ(子业务收入占比% × 该子业务参数)。不能直接用最激进的那个子业务参数套到全部分部上。
4. **Bear情景**: 必须假设事件叙事**证伪**——政策/订单/催化不兑现。事件催动的子业务增速回落至行业基线、PS退回行业地板。Bear 必须有实质性下跌（≥20%），不允许 Bear 情景涨幅为正。

**副锚分部（事件不催动）:**
- 参数来源是公司历史趋势/行业常识/LLM训练知识——不是事件信息
- **增速**: ≤ 历史中枢 + 1σ，不得超过
- **PS倍数**(若为revenue锚): ≤ 行业可比中位数，不得使用"范式切换"溢价
- **PE倍数**(若为earnings锚): ≤ 行业周期中值
- **严禁**: 将此分部的参数设得比主锚分部更激进——此分部不能主导最终估值
- 推演一组 base 参数（三情景共用）

**Bear情景必须诚实——核心要求:**
- 事件催动的增长故事在Bear中**不成立**。订单/政策/催化不兑现。
- 非事件催动的成熟业务退回到**清算/地板估值**（PB≤1.2x或PE≤行业地板）。
- **Bear 涨幅必须为负（≤-15%）**——如果算出来是正数，你的假设太乐观了。

## 估值输出必须包含

1. **基础估值（Base Case）**: 最可能的故事对应的估值。
2. **乐观估值（Bull Case）**: 叙事超预期演绎的估值。
3. **悲观估值（Bear Case）**: 叙事崩塌时的估值。

**A 股适配**: base = 故事预期内兑现 + 估值锚跟随预期推移；bull = 场景超预期催化 + 估值范式跃迁 + 主题溢价充分体现；bear = 故事证伪 + 退回保守锚。政策壁垒视为临时优势（写明失效时间）。

**Bear情景参数地板——故事证伪时倍数不得悬在半空:**

Bear意味着事件叙事**不成立**——政策没落地/订单被抢/催化落空。此时估值逻辑退回事件前的状态:

| 业务类型 | Bear PS地板 | Bear PE地板 | 逻辑 |
|---------|------------|------------|------|
| 事件催动的ToG/政策型业务 | **≤5x PS** | — | 政策落空→收入归零风险→PS必须压到地板 |
| 非事件催动的成长型业务 | **≤行业25分位PS** | — | 回归事件前增速→市场不会给亏损/微利成长股溢价 |
| 成熟/存量业务 | — | **≤行业地板PE(8-12x)** | 周期底部+无成长→退守清算估值 |

**自检**: 如果你的Bear算出来涨幅≥-10%，逐一检查——哪个分部的参数设得太高了？

## SOTP 参数体系

每个分部 LLM 直接输出**绝对收入**（`segment_revenue_yi`，亿元），不要用营收占比。代码用此收入代入公式计算分部价值。

**0→1 业务的 segment_revenue_yi 特殊规则——必须执行，不可跳过:**

如果当前收入为 0 或 <100 万（刚从 0 起步的新业务），`segment_revenue_yi` **必须填第一年可实现收入**（基于产能×价格×利用率），不是当前的 0。否则公式 `0 × (1+CAGR)³ × PS = 0` 永远为 0，估值失效。

例: 3500万米产能 × 160元/米 × 满产后利用率30% → 第一年收入 ≈ 1.7亿 → segment_revenue_yi=1.7。心算验证: 1.7 × (1+CAGR)³ × PS ≈ 你的目标市值吗？

| 锚 | 参数 | 代码公式 |
|----|------|----------|
| earnings | segment_revenue_yi, pe_target, segment_net_margin_pct | `segment_revenue_yi × 净利率% × PE` |
| revenue | segment_revenue_yi, [revenue_growth_3y_cagr_pct 或 forward_revenue_3y_yi], target_ps | 连续增长: segment_revenue_yi × (1+CAGR%)³ × target_ps. 0→1阶跃: forward_revenue_3y_yi × target_ps |

**revenue 锚两种增长模式**:
- **连续增长** (成熟/成长业务): 提供 `revenue_growth_3y_cagr_pct`，代码从当前收入按CAGR复利3年到终局收入
- **0→1阶跃** (pre-revenue/从0爆发): 当前收入≈0或极小，CAGR公式失效。**不要用CAGR从0推导**——直接基于事件冲击估3年后的收入:
  `forward_revenue_3y_yi` = TAM × 事件驱动的市占率 × 时间线(3年后能拿到多少?)
  例: AR光波导当前收入0.1亿，但事件(瑞声量产)打开千亿级TAM，3年后若获5%份额=50亿→forward_revenue_3y_yi=50

`target_ps` 是**第3年(终端年)的PS**——不是trailing PS。心算校验: 你的终局收入×target_ps≈你剧本里的目标市值吗？
| asset | segment_revenue_yi, target_pb, [segment_equity_yi] | `净资产 × PB`（无segment_equity_yi时按收入占比估算） |
| pipeline | pos_pct, peak_sales_yi, discount_rate_pct | `峰值销售 × PoS% / (1+折现率%)` |
| dcf | segment_revenue_yi, stage1_growth_pct, stage1_years(默认5), roic_assumed_pct, terminal_pe, segment_net_margin_pct | 阶段1: NOPAT逐年复利增长→FCFF=NOPAT×(1-RR), RR=g/ROIC封顶[0.3,0.9]. 阶段2: NOPAT_N×terminal_PE. 全部折现到现值 |

**dcf 锚适用场景**: **仅限earnings锚分部使用**。适用于分部当前盈利(NOPAT>0.5亿且NOPAT/市值>0.8%)、高增长(>25%)、行业终局清晰(3-7年后增速回落+稳态PE可判断)的标的。dcf能建模"增长→利润→现金流"的完整路径。**revenue锚分部应使用revenue锚(PS+TAM)——dcf从NOPAT出发,revenue锚意味着利润路径不清晰,两者范式不可混淆。**
**dcf vs revenue vs earnings选择**:
- revenue锚分部 → 用revenue锚(PS公式),不要越界用dcf
- earnings锚分部 + NOPAT充足 + 高增长 + 终局可见 → 用dcf(两阶段DCF)
- earnings锚分部 + NOPAT不足或增速已放缓 → 用earnings锚(PE公式)

注:
- `segment_net_margin_pct` 是分部**净利润率**（净利润/收入），不是毛利率。参考公司整体净利率、行业可比公司净利率、或火山数据中的分部利润率来估算。SOTP 用收入×净利率估算分部利润（分部投入资本无法拆分），不需要 roic_assumed_pct。dcf锚需要roic_assumed_pct——这是阶段1的ROIC假设，用于计算再投资率(RR=g/ROIC)。

**各分部 PE/PS/PB 锚定 — baseline 和火山数据都是参考输入:**

你在赋各分部的 target_ps / pe_target / target_pb 时，可利用:
- baseline「产业位置」维度: 各业务线对应的可比公司+市场地位
- baseline「量化锚点」+ 火山数据: 可比 PE/PS/PB 中位数

以上都是参考，不替代你的行业判断。

**分部门槛规则:**
- **事件催动分部**: PE/PS 可超出可比中位数但应有合理上限（行业领导者的历史峰值可作为参考上限）
- **非事件催动分部**: PE/PS ≤ 可比中位数
- **Bear 分部门槛**: 按上文 Bear 地板表执行

**赋完各分部参数后做参照系交叉校验:**
- 各分部 base PE/PS 与可比中位数的偏差 → 事件催动分部可以有溢价但要写理由
- 各分部 bull PE/PS 是否远超可比公司在非泡沫期的交易峰值？检查是否合理
- SOTP 加总与当前市值的差距方向是否与 2a 的计价程度一致

# 执行清单

以下清单项是递进步骤。清单项必须按顺序执行，不可跳过、不可调换。

## 清单项 2: 引用 Agent-2a 诊断结论（不重做审核）

**Agent-2a 已完成信号审核和叙事诊断。** 从用户消息中的"Agent-2a 叙事诊断结论"提取:

**2a. 信号审核结论** — 直接引用:
- step2d_score: 2a 的信号匹配度评分 (0-10)
- score_rationale: 2a 的评分理由
- step2b_match: 关键的交叉验证结论（支撑/削弱/时序错位）
- 数据异常标注: 2a 已在 data_gaps 中标注的数据问题

**2b. 概率推导原则**: 概率不由模板决定，由叙事中的因果链条推导。从 3d 的因果剧本出发:
- bull 概率取决于超预期需要的独立条件数量和每个条件的确定性。条件越少越确定 → bull 概率越高。连续取值，不要凑整数
- bear 概率聚焦 2-3 个最脆弱的核心假设，推演"如果这个错了故事就塌了"的联合概率
- 分布形状提供方向感——bimodal 两种极端都可能、narrow 超预期难度大、unimodal 居中
- 2a 的 step2d_score 告诉你前瞻信号对叙事的数据支撑程度，在概率推演时作为参考——不是模板，不是上限
- base = 100% - bull - bear

**分布形状调节逻辑**: bimodal 类（高二元性）结果不确定性最高 → bull 不应趋近 0（尾部保护）。narrow 类（低不确定性）超预期难度大 → bull 应保守。unimodal 居中。

**bear 概率上限**（防过度悲观）:
| distribution_shape | bear 上限 | 理由 |
|:------|:------:|------|
| wide_bimodal | 35% | 高不确定性→两个极端都可能 |
| narrow_concentrated | **15%** | 低不确定性→极端尾部概率天然低 |
| narrow_base_dominant | 8% | 趋势有惯性→逆转是小概率 |
中间形状按线性插值。若证伪需要N个独立环节同时崩塌→联合概率自然更低。

**bear 估值硬底**: 故事证伪不等于公司归零。从 baseline「财务基线」维度获取当前净利/净资产/净现金数据，选择适用底线:
  - 盈利企业: bear mcap ≥ TTM净利 × 行业周期底部PE（凭行业知识判断——军工和化工的底部PE天差地别）
  - 有硬资产: bear mcap ≥ 净资产 × 保守PB（与ROE匹配,ROE越低保值PB越低）
  - 纯故事型: bear mcap ≥ 净现金
bear 不可推翻已发生的业务事实（如已出货产品→不应给0估值）。


**禁止**: 重新从面板逐条审核信号——2a 已完成此工作。你只需引用结论。

## 清单项 3: 三情景因果推演（事件感知）

**核心公理: 概率分布由三个维度联合决定，不是模板。**

| 输入维度 | 来源 | 控制什么 |
|---------|------|---------|
| 信号匹配度 (step2d) | 2a signal_audit | **基础展宽** — 信号越好, bull 概率上限越高 |
| 分布形状 (distribution_shape) | 2a event_profile | **分布形状** — bimodal→宽双峰, unimodal→宽单峰, narrow→窄集中 |
| 计价程度 (priced_in %) | 2a event_pricing | **偏斜方向 + upside 天花板** |

### 3a. 事件性质→分布形状

**为什么事件性质改变分布形状:**
事件的 payoff 结构由 2a 的 `distribution_shape` 决定:

| distribution_shape | 分布特征 | bull上限 | bear特征 |
|---------|:------:|:------:|------|
| **wide_bimodal** | 宽双峰, 两个极端都可能 | 全量事件价值 | 回到事件前估值范式 |
| **wide_bimodal_date_anchored** | 宽双峰, 锚定在日期附近 | 全量事件价值 | 回到事件前估值范式 |
| **wide_unimodal** | 宽单峰, 方向确定但幅度不确定 | 全量但高不确定性 | 叙事证伪+退回 |
| **narrow_concentrated** | 窄集中, base主导 | 二阶导数部分 | 趋势逆转+范式降级 |
| **narrow_base_dominant** | 极窄, 几乎只有base | 必须有质变 | 趋势惯性保护 |

**关键**: 不要用旧的 sudden/ongoing 概念。直接根据 2a 给出的 `distribution_shape` 选择对应的行。

### 3a+. 事件冲击量级→分部参数幅度（SOTP核心——标准管线对齐）

**在赋参数之前，必须先把事件冲击转化为每个分部的参数幅度。** SOTP的估值不是基于当前财务，而是基于事件冲击后的预期。

对每个分部，回答三个问题:
1. **事件直接冲击了哪个分部？** 冲击的是收入端(TAM/市占率)还是利润端(毛利率/净利率)？
2. **冲击的幅度有多大？** 打折规则: 事件提供方向，实际幅度从行业参照系取中位数。例: 事件说"AR光学市场2030年3211万台(CAGR 140%)"，但你给苏大维格的CAGR不需要=140%——那是行业，公司是个体。取行业中位数增速(如80%)再打个8折(公司执行风险)。
3. **每个分部的参数应该怎么动？**

| 分部类型 | 增长模式 | 赋参方式 |
|---------|---------|---------|
| 成熟盈利分部 | 连续增长 | revenue_growth_3y_cagr_pct = 事件冲击后的行业增速×公司alpha折扣 |
| 0→1爆发分部 | 阶跃增长 | **不用CAGR**。forward_revenue_3y_yi = TAM₃年 × 事件驱动的市占率 × 事件兑现概率。例: AR TAM₃年≈500亿 × 市占率5% × 兑现概率60% = 15亿 |
| 传统稳定分部 | 低增长 | revenue_growth_3y_cagr_pct ≈ GDP增速，事件若无直接关联则不调整 |

**0→1分部的forward_revenue_3y_yi推导链**（写入reasoning_trace）:
```
TAM估算: [行业数据来源] → 3年后总市场≈X亿
市占率假设: 基于[竞争格局/客户验证/技术壁垒] → Y%
事件兑现概率: 基于[事件确定性/时间线/政策持续性] → Z%
→ forward_revenue_3y_yi = X × Y% × Z% = W亿
同时赋 target_ps = [可比公司PS × 成长性溢价折扣]
```

### 3b. 计价程度→upside 天花板

**你在清单项1中已消化的 2a 计价结论现在派上用场:**

2a 的 priced_in 告诉你市场已经消化了多少事件价值。剩余未计价的空间越大，bull 的理论上限越高；已充分计价的标的，bull 只能来自"比市场预期的还要好"——即二阶导数变化。

**bear 的 downside 则相反:** 计价越多，逆转伤害越大。未计价的标的，bear 仅回到事件前估值范式；充分计价的标的，预期逆转叠加估值范式降级。

### 3c. 投资命题 + 因果分叉点

引用 2a 的 primary_anchor 和 priced_in_estimate，结合事件变量和个股路线，写 1 句"如果-那么"命题。
拆命题为因果环节，标注证实/证伪条件。

### 3d. 因果剧本（先写故事，不赋参数）

**前置: 风险映射** — 分两步:

**第一步: 引用 baseline 脆弱点** — 从投资地图的「投资主线与脆弱点」维度提取已识别风险。逐条声明: 该风险在 baseline 中的原始表述、主要约束哪个情景（bear/base/bull）、在各分部参数中如何体现（降概率/压倍数/限增速/调利润率）。

**第二步: 补充事件特有风险** — 从逆向推演中提取存活强度和降级条件，从催化日历中提取P0级证伪节点。检查是否有 baseline 未覆盖的风险维度。

**风险分类规则**: 涉及已发生负面事实的风险→同时约束 base 和 bull；涉及未发生潜在威胁的风险→主要约束 bear 的证伪路径。如果你认为某条风险不影响任何情景，在 reasoning_trace 中写一句理由。

**不要再扫一遍财务数据找负面信号**——baseline 的脆弱点分析已经做了这件事。你的工作是引用 + 补充，不是重做。

然后写三情景剧本:
- **bear**: 证伪路径必须区分两件事:
    **已发生的事实**（认证通过、已签合同、已投产产能）→ bear 不能"反悔"这些，只能假设后续执行恶化
    **未发生的推测**（远期订单、产能爬坡、市场份额）→ 这才是 bear 的证伪空间
    传导链从哪里崩塌？市场退回什么模型？当前已计价程度意味着下跌空间多大？
- **base**: 哪些证实信号按预期兑现？估值锚如何推移？当前已计价的部分是否已经在 base 中体现？
- **bull**: 哪些催化超预期？超预期的幅度对应剩余计价空间。估值范式是否跃迁？

**bull 涨幅拆解——范式切换 vs 基本面**:

起涨初期的大部分涨幅往往来自估值范式的切换，而非基本面改善。在 bull scenario_narrative 中必须显式拆解:

1. 如果 2a 的 `anchor_shift_potential.shift_possible=true`:
   - 范式切换溢价 = 旧范式合理估值 → 新范式合理估值之间的差距
   - 例: "从传统电力设备 PE 15x → 出海AI数据中心 PS 7x, 仅范式切换就贡献 +80%"
   - 基本面增长 = 新范式内的增长空间（订单增长→收入爆发→PS进一步扩张）
   - scenario_narrative 格式: "范式切换(PE→PS,+80%) + 订单超预期(+50%,→合计+170%)"

2. 如果 2a 的 `anchor_shift_potential.shift_possible=false`:
   - 范式内倍数扩张: 当前锚不变但倍数提升（如 PE 从 30x→50x）
   - scenario_narrative 格式: "倍数扩张(+30%) + 利润超预期(+40%,→合计+82%)"

3. 如果范式切换已发生(`shift_timing=切换已发生`):
   - 新范式已在 base 中体现, bull 只看新范式内的超预期幅度
   - base 的估值倍数已经是新范式的水平

将叙事写入 scenario_narrative。

**重要: 永远不要"凑"概率**——bear 需要 N 个独立环节同时崩塌 → 联合概率自然就是小概率。

**参数-叙事一致性**: 赋完参数后，回顾 3d 因果剧本和风险映射。

### 3d+. 产品→分部映射（赋参前硬步骤，不可跳过）

**在赋 segment_revenue_yi 之前，逐产品声明映射关系。** 火山数据中的产品名可能与财报产品表中名称相似但不同——这是最常见的错误来源。

从用户消息的"产品结构数据"表中逐产品声明:
| 产品 | 财报收入(亿) | 归入哪个SOTP分部 | is_event_driven | 判定依据 |

**硬规则:**
- 产品表中每个产品必须出现在映射表中
- 事件催动的产品→叙事主锚分部，其余→其他业务
- **名称相似的产品不是同一业务**: "功能性薄膜材料"≠"高分子薄膜材料"≠"薄膜包装材料"
- segment_revenue_yi = 该分部所有产品收入之和（直接从产品表取）
- 此映射写入 reasoning_trace，以 "清单项3d+-产品分部映射: ..." 开头

### 3e. 分部赋参

**叙事主锚分部** (is_primary=true): bear/base/bull 三组参数。

**你的模型**: 2b路由判官已将叙事主锚分部模型选定为 **{PRIMARY_MODEL} ({MODEL_DESC})**，参数族为 {MODEL_FAMILY}。你的 `anchor` 字段必须设为 `{SEGMENT_ANCHOR}`，bear/base/bull 参数必须严格使用以下参数体系——不允许使用其他模型的参数名。

**赋参框架: 分部参数 = 理解起点（baseline）+ 事件冲击（event）**

两个信息来源，分工不同:

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
      {"signal": "合同负债", "match": "支撑", "source_level": "L4", "basis": "合同负债跳升验证订单落地——行业数据(L4)与财务数据同向"},
      {"signal": "化合物半导体材料毛利率", "match": "时序错位", "source_level": "L3", "basis": "FY2025年报GM=23.2%远低于叙事宣称75%+(L3:券商研报)。数据截止早于事件窗口，不判为矛盾"},
      {"signal": "业绩预告(FY2025预减)", "match": "削弱", "source_level": "L5", "basis": "公司公告(L5)预减。预告窗口与事件窗口有时序差异，不构成证伪，但揭示bull利润弹性依赖极大基数效应"}
    ],
    "step2c_product_restate": "化合物半导体材料: 收入1.38亿(占12.9%,同比+146%),GM=23.2%(vs公司整体20.3%)",
    "step2d_score": 6,
    "score_rationale": "合同负债+在建工程支撑,预告预减(时序错位)不扣分,化合物半导体GM与叙事存在差距但属时序错位"
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
}"""


# ═══════════════════════════════════════
# SOTP LLM-2 系统提示词 — 审阅分部参数 + 最终报告
# ═══════════════════════════════════════

SOTP_LLM2_PROMPT = """# 你是 SOTP 估值审阅官

你的职责是审阅 LLM-1 的分部参数推演，对照代码计算的 SOTP 加总结果，补充缺失数据，纠正错误，输出完整最终报告。

## 多轮对话与搜索（同标准管线，每轮最多 2 条搜索）

格式: `"search_requests": [{"query": "...", "purpose": "...", "source": "volc"}]`。最终报告不输出 search_requests。

## 任务

### 任务0: 事件锚点对照 —— 最先执行，写入 reasoning_trace

从事件素材中提取所有量化锚点（价格、产能、时间节点、客户、毛利率目标），与 LLM-1 的各分部参数做逐项对比。**不需要输出独立 JSON 字段**——结果直接写入 reasoning_trace 的 "LLM-2: 事件锚校验" 条目。

**reasoning_trace 必填条目格式**（自然语言）:
```
LLM-2: 事件锚校验:
- 事件锚点[XX]: (来源) → LLM-1分部参数 → 差距 → 打折合理性 → 结论
- 收入校验: 事件推算各分部收入 vs LLM-1隐含收入, 差距X%, 打折链是否合理
- 结论: N/M个锚点合理, 不合理锚点已在change_log修正
```

**执行规则**: 每个事件硬数字都要过一遍。算差距→判理由→做结论。不能 0 条 change_log 但锚校验写"多项不合理"——两者必须自洽。

### 任务 1: 数据补充 — LLM-1 的 data_gaps 和 change_request 是必搜清单

逐条生成 search_request，火山支持自然语言查询。volc 预搜索结果如已覆盖可跳过。

### 任务 2: 逻辑审查 — 从 LLM-1 的 reasoning_trace 逐条追溯

每个参数赋值在推理链里有依据吗？引用的数据和 baseline 一致吗？风险映射在参数里有体现吗？三情景逻辑分叉和参数差异对应吗？

常规检查: 分部参数内部矛盾？可比公司选错？分部锚选择合理？

**⚠️ 数据时效性铁律: 事件 > 一切。** 事件是唯一最新情报。券商预测、历史财务、火山搜索结果都可能是事件前的旧数据。矛盾时以事件为准——券商预测没反映涨价 → 券商预测过时，不是事件错了。

### 任务 3: 参数修改 — 发现问题就必须改

**修正铁律: 沿事件因果链走，不能跳过事件套历史数据。** 事件改变了什么 → 参数如何反映 → LLM-1 偏差是高估还是低估事件 → 往哪个方向调。禁止用当前 ROIC/历史 PE 做机械对标——它们是事件冲击前的基本面快照。

每个修改附理由+证据。

### 任务 4: 最终判断 — 基于代码计算的 SOTP 加总数字:
- 置信度、交易标注、预期差、监测 KPI
- 最终叙事: 150-300字精炼故事，不是审阅摘要。详见输出Schema中narrative字段的规范。

## 输出 Schema — 完整最终报告

你在 LLM-1 的输出基础上审阅修改，输出完整报告。包含 LLM-1 的所有字段 + 你的审阅追加:

{
  "scenario_valuation": { "scenario_details": { "bear/base/bull": { "完整参数" } } },
  "reasoning_trace": ["LLM-1: ...", "LLM-2: 审查-..."],
  "change_log": [{"path": "segments.0.base.target_ps", "old_value": 12, "new_value": 8, "reason": "...", "evidence": "..."}],
  "confidence": { "overall_score": 1-10, "overall_label": "高|中|低", "dimensions": { "info_quality": {"score": 1-10, "label": "信息质量", "note": "..."}, "financial_feasibility": {"score": 1-10, "label": "财务可行性", "note": "..."}, "valuation_safety": {"score": 1-10, "label": "估值安全边际", "note": "..."}, "historical_precedent": {"score": 1-10, "label": "历史案例匹配", "note": "..."} } },
  "trade_annotation": { "tier": "★★★ 高赔率机会|★★☆ 中等赔率|★☆☆ 低赔率机会|☆☆☆ 规避", "total_score": "X/10", "dimension_scores": {"odds_quality": 0-3, "pricing_headroom": 0-3, "transmission_confidence": 0-3, "model_consistency": 0-3}, "tier_note": "...", "suggested_action": "..." },
  "monitoring_kpis": { "financial_verification_kpis": [{"name":"","baseline":"","target":"","frequency":"季度","verifies":""}], "event_milestone_kpis": [{"name":"","expected_timing":"","significance":"","verification_source":""}], "competition_signal_kpis": [{"name":"","current_state":"","trigger":"","action_if_triggered":""}], "risk_trigger_kpis": [{"name":"","linked_to":"","severity":"high|medium|low","monitor":""}] },
  "risk_triggers": {},
  "narrative": "<必填: 150-300字精炼投资叙事，非审阅摘要。SOTP叙事需覆盖: (1)公司由哪几个分部构成、各自核心逻辑 (2)分部间的关键矛盾或互补关系 (3)情景分叉条件——什么触发不同分部的同时兑现/证伪 (4)最关键的监测变量。你的审阅发现(参数修正、前瞻信号解读)已在change_log和reasoning_trace中——叙事里不必复述。禁止: 写市值数字、列举参数、逐分部复述估值结果。>",
  "expectation_gap": { "level": "市场更乐观|市场更悲观|预期相近|无法解码", "note": "..." },
  "validation_crosscheck": {}
}

核心约束: WACC 不可改 / 概率和=1.0 / 参数修改必须有证据 / 输出纯 JSON / **禁止在 narrative 中写任何市值数字——估值由代码计算，你不应该自己估算** / **分部总数≤3(1主锚+最多2副锚)，禁止新建超过此限的分部，相似业务合并**

**⚠️ 关键铁律: change_log 与 reasoning_trace 一一对应。** reasoning_trace 中每条"审查-参数修改"（如"base CAGR 从40%降至30%"）必须在 change_log 数组中有对应的结构化条目（path + old_value + new_value + reason + evidence）。禁止只在 reasoning_trace 里描述修改但在 change_log 里留空。两者数量必须一致：如果在 reasoning_trace 里写了 3 条参数修改，change_log 就必须有 3 条。只有一种情况 change_log 可以为空：你确认 LLM-1 的每个分部参数都完美无误，且 reasoning_trace 里没有任何参数修改内容。

**⚠️ 分部参数完整性: 每个分部必须有与anchor匹配的完整参数。earnings锚→pe_target+segment_net_margin_pct; revenue锚→target_ps+(revenue_growth_3y_cagr_pct或forward_revenue_3y_yi); asset锚→target_pb。新建分部时必须保证base参数齐全，否则代码无法计算该分部价值。
"""


# ═══════════════════════════════════════
# 数据格式兼容层
# ═══════════════════════════════════════

def _safe_dict(v, default=None):
    """防御: 如果 v 不是 dict 则返回 default(默认{})。防止 'str' object has no attribute 'get' 崩溃。"""
    if default is None:
        default = {}
    return v if isinstance(v, dict) else default

def _get_core_fields(data_package: dict) -> dict:
    """从 data_package 提取核心财务字段，兼容两种格式：
    - 新格式: packages.core.fields (Agent-1 标准输出)
    - 旧格式: clean_financials (历史缓存/快照)
    """
    # 新格式
    pkgs = _safe_dict(data_package.get("packages", {}))
    core = _safe_dict(pkgs.get("core", {}))
    fields = _safe_dict(core.get("fields", {}))
    if fields:
        return fields

    # 旧格式 (clean_financials 平坦结构)
    cf = data_package.get("clean_financials", {}) or {}
    if cf:
        return cf

    # 兜底：从 data_package 顶层直接取
    return {
        k: data_package.get(k, 0)
        for k in ["market_cap_yi", "revenue_ttm_yi", "net_profit_ttm_yi",
                   "total_equity_yi", "total_assets_yi", "cash_yi",
                   "interest_bearing_debt_yi", "pe_ttm", "pb", "ps_ttm",
                   "roic_pct", "gross_margin_pct", "net_margin_pct",
                   "stock_name", "data_quality_score"]
    }


def _build_bs_section(data_package: dict, agent2a_output: dict, wacc_params: dict) -> tuple:
    """构建 BS 画像文本，与 Agent-3 对齐。"""
    from agent3_scenario_asymmetry import precompute_bs_profile, precompute_wacc
    core = _get_core_fields(data_package)
    mn_bs = _safe_dict(agent2a_output.get("market_narrative"))
    anchor = mn_bs.get("primary_anchor", "earnings")
    pt = _safe_dict(agent2a_output.get("_pricing_tool"))

    mcap = core.get("market_cap_yi", 50)
    if anchor == "earnings":
        nopat = core.get("nopat_yi", 0.01)
        wacc = wacc_params.get("wacc_pct", 10)
        ev = mcap + core.get("interest_bearing_debt_yi", 0) - core.get("cash_yi", 0)
        implied_g = round((ev * wacc / 100 - nopat) / nopat * 100, 1) if nopat > 0 else 0
        lines = [
            "**方法: 反向 DCF (利润锚)**",
            "- EV: {:.0f}亿 NOPAT: {:.2f}亿 ROIC: {:.1f}%".format(ev, nopat, core.get('roic_pct',0)),
            "- 隐含永续增速 g ≈ {}% (WACC={}%)".format(implied_g, wacc),
            "- PE: {:.1f}x PB: {:.1f}x".format(core.get('pe_ttm',0), core.get('pb',0)),
        ]
        section = "\n".join(lines)
        warning = ""
    elif anchor == "revenue":
        ps = core.get("ps_ttm", 0)
        rev = core.get("revenue_ttm_yi", 1)
        section = f"""**方法: 隐含收入 CAGR (收入锚)**
- 当前 PS = {ps:.1f}x 营收TTM = {rev:.1f}亿 市值 = {mcap:.0f}亿"""
        if pt.get("applicable"):
            section += "\\n- 隐含3年收入CAGR = " + str(pt.get('implied_value','?')) + "%"
        warning = f"- PE: {core.get('pe_ttm',0):.1f}x PB: {core.get('pb',0):.1f}x (利润锚仅供参考)\\n"
    elif anchor == "asset":
        pb = core.get("pb", 0)
        roe = core.get("roe_ttm_pct", 0)
        section = f"""**方法: 隐含 ROE 改善 (资产锚)**
- 当前 PB = {pb:.1f}x ROE = {roe:.1f}%"""
        if pt.get("applicable"):
            section += "\\n- 隐含ROE需改善 " + str(pt.get('implied_value','?')) + "ppt"
        warning = f"- PE: {core.get('pe_ttm',0):.1f}x (利润锚仅供参考)\\n"
    else:
        section = f"**方法: {anchor}锚 (定性判断)**"
        warning = ""

    return section, warning


# ═══════════════════════════════════════
# 用户消息构建
# ═══════════════════════════════════════

def _build_segments_section(
    secondary_anchors: list[dict],
    primary_anchor: str,
    market_narrative: dict,
    core: dict,
) -> str:
    """构建分部信息——列出各分部名称、锚类型、是否事件催动。

    LLM-1 根据此表和 product_mix 数据自行判定 segment_revenue_yi。
    不在此处做任何算术——revenue_share_pct 可能为字符串，不可靠。
    """
    lines = ["| 分部 | 锚 | 事件催动 |",
             "|------|-----|---------|"]

    for sa in secondary_anchors:
        seg_name = sa.get("segment", "?")[:40]
        anchor = sa.get("anchor", "?")
        driven = "✅是" if sa.get("is_event_driven") else "❌否"
        lines.append(f"| {seg_name} | {anchor} | {driven} |")

    if not secondary_anchors:
        lines.append("| （单一分部，无需拆分） | — | — |")

    return chr(10).join(lines)

def _build_event_driven_note(
    rd_2b: dict,
    secondary_anchors: list[dict],
    primary_anchor: str,
) -> str:
    """构建事件催动分部标注——标注哪些分部参数受事件约束、哪些不受。"""
    # 从2b的routing_decision中读取event_driven_segment
    eds = rd_2b.get("event_driven_segment")
    if not eds or not isinstance(eds, dict) or not eds:
        return ""

    driven_seg = eds.get("segment", "?")
    driven_anchor = eds.get("anchor", primary_anchor)

    # 找出未被事件催动的副锚
    non_driven = [
        sa for sa in secondary_anchors
        if sa.get("is_event_driven") is False
    ]

    if not non_driven:
        return f"\n**事件催动分部**: 全部 — 事件因果链路覆盖了所有SOTP分部。各分部参数均可从事件信息中锚定。\n"

    lines = [f"\n## ⚠️ 事件催动分部标注 (Agent-2a 1j判定)\n"]
    lines.append(f"**被事件催动的分部**: **{driven_seg}** ({driven_anchor}锚)")
    lines.append(f"  - 事件的因果链路为该分部提供了前瞻判断依据")
    lines.append(f"  - 此分部的参数(增速/利润率/倍数)必须以事件数据为锚定基准\n")

    lines.append("**未被事件催动的分部**:")
    for nd in non_driven:
        nd_name = nd.get("segment", "?")
        nd_anchor = nd.get("anchor", "?")
        nd_rationale = nd.get("non_driven_rationale", "事件因果链路不经过此分部")
        lines.append(f"  - **{nd_name}** ({nd_anchor}锚): {nd_rationale}")
    lines.append("")
    lines.append("**参数约束——对未被事件催动的分部**:")
    lines.append("  - 增速: ≤ 历史中枢 + 1σ（不得用事件推导增速）")
    if any(nd.get("anchor") == "revenue" for nd in non_driven):
        lines.append("  - PS倍数: ≤ 行业可比中位数（不得用'范式切换'溢价）")
    if any(nd.get("anchor") in ("earnings", "asset") for nd in non_driven):
        lines.append("  - PE/PB倍数: ≤ 行业周期中值")
    lines.append("  - **禁止**: 此分部的参数比主锚分部更激进, 此分部估值不得主导最终SOTP加总")
    return "\n".join(lines)


def _build_product_mix_section(data_package: dict) -> str:
    """从 Agent-1 的 forward_looking 提取分产品收入/毛利率数据。"""
    # forward_looking 在 data_package 顶层（与 clean_financials 同级）或嵌套在 packages.core.fields._forward_looking 中
    fw = _safe_dict(data_package.get("forward_looking")) or _safe_dict(data_package.get("_forward_looking"))
    core = _get_core_fields(data_package)
    # 也检查 core fields 内部是否有 _forward_looking
    if not fw:
        fw = _safe_dict(core.get("_forward_looking"))
    products = _safe_dict(_safe_dict(_safe_dict(fw.get("categories")).get("earnings_elasticity")).get("products"))
    mix = products.get("product_mix", []) or []

    if not mix:
        return "（无分产品数据）\n\n注: 分部毛利率请基于行业知识和公司整体毛利率估算，并在 segment_rationale 中标注[估算]。"

    lines = [
        "| 产品 | 收入(亿) | 占比 | 毛利率 | 同比 | → 映射到哪个SOTP分部 |",
        "|------|---------|------|--------|------|------------------------|",
    ]
    for p in mix:
        rev = p.get("revenue", 0)
        share = p.get("revenue_share_pct", 0)
        gm = p.get("gross_margin_pct")
        gm_str = f"{gm:.1f}%" if gm is not None else "?"
        yoy = p.get("revenue_yoy_pct")
        yoy_str = f"{yoy:+.1f}%" if yoy is not None else "?"
        lines.append(f"| {p['name']} | {rev:.2f} | {share:.1f}% | {gm_str} | {yoy_str} |")

    # 毛利率数据质量标注
    gm_src = products.get("gm_source", "actual")
    gm_cov = products.get("gm_coverage_pct", 100)
    notes = []
    if gm_src != "actual":
        notes.append(f"毛利率来源={gm_src}(覆盖率{gm_cov}%)——非实际分产品数据")
    if products.get("has_h1_data"):
        notes.append("含H2半年轨迹数据（年报-半年报推算下半年趋势）")
    if notes:
        lines.append(f"\n数据质量: {'; '.join(notes)}")

    lines.append("\n> **分部映射要求**: 在reasoning_trace清单项3e中,逐产品说明你把它归入哪个SOTP分部、为什么。产品增速是赋CAGR的硬锚——新业务分部CAGR必须与该分部内产品的实际YoY增速一致,不得凭空取值。")

    # 毛利率结构分析
    margin = products.get("margin_structure", {}) or {}
    if margin:
        gm_spread = margin.get("gm_spread_ppt", 0)
        imp_src = margin.get("gm_improvement_source", "?")
        lines.append(f"毛利率极差: {gm_spread}ppt | 改善来源: {imp_src}")

    # 增速时效性提示：产品表是年报数据，Q1加速信号在软素材和火山数据中
    data_vintage = products.get("data_vintage", "")
    if "2025" in str(data_vintage):
        lines.append(f"\n> 以上产品增速基于{data_vintage}。赋CAGR前按以下顺序交叉验证：")
        lines.append("> 1. 查看'事件推演'——各产品线的最新增速是否显著高于上述2025全年增速？")
        lines.append("> 2. 查看'火山联网搜索'——券商对各产品线的未来2年收入预测是否隐含更高的增速预期？")
        lines.append("> 3. 结合事件驱动逻辑——事件变量是加速、跃迁、还是稳步推进？若事件指向技术突破/产能释放/客户导入等质变节点，CAGR应反映非线性加速而非均值回归。")
        lines.append("> 4. **dcf锚判定**——检查以上三条交叉验证的结论：(a)分产品毛利率是否可直接取到？(b)毛利率改善+规模效应→ROIC从当前水平升至8%以上的路径是否可见？(c)火山数据的产能/订单是否约束了增速上限使终局可预见？若三项全满足，叙事主锚分部应使用dcf锚（两阶段DCF）而非revenue锚——dcf能建模增长→利润→现金流的完整路径。三项中任一不满足则保持revenue锚。")

    return "\n".join(lines)


def _build_recent_growth_row(core: dict) -> str:
    """Extract recent 4Q revenue YoY growth from Forward-Looking data."""
    fw = core.get('_forward_looking', {}) or {}
    cats = fw.get('categories', {}) or {}
    mg = cats.get('management_guidance', {}) or {}
    et = mg.get('earnings_trend', {}) or {}
    recent = et.get('recent_4q', [])
    if not recent:
        return ''

    parts = []
    for q in recent[:4]:
        period = str(q.get('period', ''))
        if len(period) >= 6:
            yr = period[2:4]
            m = int(period[4:6])
            qn = (m - 1) // 3 + 1
            label = f"{yr}Q{qn}"
        else:
            label = period
        yoy = q.get('revenue_yoy') or q.get('revenue_q_yoy')
        if yoy is not None:
            parts.append(f'{label}={yoy:+.1f}%'.replace('+', '+'))

    if not parts:
        return ''
    trend = et.get('trend_direction', '')
    trend_str = f' | {trend}' if trend else ''
    hint = (
        '**最近季度营收同比增速(公司整体)**: ' +
        ' | '.join(parts) + trend_str + '\n'
        '> **SOTP分部增速对照**: 上述增速是公司整体——老业务基数大会拖低整体增速。'
        '赋CAGR前必须做两步:\n'
        '> 1. 将上方"产品结构"中的各产品线映射到你的SOTP分部——哪些产品属于叙事主锚分部,哪些属于副锚\n'
        '> 2. 用各产品的YoY增速校准对应分部的CAGR——老业务取老业务的实际增速,新业务取新业务的实际增速\n'
        '> **关键**: 若产品表中新业务产品增速远高于公司整体(如44% vs 12%),'
        '新业务分部CAGR应接近产品增速而非公司整体增速。'
        '反之,若新业务产品Q1增速明显减速(如从40%降到12%),'
        'CAGR必须反映这一趋势——不能假设减速会自动逆转。'
    )
    return hint

def _build_volc_section(volc_data: dict | None) -> str:
    """构建火山搜索段落——SOTP 分部数据的市场视角补充。"""
    if not volc_data:
        return "（未触发火山搜索）"

    text = volc_data.get("volc_text", "")
    if not text:
        return "（火山搜索未返回有效数据）"

    return f"""**以下数据来自联网搜索（火山引擎），是对 SOTP 各分部/各产品线收入的独立补充。Investoday/Tushare 的产品分类粒度粗（可能合并多个产品线），火山数据来自券商研报和公司披露原文，拆分更细、更接近市场定价视角。如果火山数据与上面的产品结构数据不一致，以火山为准。**

{text}

**火山数据 → SOTP 参数映射**：
- 各产品收入（绝对值） → 直接填入 segment_revenue_yi
- 各产品毛利率 → 减 10-15pp 换算为 segment_net_margin_pct（毛利率到净利率的简化折算）
- 最新季度各产品增速 → 校准该分部的 base CAGR（不应大幅偏离最新实际增速）
- 券商对各产品 2026-2027 收入预测 → 校验你的 (1+CAGR)^3 × segment_revenue 是否与市场一致
- 可比公司当前 PE/PS → 校验你的 target_ps/pe_target（不应无故偏离行业中枢 2σ 以上）
- 产能投产时间/规模 → 约束 CAGR 的物理上限（增速不能超越产能）
- 若火山未覆盖某项数据，回退到 Agent-1 的产品结构数据和行业全貌寻找替代依据"""


def _format_signal_audit(sa: dict) -> str:
    """格式化信号审核摘要。"""
    if not sa:
        return "无"
    items = []
    matches = sa.get("step2b_match", [])
    if matches:
        items.append("交叉验证: " + "; ".join(
            f"{m.get('signal','?')}={m.get('match','?')}" for m in matches[:3]
        ))
    return " | ".join(items) if items else "无异常信号"


def _format_anchor_shift(mn: dict) -> str:
    """格式化范式切换潜力。"""
    asp = mn.get("anchor_shift_potential", {}) or {}
    if not asp.get("shift_possible"):
        return "- 范式切换潜力: 否"
    lines = [
        "- 范式切换潜力: 是",
        "  从 {} -> {}".format(asp.get('from_anchor','?'), asp.get('to_anchor','?')),
        "  触发条件: {}".format(asp.get('shift_trigger','?')),
        "  理由: {}".format(str(asp.get('shift_rationale','?'))[:200]),
        "  时机: {}".format(asp.get('shift_timing','?')),
    ]
    return "\\n".join(lines)


def _format_pricing_tool(agent2a_output: dict) -> str:
    """格式化定价工具详情。"""
    pt = agent2a_output.get("_pricing_tool", {}) or {}
    if not pt or not pt.get("applicable"):
        return "- 定价工具: 不适用"
    lines = [
        "- 定价工具: " + str(pt.get('method','?')),
        "  隐含指标: " + str(pt.get('implied_metric','?')) + " = " + str(pt.get('implied_value','?')),
        "  局限: " + str(pt.get('limitations',[])),
    ]
    return "\n".join(lines)


def _fill_sotp_placeholders(prompt: str, agent2b_output: dict | None = None) -> str:
    """替换 SOTP prompt 中残留的 Agent-3 占位符。"""
    # 从 2b 取主锚分部模型（2b已在SOTP分叉前运行，必有输出）
    seg_model = "B"
    if agent2b_output:
        rd = agent2b_output.get("routing_decision", {})
        if isinstance(rd, dict):
            seg_model = rd.get("sotp_primary_segment_model", "B")
    # 规范化: 取首字母，确保在已知模板中
    seg_model = seg_model[0] if seg_model else "B"
    if seg_model not in MODEL_PARAM_TEMPLATES:
        seg_model = "B"

    # 注入模型专属参数模板（复用 Agent-3 的详细定义）
    # 注意: K/dcf的NOPAT量化校验在 SOTPScenarioAsymmetry.run() 中完成（有data_package可取值）
    schema = MODEL_PARAM_TEMPLATES.get(seg_model, MODEL_PARAM_TEMPLATES["B"])
    self_check = PARAM_SELF_CHECK_MAP.get(seg_model, PARAM_SELF_CHECK_MAP.get("B", ""))
    # 模型专属参数示例（SOTP 的 scenario_details 只存 prob+narrative，但示例要展示
    # seg_model 的完整参数以引导 LLM 在 reasoning_trace 中展开推理）
    params_example_raw = SCENARIO_PARAMS_MAP.get(seg_model, SCENARIO_PARAMS_MAP["A"])

    # seg_model = 2b判定的叙事主锚分部模型 (B/K/A/G等)
    seg_desc = MODEL_NAMES.get(seg_model, seg_model)
    seg_family = MODEL_FAMILIES.get(seg_model, "盈利乘数")

    # 构建分部参数JSON示例：从SCENARIO_PARAMS_MAP取，去掉probability/scenario_narrative
    # （这些属于scenario_details，不属于segments）
    _seg_raw = SCENARIO_PARAMS_MAP.get(seg_model, SCENARIO_PARAMS_MAP["B"])
    import re as _re
    _seg_raw = _re.sub(r'"probability":\s*0?\.?\w+,\s*', '', _seg_raw)
    _seg_raw = _re.sub(r'"scenario_narrative":\s*"[^"]*",?\s*', '', _seg_raw)
    _seg_raw = _re.sub(r',\s*,', ',', _seg_raw)
    _seg_raw = _re.sub(r'{\s*,', '{', _seg_raw)
    _seg_raw = _re.sub(r',\s*}', '}', _seg_raw)

    # 锚映射（模型→SOTP锚名），全部11个模型覆盖
    seg_anchor_map = {"A": "earnings", "B": "revenue", "C": "earnings",
                      "D": "asset", "E": "asset", "F": "pipeline",
                      "G": "earnings", "H": "asset", "I": "earnings",
                      "J": "revenue", "K": "dcf"}

    replacements = {
        "{PRIMARY_MODEL}": seg_model,
        "{MODEL_DESC}": seg_desc,
        "{MODEL_FAMILY}": seg_family,
        "{SEGMENT_ANCHOR}": seg_anchor_map.get(seg_model, "earnings"),
        "{SEGMENT_PARAMS_EXAMPLE}": _seg_raw,
        "{VALIDATION_MODEL}": "自校验(SOTP无独立校验模型)",
        "{VALIDATION_MODEL_DESC}": "SOTP不分拆校验",
        "{SCENARIO_PARAMS_EXAMPLE}": "{" + params_example_raw + "}",
        "{MODEL_PARAM_SCHEMA}": schema,
        "{MODEL_PARAM_NAMES}": (
            f"叙事主锚({seg_model}模型): {MODEL_PARAM_NAMES_MAP.get(seg_model, 'probability, pe_target, ...')}\n"
            f"其他业务(base only): pe_target+segment_net_margin_pct(earnings)或target_ps(revenue)或target_pb(asset)"
        ),
        "{MODEL_PARAM_SELF_CHECK}": (
            f"- 叙事分部({seg_model}模型):\n{self_check}\n"
            "- 叙事分部参数单调递增(bear<base<bull)\n"
            "- 其他业务: PE/PS/PB与主锚分部相同的锚定法则——凭行业知识找可比公司稳态估值,不取当前市场价\n"
            "- Bull/base<=3x"
        ),
    }
    for k, v in replacements.items():
        prompt = prompt.replace(k, v)
    return prompt


def _get_sotp_primary_model(agent2b_output: dict | None) -> str:
    """从 Agent-2b 输出提取叙事主锚分部的模型。"""
    if not agent2b_output:
        return "?"
    rd = agent2b_output.get("routing_decision", {})
    if isinstance(rd, dict):
        return rd.get("sotp_primary_segment_model", "?")
    return "?"


def _get_2b_info(agent2b_output: dict | None) -> str:
    """从 Agent-2b 输出提取主锚模型信息。"""
    if not agent2b_output:
        return "未提供(2b未运行)"
    rd = agent2b_output.get("routing_decision", {})
    model = rd.get("primary_model", "?")
    cat = rd.get("model_category", "?")
    return f"{model} ({cat})"


def _build_sotp_user_message(
    data_package: dict,
    agent2a_output: dict,
    agent2b_output: dict | None,
    event_data: dict,
    wacc_params: dict,
    volc_data: dict | None = None,
    baseline_report: str | None = None,
) -> str:
    """构建 SOTP Agent 用户消息——注入投资地图、分部数据、财务基线、事件背景、2b路由。"""
    core = _get_core_fields(data_package)
    stock = core.get("stock_name", data_package.get("stock_name", ""))
    code = data_package.get("stock_code", "")

    mn = _safe_dict(agent2a_output.get("market_narrative"))
    ep = _safe_dict(agent2a_output.get("event_pricing"))
    sa = _safe_dict(agent2a_output.get("signal_audit"))
    pa = _safe_dict(ep.get("pricing_assessment"))
    primary = mn.get("primary_anchor", "earnings")
    sas = mn.get("secondary_anchors", [])

    # BS画像 (与 Agent-3 对齐)
    bs_section, bs_warning = _build_bs_section(data_package, agent2a_output, wacc_params)

    # ── 核心财务 ──
    mcap = core.get("market_cap_yi", 0)
    rev = core.get("revenue_ttm_yi", 0)
    np = core.get("net_profit_ttm_yi", 0)
    equity = core.get("total_equity_yi", 0)
    cash = core.get("cash_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    gm = core.get("gross_margin_pct", 0)
    nm = core.get("net_margin_pct", 0)
    roic = core.get("roic_pct", 0)
    pe = core.get("pe_ttm", 0)
    pb = core.get("pb", 0)
    ps = core.get("ps_ttm", 0)
    net_cash = cash - debt
    ebitda = core.get("ebitda_ttm_yi", 0)
    ebitda_margin = ebitda / max(rev, 1) * 100

    # ── 事件窗口价格 ──
    ew = _safe_dict(data_package.get("event_window_prices"))
    ew_text = ""
    if ew and ew.get("source") not in ("none", None):
        pre = _safe_dict(ew.get("pre_event"))
        post = _safe_dict(ew.get("post_event"))
        cur = _safe_dict(ew.get("current"))
        ew_text = f"""
## 事件窗口价格
| 窗口 | 均价 |
|------|------|
| 事件前({pre.get('num_days','?')}日) | {pre.get('avg_close','?')} |
| 事件后({post.get('num_days','?')}日) | {post.get('avg_close','?')} |
| 最新({cur.get('date','?')}) | {cur.get('close','?')} |
"""

    # ── 前瞻信号面板 ──
    signal_panel = build_forward_signal_panel(core)

    # 路由信息
    rd_2b = (agent2b_output or {}).get("routing_decision", {}) if isinstance(agent2b_output, dict) else {}

    # ── V7: 投资地图 ──
    baseline_section = ""
    if baseline_report and len(baseline_report) > 100:
        baseline_section = f"""
## 投资地图 — Agent-Baseline 合成（事件冲击前的企业全貌，主输入）

{baseline_report}

---
"""

    msg = f"""# SOTP 分部估值: {stock}({code})
{baseline_section}
## 一、前置裁决 — Agent-2a 叙事诊断 + Agent-2b 路由（已审核，可直接信任，不可推翻）

- 主锚: {primary}
- 锚证据: {mn.get('primary_anchor_evidence','?')[:200]}
- 核心赌注: {mn.get('core_bet','?')}
- 叙事总结: {mn.get('narrative_summary','?')[:300]}
- 生命周期: {mn.get('narrative_lifecycle','?')}
- SOTP触发理由: {mn.get('sotp_rationale','?')}
- 锚冲突: {mn.get('anchor_conflict','') or '无'}
- 事件分布形状: {ep.get('event_profile',{}).get('distribution_shape','?')} — {ep.get('event_profile',{}).get('shape_rationale','?')[:150]}
- 计价程度: {pa.get('overall_priced_in','?')}（{pa.get('priced_in_estimate','?')}）
- 剩余催化: {pa.get('residual_catalyst','?')[:200]}
- 信号评分: {sa.get('step2d_score','?')}/10 — {sa.get('score_rationale','?')[:200]}
- 信号审核: {_format_signal_audit(sa)}
{_format_anchor_shift(mn)}
{_format_pricing_tool(agent2a_output)}
- Agent-2b 路由: 主模型={_get_2b_info(agent2b_output)}, 叙事主锚分部模型={_get_sotp_primary_model(agent2b_output)}

## 二、事件素材 — 当前情形的一手数据，是估值参数的主要锚定来源

> **数据层级原则**: 以下来自事件/行业的产能、价格、利用率、客户认证、供需缺口等信息，
> 反映的是"现在正在发生什么"。在事件驱动框架中，这是你判断当前企业状态的首要依据。
> 财报数据（第三节）反映的是事件冲击前的过去状态——只用于理解冲击幅度和商业模式，
> 不可替代事件素材中的产能/价格/利用率作为当前情形的基准。

### 事件原始文本
{event_data.get('raw_event_text','')}

### 事件研判
{event_data.get('preliminary_reasoning','')}

### 事件推演 (传导链→关键发现→脆弱性与证伪→市场共识对照→瓶颈节点)
{event_data.get('event_deduction','')}

### 逆向推演 (各假设存活强度+降级条件+击穿信号组合)
{event_data.get('adversarial_thinking','')}

### 催化日历 (P0/P1/P2优先级+证实/证伪条件+日历风险提示)
{event_data.get('future','')}

### 投资主题
{event_data.get('investment_theme','')}

### 行业研究
{event_data.get('industry_expert_research','')}

### 火山联网搜索 — SOTP 分部/分产品数据的市场视角补充

{_build_volc_section(volc_data)}

## 三、历史财务基线 — 事件冲击前的企业快照，用于理解冲击幅度和商业模式

> **正确用法**: 以下数据反映事件发生前的企业状态。不要用这些历史数字直接作为
> "当前情形"——事件已经改变了现状（如：价格从100万/吨涨到220万/吨、出口量+198%）。
> 用法: (1) 对比事件素材中的产能×价格×利用率，推算事件造成的收入/利润增量；
> (2) 用历史毛利率/净利率理解企业的成本结构和盈利模型，判断价格变化对利润的杠杆效应；
> (3) 用历史ROIC理解企业的资本回报基线，判断事件能否推动ROIC跨过关键阈值。

| 指标 | 数值 | 指标 | 数值 |
|------|------|------|------|
| 市值 | {mcap:.0f}亿 | PE(TTM) | {pe:.1f}x |
| TTM营收 | {rev:.1f}亿 | PB | {pb:.1f}x |
| TTM净利润 | {np:.1f}亿 | PS(TTM) | {ps:.1f}x |
| EBITDA | {ebitda:.1f}亿 | EBITDA率 | {ebitda_margin:.1f}% |
| ROIC | {roic:.1f}% | 毛利率 | {gm:.1f}% |
| 净资产 | {equity:.0f}亿 | 净利率 | {nm:.1f}% |
| 现金 | {cash:.1f}亿 | 有息负债 | {debt:.1f}亿 |
| 净现金 | {net_cash:.1f}亿 | 数据质量 | {core.get('data_quality_score', '?')}/10 |

**WACC** (代码预计算, 不可修改): {wacc_params.get('wacc_pct', 10)}% (rf={wacc_params.get('rf_pct', '?')}% beta={wacc_params.get('beta', '?')} ERP={wacc_params.get('erp_pct', '?')}%)
{_build_recent_growth_row(core)}
{ew_text}
### 产品结构数据 (Agent-1 财报提取)
{_build_product_mix_section(data_package)}

{signal_panel}

## 分部定义 (Agent-2a 判定 — 你的 SOTP 输出必须以这些分部为基础)

> 下表中"估算收入"是从财报总营收按占比推算的——**这是事件前的历史收入，不是当前水平。**
> 对于事件催动的主锚分部，`segment_revenue_yi` 应以事件素材中的产能×价格×利用率为准，
> 而非下表中的推算值。下表的收入仅作为分部收入占比的参照（帮助理解各分部相对体量）。

{_build_segments_section(sas, primary, mn, core)}

{_build_event_driven_note(rd_2b, sas, primary)}

## 四、反向定价参照 — 当前市值在定价什么故事

{bs_section}{bs_warning}

请按分部独立推演 bear/base/bull 参数。输出纯 JSON。
"""
    return msg


# ═══════════════════════════════════════
# 核心计算函数 — SOTP 分部加总
# ═══════════════════════════════════════

# _compute_other_value removed — LLM handles other business params now


def _compute_segment_value(
    anchor: str,
    params: dict,
    segment_revenue: float,
    core: dict,
) -> float | None:
    """计算单个分部的目标市值。

    Args:
        anchor: 该分部的估值锚 (earnings | revenue | asset | pipeline | dcf)
        params: LLM 输出的该分部该情景参数
        segment_revenue: 该分部的估算收入（亿元）
        core: 公司整体财务数据字典

    Returns:
        分部目标市值（亿元），None 表示参数不足无法计算
    """
    if anchor == "earnings":
        pe = params.get("pe_target", 0)
        net_margin = params.get("segment_net_margin_pct")
        if net_margin is None:
            # 后备: 旧字段 segment_margin_pct（向后兼容），再后备: 公司整体净利率
            net_margin = params.get("segment_margin_pct")
        if net_margin is None:
            net_margin = core.get("net_margin_pct", 0)
        net_margin = net_margin or 0  # .get()在key存在但值为None时不返回default
        segment_revenue = segment_revenue or 0
        if pe > 0 and segment_revenue > 0 and net_margin > 0:
            segment_net_profit = segment_revenue * net_margin / 100
            return round(segment_net_profit * pe, 1)
        return None

    elif anchor == "revenue":
        # 两种模式:
        #   Mode A (连续增长): LLM提供CAGR → future_revenue = revenue × (1+CAGR)³
        #   Mode B (0→1阶跃): LLM基于事件冲击直接估3年后收入 → forward_revenue_3y_yi
        forward_rev = params.get("forward_revenue_3y_yi")
        if forward_rev and forward_rev > 0:
            future_revenue = forward_rev
        else:
            cagr = params.get("revenue_growth_3y_cagr_pct", 0)
            future_revenue = segment_revenue * (1 + cagr / 100) ** 3 if segment_revenue > 0 else 0
        ps = params.get("target_ps") or 0
        if future_revenue > 0 and ps > 0:
            return round(future_revenue * ps, 1)
        return None

    elif anchor == "asset":
        pb = params.get("target_pb", 0)
        total_revenue = core.get("revenue_ttm_yi", 1)
        if pb > 0 and total_revenue > 0:
            # 优先使用 LLM 提供的分部净资产（若提供）
            segment_equity = params.get("segment_equity_yi")
            if segment_equity is None or segment_equity <= 0:
                # 后备: 按收入占比估算（对重资产/轻资产混合的公司有偏差）
                total_equity = core.get("total_equity_yi", 1)
                segment_equity = total_equity * (segment_revenue / total_revenue)
            return round(segment_equity * pb, 1)
        return None

    elif anchor == "pipeline":
        pos = (params.get("pos_pct", 0) or 0) / 100  # pos_pct=25 → 0.25
        peak = params.get("peak_sales_yi", 0) or 0
        rate = params.get("discount_rate_pct", 15) or 0
        if peak > 0 and pos > 0 and rate > 0:
            return round(peak * pos / (1 + rate / 100), 1)
        return None

    elif anchor == "dcf":
        g1 = params.get("stage1_growth_pct", 0) / 100
        years = int(params.get("stage1_years", 5) or 5)
        term_pe = params.get("terminal_pe", 0)
        roic_k = params.get("roic_assumed_pct", 0) / 100
        wacc_k = core.get("_wacc_decimal", 0.10)

        net_margin = params.get("segment_net_margin_pct")
        if net_margin is None:
            net_margin = params.get("segment_margin_pct")
        if net_margin is None:
            net_margin = core.get("net_margin_pct", 0)
        net_margin = net_margin or 0
        segment_revenue = segment_revenue or 0

        if g1 <= 0 or term_pe <= 0 or roic_k <= 0 or segment_revenue <= 0 or net_margin <= 0:
            return None

        nopat = segment_revenue * net_margin / 100
        pv_stage1 = 0.0
        for t in range(1, min(years, 10) + 1):
            nopat = nopat * (1 + g1)
            rr = g1 / roic_k if roic_k > 0 else 0.5
            rr = max(0.3, min(0.9, rr))
            fcff = nopat * (1 - rr)
            pv_stage1 += fcff / (1 + wacc_k) ** t

        tv = nopat * term_pe
        pv_tv = tv / (1 + wacc_k) ** min(years, 10)
        return round(pv_stage1 + pv_tv, 1)

    return None


def _compute_sotp_total(
    segments: list[dict],
    scenario_name: str,
    core: dict,
) -> dict:
    """计算单个情景的 SOTP 加总价值。

    SOTP = Σ各分部(LLM参数) + 净现金
    叙事主锚分部用 scenario 对应参数(bear/base/bull)；
    其他业务用 base 参数(三情景不变)。

    Args:
        segments: LLM 输出的分部列表(含 is_primary 标志)
        scenario_name: "bear" | "base" | "bull"
        core: 公司整体财务数据
    """
    total_revenue = core.get("revenue_ttm_yi", 1)
    cash = core.get("cash_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    net_cash = cash - debt

    # PE/PS/PB 是权益乘数（市值=权益价值），已内含资本结构定价。
    # 用权益乘数估值的分部不应再额外减扣净负债——那是重复扣减。
    # 只有 EV/EBITDA 等企业价值乘数才需要减净负债得到权益价值。
    total_value = 0.0  # 从零开始，不预扣净负债
    total_ev_value = 0.0  # 追踪 EV 类分部价值（需要减债）
    has_ev_segments = False
    segment_values = []
    primary_val = None
    other_val = 0.0

    for seg in segments:
        if not isinstance(seg, dict):
            print(f"  [SOTP] ⚠️ segment不是dict, 跳过: type={type(seg).__name__}", flush=True)
            continue

        seg_name = seg.get("segment", "?")
        anchor = seg.get("anchor", "earnings")
        is_primary = seg.get("is_primary", True)

        # ── 分部收入: 优先用 LLM 直接输出的绝对收入 ──
        seg_revenue = seg.get("segment_revenue_yi")
        if seg_revenue is None or seg_revenue <= 0:
            # 后备: 旧格式用 revenue_share_pct（向后兼容）
            share = seg.get("revenue_share_pct", 0)
            if share > 0:
                seg_revenue = total_revenue * share / 100
            else:
                seg_revenue = 0

        # 非主锚分部：始终使用 base 参数（不受事件驱动）
        if not is_primary:
            params = seg.get("base", {})
        else:
            params = seg.get(scenario_name, {})

        # 防御 LLM 输出格式错误：params 必须是 dict
        if not isinstance(params, dict):
            print(f"  [SOTP] ⚠️ {seg_name}/{scenario_name} params不是dict: type={type(params).__name__} val={str(params)[:200]}", flush=True)
            params = {}

        seg_val = _compute_segment_value(anchor, params, seg_revenue, core)

        if seg_val is not None:
            # 权益乘数(PE/PS/PB) → 直接加总，不再减债（已内含杠杆定价）
            # EV乘数(EV/EBITDA) → 计入EV池，最后统一减净负债
            if anchor == "resource":  # E model uses EV/EBITDA
                total_ev_value += seg_val
                has_ev_segments = True
            else:
                total_value += seg_val
            segment_values.append({
                "segment": seg_name,
                "anchor": anchor,
                "segment_revenue_yi": round(seg_revenue, 2),
                "segment_value_yi": seg_val,
                "source": "LLM(变参)" if is_primary else "LLM(base)",
            })
            if is_primary:
                primary_val = (primary_val or 0) + seg_val
            else:
                other_val += seg_val

    # ── 净负债调整: 仅对 EV 乘数分部做，权益乘数分部已内含杠杆 ──
    if has_ev_segments and net_cash < 0:
        # EV类分部价值减净负债 → 权益价值
        total_value += total_ev_value + net_cash
        total_value = max(0.0, total_value)  # 有限责任底线
    elif has_ev_segments:
        total_value += total_ev_value + net_cash  # net_cash为正→加现金

    # ── 经济底线: 权益价值不能为负（有限责任原则）──
    raw_total = round(total_value, 1)
    floor = max(0.0, net_cash) if net_cash > 0 else 0.0
    floored_total = max(floor, raw_total)
    was_floored = floored_total > raw_total

    return {
        "total_mcap_yi": floored_total,
        "total_mcap_raw_yi": raw_total if was_floored else None,  # 仅触发底线时记录原始值
        "net_cash_yi": round(net_cash, 1),
        "primary_value_yi": primary_val,
        "other_value_yi": round(other_val, 1) if other_val > 0 else 0,
        "segment_values": segment_values,
        "skipped_segments": [],
        "_floor_applied": was_floored,
    }


def _compute_sotp_from_llm(
    llm_output: dict,
    core: dict,
) -> dict:
    """从 LLM 输出计算 SOTP 三情景加权结果。

    所有分部均由 LLM 输出参数，代码计算各分部价值后加总。
    回写计算结果到 llm_output，使其与 _assemble_final_output 兼容。
    """
    segments = llm_output.get("segments", [])
    # 兼容旧格式: primary_segment
    if not segments:
        ps = llm_output.get("primary_segment", {})
        if ps:
            segments = [ps]
            print(f"  [SOTP] LLM used old 'primary_segment' format", flush=True)
        else:
            # 诊断: LLM未输出segments, 打印顶层键以排查
            print(f"  [SOTP] WARNING: LLM未输出segments! 顶层键: {list(llm_output.keys())[:20]}", flush=True)
            # 尝试从scenario_valuation中提取
            sv_test = llm_output.get("scenario_valuation", {})
            if isinstance(sv_test, dict):
                sd_test = sv_test.get("scenario_details", {})
                print(f"  [SOTP] scenario_details type={type(sd_test).__name__} keys={list(sd_test.keys())[:5] if isinstance(sd_test, dict) else '?'}", flush=True)
    sv = llm_output.get("scenario_valuation", {})
    details_raw = sv.get("scenario_details", {})

    # 容错: LLM 可能输出数组格式
    if isinstance(details_raw, list):
        details = {}
        for item in details_raw:
            name = item.get("scenario", "")
            if name in ("bear", "base", "bull"):
                details[name] = item
    else:
        details = details_raw

    current_mcap = core.get("market_cap_yi", 50)
    probs, upsides, mcaps = [], [], []

    for scenario_name in ("bear", "base", "bull"):
        sotp = _compute_sotp_total(segments, scenario_name, core)
        target_mcap = sotp["total_mcap_yi"]

        prob = details.get(scenario_name, {}).get("probability", 0)
        if prob is None or prob == 0:
            # 保守兜底: 偏 base-dominant（15/70/15），避免尾巴概率被高估
            # 若 LLM 连概率都没输出 → 不确定性极高 → bull 不应有显著权重
            defaults = {"bear": 0.15, "base": 0.70, "bull": 0.15}
            prob = defaults.get(scenario_name, 0.15)
            details[scenario_name]["probability"] = prob
            details[scenario_name]["_probability_fallback"] = True
            print(f"  [SOTP] ⚠️ {scenario_name}概率兜底: LLM未输出→使用默认{prob}", flush=True)
        probs.append(prob)

        if current_mcap > 0:
            if target_mcap > 0:
                ups = round((target_mcap / current_mcap - 1) * 100, 1)
            else:
                # 被底线抬升至 0 或接近 0：真实跌幅 ≈ -100%
                ups = -100.0
        else:
            ups = 0

        mcaps.append(target_mcap)
        upsides.append(ups)

        # 回写计算结果到 details
        if scenario_name not in details:
            details[scenario_name] = {}
        details[scenario_name]["target_mcap_yi"] = target_mcap
        details[scenario_name]["upside_pct"] = ups
        details[scenario_name]["_segment_breakdown"] = sotp["segment_values"]
        details[scenario_name]["_net_cash_yi"] = sotp["net_cash_yi"]
        details[scenario_name]["_primary_value_yi"] = sotp["primary_value_yi"]
        details[scenario_name]["_other_value_yi"] = sotp["other_value_yi"]
        if sotp.get("_floor_applied"):
            details[scenario_name]["_floor_applied"] = True
            details[scenario_name]["_floor_raw_mcap"] = sotp.get("total_mcap_raw_yi")

    # 概率归一化（兜底后可能不正好1.0）
    prob_sum = sum(probs)
    if abs(prob_sum - 1.0) > 0.01:
        probs = [p / prob_sum for p in probs]

    # 概率加权计算
    weighted_upside = sum(p * u for p, u in zip(probs, upsides))
    weighted_mcap = sum(p * m for p, m in zip(probs, mcaps))
    bear_u = upsides[0]
    bull_u = upsides[2]
    asym = abs(bull_u / bear_u) if bear_u != 0 and abs(bull_u) > 0 else 0

    # 回写 scenario_valuation
    sv["scenario_details"] = details
    sv["probability_weighted_upside_pct"] = round(weighted_upside, 1)
    sv["probability_weighted_mcap_yi"] = round(weighted_mcap, 1)
    sv["asymmetry_ratio"] = round(asym, 1)
    sv["_computed_by_code"] = True

    llm_output["scenario_valuation"] = sv

    return {
        "weighted_upside_pct": round(weighted_upside, 1),
        "weighted_mcap_yi": round(weighted_mcap, 1),
        "asymmetry_ratio": round(asym, 1),
    }


# ═══════════════════════════════════════
# SOTP 专属一致性校验
# ═══════════════════════════════════════

def _validate_sotp_specific(
    sotp_result: dict,
    sotp_details: dict,
    core: dict,
) -> list[dict]:
    """SOTP 特有的一致性校验——补充标准 _validate_output。

    Checks:
      1. 分部值单调性: primary_val(bear) < primary_val(base) < primary_val(bull)
      2. 其他业务不变性: other_val 三情景一致
      3. 收入占比和 ≈ 100%
      4. 分部参数 bear < base < bull (逐参数)
    """
    warnings = []

    # Check 1: 分部值单调性
    primary_vals = {}
    for sn in ("bear", "base", "bull"):
        d = sotp_details.get(sn, {})
        primary_vals[sn] = d.get("_primary_value_yi")
    if primary_vals.get("bear") is not None and primary_vals.get("base") is not None and primary_vals.get("bull") is not None:
        if not (primary_vals["bear"] < primary_vals["base"] < primary_vals["bull"]):
            warnings.append({
                "code": "E401", "level": "SOTP",
                "message": f"主锚分部值非单调递增: bear={primary_vals['bear']} base={primary_vals['base']} bull={primary_vals['bull']}",
            })

    # Check 2: 其他业务不变性
    other_vals = {}
    for sn in ("bear", "base", "bull"):
        d = sotp_details.get(sn, {})
        other_vals[sn] = d.get("_other_value_yi", 0)
    unique_other = set(round(v, 1) for v in other_vals.values() if v is not None)
    if len(unique_other) > 1:
        warnings.append({
            "code": "E402", "level": "SOTP",
            "message": f"其他业务分部值应在三情景中不变，实际值: {other_vals}",
        })

    # Check 3: 收入占比和（优先用 revenue_share_pct，若缺失则用 segment_revenue_yi 推算）
    segments = sotp_result.get("segments", [])
    if segments:
        total_share = sum(seg.get("revenue_share_pct", 0) for seg in segments)
        if total_share < 1:
            # LLM 未填 revenue_share_pct → 用 segment_revenue_yi 替代校验
            total_rev = core.get("revenue_ttm_yi", 0)
            if total_rev > 0:
                total_share = sum(
                    (seg.get("segment_revenue_yi", 0) or 0) / total_rev * 100
                    for seg in segments
                )
        if abs(total_share - 100) > 15:  # 放宽容差：分部收入可能含非经常性或内部抵消
            warnings.append({
                "code": "E403", "level": "SOTP",
                "message": f"分部收入占比之和={total_share:.1f}%（应≈100%）",
            })

    # Check 4: 分部级 monotonic 参数递增
    for seg in segments:
        if not seg.get("is_primary", True):
            continue
        anchor = seg.get("anchor", "")
        key_params = {
            "earnings": ["pe_target", "segment_net_margin_pct"],
            "revenue": ["revenue_growth_3y_cagr_pct", "forward_revenue_3y_yi", "target_ps"],
            "asset": ["target_pb"],
            "pipeline": ["pos_pct", "peak_sales_yi"],
            "dcf": ["stage1_growth_pct", "terminal_pe", "roic_assumed_pct"],
        }.get(anchor, [])

        for param_name in key_params:
            vals = {}
            for sn in ("bear", "base", "bull"):
                vals[sn] = seg.get(sn, {}).get(param_name)
            if all(v is not None for v in vals.values()):
                if not (vals["bear"] <= vals["base"] <= vals["bull"]):
                    warnings.append({
                        "code": "E404", "level": "SOTP",
                        "message": f"分部'{seg.get('segment','?')}'参数{param_name}非递增: bear={vals['bear']} base={vals['base']} bull={vals['bull']}",
                    })

    return warnings

def _sotp_capital_structure_check(core: dict, sotp_base_mcap: float) -> dict:
    """诊断净现金对 SOTP 估值的影响程度。

    问题: 当 |净负债| 接近或超过分部价值时，SOTP 退化为
    "债务覆盖测试"而非真正的分部估值。此函数标记这些情况。

    Returns:
        {"leverage_flag": "normal"|"high"|"extreme", "note": str,
         "net_cash_pct_of_sotp": float}
    """
    cash = core.get("cash_yi", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    net_cash = cash - debt
    mcap = core.get("market_cap_yi", 50)
    equity = core.get("total_equity_yi", 0)

    # 净现金占市值比例
    net_cash_pct_of_mcap = abs(net_cash) / mcap * 100 if mcap > 0 else 0
    # 净现金占 SOTP base 比例
    net_cash_pct_of_sotp = abs(net_cash) / sotp_base_mcap * 100 if sotp_base_mcap > 0 else 0

    if net_cash < 0 and (net_cash_pct_of_sotp > 50 or net_cash_pct_of_mcap > 60):
        flag = "extreme"
        note = (f"净负债{-net_cash:.0f}亿占SOTP Base {sotp_base_mcap:.0f}亿的{net_cash_pct_of_sotp:.0f}%。"
                f"SOTP估值对分部参数的敏感性被净负债剧烈放大——Bear情景下"
                f"分部价值可能完全被净负债吞噬。这不是传统意义上的分部估值，"
                f"而是'分部价值能否跑赢债务黑洞'的二元赌注。"
                f"建议同时评估债务可持续性。")
    elif net_cash < 0 and (net_cash_pct_of_sotp > 30 or net_cash_pct_of_mcap > 30):
        flag = "high"
        note = (f"净负债{-net_cash:.0f}亿占SOTP Base {sotp_base_mcap:.0f}亿的{net_cash_pct_of_sotp:.0f}%。"
                f"净负债对SOTP估值有显著影响。Bear情景下分部价值可能不足以覆盖净负债。")
    elif net_cash > 0 and net_cash_pct_of_sotp > 30:
        flag = "cash_heavy"
        note = (f"净现金{net_cash:.0f}亿占SOTP Base {sotp_base_mcap:.0f}亿的{net_cash_pct_of_sotp:.0f}%。"
                f"大量净现金对SOTP估值有显著正面影响。请注意：分部估值(PE/PS/PB法)"
                f"已内含分部应占的现金部分——在SOTP顶层再加净现金可能部分双计。")
    else:
        flag = "normal"
        note = "净现金/净负债对SOTP估值影响在正常范围内。"

    return {
        "leverage_flag": flag,
        "note": note,
        "net_cash_yi": round(net_cash, 1),
        "net_cash_pct_of_mcap": round(net_cash_pct_of_mcap, 1),
        "net_cash_pct_of_sotp_base": round(net_cash_pct_of_sotp, 1),
    }

def _sotp_sanity_check(
    core: dict,
    segments: list[dict],
    sotp_base_mcap: float,
    primary_anchor: str,
) -> dict:
    """用公司整体简单倍数做 SOTP 的独立交叉校验。

    原理: 取"其他业务"分部的行业合理倍数，反推如果整家公司用
    同样倍数估值会是多少。与 SOTP 加总结果对比，差异 >30% 标记。

    这不是严格意义上的"第二模型"，但提供了零成本的独立视角——
    至少比"自查——无独立验证"更有信息量。

    Returns:
        validation_crosscheck 兼容格式 dict
    """
    # 1. 从"其他业务"分部提取行业合理倍数作为参考
    ref_pe = None
    ref_ps = None
    for seg in segments:
        if not seg.get("is_primary", True):
            anchor = seg.get("anchor", "")
            base_params = seg.get("base", {})
            if anchor == "earnings":
                ref_pe = base_params.get("pe_target")
            elif anchor == "revenue":
                ref_ps = base_params.get("target_ps")
            # asset 锚不产生可比的 PE/PS

    # 2. 用参考倍数估算整家公司价值
    simple_mcap = None
    method_label = ""

    if ref_pe and ref_pe > 0:
        net_profit = core.get("net_profit_ttm_yi", 0)
        if net_profit > 0:
            simple_mcap = round(net_profit * ref_pe, 1)
            method_label = f"整体PE法 (PE={ref_pe}x × TTM净利{net_profit:.1f}亿)"

    if simple_mcap is None and ref_ps and ref_ps > 0:
        revenue = core.get("revenue_ttm_yi", 0)
        if revenue > 0:
            simple_mcap = round(revenue * ref_ps, 1)
            method_label = f"整体PS法 (PS={ref_ps}x × TTM营收{revenue:.1f}亿)"

    if simple_mcap is None:
        # 用最保守的兜底倍数
        net_profit = core.get("net_profit_ttm_yi", 0)
        if net_profit > 0:
            simple_mcap = round(net_profit * 15, 1)  # A股底线PE
            method_label = f"保守PE法 (PE=15x × TTM净利{net_profit:.1f}亿)"
        else:
            revenue = core.get("revenue_ttm_yi", 0)
            if revenue > 0:
                simple_mcap = round(revenue * 1.5, 1)  # A股底线PS
                method_label = f"保守PS法 (PS=1.5x × TTM营收{revenue:.1f}亿)"

    if simple_mcap is None or simple_mcap <= 0:
        return {
            "validation_model": "简易倍数校验",
            "validation_paradigm": "无法执行",
            "base_target_mcap_yi": sotp_base_mcap,
            "validation_mcap_yi": None,
            "gap_pct": None,
            "gap_direction": "无法计算",
            "assessment": "无可用倍数——SOTP无独立校验",
        }

    # 3. 计算差异 → SOTP 感知的评估标签
    gap_pct = round((sotp_base_mcap / simple_mcap - 1) * 100, 1)
    gap_abs = abs(gap_pct)

    if gap_abs <= 30:
        assessment = "互相印证"
        note = "整体倍数与SOTP大致吻合，叙事溢价有限"
    elif gap_abs <= 100:
        assessment = "叙事依赖"
        note = f"整体倍数法仅{simple_mcap:.0f}亿，SOTP中{abs(gap_pct):.0f}%的增量来自叙事驱动的分部重估。此偏离是SOTP的预期特征，但提示估值高度依赖事件催化兑现。"
    else:
        assessment = "强叙事依赖"
        note = f"SOTP估值({sotp_base_mcap:.0f}亿)与整体倍数({simple_mcap:.0f}亿)差距{abs(gap_pct):.0f}%。估值近乎完全由事件驱动叙事支撑——若叙事证伪，价值将回归整体倍数水平。这不是校验错误，而是SOTP的'叙事纯度'指标。"

    direction = "SOTP高估" if gap_pct > 0 else "SOTP低估"

    return {
        "validation_model": f"整体倍数锚 ({method_label})",
        "validation_paradigm": "整体倍数视角（SOTP预期偏离——此校验度量'叙事纯度'而非估值准确度）",
        "base_target_mcap_yi": sotp_base_mcap,
        "validation_mcap_yi": simple_mcap,
        "gap_pct": gap_pct,
        "gap_direction": direction,
        "assessment": assessment,
        "_note": note,
    }


# ═══════════════════════════════════════
# SOTPScenarioAsymmetry 主类
# ═══════════════════════════════════════

class SOTPScenarioAsymmetry:
    """SOTP 分部估值 — Agent-3s (V6.1)。

    复用 Agent-3 的校验、组装框架，将估值计算替换为分部加总逻辑。
    单次 LLM 调用完成分部参数推演 + 情景判断。
    """

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key

    def run(
        self,
        data_package: dict,
        agent2a_output: dict,
        agent2b_output: dict | None = None,
        event_data: dict | None = None,
        wacc_params: dict | None = None,
        volc_data: dict | None = None,
        baseline_report: str | None = None,
        progress_cb=None,
    ) -> dict:
        """执行 SOTP 分部估值。

        Args:
            data_package: Agent-1 输出（含 product_mix 和财务数据）
            agent2a_output: Agent-2a 输出（含 secondary_anchors + sotp_triggered）
            event_data: Coze Agent0 预研
            wacc_params: WACC 预计算参数
            baseline_report: V7 Agent-Baseline 投资地图报告
            progress_cb: 进度回调 (step, msg)

        Returns:
            与标准 Agent-3 格式兼容的输出 dict
        """
        cb = progress_cb or (lambda s, n: None)
        # ── 入参防御: 防止上游传入非dict类型(如字符串)导致 .get() 崩溃 ──
        data_package = _safe_dict(data_package)
        agent2a_output = _safe_dict(agent2a_output)
        agent2b_output = _safe_dict(agent2b_output) if agent2b_output else {}
        event_data = _safe_dict(event_data)
        wacc_params = _safe_dict(wacc_params)
        volc_data = _safe_dict(volc_data) if volc_data else {}
        core = _get_core_fields(data_package)

        # ── Step 0: 火山数据（orchestrator预取, 免重复搜索）──
        if volc_data and volc_data.get("volc_text"):
            print(f"  [SOTP] 使用预取火山数据 ({len(volc_data.get('volc_text',''))} chars)", flush=True)
        else:
            cb(0.5, "火山搜索分部数据")
            volc_data = _search_segment_data(
                core.get("stock_name", ""), data_package.get("stock_code", ""),
                data_package, agent2a_output,
            )
            if not volc_data:
                print(f"  [SOTP] 火山搜索无结果，继续使用财报数据", flush=True)

        # ── K/dcf 护栏: SOTP内与标准管线同一规则 ──
        # dcf从NOPAT出发,要求NOPAT>0.5亿且NOPAT/市值>0.8%
        nopat_yi = core.get("nopat_yi", 0) or (core.get("net_profit_ttm_yi", 0) * 0.8)
        mcap_yi = core.get("market_cap_yi", 100)
        nopat_ratio = nopat_yi / max(mcap_yi, 1)
        anchor_2a = (agent2a_output or {}).get("market_narrative", {}).get("primary_anchor", "earnings")
        if agent2b_output and isinstance(agent2b_output, dict):
            rd_check = agent2b_output.get("routing_decision", {})
            if isinstance(rd_check, dict):
                sotp_model = rd_check.get("sotp_primary_segment_model", "B")
                if sotp_model == "K" and (nopat_yi < 0.5 or nopat_ratio < 0.008):
                    # K不适用: NOPAT起点过低,DCF退化为终值PE赌注
                    fallback = "B" if anchor_2a == "revenue" else "A"
                    print(f"  [SOTP] K blocked: NOPAT={nopat_yi:.2f}yi NOPAT/mcap={nopat_ratio*100:.2f}% < 0.8% → override to {fallback}", flush=True)
                    rd_check["sotp_primary_segment_model"] = fallback
                    rd_check["_sotp_k_blocked"] = True
                    agent2b_output["routing_decision"] = rd_check

        # ── Step 1: LLM 推演分部参数 ──
        cb(1, "SOTP LLM分部推演")
        user_msg = _build_sotp_user_message(
            data_package, agent2a_output, agent2b_output, event_data, wacc_params,
            volc_data=volc_data,
            baseline_report=baseline_report,
        )

        prompt = _fill_sotp_placeholders(SOTP_SYSTEM_PROMPT, agent2b_output)
        try:
            result = call_deepseek(
                prompt, user_msg,
                temperature=0.1,
                api_key=self.api_key,
            )
        except Exception as e:
            raise ScenarioError("E303", f"SOTP LLM调用失败: {e}")

        # 防御: call_deepseek 通过 parse_json 可能返回非 dict（str/list/None）
        if not isinstance(result, dict):
            print(f"  [SOTP] LLM返回非dict type={type(result).__name__}", flush=True)
            result = {}  # 触发下方 _parse_error 逻辑
        if "_parse_error" in result:
            # 重试一次
            try:
                result = call_deepseek(
                    prompt, user_msg,
                    temperature=0.1,
                    api_key=self.api_key,
                )
                if not isinstance(result, dict):
                    result = {}
            except Exception:
                pass

        if not isinstance(result, dict) or "_parse_error" in result:
            raw_info = str(result.get("_parse_error", ""))[:300] if isinstance(result, dict) else str(result)[:300]
            raise ScenarioError(
                "E301", "SOTP LLM JSON解析失败",
                {"raw": raw_info},
            )

        # ── Step 2: 代码计算 SOTP 加总 ──
        cb(2, "SOTP代码加总")
        core['_wacc_decimal'] = wacc_params.get('wacc_pct', 10) / 100
        try:
            sotp_computed = _compute_sotp_from_llm(result, core)
        except Exception as e:
            print(f"  [SOTP] _compute_sotp_from_llm崩溃: {e}", flush=True)
            print(f"  [SOTP] result type={type(result).__name__}", flush=True)
            if isinstance(result, dict):
                print(f"  [SOTP] result keys: {list(result.keys())[:20]}", flush=True)
                print(f"  [SOTP] result seg字段: {result.get('segments', 'MISSING')}", flush=True)
            raise

        # ── Step 2a: volc 预搜索（从 LLM-1 的 data_gaps 提取）──
        cb(2.5, "volc 预搜索")
        pre_search_queries = _extract_search_queries(result)
        volc_pre_search = ""
        if pre_search_queries:
            volc_results = []
            for q in pre_search_queries:
                try:
                    res = _call_volc_search(q)
                    volc_results.append(f"查询: {q}\n结果: {res}")
                except Exception:
                    volc_results.append(f"查询: {q}\n结果: 搜索失败")
            volc_pre_search = "\n\n".join(volc_results)

        # ── Step 2b: LLM-2 多轮搜索审阅 ──
        cb(2.7, "LLM-2 审阅")
        try:
            # 构建 LLM-2 输入: LLM-1 输出 + 代码计算结果 + 完整上下文
            llm2_result = _call_llm2(
                result, sotp_computed,
                {"pe_ttm": core.get("pe_ttm", 0), "pb": core.get("pb", 0),
                 "implied_g_pct": 0, "market_premium_pct": 0, "ev_yi": 0,
                 "nopat_yi": 0, "roic_pct": 0, "wacc_simple_pct": wacc_params.get("wacc_pct", 10)},
                wacc_params, data_package,
                agent2b_output or {}, event_data,
                agent2a_output=agent2a_output,
                baseline_report=baseline_report,
                volc_pre_search=volc_pre_search,
                system_prompt=SOTP_LLM2_PROMPT,
            )
        except Exception:
            print("  [SOTP] LLM-2 故障，降级为 LLM-1 + 代码修正模式", flush=True)
            import traceback
            traceback.print_exc()
            llm2_result = {}

        # ── Step 2.5: 合并 LLM-1 + LLM-2，LLM-2 为主体 ──
        cb(2.8, "合并输出")
        result = _merge_llm_outputs(result, llm2_result)

        # 应用 LLM-2 的 change_log 参数修改到 segments
        changes = result.get("change_log", [])
        if changes:
            segments = result.get("segments", [])
            for c in changes:
                path = c.get("path", "")
                parts = path.split(".")
                new_val = c.get("new_value")
                # path like "segments.0.base.target_ps" or "segments.1.bull.revenue_growth_3y_cagr_pct"
                if parts[0] == "segments" and len(parts) >= 4:
                    idx = int(parts[1])
                    if idx < len(segments):
                        target = segments[idx]
                        for p in parts[2:-1]:
                            target = target.get(p, {})
                        c["old_value"] = target.get(parts[-1])
                        target[parts[-1]] = new_val
            if changes:
                print(f"  [SOTP] 应用了 {len(changes)} 条参数修改", flush=True)

        # 验证 segments 完整性（重新计算前）— 按锚类型逐分部校验
        final_segments = result.get("segments", [])
        def _seg_has_params(seg: dict, anchor: str, scenarios: list) -> bool:
            """检查分部在指定场景中是否有该锚类型的必需参数。"""
            anchor_key = {"earnings": "pe_target", "revenue": ("target_ps", "revenue_growth_3y_cagr_pct", "forward_revenue_3y_yi"),
                          "asset": "target_pb", "dcf": "stage1_growth_pct", "pipeline": "pos_pct"}
            required = anchor_key.get(anchor)
            if isinstance(required, tuple):
                required = required[0]  # 取第一个作为主检查
            for sn in scenarios:
                params = seg.get(sn, {})
                if isinstance(params, dict) and params.get(required):
                    return True
            return False

        valid_segs = 0
        for i, seg in enumerate(final_segments):
            if not isinstance(seg, dict) or not seg.get("anchor"):
                print(f"  [SOTP] WARNING: segment[{i}] 无anchor, 跳过", flush=True)
                continue
            anchor = seg.get("anchor", "")
            is_primary = seg.get("is_primary", False)
            scenarios = ("bear", "base", "bull") if is_primary else ("base",)
            if _seg_has_params(seg, anchor, scenarios):
                valid_segs += 1
            else:
                seg_name = seg.get("segment", f"#{i}")
                print(f"  [SOTP] WARNING: {seg_name}(anchor={anchor},primary={is_primary}) 缺少{anchor}锚必需参数, 无法计算", flush=True)
        if len(final_segments) == 0:
            print(f"  [SOTP] WARNING: segments为空, 无法重新计算!", flush=True)
        elif valid_segs < len(final_segments):
            print(f"  [SOTP] WARNING: 仅{valid_segs}/{len(final_segments)}个分部有可计算参数, 缺少参数的分部将被跳过", flush=True)

        # 在 LLM-2 的参数上重新计算
        sotp_computed = _compute_sotp_from_llm(result, core)
        sv = result.get("scenario_valuation", {})
        sv["probability_weighted_upside_pct"] = sotp_computed["weighted_upside_pct"]
        sv["probability_weighted_mcap_yi"] = sotp_computed["weighted_mcap_yi"]
        sv["asymmetry_ratio"] = sotp_computed["asymmetry_ratio"]
        sv["_computed_by_code"] = True

        # ── Step 3: 修正交易标注 ──
        cb(3, "修正交易标注")
        ta = result.get("trade_annotation", {})
        sv = result.get("scenario_valuation", {})
        details = sv.get("scenario_details", {})
        if isinstance(details, list):
            details_dict = {}
            for item in details:
                name = item.get("scenario", "")
                if name in ("bear", "base", "bull"):
                    details_dict[name] = item
            details = details_dict
        bear_u = details.get("bear", {}).get("upside_pct", 0)
        bull_u = details.get("bull", {}).get("upside_pct", 0)
        result["trade_annotation"] = _fix_trade_annotation(
            ta,
            sotp_computed["weighted_upside_pct"],
            sotp_computed["asymmetry_ratio"],
            bear_u, bull_u,
        )

        # ── Step 4: 校验（复用 Agent-3）──
        cb(4, "一致性校验")
        bs_profile = {
            "bs_method": "SOTP 分部加总 (2段: 叙事主锚 + 其他)",
            "bs_level": f"分部独立估值后加总净现金{core.get('cash_yi',0)-core.get('interest_bearing_debt_yi',0):+.1f}亿 → 总市值{sotp_computed['weighted_mcap_yi']:.0f}亿",
            "ev_yi": 0,
            "nopat_yi": 0,
            "roic_pct": 0,
            "wacc_simple_pct": wacc_params.get("wacc_pct", 10),
            "market_premium_pct": 0,
            "implied_g_pct": 0,
            "pe_ttm": core.get("pe_ttm", 0),
            "pb": core.get("pb", 0),
            "market_story": "SOTP: 叙事主锚(LLM推演) + 其他业务(代码自动) + 净现金",
            "warnings": [],
            "wacc_params": wacc_params,
            "bs_secondary": "",
            "note_to_llm": "",
            "reverse_dcf_applicable": False,
            "reverse_dcf_applicable_note": "SOTP 不使用反向DCF——分部加总本身就是定价验证",
            "valuation_anchor_used": "sotp",
        }

        validation_warnings = _validate_output(
            result, bs_profile, wacc_params,
        )
        # 过滤 E306 类（代码已重算，数值差异是预期内的）
        validation_warnings = [
            w for w in validation_warnings
            if not w.get("code", "").startswith("E306")
        ]
        # ── 追加 SOTP 专属校验 ──
        sv_details = sv.get("scenario_details", {})
        sotp_warnings = _validate_sotp_specific(result, sv_details, core)
        validation_warnings.extend(sotp_warnings)

        # ── 强制跨族底线校验 (与标准Agent-3一致) ──
        mandatory_xcheck = _mandatory_cross_validation(
            core, result, agent2b_output or {},
        )
        if mandatory_xcheck:
            existing_xcheck = result.get("validation_crosscheck", {})
            if existing_xcheck and existing_xcheck.get("validation_strategy") == "self_validation":
                mandatory_xcheck["_overrides_llm_selfcheck"] = True
            result["_code_cross_validation"] = mandatory_xcheck

        if validation_warnings:
            codes = [w["code"] for w in validation_warnings]
            print(f"  [SOTP validation] warnings: {codes}", flush=True)

        # ── Step 5: 组装输出（复用 Agent-3 的 _assemble_final_output）──
        cb(5, "组装输出")
        routing = {
            "primary_model": "J",
            "model_category": "SOTP",
            "routing_reason": (
                "Agent-2a 触发 SOTP: 2段式(叙事主锚+其他), "
                "范式冲突需分部独立估值"
            ),
            "validation_models": [],
            "model_migration_path": {},
        }

        output = _assemble_final_output(
            result, bs_profile, data_package, routing, validation_warnings,
            llm_original_values={
                "upside": sotp_computed["weighted_upside_pct"],
                "asymmetry": sotp_computed["asymmetry_ratio"],
                "mcap": sotp_computed["weighted_mcap_yi"],
            },
        )

        # ── SOTP 简易交叉校验（替换 LLM 的"自查——无独立验证"）──
        base_details = sv.get("scenario_details", {}).get("base", {})
        sotp_base_mcap = base_details.get("target_mcap_yi", sotp_computed["weighted_mcap_yi"])
        output["validation_crosscheck"] = _sotp_sanity_check(
            core, result.get("segments", []), sotp_base_mcap,
            primary_anchor=core.get("_primary_anchor", ""),
        )
        if output["validation_crosscheck"].get("gap_pct") is not None:
            gap = abs(output["validation_crosscheck"]["gap_pct"])
            assessment = output["validation_crosscheck"]["assessment"]
            simple = output["validation_crosscheck"]["validation_mcap_yi"]
            if gap > 100:
                print(f"  [SOTP crosscheck] 强叙事依赖: SOTP={sotp_base_mcap:.0f}亿 vs 整体倍数={simple:.0f}亿 (叙事纯度={gap:.0f}%)", flush=True)
            elif gap > 30:
                print(f"  [SOTP crosscheck] 叙事依赖: gap={gap:.0f}%", flush=True)
            else:
                print(f"  [SOTP crosscheck] OK gap={gap:.0f}%", flush=True)

        # ── Step 6: 注入 SOTP 特有字段 ──
        base_details_for_meta = sv.get("scenario_details", {}).get("base", {})
        sotp_base_mcap_meta = base_details_for_meta.get("target_mcap_yi", sotp_computed["weighted_mcap_yi"])
        capital_diag = _sotp_capital_structure_check(core, sotp_base_mcap_meta)
        if capital_diag["leverage_flag"] != "normal":
            print(f"  [SOTP capital] {capital_diag['leverage_flag']}: {capital_diag['note'][:120]}", flush=True)

        # 从 scenario_details 中提取分录计算明细（_compute_sotp_from_llm已写入_segment_breakdown）
        base_details = sv.get("scenario_details", {}).get("base", {})
        computed_segments = base_details.get("_segment_breakdown", [])

        output["_sotp_breakdown"] = {
            "segments": result.get("segments", []),           # LLM参数(含LLM-2修改)
            "computed": computed_segments,                     # 代码计算的各分部值
            "scenario_details": sv.get("scenario_details", {}),
            "capital_structure": capital_diag,
        }
        # 前端可读: 合并参数+计算值
        enriched_segments = []
        for i, seg in enumerate(result.get("segments", [])):
            enriched = dict(seg)
            if i < len(computed_segments):
                enriched["_computed"] = computed_segments[i]
            enriched_segments.append(enriched)
        output["segments"] = enriched_segments
        output["llm2_change_log"] = result.get("_llm2_change_log", result.get("change_log", []))
        output["llm_split_version"] = result.get("_llm_split_version", "1-call")

        cb(6, "SOTP估值完成")
        return output


# ── 便捷函数 ──

def run_sotp_scenario(
    data_package: dict,
    agent2a_output: dict,
    event_data: dict | None = None,
    wacc_params: dict | None = None,
) -> dict:
    """便捷入口：运行 SOTP 分部估值。"""
    agent = SOTPScenarioAsymmetry()
    return agent.run(data_package, agent2a_output, event_data, wacc_params)
