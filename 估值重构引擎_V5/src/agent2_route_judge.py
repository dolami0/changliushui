"""
Agent-2 路由判官 (RouteJudge) — V5

V5 管线中唯一拥有模型选择权的 Agent。

执行流程:
  Step 1: V3 案例匹配（代码，case_loader）→ Top8 案例 + 锚点
  Step 2: 三层路由决策（LLM）→ 业务本质→盈利框架→估值水位
  Step 3: 冲突仲裁 → 规则1:业务优先 2:盈利否决 3:增速优先
  Step 5: 迁移路径预判 → 当前模型→触发条件→下一阶段模型
  Step 6: 增量补取检查 → 触发则 Orchestrator 回退 Agent-1

原则:
  - 采购员不判案: Agent-0 hint 仅供参考，Agent-2 独立判决
  - 前置搜索、后置推演: Agent-2 做完搜索，Agent-3 专注推演裁决
  - 最多2轮搜索，不可无限循环
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_config import DEEPSEEK_API_KEY
import case_loader

# ═══════════════════════════════════════
# System Prompt — 路由判官专用（聚焦路由，不涉及估值计算）
# ═══════════════════════════════════════

ROUTE_JUDGE_SYSTEM_PROMPT = """你是估值路由判官。你的唯一职责: 基于完整数据，为标的公司选择最适合的估值模型。

# 执行模式

直接输出 `action = "evaluate"`:

## 输出格式
```json
{"action": "evaluate", "routing_decision": {
  "valuation_anchor": "earnings",
  "hard_constraints_applied": ["ROIC<8%→排除A", "亏损→排除C/G"],
  "primary_model": "A",
  "secondary_model": "B",
  "model_category": "Earnings Multiples",
  "routing_reason": "...",
  "validation_models": ["B"],
  "validation_rationale": "选B(PS+TAM)做交叉校验: A用盈利视角估值, B用收入视角——两个范式互为印证。B通过硬约束: 亏损+ROIC<8%"
}}
```

`routing_decision` 必须包含:
- `valuation_anchor`: "earnings"|"revenue"|"asset"|"pipeline" — Step 1 识别的估值锚
- `hard_constraints_applied`: string[] — Step 2 中实际触发的排除规则（如"ROIC<8%→排除A"），至少列出2条
- `primary_model`: A-J 单字母
- `model_category`: "Earnings Multiples"|"Revenue Multiples"|"Asset/Resource"
- `routing_reason`: 引用具体财务数据+事件叙事，≥100字
- `validation_models`: 至少1个校验模型
- `validation_rationale`: 说明校验模型为何通过硬约束

# 路由决策框架 — 锚驱动原则

**核心公理**: 估值模型跟"市场在为什么定价"，不跟"公司有什么资产"。事件叙事决定估值锚，估值锚决定模型。历史资产结构不能否决事件驱动的范式切换。

## 第零层: 案例破平局

V3案例锚点含历史模型选择，但来自十倍股案例库(幸存者偏差)。**案例只能破平局，不能否决逻辑**:
1. 先独立完成路由，得初步判断
2. 仅当 2 个模型都合理时(如 A vs G)，用案例破平局
3. 案例不能否决硬约束(如亏损→不可用A)
4. 禁止"3个案例都用了PEG所以我们也用"的投票推理

## 路由流程（按顺序执行）

### Step 1: 识别估值锚（从事件叙事推导，不是从资产负债表）

读出 Agent-0 投资主题中的**核心一句话**: "市场在为什么定价？"

| 市场在定价 | 估值锚 | 模型大类 |
|-----------|--------|---------|
| 利润(当前或近期) | PE/DCF | Earnings |
| 收入(增长/TAM/渗透率) | PS | Revenue |
| 资产(资源储量/净资) | PB/EV/NAV | Asset |
| 管线(未商业化) | rNPV/SOTP | Pipeline |

