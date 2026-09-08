"""行情查询：筛选列表 / 元信息（行业统计+情绪统计） / 健康检查。

所有 /api/quote/* 需要登录且账号未被禁用。
返回行保留东财字段名（f12/f14/f2...），与前端现有渲染逻辑零改动兼容。
"""
import json
import math

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_conn
from ..security import current_user

router = APIRouter(tags=["quote"])

# 允许作为自定义指标过滤的列（市值/成交额原始单位是元，前端按亿过滤）
METRIC_COLS = {"f6", "f7", "f9", "f10", "f20", "f21", "f23", "f24", "f25"}
YI_COLS = {"f6", "f20", "f21"}

# 市场勾选值白名单（防止任意 fs 注入；多值用逗号分隔）
MARKET_FS = {
    "沪主板": "m:1+t:2",
    "深主板": "m:0+t:6",
    "创业板": "m:0+t:80",
    "科创板": "m:1+t:23",
    "北交所": "m:0+t:81+s:2048",
}
ALLOWED_FS = set(MARKET_FS.values())


def _parse_markets(markets):
    if not markets:
        return []
    vals = [m for m in markets.split(",") if m]
    if any(m not in ALLOWED_FS for m in vals):
        raise HTTPException(400, "非法市场参数")
    return vals


def _market_where(vals):
    """fs 值 → market 中文名过滤。"""
    if not vals:
        return "", []
    fs2name = {v: k for k, v in MARKET_FS.items()}
    names = [fs2name[v] for v in vals]
    return " AND market IN (" + ",".join("?" for _ in names) + ")", names


def _to_float(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _parse_metrics(raw):
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "metrics 参数不是合法 JSON")
    out = []
    for m in items if isinstance(items, list) else []:
        k = m.get("k") if isinstance(m, dict) else None
        if k not in METRIC_COLS:
            continue
        lo, hi = _to_float(m.get("min")), _to_float(m.get("max"))
        if lo is None and hi is None:
            continue                      # 未设区间的指标仅展示不过滤（同前端）
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo               # 区间填反自动交换（同前端 range()）
        out.append({"k": k, "min": lo, "max": hi})
    return out


def build_filter_sql(args):
    """筛选 SQL（参数化，可单测）。规则与前端 filtered() 完全对齐。"""
    where, params = ["f2 IS NOT NULL"], []
    mw, mp = _market_where(args["markets"])
    where.append("1=1" + mw)
    params += mp
    if args["no_st"]:
        where.append("name NOT LIKE '%ST%' AND name NOT LIKE '%退%'")
    if args["no_suspend"]:
        where.append("f8 > 0")
    for col, lo, hi in (("f8", args["tmin"], args["tmax"]),
                        ("f3", args["cmin"], args["cmax"])):
        if lo is not None:
            where.append(col + " >= ?")
            params.append(lo)
        if hi is not None:
            where.append(col + " <= ?")
            params.append(hi)
    if args["industry"]:
        where.append("industry = ?")
        params.append(args["industry"])
    if args["kw"]:
        where.append("(code LIKE ? OR name LIKE ?)")
        params += ["%" + args["kw"] + "%"] * 2
    for m in args["metrics"]:
        # 无数据的行视为不达标（同前端 metricPass）
        expr = "(%s / 100000000.0)" % m["k"] if m["k"] in YI_COLS else m["k"]
        where.append(expr + " IS NOT NULL")
        lo, hi = m["min"], m["max"]
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo                   # 区间填反自动交换（防御,前端 range() 已处理）
        if lo is not None:
            where.append(expr + " >= ?")
            params.append(lo)
        if hi is not None:
            where.append(expr + " <= ?")
            params.append(hi)
    return " WHERE " + " AND ".join(where), params


def _row_to_fkeys(r):
    d = dict(r)
    d["f12"], d["f14"], d["f100"] = d.pop("code"), d.pop("name"), d.pop("industry")
    return d


def _snapshot_meta():
    row = get_conn().execute("SELECT * FROM snapshot_meta WHERE id = 1").fetchone()
    return dict(row) if row else {"fetched_at": None, "source": None,
                                  "total": 0, "ok": 0, "error": None}


@router.get("/api/quote/list")
def quote_list(
    markets: str | None = Query(default=None),
    tmin: float | None = None, tmax: float | None = None,
    cmin: float | None = None, cmax: float | None = None,
    industry: str | None = Query(default=None, max_length=32),
    kw: str | None = Query(default=None, max_length=32),
    no_st: bool = True, no_suspend: bool = True,
    metrics: str | None = Query(default=None, max_length=2000),
    limit: int = Query(default=5000, ge=1, le=10000),
    user=Depends(current_user),
):
    args = {
        "markets": _parse_markets(markets),
        "tmin": tmin, "tmax": tmax, "cmin": cmin, "cmax": cmax,
        "industry": industry or None, "kw": (kw or "").strip() or None,
        "no_st": no_st, "no_suspend": no_suspend,
        "metrics": _parse_metrics(metrics),
    }
    where, params = build_filter_sql(args)
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM latest" + where, params).fetchone()["c"]
    rows = conn.execute(
        "SELECT * FROM latest" + where + " ORDER BY f8 DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    meta = _snapshot_meta()
    return {
        "total": total,
        "rows": [_row_to_fkeys(r) for r in rows],
        "fetched_at": meta["fetched_at"],
        "source": meta["source"],
        "stale": not bool(meta["ok"]),
    }


# 涨跌停标记由 fetcher 按 最新价 vs 东财涨/跌停价(f350/f351) 判定写入。
# 统计口径与同花顺一致:涨跌停家数剔除 ST 股(北交所计入);
# 上涨/下跌/大跌不过滤 ST。
@router.get("/api/quote/meta")
def quote_meta(markets: str | None = Query(default=None),
               user=Depends(current_user)):
    """行业计数 + 情绪统计（对所选市场的完整快照计算，与筛选条件无关）。"""
    mw, mp = _market_where(_parse_markets(markets))
    where = " WHERE f2 IS NOT NULL" + mw
    conn = get_conn()
    inds = conn.execute(
        "SELECT industry AS name, COUNT(*) AS n FROM latest" + where +
        " AND industry IS NOT NULL GROUP BY industry ORDER BY n DESC", mp,
    ).fetchall()
    stats = conn.execute(
        "SELECT COUNT(*) AS valid,"
        " SUM(CASE WHEN f3 > 0 THEN 1 ELSE 0 END) AS up,"
        " SUM(CASE WHEN f3 < 0 THEN 1 ELSE 0 END) AS down,"
        " SUM(CASE WHEN f3 <= -5 THEN 1 ELSE 0 END) AS big_down,"
        " SUM(CASE WHEN limit_up = 1 AND name NOT LIKE '%ST%'"
        "     THEN 1 ELSE 0 END) AS limit_up,"
        " SUM(CASE WHEN limit_down = 1 AND name NOT LIKE '%ST%'"
        "     THEN 1 ELSE 0 END) AS limit_down"
        " FROM latest" + where + " AND f3 IS NOT NULL", mp,
    ).fetchone()
    meta = _snapshot_meta()
    return {
        "fetched_at": meta["fetched_at"], "source": meta["source"],
        "stale": not bool(meta["ok"]), "error": meta["error"],
        "snapshot_total": meta["total"],
        "industries": [dict(r) for r in inds],
        "stats": {k: (stats[k] or 0) for k in
                  ("valid", "up", "down", "big_down", "limit_up", "limit_down")},
    }


@router.get("/api/health")
def health():
    meta = _snapshot_meta()
    return {"status": "ok", **meta}
