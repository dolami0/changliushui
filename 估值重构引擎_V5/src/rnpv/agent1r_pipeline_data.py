"""
Agent-1r 管线数据组装 (PipelineDataAssembler) — rNPV 管线 V7

流程:
  1. Volc 通用搜索（不依赖药名）
  2. Flash 模型从 Coze预研 + Volc结果 合并提取结构化管线
  3. 可选：关键管线深度 Volc 搜索
  4. 组装财务数据（复用 Agent-1）

设计原则:
  - 提取用 Flash 模型（deepseek-chat），便宜快速
  - 推演用 Pro 模型（deepseek-v4-pro），推理深度
  - 先搜索后提取：LLM 能同时看到 Coze 预研和 Volc 搜索结果
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_config import VOLC_AGENT_KEY, DEEPSEEK_API_KEY
from data_fetcher import DataFetcher


# ═══════════════════════════════════════
# Volcengine 知识问答
# ═══════════════════════════════════════

VOLC_URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
VOLC_BOT_ID = "7640524154441156122"


def _call_volc(query: str, timeout: int = 120) -> str:
    """调用火山引擎知识问答。失败返回空字符串。"""
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
                return choices[0].get("message", {}).get("content", "")
        return ""
    except Exception:
        return ""


# ═══════════════════════════════════════
# Flash 模型管线提取
# ═══════════════════════════════════════

FLASH_MODEL = "deepseek-v4-flash"  # 便宜快速，仅做提取不做推理

PIPELINE_EXTRACTION_PROMPT = """你是创新药管线数据提取助手。从以下材料中提取 **目标公司自己的** 创新药管线结构化数据。

# 核心规则

1. **只提取目标公司自己的管线**。竞品/可比公司的药物是背景参考，不提取
2. **提取所有阶段的管线药物**：
   - 已上市/已获批的商业化产品（Approved）
   - 在研管线：NDA / Ph3 / Ph2 / Ph1 / Preclinical 各阶段
   - 药物代号（如 HSK31858、HSK39004 等格式）
   - 对外授权/合作开发的管线（如授权给其他公司的海外权益）
   - 早期合作项目（如与大型药企的靶点合作）
3. **区分已上市 vs 在研**：已获批/已商业化的 → Approved；在研的 → 对应临床阶段
4. **临床阶段取最高值**: Approved > NDA > Ph3 > Ph2 > Ph1 > Preclinical
5. **数据来源**：优先引用材料中明确提到的数值，缺失时填 null
6. **不要遗漏**：即使是材料中只提了一次的药物代号，只要确认是目标公司的，就应提取

# 输出格式

```json
{
  "drugs": [
    {
      "name": "药物通用名或代号",
      "target": "靶点/机制，无则null",
      "indication": "适应症，无则null",
      "clinical_phase": "Approved|NDA|Ph3|Ph2|Ph1|Preclinical",
      "phase_detail": "阶段补充说明，无则null",
      "peak_sales_hint": "材料中提到的峰值销售/市场空间，无则null",
      "is_key_catalyst": true
    }
  ],
  "mature_products_summary": "已上市产品的整体描述（<=100字）",
  "pipeline_overview": "管线的整体描述（<=100字）"
}
```

