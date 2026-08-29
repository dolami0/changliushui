"""N9 [Code] 写入万业谱 + 标记天机卷
Coze Code节点 — Python 3

输入变量: final_record (JSON), stock_code, stock_name, source_id,
          event_date, event_source, raw_text, uuid, response_level, step_one
输出: 打印写入结果
"""

import json
import requests
from datetime import datetime

# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════

COZE_TOKEN = ""  # Coze 平台注入
COZE_BASE = "https://api.coze.cn/v1/databases"
DB_WANYEPU = "7639784337973477386"
DB_TIANJI = "7479116110479048754"

# ═══════════════════════════════════════════════
# 主逻辑
# ═══════════════════════════════════════════════

# 1. 解析去重后的记录
try:
    dedup = json.loads(final_record)
except json.JSONDecodeError:
    # LLM输出可能包裹在```json```中
    import re
    match = re.search(r'\{[\s\S]*\}', final_record)
    if match:
        dedup = json.loads(match.group())
    else:
        print(f"JSON解析失败: {final_record[:500]}")
        exit(1)

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 2. 构建万业谱写入 payload
record = {
    "stock_code": stock_code,
    "stock_name": stock_name,
    "event_date": event_date or "",
    "event_source": event_source or "天机",
    "raw_event_text": (raw_text or "")[:10000],
    "response_level": response_level or "",
    "preliminary_reasoning": (step_one or "")[:15000],
    "industry_expert_research": dedup.get("industry_expert_research", "")[:15000],
    "adversarial_thinking": dedup.get("adversarial_thinking", "")[:15000],
    "investment_theme": dedup.get("investment_theme", "")[:15000],
    "future": dedup.get("future", "")[:10000],
    "event_deduction": dedup.get("event_deduction", "")[:10000],
    "knowledge_supplement": dedup.get("knowledge_supplement", "")[:10000],
    "uuid": uuid or "",
    "source_record_id": source_id or "",
    "is_complete": "false",
    "created_at": now,
}

# 3. 写入万业谱
try:
    r1 = requests.post(
        f"{COZE_BASE}/{DB_WANYEPU}/records",
        headers={
            "Authorization": f"Bearer {COZE_TOKEN}",
            "Content-Type": "application/json",
        },
        json=record,
        timeout=30,
    )
    result1 = r1.json()
    print(f"万业谱写入: code={result1.get('code')} msg={result1.get('msg', '')}")
except Exception as e:
    print(f"万业谱写入失败: {e}")

# 4. 标记天机卷已处理
try:
    r2 = requests.post(
        f"{COZE_BASE}/{DB_TIANJI}/records/{source_id}",
        headers={
            "Authorization": f"Bearer {COZE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "is_analyzed": "true",
            "is_analyzing": "false",
            "analysis_time": now,
        },
        timeout=30,
    )
    result2 = r2.json()
    print(f"天机卷标记: code={result2.get('code')} msg={result2.get('msg', '')}")
except Exception as e:
    print(f"天机卷标记失败: {e}")

print("done")
