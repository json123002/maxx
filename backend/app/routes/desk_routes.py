"""我的工作台：独立股票池 + 重点关注（星标）+ 自定义分组 + 个股 F10 资料代理。

工作台与「我的自选」完全解耦：desk_stock 是自己的股票池（支持从自选一键导入），
desk_star 星标、desk_group / desk_group_item 自定义分组都以股票池为准
（股票须先在池内，同一股票可进多个分组，组内支持拖拽排序）。
F10 数据（公司概况/股东人数/题材概念）代理自东财 emweb 接口，按 code 做
内存缓存（6 小时 TTL）：这些资料按披露节奏变化，无需实时。
"""
import re
import threading
import time
from datetime import datetime

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import get_conn
from ..oplog import client_ip, log_op, user_agent
from ..security import current_user
from .watchlist_routes import LETTER_RE, _fkey_row, _suggest_astock

router = APIRouter(prefix="/api/desk", tags=["desk"])

CODE_RE = re.compile(r"^\d{6}$")

# 与 fetcher 同样 trust_env=False 忽略系统代理;emweb 需要页面 Referer
_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://emweb.securities.eastmoney.com/",
})

EMWEB = "https://emweb.securities.eastmoney.com/PC_HSF10"
F10_TTL = 6 * 3600  # F10 资料按披露节奏变化,缓存 6 小时
_f10_cache = {}     # code -> (expire_ts, payload)
_f10_lock = threading.Lock()


def _market_prefix(code: str) -> str:
    """东财 F10 接口的市场前缀:6 开头 SH,4/8 开头 BJ,其余 SZ。"""
    if code.startswith("6"):
        return "SH"
    if code.startswith(("4", "8", "9")):
        return "BJ"
    return "SZ"


def _get_json(path: str, params: dict) -> dict:
    r = _session.get(EMWEB + path, params=params, timeout=6)
    return r.json() if r.ok else {}


def _clean_text(s: str, limit: int = 600) -> str:
    """F10 长文本去空白截断（简介/题材要点展示用）。"""
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    return t[:limit]


def _fetch_f10(code: str) -> dict:
    """聚合公司概况/股东人数/核心题材/管理层;单源失败降级为空,不拖垮整体。"""
    mcode = _market_prefix(code) + code
    survey, holders, boards, points, execs = {}, [], [], [], []

    try:
        jbzl = (_get_json("/CompanySurvey/CompanySurveyAjax",
                          {"code": mcode}).get("jbzl") or {})
        survey = {
            "full_name": jbzl.get("gsmc") or "",
            "industry": jbzl.get("sshy") or "",
            "csrc_industry": jbzl.get("sszjhhy") or "",
            "region": jbzl.get("qy") or "",
            "address": jbzl.get("zcdz") or jbzl.get("bgdz") or "",
            "chairman": jbzl.get("dsz") or "",
            "reg_capital": jbzl.get("zczb") or "",
            "employees": jbzl.get("gyrs") or "",
            "intro": _clean_text(jbzl.get("gsjj")),
        }
    except Exception:
        pass

    try:
        gdrs = (_get_json("/ShareholderResearch/PageAjax",
                          {"code": mcode}).get("gdrs") or [])
        for r in gdrs[:8]:
            holders.append({
                "date": str(r.get("END_DATE") or "")[:10],
                "num": r.get("HOLDER_TOTAL_NUM"),
                "ratio": r.get("TOTAL_NUM_RATIO"),
                "focus": r.get("HOLD_FOCUS") or "",
                "price": r.get("PRICE"),
                "avg_amt": r.get("AVG_HOLD_AMT"),
            })
    except Exception:
        pass

    try:
        d = _get_json("/CoreConception/PageAjax", {"code": mcode})
        seen = set()
        for r in (d.get("ssbk") or [])[:24]:
            # 去掉 Ⅱ/Ⅲ 分级后缀后去重(行业各级会重名)
            name = str(r.get("BOARD_NAME") or "").replace("Ⅱ", "").replace("Ⅲ", "")
            if name and name not in seen:
                seen.add(name)
                boards.append(name)
                if len(boards) >= 16:
                    break
        # 同一大类(如"主营业务")可能有多条要点:合并为一组,内容并列展示
        grouped = {}
        for r in (d.get("hxtc") or []):
            content = _clean_text(r.get("MAINPOINT_CONTENT"), 300)
            title = r.get("KEY_CLASSIF") or r.get("KEYWORD") or ""
            if content and title:
                grouped.setdefault(title, []).append(content)
        for title, contents in list(grouped.items())[:4]:
            points.append({"title": title, "contents": contents[:3]})
    except Exception:
        pass

    try:
        d = _get_json("/CompanyManagement/PageAjax", {"code": mcode})
        for r in (d.get("gglb") or [])[:30]:
            age = str(r.get("AGE") or "")
            execs.append({
                "name": r.get("PERSON_NAME") or "",
                "position": r.get("POSITION") or "",
                "sex": r.get("SEX") or "",
                "age": int(age) if age.isdigit() else None,
                "degree": r.get("HIGH_DEGREE") or "",
                "salary": r.get("SALARY"),
                "hold_num": r.get("HOLD_NUM"),
                "resume": _clean_text(r.get("RESUME"), 500),
            })
    except Exception:
        pass

    return {"survey": survey, "holders": holders,
            "boards": boards, "points": points, "execs": execs}


