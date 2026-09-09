"""用户操作埋点：服务端关键动作自动记录 + 前端行为主动上报（/api/track）。"""
from datetime import datetime

from .db import get_conn


def log_op(user, action: str, detail: str = "", ip: str = "") -> None:
    """写一条操作日志。埋点绝不能影响业务：任何失败都静默吞掉。"""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO op_logs (ts, user_id, username, action, detail, ip)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"),
                 user.get("id"), user.get("username"), action,
                 (detail or "")[:300], ip or ""),
            )
    except Exception:
        pass
