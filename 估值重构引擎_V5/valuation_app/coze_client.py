"""
Coze Open API 客户端 — 数据库读写封装

API 端点 (基础地址 https://api.coze.cn):
  POST /v1/databases                          — 创建数据表
  POST /v1/databases/{id}/records/query       — 查询记录
  POST /v1/databases/{id}/records             — 插入记录
  PUT  /v1/databases/{id}/records             — 更新记录
"""

import json
from datetime import datetime
from typing import Any

import requests


class CozeClient:
    """Coze 数据库 API 客户端"""

    def __init__(self, token: str, workspace_id: str, base_url: str = "https://api.coze.cn"):
        self.token = token
        self.workspace_id = workspace_id
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = self._session.post(url, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Coze API error: {data.get('msg', 'unknown')} — {json.dumps(body, ensure_ascii=False)[:300]}")
        return data

    def _put(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        resp = self._session.put(url, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Coze API error: {data.get('msg', 'unknown')}")
        return data

    # ── 建表 ─────────────────────────────────

    def create_database(self, table_name: str, table_desc: str, fields: list[dict]) -> str:
        """
        创建数据表，返回 database_id。

        fields 格式:
          [{"name":"stock_code","desc":"股票代码","type":"string","is_required":true}, ...]
        类型: string | integer | number | boolean | date | time | datetime
        命名: 小写字母/数字/下划线，字母开头，最长64字符
        """
        body = {
            "workspace_id": self.workspace_id,
            "table_name": table_name,
            "table_desc": table_desc,
            "fields": fields,
            "rw_mode": "limited_read_write",
        }
        data = self._post("/v1/databases", body)
        db_id = data["data"]["database_id"]
        return db_id

    # ── 查询 (Agent0 输入表) ──────────────────

    def query_incomplete_records(self, database_id: str, page_size: int = 100) -> list[dict]:
        """查询 is_complete='false' 的记录"""
        body = {
            "page_num": 1,
            "page_size": page_size,
            "filter": {
                "logic": "and",
                "conditions": [
                    {"left": "is_complete", "operation": "equal", "right": "false"}
                ]
            },
            "is_async": False,
        }
        data = self._post(f"/v1/databases/{database_id}/records/query", body)
        return data.get("data", {}).get("items", [])

    def query_all_records(self, database_id: str) -> list[dict]:
        """查询表中全部记录（分页获取）"""
        all_items = []
        page_num = 1
        while True:
            body = {"page_num": page_num, "page_size": 500, "is_async": False}
            data = self._post(f"/v1/databases/{database_id}/records/query", body)
            items = data.get("data", {}).get("items", [])
            all_items.extend(items)
            if not data.get("data", {}).get("has_more"):
                break
            page_num += 1
        return all_items

    # ── 写入 (输出表) ─────────────────────────

    def insert_records(self, database_id: str, rows: list[dict]) -> int:
        """
        批量插入记录。rows 中所有值自动转为字符串。
        单次最多 1000 条，返回 affected_rows。
        """
        insert_rows = []
        for row in rows:
            str_row = {k: str(v) if v is not None else "" for k, v in row.items()}
            insert_rows.append(str_row)

        body = {"insert_rows": insert_rows, "is_async": False}
        data = self._post(f"/v1/databases/{database_id}/records", body)
        return data.get("data", {}).get("affected_rows", 0)

    # ── 更新 ─────────────────────────────────

    def update_records(self, database_id: str, update_fields: list[dict], filter_conditions: dict) -> int:
        """
        按条件更新记录。filter 必须提供，不允许全表更新。

        update_fields: [{"field_name":"is_complete","value":"true"}]
        filter_conditions: {"logic":"and","conditions":[{"left":"id","operation":"equal","right":"xxx"}]}
        """
        body = {
            "update_fields": update_fields,
            "filter": filter_conditions,
            "is_async": False,
        }
        data = self._put(f"/v1/databases/{database_id}/records", body)
        return data.get("data", {}).get("affected_rows", 0)

    def mark_record_complete(self, database_id: str, record_id: str):
        """将 Agent0 表中的记录标记为已完成"""
        self.update_records(
            database_id,
            [{"field_name": "is_complete", "value": "true"}],
            {"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": record_id}]},
        )


# ── 输出表字段定义（精简至20字段，满足 Coze API 建表上限）────

OUTPUT_TABLE_FIELDS = [
    # 标识 (5)
    {"name": "stock_code", "desc": "股票代码", "type": "string", "is_required": True},
    {"name": "stock_name", "desc": "股票名称", "type": "string", "is_required": True},
    {"name": "event_date", "desc": "事件日期", "type": "string", "is_required": False},
    {"name": "event_source", "desc": "事件来源", "type": "string", "is_required": False},
    {"name": "primary_model", "desc": "主估值模型(A-J)", "type": "string", "is_required": False},
    # 核心结果 (5)
    {"name": "prob_weighted_upside_pct", "desc": "概率加权涨幅(%)", "type": "number", "is_required": False},
    {"name": "asymmetry_ratio", "desc": "不对称比", "type": "number", "is_required": False},

    {"name": "current_mcap_billion", "desc": "当前市值(亿)", "type": "number", "is_required": False},
    {"name": "prob_weighted_mcap_billion", "desc": "概率加权目标市值(亿)", "type": "number", "is_required": False},
    # 三情景 (6)
    {"name": "bear_prob", "desc": "Bear概率(%)", "type": "number", "is_required": False},
    {"name": "bear_upside_pct", "desc": "Bear涨跌幅(%)", "type": "number", "is_required": False},
    {"name": "base_prob", "desc": "Base概率(%)", "type": "number", "is_required": False},
    {"name": "base_upside_pct", "desc": "Base涨跌幅(%)", "type": "number", "is_required": False},
    {"name": "bull_prob", "desc": "Bull概率(%)", "type": "number", "is_required": False},
    {"name": "bull_upside_pct", "desc": "Bull涨跌幅(%)", "type": "number", "is_required": False},
    # 置信度与交易 (2)
    {"name": "confidence_score", "desc": "综合置信度(0-10)", "type": "number", "is_required": False},
    {"name": "trade_tier", "desc": "交易等级", "type": "string", "is_required": False},
    # 链接与状态 (2)
    {"name": "report_html_url", "desc": "HTML完整报告链接", "type": "string", "is_required": False},
    {"name": "processed_at", "desc": "处理完成时间", "type": "string", "is_required": False},
]
