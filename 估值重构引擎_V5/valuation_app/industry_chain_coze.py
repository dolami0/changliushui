"""
产业链利润流工作流 — Coze 表读写专用模块

数据流:
  读: Coze 表 7479116110479048754 (产业资讯源)
      筛选: level>=4, mode="产业模式", is_analyzed!=true
  写: 自建 Coze 输出表 (产业链分析结果)
  标记: 处理完后更新源表 is_analyzed=true
"""

import time
from valuation_app.coze_client import CozeClient

# ── 表 ID ─────────────────────────────────────
SOURCE_TABLE_ID = "7479116110479048754"       # 产业资讯源表
OUTPUT_TABLE_ID = "7640928034144698374"       # industry_chain_analysis


# ── 输出表字段定义 ─────────────────────────────
OUTPUT_TABLE_FIELDS = [
    {"name": "source_record_id", "type": "integer", "desc": "Source record ID", "is_required": True},
    {"name": "news_content", "type": "string", "desc": "Original news", "is_required": False},
    {"name": "step_one_data", "type": "string", "desc": "Agent0 analysis", "is_required": False},
    {"name": "industry_chain", "type": "string", "desc": "Industry chain name", "is_required": False},
    {"name": "event_summary", "type": "string", "desc": "Event summary", "is_required": False},
    {"name": "top_nodes_json", "type": "string", "desc": "Top 2 nodes JSON", "is_required": False},
    {"name": "top_pick_code", "type": "string", "desc": "Top pick stock code", "is_required": False},
    {"name": "top_pick_name", "type": "string", "desc": "Top pick stock name", "is_required": False},
    {"name": "top_pick_score", "type": "string", "desc": "Top pick total score", "is_required": False},
    {"name": "top_pick_thesis", "type": "string", "desc": "Top pick investment thesis", "is_required": False},
    {"name": "runner_up_code", "type": "string", "desc": "Runner up stock code", "is_required": False},
    {"name": "runner_up_name", "type": "string", "desc": "Runner up stock name", "is_required": False},
    {"name": "runner_up_score", "type": "string", "desc": "Runner up total score", "is_required": False},
    {"name": "runner_up_thesis", "type": "string", "desc": "Runner up investment thesis", "is_required": False},
    {"name": "top5_json", "type": "string", "desc": "All candidate stock scores JSON (renamed from top5, now full list)", "is_required": False},
    {"name": "chain_analysis_json", "type": "string", "desc": "Full chain analysis JSON", "is_required": False},
    {"name": "stock_analysis_json", "type": "string", "desc": "Full stock scoring JSON", "is_required": False},
    {"name": "is_analyzed", "type": "boolean", "desc": "Flag for downstream workflows", "is_required": False},
    {"name": "status", "type": "string", "desc": "done/error/skipped", "is_required": False},
]


