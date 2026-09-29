"""龙虎榜查询：每日榜单 / 个股上榜记录 / 席位明细 / 席位画像 / 游资席位标注。"""
import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import get_conn
from ..lhb import famous_map, tag_of
from ..oplog import client_ip, log_op, user_agent
from ..security import current_user, require_admin

router = APIRouter(prefix="/api/lhb", tags=["lhb"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEAT_SORTS = {"win_rate": "win_rate DESC", "apps": "appearances DESC",
               "net": "total_net DESC"}


def _check_date(date: str) -> None:
    if not _DATE_RE.match(date):
        raise HTTPException(400, "date 格式须为 YYYY-MM-DD")


def _with_tag(row: dict, famous: dict) -> dict:
    row["seat_tag"] = tag_of(row["dept_name"], famous)
    return row


@router.get("/dates")
def lhb_dates(user=Depends(current_user)):
    """有榜单数据的交易日（新→旧，最多 60 天）。"""
    rows = get_conn().execute(
        "SELECT DISTINCT trade_date FROM lhb_item"
        " ORDER BY trade_date DESC LIMIT 60").fetchall()
    return {"dates": [r["trade_date"] for r in rows]}


@router.get("/daily")
def lhb_daily(date: str = Query(...), user=Depends(current_user)):
    """某日榜单：按净买额绝对值降序。"""
    _check_date(date)
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM lhb_item WHERE trade_date = ?"
        " ORDER BY ABS(net_amt) DESC", (date,)).fetchall()]
    buy = sum(r["net_amt"] or 0 for r in rows if (r["net_amt"] or 0) > 0)
    sell = sum(-(r["net_amt"] or 0) for r in rows if (r["net_amt"] or 0) < 0)
    return {"date": date, "total": len(rows), "rows": rows,
            "summary": {"buy": buy, "sell": sell}}


@router.get("/stock/{code}")
def lhb_stock(code: str, days: int = Query(default=60, ge=1, le=250),
              user=Depends(current_user)):
    """个股近期上榜记录。"""
    if not re.match(r"^\d{6}$", code):
        raise HTTPException(400, "code 须为 6 位数字")
    rows = [dict(r) for r in get_conn().execute(
        "SELECT * FROM lhb_item WHERE code = ?"
        " ORDER BY trade_date DESC LIMIT ?", (code, days)).fetchall()]
    return {"rows": rows}


@router.get("/stock/{code}/seats")
def lhb_stock_seats(code: str, date: str = Query(...),
                    user=Depends(current_user)):
    """个股某日买卖席位明细。"""
    if not re.match(r"^\d{6}$", code):
        raise HTTPException(400, "code 须为 6 位数字")
    _check_date(date)
    conn = get_conn()
    famous = famous_map(conn)
    buy = [_with_tag(dict(r), famous) for r in conn.execute(
        "SELECT * FROM lhb_seat WHERE code = ? AND trade_date = ? AND side = 'B'"
        " ORDER BY buy DESC", (code, date)).fetchall()]
    sell = [_with_tag(dict(r), famous) for r in conn.execute(
        "SELECT * FROM lhb_seat WHERE code = ? AND trade_date = ? AND side = 'S'"
        " ORDER BY sell DESC", (code, date)).fetchall()]
    return {"buy": buy, "sell": sell}


