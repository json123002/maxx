"""同花顺挂单异动采集器(L2:特大挂买/撤单/压托单)。

源站 market-events 是"滚动 200 条"的全市场事件流(实测仅覆盖约 5 秒),
由调度器在交易时段每 5 秒轮询,按 eventId 去重后累积当日异动。
全市场日事件量几十万条,只保留「工作台 ∪ 自选」池内股票(集合 5 分钟刷新)。
纯内存态:eventDate 变化自动重置;盘中启动只含启动之后的事件。
"""
import logging
import threading
import time
from datetime import datetime

import requests

from .db import get_conn

log = logging.getLogger("thsflow")

URL = "https://stockpage.10jqka.com.cn/stock_page/api/v1/stockpage/market-events/"
CODES_TTL = 300  # 关注股票集合缓存秒数

_session = requests.Session()
_session.trust_env = False
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://stockpage.10jqka.com.cn/",
})

_lock = threading.Lock()
_day = ""          # 当前累积的交易日(eventDate)
_events = {}       # code -> [{time,type,value}, ...]
_seen = set()      # 当日已见 eventId(去重)
_codes = set()     # 关注股票集合(工作台 ∪ 自选)
_codes_at = 0.0    # 集合上次刷新时间

# 内存上限保护：本模块状态只活在内存里，须有硬顶（OOM 教训 2026-10-23）。
SEEN_MAX = 400_000          # 当日去重集合条数上限（实测全市场日事件几十万条）
EVENTS_PER_CODE_MAX = 300   # 单股当日保留事件条数上限


def _watch_codes() -> set:
    """关注股票集合(5 分钟缓存;查库失败沿用旧值)。"""
    global _codes_at
    if _codes and time.time() - _codes_at < CODES_TTL:
        return _codes
    try:
        rows = get_conn().execute(
            "SELECT code FROM desk_stock UNION SELECT code FROM watchlist"
        ).fetchall()
        codes = {r["code"] for r in rows}
        if codes:
            with _lock:
                _codes.clear()
                _codes.update(codes)
            _codes_at = time.time()
    except Exception as e:  # noqa: BLE001 - 失败沿用旧集合
        log.warning("ths watch codes refresh failed: %s", e)
    return _codes


def collect_job(force: bool = False) -> bool:
    """拉一次全市场事件流并累积。force=True 跳过交易时段判断(启动时补一次)。"""
    global _day
    now = datetime.now()
    if not force:
        if now.weekday() >= 5:
            return False
        mins = now.hour * 60 + now.minute
        if not ((9 * 60 + 15 <= mins <= 11 * 60 + 30)
                or (13 * 60 <= mins <= 15 * 60 + 5)):
            return False
    watch = _watch_codes()
    if not watch:
        return False
    try:
        # code/marketId 为接口必传参数但对事件流无过滤作用,固定传平安银行
        r = _session.get(URL, params={"code": "000001", "marketId": "33"},
                         timeout=8)
        d = r.json() if r.ok else {}
        data = d.get("data") if d.get("status_code") == 0 else None
    except Exception as e:  # noqa: BLE001 - 源站异常本轮放弃,下轮重试
        log.warning("ths events fetch failed: %s", e)
        return False
    if data is None:
        return False
    added = 0
    with _lock:
        today = data.get("eventDate") or now.date().isoformat()
        if _day != today:  # 换交易日:清空重新累积
            _events.clear()
            _seen.clear()
        _day = today
        if len(_seen) > SEEN_MAX:
            # 防内存无限增长:超限清空去重集合。代价是滚动窗口(约 5 秒)内的
            # 极近期事件可能重复累积一次,可接受
            _seen.clear()
        for e in data.get("list") or []:
            eid, code = e.get("eventId"), e.get("stockCode")
            if not eid or code not in watch or eid in _seen:
                continue
            _seen.add(eid)
            ev = _events.setdefault(code, [])
            if len(ev) >= EVENTS_PER_CODE_MAX:
                continue
            ev.append({
                "time": e.get("eventTime") or "",
                "type": e.get("eventName") or "",
                "value": e.get("eventValue") or "",
            })
            added += 1
    if added:
        log.info("ths events collected: +%s (%s)", added, _day)
    return True


def events_of(code: str) -> dict:
    """该股当日已累积的挂单异动(时间升序)。"""
    with _lock:
        rows = sorted(_events.get(code) or [], key=lambda x: x["time"])
        return {"code": code, "date": _day, "events": rows}
