"""全局配置：均可用环境变量覆盖。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
DB_PATH = os.environ.get("TS_DB_PATH", os.path.join(BASE_DIR, "data", "screener.db"))

# 初始管理员（仅首次建库时写入；生产部署请用 TS_ADMIN_PASSWORD 覆盖并尽快改密）
ADMIN_USERNAME = os.environ.get("TS_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("TS_ADMIN_PASSWORD", "admin123")

# 隐藏 root 账号：拥有全部权限，但对所有人（含 admin）不出现在用户管理列表，
# 独享 /api/logs 操作日志。密码【不落在代码里】：仅当环境变量 TS_ROOT_PASSWORD
# 存在时才创建该账号（生产由 /etc/turnover-screener.env 注入，见 deploy.py）。
# 未设置时跳过创建；账号已存在则不受影响（之后可在页面「修改密码」改密）。
ROOT_USERNAME = os.environ.get("TS_ROOT_USERNAME", "root")
ROOT_PASSWORD = os.environ.get("TS_ROOT_PASSWORD", "")

# 会话有效期（小时）
SESSION_TTL_HOURS = int(os.environ.get("TS_SESSION_TTL_HOURS", "168"))  # 7 天

# 抓数：交易时段内间隔（分钟）；东财接口限流时指数退避
FETCH_INTERVAL_MIN = int(os.environ.get("TS_FETCH_INTERVAL_MIN", "3"))

# 每日维护：操作日志保留天数 / 数据库备份保留份数
LOG_RETENTION_DAYS = int(os.environ.get("TS_LOG_RETENTION_DAYS", "180"))
BACKUP_KEEP = int(os.environ.get("TS_BACKUP_KEEP", "14"))

# 本地开发时由 FastAPI 直接托管的前端目录（生产由 nginx 托管，不影响）
FRONTEND_DIR = os.environ.get(
    "TS_FRONTEND_DIR", os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))
)
