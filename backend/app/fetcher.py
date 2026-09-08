"""东方财富全市场快照抓取（服务端直连 HTTP，不再走浏览器 JSONP）。

接口与前端原版一致：clist/get，pz=100/页，fid=f8 按换手率排序。
停牌/无数据字段东财返回 "-"，统一归一化为 None。
"""
import logging
import time

import requests

log = logging.getLogger("fetcher")

HOSTS = ["https://push2.eastmoney.com", "https://push2delay.eastmoney.com"]
FIELDS = "f12,f14,f2,f3,f6,f7,f8,f9,f10,f20,f21,f23,f24,f25,f100"
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

_NUM_FIELDS = ["f2", "f3", "f6", "f7", "f8", "f9", "f10",
               "f20", "f21", "f23", "f24", "f25"]


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
    row = {
        "code": item.get("f12"),
        "name": item.get("f14"),
        "industry": item.get("f100") or None,
        "market": market_of(str(item.get("f12") or "")),
    }
    for k in _NUM_FIELDS:
        v = item.get(k)
        row[k] = float(v) if isinstance(v, (int, float)) else None
    return row


def _fetch_page(host: str, pn: int) -> dict:
    r = _session.get(
        host + "/api/qt/clist/get",
        params={"pn": pn, "pz": PAGE_SIZE, "po": 1, "np": 1, "fltt": 2,
                "invt": 2, "fid": "f8", "fs": FS_ALL, "fields": FIELDS},
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
