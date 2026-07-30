"""快讯抓取 — 双源汇聚

东方财富 7×24 快讯：公开 JSON API，50条/次，偏 A 股公告/交易面
36氪快讯：SSR 页面内嵌 JSON，~20条/次，偏科技/创投/产业趋势
"""

import json
import re
import time
from datetime import datetime

import requests

_EM_URL = "https://newsapi.eastmoney.com/kuaixun/v1/getlist_101_ajaxResult_50_1_.html"
_36KR_URL = "https://36kr.com/newsflashes"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def fetch_eastmoney(max_retries: int = 3) -> list[dict]:
    """抓取东方财富 7×24 快讯。返回统一格式列表。"""
    for attempt in range(max_retries):
        try:
            resp = requests.get(_EM_URL, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            text = resp.text
            if text.startswith("var ajaxResult="):
                text = text[len("var ajaxResult="):]
            data = json.loads(text)
            items = data.get("LivesList", [])

            results = []
            for item in items:
                news_id = f"em_{item.get('newsid', '')}"
                if not item.get("title"):
                    continue
                results.append({
                    "news_id": news_id,
                    "title": str(item.get("title", "")),
                    "summary": str(item.get("digest", "") or item.get("simdigest", "")),
                    "source": "eastmoney",
                    "url": str(item.get("url_w", "") or item.get("url_m", "")),
                    "publish_time": str(item.get("showtime", "")),
                })
            return results
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"[fetcher] 东方财富抓取失败: {e}", flush=True)
            return []
    return []


def fetch_36kr(max_retries: int = 3) -> list[dict]:
    """抓取 36氪快讯（解析 SSR 页面内嵌 JSON）。返回统一格式列表。"""
    for attempt in range(max_retries):
        try:
            resp = requests.get(_36KR_URL, headers=_HEADERS, timeout=15)
            resp.raise_for_status()

            m = re.search(
                r"window\.initialState\s*=\s*({.*?})\s*;?\s*</script>",
                resp.text, re.DOTALL,
            )
            if not m:
                print("[fetcher] 36氪页面未找到 initialState", flush=True)
                return []

            data = json.loads(m.group(1))
            items = (
                data.get("newsflashCatalogData", {})
                .get("data", {})
                .get("newsflashList", {})
                .get("data", {})
                .get("itemList", [])
            )

            results = []
            for item in items:
                mat = item.get("templateMaterial", {})
                title = mat.get("widgetTitle", "")
                if not title:
                    continue
                item_id = item.get("itemId", "")
                ts_ms = mat.get("publishTime", 0)
                try:
                    pub_time = datetime.fromtimestamp(int(ts_ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, OSError):
                    pub_time = ""
                results.append({
                    "news_id": f"36kr_{item_id}",
                    "title": str(title),
                    "summary": str(mat.get("widgetContent", "")),
                    "source": "36kr",
                    "url": f"https://36kr.com/newsflashes/{item_id}" if item_id else "",
                    "publish_time": pub_time,
                })
            return results
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"[fetcher] 36氪抓取失败: {e}", flush=True)
            return []
    return []


def fetch_all() -> list[dict]:
    """抓取所有源，合并返回。"""
    em = fetch_eastmoney()
    kr = fetch_36kr()
    combined = em + kr
    print(f"[fetcher] 东方财富 {len(em)} 条 + 36氪 {len(kr)} 条 = 共 {len(combined)} 条", flush=True)
    return combined


def fetch_flashnews(tag: str = "A股", max_retries: int = 3) -> list[dict]:
    """兼容旧接口，内部调 fetch_all()。"""
    return fetch_all()
