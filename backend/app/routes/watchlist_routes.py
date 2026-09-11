"""自选股：列表 / 添加 / 删除 / 搜索。

按用户隔离存储（watchlist 表，user_id + code 主键），所有 /api/watchlist/*
需要登录。列表和搜索都关联 latest 快照返回实时行情字段（f2/f3/f8...），
与前端筛选页渲染逻辑一致。
"""
import re
from datetime import datetime

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import get_conn
from ..oplog import client_ip, log_op, user_agent
from ..security import current_user

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

CODE_RE = re.compile(r"^\d{6}$")
LETTER_RE = re.compile(r"^[a-zA-Z]+$")

# 东财搜索联想:拼音简写/全拼 → A股候选(token 为东财网页端公开值)。
# 与 fetcher 同样 trust_env=False 忽略系统代理;任何失败都不影响本地搜索。
_suggest = requests.Session()
_suggest.trust_env = False
SUGGEST_URL = "https://searchapi.eastmoney.com/api/suggest/get"
SUGGEST_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"


def _suggest_astock(kw: str, limit: int = 20) -> list[dict]:
    """拼音联想 → [{code, name, pinyin}](仅 A 股;异常返回空列表)。"""
    try:
        r = _suggest.get(SUGGEST_URL, params={
            "input": kw, "type": 14, "token": SUGGEST_TOKEN, "count": limit,
        }, timeout=2)
        data = (r.json().get("QuotationCodeTable") or {}).get("Data") or []
        return [
            {"code": d.get("Code", ""), "name": d.get("Name", ""),
             "pinyin": d.get("PinYin", "")}
            for d in data if d.get("Classify") == "AStock"
        ]
    except Exception:
        return []


class AddIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)


def _fkey_row(r, added: bool = True, created_at: str | None = None) -> dict:
    """latest 行 → 东财字段名，附带自选状态/加选时间/涨跌停标记。"""
    d = {
        "f12": r["code"], "f14": r["name"], "f100": r["industry"],
        "f2": r["f2"], "f3": r["f3"], "f8": r["f8"],
        "f6": r["f6"], "f20": r["f20"], "f9": r["f9"],
        "limit_up": r["limit_up"], "limit_down": r["limit_down"],
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
        " l.industry, l.f2, l.f3, l.f6, l.f8, l.f9, l.f20, l.limit_up, l.limit_down"
        " FROM watchlist w LEFT JOIN latest l ON l.code = w.code"
        " WHERE w.user_id = ? ORDER BY w.created_at DESC",
        (user["id"],),
    ).fetchall()
    return {"rows": [_fkey_row(r, created_at=r["w_created_at"]) for r in rows]}


@router.post("")
def watch_add(request: Request, body: AddIn, user=Depends(current_user)):
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
    log_op(user, "watchlist_add", "%s %s" % (code, row["name"]),
           client_ip(request), user_agent(request))
    return {"ok": True, "code": code, "name": row["name"]}


@router.delete("/{code}")
def watch_remove(code: str, request: Request, user=Depends(current_user)):
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
           code + (" " + row["name"] if row and row["name"] else ""),
           client_ip(request), user_agent(request))
    return {"ok": True}


@router.get("/search")
def watch_search(kw: str = Query(default="", max_length=32),
                 user=Depends(current_user)):
    """搜索可添加的股票（最多 20 条，附带是否已加自选）。

    数字/中文走本地快照（代码前缀优先、按换手率排）；纯字母走东财拼音联想，
    合并去重后追加（联想项须存在于本地快照，否则添加后也取不到行情）。
    """
    kw = kw.strip()
    if not kw:
        return {"rows": []}
    conn = get_conn()
    like = "%" + kw + "%"
    rows = list(conn.execute(
        "SELECT l.*,"
        " EXISTS(SELECT 1 FROM watchlist w"
        "        WHERE w.user_id = ? AND w.code = l.code) AS added"
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
                " EXISTS(SELECT 1 FROM watchlist w"
                "        WHERE w.user_id = ? AND w.code = l.code) AS added"
                " FROM latest l"
                " WHERE l.f2 IS NOT NULL AND l.code IN (" + marks + ")",
                (user["id"], *codes),
            ).fetchall()}
            # 保持联想返回的相关度顺序(东财已按热度排序)
            rows.extend(by_code[c] for c in codes if c in by_code)
    out = []
    for r in rows[:20]:
        d = _fkey_row(r, added=bool(r["added"]))
        if r["code"] in pinyin_of:
            d["pinyin"] = pinyin_of[r["code"]]
        out.append(d)
    return {"rows": out}
