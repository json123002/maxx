"""登录 / 登出 / 当前用户 / 改密。注册不开放，用户由管理员创建。"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .. import config
from ..db import get_conn
from ..oplog import client_ip, log_op, user_agent
from ..security import (create_session, current_user, drop_session,
                        hash_password, verify_password)

router = APIRouter(prefix="/api/auth", tags=["auth"])

def _public_user(u) -> dict:
    """对外用户对象：root = 种子管理员账号(用户名 = TS_ADMIN_USERNAME)；
    hidden = 隐藏 root 账号(前端据此显示日志菜单)；
    risk_ack = 是否已确认风险声明(前端据此弹强制确认窗)。"""
    return {"id": u["id"], "username": u["username"], "role": u["role"],
            "root": u["username"] == config.ADMIN_USERNAME,
            "hidden": bool(u["hidden"]),
            "risk_ack": bool(u["risk_ack_at"])}


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePwdIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


@router.post("/login")
def login(body: LoginIn, request: Request):
    ip = client_ip(request)
    ua = user_agent(request)
    username = body.username.strip()
    row = get_conn().execute(
        "SELECT id, username, password_hash, role, enabled, hidden, risk_ack_at"
        " FROM users"
        " WHERE username = ?",
        (username,),
    ).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        # 登录失败也记录(暴力破解/输错密码是重要安全信号)
        log_op({"id": None, "username": username},
               "login_fail", "用户名或密码错误", ip, ua)
        raise HTTPException(401, "用户名或密码错误")
    if not row["enabled"]:
        log_op(dict(row), "login_fail", "账号已禁用", ip, ua)
        raise HTTPException(403, "账号已被禁用，请联系管理员")
    token = create_session(row["id"])
    log_op(dict(row), "login", "", ip, ua)
    return {"token": token, "user": _public_user(row)}


@router.post("/logout")
def logout(request: Request, user=Depends(current_user)):
    drop_session(user["token"])
    log_op(user, "logout", "", client_ip(request), user_agent(request))
    return {"ok": True}


@router.post("/risk-ack")
def risk_ack(request: Request, user=Depends(current_user)):
    """确认风险声明：记录确认时间（首次确认即留痕，重复调用幂等）。"""
    conn = get_conn()
    now = datetime.now().isoformat(timespec="seconds")
    with conn:
        conn.execute("UPDATE users SET risk_ack_at = ?"
                     " WHERE id = ? AND risk_ack_at IS NULL",
                     (now, user["id"]))
    log_op(user, "risk_ack", "确认风险声明", client_ip(request), user_agent(request))
    return {"ok": True, "risk_ack_at": now}


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": _public_user(user)}


@router.post("/change-password")
def change_password(body: ChangePwdIn, request: Request,
                    user=Depends(current_user)):
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
    # 改密属安全敏感操作,与登录/登出同口径记录(不记密码本身)
    log_op(user, "change_password", "改密并吊销其它会话",
           client_ip(request), user_agent(request))
    return {"ok": True}
