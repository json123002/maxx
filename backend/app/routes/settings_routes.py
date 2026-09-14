"""行情源设置：每用户独立的第三方行情接口配置 + 首页实时行情代理。

- quote_source 表按用户隔离存储（user_id + name 唯一），证书编号只回给本人；
- 第三方请求全部由后端代理（浏览器不直连，避免 CORS，也避免把证书编号
  泄漏给其他用户/网络中间层）；服务商白名单内置固定域名，不接受用户填写
  URL（从根上排除 SSRF）；
- /api/quote/realtime 按当前用户启用的行情源取实时行情并归一化为东财字段名
  （f12/f14/f2/f3/f6/f8，与全站渲染逻辑零改动兼容），无启用源或源调用失败
  时回落到本地最新快照，页面永不空窗。
"""
import json
import re
import time
from datetime import datetime

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import get_conn
from ..oplog import client_ip, log_op, user_agent
from ..security import current_user

router = APIRouter(tags=["quotesettings"])   # 两类路径前缀，统一用全路径

CODE_RE = re.compile(r"^\d{6}$")
LIC_RE = re.compile(r"^[A-Za-z0-9\-_]{8,64}$")

# 服务商白名单：域名固定，用户只填证书编号（新增服务商时在此登记）
PROVIDERS = {
    "mairui": {"label": "麦蕊智数", "base": "https://api.mairuiapi.com"},
}

# 与 fetcher/watchlist 同口径：忽略系统代理（代理出口会被第三方 CDN 分配到
# 行为不同的节点）；任何失败都不影响回落到本地快照。
_mr = requests.Session()
_mr.trust_env = False


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _mairui_fetch(licence: str, codes: list[str]) -> list[dict]:
    """麦蕊实时行情（ssjy_more，≤20 只/次）→ 东财字段名行列表。

    单股接口换手字段是 hs，批量接口是 tr（两套字段名，历史原因）；
    归一化时 hs 优先、tr 兜底。名称/行业不在行情接口里，由 _attach_names
    从本地快照补齐。
    """
    base = PROVIDERS["mairui"]["base"]
    rows = []
    for i in range(0, len(codes), 20):
        chunk = codes[i:i + 20]
        r = _mr.get(
            base + "/hsrl/ssjy_more/" + licence,
            params={"stock_codes": ",".join(chunk)}, timeout=6)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            # 错误时返回 {"code":..,"msg":..} 或纯文本提示（如配额用尽的 "101"）
            msg = data if isinstance(data, str) else (
                data.get("msg") or data.get("message")
                or json.dumps(data, ensure_ascii=False))
            raise RuntimeError("麦蕊接口返回异常: " + str(msg)[:120])
        for it in data:
            rows.append({
                "f12": str(it.get("dm", "")).split(".")[0],  # 兼容 000001.SZ
                "f2": _num(it.get("p")),                     # 最新价
                "f3": _num(it.get("pc")),                    # 涨跌幅%
                "f6": _num(it.get("cje")),                   # 成交额
                "f8": _num(it.get("hs", it.get("tr"))),      # 换手率%
                "t": it.get("t"),                            # 行情时间
            })
    return rows


def _attach_names(rows: list[dict]) -> None:
    """用本地快照补 name(f14)/industry(f100)，前端渲染逻辑无需感知数据源差异。"""
    if not rows:
        return
    marks = ",".join("?" * len(rows))
    by = {r["code"]: dict(r) for r in get_conn().execute(
        "SELECT code, name, industry FROM latest WHERE code IN (" + marks + ")",
        [r["f12"] for r in rows]).fetchall()}
    for r in rows:
        snap = by.get(r["f12"]) or {}
        r["f14"] = snap.get("name") or r["f12"]
        r["f100"] = snap.get("industry")


# ===== 配置 CRUD =====

class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    provider: str = Field(min_length=1, max_length=32)
    licence: str = Field(min_length=8, max_length=64)


class SourcePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    licence: str | None = Field(default=None, min_length=8, max_length=64)
    enabled: bool | None = None


@router.get("/api/quotesettings")
def source_list(user=Depends(current_user)):
    """我的行情源配置列表（证书编号只返回给本人）。"""
    rows = get_conn().execute(
        "SELECT id, name, provider, licence, enabled, created_at, updated_at"
        " FROM quote_source WHERE user_id = ? ORDER BY id", (user["id"],),
    ).fetchall()
    return {"rows": [dict(r) for r in rows]}


@router.post("/api/quotesettings", status_code=201)
def source_create(request: Request, body: SourceIn, user=Depends(current_user)):
    """新增行情源：首个配置自动启用。"""
    if body.provider not in PROVIDERS:
        raise HTTPException(400, "暂不支持该行情源服务商")
    licence = body.licence.strip()
    if not LIC_RE.match(licence):
        raise HTTPException(400, "证书编号格式不正确")
    name = body.name.strip()
    conn = get_conn()
    dup = conn.execute(
        "SELECT 1 FROM quote_source WHERE user_id = ? AND name = ?",
        (user["id"], name)).fetchone()
    if dup:
        raise HTTPException(409, "同名配置已存在")
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM quote_source WHERE user_id = ?",
        (user["id"],)).fetchone()["c"]
    with conn:
        conn.execute(
            "INSERT INTO quote_source"
            " (user_id, name, provider, licence, enabled, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], name, body.provider, licence, 1 if n == 0 else 0,
             datetime.now().isoformat(timespec="seconds")))
    log_op(user, "qsource_add", name, client_ip(request), user_agent(request))
    return {"ok": True}


@router.patch("/api/quotesettings/{sid}")
def source_update(sid: int, request: Request, body: SourcePatch,
                  user=Depends(current_user)):
    """改配置：启用某源时自动停用同用户其它源（首页实时行情只走一个源）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM quote_source WHERE id = ? AND user_id = ?",
        (sid, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "配置不存在")
    name, licence, sets, params = row["name"], row["licence"], [], []
    if body.name is not None and body.name.strip() != row["name"]:
        name = body.name.strip()
        dup = conn.execute(
            "SELECT 1 FROM quote_source WHERE user_id = ? AND name = ? AND id != ?",
            (user["id"], name, sid)).fetchone()
        if dup:
            raise HTTPException(409, "同名配置已存在")
        sets.append("name = ?")
        params.append(name)
    if body.licence is not None and body.licence.strip() != row["licence"]:
        if not LIC_RE.match(body.licence.strip()):
            raise HTTPException(400, "证书编号格式不正确")
        licence = body.licence.strip()
        sets.append("licence = ?")
        params.append(licence)
    toggled = False
    if body.enabled is not None and bool(body.enabled) != bool(row["enabled"]):
        toggled = True
        if body.enabled:                       # 单启用：先全关再开这一个
            with conn:
                conn.execute("UPDATE quote_source SET enabled = 0"
                             " WHERE user_id = ?", (user["id"],))
        sets.append("enabled = ?")
        params.append(1 if body.enabled else 0)
    if sets:
        sets.append("updated_at = ?")
        params.append(datetime.now().isoformat(timespec="seconds"))
        with conn:
            conn.execute("UPDATE quote_source SET " + ",".join(sets)
                         + " WHERE id = ?", (*params, sid))
    if toggled:
        log_op(user, "qsource_enable", "%s %s" % (name, "开" if body.enabled else "关"),
               client_ip(request), user_agent(request))
    elif sets:
        log_op(user, "qsource_edit", name, client_ip(request), user_agent(request))
    return {"ok": True}


@router.delete("/api/quotesettings/{sid}")
def source_delete(sid: int, request: Request, user=Depends(current_user)):
    """删除行情源（不存在也返回 ok，幂等）。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM quote_source WHERE id = ? AND user_id = ?",
            (sid, user["id"])).fetchone()
        conn.execute("DELETE FROM quote_source WHERE id = ? AND user_id = ?",
                     (sid, user["id"]))
    if row:
        log_op(user, "qsource_del", row["name"],
               client_ip(request), user_agent(request))
    return {"ok": True}