**锚切换识别**: 如果事件叙事把公司从旧锚切换到新锚，路由必须跟随新锚。
例如: 矿业公司的 AI 材料业务 → 旧锚=资源储量, 新锚=收入/TAM → 路由到 B。

### Step 2: 财务状态硬约束（排除不可行的模型）

**这是闸门，不是参考。硬约束与锚识别是 AND 关系：只有同时通过锚匹配和硬约束的模型才能进入候选集。**

检查条件，逐条排除:
- ROIC<0 → 排除 A (DCF需要正ROIC做再投资率基准)
- ROIC<8% → 排除 A (ROIC过低,DCF假设不可靠除非事件明确能在2年内将ROIC推至>8%)
- 亏损+无明确盈利时点 → 排除 C (拐点模型需要可识别的时间节点)
- 非生物医药 → 排除 F (rNPV仅限biotech)
- 增速<20% → 排除 G (PEG需要>30%增速才有意义)
- 非重资产+ROE稳定 → 排除 D (PB-ROE需要重资产+ROE改善逻辑)
- PS > 10x 且亏损 → 排除 C (市场在用收入定价，IC×ROIC×PE 无法配平；应走 B(PS+TAM))

**反向硬约束（盈利企业不可用亏损模型）——这是最常被违反的规则**:
- **盈利+ROIC>8% → 排除 B** (PS+TAM只适用于亏损/微利企业。盈利企业即使叙事围绕收入/TAM，估值锚也是利润——B的准入条件明确要求ROIC<8%或净利润<市值×2%)
- **盈利+ROIC>0 → 排除 C** (Forward DCF+拐点适用于亏损+有拐点时间节点。盈利企业不存在拐点问题，应走A/G/I)
- 简记: B和C是"现在还亏钱"的模型。公司已经赚钱且ROIC>8%，B和C自动出局。

### Step 3: 从剩余候选模型中选最优

按以下优先级:

**优先级1: 估值锚匹配** — 模型的估值锚必须与 Step1 识别的锚一致:
- 收入锚(B) → 模型 B
- 利润锚(A/C/G/I) → 在 A/C/G/I 中选择
- 资产锚(D/E/H) → 在 D/E/H 中选择

**优先级2: 事件-模型契合度**:
- 事件核心是"TAM多大/渗透率多高" → B, 不是 C(B 锚定 TAM+PS, C 锚定盈利时点)
- 事件核心是"盈利何时转正/拐点何时到" → C, 不是 B
- 事件核心是"资源价格/储量变化" → E, 不是 I
- 事件核心是"周期底部均值回归" → I, 不是 C

**优先级4: B vs C 的叙事区分** (两者都处理"亏损/微利+事件"):
- 选 B: 叙事围绕收入爆发(PS锚定TAM/渗透率/收入CAGR),盈利改善是收入增长的**自然结果**而非独立事件
- 选 C: 叙事围绕盈利拐点(DCF锚定拐点时间/改善幅度),收入增长可能已在进行但**拐点本身**是核心变量
- 简记: 叙事在讲"市场会有多大"→B; 叙事在讲"何时开始赚钱"→C

### 模型准入条件（硬约束 + 最优场景）

**Model A (ROIC-RR DCF)**:
- 硬约束: ROIC>8% 或事件明确将ROIC推至>8%且有时序; 净利润>0
- 最优: 盈利稳定,事件改善ROIC或再投资效率

**Model B (PS+TAM)**:
- 硬约束: 当前亏损/微利(ROIC<8%或净利润<市值×2%)
- **反向约束: 盈利企业(ROIC>8%且净利润>市值×2%)不可用B** — 即使事件叙事是"收入/TAM"，盈利企业的估值锚是利润而非收入。B的公式是 revenue×PS，它隐含的前提是"利润还不能用"。
- 最优: 事件叙事围绕①TAM扩张 ②渗透率提升 ③收入CAGR爆发
- **B优先于E**: 当公司虽有资源资产,但事件核心叙事是新产品收入驱动。矿业公司+AI材料事件→选B不选E。

