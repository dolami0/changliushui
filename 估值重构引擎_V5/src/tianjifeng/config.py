"""天机峰配置常量"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_config import DEEPSEEK_API_KEY, COZE_SAT_TOKEN, VOLC_AGENT_KEY  # noqa: F401

# DeepSeek
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_MODEL_PRO = "deepseek-v4-flash"  # 降级为 flash（pro 涨价，筛选环节不必要）

# 火山 Agent
VOLC_URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
VOLC_BOT_ID = "7640524154441156122"

# Coze DB
COZE_BASE = "https://api.coze.cn/v1/databases"
DB_TIANJIJUAN = "7479116110479048754"
DB_NEWS_POOL = "7668348021729476646"  # 天机峰快讯池中间表
DB_YANBAO = "7631166750289051675"  # 研报表（棱镜内参）

# 快讯来源（东方财富 7×24，无需认证）
THS_FLASHNEWS_URL = ""  # 已弃用，保留占位
THS_TAGS = ["A股"]  # 东方财富不分板块，保留兼容

# 轮询默认参数
DEFAULT_POLL_INTERVAL_SEC = 600
DEFAULT_YANBAO_INTERVAL_SEC = 600  # 研报管线轮询间隔
DEFAULT_MAX_NEWS_PER_CYCLE = 20
DEFAULT_MAX_YANBAO_PER_CYCLE = 30  # 研报单轮最多处理 30 条
DEFAULT_FULL_WRITE_LEVEL = 4
