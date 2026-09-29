"""龙虎榜采集与席位画像（数据源：东财数据中心 datacenter-web，实测服务器/浏览器均可达）。

每日榜单 RPT_DAILYBILLBOARD_DETAILS（个股上榜汇总，同股同日可多原因多条）
席位明细 RPT_BILLBOARD_DAILYDETAILSBUY / ...SELL（营业部买卖榜）

发布窗口约收盘后 16:30-18:00：collect_job 在 18/19/20 点各试一次，
已有足够行则跳过（重试为 no-op）。首次运行 backfill 回填约 60 个交易日。

席位胜率口径：t_close 取 kline 表前复权收盘（与次日涨跌幅口径自洽，
不与榜单原始价混算）；次日开/高/收同样来自 kline。stats_job 每个交易日
15:20（history 落库后）回填近期待定结果并重建 lhb_seat_stat。
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta

import requests

from . import db, kline

log = logging.getLogger("lhb")

BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
      "Referer": "https://data.eastmoney.com/"}

# 与 fetcher/kline 同样 trust_env=False 忽略系统代理
_session = requests.Session()
_session.trust_env = False
_session.headers.update(UA)

PAGE_SIZE = 500
RETRY = 2
MIN_ROWS_DONE = 20   # 当日榜单达到此行数视为已采集完整,后续重试跳过

_backfill_started = False
_backfill_lock = threading.Lock()


def _now_shanghai() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return datetime.now()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date10(v) -> str:
    return str(v or "")[:10]


# ---------- 席位标签 ----------
# 自动标签:由席位名称确定性推导(机构专用/沪深股通/自营),口径可靠;
# 游资标签:来自管理员维护的 lhb_famous_seat 网传映射——没有任何公开权威
# 数据源提供游资席位归属,故一律标注"网传"口径,优先级高于自动标签。
AUTO_TAGS = (
    ("机构专用", "机构"),
    ("沪股通", "北向"),
    ("深股通", "北向"),
    ("自营", "自营"),
)


def famous_map(conn) -> dict:
    """网传游资映射 {dept_name: alias};老库缺表时视为空。"""
    try:
        return {r["dept_name"]: r["alias"] for r in conn.execute(
            "SELECT dept_name, alias FROM lhb_famous_seat").fetchall()}
    except Exception:  # noqa: BLE001 - sqlite OperationalError(no such table)
        return {}


def tag_of(dept_name: str, famous: dict | None = None) -> dict | None:
    """席位标签:游资(网传映射) > 机构/北向/自营(名称推导);无标签返回 None。"""
    if famous and dept_name in famous:
        return {"tag": "游资", "alias": famous[dept_name], "src": "网传"}
    for kw, tag in AUTO_TAGS:
        if kw in dept_name:
            return {"tag": tag}
    return None


def _get(report: str, date: str, page: int, sort_col: str = None):
    """单页拉取,返回 (rows, pages);空结果返回 ([], 0)。"""
    params = {
        "reportName": report,
        "columns": "ALL",
        "filter": "(TRADE_DATE='%s')" % date,
        "pageNumber": page,
        "pageSize": PAGE_SIZE,
        "source": "DataCenter",
    }
    if sort_col:
        params["sortColumns"] = sort_col
        params["sortTypes"] = "-1"
    r = _session.get(BASE, params=params, timeout=10)
    r.raise_for_status()
    d = r.json() or {}
    res = d.get("result") or {}
    return res.get("data") or [], res.get("pages") or 0


def _get_all(report: str, date: str, sort_col: str = None) -> list:
    """分页拉满,带重试;全失败抛最后一次异常。"""
    rows, page, pages = [], 1, 1
    last_err = None
    while page <= pages:
        for attempt in range(RETRY + 1):
            try:
                chunk, pages = _get(report, date, page, sort_col)
                rows.extend(chunk)
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < RETRY:
                    time.sleep(0.5)
        if last_err:
            raise last_err
        page += 1
        if page <= pages:
            time.sleep(0.3)   # 翻页礼貌间隔
    return rows


def fetch_daily(date: str) -> list:
    return _get_all("RPT_DAILYBILLBOARD_DETAILS", date, "BILLBOARD_NET_AMT")


def fetch_seats(date: str) -> list:
    """买卖两侧席位明细合并,每条附加 side 字段('B'/'S')。"""
    out = []
    for report, side in (("RPT_BILLBOARD_DAILYDETAILSBUY", "B"),
                         ("RPT_BILLBOARD_DAILYDETAILSSELL", "S")):
        for r in _get_all(report, date):
            r["side"] = side
            out.append(r)
    return out


def ingest_date(conn, date: str) -> int:
    """采集某日榜单+席位入库(INSERT OR REPLACE 幂等)。返回榜单行数。"""
    items = fetch_daily(date)
    seats = fetch_seats(date)
    now = datetime.now().isoformat(timespec="seconds")
    with conn:
        conn.executemany(
            "INSERT OR REPLACE INTO lhb_item"
            " (trade_date, code, name, explain, close_price, change_rate,"
            "  net_amt, buy_amt, sell_amt, accum_amount, turnover_rate, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [[date, r.get("SECURITY_CODE"), r.get("SECURITY_NAME_ABBR"),
              r.get("EXPLAIN"), _num(r.get("CLOSE_PRICE")), _num(r.get("CHANGE_RATE")),
              _num(r.get("BILLBOARD_NET_AMT")), _num(r.get("BILLBOARD_BUY_AMT")),
              _num(r.get("BILLBOARD_SELL_AMT")), _num(r.get("ACCUM_AMOUNT")),
              _num(r.get("TURNOVERRATE")), now]
             for r in items if r.get("SECURITY_CODE")],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO lhb_seat"
            " (trade_date, code, name, side, dept_code, dept_name, buy, sell, net)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [[date, r.get("SECURITY_CODE"), r.get("SECURITY_NAME_ABBR"),
              r["side"], str(r.get("OPERATEDEPT_CODE") or ""),
              (r.get("OPERATEDEPT_NAME") or "").strip(),
              _num(r.get("BUY")), _num(r.get("SELL")), _num(r.get("NET"))]
             for r in seats if r.get("SECURITY_CODE") and r.get("OPERATEDEPT_NAME")],
        )
    log.info("lhb %s: %d items, %d seat rows", date, len(items), len(seats))
    return len(items)


def collect_job(force: bool = False) -> None:
    """收盘后榜单采集(18-20 点整点重试由调度器控制)。"""
    now = _now_shanghai()
    if now.weekday() >= 5:
        return
    today = now.date().isoformat()
    conn = db.get_conn()
    cnt = conn.execute(
        "SELECT COUNT(*) AS c FROM lhb_item WHERE trade_date = ?",
        (today,)).fetchone()["c"]
    if cnt >= MIN_ROWS_DONE and not force:
        return
    try:
        n = ingest_date(conn, today)
        if n == 0:
            log.info("lhb %s not published yet", today)
    except Exception as e:  # noqa: BLE001 - 采集失败不影响主业务,下个整点重试
        log.error("lhb collect failed: %s", e)


def backfill(days: int = 60) -> None:
    """首次运行(空表)回填近 N 个日历日(跳过周末),daemon 线程调用。"""
    global _backfill_started
    with _backfill_lock:
        if _backfill_started:
            return
        _backfill_started = True
    conn = db.get_conn()
    if conn.execute("SELECT COUNT(*) AS c FROM lhb_item").fetchone()["c"] > 0:
        return
    log.info("lhb backfill start: %d days", days)
    d = _now_shanghai().date() - timedelta(days=1)   # 今日榜单未发布,从昨日回退
    done = 0
    while done < days and d > d - timedelta(days=days * 2):
        if d.weekday() < 5:
            try:
                ingest_date(conn, d.isoformat())
                done += 1
            except Exception as e:  # noqa: BLE001 - 单日失败跳过继续
                log.warning("lhb backfill %s failed: %s", d, e)
            time.sleep(1.0)   # 礼貌间隔
        d -= timedelta(days=1)
    log.info("lhb backfill done: %d days", done)
    stats_job()   # 回填完顺手算一遍席位画像


def fill_outcomes(conn, today: str) -> int:
    """回填席位出场的次日表现(T+1 开/高/低/收,来自 kline 前复权序列)。

    每次运行处理近 30 个自然日内尚未回填的 (code, trade_date) 组合,
    单票日K当天内走 kline 缓存不重复触网。返回回填条数。
    """
    since = (_now_shanghai().date() - timedelta(days=30)).isoformat()
    pending = conn.execute(
        "SELECT DISTINCT code, trade_date FROM lhb_seat"
        " WHERE t1_close IS NULL AND trade_date < ? AND trade_date >= ?"
        " ORDER BY trade_date DESC LIMIT 400",
        (today, since)).fetchall()
    filled = 0
    for row in pending:
        code, tdate = row["code"], row["trade_date"]
        try:
            bars = kline.get_bars(code, 60)
        except Exception as e:  # noqa: BLE001 - 单票失败跳过
            log.warning("lhb outcome kline %s failed: %s", code, e)
            continue
        idx = next((i for i, b in enumerate(bars) if b["date"] == tdate), None)
        if idx is None or idx + 1 >= len(bars):
            continue   # T 日缺失或 T+1 尚未发生
        t, t1 = bars[idx], bars[idx + 1]
        if not t.get("close"):
            continue
        with conn:
            cur = conn.execute(
                "UPDATE lhb_seat SET t_close=?, t1_open=?, t1_high=?, t1_low=?,"
                " t1_close=?, filled_at=? WHERE code=? AND trade_date=?",
                (t["close"], t1.get("open"), t1.get("high"), t1.get("low"),
                 t1.get("close"), datetime.now().isoformat(timespec="seconds"),
                 code, tdate))
        filled += cur.rowcount
    if filled:
        log.info("lhb outcomes filled: %d seat rows", filled)
    return filled


def recompute_stats(conn) -> int:
    """重建 lhb_seat_stat(全量 DELETE+INSERT,席位量级千级,秒级完成)。

    appearances 计全部出场;胜率/溢价仅用已回填次日结果的样本。
    偏好个股/联动席位仅对出场 ≥3 次的席位计算(长尾席位无画像价值)。
    """
    now = datetime.now().isoformat(timespec="seconds")
    aggs = conn.execute(
        "SELECT dept_name, COUNT(*) AS apps,"
        " SUM(CASE WHEN t1_close IS NOT NULL AND t_close > 0"
        "          AND t1_close > t_close THEN 1 ELSE 0 END) AS wins,"
        " SUM(CASE WHEN t1_close IS NOT NULL AND t_close > 0 THEN 1 ELSE 0 END) AS judged,"
        " AVG(CASE WHEN t1_close IS NOT NULL AND t_close > 0"
        "     THEN t1_open / t_close - 1 END) AS avg_open,"
        " AVG(CASE WHEN t1_close IS NOT NULL AND t_close > 0"
        "     THEN t1_close / t_close - 1 END) AS avg_close,"
        " AVG(CASE WHEN t1_close IS NOT NULL AND t_close > 0"
        "     THEN t1_high / t_close - 1 END) AS avg_max,"
        " SUM(net) AS total_net, MAX(trade_date) AS last_date"
        " FROM lhb_seat GROUP BY dept_name").fetchall()
    rows = []
    for a in aggs:
        dept, apps = a["dept_name"], a["apps"]
        judged = a["judged"] or 0
        top_stocks, co_seats = [], []
        if apps >= 3:
            top_stocks = [dict(r) for r in conn.execute(
                "SELECT code, MAX(name) AS name, COUNT(*) AS n FROM lhb_seat"
                " WHERE dept_name = ? GROUP BY code ORDER BY n DESC LIMIT 5",
                (dept,)).fetchall()]
            co_seats = [dict(r) for r in conn.execute(
                "SELECT s2.dept_name AS dept, COUNT(*) AS n"
                " FROM lhb_seat s1 JOIN lhb_seat s2"
                "   ON s1.trade_date = s2.trade_date AND s1.code = s2.code"
                "  AND s2.dept_name != s1.dept_name"
                " WHERE s1.dept_name = ?"
                " GROUP BY s2.dept_name ORDER BY n DESC LIMIT 5",
                (dept,)).fetchall()]
        rows.append((dept, apps, a["wins"] or 0,
                     (a["wins"] or 0) / judged if judged else None,
                     a["avg_open"], a["avg_close"], a["avg_max"],
                     a["total_net"], a["last_date"],
                     json.dumps(top_stocks, ensure_ascii=False),
                     json.dumps(co_seats, ensure_ascii=False), now))
    with conn:
        conn.execute("DELETE FROM lhb_seat_stat")
        conn.executemany(
            "INSERT INTO lhb_seat_stat"
            " (dept_name, appearances, win_cnt, win_rate, avg_open_premium,"
            "  avg_close_pct, avg_max_premium, total_net, last_date,"
            "  top_stocks, co_seats, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    log.info("lhb seat stats rebuilt: %d seats", len(rows))
    return len(rows)


def stats_job() -> None:
    """每个交易日 15:20(history 落库后):回填次日结果 + 重建席位画像。"""
    now = _now_shanghai()
    if now.weekday() >= 5:
        return
    conn = db.get_conn()
    try:
        fill_outcomes(conn, now.date().isoformat())
        recompute_stats(conn)
    except Exception as e:  # noqa: BLE001 - 统计失败不影响主业务
        log.error("lhb stats failed: %s", e)