@router.get("/seats")
def lhb_seats(kw: str = Query(default="", max_length=32),
              min_apps: int = Query(default=3, ge=1, le=100),
              sort: str = Query(default="win_rate"),
              limit: int = Query(default=200, ge=1, le=1000),
              user=Depends(current_user)):
    """席位画像榜：胜率/上榜次数/净买额排序。"""
    order = _SEAT_SORTS.get(sort)
    if not order:
        raise HTTPException(400, "sort 须为 win_rate/apps/net")
    where, params = " WHERE appearances >= ?", [min_apps]
    kw = kw.strip()
    if kw:
        where += " AND dept_name LIKE ?"
        params.append("%" + kw + "%")
    # 胜率排序只看有次日结果样本的席位,无样本垫底
    if sort == "win_rate":
        order = "win_rate IS NULL, " + order
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM lhb_seat_stat" + where, params).fetchone()["c"]
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM lhb_seat_stat" + where +
        " ORDER BY " + order + ", appearances DESC LIMIT ?",
        (*params, limit)).fetchall()]
    famous = famous_map(conn)
    for r in rows:
        r["top_stocks"] = json.loads(r["top_stocks"] or "[]")
        r["co_seats"] = json.loads(r["co_seats"] or "[]")
        r["seat_tag"] = tag_of(r["dept_name"], famous)
    return {"total": total, "rows": rows}


@router.get("/seat/{name}")
def lhb_seat(name: str, user=Depends(current_user)):
    """单个席位画像：聚合统计 + 近 20 次出场(含次日结果)。"""
    name = name.strip()
    if not name or len(name) > 64:
        raise HTTPException(400, "name 不合法")
    conn = get_conn()
    stat = conn.execute(
        "SELECT * FROM lhb_seat_stat WHERE dept_name = ?", (name,)).fetchone()
    if not stat:
        raise HTTPException(404, "席位不存在")
    stat = dict(stat)
    stat["top_stocks"] = json.loads(stat["top_stocks"] or "[]")
    stat["co_seats"] = json.loads(stat["co_seats"] or "[]")
    stat["seat_tag"] = tag_of(name, famous_map(conn))
    recent = [dict(r) for r in conn.execute(
        "SELECT trade_date, code, name, side, buy, sell, net,"
        " t_close, t1_open, t1_high, t1_close FROM lhb_seat"
        " WHERE dept_name = ? ORDER BY trade_date DESC LIMIT 20",
        (name,)).fetchall()]
    return {"stat": stat, "recent": recent}


# ---------- 网传游资席位映射(管理员维护) ----------

class FamousIn(BaseModel):
    dept_name: str = Field(min_length=4, max_length=64)
    alias: str = Field(min_length=1, max_length=32)
    note: str = Field(default="", max_length=200)


@router.get("/famous")
def famous_list(user=Depends(current_user)):
    """网传游资映射全量列表(所有登录用户可读,供席位标注展示口径说明)。"""
    rows = [dict(r) for r in get_conn().execute(
        "SELECT dept_name, alias, note, updated_at FROM lhb_famous_seat"
        " ORDER BY updated_at DESC").fetchall()]
    return {"rows": rows}


@router.post("/famous", status_code=201)
def famous_set(body: FamousIn, request: Request, admin=Depends(require_admin)):
    """新增/覆盖一条网传游资映射。"""
    dept_name, alias = body.dept_name.strip(), body.alias.strip()
    if not dept_name or not alias:
        raise HTTPException(400, "dept_name 与 alias 不能为空")
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO lhb_famous_seat (dept_name, alias, note, updated_at)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(dept_name) DO UPDATE SET"
            " alias=excluded.alias, note=excluded.note,"
            " updated_at=excluded.updated_at",
            (dept_name, alias, body.note.strip(),
             datetime.now().isoformat(timespec="seconds")))
    log_op(admin, "lhb_famous_set", f"{dept_name} → {alias}",
           client_ip(request), user_agent(request))
    return {"ok": True}


@router.delete("/famous/{dept_name}")
def famous_del(dept_name: str, request: Request, admin=Depends(require_admin)):
    conn = get_conn()
    with conn:
        cur = conn.execute("DELETE FROM lhb_famous_seat WHERE dept_name = ?",
                           (dept_name,))
    if cur.rowcount == 0:
        raise HTTPException(404, "映射不存在")
    log_op(admin, "lhb_famous_del", dept_name, client_ip(request), user_agent(request))
    return {"ok": True}
