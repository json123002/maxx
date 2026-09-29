"""东方财富全市场快照抓取（服务端直连 HTTP，不再走浏览器 JSONP）。

接口与前端原版一致：clist/get，pz=100/页。
分页排序必须用 fid=f12（按代码）：盘中按换手率(fid=f8)排序时排名逐秒变动，
翻页间行错位、按 code 去重后每轮快照会随机丢 150~400 只股票，
直接导致市场脉搏的上涨/下跌家数偏少（2026-09-09 实测丢股 4~7%）。
停牌/无数据字段东财返回 "-"，统一归一化为 None。
"""
from concurrent.futures import ThreadPoolExecutor
import logging
import math
import time

import requests

log = logging.getLogger("fetcher")

HOSTS = ["https://push2.eastmoney.com", "https://push2delay.eastmoney.com"]
# f350/f351 = 东财计算的涨停价/跌停价（已处理除权除息基准价，比自算更可靠）
# f17 = 今开（竞价涨幅用）; f62 = 主力净流入（涨停雷达用）
FIELDS = "f12,f14,f2,f3,f6,f7,f8,f9,f10,f18,f20,f21,f23,f24,f25,f350,f351,f100,f17,f62"
PAGE_SIZE = 100          # 接口上限（pz>100 会被静默截断）
RETRY = 2
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://quote.eastmoney.com/",
}

# 独立会话：trust_env=False 忽略系统代理（部分网络环境代理对东财长连接不稳定）
_session = requests.Session()
_session.trust_env = False
_session.headers.update(HEADERS)

# 全部 5 个市场（前端市场复选框的并集）
FS_ALL = "m:1+t:2,m:0+t:6,m:0+t:80,m:1+t:23,m:0+t:81+s:2048"

_NUM_FIELDS = ["f2", "f3", "f6", "f7", "f8", "f9", "f10", "f18",
               "f20", "f21", "f23", "f24", "f25", "f350", "f351", "f17", "f62"]


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
    if row.get("f17") is None and row.get("f2"):
        row["f17"] = row["f2"]
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


# ===== 腾讯兜底源（东财封禁/故障时启用）=====
# 2026-09-23 服务器 IP 遭东财 WAF 断连（TLS 通、HTTP 层拒绝），同机房同
# 请求从腾讯 qt.gtimg.cn 正常。批量报价按代码直查（无需翻页、无排名漂移）,
# 代码清单沿用上一轮快照（库内 latest）;行业/名称等静态字段同样沿用,
# 涨跌停判定复用腾讯给出的涨停价/跌停价（下标 47/48)。
# 局限:f24/f25（阶段涨幅）、f62（主力净流入）腾讯无对应字段,置 None;
# 快照缺失期间新上市的个股不在清单内,兜底期查不到。
TX_URL = "https://qt.gtimg.cn/q="
TX_BATCH = 60            # qt.gtimg.cn 单请求代码数上限（超出会被截断）
TX_SOURCE = "腾讯行情(备用)"

_tx_session = requests.Session()
_tx_session.trust_env = False
_tx_session.headers.update({"User-Agent": HEADERS["User-Agent"]})


def _tx_symbol(code: str) -> str:
    """6 位代码 → 腾讯带市场前缀代码（沪 sh / 深 sz / 北 bj）。"""
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("4", "8", "9")):
        return "bj" + code
    return "sz" + code


def _tx_num(parts, i, scale=1.0):
    """按下标取数值;空串/越界/非法 → None。scale 做单位换算。"""
    try:
        v = float(parts[i])
    except (IndexError, ValueError):
        return None
    return v * scale if math.isfinite(v) else None


def _tx_row(symbol: str, parts, static: dict) -> dict:
    """腾讯报价字段数组 → 东财口径行。下标经 2026-09-23 三市场实测核对:
    3 最新价 / 4 昨收 / 5 今开 / 32 涨跌幅 / 43 振幅 / 38 换手率 /
    52 市盈率(与东财 f9 一致) / 49 量比 / 37 成交额(万) / 44 流通市值(亿) /
    45 总市值(亿) / 46 市净率 / 47 涨停价 / 48 跌停价。"""
    code = symbol[2:]
    st = static.get(code) or {}
    price = _tx_num(parts, 3) or None
    open_px = _tx_num(parts, 5)
    if open_px == 0.0:
        # 集合竞价时段(09:15-09:25)今开尚未正式定格, 腾讯返回 0.00; 撮合匹配价即为主力竞价开盘预估价
        open_px = price if (price and price > 0) else None
    row = {
        "code": code,
        "name": st.get("name"),
        "industry": st.get("industry"),
        "market": market_of(code),
        "f2": price,
        "f18": _tx_num(parts, 4),
        "f17": open_px,
        "f3": _tx_num(parts, 32),
        "f7": _tx_num(parts, 43),
        "f8": _tx_num(parts, 38),
        "f9": _tx_num(parts, 52) or _tx_num(parts, 39),
        "f10": _tx_num(parts, 49),
        "f6": _tx_num(parts, 37, 1e4),
        "f20": _tx_num(parts, 45, 1e8),
        "f21": _tx_num(parts, 44, 1e8),
        "f23": _tx_num(parts, 46),
        "f350": _tx_num(parts, 47),
        "f351": _tx_num(parts, 48),
        "f24": None, "f25": None, "f62": None,
    }
    row["limit_up"], row["limit_down"] = limit_flags(
        row["f2"], row["f350"], row["f351"])
    return row


def _fetch_tx_batch(symbols) -> dict:
    """一批代码 → {symbol: 字段数组};停牌/退市返回空体,解析后自然剔除。"""
    r = _tx_session.get(TX_URL + ",".join(symbols), timeout=10)
    r.raise_for_status()
    r.encoding = "gbk"
    out = {}
    for seg in r.text.split(";"):
        seg = seg.strip()
        if not seg.startswith("v_") or "=" not in seg:
            continue
        key, _, val = seg.partition("=")
        body = val.strip().strip('"')
        if body:
            out[key[2:]] = body.split("~")
    return out


def fetch_snapshot_tx(static_rows):
    """腾讯兜底全量快照。static_rows: 上一轮快照的 code/name/industry 清单
    (db.latest_static())。多线程并发批量抓取（99 批由 ~30s 缩短至 2~4s）。
    返回 (rows, source),失败抛异常由调度层记录。"""
    static = {r["code"]: r for r in static_rows if r.get("code")}
    symbols = [_tx_symbol(c) for c in static]
    if not symbols:
        return [], TX_SOURCE

    batches = [symbols[i:i + TX_BATCH] for i in range(0, len(symbols), TX_BATCH)]
    rows = []

    def _fetch_one_batch(batch):
        try:
            got = _fetch_tx_batch(batch)
            return [_tx_row(s, got[s], static) for s in batch if s in got]
        except Exception as e:  # noqa: BLE001
            log.warning("tencent batch failed: %s", e)
            return []

    workers = min(10, max(2, len(batches)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for batch_rows in pool.map(_fetch_one_batch, batches):
            rows.extend(batch_rows)

    if len(rows) < len(symbols) * 0.9:
        raise RuntimeError("tencent fallback incomplete: %s/%s"
                           % (len(rows), len(symbols)))
    return rows, TX_SOURCE
