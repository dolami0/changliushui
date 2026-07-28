"""配置常量 — 从 env_config 读取密钥"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_config import DEEPSEEK_API_KEY, COZE_SAT_TOKEN, VOLC_AGENT_KEY, TUSHARE_TOKEN

import os
BOCHA_KEY = os.environ.get("BOCHA_KEY", "sk-090c432b4f5745caa8767ae70f5b348b")

# DeepSeek
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"

# Kimi (Moonshot) — Kimi For Coding 订阅套餐
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "sk-kimi-lQupxU1ZGzdieUBPu9q2b3nOJYvaPcQ6QxlKYPaV3Fbt2Sldqmjh5YNEQH9gdYu2")
KIMI_URL = "https://api.kimi.com/coding/v1/chat/completions"
KIMI_MODEL = "k3"

# 火山 Agent
VOLC_URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
VOLC_BOT_ID = "7640524154441156122"

# Coze DB
COZE_BASE = "https://api.coze.cn/v1/databases"
DB_TIANJIJUAN = "7479116110479048754"
DB_WANYEPU = "7639784337973477386"
