"""飞书群消息 → Coze 采集器

替代原 Coze Bot（棱镜内参群消息写入研报表的工作流）。
按消息类型分流：
  - 📝 棱镜内参 → 研报表（B 管线，高质量长篇研报）
  - 🎯 实时小作文 → 快讯池（A 管线，短消息需初筛过滤）

由天机峰调度器 B 管线轮询前调用，也可独立 CLI 运行。

数据源: 飞书群 oc_10a454b1d6966bd0e04b50a027a947ea（棱镜内参）
目标表: 研报表 DB_YANBAO / 快讯池 DB_NEWS_POOL

CLI:
  python -m src.tianjifeng.lark_fetcher            # 采集一轮
  python -m src.tianjifeng.lark_fetcher --dry-run   # 只看不写
"""

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from .config import COZE_SAT_TOKEN, COZE_BASE, DB_YANBAO, DB_NEWS_POOL

import requests

# ── 常量 ──────────────────────────────────────────────

LARK_CHAT_ID = "oc_10a454b1d6966bd0e04b50a027a947ea"
# lark-cli 完整路径 — subprocess 不继承 shell PATH，必须用绝对路径
LARK_CLI = r"C:\Users\1\AppData\Roaming\npm\lark-cli.cmd"

# 每次拉取的消息页大小（飞书 API 上限 50）
PAGE_SIZE = 50

# 单次最多采集条数（防 backlog 过大时一次写太多）
MAX_FETCH_PER_RUN = 200


# ── 飞书消息拉取 ──────────────────────────────────────

def fetch_messages(page_token: str = "", start_time: str = "") -> dict:
    """通过 lark-cli 拉取群消息（user 身份）。"""
    cmd = [
        LARK_CLI, "im", "+chat-messages-list",
        "--chat-id", LARK_CHAT_ID,
        "--as", "user",
        "--page-size", str(PAGE_SIZE),
        "--sort", "desc",
    ]
    if page_token:
        cmd += ["--page-token", page_token]
    if start_time:
        cmd += ["--start", start_time]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"lark-cli 调用失败: {result.stderr[:300]}")

    data = json.loads(result.stdout)
    if not data.get("ok"):
        raise RuntimeError(f"lark-cli 返回错误: {data.get('error', {}).get('message', '?')}")

    return data.get("data", {})


# ── 消息分类 ──────────────────────────────────────────

def classify_message(msg: dict) -> str:
    """分类消息: 'yanbao' | 'xiaozuowen' | 'skip'"""
    content = msg.get("content", "")
    if '<card title="📝 棱镜内参">' in content:
        return "yanbao"
    if '<card title="🎯 实时小作文">' in content:
        return "xiaozuowen"
    return "skip"


def extract_card_body(content: str) -> str:
    """从 card 标签中提取正文（去掉 card 标签和尾部的收录时间行）。"""
    text = re.sub(r"</?card[^>]*>", "", content).strip()
    # 去掉末尾的 📝 ⏱ 捕获时间 / 📝 棱镜收录 行
    lines = text.split("\n")
    lines = [l for l in lines if not re.match(r"^📝\s*(⏱|棱镜收录)", l.strip())]
    # 去掉分隔线
    lines = [l for l in lines if l.strip() != "---"]
    return "\n".join(lines).strip()


def is_image_only(msg: dict) -> bool:
    """判断是否纯图片消息（无文字内容）。"""
    body = extract_card_body(msg.get("content", ""))
    # "🖼️ 大V图片" 或 "🖼️ Image" 且正文只有这一行
    return bool(re.match(r"^🖼️\s*(大V图片|Image)\s*$", body))


def extract_message_time(msg: dict) -> str:
    """从消息内容中提取时间，格式化为 Coze 的 bstudio_create_time。"""
    content = msg.get("content", "")
    m = re.search(r"(?:棱镜收录|捕获时间)[：:|]+\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})", content)
    if m:
        y, mo, d, h, mi, s = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d} {int(h):02d}:{mi}:{s} +0800 CST"

    ct = msg.get("create_time", "")
    if ct:
        try:
            dt = datetime.strptime(ct, "%Y-%m-%d %H:%M")
            return dt.strftime("%Y-%m-%d %H:%M:%S") + " +0800 CST"
        except ValueError:
            pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " +0800 CST"


# ── 去重 ──────────────────────────────────────────────

def fetch_existing_news_ids(db_id: str) -> set[str]:
    """拉取指定 Coze 表已有的全部 news_id。"""
    headers = {
        "Authorization": f"Bearer {COZE_SAT_TOKEN}",
        "Content-Type": "application/json",
    }
    existing = set()
    page = 1
    while True:
        body = {"page_num": page, "page_size": 500, "is_async": False}
        r = requests.post(
            f"{COZE_BASE}/{db_id}/records/query",
            headers=headers, json=body, timeout=30,
        )
        data = r.json()
        if data.get("code") != 0:
            print(f"[去重] 查询失败({db_id}): {data.get('msg', '?')}", file=sys.stderr)
            break
        items = data.get("data", {}).get("items", [])
        for it in items:
            nid = it.get("news_id", "")
            if nid:
                existing.add(nid)
        if not data.get("data", {}).get("has_more"):
            break
        page += 1
    return existing


