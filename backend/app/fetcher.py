"""东方财富全市场快照抓取（服务端直连 HTTP，不再走浏览器 JSONP）。

接口与前端原版一致：clist/get，pz=100/页。
分页排序必须用 fid=f12（按代码）：盘中按换手率(fid=f8)排序时排名逐秒变动，
翻页间行错位、按 code 去重后每轮快照会随机丢 150~400 只股票，
直接导致市场脉搏的上涨/下跌家数偏少（2026-09-09 实测丢股 4~7%）。
停牌/无数据字段东财返回 "-"，统一归一化为 None。
"""
import logging
import time

import requests

log = logging.getLogger("fetcher")

HOSTS = ["https://push2.eastmoney.com", "https://push2delay.eastmoney.com"]
# f350/f351 = 东财计算的涨停价/跌停价（已处理除权除息基准价，比自算更可靠）
FIELDS = "f12,f14,f2,f3,f6,f7,f8,f9,f10,f18,f20,f21,f23,f24,f25,f350,f351,f100"
PAGE_SIZE = 100          # 接口上限（pz>100 会被静默截断）
RETRY = 2
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://quote.eastmoney.com/",
}

# 独立会话：trust_env=False 忽略系统代理（部分网络环境代理对东财长连接不稳定）
_session = requests.Session()
_session.trust_env = False
_session.headers.update(HEADERS)

# 全部 5 个市场（前端市场复选框的并集）
FS_ALL = "m:1+t:2,m:0+t:6,m:0+t:80,m:1+t:23,m:0+t:81+s:2048"

_NUM_FIELDS = ["f2", "f3", "f6", "f7", "f8", "f9", "f10", "f18",
               "f20", "f21", "f23", "f24", "f25", "f350", "f351"]


def limit_flags(price, limit_up_px, limit_down_px):
    """涨跌停判定:最新价是否达到东财给出的涨停价/跌停价(f350/f351)。

    返回 (limit_up, limit_down),停牌/无涨跌停价(上市初期无限制的新股等)
    返回 (None, None)。容差 0.005 防御浮点与最小变动价位(0.01)误差。
    """
    if price is None:
        return None, None
    lu = ld = 0
    if limit_up_px is not None and abs(price - limit_up_px) < 0.005:
        lu = 1
    if limit_down_px is not None and abs(price - limit_down_px) < 0.005:
        ld = 1
    return lu, ld


def market_of(code: str) -> str:
    if code.startswith("68"):
        return "科创板"
    if code.startswith("6"):
        return "沪主板"
    if code.startswith("30"):
        return "创业板"
    if code.startswith(("4", "8", "9")):
        return "北交所"
    return "深主板"


def _normalize(item: dict) -> dict:
    code = str(item.get("f12") or "")
    row = {
        "code": item.get("f12"),
        "name": item.get("f14"),
        "industry": item.get("f100") or None,
        "market": market_of(code),
    }
    for k in _NUM_FIELDS:
        v = item.get(k)
        row[k] = float(v) if isinstance(v, (int, float)) else None
    row["limit_up"], row["limit_down"] = limit_flags(
        row["f2"], row["f350"], row["f351"])
    return row


def _fetch_page(host: str, pn: int) -> dict:
    r = _session.get(
        host + "/api/qt/clist/get",
        params={"pn": pn, "pz": PAGE_SIZE, "po": 1, "np": 1, "fltt": 2,
                "invt": 2, "fid": "f12", "fs": FS_ALL, "fields": FIELDS},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if not data or not data.get("data"):
        raise ValueError("empty response")
    return data["data"]


def _fetch_page_retry(pn: int, preferred: str = None) -> tuple[dict, str]:
    """单页重试：优先已知可用 host，失败交替换源。"""
    hosts = ([preferred] + [h for h in HOSTS if h != preferred]) if preferred else HOSTS
    last_err = None
    for attempt in range(RETRY + 1):
        for host in hosts:
            try:
                return _fetch_page(host, pn), host
            except Exception as e:  # noqa: BLE001
                last_err = e
        if attempt < RETRY:
            time.sleep(0.5)
    raise RuntimeError("page %s: %s" % (pn, last_err))


def fetch_snapshot():
    """全量抓取，返回 (rows, source)。失败抛异常由调度层记录。"""
    first, host = _fetch_page_retry(1)
    total = first.get("total") or 0
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    rows = [_normalize(x) for x in first.get("diff") or []]
    log.info("fetch page 1/%s ok, total=%s, host=%s", pages, total, host)
    for pn in range(2, pages + 1):
        data, host = _fetch_page_retry(pn, preferred=host)
        rows.extend(_normalize(x) for x in data.get("diff") or [])
        time.sleep(0.15)   # 礼貌间隔，避免触发限流
    # 市场并集可能重复返回同一代码（如跨板块归类）,按 code 去重
    seen, uniq = set(), []
    for r in rows:
        if r["code"] and r["code"] not in seen:
            seen.add(r["code"])
            uniq.append(r)
    rows = uniq
    return rows, ("延迟行情" if "delay" in host else "实时行情")
