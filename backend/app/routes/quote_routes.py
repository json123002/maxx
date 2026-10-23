"""行情查询：筛选列表 / 元信息（行业统计+情绪统计） / 单股快照 / 健康检查。

所有 /api/quote/* 需要登录且账号未被禁用。
返回行保留东财字段名（f12/f14/f2...），与前端现有渲染逻辑零改动兼容。
"""
from datetime import datetime
import json
import math
import re

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


def _is_call_auction(now: datetime = None) -> bool:
    """是否处于早盘集合竞价时段 (09:15 - 09:25)。"""
    try:
        from zoneinfo import ZoneInfo
        now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= mins < 9 * 60 + 25


def build_filter_sql(args):
    """筛选 SQL（参数化，可单测）。规则与前端 filtered() 完全对齐。"""
    where, params = ["f2 IS NOT NULL"], []
    mw, mp = _market_where(args["markets"])
    where.append("1=1" + mw)
    params += mp
    if args["no_st"]:
        where.append("name NOT LIKE '%ST%' AND name NOT LIKE '%退%'")
    if args["no_suspend"]:
        # 集合竞价时段(09:15-09:25)成交未开始、换手均为0，不可用 f8 > 0 过滤，否则会误剔全市场个股
        if args.get("is_auction"):
            where.append("f2 IS NOT NULL")
        else:
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
        marks = ",".join("?" * len(args["industry"]))
        where.append("industry IN (" + marks + ")")
        params += args["industry"]
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
    industry: str | None = Query(default=None, max_length=200),
    kw: str | None = Query(default=None, max_length=32),
    no_st: bool = True, no_suspend: bool = True,
    metrics: str | None = Query(default=None, max_length=2000),
    limit: int = Query(default=5000, ge=1, le=10000),
    user=Depends(current_user),
):
    is_auction = _is_call_auction()
    args = {
        "markets": _parse_markets(markets),
        "tmin": tmin, "tmax": tmax, "cmin": cmin, "cmax": cmax,
        "industry": [x for x in (industry or "").split(",") if x][:10] or None,
        "kw": (kw or "").strip() or None,
        "no_st": no_st, "no_suspend": no_suspend,
        "metrics": _parse_metrics(metrics),
        "is_auction": is_auction,
    }
    where, params = build_filter_sql(args)
    conn = get_conn()
    # 黑名单:服务端直接剔除(不计入 total、不出现在行内)
    bl = [r["code"] for r in conn.execute(
        "SELECT code FROM blacklist WHERE user_id = ?", (user["id"],)).fetchall()]
    if bl:
        where += " AND code NOT IN (" + ",".join("?" * len(bl)) + ")"
        params += bl
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM latest" + where, params).fetchone()["c"]
    order_col = "ABS(f3) DESC" if is_auction else "f8 DESC"
    rows = conn.execute(
        f"SELECT * FROM latest{where} ORDER BY {order_col} LIMIT ?",
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
        " SUM(CASE WHEN f3 = 0 THEN 1 ELSE 0 END) AS flat,"
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
                  ("valid", "up", "down", "flat", "big_down",
                   "limit_up", "limit_down")},
    }