**Model C (DCF+拐点)**:
- 硬约束: 当前亏损/微利; 事件含**可识别的盈利拐点时间节点**(如"2026Q3盈亏平衡""半年报后扭亏")
- **反向约束: 已经盈利的企业(ROIC>0且净利润>0)不可用C** — C的核心逻辑是"拐点前的亏损期→拐点后的正常化利润"，盈利企业不存在拐点概念，应走A/G/I。
- 最优: 拐点逻辑清晰,触发条件具体
- **C vs B**: 若叙事围绕"市场空间+渗透率"而非"盈利时点",选B不选C

**Model D (PB-ROE)**:
- 硬约束: 重资产(总资产/净资产>1.5); ROE有改善逻辑
- 最优: 金融/地产/基建; ROE从周期底部回升

**Model E (EV/EBITDA+资源)**:
- 硬约束: ALL THREE must be true:
  1. 公司拥有不可复制的自然资源(矿/煤/油/气/储量)
  2. 事件核心是对**资源本身**的量/价/储量产生影响
  3. 事件**没有**将估值锚切换到收入或利润大类
- **E 的排除测试**: 如果对以下问题回答"是",则不是 E:
  - 事件的核心叙事是否围绕"新产品线"而非"资源涨价"? → 是→选 B
  - 事件是否将公司定义为"XX 材料/XX 科技"而非"XX 矿"? → 是→选 B 或 C
  - 公司当前的估值溢价(高PE/PS)是在定价新业务还是资源储量? → 新业务→选 B
- 典型E场景: 兖矿(煤炭→煤价/产量→EV/EBITDA); 紫金(铜金矿→金属价格→EV/EBITDA)
- 典型非E场景: 云南锗业(虽有锗矿,但事件是磷化铟衬底→AI材料收入→选B); 天齐锂业(若有新技术突破,锚从锂价切换到新材料收入→选B)

**Model F (rNPV)**:
- 硬约束: **仅限**创新药/biotech(临床阶段管线、FDA/NMPA审批)
- 排除: 科技硬件/SaaS/芯片的"产品管线"概念→用B而非F

**Model G (PEG)**:
- 硬约束: 利润增速>30%且可持续; 盈利为正
- 最优: 增速确认+估值合理(PEG<2)

**Model H (NAV)**:
- 硬约束: 隐蔽资产型(大量未重估资产/投资性房地产/股权)
- 最优: 事件触发资产价值再发现

**Model I (盈利正常化)**:
- 硬约束: 利润波动源于行业周期(航运/化工/养殖/钢铁/造纸); 无硬资产资源
- **I vs E**: 如果公司有矿/煤/油→优先E(资源储量比周期利润更硬)。I 仅用于无硬资产的纯周期股。
- 约束: PE>历史3σ时,先问"市场是否在定价公司质变"而非武断判高估

**Model J (SOTP)**:
- 硬约束: 多元控股/平台型/跨行业经营,分部价值差异大

## 校验模型选择

**校验模型也必须通过硬约束**。先从以下候选池中选择，再执行硬约束过滤：

- A/G → 候选: B / E / C（取第一个通过硬约束的）
- B → 候选: C / G / A（B只适用于亏损企业，校验模型应从盈利模型中选。如果公司盈利→A/G；如果亏损→C）
- D → 候选: A / H
- E/H/J → 候选: A / B

**校验模型硬约束过滤**: 对候选模型依次执行 Step 2 的硬约束检查，第一个通过的即为校验模型。如果全部不通过，选 A（通用基准）并标注"校验模型无最优选择，已降级为A"。validation_rationale 必须说明"为什么这个校验模型通过了硬约束"。

