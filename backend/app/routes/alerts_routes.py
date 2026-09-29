"""预警中心:规则 CRUD + 触发事件查询(评估在 app/alerts.py,随快照节拍)。"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import db
from ..alerts import LIMIT_TYPES, MAX_RULES_PER_USER, RULE_TYPES
from ..oplog import client_ip, log_op, user_agent
from ..security import current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

_CODE_RE = re.compile(r"^\d{6}$")


class RuleIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    rule_type: str = Field(max_length=20)
    threshold: float | None = None
    cooldown_min: int = Field(default=60, ge=5, le=720)


class RulePatch(BaseModel):
    threshold: float | None = None
    cooldown_min: int | None = Field(default=None, ge=5, le=720)
    enabled: bool | None = None


def _validate_rule(body: RuleIn) -> None:
    if not _CODE_RE.match(body.code):
        raise HTTPException(400, "code 须为 6 位数字")
    if body.rule_type not in RULE_TYPES:
        raise HTTPException(400, "rule_type 不支持")
    if body.rule_type not in LIMIT_TYPES and body.threshold is None:
        raise HTTPException(400, "该类型必须提供 threshold")


def _owned_rule(conn, rid: int, user) -> dict:
    row = conn.execute("SELECT * FROM alert_rule WHERE id = ?", (rid,)).fetchone()
    if not row or row["user_id"] != user["id"]:
        raise HTTPException(404, "规则不存在")
    return dict(row)


@router.get("/rules")
def list_rules(user=Depends(current_user)):
    rows = [dict(r) for r in db.get_conn().execute(
        "SELECT * FROM alert_rule WHERE user_id = ? ORDER BY id DESC",
        (user["id"],)).fetchall()]
    return {"rows": rows}


@router.post("/rules", status_code=201)
def create_rule(body: RuleIn, request: Request, user=Depends(current_user)):
    _validate_rule(body)
    conn = db.get_conn()
    cnt = conn.execute(
        "SELECT COUNT(*) AS c FROM alert_rule WHERE user_id = ?",
        (user["id"],)).fetchone()["c"]
    if cnt >= MAX_RULES_PER_USER:
        raise HTTPException(400, f"规则数量已达上限 {MAX_RULES_PER_USER} 条")
    stock = conn.execute(
        "SELECT name FROM latest WHERE code = ?", (body.code,)).fetchone()
    if not stock:
        raise HTTPException(400, "未找到该股票(不在全市场快照中)")
    with conn:
        cur = conn.execute(
            "INSERT INTO alert_rule"
            " (user_id, code, name, rule_type, threshold, cooldown_min, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (user["id"], body.code, stock["name"], body.rule_type,
             body.threshold, body.cooldown_min,
             datetime.now().isoformat(timespec="seconds")))
    log_op(user, "alert_rule_add",
           f"{body.code} {stock['name']} {body.rule_type} {body.threshold}",
           client_ip(request), user_agent(request))
    return {"id": cur.lastrowid}


@router.patch("/rules/{rid}")
def update_rule(rid: int, body: RulePatch, request: Request,
                user=Depends(current_user)):
    conn = db.get_conn()
    rule = _owned_rule(conn, rid, user)
    sets, params = [], []
    if body.threshold is not None:
        if rule["rule_type"] in LIMIT_TYPES:
            raise HTTPException(400, "涨跌停类规则无阈值")
        sets.append("threshold = ?")
        params.append(body.threshold)
    if body.cooldown_min is not None:
        sets.append("cooldown_min = ?")
        params.append(body.cooldown_min)
    if body.enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if body.enabled else 0)
    if not sets:
        raise HTTPException(400, "无可更新字段")
    with conn:
        conn.execute("UPDATE alert_rule SET " + ", ".join(sets) + " WHERE id = ?",
                     (*params, rid))
    log_op(user, "alert_rule_update", f"#{rid} " + ", ".join(sets),
           client_ip(request), user_agent(request))
    return {"ok": True}


@router.delete("/rules/{rid}")
def delete_rule(rid: int, request: Request, user=Depends(current_user)):
    conn = db.get_conn()
    _owned_rule(conn, rid, user)
    with conn:
        conn.execute("DELETE FROM alert_rule WHERE id = ?", (rid,))
    log_op(user, "alert_rule_del", f"#{rid}", client_ip(request), user_agent(request))
    return {"ok": True}


@router.get("/events")
def events(since_id: int = Query(default=0, ge=0),
           limit: int = Query(default=100, ge=1, le=100),
           user=Depends(current_user)):
    """增量轮询:返回 id > since_id 的事件(升序) + max_id 游标 + 未读总数。"""
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM alert_event WHERE user_id = ? AND id > ?"
        " ORDER BY id ASC LIMIT ?", (user["id"], since_id, limit)).fetchall()]
    max_id = rows[-1]["id"] if rows else since_id
    unread = conn.execute(
        "SELECT COUNT(*) AS c FROM alert_event WHERE user_id = ? AND read = 0",
        (user["id"],)).fetchone()["c"]
    return {"events": rows, "max_id": max_id, "unread": unread}


@router.get("/events/history")
def events_history(page: int = Query(default=1, ge=1),
                   size: int = Query(default=20, ge=1, le=100),
                   user=Depends(current_user)):
    conn = db.get_conn()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM alert_event WHERE user_id = ?",
        (user["id"],)).fetchone()["c"]
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM alert_event WHERE user_id = ?"
        " ORDER BY id DESC LIMIT ? OFFSET ?",
        (user["id"], size, (page - 1) * size)).fetchall()]
    return {"rows": rows, "total": total}


class ReadIn(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=200)


@router.post("/events/read")
def events_read(body: ReadIn, user=Depends(current_user)):
    """标记已读;ids 为空表示全部已读(均为 owner-only)。"""
    conn = db.get_conn()
    with conn:
        if body.ids:
            conn.execute(
                "UPDATE alert_event SET read = 1 WHERE user_id = ?"
                " AND id IN (%s)" % ",".join("?" * len(body.ids)),
                (user["id"], *body.ids))
        else:
            conn.execute("UPDATE alert_event SET read = 1 WHERE user_id = ?",
                         (user["id"],))
    return {"ok": True}
