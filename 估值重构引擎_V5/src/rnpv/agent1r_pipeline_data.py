"""
Agent-1r 管线数据组装 (PipelineDataAssembler) — rNPV 管线

从 Coze 预研文本和已用数据源中提取创新药管线相关数据，
使用火山引擎知识问答搜索补充管线结构化信息。

输出结构化管线数据包供 Agent-2r 消费。

原则:
  - 不做新 API 调用——所有财务数据来自已有 Agent-1
  - 管线信息主源: Coze 预研 + Volc 知识搜索
  - 搜索 query 用模板构造，不依赖 LLM
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_config import VOLC_AGENT_KEY
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
# 管线关键词提取 (规则引擎，不依赖 LLM)
# ═══════════════════════════════════════

# 中文创新药管线常见模式
DRUG_PATTERNS = [
    # 管线编码 (优先级最高): BGB-11417, RC48, DZD8586
    r'([A-Z]{2,4}[-_]\d{2,6}[A-Za-z]?)',
    # 中文药品名 (≥4字): 泽布替尼, 替雷利珠单抗, 维迪西妥单抗, 欧司珀利单抗
    r'([一-鿿]{4,8}(?:替尼|利珠|西妥|珠单抗|非尼|帕尼|妥珠|西普|西尤|珠单|洛尔|替雷|帕他|鲁胺|司他|莫德|拉宁|西林|康唑|瑞克|利珠单抗|司珀利|雷利珠|迪西妥))',
    # 靶点+药物后缀 (仅当≥6字符): HER2单抗, PD-L1抑制剂
    r'([A-Za-z0-9\-/]{6,})\s*(?:单抗|双抗|ADC|抑制剂|激动剂|拮抗剂|降解剂|融合蛋白|CAR-T)',
]

# 虚假靶点/基因名过滤 (不是药品名)
DRUG_BLACKLIST = {
    'BTK', 'BCL-2', 'BCL2', 'PD-1', 'PD1', 'PD-L1', 'PDL1', 'HER2', 'HER-2',
    'EGFR', 'TIGIT', 'CDK4', 'CDK6', 'CDK4/6', 'PI3K', 'AKT', 'MTOR', 'mTOR',
    'KRAS', 'BRAF', 'MEK', 'ERK', 'JAK', 'STAT', 'VEGF', 'VEGFR',
    'CTLA-4', 'CTLA4', 'OX40', '4-1BB', 'GPC3', 'CEA', 'B7-H4', 'PRMT5',
    'CLDN18.2', 'TROP2', 'NECTIN4', 'FRalpha', 'c-MET', 'RET', 'FGFR',
    'ALK', 'ROS1', 'NTRK', 'FLT3', 'IDH1', 'IDH2', 'PARP',
}

# 已获批/商业化产品关键词
COMMERCIAL_PATTERNS = [
    r'(?:已获批|已上市|商业化|销售额|营收|年收入|销售\d+亿)',
    r'(?:获批.*?适应症|已在中国.*?获批|FDA.*?批准)',
]

# 临床阶段关键词
PHASE_PATTERNS = {
    "Ph1": [r'Ph(?:ase)?\s*1', r'I期', r'一期', r'剂量递增', r'剂量爬坡', r'首次人体'],
    "Ph2": [r'Ph(?:ase)?\s*2', r'II期', r'二期', r'概念验证', r'队列扩展'],
    "Ph3": [r'Ph(?:ase)?\s*3', r'III期', r'三期', r'关键性临床', r'注册性临床', r'确证性临床'],
    "NDA": [r'NDA', r'BLA', r'上市申请', r'新药上市', r'递交上市', r'已受理'],
    "Approved": [r'已获批', r'已上市', r'销售中', r'商业化'],
}


def _extract_drug_names(text: str) -> list[str]:
    """从文本中提取创新药管线名称。"""
    found = []
    for pattern in DRUG_PATTERNS:
        matches = re.findall(pattern, text)
        for m in matches:
            m = m.strip().strip("-").strip("_")
            if len(m) >= 2 and m not in found:
                # 过滤假阳性: 靶点/基因名、非药名词
                if m.upper() in DRUG_BLACKLIST:
                    continue
                if m.lower() in ("ai", "mlcc", "led", "cpo", "gpu", "fpga", "mems", "cmos"):
                    continue
                found.append(m)
    return found[:8]  # 限制数量


def _extract_commercial_products(text: str) -> list[str]:
    """识别已商业化的产品。"""
    # 简单策略：在商业化关键词附近的管线名称
    return []


def _detect_clinical_phase(drug_name: str, text: str) -> str:
    """检测单个管线药物的最高临床阶段。"""
    # 找到药物名附近的文本
    idx = text.find(drug_name)
    if idx < 0:
        return "Unknown"
    context = text[max(0, idx - 200):idx + 500]

    # 按优先级从高到低检查
    for phase_name in ["Approved", "NDA", "Ph3", "Ph2", "Ph1"]:
        for pattern in PHASE_PATTERNS[phase_name]:
            if re.search(pattern, context):
                return phase_name
    return "Preclinical"


# ═══════════════════════════════════════
# Agent-1r 主类
# ═══════════════════════════════════════

class PipelineDataAssembler:
    """管线数据组装器 — rNPV Agent-1r。"""

    def __init__(self):
        self.fetcher = DataFetcher()
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
        # ── Step 1: 从 Coze 预研中提取管线信息 ──
        pre_text = (
            event_data.get("investment_theme", "") + " " +
            event_data.get("raw_event_text", "") + " " +
            event_data.get("knowledge_supplement", "") + " " +
            event_data.get("preliminary_reasoning", "")
        )

        drug_names = _extract_drug_names(pre_text)
        print(f"  [Agent-1r] 提取到管线药物: {drug_names}")

        # ── Step 2: Volc 知识问答搜索 ──
        search_results = self._search_pipeline(stock_name, stock_code, drug_names, pre_text)

        # ── Step 3: 提取财务数据 (复用 Agent-1) ──
        core_fields = {}
        if agent1_standard:
            core_fields = agent1_standard.get("packages", {}).get("core", {}).get("fields", {})

        cash = core_fields.get("cash_yi", 0)
        debt = core_fields.get("interest_bearing_debt_yi", 0)
        mcap = core_fields.get("market_cap_yi", 0)
        revenue = core_fields.get("revenue_ttm_yi", 0)
        np_val = core_fields.get("net_profit_ttm_yi", 0)

        # 成熟产品数据
        mature_products = []
        if revenue > 0:
            mature_products.append({
                "name": "已上市产品组合",
                "revenue_ttm_yi": round(revenue, 1),
                "profit_ttm_yi": round(np_val, 1),
                "is_profitable": np_val > 0,
                "valuation_hint": "PE" if np_val > 0 else "PS",
                "note": "来自合并报表,未做分产品拆分"
            })

        # ── Step 4: 组装输出 ──
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
            "extracted_from_pre_research": {
                "drug_count": len(drug_names),
                "drug_names": drug_names,
            },
            "volc_search_results": search_results,
            "_data_sources": {
                "financials": "Agent-1 (standard pipeline)",
                "pipeline_info": "Coze Agent0 pre-research + Volcengine search",
            },
        }

    # ── Volc 搜索 ──

    def _search_pipeline(
        self, stock_name: str, stock_code: str,
        drug_names: list[str], pre_text: str,
    ) -> dict[str, str]:
        """执行 Volc 知识问答搜索，返回每轮的搜索结果。"""
        results = {}

        # 第一轮：管线全景
        if drug_names:
            drugs_str = " ".join(drug_names[:4])
            query1 = f"{stock_name} {stock_code} 创新药管线 {drugs_str} 临床阶段 峰值销售预估 竞争格局 获批时间表"
        else:
            query1 = f"{stock_name} {stock_code} 在研创新药管线 临床阶段 峰值销售 商业化进展"

        cache_key = f"overview_{stock_code}"
        if cache_key not in self._volc_cache:
            print(f"  [Agent-1r] Volc Query 1: {query1[:120]}...")
            self._volc_cache[cache_key] = _call_volc(query1)
            time.sleep(0.5)
        results["pipeline_overview"] = self._volc_cache[cache_key]

        # 第二轮：核心管线深度（如果有 > 3 个药，选前 3 个）
        if len(drug_names) > 1:
            for drug in drug_names[:3]:
                dk = f"drug_{drug}_{stock_code}"
                if dk not in self._volc_cache:
                    query2 = f"{stock_name} {stock_code} {drug} 临床进展 Ph3数据 峰值销售预估 竞争品种 差异化优势"
                    print(f"  [Agent-1r] Volc Query ({drug}): {query2[:120]}...")
                    self._volc_cache[dk] = _call_volc(query2)
                    time.sleep(0.5)
                results[f"drug_detail_{drug}"] = self._volc_cache[dk]

        return results


# ── 便捷函数 ──

def assemble_pipeline_data(
    stock_code: str,
    stock_name: str,
    event_data: dict,
    agent1_standard: dict | None = None,
) -> dict:
    """便捷入口：组装管线数据。"""
    assembler = PipelineDataAssembler()
    return assembler.run(stock_code, stock_name, event_data, agent1_standard)