## 重要约束
- Agent-0 的 model_category_hint 仅供参考,必须独立判决
- routing_reason 必须引用具体财务数据+事件叙事
- 总输出 ≤800 tokens
"""

# ═══════════════════════════════════════
# DeepSeek LLM 调用
# ═══════════════════════════════════════

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"


def _parse_json(text: str) -> dict:
    """从 LLM 回复中提取 JSON（增强容错）。

    处理: markdown代码块、前置/后置自然语言、嵌套括号。
    """
    text = text.strip()
    import re

    # 1. 提取 markdown 代码块中的 JSON
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
    if m:
        text = m.group(1).strip()

    # 2. 如果仍有前置文字，找第一个 { 和配对的 }
    if not text.startswith("{"):
        s = text.find("{")
        if s >= 0:
            depth = 0
            e = -1
            for i in range(s, len(text)):
                if text[i] == "{": depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0: e = i; break
            if e > s:
                text = text[s:e + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s = text.find("{")
        e = text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                pass
        return {"_parse_error": "JSON解析失败", "_raw": text[:500]}


def _call_deepseek(system: str, user_message: str, max_tokens: int = 30720,
                   temperature: float = 0) -> dict:
    """调用 DeepSeek API，返回解析后的 routing_decision dict。

    LLM 输出格式: {"action": "evaluate", "routing_decision": {...}}
    本函数自动提取 routing_decision 部分。
    """
    resp = requests.post(
        DEEPSEEK_API,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        },
        json={
            "model": "deepseek-v4-pro",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "max",
        },
        timeout=600,
    )
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        if usage:
            print(f"  [Agent2 tokens] prompt={usage.get('prompt_tokens')} "
                  f"completion={usage.get('completion_tokens')}", flush=True)
        parsed = _parse_json(content)
        # 提取 routing_decision: 支持 {"action":"evaluate","routing_decision":{...}} 格式
        if isinstance(parsed, dict) and "routing_decision" in parsed:
            return parsed["routing_decision"]
        return parsed
    except Exception as e:
        print(f"  [Agent2] LLM response parse error: {e}", flush=True)
        return {"_parse_error": str(e)[:200]}


# ═══════════════════════════════════════
# 增量补取字段检查
# ═══════════════════════════════════════

MODEL_REQUIRED_FIELDS: dict[str, list[str]] = {
    "A": ["roic_pct", "nopat_yi", "pe_ttm", "total_equity_yi"],
    "B": ["revenue_ttm_yi", "ps_ttm", "market_cap_yi"],
    "C": ["roic_pct", "net_profit_ttm_yi", "cash_yi"],
    "D": ["pb", "roe_ttm_pct", "total_equity_yi"],
    "E": ["ev_ebitda", "ebitda", "net_debt_yi"],
    "F": [],  # 依赖 Agent0 语料 + 联网搜索
    "G": ["roic_pct", "pe_ttm", "net_profit_ttm_yi"],
    "H": [],  # 依赖联网搜索
    "I": ["roic_pct", "pe_ttm", "net_profit_ttm_yi"],
    "J": [],  # 依赖联网搜索
}


def _check_missing_fields(primary_model: str, data_package: dict) -> dict:
    """检查选定模型的关键字段是否缺失。"""
    required = MODEL_REQUIRED_FIELDS.get(primary_model, [])
    core_fields = data_package.get("packages", {}).get("core", {}).get("fields", {})
    missing = [f for f in required if not core_fields.get(f) and core_fields.get(f) != 0]
    return {
        "triggered": len(missing) > 0 and primary_model not in ("F", "H", "J"),
        "missing_fields": missing,
        "note": f"模型{primary_model}缺少: {missing}" if missing else "所有关键字段已满足",
    }


# ═══════════════════════════════════════
# 构建用户消息（数据注入）
# ═══════════════════════════════════════

def _build_routing_user_message(
    data_package: dict, case_anchors: str,
    agent0_hint: dict, event_data: dict,
) -> str:
    """构建 LLM 用户消息：注入数据包 + 搜索 + 案例 + hint。"""

    core = data_package.get("packages", {}).get("core", {}).get("fields", {})
    stock = core.get("stock_name", "")
    code = data_package.get("stock_code", "")

    # 提取关键财务数据
    roic = core.get("roic_pct", 0)
    mcap = core.get("market_cap_yi", 0)
    rev = core.get("revenue_ttm_yi", 0)
    np = core.get("net_profit_ttm_yi", 0)
    pe = core.get("pe_ttm", 0)
    pb = core.get("pb", 0)
    equity = core.get("total_equity_yi", 0)
    assets = core.get("total_assets_yi", 0)
    ocf = core.get("ocf_ttm_yi", 0)
    industry = data_package.get("industry", "")
    flags = core.get("caution_flags", [])
    gm = core.get("gross_margin_pct", 0)
    nm = core.get("net_margin_pct", 0)
    debt = core.get("interest_bearing_debt_yi", 0)
    cash = core.get("cash_yi", 0)

    msg = f"""# 路由任务: {stock}({code})

