"""个股日K抓取与本地缓存（涨停雷达的基因/前高判定用）。

数据源与前端分析层同源：东财 push2his 日K（前复权）→ 腾讯 fqkline（前复权）兜底。
前复权口径以最近一个交易日的真实价为锚、向前调整历史价，因此历史前高/
涨跌停判定可直接与快照价（f2/f350）比较。

结果按 (code, date) 落 kline 表，kline_meta 记录每票最后抓取日期：
当天内重复查询直接读缓存不触网；跨天或缓存为空时才请求远端，
远端失败时退化返回陈旧缓存（有总比没有强）。
"""
import logging
import time
from datetime import datetime

import requests

from . import db

log = logging.getLogger("kline")

EM_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EM_FIELDS1 = "f1,f2,f3,f4,f5,f6"
# f51 日期 f52 开 f53 收 f54 高 f55 低 f56 量 f57 额 f58 振幅 f59 涨跌幅 f60 涨跌额 f61 换手
EM_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
TX_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
RETRY = 2

# 与 fetcher 同样 trust_env=False 忽略系统代理（代理出口会被分配到行为不同的节点）
_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
})


def _secid(code: str) -> str:
    """东财 secid：沪 1. / 深、北 0.（与前端 analysis/data.js 一致）。"""
    return ("1." if code.startswith("6") else "0.") + code


def _tx_code(code: str) -> str:
    """腾讯行情代码：sh/sz/bj 前缀。"""
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return "sz" + code


def _bar(date, open_, high, low, close, vol, amount, pct):
    return {"date": date, "open": open_, "high": high, "low": low,
            "close": close, "vol": vol, "amount": amount, "pct": pct}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_em(data: dict) -> list[dict]:
    """东财 klines 字符串数组 → bar 列表（升序，收盘无效的行剔除）。"""
    bars = []
    for s in (data or {}).get("klines") or []:
        a = s.split(",")
        if len(a) < 9:
            continue
        close = _num(a[2])
        if close is None:
            continue
        bars.append(_bar(a[0], _num(a[1]), _num(a[3]), _num(a[4]),
                         close, _num(a[5]), _num(a[6]), _num(a[8])))
    return bars


def _parse_tx(arr: list) -> list[dict]:
    """腾讯 fqkline 数组 → bar 列表；无涨跌幅字段，由前复权收盘价推算。"""
    bars = []
    for a in arr or []:
        if len(a) < 6:
            continue
        close = _num(a[2])
        if close is None:
            continue
        bars.append(_bar(a[0], _num(a[1]), _num(a[3]), _num(a[4]),
                         close, _num(a[5]), None, None))
    for i, b in enumerate(bars):
        prev = bars[i - 1]["close"] if i else None
        if prev and b["close"]:
            b["pct"] = round((b["close"] / prev - 1) * 100, 4)
    return bars


def _fetch_em(code: str, days: int) -> list[dict]:
    r = _session.get(EM_URL, params={
        "secid": _secid(code), "klt": 101, "fqt": 1, "lmt": days,
        "end": 20500101, "fields1": EM_FIELDS1, "fields2": EM_FIELDS2,
    }, timeout=8)
    r.raise_for_status()
    bars = _parse_em((r.json() or {}).get("data"))
    if not bars:
        raise ValueError("empty klines")
    return bars


def _fetch_tx(code: str, days: int) -> list[dict]:
    tx = _tx_code(code)
    r = _session.get(TX_URL, params={
        "param": "%s,day,,,%d,qfq" % (tx, days)}, timeout=8)
    r.raise_for_status()
    node = ((r.json() or {}).get("data") or {}).get(tx) or {}
    bars = _parse_tx(node.get("qfqday") or node.get("day"))
    if not bars:
        raise ValueError("empty klines")
    return bars


def _fetch_remote(code: str, days: int) -> list[dict]:
    """东财 → 腾讯两级取数，带重试；全失败抛最后一次异常。"""
    last_err = None
    for attempt in range(RETRY + 1):
        for fetch in (_fetch_em, _fetch_tx):
            try:
                return fetch(code, days)
            except Exception as e:  # noqa: BLE001
                last_err = e
        if attempt < RETRY:
            time.sleep(0.5)
    log.warning("kline fetch failed %s: %s", code, last_err)
    raise last_err


def _cached_bars(conn, code: str, days: int) -> list[dict]:
    rows = conn.execute(
        "SELECT date, open, high, low, close, vol, amount, pct FROM kline"
        " WHERE code = ? ORDER BY date DESC LIMIT ?",
        (code, days)).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_bars(code: str, days: int = 250) -> list[dict]:
    """个股日K（升序）。当天已抓过直接读缓存；否则触网刷新，失败退化陈旧缓存。"""
    conn = db.get_conn()
    today = datetime.now().date().isoformat()
    meta = conn.execute(
        "SELECT fetched_date FROM kline_meta WHERE code = ?", (code,)).fetchone()
    if not (meta and meta["fetched_date"] == today):
        try:
            bars = _fetch_remote(code, days)
        except Exception:  # noqa: BLE001 — 退化到陈旧缓存
            pass
        else:
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO kline"
                    " (code, date, open, high, low, close, vol, amount, pct)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    [[code, b["date"], b["open"], b["high"], b["low"],
                      b["close"], b["vol"], b["amount"], b["pct"]]
                     for b in bars],
                )
                conn.execute(
                    "INSERT OR REPLACE INTO kline_meta (code, fetched_date)"
                    " VALUES (?, ?)", (code, today))
    return _cached_bars(conn, code, days)