# ---------- 工作台股票池（独立于自选） ----------

class StockIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class StockOrderIn(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=500)


@router.get("/stocks")
def desk_stock_list(user=Depends(current_user)):
    """工作台股票列表（手工排序优先，其次加选时间倒序），关联最新快照行情。"""
    rows = get_conn().execute(
        "SELECT s.created_at AS s_created_at,"
        " COALESCE(l.code, s.code) AS code, COALESCE(l.name, s.name) AS name,"
        " l.industry, l.f2, l.f3, l.f6, l.f8, l.f9, l.f20, l.limit_up, l.limit_down"
        " FROM desk_stock s LEFT JOIN latest l ON l.code = s.code"
        " WHERE s.user_id = ? ORDER BY s.sort DESC, s.created_at DESC",
        (user["id"],),
    ).fetchall()
    return {"rows": [_fkey_row(r, created_at=r["s_created_at"]) for r in rows]}


@router.post("/stocks")
def desk_stock_add(body: StockIn, request: Request, user=Depends(current_user)):
    """添加股票到工作台：code 必须存在于行情快照（防脏数据）；重复添加幂等。"""
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
            "INSERT OR IGNORE INTO desk_stock (user_id, code, name, created_at)"
            " VALUES (?, ?, ?, ?)",
            (user["id"], code, row["name"],
             datetime.now().isoformat(timespec="seconds")))
    log_op(user, "desk_stock_add", "%s %s" % (code, row["name"]),
           client_ip(request), user_agent(request))
    return {"ok": True, "code": code, "name": row["name"]}


@router.delete("/stocks/{code}")
def desk_stock_remove(code: str, request: Request, user=Depends(current_user)):
    """从工作台移除（连带清理星标和分组成员关系；不存在也返回 ok）。"""
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM desk_stock WHERE user_id = ? AND code = ?",
            (user["id"], code)).fetchone()
        conn.execute("DELETE FROM desk_stock WHERE user_id = ? AND code = ?",
                     (user["id"], code))
        conn.execute("DELETE FROM desk_star WHERE user_id = ? AND code = ?",
                     (user["id"], code))
        conn.execute("DELETE FROM desk_group_item WHERE user_id = ? AND code = ?",
                     (user["id"], code))
    log_op(user, "desk_stock_del",
           code + (" " + row["name"] if row and row["name"] else ""),
           client_ip(request), user_agent(request))
    return {"ok": True}


