"""N0: 股票代码验证 — Tushare Pro

用 Tushare stock_basic API 做股票名称→代码的双向查证。
单一权威数据源，不再依赖新浪。
"""

import re
import requests

from .config import TUSHARE_TOKEN

TUSHARE_URL = "https://api.tushare.pro"

# A股主板前缀
MAIN_BOARD_PREFIXES = ("60", "00")
# 含科创/创业板（也属于 A 股范畴）
A_SHARE_PREFIXES = ("60", "00", "68", "30")


def _call_tushare(api_name: str, params: dict, fields: str) -> list[dict]:
    """调用 Tushare API，返回 records 列表。"""
    try:
        r = requests.post(TUSHARE_URL, json={
            "api_name": api_name,
            "token": TUSHARE_TOKEN,
            "params": params,
            "fields": fields,
        }, timeout=15)
        data = r.json()
        if data.get("code") != 0:
            return []
        items = data.get("data", {}).get("items", [])
        fields_list = data.get("data", {}).get("fields", [])
        return [dict(zip(fields_list, row)) for row in items]
    except Exception:
        return []


def _lookup_by_name(name: str) -> dict | None:
    """按股票名称查 Tushare stock_basic，返回第一条记录。"""
    rows = _call_tushare(
        "stock_basic",
        {"name": name, "list_status": "L"},
        "ts_code,symbol,name,market,list_date",
    )
    return rows[0] if rows else None


def _lookup_by_code(code: str) -> dict | None:
    """按 6 位代码查 Tushare stock_basic。"""
    # Tushare 需要 ts_code 格式（如 688371.SH/000001.SZ）
    if code.startswith(("60", "68")):
        ts_code = f"{code}.SH"
    else:
        ts_code = f"{code}.SZ"

    rows = _call_tushare(
        "stock_basic",
        {"ts_code": ts_code, "list_status": "L"},
        "ts_code,symbol,name,market,list_date",
    )
    return rows[0] if rows else None


def validate_stock(stock_name: str = "", stock_code: str = "") -> dict:
    """用 Tushare 验证股票名称/代码。

    Args:
        stock_name: 股票名称（可为空）
        stock_code: 股票代码（可为空）

    Returns:
        {
            "is_valid": bool,
            "verified_name": str,
            "verified_code": str,
            "stock_market": str,   # "主板" / "科创板" / "创业板" / "北交所"
            "error": str,
        }
    """
    name_clean = re.sub(r"\([^)]*\)", "", stock_name).strip()
    code_clean = re.sub(r"[^0-9]", "", stock_code)

    # ── 路径1: 有代码 → 用代码查证 ──
    if code_clean and len(code_clean) == 6:
        row = _lookup_by_code(code_clean)
        if not row:
            return {
                "is_valid": False,
                "verified_name": name_clean,
                "verified_code": code_clean,
                "stock_market": "",
                "error": f"代码 '{code_clean}' 在 Tushare 中未找到",
            }

        ts_name = row["name"]
        if name_clean and not _fuzzy_match(name_clean, ts_name):
            return {
                "is_valid": False,
                "verified_name": ts_name,
                "verified_code": row["symbol"],
                "stock_market": row["market"],
                "error": f"名称不匹配: 输入 '{name_clean}', Tushare 查得 '{ts_name}' ({row['symbol']})",
            }

        return {
            "is_valid": True,
            "verified_name": ts_name,
            "verified_code": row["symbol"],
            "stock_market": row["market"],
            "error": "",
        }

    # ── 路径2: 无代码，只有名称 → 按名称查证 ──
    if name_clean:
        row = _lookup_by_name(name_clean)
        if not row:
            return {
                "is_valid": False,
                "verified_name": name_clean,
                "verified_code": "",
                "stock_market": "",
                "error": f"名称 '{name_clean}' 在 Tushare 中未找到",
            }

        if not _fuzzy_match(name_clean, row["name"]):
            return {
                "is_valid": False,
                "verified_name": row["name"],
                "verified_code": row["symbol"],
                "stock_market": row["market"],
                "error": f"名称不匹配: 输入 '{name_clean}', Tushare 查得 '{row['name']}' ({row['symbol']})",
            }

        return {
            "is_valid": True,
            "verified_name": row["name"],
            "verified_code": row["symbol"],
            "stock_market": row["market"],
            "error": "",
        }

    # ── 都为空 ──
    return {
        "is_valid": False,
        "verified_name": "",
        "verified_code": "",
        "stock_market": "",
        "error": "stock_name 和 stock_code 均为空",
    }


def _fuzzy_match(a: str, b: str) -> bool:
    """去空格/ST 标记/字母后互相包含即匹配。"""
    def clean(s):
        return re.sub(r"[\s*STＡ-Ｚa-z0-9]", "", s)
    ca, cb = clean(a), clean(b)
    return (ca in cb) or (cb in ca) or (ca == cb)
