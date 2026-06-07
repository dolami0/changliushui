"""
V6 估值管线 — 共享工具模块。

提取 Agent-2/Agent-3 中重复的逻辑，避免修改时两处同步。
"""

import json
import re
from typing import Any

import requests

from env_config import DEEPSEEK_API_KEY

DEEPSEEK_API = "https://api.deepseek.com/chat/completions"


# ═══════════════════════════════════════
# JSON 解析（Agent-2/3 共用）
# ═══════════════════════════════════════

def parse_json(text: str) -> dict:
    """从 LLM 回复中提取 JSON（增强容错）。

    处理: markdown代码块、前置/后置自然语言、嵌套括号。
    """
    text = text.strip()

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
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        e = i
                        break
            if e > s:
                text = text[s:e + 1]

    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {"_parse_error": f"JSON顶层非object(type={type(parsed).__name__})", "_raw": text[:500]}
        return parsed
    except json.JSONDecodeError:
        s = text.find("{")
        e = text.rfind("}")
        if s >= 0 and e > s:
            try:
                parsed2 = json.loads(text[s:e + 1])
                if not isinstance(parsed2, dict):
                    return {"_parse_error": f"JSON非object(type={type(parsed2).__name__})", "_raw": text[:500]}
                return parsed2
            except json.JSONDecodeError:
                pass
        return {"_parse_error": "JSON解析失败", "_raw": text[:500]}


# ═══════════════════════════════════════
# DeepSeek LLM 调用（Agent-2a/2b/3 共用）
# ═══════════════════════════════════════

def call_deepseek(
    system: str,
    user_message: str,
    max_tokens: int = 40960,
    temperature: float = 0,
    api_key: str | None = None,
    model: str = "deepseek-v4-pro",
    print_usage: bool = True,
) -> dict:
    """调用 DeepSeek API，返回解析后的 JSON dict。"""
    key = api_key or DEEPSEEK_API_KEY
    resp = requests.post(
        DEEPSEEK_API,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
        },
        timeout=600,
    )
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        if print_usage and usage:
            print(
                f"  [LLM tokens] prompt={usage.get('prompt_tokens')} "
                f"completion={usage.get('completion_tokens')}",
                flush=True,
            )
        return parse_json(content)
    except Exception as e:
        print(f"  [LLM] response parse error: {e}", flush=True)
        return {"_parse_error": str(e)[:200]}


# ═══════════════════════════════════════
# 格式化工具
# ═══════════════════════════════════════

def fmt_pct(val: Any) -> str:
    """安全格式化百分比。"""
    if val is None:
        return '?'
    try:
        f = float(val)
        return f'{f:+.1f}%'
    except (ValueError, TypeError):
        return '?'