@router.get("/api/quote/sector-strength")
def quote_sector_strength(user=Depends(current_user)):
    """全市场行业板块强度统计：客观聚合各行业涨跌幅、赚钱效应广度、涨停家数与领涨龙头。"""
    conn = get_conn()
    query = """
    WITH TopStock AS (
      SELECT industry, code, name, f3,
             ROW_NUMBER() OVER (PARTITION BY industry ORDER BY f3 DESC) as rn
      FROM latest
      WHERE f2 IS NOT NULL AND industry IS NOT NULL AND industry != '' AND industry != '-'
    ),
    Agg AS (
      SELECT 
        industry,
        COUNT(*) as total,
        SUM(CASE WHEN f3 > 0 THEN 1 ELSE 0 END) as up_cnt,
        SUM(CASE WHEN f3 < 0 THEN 1 ELSE 0 END) as down_cnt,
        SUM(CASE WHEN limit_up = 1 AND name NOT LIKE '%ST%' THEN 1 ELSE 0 END) as limit_up_cnt,
        ROUND(AVG(f3), 2) as avg_chg,
        ROUND(SUM(f6) / 100000000.0, 2) as amt_yi,
        ROUND(AVG(f8), 2) as avg_tov
      FROM latest
      WHERE industry IS NOT NULL AND industry != '' AND industry != '-' AND f2 IS NOT NULL
      GROUP BY industry
    )
    SELECT 
      a.industry, a.total, a.up_cnt, a.down_cnt,
      (a.total - a.up_cnt - a.down_cnt) as flat_cnt,
      a.limit_up_cnt, a.avg_chg, a.amt_yi, a.avg_tov,
      t.code as top_code, t.name as top_name, t.f3 as top_chg
    FROM Agg a
    LEFT JOIN TopStock t ON a.industry = t.industry AND t.rn = 1
    ORDER BY a.avg_chg DESC
    """
    rows = conn.execute(query).fetchall()
    meta = _snapshot_meta()
    
    total_sectors = len(rows)
    up_sectors = sum(1 for r in rows if (r["avg_chg"] or 0) > 0)
    down_sectors = sum(1 for r in rows if (r["avg_chg"] or 0) < 0)
    
    return {
        "fetched_at": meta["fetched_at"],
        "source": meta["source"],
        "summary": {
            "total_sectors": total_sectors,
            "up_sectors": up_sectors,
            "down_sectors": down_sectors,
            "flat_sectors": total_sectors - up_sectors - down_sectors,
            "top_sector": rows[0]["industry"] if rows else "",
            "top_gain": rows[0]["avg_chg"] if rows else 0,
        },
        "rows": [dict(r) for r in rows],
    }


@router.get("/api/quote/stock/{code}")
def quote_stock(code: str, user=Depends(current_user)):
    """单股最新快照（个股详情页用）。"""
    if not re.fullmatch(r"\d{6}", code):
        raise HTTPException(400, "股票代码须为 6 位数字")
    row = get_conn().execute(
        "SELECT * FROM latest WHERE code = ?", (code,)).fetchone()
    if not row:
        raise HTTPException(404, "未找到该股票（可能已退市或代码有误）")
    return {"row": _row_to_fkeys(row)}


@router.get("/api/health")
def health():
    meta = _snapshot_meta()
    return {"status": "ok", **meta}


# ===== 历史榜单（每交易日 15:06 由调度器落收盘价到 history 表）=====
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("/api/quote/history/dates")
def history_dates(user=Depends(current_user)):
    """可回看的交易日列表（新→旧，最多 60 天）。"""
    rows = get_conn().execute(
        "SELECT DISTINCT trade_date FROM history"
        " ORDER BY trade_date DESC LIMIT 60").fetchall()
    return {"dates": [r["trade_date"] for r in rows]}


ALLOWED_HISTORY_SORT = {
    "f8": "f8",
    "f2": "f2",
    "f3": "f3",
    "f6": "f6",
    "f20": "f20",
    "f12": "code",
    "code": "code",
    "f14": "name",
    "name": "name",
    "f100": "industry",
    "industry": "industry",
    "market": "market",
}


