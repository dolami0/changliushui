"""
N_gate [Code] 闸门
- N0校验未通过 → 跳过
- 非A股 → 跳过
- 市值 > 500亿 → 跳过
- 市值数据缺失 → 放行（不拦截）
"""

import re

async def main(args: Args) -> Output:
    code = args.params.get("verified_code", "")
    code_valid = args.params.get("is_valid", "true")
    raw = args.params.get("data_pack", "")

    # ── 0. N0校验拦截 ──
    if code_valid == "false":
        ret: Output = {
            "pass_gate": "false",
            "market_cap_yi": "0",
            "gate_msg": "N0校验未通过，跳过"
        }
        return ret

    # ── 1. 非A股判定 ──
    a_share = (
        len(code) == 6 and code.isdigit() and
        (code.startswith(("60", "00", "30", "68")))
    )

    if not a_share:
        ret: Output = {
            "pass_gate": "false",
            "market_cap_yi": "0",
            "gate_msg": f"非A股标的(code={code})，跳过"
        }
        return ret

    # ── 2. 市值判定 ──
    m = re.search(r'Market Cap:\s*([\d.]+)\s*yi', raw)
    if not m:
        # 市值数据缺失 — 不拦截。数据缺口不是大市值
        ret: Output = {
            "pass_gate": "true",
            "market_cap_yi": "0",
            "gate_msg": "市值数据缺失，放行"
        }
        return ret

    mcap = float(m.group(1))

    if mcap > 500:
        ret: Output = {
            "pass_gate": "false",
            "market_cap_yi": str(mcap),
            "gate_msg": f"市值{mcap:.0f}亿 > 500亿，跳过"
        }
    else:
        ret: Output = {
            "pass_gate": "true",
            "market_cap_yi": str(mcap),
            "gate_msg": f"市值{mcap:.0f}亿，继续"
        }
    return ret