@router.put("/stocks/order")
def desk_stock_order(body: StockOrderIn, request: Request,
                     user=Depends(current_user)):
    """保存分组内拖拽排序：按传入顺序写递减 sort 值（与自选排序同口径）。"""
    codes = [c.strip() for c in body.codes if CODE_RE.match(c.strip())]
    if not codes:
        raise HTTPException(400, "无有效股票代码")
    n = len(codes)
    with get_conn() as conn:
        conn.executemany(
            "UPDATE desk_stock SET sort = ? WHERE user_id = ? AND code = ?",
            [(n - i, user["id"], c) for i, c in enumerate(codes)],
        )
    log_op(user, "desk_stock_order", "%d 只" % len(codes),
           client_ip(request), user_agent(request))
    return {"ok": True, "count": len(codes)}


@router.post("/stocks/import")
def desk_stock_import(request: Request, user=Depends(current_user)):
    """从「我的自选」一键导入（幂等，只补新代码，不影响已有排序/分组）。"""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO desk_stock (user_id, code, name, created_at)"
            " SELECT user_id, code, name, created_at FROM watchlist"
            " WHERE user_id = ?",
            (user["id"],),
        )
    log_op(user, "desk_stock_import", "新增 %d 只" % cur.rowcount,
           client_ip(request), user_agent(request))
    return {"ok": True, "added": cur.rowcount}


@router.get("/stocks/search")
def desk_stock_search(kw: str = Query(default="", max_length=32),
                      user=Depends(current_user)):
    """搜索可添加的股票（最多 20 条，附带是否已在工作台）。逻辑同自选搜索。"""
    kw = kw.strip()
    if not kw:
        return {"rows": []}
    conn = get_conn()
    like = "%" + kw + "%"
    rows = list(conn.execute(
        "SELECT l.*,"
        " EXISTS(SELECT 1 FROM desk_stock s"
        "        WHERE s.user_id = ? AND s.code = l.code) AS added"
        " FROM latest l"
        " WHERE l.f2 IS NOT NULL AND (l.code LIKE ? OR l.name LIKE ?)"
        " ORDER BY (l.code LIKE ?) DESC, l.f8 DESC LIMIT 20",
        (user["id"], like, like, kw + "%"),
    ).fetchall())
    pinyin_of = {}
    if LETTER_RE.match(kw) and len(rows) < 20:
        sugs = [s for s in _suggest_astock(kw)
                if s["code"] not in {r["code"] for r in rows}]
        codes = [s["code"] for s in sugs]
        pinyin_of = {s["code"]: s["pinyin"] for s in sugs}
        if codes:
            marks = ",".join("?" * len(codes))
            by_code = {r["code"]: r for r in conn.execute(
                "SELECT l.*,"
                " EXISTS(SELECT 1 FROM desk_stock s"
                "        WHERE s.user_id = ? AND s.code = l.code) AS added"
                " FROM latest l"
                " WHERE l.f2 IS NOT NULL AND l.code IN (" + marks + ")",
                (user["id"], *codes),
            ).fetchall()}
            rows.extend(by_code[c] for c in codes if c in by_code)
    out = []
    for r in rows[:20]:
        d = _fkey_row(r, added=bool(r["added"]))
        if r["code"] in pinyin_of:
            d["pinyin"] = pinyin_of[r["code"]]
        out.append(d)
    return {"rows": out}


# ---------- 重点关注 ----------

@router.get("/star")
def star_list(user=Depends(current_user)):
    """重点关注代码集合（前端用来把星标股排到分组顶部）。"""
    rows = get_conn().execute(
        "SELECT code FROM desk_star WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return {"codes": [r["code"] for r in rows]}


@router.post("/star")
def star_add(body: StockIn, request: Request, user=Depends(current_user)):
    """标记重点关注：须已在工作台股票池内（重点关注是池的子集），重复幂等。"""
    code = body.code.strip()
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    conn = get_conn()
    in_pool = conn.execute(
        "SELECT name FROM desk_stock WHERE user_id = ? AND code = ?",
        (user["id"], code)).fetchone()
    if not in_pool:
        raise HTTPException(400, "请先加入工作台，再标记重点关注")
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO desk_star (user_id, code, created_at)"
            " VALUES (?, ?, ?)",
            (user["id"], code, datetime.now().isoformat(timespec="seconds")))
    # 详情带名称,日志页一眼可读(与 desk_stock_del 同口径)
    log_op(user, "desk_star_add",
           code + (" " + in_pool["name"] if in_pool["name"] else ""),
           client_ip(request), user_agent(request))
    return {"ok": True, "code": code}


