"""
N_vdc [Code] DC数据校验 + 补采
- 检查 data_pack 关键段落是否齐全
- 缺 Market Data / Revenue Breakdown → 补采Tushare, 最多2次
- 缺其他段落 → 标记但不阻塞
"""

import requests_async
import asyncio
import re

TUSHARE_TOKEN = "aab25ecdb29ca0db9964413e9e6cdb29c92d6d15b6a419705889eae9"
TUSHARE_URL = "https://api.tushare.pro"


def to_ts_code(code):
    if code.startswith(("60", "68")):
        return f"{code}.SH"
    elif code.startswith("8"):
        return f"{code}.BJ"
    else:
        return f"{code}.SZ"


async def call(api_name, params, fields, retries=3):
    for attempt in range(retries):
        try:
            r = await requests_async.post(TUSHARE_URL, json={
                "api_name": api_name,
                "token": TUSHARE_TOKEN,
                "params": params,
                "fields": fields
            }, timeout=15)
            data = r.json()
            if data.get("code") == 0:
                flist = data["data"]["fields"]
                items = data["data"]["items"]
                return flist, items
            if data.get("code") == 40204 and attempt < retries - 1:
                await asyncio.sleep(1.0)
                continue
        except Exception:
            if attempt < retries - 1:
                await asyncio.sleep(1.0)
                continue
    return [], []


def fval(row, name, flist):
    v = row[flist.index(name)] if name in flist else None
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def fmt(v, decimals=2):
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f}"


def fmt_pct(v, decimals=1):
    if v is None:
        return "N/A"
    return f"{round(v, decimals)}%"


MISSING_MARKET = "## Market Data"
MISSING_REVENUE = "## Revenue Breakdown"


async def main(args: Args) -> Output:
    code = args.params.get("verified_code", "")
    raw = args.params.get("data_pack", "")
    retry_count = int(args.params.get("dc_retry", "0") or "0")

    missing = []
    if MISSING_MARKET not in raw:
        missing.append("Market Data")
    if MISSING_REVENUE not in raw:
        missing.append("Revenue Breakdown")

    # 不缺 → 直接放行
    if not missing:
        ret: Output = {
            "data_pack": raw,
            "dc_retry": str(retry_count),
            "gate_msg": "数据完整",
        }
        return ret

    # 已重试2次 → 放弃，放行（标记）
    if retry_count >= 2:
        ret: Output = {
            "data_pack": raw,
            "dc_retry": str(retry_count),
            "gate_msg": f"补采{retry_count}次后仍缺: {', '.join(missing)}，放行",
        }
        return ret

    # ── 补采 ──
    ts_code = to_ts_code(code)
    append_lines = []

    if "Market Data" in missing:
        f_daily, d_daily = await call("daily_basic",
            {"ts_code": ts_code, "limit": "250"},
            "trade_date,close,pe_ttm,pb,total_mv,turnover_rate")
        if d_daily:
            r = d_daily[0]
            date = str(r[f_daily.index("trade_date")] if "trade_date" in f_daily else "")
            close = fval(r, "close", f_daily)
            pe_val = fval(r, "pe_ttm", f_daily)
            pb_val = fval(r, "pb", f_daily)
            mv_raw = fval(r, "total_mv", f_daily)
            mv = round(mv_raw / 10000, 2) if mv_raw else None
            tr = fval(r, "turnover_rate", f_daily)
            closes = [fval(d, "close", f_daily) for d in d_daily if fval(d, "close", f_daily)]
            vols = [fval(d, "turnover_rate", f_daily) for d in d_daily if fval(d, "turnover_rate", f_daily)]
            yh = max(closes) if closes else None
            yl = min(closes) if closes else None
            append_lines.append(f"\n## Market Data ({date}) [补采-第{retry_count+1}次]")
            append_lines.append(f"- Close: {fmt(close)} | PE: {fmt(pe_val, 1)} | PB: {fmt(pb_val, 1)}")
            append_lines.append(f"- Market Cap: {fmt(mv, 2)} yi")
            append_lines.append(f"- Year High: {fmt(yh)} | Year Low: {fmt(yl)}")
            append_lines.append(f"- Turnover Rate: {fmt_pct(tr)} | 3M Avg Turnover: {fmt_pct(round(sum(vols[-60:]) / min(60, len(vols[-60:])), 2) if vols else None)}")

    if "Revenue Breakdown" in missing:
        f_mbz, d_mbz = await call("fina_mainbz",
            {"ts_code": ts_code, "type": "P", "limit": "30"},
            "end_date,bz_item,bz_sales,bz_profit,bz_cost")
        if d_mbz:
            mbz_periods = {}
            for row in d_mbz:
                dt = str(row[f_mbz.index("end_date")] if "end_date" in f_mbz else "")
                if dt not in mbz_periods:
                    mbz_periods[dt] = []
                mbz_periods[dt].append(row)

            fy_dates = sorted([d for d in mbz_periods if d.endswith("1231")], reverse=True)
            cur_fy = fy_dates[0] if fy_dates else None
            prev_fy = fy_dates[1] if len(fy_dates) > 1 else None

            if cur_fy and cur_fy in mbz_periods:
                cur_rows = mbz_periods[cur_fy]
                cur_total = sum(fval(r, "bz_sales", f_mbz) or 0 for r in cur_rows)
                append_lines.append(f"\n## Revenue Breakdown ({cur_fy}) [补采-第{retry_count+1}次]")
                cur_rows.sort(key=lambda r: fval(r, "bz_sales", f_mbz) or 0, reverse=True)

                for r in cur_rows:
                    item = str(r[f_mbz.index("bz_item")] if "bz_item" in f_mbz else "N/A")
                    sales = (fval(r, "bz_sales", f_mbz) or 0) / 1e8
                    profit = (fval(r, "bz_profit", f_mbz) or 0) / 1e8
                    ratio = (fval(r, "bz_sales", f_mbz) or 0) / cur_total * 100 if cur_total else 0
                    gm = (fval(r, "bz_profit", f_mbz) or 0) / (fval(r, "bz_sales", f_mbz) or 1) * 100
                    parts = [f"- {item}: {fmt(sales)} yi ({fmt_pct(ratio)} of revenue)"]
                    if gm > 0:
                        parts.append(f", GM={fmt_pct(gm)}")
                    if profit:
                        parts.append(f", profit={fmt(profit)} yi")
                    append_lines.append("".join(parts))

                if prev_fy and prev_fy in mbz_periods:
                    prev_rows = mbz_periods[prev_fy]
                    prev_map = {}
                    for r in prev_rows:
                        it = str(r[f_mbz.index("bz_item")] if "bz_item" in f_mbz else "")
                        prev_map[it] = fval(r, "bz_sales", f_mbz) or 0
                    append_lines.append(f"\n## Revenue YoY ({prev_fy} -> {cur_fy})")
                    for r in cur_rows:
                        it = str(r[f_mbz.index("bz_item")] if "bz_item" in f_mbz else "N/A")
                        cur_s = fval(r, "bz_sales", f_mbz) or 0
                        prev_s = prev_map.get(it)
                        if prev_s and prev_s > 0:
                            append_lines.append(f"- {it}: {fmt_pct((cur_s / prev_s - 1) * 100)}")
                        else:
                            append_lines.append(f"- {it}: new segment")

    if append_lines:
        raw += "\n".join(append_lines)

    ret: Output = {
        "data_pack": raw,
        "dc_retry": str(retry_count + 1),
        "gate_msg": f"补采第{retry_count+1}次: {' '.join(missing)}",
    }
    return ret
