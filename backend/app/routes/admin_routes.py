"""管理员用户管理：列表 / 新增 / 启停 / 重置密码 / 删除。

权限模型（不设独立 super 角色）：
- 种子账号（用户名 = TS_ADMIN_USERNAME，默认 admin）即 root，拥有全部权限；
  root 账号不可被任何人通过管理接口修改/删除（自己改密走 /api/auth/change-password）。
- 隐藏 root 账号（hidden=1，用户名 = TS_ROOT_USERNAME）：对所有人（含种子 root）
  不出现在用户列表，管理接口触碰一律 404（不暴露其存在）。
- 其他 role=admin 的管理员：可创建和管理普通用户；不能创建管理员、
  不能动 root、不能动其他管理员。
- role=user 的普通用户：无管理权限。
"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..db import get_conn
from ..oplog import log_op
from ..security import hash_password, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_@.\-]{2,32}$")


class CreateUserIn(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    role: str = "user"


class UpdateUserIn(BaseModel):
    enabled: bool | None = None
    role: str | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)


def _is_root(user) -> bool:
    return user["username"] == config.ADMIN_USERNAME


def _public(user_dict) -> dict:
    """对外用户对象：附带 root 标记,前端据此做权限 UI。"""
    return {**user_dict, "root": _is_root(user_dict)}


def _validate_role(role: str) -> str:
    if role not in ("admin", "user"):
        raise HTTPException(400, "role 只能是 admin 或 user")
    return role


def _get_user(user_id: int):
    row = get_conn().execute(
        "SELECT id, username, role, hidden FROM users WHERE id = ?",
        (user_id,)).fetchone()
    if not row or row["hidden"]:
        # 隐藏 root:管理接口视角下等同于不存在
        raise HTTPException(404, "用户不存在")
    return dict(row)


def _check_not_root(target) -> None:
    """root 账号不可通过管理接口被任何人触碰(最高优先级)。"""
    if _is_root(target):
        raise HTTPException(403, "无权修改超级管理员账号")


def _check_admin_scope(caller, target, new_role: str | None = None) -> None:
    """非 root 管理员的作用域:只能管理普通用户,且不能授予 admin。"""
    if _is_root(caller):
        return
    if target["role"] != "user":
        raise HTTPException(403, "管理员只能管理普通用户")
    if new_role == "admin":
        raise HTTPException(403, "仅超级管理员可授予管理员权限")


@router.get("/users")
def list_users(admin=Depends(require_admin)):
    rows = get_conn().execute(
        "SELECT id, username, role, enabled, created_at FROM users"
        " WHERE hidden = 0 ORDER BY id"
    ).fetchall()
    users = [_public(dict(r)) for r in rows]
    # 非 root 管理员看不到 root 账号
    if not _is_root(admin):
        users = [u for u in users if not u["root"]]
    return {"users": users}


@router.post("/users", status_code=201)
def create_user(body: CreateUserIn, admin=Depends(require_admin)):
    username = body.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(400, "用户名仅限字母数字及 _ @ . -，长度 2-32")
    _validate_role(body.role)
    if username in (config.ADMIN_USERNAME, config.ROOT_USERNAME):
        raise HTTPException(409, "用户名已存在")
    if body.role == "admin" and not _is_root(admin):
        raise HTTPException(403, "仅超级管理员可创建管理员")
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, role, enabled, created_at)"
                " VALUES (?, ?, ?, 1, ?)",
                (username, hash_password(body.password), body.role,
                 datetime.now().isoformat(timespec="seconds")),
            )
    except Exception:
        raise HTTPException(409, "用户名已存在")
    log_op(admin, "admin_create_user", "%s(%s)" % (username, body.role))
    return {"id": cur.lastrowid, "username": username, "role": body.role}


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UpdateUserIn, admin=Depends(require_admin)):
    target = _get_user(user_id)
    _check_not_root(target)                       # root 账号优先拦截
    if body.enabled is not None and user_id == admin["id"] and not body.enabled:
        raise HTTPException(400, "不能禁用自己的账号")
    if body.role is not None and user_id == admin["id"] and body.role != "admin":
        raise HTTPException(400, "不能取消自己的管理员权限")
    _check_admin_scope(admin, target, body.role)
    sets, params = [], []
    if body.enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if body.enabled else 0)
    if body.role is not None:
        sets.append("role = ?")
        params.append(_validate_role(body.role))
    if body.password is not None:
        sets.append("password_hash = ?")
        params.append(hash_password(body.password))
    if not sets:
        raise HTTPException(400, "没有需要更新的字段")
    conn = get_conn()
    with conn:
        conn.execute("UPDATE users SET " + ", ".join(sets) + " WHERE id = ?",
                     (*params, user_id))
        if body.enabled is False or body.password is not None:
            # 禁用或重置密码后立即吊销该用户所有会话
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    changes = ",".join(f.replace("password_hash", "password")
                       for f in sets)
    log_op(admin, "admin_update_user", "%s: %s" % (target["username"], changes))
    return {"ok": True}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, admin=Depends(require_admin)):
    if user_id == admin["id"]:
        raise HTTPException(400, "不能删除自己的账号")
    target = _get_user(user_id)
    _check_not_root(target)
    _check_admin_scope(admin, target)
    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    log_op(admin, "admin_delete_user", target["username"])
    return {"ok": True}