@router.delete("/star/{code}")
def star_remove(code: str, request: Request, user=Depends(current_user)):
    """取消重点关注（不存在也返回 ok，幂等）。"""
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM desk_stock WHERE user_id = ? AND code = ?",
            (user["id"], code)).fetchone()
        conn.execute("DELETE FROM desk_star WHERE user_id = ? AND code = ?",
                     (user["id"], code))
    log_op(user, "desk_star_del",
           code + (" " + row["name"] if row and row["name"] else ""),
           client_ip(request), user_agent(request))
    return {"ok": True}


# ---------- 自定义分组 ----------

class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)


class GroupItemIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class GroupOrderIn(BaseModel):
    codes: list[str] = Field(min_length=1, max_length=500)


def _own_group(gid: int, user_id: int):
    """取属于当前用户的分组行;不存在/越权一律 404。"""
    row = get_conn().execute(
        "SELECT id, name FROM desk_group WHERE id = ? AND user_id = ?",
        (gid, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "分组不存在")
    return row


@router.get("/groups")
def group_list(user=Depends(current_user)):
    """我的分组列表(创建顺序) + 每组股票代码(组内 sort 优先,其次加入时间)。"""
    conn = get_conn()
    gs = conn.execute(
        "SELECT id, name FROM desk_group WHERE user_id = ? ORDER BY id",
        (user["id"],)).fetchall()
    items = conn.execute(
        "SELECT group_id, code FROM desk_group_item WHERE user_id = ?"
        " ORDER BY sort DESC, created_at DESC",
        (user["id"],)).fetchall()
    by_group = {}
    for it in items:
        by_group.setdefault(it["group_id"], []).append(it["code"])
    return {"groups": [{"id": g["id"], "name": g["name"],
                        "codes": by_group.get(g["id"], [])} for g in gs]}


@router.post("/groups")
def group_add(body: GroupIn, request: Request, user=Depends(current_user)):
    """新建分组:按用户同名查重,上限 50 个防滥用。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "分组名称不能为空")
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM desk_group WHERE user_id = ?",
        (user["id"],)).fetchone()["c"]
    if n >= 50:
        raise HTTPException(400, "分组数量已达上限(50)")
    dup = conn.execute(
        "SELECT 1 FROM desk_group WHERE user_id = ? AND name = ?",
        (user["id"], name)).fetchone()
    if dup:
        raise HTTPException(400, "已存在同名分组")
    with conn:
        cur = conn.execute(
            "INSERT INTO desk_group (user_id, name, created_at) VALUES (?, ?, ?)",
            (user["id"], name, datetime.now().isoformat(timespec="seconds")))
    log_op(user, "desk_group_add", name, client_ip(request), user_agent(request))
    return {"ok": True, "id": cur.lastrowid, "name": name}


@router.put("/groups/{gid}")
def group_rename(gid: int, body: GroupIn, request: Request,
                 user=Depends(current_user)):
    """重命名分组。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "分组名称不能为空")
    row = _own_group(gid, user["id"])
    dup = get_conn().execute(
        "SELECT 1 FROM desk_group WHERE user_id = ? AND name = ? AND id != ?",
        (user["id"], name, gid)).fetchone()
    if dup:
        raise HTTPException(400, "已存在同名分组")
    with get_conn() as conn:
        conn.execute("UPDATE desk_group SET name = ? WHERE id = ?", (name, gid))
    log_op(user, "desk_group_rename", "%s → %s" % (row["name"], name),
           client_ip(request), user_agent(request))
    return {"ok": True, "name": name}


@router.delete("/groups/{gid}")
def group_remove(gid: int, request: Request, user=Depends(current_user)):
    """删除分组(组内成员关系一并删除,不影响自选本身)。"""
    row = _own_group(gid, user["id"])
    with get_conn() as conn:
        conn.execute("DELETE FROM desk_group WHERE id = ?", (gid,))
    log_op(user, "desk_group_del", row["name"],
           client_ip(request), user_agent(request))
    return {"ok": True}