输出纯 JSON，不包含任何其他文字。"""

DEEPSEEK_API = "https://api.deepseek.com/v1/chat/completions"


def _call_flash_extraction(
    prompt_text: str,
    stock_name: str,
    api_key: str | None = None,
) -> dict:
    """调用 Flash 模型从文本中提取管线结构化数据。"""
    key = api_key or DEEPSEEK_API_KEY

    try:
        resp = requests.post(
            DEEPSEEK_API,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            json={
                "model": FLASH_MODEL,
                "messages": [
                    {"role": "system", "content": PIPELINE_EXTRACTION_PROMPT},
                    {"role": "user", "content": f"目标公司: {stock_name}\n\n材料:\n{prompt_text[:40000]}"},
                ],
                "max_tokens": 8192,
                "temperature": 0,
                "stream": False,
            },
            timeout=120,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        print(
            f"  [Agent-1r Flash] model={FLASH_MODEL} "
            f"prompt={usage.get('prompt_tokens')} "
            f"completion={usage.get('completion_tokens')}",
            flush=True,
        )

        # 解析 JSON（容错 markdown 代码块包裹）
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        return json.loads(content)
    except Exception as e:
        print(f"  [Agent-1r Flash] 提取失败: {e}", flush=True)
        return {"drugs": [], "_error": str(e)[:200]}


# ═══════════════════════════════════════
# Agent-1r 主类
# ═══════════════════════════════════════

class PipelineDataAssembler:
    """管线数据组装器 — rNPV Agent-1r (V7: Volc搜索 → Flash提取)。"""

    def __init__(self, deepseek_key: str | None = None):
        self.fetcher = DataFetcher()
        self.api_key = deepseek_key
        self._volc_cache: dict[str, str] = {}

    def run(
        self,
        stock_code: str,
        stock_name: str,
        event_data: dict,
        agent1_standard: dict | None = None,
    ) -> dict:
        """
        组装管线数据包。

        stock_code/stock_name: 标的
        event_data: Coze Agent0 预研字段
        agent1_standard: 标准 Agent-1 输出（复用财务数据）

        返回: 结构化管线数据包
        """
        # ── Step 1: Volc 通用搜索（不依赖药名）──
        print(f"  [Agent-1r] Volc 通用搜索...", flush=True)
        t0 = time.time()
        volc_results = self._search_pipeline_general(stock_name, stock_code)
        print(f"  [Agent-1r] Volc 完成 ({time.time()-t0:.1f}s)", flush=True)

        # ── Step 2: Flash 模型从 Coze预研 + Volc结果 合并提取 ──
        # 构建提取材料: Coze 预研文本 + Volc 搜索结果
        coze_text = "\n\n".join([
            f"=== 投资主题 ===\n{event_data.get('investment_theme', '')}",
            f"=== 事件原文 ===\n{event_data.get('raw_event_text', '')}",
            f"=== 知识补充 ===\n{event_data.get('knowledge_supplement', '')}",
            f"=== 产业研究 ===\n{event_data.get('industry_expert_research', '')}",
        ])
        volc_text = "\n\n".join(
            f"=== Volc: {k} ===\n{v}"
            for k, v in volc_results.items() if v
        )
        extraction_input = coze_text + "\n\n" + volc_text

        print(f"  [Agent-1r] Flash 提取管线...", flush=True)
        t0 = time.time()
        extracted = _call_flash_extraction(extraction_input, stock_name, self.api_key)
        drugs = extracted.get("drugs", [])
        print(f"  [Agent-1r] Flash 完成 ({time.time()-t0:.1f}s): {len(drugs)} 个管线药物", flush=True)
        for d in drugs:
            phase = d.get('clinical_phase') or '?'
            ind = (d.get('indication') or '?')[:50]
            print(f"    - {d.get('name','?')} [{phase}] {ind}", flush=True)

        # ── Step 3: 关键管线深度 Volc 搜索（可选，非必需）──
        key_drugs = [d for d in drugs if d.get("is_key_catalyst")][:3]
        if key_drugs:
            print(f"  [Agent-1r] 关键管线深度搜索 ({len(key_drugs)}个)...", flush=True)
            deep_results = self._search_pipeline_deep(stock_name, stock_code, key_drugs)
            for k, v in deep_results.items():
                if v:
                    volc_results[k] = v

        # ── Step 4: 提取财务数据 (复用 Agent-1) ──
        core_fields = {}
        if agent1_standard:
            core_fields = agent1_standard.get("packages", {}).get("core", {}).get("fields", {})

        cash = core_fields.get("cash_yi", 0)
        debt = core_fields.get("interest_bearing_debt_yi", 0)
        mcap = core_fields.get("market_cap_yi", 0)
        revenue = core_fields.get("revenue_ttm_yi", 0)
        np_val = core_fields.get("net_profit_ttm_yi", 0)

        mature_products = [{
            "name": "已上市产品组合",
            "revenue_ttm_yi": round(revenue, 1),
            "profit_ttm_yi": round(np_val, 1),
            "is_profitable": np_val > 0,
            "valuation_hint": "PE" if np_val > 0 else "PS",
            "note": "来自合并报表，未做分产品拆分",
        }] if revenue > 0 else []

        drug_names = [d.get("name", "") for d in drugs if d.get("name")]

        # ── Step 5: 组装输出 ──
        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "company_financials": {
                "market_cap_yi": round(mcap, 1),
                "cash_yi": round(cash, 1),
                "debt_yi": round(debt, 1),
                "net_cash_yi": round(cash - debt, 1),
                "revenue_ttm_yi": round(revenue, 1),
                "net_profit_ttm_yi": round(np_val, 1),
                "burn_rate_hint": f"TTM净利润{np_val:.1f}亿(负=烧钱)"
                    if np_val < 0 else f"TTM盈利{np_val:.1f}亿",
            },
            "mature_products": mature_products,
            "pipeline_drugs_hint": drug_names,
            "pipeline_drugs_structured": drugs,
            "extracted_from_pre_research": {
                "drug_count": len(drugs),
                "drug_names": drug_names,
                "extraction_method": "Flash LLM (Coze + Volc)",
            },
            "volc_search_results": volc_results,
            "_data_sources": {
                "financials": "Agent-1 (standard pipeline)",
                "pipeline_info": "Volcengine search → Flash LLM extraction",
            },
        }

    # ── Volc 搜索方法 ──

    def _search_pipeline_general(self, stock_name: str, stock_code: str) -> dict[str, str]:
        """Volc 通用搜索（不依赖药名）。"""
        results = {}
        cache_key = f"general_{stock_code}"

        if cache_key not in self._volc_cache:
            query = f"{stock_name} {stock_code} 创新药管线 在研药品 临床阶段 峰值销售预估 竞争格局 获批时间表"
            print(f"  [Agent-1r] Volc: {query[:100]}...", flush=True)
            self._volc_cache[cache_key] = _call_volc(query)
            time.sleep(0.5)
        results["pipeline_overview"] = self._volc_cache[cache_key]
        return results

    def _search_pipeline_deep(
        self, stock_name: str, stock_code: str,
        key_drugs: list[dict],
    ) -> dict[str, str]:
        """关键管线深度 Volc 搜索。"""
        results = {}
        for d in key_drugs:
            name = d.get("name", "")
            if not name:
                continue
            dk = f"deep_{name}_{stock_code}"
            if dk not in self._volc_cache:
                phase = d.get("clinical_phase") or ""
                indication = d.get("indication") or ""
                query = f"{stock_name} {stock_code} {name} {phase} {indication} 临床数据 峰值销售 竞争格局"
                print(f"  [Agent-1r] Volc深度({name}): {query[:100]}...", flush=True)
                self._volc_cache[dk] = _call_volc(query)
                time.sleep(0.5)
            results[f"drug_detail_{name}"] = self._volc_cache[dk]
        return results


# ── 便捷函数 ──

def assemble_pipeline_data(
    stock_code: str,
    stock_name: str,
    event_data: dict,
    agent1_standard: dict | None = None,
    deepseek_key: str | None = None,
) -> dict:
    """便捷入口：组装管线数据。"""
    assembler = PipelineDataAssembler(deepseek_key=deepseek_key)
    return assembler.run(stock_code, stock_name, event_data, agent1_standard)
