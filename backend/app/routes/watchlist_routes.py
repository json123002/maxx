"""自选股：列表 / 添加 / 删除 / 搜索。

按用户隔离存储（watchlist 表，user_id + code 主键），所有 /api/watchlist/*
需要登录。列表和搜索都关联 latest 快照返回实时行情字段（f2/f3/f8...），
与前端筛选页渲染逻辑一致。
"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import get_conn
from ..oplog import log_op
from ..security import current_user

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

CODE_RE = re.compile(r"^\d{6}$")


class AddIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


def _fkey_row(r, added: bool = True, created_at: str | None = None) -> dict:
    """latest 行 → 东财字段名，附带自选状态/加选时间。"""
    d = {
        "f12": r["code"], "f14": r["name"], "f100": r["industry"],
        "f2": r["f2"], "f3": r["f3"], "f8": r["f8"],
        "f6": r["f6"], "f20": r["f20"], "f9": r["f9"],
        "added": added,
    }
    if created_at is not None:
        d["created_at"] = created_at
    return d


@router.get("")
def watch_list(user=Depends(current_user)):
    """我的自选列表（按加选时间倒序），关联最新快照行情。"""
    rows = get_conn().execute(
        "SELECT w.created_at AS w_created_at,"
        " COALESCE(l.code, w.code) AS code, COALESCE(l.name, w.name) AS name,"
        " l.industry, l.f2, l.f3, l.f6, l.f8, l.f9, l.f20"
        " FROM watchlist w LEFT JOIN latest l ON l.code = w.code"
        " WHERE w.user_id = ? ORDER BY w.created_at DESC",
        (user["id"],),
    ).fetchall()
    return {"rows": [_fkey_row(r, created_at=r["w_created_at"]) for r in rows]}


@router.post("")
def watch_add(body: AddIn, user=Depends(current_user)):
    """添加自选：code 必须存在于行情快照（防脏数据）；重复添加幂等。"""
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
            "INSERT OR IGNORE INTO watchlist (user_id, code, name, created_at)"
            " VALUES (?, ?, ?, ?)",
            (user["id"], code, row["name"],
             datetime.now().isoformat(timespec="seconds")),
        )
    log_op(user, "watchlist_add", "%s %s" % (code, row["name"]))
    return {"ok": True, "code": code, "name": row["name"]}


@router.delete("/{code}")
def watch_remove(code: str, user=Depends(current_user)):
    """删除自选（不存在也返回 ok，幂等）。"""
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM watchlist WHERE user_id = ? AND code = ?",
            (user["id"], code)).fetchone()
        conn.execute("DELETE FROM watchlist WHERE user_id = ? AND code = ?",
                     (user["id"], code))
    log_op(user, "watchlist_del",
           code + (" " + row["name"] if row and row["name"] else ""))
    return {"ok": True}


@router.get("/search")
def watch_search(kw: str = Query(default="", max_length=32),
                 user=Depends(current_user)):
    """按代码/名称搜索可添加的股票（最多 20 条，附带是否已加自选）。"""
    kw = kw.strip()
    if not kw:
        return {"rows": []}
    like = "%" + kw + "%"
    rows = get_conn().execute(
        "SELECT l.*,"
        " EXISTS(SELECT 1 FROM watchlist w"
        "        WHERE w.user_id = ? AND w.code = l.code) AS added"
        " FROM latest l"
        " WHERE l.f2 IS NOT NULL AND (l.code LIKE ? OR l.name LIKE ?)"
        " ORDER BY (l.code LIKE ?) DESC, l.f8 DESC LIMIT 20",
        (user["id"], like, like, kw + "%"),
    ).fetchall()
    return {"rows": [_fkey_row(r, added=bool(r["added"])) for r in rows]}