# ── 写入 Coze ─────────────────────────────────────────

def insert_to_db(db_id: str, rows: list[dict]) -> int:
    """批量写入 Coze 表。"""
    if not rows:
        return 0
    headers = {
        "Authorization": f"Bearer {COZE_SAT_TOKEN}",
        "Content-Type": "application/json",
    }
    insert_rows = [{k: str(v) for k, v in row.items()} for row in rows]
    body = {"insert_rows": insert_rows, "is_async": False}
    r = requests.post(
        f"{COZE_BASE}/{db_id}/records",
        headers=headers, json=body, timeout=60,
    )
    data = r.json()
    if data.get("code") != 0:
        print(f"[写入] Coze 写入失败({db_id}): {data.get('msg', '?')}", file=sys.stderr)
        return 0
    return data.get("data", {}).get("affected_rows", 0)


# ── 主流程 ────────────────────────────────────────────

def run_fetch(dry_run: bool = False, verbose: bool = True) -> dict:
    """采集一轮：拉群消息 → 分类 → 去重 → 分别写入研报表和快讯池。

    Returns: {"fetched": int, "yanbao_new": int, "yanbao_inserted": int,
              "xiaozuowen_new": int, "xiaozuowen_inserted": int, "skipped": int}
    """
    stats = {
        "fetched": 0, "skipped": 0, "image_only": 0,
        "yanbao_new": 0, "yanbao_inserted": 0,
        "xiaozuowen_new": 0, "xiaozuowen_inserted": 0,
    }

    # 1. 拉取两张表已有的 news_id
    yanbao_ids = fetch_existing_news_ids(DB_YANBAO)
    pool_ids = fetch_existing_news_ids(DB_NEWS_POOL)
    if verbose:
        print(f"[采集] 研报表已有 {len(yanbao_ids)} 条, 快讯池已有 {len(pool_ids)} 条")

    # 2. 分页拉取群消息
    new_yanbao = []
    new_xiaozuowen = []
    page_token = ""
    pages = 0
    max_pages = (MAX_FETCH_PER_RUN + PAGE_SIZE - 1) // PAGE_SIZE

    while pages < max_pages:
        try:
            data = fetch_messages(page_token=page_token)
        except Exception as e:
            print(f"[采集] 拉取消息失败: {e}", file=sys.stderr)
            break

        messages = data.get("messages", [])
        if not messages:
            break

        for msg in messages:
            stats["fetched"] += 1
            mid = msg.get("message_id", "")
            category = classify_message(msg)

            if category == "skip":
                stats["skipped"] += 1
                continue

            if category == "yanbao":
                if mid in yanbao_ids:
                    continue
                new_yanbao.append(msg)

            elif category == "xiaozuowen":
                if mid in pool_ids:
                    continue
                if is_image_only(msg):
                    stats["image_only"] += 1
                    continue
                new_xiaozuowen.append(msg)

        if not data.get("has_more"):
            break
        page_token = data.get("page_token", "")
        pages += 1

    stats["yanbao_new"] = len(new_yanbao)
    stats["xiaozuowen_new"] = len(new_xiaozuowen)
    if verbose:
        print(f"[采集] 拉取 {stats['fetched']} 条消息: "
              f"棱镜内参新 {stats['yanbao_new']} 条, "
              f"小作文新 {stats['xiaozuowen_new']} 条, "
              f"纯图片跳过 {stats['image_only']} 条")

    if dry_run:
        for msg in (new_yanbao[:2] + new_xiaozuowen[:2]):
            cat = classify_message(msg)
            body_preview = extract_card_body(msg.get("content", ""))[:80].replace("\n", " ")
            print(f"  [dry-run][{cat}] {msg.get('message_id', '?')[:25]}... | {body_preview}...")
        return stats

    # 3. 写入研报表
    if new_yanbao:
        rows = []
        for msg in new_yanbao:
            rows.append({
                "news_id": msg.get("message_id", ""),
                "news_content": msg.get("content", ""),
                "is_analyzed": "false",
                "step_one": "",
                "level": "",
                "analysis_time": "",
            })
        n = insert_to_db(DB_YANBAO, rows)
        stats["yanbao_inserted"] = n
        if verbose:
            print(f"[写入] 研报表: {n} 条")

    # 4. 写入快讯池
    if new_xiaozuowen:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for msg in new_xiaozuowen:
            body = extract_card_body(msg.get("content", ""))
            # 第一行当 title，其余当 summary
            lines = body.split("\n", 1)
            title = lines[0].strip() if lines else ""
            summary = lines[1].strip() if len(lines) > 1 else ""
            rows.append({
                "news_id": msg.get("message_id", ""),
                "title": title,
                "summary": summary,
                "source": "lark_xiaozuowen",
                "url": msg.get("message_app_link", ""),
                "publish_time": extract_message_time(msg).replace(" +0800 CST", ""),
                "is_processed": "false",
                "fetched_at": now_str,
            })
        n = insert_to_db(DB_NEWS_POOL, rows)
        stats["xiaozuowen_inserted"] = n
        if verbose:
            print(f"[写入] 快讯池: {n} 条")

    return stats


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    result = run_fetch(dry_run=dry)
    print(f"结果: {result}")
