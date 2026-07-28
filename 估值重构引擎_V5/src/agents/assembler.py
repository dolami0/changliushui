"""第3层: 总装 — 去重、knowledge_supplement、透传合并、Coze 写入"""

import json
import time
import requests
from typing import Optional
from datetime import datetime

from urllib.parse import quote

COZE_TOKEN = "sat_UxIpTimxUFwh0BGedY1yxK7YJbqrqryebdRVyt8AjducYxsH8cFkkso6Orh2RTGc"
COZE_BASE = "https://api.coze.cn/v1/databases"
DB_WANYEPU = "7639784337973477386"


def assemble_and_write(
    stock_name: str,
    stock_code: str,
    source_record_id: str,
    tianji_data: dict,
    preliminary_reasoning: str,
    industry_expert_research: str,
    adversarial_thinking: str,
    investment_theme: str,
    future: str,
    event_deduction: str,
    verbose: bool = True,
) -> dict:
    """总装6语料字段 + 透传字段，写入万业谱。

    Args:
        tianji_data: 天机卷原始记录（用于透传字段）
        其他: 各语料字段内容

    Returns:
        Coze API 写入结果
    """
    # ── 透传字段 ──
    bstudio_time = tianji_data.get("bstudio_create_time", "")
    event_date = bstudio_time[:10] if bstudio_time else ""
    uuid = tianji_data.get("uuid", "")
    news_content = tianji_data.get("news_content", "")
    response_level = tianji_data.get("level", "")
    mode = tianji_data.get("mode", "")

    # 去掉 HTML 标签
    import re
    raw_event_text = re.sub(r"<[^>]+>", "", news_content)
    raw_event_text = re.sub(r"&[^;]+;", " ", raw_event_text)
    raw_event_text = re.sub(r"\s+", " ", raw_event_text).strip()

    # event_source 映射
    event_source = "天机" if mode == "个股模式" else mode

    # ── knowledge_supplement: 收集未被覆盖的搜索数据 ──
    # (简化版: 标记为占位，后续可增强为真正的内容去重分析)
    knowledge_supplement = (
        "[自动生成] 本文档为搜索过程中获取的补充数据。"
        "主要字段已在前5份语料中覆盖。如有未覆盖的关键数据，请手动补充。"
    )

    # ── 构建 Coze 写入 payload ──
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    record = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "event_date": event_date,
        "event_source": event_source,
        "raw_event_text": raw_event_text[:10000],
        "response_level": response_level,
        "preliminary_reasoning": preliminary_reasoning[:15000],
        "industry_expert_research": industry_expert_research[:15000],
        "adversarial_thinking": adversarial_thinking[:15000],
        "investment_theme": investment_theme[:15000],
        "future": future[:10000],
        "event_deduction": event_deduction[:10000],
        "knowledge_supplement": knowledge_supplement[:10000],
        "uuid": uuid,
        "source_record_id": source_record_id,
        "is_complete": "false",
        "created_at": now,
    }

    if verbose:
        total_chars = sum(
            len(str(v)) for k, v in record.items()
            if k not in ["stock_code", "stock_name", "event_date", "event_source",
                         "response_level", "uuid", "source_record_id", "is_complete", "created_at"]
        )
        print(f"[Assembler] 写入记录: {stock_name}({stock_code})")
        print(f"[Assembler] 语料总字符: {total_chars}c")

    # ── 写入 Coze ──
    try:
        r = requests.post(
            f"{COZE_BASE}/{DB_WANYEPU}/records",
            headers={
                "Authorization": f"Bearer {COZE_TOKEN}",
                "Content-Type": "application/json",
            },
            json=record,
            timeout=30,
        )
        result = r.json()
        if verbose:
            print(f"[Assembler] 写入结果: {result.get('code', '?')} {result.get('msg', '')}")

        return {"status": "ok", "coze_response": result, "total_chars": total_chars}

    except Exception as e:
        return {"status": "error", "error": str(e)}


def mark_tianji_processed(record_id: str, verbose: bool = True) -> bool:
    """标记天机卷记录为已处理。

    Args:
        record_id: 天机卷记录 ID
        verbose: 是否打印日志

    Returns:
        是否成功
    """
    try:
        r = requests.post(
            f"{COZE_BASE}/DB_WANYEPU/records/{record_id}",
            headers={
                "Authorization": f"Bearer {COZE_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "is_analyzed": "true",
                "is_analyzing": "false",
                "analysis_time": datetime.now().isoformat(),
            },
            timeout=30,
        )

        if verbose:
            result = r.json()
            print(f"[天机卷标记] {record_id}: {result.get('code', '?')}")

        return r.status_code == 200

    except Exception as e:
        if verbose:
            print(f"[天机卷标记] 失败: {e}")
        return False
