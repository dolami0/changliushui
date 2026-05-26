"""
36kr RSS → Coze 万象阁 ETL 测试脚本
第一性原理：抓取 → 清洗 → 去重指纹 → 入库
"""
import hashlib
import re
import sys
import time
from datetime import datetime, timezone, timedelta

import feedparser
import httpx

import os
# ====== Coze 配置 ======
COZE_TOKEN = os.environ.get("COZE_TOKEN", "")
COZE_BASE = "https://api.coze.cn/v1/databases"
HEADERS = {
    "Authorization": f"Bearer {COZE_TOKEN}",
    "Content-Type": "application/json",
}

# 北京时区
TZ_BEIJING = timezone(timedelta(hours=8))

# ====== 41. 万象阁字段定义 ======
# 所有字段预留下游 Agent 消费：stock_codes, tags, sentiment, quality_score
TABLE_FIELDS = [
    {"name": "title",        "desc": "资讯标题",         "type": "string",  "is_required": True},
    {"name": "content",      "desc": "清洗后纯文本正文",   "type": "string",  "is_required": True},
    {"name": "summary",      "desc": "前200字摘要",        "type": "string",  "is_required": False},
    {"name": "source",       "desc": "灵脉标识: 36kr_rss / user_submit / tianjijuan", "type": "string", "is_required": True},
    {"name": "source_url",   "desc": "原始链接",           "type": "string",  "is_required": True},
    {"name": "fingerprint",  "desc": "SHA256(title_norm + content[:200]) 去重指纹", "type": "string", "is_required": True},
    {"name": "published_at", "desc": "发布时间 ISO8601",   "type": "string",  "is_required": True},
    {"name": "stock_codes",  "desc": "关联股票代码 JSON数组,如 [\"688805\"]", "type": "string", "is_required": False},
    {"name": "tags",         "desc": "标签 JSON数组,如 [\"AI\",\"融资\"]",    "type": "string", "is_required": False},
    {"name": "sentiment",    "desc": "情感: positive / negative / neutral",  "type": "string", "is_required": False},
    {"name": "visibility",   "desc": "可见性: public / private",             "type": "string", "is_required": True},
    {"name": "quality_score","desc": "质量评分 0-10",      "type": "number",  "is_required": False},
    {"name": "ingested_at",  "desc": "入库时间 ISO8601",   "type": "string",  "is_required": True},
]

# ====== 工具函数 ======

def strip_html(html: str) -> str:
    """去除 HTML 标签，保留纯文本"""
    text = re.sub(r"<[^>]*>", "", html)           # 去标签
    text = re.sub(r"&[^;]+;", " ", text)          # 去 HTML 实体
    text = re.sub(r"\s+", " ", text).strip()       # 合并空白
    return text

def make_fingerprint(title: str, content: str) -> str:
    """SHA256 去重指纹：规范化标题 + 正文前 200 字符"""
    title_norm = re.sub(r"\s+", "", title).lower()
    content_head = content[:200].strip()
    raw = f"{title_norm}|{content_head}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def extract_summary(content: str, max_len: int = 200) -> str:
    """从正文提取摘要"""
    clean = content.strip()
    return clean[:max_len] + ("..." if len(clean) > max_len else "")

def now_iso() -> str:
    return datetime.now(TZ_BEIJING).isoformat()

# ====== Coze API 封装 ======

async def coze_create_table(name: str, desc: str, fields: list[dict]) -> str:
    """创建 Coze 数据库表，返回 database_id"""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            COZE_BASE,
            headers=HEADERS,
            json={
                "table_name": name,
                "table_desc": desc,
                "fields": fields,
                "rw_mode": "unlimited_read_write",
            },
        )
        data = resp.json()
        if data.get("code") != 0:
            print(f"  [ERROR] 建表失败: {data}")
            # 如果已存在，尝试从 msg 中提取 id 或返回 None
            return ""
        db_id = data["data"]["database_id"]
        print(f"  [OK] 万象阁 database_id: {db_id}")
        return db_id

async def coze_insert_records(database_id: str, records: list[dict]) -> int:
    """批量插入记录，返回成功条数"""
    # Coze 创建记录 API: POST /v1/databases/{id}/records
    async with httpx.AsyncClient(timeout=30) as client:
        inserted = 0
        for record in records:
            resp = await client.post(
                f"{COZE_BASE}/{database_id}/records",
                headers=HEADERS,
                json={"records": [record]},
            )
            data = resp.json()
            if data.get("code") == 0:
                inserted += 1
            else:
                print(f"  [WARN] 插入失败: {record.get('title','')[:30]}... → {data.get('msg','')}")
            # Coze API 限流保护
            time.sleep(0.3)
        return inserted