@router.get("/api/quote/history")
def history_list(
    date: str = Query(default=""),
    kw: str | None = Query(default=None, max_length=32),
    market: str | None = Query(default=None, max_length=64),
    pmin: float | None = None,
    pmax: float | None = None,
    cmin: float | None = None,
    cmax: float | None = None,
    tmin: float | None = None,
    tmax: float | None = None,
    no_st: bool = False,
    sort_by: str = Query(default="f8"),
    order: str = Query(default="desc"),
    limit: int = Query(default=6000, ge=1, le=10000),
    user=Depends(current_user),
):
    """某交易日的收盘榜单：支持板块、股价、涨跌、换手率全维筛选与服务端动态排序。"""
    raw_date = date.default if hasattr(date, "default") else date
    if not isinstance(raw_date, str) or not _DATE_RE.match(raw_date):
        raise HTTPException(400, "date 格式须为 YYYY-MM-DD")
    date_val = raw_date

    raw_kw = kw.default if hasattr(kw, "default") else kw
    kw_str = (raw_kw or "").strip() if isinstance(raw_kw, str) else ""

    raw_market = market.default if hasattr(market, "default") else market
    market_str = (raw_market or "").strip() if isinstance(raw_market, str) else ""

    raw_sort = sort_by.default if hasattr(sort_by, "default") else sort_by
    sort_str = str(raw_sort or "f8")

    raw_order = order.default if hasattr(order, "default") else order
    order_str = str(raw_order or "desc")

    raw_limit = limit.default if hasattr(limit, "default") else limit
    limit_val = int(raw_limit) if raw_limit is not None and not hasattr(raw_limit, "default") else 6000

    conn = get_conn()
    where = ["trade_date = ?"]
    params = [date_val]

    if kw_str:
        where.append("(code LIKE ? OR name LIKE ?)")
        params += ["%" + kw_str + "%"] * 2

    # 板块 / 市场过滤
    if market_str:
        mkt_list = []
        for m in market_str.split(","):
            m = m.strip()
            if m == "主板":
                mkt_list.extend(["沪主板", "深主板"])
            elif m in {"沪主板", "深主板", "创业板", "科创板", "北交所"}:
                mkt_list.append(m)
        if mkt_list:
            unique_mkts = list(dict.fromkeys(mkt_list))
            where.append("market IN (" + ",".join("?" for _ in unique_mkts) + ")")
            params += unique_mkts

    # 股价区间 (f2)
    if pmin is not None and pmax is not None and pmin > pmax:
        pmin, pmax = pmax, pmin
    if pmin is not None:
        where.append("f2 >= ?")
        params.append(pmin)
    if pmax is not None:
        where.append("f2 <= ?")
        params.append(pmax)

    # 涨跌幅区间 (f3)
    if cmin is not None and cmax is not None and cmin > cmax:
        cmin, cmax = cmax, cmin
    if cmin is not None:
        where.append("f3 >= ?")
        params.append(cmin)
    if cmax is not None:
        where.append("f3 <= ?")
        params.append(cmax)

    # 换手率区间 (f8)
    if tmin is not None and tmax is not None and tmin > tmax:
        tmin, tmax = tmax, tmin
    if tmin is not None:
        where.append("f8 >= ?")
        params.append(tmin)
    if tmax is not None:
        where.append("f8 <= ?")
        params.append(tmax)

    # 剔除 ST / 退市
    if no_st:
        where.append("name NOT LIKE '%ST%' AND name NOT LIKE '%退%'")

    where_sql = " WHERE " + " AND ".join(where)
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM history" + where_sql, params
    ).fetchone()["c"]

    col = ALLOWED_HISTORY_SORT.get(sort_str, "f8")
    dir_str = "ASC" if order_str.lower() == "asc" else "DESC"
    order_sql = f" ORDER BY CASE WHEN {col} IS NULL THEN 1 ELSE 0 END, {col} {dir_str}"

    rows = conn.execute(
        "SELECT * FROM history" + where_sql + order_sql + " LIMIT ?",
        (*params, limit_val),
    ).fetchall()
    stats = conn.execute(
        "SELECT COUNT(*) AS valid,"
        " SUM(CASE WHEN f3 > 0 THEN 1 ELSE 0 END) AS up,"
        " SUM(CASE WHEN f3 < 0 THEN 1 ELSE 0 END) AS down,"
        " SUM(CASE WHEN limit_up = 1 THEN 1 ELSE 0 END) AS limit_up,"
        " SUM(CASE WHEN limit_down = 1 THEN 1 ELSE 0 END) AS limit_down"
        " FROM history WHERE trade_date = ? AND f3 IS NOT NULL", (date_val,),
    ).fetchone()
    return {"date": date_val, "total": total,
            "rows": [_row_to_fkeys(r) for r in rows],
            "stats": {k: (stats[k] or 0)
                      for k in ("valid", "up", "down", "limit_up", "limit_down")}}