class IndustryChainCoze:
    """产业链工作流专用 Coze 读写器"""

    def __init__(self, coze_client: CozeClient):
        self.coze = coze_client
        self._output_db_id = OUTPUT_TABLE_ID

    # ── 读操作 ─────────────────────────────────

    def query_unprocessed(self, min_level: int = 4) -> list[dict]:
        """
        查询未处理的产业模式记录。

        筛选条件:
          - level >= min_level (默认4)
          - mode = "产业模式"
          - is_analyzed != "true"

        去重: 同日相同 news_content 只保留一条
        """
        all_records = self.coze.query_all_records(SOURCE_TABLE_ID)

        candidates = []
        for r in all_records:
            level = int(r.get("level", 0))
            mode = str(r.get("mode", ""))
            analyzed = str(r.get("is_analyzed", "")).lower()
            analyzing = str(r.get("is_analyzing", "")).lower()

            if level >= min_level and "产业" in mode and analyzed != "true" and analyzing != "true":
                candidates.append(r)

        # 去重: 同日同 news_content 跳过
        seen = set()
        deduped = []
        for r in candidates:
            date = str(r.get("date", "") or r.get("bstudio_create_time", ""))[:10]
            content = str(r.get("news_content", ""))[:200]
            key = (date, content)
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        return deduped

    def get_record_by_id(self, record_id: str) -> dict | None:
        """按 ID 获取单条记录"""
        records = self.coze.query_all_records(SOURCE_TABLE_ID)
        for r in records:
            if str(r.get("id", "")) == str(record_id):
                return r
        return None

    # ── 写操作 ─────────────────────────────────

    def ensure_output_table(self, table_name: str = "产业链利润流分析结果") -> str:
        """确保输出表存在，返回 database_id"""
        if self._output_db_id and self._output_db_id != "None":
            return self._output_db_id
        for attempt in range(5):
            try:
                db_id = self.coze.create_database(
                    table_name=table_name,
                    table_desc="Agent 0_5 产业链利润流分析结果",
                    fields=OUTPUT_TABLE_FIELDS,
                )
                self._output_db_id = db_id
                print(f"[IndustryChainCoze] 创建输出表: {db_id}")
                return db_id
            except Exception as e:
                msg = str(e)
                if "500" in msg or "server" in msg.lower():
                    wait = (attempt + 1) * 10
                    print(f"[IndustryChainCoze] Coze服务繁忙，{wait}s后重试({attempt+1}/5)...")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("Coze 建表失败：持续返回错误，请稍后重试")

    def write_result(self, result: dict) -> str:
        """
        写入一条分析结果到输出表。

        result 字段:
          - source_record_id, industry_chain, event_summary
          - top_nodes_json (str), top5_reference_json (str)
          - chain_analysis_json (str)
          - top_pick_code/name/score, runner_up_code/name/score
          - status
        """
        db_id = self.ensure_output_table()

        row = {
            "source_record_id": _safe_int(result.get("source_record_id", 0)),
            "news_content": str(result.get("news_content", ""))[:3000],
            "step_one_data": str(result.get("step_one", ""))[:3000],
            "web_research": str(result.get("web_research", ""))[:5000],
            "industry_chain": str(result.get("industry_chain", "")),
            "event_summary": str(result.get("event_summary", ""))[:500],
            "top_nodes_json": str(result.get("top_nodes_json", "")),
            "top_pick_code": str(result.get("top_pick_code", "")),
            "top_pick_name": str(result.get("top_pick_name", "")),
            "top_pick_score": str(result.get("top_pick_score", "")),
            "top_pick_thesis": str(result.get("top_pick_thesis", ""))[:500],
            "runner_up_code": str(result.get("runner_up_code", "")),
            "runner_up_name": str(result.get("runner_up_name", "")),
            "runner_up_score": str(result.get("runner_up_score", "")),
            "runner_up_thesis": str(result.get("runner_up_thesis", ""))[:500],
            "top5_json": str(result.get("scored_stocks_json", "")),
            "chain_analysis_json": str(result.get("chain_analysis_json", "")),
            "stock_analysis_json": str(result.get("stock_analysis_json", "")),
            "is_analyzed": False,
            "status": str(result.get("status", "done")),
        }

        self.coze.insert_records(db_id, [row])
        return db_id

    def mark_analyzing(self, record_id: str) -> None:
        """标记源表记录为分析中 — 防止调度器重复拉取"""
        try:
            self.coze.update_records(
                SOURCE_TABLE_ID,
                update_fields=[{"field_name": "is_analyzing", "value": "true"}],
                filter_conditions={"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": str(record_id)}]},
            )
        except Exception as e:
            print(f'[Coze] mark_analyzing 失败: {e}', flush=True)

    def mark_error(self, record_id: str) -> None:
        """标记为错误: is_analyzing=true + is_analyzed=false。

        效果: 调度器跳过(analyzing=true)，不重试；analyzed=false 可区分成功记录。
        适合错误记录，需手动排查后重置。
        """
        try:
            self.coze.update_records(
                SOURCE_TABLE_ID,
                update_fields=[
                    {"field_name": "is_analyzing", "value": "true"},
                    {"field_name": "is_analyzed", "value": "false"},
                ],
                filter_conditions={"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": str(record_id)}]},
            )
        except Exception as e:
            print(f'[Coze] mark_error 失败: {e}', flush=True)

    def mark_processed(self, record_id: str) -> None:
        """标记源表记录为已分析，同时清除分析中标志"""
        try:
            self.coze.update_records(
                SOURCE_TABLE_ID,
                update_fields=[
                    {"field_name": "is_analyzed", "value": "true"},
                    {"field_name": "is_analyzing", "value": "false"},
                ],
                filter_conditions={"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": str(record_id)}]},
            )
        except Exception as e:
            print(f'[Coze] mark_processed 失败: {e}', flush=True)

    def get_output_db_id(self) -> str | None:
        return self._output_db_id


def _safe_int(val) -> int:
    """安全转 int"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0
