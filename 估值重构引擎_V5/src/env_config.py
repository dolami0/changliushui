"""
环境变量与密钥集中管理 — V5

优先级: os.environ > .env 文件 > config.json fallback
"""

import json
import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

_CFG_FILE = Path(__file__).resolve().parent.parent / "valuation_app" / "config.json"
_cfg = {}
if _CFG_FILE.exists():
    with open(_CFG_FILE, encoding="utf-8") as f:
        _cfg = json.load(f)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY") or _cfg.get("deepseek_api_key", "")
if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY 未设置。请在 .env 或 config.json 中配置。")

COZE_SAT_TOKEN = os.environ.get("COZE_SAT_TOKEN") or _cfg.get("coze_sat_token", "")
INVESTODAY_API_KEY = os.environ.get("INVESTODAY_API_KEY") or _cfg.get("investoday_api_key", "")
VOLC_AGENT_KEY = os.environ.get("VOLC_AGENT_KEY", "")
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN") or _cfg.get("tushare_token", "")