@router.post("/groups/{gid}/items")
def group_item_add(gid: int, body: GroupItemIn, request: Request,
                   user=Depends(current_user)):
    """股票加入分组:须已在工作台股票池内,重复幂等。"""
    row = _own_group(gid, user["id"])
    code = body.code.strip()
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    in_pool = get_conn().execute(
        "SELECT name FROM desk_stock WHERE user_id = ? AND code = ?",
        (user["id"], code)).fetchone()
    if not in_pool:
        raise HTTPException(400, "请先加入工作台，再归入分组")
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO desk_group_item"
            " (group_id, user_id, code, created_at) VALUES (?, ?, ?, ?)",
            (gid, user["id"], code, datetime.now().isoformat(timespec="seconds")))
    # 详情:组名 + 代码 + 名称,日志页一眼可读
    log_op(user, "desk_gitem_add",
           "「%s」%s%s" % (row["name"], code,
                          " " + in_pool["name"] if in_pool["name"] else ""),
           client_ip(request), user_agent(request))
    return {"ok": True, "code": code}


@router.delete("/groups/{gid}/items/{code}")
def group_item_remove(gid: int, code: str, request: Request,
                      user=Depends(current_user)):
    """股票移出分组(不存在也返回 ok,幂等)。"""
    row = _own_group(gid, user["id"])
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    with get_conn() as conn:
        stk = conn.execute(
            "SELECT name FROM desk_stock WHERE user_id = ? AND code = ?",
            (user["id"], code)).fetchone()
        conn.execute(
            "DELETE FROM desk_group_item WHERE group_id = ? AND user_id = ?"
            " AND code = ?",
            (gid, user["id"], code))
    log_op(user, "desk_gitem_del",
           "「%s」%s%s" % (row["name"], code,
                          " " + stk["name"] if stk and stk["name"] else ""),
           client_ip(request), user_agent(request))
    return {"ok": True}


@router.put("/groups/{gid}/order")
def group_item_order(gid: int, body: GroupOrderIn, request: Request,
                     user=Depends(current_user)):
    """保存组内拖拽排序:按传入顺序写递减 sort 值(与自选排序同口径)。"""
    row = _own_group(gid, user["id"])
    codes = [c.strip() for c in body.codes if CODE_RE.match(c.strip())]
    if not codes:
        raise HTTPException(400, "无有效股票代码")
    n = len(codes)
    with get_conn() as conn:
        conn.executemany(
            "UPDATE desk_group_item SET sort = ?"
            " WHERE group_id = ? AND user_id = ? AND code = ?",
            [(n - i, gid, user["id"], c) for i, c in enumerate(codes)])
    log_op(user, "desk_gitem_order", "「%s」%d 只" % (row["name"], len(codes)),
           client_ip(request), user_agent(request))
    return {"ok": True, "count": len(codes)}


# ---------- 个股 F10 资料 ----------

@router.get("/f10/{code}")
def f10(code: str, user=Depends(current_user)):
    """公司概况/股东人数/题材概念聚合（6 小时缓存）。"""
    if not CODE_RE.match(code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    with _f10_lock:
        hit = _f10_cache.get(code)
        if hit and hit[0] > time.time():
            return hit[1]
    payload = _fetch_f10(code)
    payload["code"] = code
    payload["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    # 数据源全挂(限流/断网)时不写缓存,避免空结果占满 6 小时 TTL
    if not (payload["survey"] or payload["holders"]
            or payload["boards"] or payload["execs"]):
        return payload
    with _f10_lock:
        _f10_cache[code] = (time.time() + F10_TTL, payload)
        # 防内存膨胀:缓存超过 200 只时清掉过期项
        if len(_f10_cache) > 200:
            now = time.time()
            for k in [k for k, v in _f10_cache.items() if v[0] <= now]:
                _f10_cache.pop(k, None)
    return payload