@router.post("/api/quotesettings/{sid}/test")
def source_test(sid: int, user=Depends(current_user)):
    """连通性测试：后端代理请求平安银行实时行情，回延迟与样例字段。"""
    row = get_conn().execute(
        "SELECT * FROM quote_source WHERE id = ? AND user_id = ?",
        (sid, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "配置不存在")
    if row["provider"] not in PROVIDERS:
        return {"ok": False, "error": "暂不支持该服务商"}
    t0 = time.monotonic()
    try:
        rows = _mairui_fetch(row["licence"], ["000001"])
        ms = int((time.monotonic() - t0) * 1000)
        s = rows[0] if rows else {}
        return {"ok": True, "latency_ms": ms,
                "sample": {"code": "000001", "p": s.get("f2"),
                           "pc": s.get("f3"), "hs": s.get("f8"), "t": s.get("t")}}
    except Exception as e:
        return {"ok": False, "latency_ms": int((time.monotonic() - t0) * 1000),
                "error": str(e)[:200]}


# ===== 首页实时行情（按用户启用源代理，失败回落本地快照） =====

@router.get("/api/quote/realtime")
def quote_realtime(codes: str = Query(default="", max_length=1000),
                   user=Depends(current_user)):
    """我的自选实时行情：启用源 → 第三方实时；否则/失败 → 本地快照兜底。

    codes 缺省时取本人自选列表（首页自选条一次请求直达）；
    返回与 /api/watchlist 同一套东财字段名（f12/f14/f2/f3/f6/f8），
    另带 live（是否实时）与 source（数据源描述）供前端展示。
    """
    if (codes or "").strip():
        codelist = []
        for c in codes.split(","):
            c = c.strip()
            if not c:
                continue
            if not CODE_RE.match(c):
                raise HTTPException(400, "股票代码须为 6 位数字")
            codelist.append(c)
    else:   # 缺省 → 本人自选（按加选时间倒序，最多 50 只）
        codelist = [r["code"] for r in get_conn().execute(
            "SELECT code FROM watchlist WHERE user_id = ?"
            " ORDER BY created_at DESC LIMIT 50", (user["id"],)).fetchall()]
    codelist = list(dict.fromkeys(codelist))[:50]
    if not codelist:
        return {"rows": [], "source": None, "live": False, "error": None}

    src = get_conn().execute(
        "SELECT * FROM quote_source WHERE user_id = ? AND enabled = 1",
        (user["id"],)).fetchone()
    error, rows, source = None, [], None
    if src and src["provider"] in PROVIDERS:
        try:
            rows = _mairui_fetch(src["licence"], codelist)
            source = PROVIDERS[src["provider"]]["label"] + " · " + src["name"]
        except Exception as e:
            error = str(e)[:200]
    if rows:
        _attach_names(rows)
        by = {r["f12"]: r for r in rows}
        return {"rows": [by[c] for c in codelist if c in by],
                "source": source, "live": True, "error": error}
    # 回落：本地最新快照（收盘后也有数据，只是非实时）
    marks = ",".join("?" * len(codelist))
    snap = {r["code"]: r for r in get_conn().execute(
        "SELECT code, name, industry, f2, f3, f6, f8 FROM latest"
        " WHERE code IN (" + marks + ")", codelist).fetchall()}
    for c in codelist:
        r = snap.get(c)
        if r is None:
            continue
        rows.append({"f12": c, "f14": r["name"], "f100": r["industry"],
                     "f2": r["f2"], "f3": r["f3"], "f6": r["f6"],
                     "f8": r["f8"], "t": None})
    return {"rows": rows, "source": "东方财富快照", "live": False, "error": error}
