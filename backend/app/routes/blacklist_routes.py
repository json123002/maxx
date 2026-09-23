"""黑名单：列表 / 添加 / 删除。

按用户隔离存储（blacklist 表，user_id + code 主键），所有 /api/blacklist/*
需要登录。命中黑名单的股票由 /api/quote/list 在服务端直接剔除（不计入
total、不出现在行内）；设置页提供管理入口，移除后下次查询即恢复。
"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import get_conn
from ..oplog import client_ip, log_op, user_agent
from ..security import current_user

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])

CODE_RE = re.compile(r"^\d{6}$")


class AddIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@router.get("")
def black_list(user=Depends(current_user)):
    """我的黑名单（按加入时间倒序）。"""
    rows = get_conn().execute(
        "SELECT code, name, created_at FROM blacklist"
        " WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return {"rows": [dict(r) for r in rows]}


@router.post("")
def black_add(body: AddIn, request: Request, user=Depends(current_user)):
    """加入黑名单：code 必须存在于行情快照（防脏数据）；重复添加幂等。"""
    code = body.code.strip()
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    conn = get_conn()
    row = conn.execute(
        "SELECT code, name FROM latest WHERE code = ?", (code,)).fetchone()
    if not row:
        raise HTTPException(404, "未找到该股票（可能已退市或代码有误）")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO blacklist (user_id, code, name, created_at)"
            " VALUES (?, ?, ?, ?)",
            (user["id"], code, row["name"],
             datetime.now().isoformat(timespec="seconds")))
    log_op(user, "blacklist_add", "%s %s" % (code, row["name"]),
           client_ip(request), user_agent(request))
    return {"ok": True, "code": code, "name": row["name"]}


@router.delete("/{code}")
def black_remove(code: str, request: Request, user=Depends(current_user)):
    """移出黑名单（不存在也算成功，幂等）。移除后下次查询恢复显示。"""
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM blacklist WHERE user_id = ? AND code = ?",
            (user["id"], code))
    log_op(user, "blacklist_remove", code,
           client_ip(request), user_agent(request))
    return {"ok": True}