def build_forward_signal_panel(core: dict) -> str:
    """
    构建前瞻信号面板文本（注入 LLM 用户消息）。

    从 Agent-3 迁移至 Agent-2a —— 信号审核是叙事诊断的一部分，
    Agent-3 信任 2a 的审核结论，不做重复验证。

    重点展示异常信号（vs 历史分布的 sigma 偏离），而非罗列数字。
    """
    fw = core.get('_forward_looking', {})
    if not fw or fw.get('status') == 'unavailable':
        return """## 前瞻信号面板

状态: 不可用（Tushare 数据源未配置或不可达）
所有前瞻判断依赖 TTM 快照和定性素材，缺少季度趋势和业绩预告信号。"""

    cats = fw.get('categories', {})
    anomalies = fw.get('anomalies', [])
    text_summary = fw.get('text_summary', '')

    lines = [f"""## 前瞻信号面板（代码预计算 + 历史分布异常检测，不可编造）

数据状态: {fw.get('status','?')} | 来源: {', '.join(fw.get('sources_available',[]))}
缺失: {', '.join(fw.get('sources_missing',[])) or '无'}
⚠️ 注意: 本面板全部基于历史财报数据，与 Agent-0 实时信号存在时间差。偏差 = 事件窗口内已发生的基本面变化，不改变财务+故事的估值框架。"""]

    # ── 异常信号（最高优先级） ──
    if anomalies:
        lines.append('\n### ⚡ 定量异常信号（vs 历史8期均值±标准差）')
        for a in anomalies:
            anomaly_info = a.get('anomaly', {})
            if anomaly_info:
                sigma = anomaly_info.get('sigma', 0)
                direction = '↑' if anomaly_info.get('direction') == 'up' else '↓'
                tag = '🔴' if anomaly_info.get('level') == 'extreme' else '🟡'
                lines.append(
                    f"\n{tag} **{a['label']}**: {a.get('value','?')}{a.get('unit','')} "
                    f"({direction}{abs(sigma)}σ, 均值={anomaly_info.get('mean','?')})"
                )
            else:
                lines.append(f"\n **{a['label']}**: {a.get('value','?')}")
            if a.get('interpretation'):
                lines.append(f"   → {a['interpretation']}")
            if a.get('story_check'):
                lines.append(f"   → 叙事交叉验证: {a['story_check']}")
        if text_summary:
            lines.append(f'\n> 异常信号汇总: {text_summary}')
    else:
        lines.append('\n### 定量异常检测: 未触发')

    # ── 盈利弹性（产品结构） ──
    earnings = cats.get('earnings_elasticity', {})
    products_data = earnings.get('products', {}) if earnings else {}
    if products_data and products_data.get('product_mix'):
        data_vintage = products_data.get('data_vintage', '?')
        mix = products_data['product_mix']
        kw = products_data.get('keyword_matches', {})
        gm_src = products_data.get('gm_source', 'actual')
        gm_cov = products_data.get('gm_coverage_pct', 100)
        company_gm = core.get('gross_margin_pct', 0)
        gm_note = ''
        if gm_src == 'blended':
            gm_note = f' ️ 分产品利润数据不可用(覆盖率{gm_cov}%)，所有毛利率使用合并毛利率{company_gm:.1f}%近似'
        elif gm_src == 'mixed':
            gm_note = f' ️ 部分产品利润数据缺失(覆盖率{gm_cov}%)，缺失项使用合并毛利率近似'
        lines.append(f'\n### 3. 盈利弹性 — 产品结构 (对比窗口: {data_vintage}){gm_note}')

        h2_avail = products_data.get('has_h1_data', False)
        for p in mix:
            gm_est = '[估算]' if p.get('gm_source') == 'blended' else ''
            gm_str = f'毛利率={p["gross_margin_pct"]:.1f}%{gm_est}' if p.get('gross_margin_pct') is not None else ''
            rev_chg = f' (同比{fmt_pct(p.get("revenue_yoy_pct"))})' if p.get('revenue_yoy_pct') is not None else ''
            share_chg = p.get('share_change_ppt')
            share_info = f' 占比={p["revenue_share_pct"]:.1f}%'
            if share_chg is not None:
                share_info += f' ({share_chg:+.1f}ppt)'
            kw_hints = kw.get(p['name'], [])
            kw_tag = f' [匹配: {",".join(kw_hints)}]' if kw_hints else ''
            h2_info = ''
            if h2_avail and p.get('h2_revenue') is not None:
                h2_rev = p['h2_revenue']
                h2_gm = p.get('h2_gross_margin_pct')
                h2_yoy = p.get('h2_revenue_yoy_pct')
                h2_parts = [f'H2收入={h2_rev:.2f}亿']
                if h2_gm is not None:
                    h2_parts.append(f'H2毛利率={h2_gm:.1f}%')
                if h2_yoy is not None:
                    h2_parts.append(f'H2同比{fmt_pct(h2_yoy)}')
                h2_info = ' | ' + ' '.join(h2_parts)
            lines.append(f'  - {p["name"]}: 收入={p["revenue"]:.2f}亿{rev_chg} {share_info} {gm_str}{kw_tag}{h2_info}')

        if products_data.get('interpretation'):
            lines.append(f'\n  > {products_data["interpretation"]}')
        if products_data.get('story_check'):
            lines.append(f'  > {products_data["story_check"]}')

    # 使用指南
    lines.append("""
---
### 如何使用前瞻信号
1. **异常信号 = 必须响应的硬约束**
2. **正常信号 = 旁证**
3. **缺失类别** → 用 TTM 快照和定性素材替代判断
4. **单位**: 所有金额单位为亿元人民币(亿)，比率单位为%
""")

    return '\n'.join(lines)
