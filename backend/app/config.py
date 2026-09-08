"""全局配置：均可用环境变量覆盖。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
DB_PATH = os.environ.get("TS_DB_PATH", os.path.join(BASE_DIR, "data", "screener.db"))

# 初始管理员（仅首次建库时写入；生产部署请用 TS_ADMIN_PASSWORD 覆盖并尽快改密）
ADMIN_USERNAME = os.environ.get("TS_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("TS_ADMIN_PASSWORD", "admin123")

# 会话有效期（小时）
SESSION_TTL_HOURS = int(os.environ.get("TS_SESSION_TTL_HOURS", "168"))  # 7 天

# 抓数：交易时段内间隔（分钟）；东财接口限流时指数退避
FETCH_INTERVAL_MIN = int(os.environ.get("TS_FETCH_INTERVAL_MIN", "3"))

# 本地开发时由 FastAPI 直接托管的前端目录（生产由 nginx 托管，不影响）
FRONTEND_DIR = os.environ.get(
    "TS_FRONTEND_DIR", os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))
)
