"""天机峰 — Coze 读写

三层数据:
  NewsPoolCoze: 快讯池中间表读写（双源汇聚、管线消费）
  YanbaoCoze: 研报表读写（棱镜内参，B 管线）
  TianjifengCoze: 天机卷读写（打标结果写入、下游消费）
"""

import re
import sys
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from valuation_app.coze_client import CozeClient

from .config import DB_TIANJIJUAN, DB_NEWS_POOL, DB_YANBAO


def _title_similarity(a: str, b: str) -> float:
    """两个标题的相似度（0-1）"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class NewsPoolCoze:
    """快讯池中间表读写器"""

    DEDUP_THRESHOLD = 0.55

    def __init__(self, coze_client: CozeClient):
        self.coze = coze_client
        self._db_id = DB_NEWS_POOL
        self._existing_ids: set[str] | None = None
        self._today_titles: list[str] | None = None

    def _ensure_loaded(self) -> None:
        """一次查询同时构建 existing_ids 和 today_titles（避免两次全量拉取）"""
        if self._existing_ids is not None and self._today_titles is not None:
            return
        records = self.coze.query_all_records(self._db_id)
        today = datetime.now().strftime("%Y-%m-%d")
        self._existing_ids = set()
        self._today_titles = []
        for r in records:
            self._existing_ids.add(str(r.get("news_id", "")))
            if (str(r.get("publish_time", "")).startswith(today)
                    or str(r.get("fetched_at", "")).startswith(today)):
                self._today_titles.append(str(r.get("title", "")))

    def _is_similar_to_today(self, title: str) -> bool:
        """检查标题是否与当天已有快讯相似"""
        self._ensure_loaded()
        for existing in self._today_titles:
            if _title_similarity(title, existing) >= self.DEDUP_THRESHOLD:
                return True
        return False

    def insert_news(self, news_list: list[dict]) -> int:
        """批量写入快讯到中间表。

        去重策略:
          1. news_id 精确去重（同源重复抓取）
          2. 当天 title 相似度去重（跨源同一事件不同表述）
        返回实际插入条数。
        """
        self._ensure_loaded()

        new_items = []
        for n in news_list:
            nid = n.get("news_id", "")
            title = n.get("title", "")
            if not nid or nid in self._existing_ids:
                continue
            if self._is_similar_to_today(title):
                continue
            new_items.append(n)
            self._existing_ids.add(nid)
            self._today_titles.append(title)

        if not new_items:
            return 0

        rows = []
        for n in new_items:
            rows.append({
                "news_id": n["news_id"],
                "title": n.get("title", ""),
                "summary": n.get("summary", ""),
                "source": n.get("source", ""),
                "url": n.get("url", ""),
                "publish_time": n.get("publish_time", ""),
                "is_processed": "false",
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        return self.coze.insert_records(self._db_id, rows)

    def query_unprocessed(self, limit: int = 20) -> list[dict]:
        """查询未处理的快讯（is_processed=false）"""
        all_records = self.coze.query_all_records(self._db_id)
        unprocessed = [r for r in all_records if str(r.get("is_processed", "")) == "false"]
        return unprocessed[:limit]

    def mark_processed(self, record_id: str, level: str = "", status: str = "") -> None:
        """标记快讯为已处理，回写等级和状态（字段不存在时静默跳过）"""
        fields = [{"field_name": "is_processed", "value": "true"}]
        if level:
            fields.append({"field_name": "pipeline_level", "value": level})
        if status:
            fields.append({"field_name": "pipeline_status", "value": status})
        try:
            self.coze.update_records(
                self._db_id,
                fields,
                {"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": record_id}]},
            )
        except Exception:
            self.coze.update_records(
                self._db_id,
                [{"field_name": "is_processed", "value": "true"}],
                {"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": record_id}]},
            )

    def cleanup_old(self, days: int = 7) -> int:
        """清理 N 天前已处理的记录，返回删除条数。"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        records = self.coze.query_with_filter(
            self._db_id,
            conditions=[{"left": "is_processed", "operation": "equal", "right": "true"}],
        )
        old = [r for r in records if str(r.get("fetched_at", "")) < cutoff]
        return len(old)


class TianjifengCoze:
    """天机峰专用 Coze 读写器"""

    DEDUP_DAYS = 7

    def __init__(self, coze_client: CozeClient):
        self.coze = coze_client
        self._db_id = DB_TIANJIJUAN
        self._existing_titles: set[str] | None = None

    def load_existing_titles(self) -> set[str]:
        """加载天机卷最近 N 天的 news_content，用于去重"""
        cutoff = (datetime.now() - timedelta(days=self.DEDUP_DAYS)).strftime("%Y-%m-%d")
        records = self.coze.query_all_records(self._db_id)
        self._existing_titles = {
            str(r.get("news_content", ""))
            for r in records
            if str(r.get("date", "")) >= cutoff or str(r.get("bstudio_create_time", "")) >= cutoff
        }
        return self._existing_titles

    def is_duplicate(self, title: str) -> bool:
        """检查快讯标题是否已存在于天机卷"""
        if self._existing_titles is None:
            self.load_existing_titles()
        return title in self._existing_titles

    def insert_record(
        self,
        news_content: str,
        level: str = "0",
        step_one: str = "",
        mode: str = "",
        stock_name: str = "",
        knowledge: str = "",
        is_analyzed: bool = False,
        date: str = "",
    ) -> None:
        """写入一条快讯记录到天机卷。"""
        row = {
            "news_content": news_content,
            "level": level,
            "is_analyzed": "true" if is_analyzed else "false",
        }
        if step_one:
            row["step_one"] = step_one
        if mode:
            row["mode"] = mode
        if stock_name:
            row["stock_name"] = stock_name
        if knowledge:
            row["knowledge"] = knowledge
        if date:
            row["date"] = date

        self.coze.insert_records(self._db_id, [row])

        if self._existing_titles is not None:
            self._existing_titles.add(news_content)


class YanbaoCoze:
    """研报表（棱镜内参）读写器 — B 管线"""

    def __init__(self, coze_client: CozeClient):
        self.coze = coze_client
        self._db_id = DB_YANBAO

    def query_unprocessed(self, limit: int = 10) -> list[dict]:
        """查询 step_one 为空的研报，按时间倒序取最新"""
        all_records = self.coze.query_all_records(self._db_id)
        unprocessed = [
            r for r in all_records
            if not str(r.get("step_one", "")).strip()
        ]
        unprocessed.sort(key=lambda x: str(x.get("bstudio_create_time", "")), reverse=True)
        return unprocessed[:limit]

    def mark_analyzed(self, record_id: str) -> None:
        """标记研报为已处理"""
        self.coze.update_records(
            self._db_id,
            [{"field_name": "is_analyzed", "value": "true"}],
            {"logic": "and", "conditions": [{"left": "id", "operation": "equal", "right": record_id}]},
        )

    @staticmethod
    def parse_news_content(news_content: str) -> tuple[str, str]:
        """从研报的 news_content 中解析标题和正文。

        格式: <card title="📝 棱镜内参">\n标题\n正文...\n📝 棱镜收录 | ...\n</card>
        返回 (title, summary)。
        """
        text = re.sub(r"</?card[^>]*>", "", news_content).strip()
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        lines = [l for l in lines if not l.startswith("📝") and not l.startswith("🔒")]
        if not lines:
            return "", ""
        title = lines[0]
        summary = "\n".join(lines[1:]) if len(lines) > 1 else ""
        return title, summary
