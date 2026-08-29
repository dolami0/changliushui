"""快讯抓取 — 双源汇聚

东方财富 7×24 快讯：公开 JSON API，50条/次，偏 A 股公告/交易面
36氪 RSS：XML Feed，~20条/日，偏科技/创投/产业趋势
"""

import json
import re
import time
import html
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import requests

_EM_URL = "https://newsapi.eastmoney.com/kuaixun/v1/getlist_101_ajaxResult_50_1_.html"
_36KR_RSS_URL = "https://www.36kr.com/feed"
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
    """抓取 36氪 RSS Feed。老 SSR 数据嵌入方式已失效，用 RSS 降级替代。"""
    for attempt in range(max_retries):
        try:
            resp = requests.get(_36KR_RSS_URL, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            raw = resp.text

            # 36kr RSS 偶尔包含非标准字符，清理 & 编码
            raw = re.sub(r"&(?![a-zA-Z]+;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", raw)

            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                print("[fetcher] 36氪 RSS XML 解析失败", flush=True)
                return []

            results = []
            for item in root.iter("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                pub_el = item.find("pubDate")
                desc_el = item.find("description")

                title = html.unescape((title_el.text or "").strip()) if title_el is not None else ""
                if not title:
                    continue

                link = ""
                if link_el is not None:
                    link = (link_el.text or "").strip()
                    link = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", link)

                pub_time = ""
                if pub_el is not None:
                    raw_pub = (pub_el.text or "").strip()
                    try:
                        pub_time = parsedate_to_datetime(raw_pub).strftime("%Y-%m-%d %H:%M:%S")
                    except (ValueError, OSError):
                        pub_time = raw_pub[:19]

                desc_text = ""
                if desc_el is not None:
                    desc_text = html.unescape((desc_el.text or "")[:200]).strip()
                    desc_text = re.sub(r"<[^>]+>", "", desc_text)
                    desc_text = re.sub(r"\s+", " ", desc_text)

                item_id = re.search(r"/p/(\d+)", link)
                news_id = f"36kr_{item_id.group(1)}" if item_id else f"36kr_{hash(title) & 0x7fffffff}"

                results.append({
                    "news_id": news_id,
                    "title": title,
                    "summary": desc_text,
                    "source": "36kr",
                    "url": link,
                    "publish_time": pub_time,
                })

            if results:
                return results

            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return []
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            print(f"[fetcher] 36氪 RSS 抓取失败: {e}", flush=True)
            return []
    return []


def fetch_all() -> list[dict]:
    """抓取所有源，合并返回。"""
    em = fetch_eastmoney()
    kr = fetch_36kr()
    combined = em + kr
    print(f"[fetcher] 东方财富 {len(em)} 条 + 36氪RSS {len(kr)} 条 = 共 {len(combined)} 条", flush=True)
    return combined


def fetch_flashnews(tag: str = "A股", max_retries: int = 3) -> list[dict]:
    """兼容旧接口，内部调 fetch_all()。"""
    return fetch_all()
