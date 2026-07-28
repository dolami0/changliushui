"""N6: 总装+去重+交叉验证

从 coze_workflow/n6_assembler.json 移植。
LLM 调用: DeepSeek Flash, max_tokens=8192
"""

import json
import re

from .field_runner import call_deepseek, CURRENT_DATE
from .field_runner import FIELD_CN


ASSEMBLER_SYSTEM = """你是总编辑。你的任务是把5份顺序生成的语料做去重和交叉验证，输出一条完整的万业谱记录。

## 5份语料的生成顺序

N1(投资主题) → N2(产业链) → N3(逆向推演) → N4(催化日历) → N5(事件推演)

后序报告基于前序写成，已经做了部分交叉引用。你的任务是找出仍然存在的重复和矛盾。

## 去重规则

1. 扫描5份语料，找到内容重叠段落
2. N2(产业链)中引用了N1(投资主题)内容的 → 保留在N1, N2中删重
3. N3(逆向)中的风险判断与N5(推演)中的破裂场景重叠 → 保留在N3, N5中删重
4. 识别 knowledge_supplement — 搜索中获取但未被5份语料覆盖的补充信息

## 交叉验证规则

1. N1投资主题的判断 vs N2产业链的判断 → 是否自洽？
2. N2卡点检查 vs N3失效测试 → 逻辑是否一致？
3. N5推演路径 vs N1核心假设 → 是否存在逻辑矛盾？
4. 不一致处标注"⚠️存在分歧: [字段A]说...而[字段B]说..."，不做调和

## 输出格式

务必输出纯JSON（不要markdown代码块包裹）:

{
  "industry_expert_research": "去重后的产业链研究报告",
  "adversarial_thinking": "去重后的逆向推演",
  "investment_theme": "去重后的投资主题",
  "future": "去重后的催化日历",
  "event_deduction": "去重后的事件推演",
  "knowledge_supplement": "5份语料均未覆盖的补充信息。如无则写'无额外补充'",
  "cross_validation": {
    "consistencies": ["一致点1: N1和N2独立得出..."],
    "divergences": ["分歧点1: N2认为...但N3认为..."]
  }
}

规则:
- 去重: 保留在最相关的字段，从次要字段删除
- 不改变事实内容，只删除重复段落
- knowledge_supplement不能为空字符串
- 如果N3缺少红蓝对抗的存活强度标注，在adversarial_thinking末尾追加"⚠️ 红蓝对抗不完整\""""


def assemble(
    stock_name: str,
    stock_code: str,
    event_date: str = "",
    event_source: str = "",
    raw_text: str = "",
    step_one: str = "",
    investment_theme: str = "",
    industry_expert_research: str = "",
    adversarial_thinking: str = "",
    future: str = "",
    event_deduction: str = "",
    verbose: bool = True,
) -> dict:
    """N6: 总装 5 份字段报告，去重 + 交叉验证。

    Returns:
        {
            "industry_expert_research": str,
            "adversarial_thinking": str,
            "investment_theme": str,
            "future": str,
            "event_deduction": str,
            "knowledge_supplement": str,
            "cross_validation": {...},
        }
    """
    if verbose:
        print(f"\n[N6 总装] 去重+交叉验证...")

    user_msg = f"""[当前日期: {CURRENT_DATE}]

请去重+交叉验证以下5份语料。这些报告是按 N1→N2→N3→N4→N5 顺序生成的。

## 基础信息
股票: {stock_name}（{stock_code}）
事件日期: {event_date}
事件来源: {event_source}

## N1 投资主题
{investment_theme}

## N2 产业链研究
{industry_expert_research}

## N3 逆向推演
{adversarial_thinking}

## N4 催化日历
{future}

## N5 事件推演
{event_deduction}

## 补充信息
原始事件: {raw_text[:2000]}
预研分析: {step_one[:1000]}"""

    content = call_deepseek(
        system=ASSEMBLER_SYSTEM,
        user=user_msg,
        max_tokens=8192,
    )

    # 解析 JSON
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                if verbose:
                    print(f"[N6] JSON解析失败，使用原始报告")
                return _fallback(
                    investment_theme, industry_expert_research,
                    adversarial_thinking, future, event_deduction,
                )
        else:
            if verbose:
                print(f"[N6] JSON解析失败，使用原始报告")
            return _fallback(
                investment_theme, industry_expert_research,
                adversarial_thinking, future, event_deduction,
            )

    if verbose:
        n_div = len(result.get("cross_validation", {}).get("divergences", []))
        n_con = len(result.get("cross_validation", {}).get("consistencies", []))
        print(f"[N6] 完成: {n_con}一致 {n_div}分歧")

    return result


def _fallback(theme, ier, adv, fut, ded):
    """JSON 解析失败时的降级：直接返回原始报告。"""
    return {
        "investment_theme": theme,
        "industry_expert_research": ier,
        "adversarial_thinking": adv,
        "future": fut,
        "event_deduction": ded,
        "knowledge_supplement": "[N6解析失败] 使用原始报告",
        "cross_validation": {"consistencies": [], "divergences": []},
    }
