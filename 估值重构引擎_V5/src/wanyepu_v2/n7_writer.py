"""N7: 写入万业谱 Coze DB + 标记天机卷

从 coze_workflow/n7_writer.py 移植，修正:
  - mark_tianji_processed 中的 DB ID 硬编码正确
"""

import requests
from datetime import datetime

from .config import COZE_SAT_TOKEN, COZE_BASE, DB_WANYEPU, DB_TIANJIJUAN


def write_wanyepu(
    stock_name: str,
    stock_code: str,
    event_date: str = "",
    event_source: str = "天机",
    raw_event_text: str = "",
    response_level: str = "",
    preliminary_reasoning: str = "",
    industry_expert_research: str = "",
    adversarial_thinking: str = "",
    investment_theme: str = "",
    future: str = "",
    event_deduction: str = "",
    knowledge_supplement: str = "",
    uuid: str = "",
    source_record_id: str = "",
    verbose: bool = True,
) -> dict:
    """写入万业谱 Coze DB。

    Returns:
        {"status": "ok"|"error", "coze_response": dict, "total_chars": int}
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    record = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "event_date": event_date,
        "event_source": event_source,
        "raw_event_text": raw_event_text,
        "response_level": response_level,
        "preliminary_reasoning": preliminary_reasoning,
        "industry_expert_research": industry_expert_research,
        "adversarial_thinking": adversarial_thinking,
        "investment_theme": investment_theme,
        "future": future,
        "event_deduction": event_deduction,
        "knowledge_supplement": knowledge_supplement,
        # is_complete=false: 预研语料写入完成，但估值引擎尚未消费。
        # 估值管线 query_incomplete_records 只查 is_complete=false 的记录，
        # 处理完后由估值引擎标记为 true。
        "is_complete": "false",
        "created_at": now,
    }

    total_chars = sum(
        len(str(v)) for k, v in record.items()
        if k not in ["stock_code", "stock_name", "event_date", "event_source",
                     "response_level", "uuid", "is_complete", "created_at"]
    )

    if verbose:
        print(f"[N7] 写入万业谱: {stock_name}({stock_code}) {total_chars}c")

    try:
        # Coze POST /records 创建格式：{"insert_rows": [{...}]}
        r = requests.post(
            f"{COZE_BASE}/{DB_WANYEPU}/records",
            headers={
                "Authorization": f"Bearer {COZE_SAT_TOKEN}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"insert_rows": [record]},
            timeout=30,
        )
        result = r.json()
        ok = result.get("code") == 0
        if verbose:
            print(f"[N7] 万业谱: {'OK' if ok else 'FAIL'} code={result.get('code')} msg={result.get('msg', '')}")
        return {"status": "ok" if ok else "error", "coze_response": result, "total_chars": total_chars}
    except Exception as e:
        if verbose:
            print(f"[N7] 万业谱写入失败: {e}")
        return {"status": "error", "error": str(e), "total_chars": total_chars}


def _update_coze(db_id: str, record_id: str, fields: dict) -> bool:
    """更新 Coze DB 记录。Coze 要求 update_fields + filter 格式。"""
    try:
        update_fields = [
            {"field_name": k, "value": str(v)}
            for k, v in fields.items()
        ]
        r = requests.put(
            f"{COZE_BASE}/{db_id}/records",
            headers={
                "Authorization": f"Bearer {COZE_SAT_TOKEN}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "update_fields": update_fields,
                "filter": {
                    "logic": "and",
                    "conditions": [
                        {"left": "id", "operation": "equal", "right": record_id},
                    ],
                },
            },
            timeout=30,
        )
        result = r.json() if r.text else {}
        return result.get("code") == 0
    except Exception:
        return False


def mark_tianji_processed(record_id: str, verbose: bool = True) -> bool:
    """标记天机卷记录为已处理。"""
    now = datetime.now().isoformat()
    ok = _update_coze(DB_TIANJIJUAN, record_id, {
        "is_analyzed": "true",
        "is_analyzing": "false",
        "analysis_time": now,
    })
    if verbose:
        print(f"[N7] 天机卷标记: {'OK' if ok else 'FAIL'}")
    return ok


def unlock_tianji(record_id: str) -> None:
    """解锁天机卷记录（处理失败时调用）。"""
    _update_coze(DB_TIANJIJUAN, record_id, {"is_analyzing": "false"})