## 行业分类
{industry}

## 核心财务数据
| 指标 | 数值 |
|------|------|
| 市值 | {mcap:.0f}亿 |
| TTM营收 | {rev:.1f}亿 |
| TTM净利润 | {np:.1f}亿 |
| ROIC | {roic:.1f}% |
| 毛利率 | {gm:.1f}% |
| 净利率 | {nm:.1f}% |
| PE(TTM) | {pe:.1f}x |
| PB | {pb:.1f}x |
| 净资产 | {equity:.0f}亿 |
| 总资产 | {assets:.0f}亿 |
| 有息负债 | {debt:.1f}亿 |
| 现金 | {cash:.1f}亿 |
| 经营现金流 | {ocf:.1f}亿 |
| 数据质量 | {core.get('data_quality_score', 10)}/10 |

## 异常标记
{json.dumps(flags, ensure_ascii=False) if flags else "无"}

## 事件背景 (Agent0 全部字段)
{event_data.get('raw_event_text', '')}

## 投资主题
{event_data.get('investment_theme', '')}

## 事件推演传导链
{event_data.get('event_deduction', '')}

## 空头审查/反方观点
{event_data.get('adversarial_thinking', '')}

## 响应等级: L{event_data.get('response_level','?')}
预研推理: {event_data.get('preliminary_reasoning','')}
知识补充: {event_data.get('knowledge_supplement','')}
行业研究: {event_data.get('industry_expert_research','')}

## Agent-0 Hint (仅供参考，必须独立判决)
模型类别hint: {agent0_hint}
置信度: {agent0_hint.get('hint_confidence', '未知')}
【重要: 此hint不决定最终模型。基于实际财务数据独立判决。】

{case_anchors}

