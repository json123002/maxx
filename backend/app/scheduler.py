"""抓数调度：交易时段每 N 分钟刷 latest、每 30 秒采同花顺盘口异动；每交易日 15:06 落 history。"""
import logging
import threading
from datetime import datetime

import time

from apscheduler.schedulers.background import BackgroundScheduler

from . import config, db, fetcher, thsflow

log = logging.getLogger("scheduler")
_lock = threading.Lock()
_sched = None
_fail_streak = 0   # 主备源连续失败次数（用于退避降频）
_last_em_fail = 0.0  # 东财主源最近失败时间戳


def _now_shanghai() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return datetime.now()


def _is_trading_time(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return (9 * 60 + 15 <= mins <= 11 * 60 + 30) or (13 * 60 <= mins <= 15 * 60 + 5)


def _fetch_rows():
    """主源(东财)失败自动切腾讯兜底;若东财刚故障/封禁则短时间内直走腾讯,
    避免竞价等高频时段因反复尝试东财而阻塞或超时。都失败抛异常由 fetch_job 记录。"""
    global _last_em_fail
    now_ts = time.time()
    # 东财失败后 90 秒内直接走快速腾讯兜底，每 90 秒探活一次东财
    if now_ts - _last_em_fail > 90:
        try:
            res = fetcher.fetch_snapshot()
            _last_em_fail = 0.0
            return res
        except Exception as e:
            _last_em_fail = now_ts
            log.warning("eastmoney fetch failed: %s; switching to fast tencent fallback", e)
    return fetcher.fetch_snapshot_tx(db.latest_static())


def fetch_job(force: bool = False) -> bool:
    """抓一次快照。force=True 跳过交易时段判断（启动时/手动触发）。

    主备源连续失败 ≥10 次后进入低频探测(约每 30 分钟试一次),
    既给封禁类故障留解封时间,也避免无效请求持续打满日志。
    """
    global _fail_streak
    now = _now_shanghai()
    if not force and not _is_trading_time(now):
        return False
    if not force and _fail_streak >= 10:
        _fail_streak += 1
        if _fail_streak % 10:
            return False
    if not _lock.acquire(blocking=False):
        return False
    try:
        rows, source = _fetch_rows()
        db.replace_latest(rows, source)
        log.info("snapshot updated: %s rows (%s)", len(rows), source)
        _fail_streak = 0
        return True
    except Exception as e:  # noqa: BLE001 - 保留旧数据,记录错误
        log.error("snapshot fetch failed: %s", e)
        db.replace_latest([], "", error=str(e))
        _fail_streak += 1
        return False
    finally:
        _lock.release()


def history_job() -> None:
    now = _now_shanghai()
    if now.weekday() >= 5:
        return
    # 收盘后先补抓一次再落库，保证 history 是收盘价
    fetch_job(force=True)
    # 落库守卫:补抓失败(主备都挂)时 latest 是陈旧数据,绝不能当收盘价入库
    # (2026-09-23 东财封禁事件:竞价时段旧快照被原样落库,f8 全 0 污染当日历史)
    meta = db.snapshot_meta()
    if not meta.get("ok") or not str(meta.get("fetched_at") or "").startswith(
            now.date().isoformat()):
        log.error("history skipped for %s: no fresh snapshot (ok=%s, error=%s)",
                  now.date(), meta.get("ok"), meta.get("error"))
        return
    n = db.save_history(now.date().isoformat())
    log.info("history saved for %s: %s rows", now.date(), n)


def maintenance_job() -> None:
    """每日维护：清理过期操作日志 + 热备份数据库。"""
    try:
        n = db.prune_op_logs(config.LOG_RETENTION_DAYS)
        p = db.backup_db()
        log.info("maintenance: pruned %s op_logs, backup -> %s", n, p)
    except Exception as e:  # noqa: BLE001 - 维护失败不影响主业务
        log.error("maintenance failed: %s", e)


def start() -> None:
    global _sched
    if _sched:
        return
    _sched = BackgroundScheduler(timezone="Asia/Shanghai")
    # 集合竞价时段高频调度：周一至周五 09:15-09:25 每 30 秒抓取一次撮合快照
    _sched.add_job(
        fetch_job, "cron", day_of_week="mon-fri",
        hour=9, minute="15-25", second="0,30",
        id="auction_fetch", max_instances=1, coalesce=True
    )
    # 关键时点准点保底触发（规避 interval 启动时间漂移错过开盘与关键撮合时点）
    _sched.add_job(
        fetch_job, "cron", day_of_week="mon-fri",
        hour=9, minute=15, second=2, id="milestone_0915", max_instances=1, coalesce=True
    )
    _sched.add_job(
        fetch_job, "cron", day_of_week="mon-fri",
        hour=9, minute=20, second=2, id="milestone_0920", max_instances=1, coalesce=True
    )
    _sched.add_job(
        fetch_job, "cron", day_of_week="mon-fri",
        hour=9, minute=25, second=2, id="milestone_0925", max_instances=1, coalesce=True
    )
    _sched.add_job(
        fetch_job, "cron", day_of_week="mon-fri",
        hour=9, minute=30, second=2, id="milestone_0930", max_instances=1, coalesce=True
    )
    _sched.add_job(
        fetch_job, "cron", day_of_week="mon-fri",
        hour=13, minute=0, second=2, id="milestone_1300", max_instances=1, coalesce=True
    )
    # 交易时段常规轮询（默认每 3 分钟）
    _sched.add_job(fetch_job, "interval", minutes=config.FETCH_INTERVAL_MIN,
                   id="fetch", max_instances=1, coalesce=True)
    # 同花顺盘口异动:事件流滚动 200 条仅覆盖约 5 秒,需 5 秒高频轮询才能采全
    _sched.add_job(thsflow.collect_job, "interval", seconds=5,
                   id="ths_events", max_instances=1, coalesce=True)
    _sched.add_job(history_job, "cron", day_of_week="mon-fri",
                   hour=15, minute=6, id="history")
    _sched.add_job(maintenance_job, "cron", hour=3, minute=30,
                   id="maintenance")
    _sched.start()
    # 启动立即抓一次（异步，不阻塞服务启动）
    threading.Thread(target=fetch_job, kwargs={"force": True}, daemon=True).start()
    threading.Thread(target=thsflow.collect_job, kwargs={"force": True},
                     daemon=True).start()
    log.info("scheduler started, interval=%s min", config.FETCH_INTERVAL_MIN)


def shutdown() -> None:
    if _sched:
        _sched.shutdown(wait=False)
