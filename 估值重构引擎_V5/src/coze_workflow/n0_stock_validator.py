"""
N0 [Code] 股票校验节点
======================
管道入口: 校验 stock_name/stock_code, 缺失时补全, 无效时拦截。

输入变量: stock_name (String), stock_code (String)
输出变量: verified_name, verified_code, stock_market, is_valid, n0_error
"""

import re
import requests_async


# ═══════════════════════════════════════════
# 1. 代码验证: 东方财富行情API (免费/无需认证)
# ═══════════════════════════════════════════

async def verify_by_code(market, code):
    """
    market: "0"=深证, "1"=上证
    code: 6位数字如 "300308"
    返回: (名称, 代码) 或 (None, None)
    """
    try:
        r = await requests_async.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={"fields": "f57,f58", "secid": f"{market}.{code}"},
            timeout=8
        )
        data = r.json()
        d = data.get("data")
        if d and d.get("f58"):
            return d["f58"], d["f57"]
    except Exception:
        pass
    return None, None


# ═══════════════════════════════════════════
# 2. 名称搜索: 新浪 suggest API (免费/无认证, GBK编码)
# ═══════════════════════════════════════════

async def search_by_name(keyword):
    """
    新浪股票搜索: 用名称模糊搜代码
    返回: (名称, 代码, 市场) 或 (None, None, None)
    市场: "sz"=深证, "sh"=上证
    """
    try:
        r = await requests_async.get(
            "https://suggest3.sinajs.cn/suggest/type=11",
            params={"key": keyword},
            headers={
                "Referer": "https://finance.sina.com.cn",
                "User-Agent": "Mozilla/5.0"
            },
            timeout=8
        )
        # 新浪返回 GBK 编码
        r.encoding = "gbk"
        text = r.text

        # 格式: var suggestvalue="关键词,11,代码,sz300308,名称,,名称,99,1";
        # 多条用 ; 分隔
        if "suggestvalue" not in text:
            return None, None, None

        # 提取引号内内容
        match = re.search(r'"([^"]*)"', text)
        if not match:
            return None, None, None

        # 取第一条结果 (分号分隔多结果)
        first = match.group(1).split(";")[0]
        parts = first.split(",")

        if len(parts) >= 5:
            name = parts[4]       # 股票名称
            code = parts[2]       # 6位代码
            prefix = parts[3]     # sz300308 或 sh600xxx

            if len(code) == 6:
                market = "0" if prefix.startswith("sz") else "1"
                return name, code, market
    except Exception:
        pass
    return None, None, None


# ═══════════════════════════════════════════
# 3. 名称模糊匹配
# ═══════════════════════════════════════════

def name_fuzzy_match(a, b):
    """去空格/ST标记/字母后互相包含即匹配"""
    def clean(s):
        return re.sub(r'[\s*STＡ-Ｚa-z0-9]', '', s)
    ca, cb = clean(a), clean(b)
    return (ca in cb) or (cb in ca) or (ca == cb)


# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════

async def main(args: Args) -> Output:
    # ── 获取输入 ──
    params = args.params
    name_in = str(params.get('stock_name', '') or '').strip()
    code_in = str(params.get('stock_code', '') or '').strip()

    # ── 清洗 ──
    name_clean = re.sub(r'\([^)]*\)', '', name_in).strip()   # 去括号后缀
    code_clean = re.sub(r'[^0-9]', '', code_in)              # 只留数字

    verified_name = name_clean or name_in
    verified_code = code_clean
    stock_market = ""
    is_valid = False
    error_msg = ""

    # ── 校验 ──
    if not name_clean and not code_clean:
        error_msg = "stock_name和stock_code均为空"

    elif code_clean and len(code_clean) == 6:
        # ===== 场景A: 有代码 → 用行情API验证 =====
        primary_market = "1" if code_clean.startswith("60") else "0"

        api_name, api_code = await verify_by_code(primary_market, code_clean)

        if api_name and api_code:
            if name_clean and not name_fuzzy_match(name_clean, api_name):
                error_msg = f"名称不匹配: 输入'{name_clean}', API查得'{api_name}'({api_code})"
                verified_name = api_name
                verified_code = api_code
                stock_market = "SH" if primary_market == "1" else "SZ"
            else:
                verified_name = api_name
                verified_code = api_code
                stock_market = "SH" if primary_market == "1" else "SZ"
                is_valid = True
        else:
            # 主市场没找到, 试另一市场
            alt_market = "0" if primary_market == "1" else "1"
            api_name, api_code = await verify_by_code(alt_market, code_clean)
            if api_name:
                if name_clean and not name_fuzzy_match(name_clean, api_name):
                    error_msg = f"名称不匹配: 输入'{name_clean}', API查得'{api_name}'({api_code})"
                else:
                    verified_name = api_name
                    verified_code = api_code
                    stock_market = "SH" if alt_market == "1" else "SZ"
                    is_valid = True
            else:
                error_msg = f"代码'{code_clean}'在沪深两市均未找到"

    elif name_clean:
        # ===== 场景B: 只有名称 → 用新浪API搜索 =====
        api_name, api_code, market = await search_by_name(name_clean)
        if api_name and api_code:
            verified_name = api_name
            verified_code = api_code
            stock_market = "SH" if market == "1" else "SZ"
            is_valid = True
        else:
            error_msg = f"名称'{name_clean}'未匹配到A股标的"
    else:
        error_msg = f"代码格式异常: '{code_in}'"

    # ── 输出 ──
    ret: Output = {
        "verified_name": verified_name,
        "verified_code": verified_code,
        "stock_market": stock_market,
        "is_valid": "true" if is_valid else "false",
        "n0_error": error_msg
    }
    return ret
