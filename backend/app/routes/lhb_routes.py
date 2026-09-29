"""龙虎榜查询：每日榜单 / 个股上榜记录 / 席位明细 / 席位画像。"""
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_conn
from ..security import current_user

router = APIRouter(prefix="/api/lhb", tags=["lhb"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEAT_SORTS = {"win_rate": "win_rate DESC", "apps": "appearances DESC",
               "net": "total_net DESC"}


def _check_date(date: str) -> None:
    if not _DATE_RE.match(date):
        raise HTTPException(400, "date 格式须为 YYYY-MM-DD")


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
    buy = [dict(r) for r in conn.execute(
        "SELECT * FROM lhb_seat WHERE code = ? AND trade_date = ? AND side = 'B'"
        " ORDER BY buy DESC", (code, date)).fetchall()]
    sell = [dict(r) for r in conn.execute(
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
    for r in rows:
        r["top_stocks"] = json.loads(r["top_stocks"] or "[]")
        r["co_seats"] = json.loads(r["co_seats"] or "[]")
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
    recent = [dict(r) for r in conn.execute(
        "SELECT trade_date, code, name, side, buy, sell, net,"
        " t_close, t1_open, t1_high, t1_close FROM lhb_seat"
        " WHERE dept_name = ? ORDER BY trade_date DESC LIMIT 20",
        (name,)).fetchall()]
    return {"stat": stat, "recent": recent}
