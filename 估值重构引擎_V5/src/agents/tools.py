"""共享工具函数 — 供所有 Agent 调用"""

import requests
import json
import subprocess
import os
from typing import Optional


# ═══════════════════════════════════════════════
# Tool 1: 博查 Web Search
# ═══════════════════════════════════════════════

BOCHA_KEY = os.environ.get("BOCHA_KEY", "")
BOCHA_URL = "https://api.bochaai.com/v1/web-search"


def bocha_search(query: str, count: int = 5, freshness: str = "oneYear") -> str:
    """搜索中文互联网信息。

    Args:
        query: 搜索查询语句（自然语言）
        count: 返回结果数（1-50）
        freshness: 时间范围（noLimit/oneDay/oneWeek/oneMonth/oneYear）

    Returns:
        格式化的搜索结果文本，每条含标题、来源、日期、摘要
    """
    try:
        r = requests.post(
            BOCHA_URL,
            headers={
                "Authorization": f"Bearer {BOCHA_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "query": query,
                "count": min(count, 10),
                "freshness": freshness,
                "summary": True,
            },
            timeout=30,
        )
        data = r.json()
        pages = data.get("data", {}).get("webPages", {}).get("value", [])

        if not pages:
            return "未找到相关搜索结果。请换个角度或更具体的查询重试。"

        results = []
        for i, page in enumerate(pages):
            title = page.get("name", "无标题")
            date = page.get("datePublished", "")
            site = page.get("siteName", "")
            summary = page.get("summary", page.get("snippet", ""))
            url = page.get("url", "")

            results.append(
                f"[{i + 1}] {title}\n"
                f"来源: {site} | 日期: {date}\n"
                f"URL: {url}\n"
                f"摘要: {summary[:1200]}\n"
            )

        return "\n---\n".join(results)

    except Exception as e:
        return f"搜索异常: {str(e)}"


def fetch_url(url: str) -> str:
    """读取网页全文内容。

    Args:
        url: 网页地址（从 bocha_search 返回结果中获取）

    Returns:
        网页正文文本（已去除HTML标签）或错误提示
    """
    try:
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }, timeout=15)
        r.raise_for_status()

        # 简单 HTML→文本：去掉 script/style，保留可见文本
        import re as _re
        html = r.text
        for tag in ['script', 'style', 'nav', 'footer', 'header']:
            html = _re.sub(f'<{tag}[^>]*>.*?</{tag}>', '', html, flags=_re.DOTALL | _re.IGNORECASE)

        text = _re.sub(r'<[^>]+>', ' ', html)  # 去标签
        text = _re.sub(r'\s+', ' ', text).strip()  # 合并空白
        return text[:5000] if len(text) > 5000 else text

    except Exception as e:
        return f"网页读取失败: {str(e)}"


# ═══════════════════════════════════════════════
# Tool 2: tushare 主营构成
# ═══════════════════════════════════════════════

TUSHARE_SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..",
    ".agents", "agents", "shenwaihuashen", "data_helper.py"
)
TUSHARE_PYTHON = r"C:\Users\1\miniconda3\python"


def tushare_segment(stock_code: str) -> str:
    """获取分产品/分业务的主营构成数据。

    返回最近2个报告期的收入占比和毛利率，格式化为 LLM 可直接消费的文本。

    Args:
        stock_code: 股票代码，如 300308

    Returns:
        分产品/分业务摘要文本
    """
    try:
        script_dir = os.path.dirname(os.path.abspath(TUSHARE_SCRIPT))
        result = subprocess.run(
            [TUSHARE_PYTHON, TUSHARE_SCRIPT, "segment", stock_code],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=script_dir,
        )

        if result.returncode != 0:
            return f"tushare segment 获取失败: {result.stderr[:200]}"

        rows = json.loads(result.stdout)
        if not rows:
            return f"tushare: {stock_code} 无主营构成数据"

        # 按报告期分组
        periods = sorted(set(r["period"] for r in rows), reverse=True)

        summary = [f"## {stock_code} 主营构成（分产品/分业务）\n"]
        for period in periods[:2]:  # 最近2个报告期
            p_rows = [r for r in rows if r["period"] == period]
            summary.append(f"\n### {period}")
            for r in p_rows[:15]:  # 最多15条
                summary.append(
                    f"- {r['item']}: "
                    f"收入 {r['sales_yi']:.2f}亿, "
                    f"毛利率 {r['gross_margin_pct']:.1f}%"
                )

        return "\n".join(summary)

    except json.JSONDecodeError:
        return f"tushare 数据解析失败"
    except Exception as e:
        return f"tushare 异常: {str(e)}"


# ═══════════════════════════════════════════════
# Tool 3: Playwright 经营评述
# ═══════════════════════════════════════════════

def playwright_jyps(stock_code: str) -> str:
    """从东方财富 F10 抓取管理层经营评述原文。

    使用 headless Chromium 渲染 SPA 页面，提取年报中的管理层讨论与分析。

    Args:
        stock_code: 股票代码，如 300308

    Returns:
        经营评述原文（截取至 3000 字）
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Playwright 未安装。请运行: pip install playwright && python -m playwright install chromium"

    try:
        url = (
            f"https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html"
            f"?type=web&code={stock_code}&color=b#/jyfx/jyps"
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)

            # 点击"经营评述"标签
            try:
                page.click("text=经营评述", timeout=5000)
                page.wait_for_timeout(3000)
            except Exception:
                pass  # 可能已经在经营评述标签

            text = page.inner_text("body")
            browser.close()

        # 提取管理层讨论内容（长文本段落）
        lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 100]
        for line in lines:
            if len(line) > 500 and any(
                kw in line for kw in ["公司", "业务", "战略", "经营", "发展", "市场", "技术", "产品"]
            ):
                return f"[经营评述 {stock_code}]\n{line[:3000]}"

        return f"经营评述不完整 ({stock_code})，共 {len(lines)} 段长文本"

    except Exception as e:
        return f"Playwright 异常: {str(e)}"


# ═══════════════════════════════════════════════
# Tool Map & Definitions (OpenAI Function Calling 格式)
# ═══════════════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "bocha_search",
            "description": "搜索中文互联网信息（市场预期、估值、机构观点、行业数据、券商研报等）。返回网页标题、来源、日期和详细摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索查询语句。要具体，包含行业术语、公司名、产品名。例如 '中际旭创 800G光模块 市占率 2025' 比 '光模块行业' 更好",
                    },
                    "count": {
                        "type": "integer",
                        "description": "返回结果数，默认5，最大10",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "读取搜索结果中某条网页的全文正文。搜索返回的摘要信息不足时，传入URL获取完整内容（如公告原文、研报细节、具体数字）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "网页URL地址（从 bocha_search 返回结果中获取）",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tushare_segment",
            "description": "获取公司分产品/分业务的主营构成数据，含收入占比和毛利率，可跨报告期对比。用于了解公司收入结构和业务重心变化。",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {
                        "type": "string",
                        "description": "股票代码，如 300308（深交所）或 603738（上交所）",
                    }
                },
                "required": ["stock_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_jyps",
            "description": "从东方财富F10抓取管理层经营评述原文（年报中的管理层讨论与分析部分）。包含管理层的战略表述、业绩回顾和未来展望。",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_code": {
                        "type": "string",
                        "description": "股票代码，如 300308",
                    }
                },
                "required": ["stock_code"],
            },
        },
    },
]

TOOL_MAP = {
    "bocha_search": bocha_search,
    "fetch_url": fetch_url,
    "tushare_segment": tushare_segment,
    "playwright_jyps": playwright_jyps,
}