请基于以上信息，按照三层路由框架独立判决最合适的估值模型。输出 action=evaluate 和完整的 routing_decision。
"""
    return msg


# ═══════════════════════════════════════
# Agent2 主类
# ═══════════════════════════════════════

class RouteJudge:
    """路由判官 — V5 Agent-2。"""

    def __init__(self, deepseek_key: str | None = None):
        self.api_key = deepseek_key or DEEPSEEK_API_KEY
        self._case_library: list[dict] | None = None
    def run(
        self,
        data_package: dict,
        event_data: dict | None = None,
        progress_cb: Callable[[int, str], None] | None = None,
    ) -> dict:
        """
        执行路由判决。

        data_package: Agent-1 DataForge 输出
        event_data: Coze Agent0 输入（含 event_text, investment_theme 等）
        """
        cb = progress_cb or (lambda s, n: None)
        event_data = event_data or {}
        stock_code = data_package.get("stock_code", "")
        stock_name = data_package.get("stock_name", "")

        # ── Step 1: V3 案例匹配 ──
        cb(1, "V3案例匹配")
        case_matches, case_anchors_text = self._step_case_match(data_package)
        anchor_reliability = case_loader.assess_anchor_reliability(case_matches)

        # ── Step 2: 三层路由 + 冲突仲裁 (LLM) ──
        cb(2, "LLM路由判决")
        routing = self._step_llm_route(
            data_package, case_anchors_text, event_data
        )

        # ── Step 3: 增量补取检查 ──
        cb(3, "增量补取检查")
        primary = routing.get("primary_model", "A")
        inc_fetch = _check_missing_fields(primary, data_package)

        cb(4, "路由完成")

        return {
            "routing_decision": routing,
            "case_matches_top3": [
                {"case_code": c["stock_code"], "score": s,
                 "key_anchor": f"ROIC改善+{c.get('roic_improvement', '?')}ppt, PE扩张{c.get('pe_expansion', '?')}x"}
                for c, s in case_matches[:3]
            ],
            "case_matches_all": [
                {"case_code": c["stock_code"], "score": s} for c, s in case_matches[:8]
            ],
            "case_anchors_text": case_anchors_text,
            "anchor_reliability": anchor_reliability,
            "incremental_fetch_request": inc_fetch,
            "hint_rejection_note": routing.get("hint_rejection_note", ""),
            "reverse_dcf_applicability": "适用" if primary in ("A", "C", "I") else "不适用",
        }

    # ── Step 1: 案例匹配 ──

    def _step_case_match(self, data_package: dict) -> tuple[list, str]:
        """7规则案例匹配 + 构建锚点文本。"""
        core = data_package.get("packages", {}).get("core", {}).get("fields", {})

        # 构造 agent1_output 兼容格式供 case_loader
        a1_sim = {
            "clean_financials": {
                "roic_pct": core.get("roic_pct", 0),
                "market_cap_yi": core.get("market_cap_yi", 0),
                "industry": data_package.get("industry", ""),
                "pe_ttm": core.get("pe_ttm", 0),
            },
        }

        cases = case_loader.load_cases()
        matches = case_loader.find_similar(a1_sim, top_n=8, cases=cases)

        if not matches:
            return [], ""

        # 使用升级后的丰富锚点构建器
        anchors_text = case_loader.build_rich_anchors(matches, top_n=5)

        return matches, anchors_text

    # ── Step 3+4: LLM 路由判决 ──

    def _step_llm_route(
        self, data_package: dict,
        case_anchors: str, event_data: dict,
    ) -> dict:
        """调用 DeepSeek LLM 做三层路由判决。"""
        pr = data_package.get("pre_routing_result", {})
        agent0_hint = {
            "model_category_hint": pr.get("model_category_hint", []),
            "hint_confidence": pr.get("hint_confidence", ""),
        }

        user_msg = _build_routing_user_message(
            data_package, case_anchors, agent0_hint, event_data,
        )

        # LLM 调用（失败时自动重试一次）
        result = _call_deepseek(ROUTE_JUDGE_SYSTEM_PROMPT, user_msg, max_tokens=30720)

        if "_parse_error" in result:
            result = _call_deepseek(ROUTE_JUDGE_SYSTEM_PROMPT, user_msg, max_tokens=30720)

        if "_parse_error" in result:
            return self._fallback_routing(data_package)

        routing = result.get("routing_decision", result)
        if not routing or not routing.get("primary_model"):
            return self._fallback_routing(data_package)

        return routing

    def _fallback_routing(self, data_package: dict) -> dict:
        """纯代码 fallback 路由（DeepSeek 不可用时）。

        规则优先级: 行业特殊 > 周期底部 > 亏损/微利 > 资产/ROE > 常规盈利
        """
        core = data_package.get("packages", {}).get("core", {}).get("fields", {})
        roic = core.get("roic_pct", 0)
        np = core.get("net_profit_ttm_yi", 0)
        rev = core.get("revenue_ttm_yi", 0)
        pe = core.get("pe_ttm", 0)
        pb = core.get("pb", 0)
        gm = core.get("gross_margin_pct", 0)
        equity = core.get("total_equity_yi", 0)
        debt = core.get("interest_bearing_debt_yi", 0)
        cash = core.get("cash_yi", 0)
        industry = data_package.get("industry", "")

        primary = "A"  # default
        reason = ""

        # ── R1: 行业特殊规则 ──
        cyclical_industries = any(kw in industry for kw in
            ["化工", "化学", "钢铁", "有色", "金属", "航运", "养殖", "造纸", "煤炭", "石油", "石化"])
        biotech = any(kw in industry for kw in ["药", "生物", "医疗"])

        if biotech:
            primary = "F" if np <= 0 else "A"
            reason = f"医药/biotech, {'亏损→rNPV' if np <= 0 else '盈利→DCF'}"
        elif any(kw in industry for kw in ["银行", "保险"]):
            primary = "D"
            reason = "金融→PB-ROE"
        elif any(kw in industry for kw in ["地产", "REIT"]):
            primary = "H"
            reason = "地产→NAV"

        # ── R2: 周期底部检测 ──
        elif pe > 80 and 0 < pb < 3 and cyclical_industries:
            primary = "E" if roic > 0 else "I"
            reason = f"PE={pe:.0f}x+PB={pb:.1f}x+周期行业→{'EV/EBITDA' if roic > 0 else '盈利正常化'}"

        # ── R3: 亏损/微利 ──
        elif np <= 0:
            ps = core.get("ps_ttm", 0) or 0
            if ps > 10:
                # 高PS亏损 → 市场用收入定价，走B
                primary = "B"
                reason = f"亏损+PS={ps:.0f}x>10→PS+TAM(市场用收入定价)"
            elif ps < 5:
                # 低PS亏损 → 可能接近底部，C可用
                primary = "C"
                reason = f"亏损+PS={ps:.0f}x<5→拐点DCF"
            elif rev > 10:
                primary = "B"
                reason = f"亏损+营收{rev:.0f}亿→PS+TAM"
            elif biotech:
                primary = "F"
                reason = "亏损biotech→rNPV"
            else:
                primary = "B"
                reason = "亏损→PS+TAM"

        # ── R4: 高增长 ──
        elif roic > 15 and pe > 40:
            primary = "G"
            reason = f"ROIC={roic:.1f}%+PE={pe:.0f}x→PEG增长锚定"

        # ── R5: 资产/ROE 驱动 ──
        elif 0 < pb < 1.5 and roic < 8 and equity > 0:
            primary = "D"
            reason = f"PB={pb:.1f}x+ROIC={roic:.1f}%→PB-ROE"

        # ── R6: 隐蔽资产 ──
        elif cash > equity * 0.5 and pb < 2 and roic < 8:
            primary = "H"
            reason = f"现金{cash:.0f}亿/净资{equity:.0f}亿+低PB→NAV"

        # ── R7: 常规盈利 ──
        elif roic > 8:
            primary = "A"
            reason = f"ROIC={roic:.1f}%>8%→ROIC-RR DCF"
        elif roic > 0:
            primary = "C"
            reason = f"ROIC={roic:.1f}%>0%→DCF+拐点"

        # ── R8: 兜底 ──
        else:
            primary = "B"
            reason = "ROIC≤0→PS+TAM"

        # 模型类别
        earnings_models = {"A", "C", "G", "I"}
        revenue_models = {"B"}
        asset_models = {"D", "H", "E", "F", "J"}

        return {
            "primary_model": primary,
            "model_category": (
                "Earnings Multiples" if primary in earnings_models
                else "Revenue Multiples" if primary in revenue_models
                else "Asset/Resource"
            ),
            "validation_models": [],
            "routing_reason": f"Fallback规则路由(LLM不可用)。ROIC={roic:.1f}%, 净利={np:.1f}亿",
            "hint_rejection_note": "Fallback路由，无hint参考",
            "model_migration_path": {},
        }


# ── 便捷函数 ──

def route_judge(data_package: dict, event_data: dict | None = None) -> dict:
    """便捷入口：运行路由判决。"""
    judge = RouteJudge()
    return judge.run(data_package, event_data)
