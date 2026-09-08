"""口令哈希（PBKDF2-HMAC-SHA256）与会话令牌（存库，可吊销）。"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, Header, HTTPException

from . import config
from .db import get_conn

_ITER = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITER)
    return "pbkdf2${}${}${}".format(_ITER, salt, dk.hex())


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, hexhash = stored.split("$", 3)
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), hexhash)
    except (ValueError, AttributeError):
        return False


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at)"
            " VALUES (?, ?, ?, ?)",
            (token, user_id, now.isoformat(timespec="seconds"),
             (now + timedelta(hours=config.SESSION_TTL_HOURS)).isoformat(timespec="seconds")),
        )
        # 顺手清理过期会话
        conn.execute("DELETE FROM sessions WHERE expires_at < ?",
                     (now.isoformat(timespec="seconds"),))
    return token


def drop_session(token: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def _user_from_token(token: str):
    if not token:
        return None
    row = get_conn().execute(
        "SELECT u.id, u.username, u.role, u.enabled"
        " FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token = ? AND s.expires_at > ?",
        (token, datetime.now().isoformat(timespec="seconds")),
    ).fetchone()
    return dict(row) if row else None


def current_user(authorization: str = Header(default="")):
    """FastAPI 依赖：Bearer 令牌 → 用户；无效/被禁用 → 401/403。"""
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    user = _user_from_token(token)
    if not user:
        raise HTTPException(401, "未登录或会话已过期")
    if not user["enabled"]:
        raise HTTPException(403, "账号已被禁用")
    user["token"] = token
    return user


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user
