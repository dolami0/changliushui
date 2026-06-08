"""将追踪 JSON 同步到 Coze 云数据库 7645332166129287218"""
import json, os, sys, urllib.request, urllib.error

COZE_TOKEN = "sat_UxIpTimxUFwh0BGedY1yxK7YJbqrqryebdRVyt8AjducYxsH8cFkkso6Orh2RTGc"
DB_ID = "7645332166129287218"
BASE_URL = f"https://api.coze.cn/v1/databases/{DB_ID}"

def api(method, path, body=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {COZE_TOKEN}")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        print(f"API error {e.code}: {body}", file=sys.stderr)
        return None

def find_record(stock_code):
    result = api("POST", "/records/query", {
        "page_size": 1,
        "filter": {
            "logic": "and",
            "conditions": [{"left": "stock_code", "operation": "equal", "right": stock_code}]
        }
    })
    items = (result or {}).get("data", {}).get("items", [])
    return items[0] if items else None

def upsert(tracking_file):
    with open(tracking_file, "r", encoding="utf-8") as f:
        d = json.load(f)

    stock_code = d["stockCode"]

    # ⚠️ Coze update_fields 的 value 必须全部是字符串
    def s(v):
        if v is None: return ""
        if isinstance(v, bool): return "true" if v else "false"
        if isinstance(v, (int, float)): return str(v)
        return str(v)

    update_fields = [
        {"field_name": "stock_code",         "value": s(d.get("stockCode"))},
        {"field_name": "stock_name",         "value": s(d.get("stockName"))},
        {"field_name": "track_status",      "value": s(d.get("track_status", "active"))},
        {"field_name": "conviction",         "value": s(d.get("conviction", 0))},
        {"field_name": "decision",           "value": s(d.get("decision", ""))},
        {"field_name": "decision_date",      "value": s(d.get("decisionDate", ""))},
        {"field_name": "thesis",             "value": s(d.get("thesis", ""))},
        {"field_name": "entry_condition",    "value": s(d.get("entryCondition", ""))},
        {"field_name": "recommended_position","value": s(d.get("recommendedPosition", 0))},
        {"field_name": "base_price",         "value": s(d.get("basePrice") or 0)},
        {"field_name": "base_market_cap",    "value": s(d.get("baseMarketCap", 0))},
        {"field_name": "base_date",          "value": s(d.get("baseDate", ""))},
        {"field_name": "file_name",          "value": s(os.path.basename(tracking_file))},
        {"field_name": "pillars_json",       "value": s(json.dumps(d.get("pillars", []), ensure_ascii=False))},
        {"field_name": "risks_json",         "value": s(json.dumps(d.get("risks", []), ensure_ascii=False))},
        {"field_name": "catalyst_json",      "value": s(json.dumps(d.get("catalystCalendar", []), ensure_ascii=False))},
        {"field_name": "thesis_log_json",    "value": s(json.dumps(d.get("thesisLog", []), ensure_ascii=False))},
        {"field_name": "price_log_json",     "value": s(json.dumps(d.get("priceLog", []), ensure_ascii=False))},
        {"field_name": "meta_json",          "value": s(json.dumps({
            "exit_conditions": d.get("exitConditions", []),
            "a_share_tracking": d.get("aShareTracking", {}),
            "review_schedule": d.get("reviewSchedule", {}),
        }, ensure_ascii=False))},
    ]

    existing = find_record(stock_code)

    if existing:
        result = api("PUT", "/records", {
            "update_fields": update_fields,
            "filter": {
                "logic": "and",
                "conditions": [{"left": "stock_code", "operation": "equal", "right": stock_code}]
            }
        })
        action = "updated"
    else:
        fields = {f["field_name"]: f["value"] for f in update_fields}
        result = api("POST", "/records", {"insert_rows": [fields]})
        action = "created"

    if result and result.get("code") == 0:
        affected = (result.get("data") or {}).get("affected_rows", "?")
        print(f"[Coze OK] {stock_code} {d.get('stockName','')} {action} | rows={affected} | conviction={d.get('conviction','?')}")
    else:
        err = (result or {}).get("msg", "unknown")
        print(f"[Coze FAIL] {stock_code} {err}", file=sys.stderr)
        return False
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sync_coze.py <tracking_json_file>")
        sys.exit(1)
    ok = upsert(sys.argv[1])
    sys.exit(0 if ok else 1)
