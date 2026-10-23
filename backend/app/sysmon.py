"""进程内存观测与回收辅助：RSS 读取 + gc + glibc malloc_trim。

背景：本服务是多线程长驻 Python 进程（uvicorn + anyio 线程池 +
apscheduler + 各模块临时 ThreadPoolExecutor）。glibc 按线程分 arena
缓存空闲堆内存、默认不归还内核，表现为 RSS 随业务高峰"只涨不跌"，
最终触发 systemd MemoryMax OOM 重启（2026-10-05/10-19/10-23 三次）。
周期性 malloc_trim 主动归还空闲堆，让真实泄漏（若有）在 RSS 曲线上
显形，而不是被分配器缓存掩盖。
"""
import ctypes
import gc
import logging
import threading

log = logging.getLogger("sysmon")


def rss_mb() -> float:
    """当前进程常驻内存 MiB（/proc 不可用的平台返回 0，如本地 Windows）。"""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except OSError:
        pass
    return 0.0


def reclaim(job: str = "") -> None:
    """gc 回收 + malloc_trim 归还空闲堆；记录前后 RSS 便于观察内存趋势。"""
    before = rss_mb()
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass  # 非 glibc 平台（本地 Windows 开发）直接跳过
    log.info("mem reclaim(%s): rss %.1f -> %.1f MiB, threads=%d",
             job or "manual", before, rss_mb(), threading.active_count())
