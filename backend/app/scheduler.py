"""抓数调度：交易时段每 N 分钟刷 latest；每交易日 15:06 落 history。"""
import logging
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from . import config, db, fetcher

log = logging.getLogger("scheduler")
_lock = threading.Lock()
_sched = None


def _is_trading_time(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return (9 * 60 + 15 <= mins <= 11 * 60 + 30) or (13 * 60 <= mins <= 15 * 60 + 5)


def fetch_job(force: bool = False) -> bool:
    """抓一次快照。force=True 跳过交易时段判断（启动时/手动触发）。"""
    if not force and not _is_trading_time(datetime.now()):
        return False
    if not _lock.acquire(blocking=False):
        return False
    try:
        rows, source = fetcher.fetch_snapshot()
        db.replace_latest(rows, source)
        log.info("snapshot updated: %s rows (%s)", len(rows), source)
        return True
    except Exception as e:  # noqa: BLE001 - 保留旧数据,记录错误
        log.error("snapshot fetch failed: %s", e)
        db.replace_latest([], "", error=str(e))
        return False
    finally:
        _lock.release()


def history_job() -> None:
    now = datetime.now()
    if now.weekday() >= 5:
        return
    # 收盘后先补抓一次再落库，保证 history 是收盘价
    fetch_job(force=True)
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
    _sched.add_job(fetch_job, "interval", minutes=config.FETCH_INTERVAL_MIN,
                   id="fetch", max_instances=1, coalesce=True)
    _sched.add_job(history_job, "cron", day_of_week="mon-fri",
                   hour=15, minute=6, id="history")
    _sched.add_job(maintenance_job, "cron", hour=3, minute=30,
                   id="maintenance")
    _sched.start()
    # 启动立即抓一次（异步，不阻塞服务启动）
    threading.Thread(target=fetch_job, kwargs={"force": True}, daemon=True).start()
    log.info("scheduler started, interval=%s min", config.FETCH_INTERVAL_MIN)


def shutdown() -> None:
    if _sched:
        _sched.shutdown(wait=False)
