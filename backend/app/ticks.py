"""腾讯公开成交明细：按日期索引取末页，金额为源返回的元、成交量为手。

这是供应商聚合成交明细，并非交易所 Level-2 逐订单流水。
"""
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

URL = "https://stock.gtimg.cn/data/index.php"
_cache = {}
_lock = threading.Lock()


def _fetch(query):
    with requests.Session() as session:
        session.trust_env = False
        r = session.get(URL, params={"appn": "detail", **query}, timeout=6,
                        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})
        r.raise_for_status()
        return r.text


def _assignment(text, variable):
    # 只解析 JSON 数组，绝不执行上游 JavaScript。
    match = re.fullmatch(r"\s*" + re.escape(variable) + r"\s*=\s*(\[.*\])\s*;?\s*", text, re.S)
    if not match:
        raise ValueError("invalid detail response")
    value = json.loads(match[1])
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[1], str):
        raise ValueError("invalid detail payload")
    return value


def _parse_page(text, symbol, page):
    index, body = _assignment(text, "v_detail_data_" + symbol)
    if index != page:
        raise ValueError("detail page mismatch")
    rows = []
    for record in body.split("|"):
        fields = record.split("/")
        if len(fields) != 7 or not re.fullmatch(r"\d{2}:\d{2}:\d{2}", fields[1]):
            continue
        try:
            seq = int(fields[0])
            price, volume, amount = float(fields[2]), float(fields[4]), float(fields[5])
            if not all(math.isfinite(v) for v in (price, volume, amount)) or price <= 0 or volume <= 0 or amount <= 0:
                continue
        except ValueError:
            continue
        side = fields[6]
        rows.append({"seq": seq, "time": fields[1], "price": price,
                     "volume": volume, "amount": amount,
                     "dir": "bull" if side == "B" else "bear" if side == "S" else "neutral",
                     "type": "买盘" if side == "B" else "卖盘" if side == "S" else "中性"})
    return rows


def get_ticks(code):
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("invalid stock code")
    if code.startswith(("4", "8", "9")):
        return {"rows": [], "source": "腾讯成交明细", "trade_date": None,
                "note": "当前成交明细源暂不支持北交所股票"}
    with _lock:
        cached = _cache.get(code)
        if cached and time.monotonic() - cached[0] < 15:
            return cached[1]
    symbol = ("sh" if code.startswith("6") else "sz") + code
    text = _fetch({"action": "detail", "c": symbol})
    if not text.strip():
        return {"rows": [], "source": "腾讯成交明细", "trade_date": None,
                "note": "数据源暂无成交明细，可能停牌或尚未提供数据"}
    day, ranges = _assignment(text, "v_detail_time_" + symbol)
    trade_date = datetime.strptime(str(day), "%Y%m%d").date().isoformat()
    pages = ranges.split("|") if ranges else []
    if len(pages) > 1000:
        raise ValueError("invalid detail page count")
    # 每页约70条；末页可能只有1条，需取末3页才能保证最近100条完整。
    indices = list(range(max(0, len(pages) - 3), len(pages)))

    def fetch_page(page):
        return _parse_page(_fetch({"action": "data", "c": symbol, "p": page}), symbol, page)

    rows = []
    if indices:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for batch in pool.map(fetch_page, indices):
                rows.extend(batch)
    unique = {r["seq"]: r for r in rows}
    rows = [unique[k] for k in sorted(unique, reverse=True)[:100]]
    for row in rows:
        row.pop("seq")
    result = {"rows": rows, "source": "腾讯成交明细", "trade_date": trade_date,
              "note": "供应商聚合成交明细；买卖方向为供应商分类，不代表单个账户或完整大单资金流"}
    if rows:
        with _lock:
            if len(_cache) >= 128:
                _cache.pop(next(iter(_cache)))
            _cache[code] = (time.monotonic(), result)
    return result
