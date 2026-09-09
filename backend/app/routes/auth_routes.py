"""登录 / 登出 / 当前用户 / 改密。注册不开放，用户由管理员创建。"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import config
from ..db import get_conn
from ..oplog import log_op
from ..security import (create_session, current_user, drop_session,
                        hash_password, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public_user(u) -> dict:
    """对外用户对象：root = 种子管理员账号(用户名 = TS_ADMIN_USERNAME)；
    hidden = 隐藏 root 账号(前端据此显示日志菜单)。"""
    return {"id": u["id"], "username": u["username"], "role": u["role"],
            "root": u["username"] == config.ADMIN_USERNAME,
            "hidden": bool(u["hidden"])}


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePwdIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


@router.post("/login")
def login(body: LoginIn, request: Request):
    row = get_conn().execute(
        "SELECT id, username, password_hash, role, enabled, hidden FROM users"
        " WHERE username = ?",
        (body.username.strip(),),
    ).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "用户名或密码错误")
    if not row["enabled"]:
        raise HTTPException(403, "账号已被禁用，请联系管理员")
    token = create_session(row["id"])
    log_op(dict(row), "login",
           ip=request.client.host if request.client else "")
    return {"token": token, "user": _public_user(row)}


@router.post("/logout")
def logout(user=Depends(current_user)):
    drop_session(user["token"])
    log_op(user, "logout")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": _public_user(user)}


@router.post("/change-password")
def change_password(body: ChangePwdIn, user=Depends(current_user)):
    if not re.match(r"^\S+$", body.new_password):
        raise HTTPException(400, "新密码不能包含空白字符")
    conn = get_conn()
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?",
                       (user["id"],)).fetchone()
    if not verify_password(body.old_password, row["password_hash"]):
        raise HTTPException(400, "原密码错误")
    with conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (hash_password(body.new_password), user["id"]))
        # 改密后吊销本人其它会话（保留当前会话）
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token != ?",
                     (user["id"], user["token"]))
    return {"ok": True}