async def coze_query_existing_fingerprints(database_id: str) -> set[str]:
    """查询已有指纹，用于去重"""
    async with httpx.AsyncClient(timeout=30) as client:
        all_fps = set()
        page_token = ""
        for _ in range(10):
            body = {"page_size": 500}
            if page_token:
                body["page_token"] = page_token
            resp = await client.post(
                f"{COZE_BASE}/{database_id}/records/query",
                headers=HEADERS,
                json=body,
            )
            data = resp.json()
            items = data.get("data", {}).get("items", [])
            for item in items:
                fp = item.get("fingerprint", "")
                if fp:
                    all_fps.add(fp)
            has_more = data.get("data", {}).get("has_more", False)
            if not has_more:
                break
            page_token = data.get("data_page_token", "")
            if not page_token:
                break
        return all_fps


# ====== ETL 主流程 ======

async def main():
    print("=" * 60)
    print("  万象阁 · 36kr RSS ETL 测试")
    print("=" * 60)

    # ── Step 1: 抓取 36kr RSS ──
    print("\n[1/5] 抓取 36kr RSS feed...")
    rss_url = "https://36kr.com/feed"
    feed = feedparser.parse(rss_url)

    if feed.bozo:
        print(f"  [WARN] RSS 解析警告: {feed.bozo_exception}")

    entries = feed.entries
    print(f"  [OK] 获取到 {len(entries)} 条资讯")

    if not entries:
        print("  [FAIL] 无数据，退出")
        return

    # ── Step 2: 清洗 + 归一化 ──
    print("\n[2/5] 清洗归一化...")
    articles = []
    for entry in entries:
        title = entry.get("title", "").strip()
        raw_html = entry.get("description", "")
        content = strip_html(raw_html)
        link = entry.get("link", "")

        if not title or not content:
            continue

        articles.append({
            "title": title,
            "content": content,
            "summary": extract_summary(content),
            "source": "36kr_rss",
            "source_url": link,
            "fingerprint": make_fingerprint(title, content),
            "published_at": entry.get("published", now_iso()),
            "stock_codes": "[]",
            "tags": "[]",
            "sentiment": "neutral",
            "visibility": "public",
            "quality_score": 7.0,
            "ingested_at": now_iso(),
        })

    print(f"  [OK] 清洗完成，{len(articles)} 条有效")

    # 展示前 3 条样本
    for i, a in enumerate(articles[:3]):
        print(f"\n  --- 样本 {i+1} ---")
        print(f"  title:     {a['title'][:60]}...")
        print(f"  summary:   {a['summary'][:80]}...")
        print(f"  fingerprint: {a['fingerprint'][:16]}...")
        print(f"  published: {a['published_at']}")

    # ── Step 3: 创建 / 确认 Coze 万象阁表 ──
    print("\n[3/5] 确认 Coze 万象阁表...")
    WANXIANG_DB_ID = "7643379953873977385"  # 万象阁

    if False:  # 已建表，跳过
        print("  [ACTION] 请在 Coze 控制台手动创建数据库表，或运行建表逻辑")
        print("  字段清单:")
        for f in TABLE_FIELDS:
            print(f"    {f['name']:20s} {f['type']:8s} {f['desc']}")
        print("\n  建表后，将 database_id 填入脚本 WANXIANG_DB_ID 变量")
        print("  或在下方输入 database_id 继续（回车跳过入库）:")

        # 尝试自动建表
        print("\n  正在尝试自动创建 Coze 表...")
        db_id = await coze_create_table(
            "wanxiangge",
            "万象阁 - 长流水资讯中心。聚合多源新闻，归一化清洗，供下游Agent消费",
            TABLE_FIELDS,
        )
        if db_id:
            WANXIANG_DB_ID = db_id
        else:
            print("\n  [SKIP] 跳过入库步骤（无 database_id）")
            print("  [DONE] ETL 管道验证完成（不含入库）")
            return

    # ── Step 4: 去重检查 ──
    print("\n[4/5] 去重检查...")
    existing_fps = await coze_query_existing_fingerprints(WANXIANG_DB_ID)
    print(f"  [OK] 数据库中已有 {len(existing_fps)} 条记录")

    new_articles = []
    dup_count = 0
    for a in articles:
        if a["fingerprint"] in existing_fps:
            dup_count += 1
        else:
            new_articles.append(a)

    print(f"  [OK] 新记录: {len(new_articles)}, 重复(跳过): {dup_count}")

    # ── Step 5: 入库 ──
    print(f"\n[5/5] 入库 {len(new_articles)} 条新记录...")
    if new_articles:
        inserted = await coze_insert_records(WANXIANG_DB_ID, new_articles)
        print(f"  [OK] 成功入库 {inserted}/{len(new_articles)} 条")
    else:
        print("  [OK] 无新记录需入库")

    print("\n" + "=" * 60)
    print("  ETL 管道测试完成")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
