"""麦蕊盘口资金：分档汇总与交易时段内成交明细，保持来源与口径独立。"""
import hashlib
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BASE = "https://api.mairuiapi.com"
_cache = {}
_lock = threading.Lock()
TIERS = (("super", "特大单", "td"), ("big", "大单", "dd"),
         ("mid", "中单", "zd"), ("small", "小单", "xd"))


def number(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def total(values):
    return sum(values) if values and all(v is not None for v in values) else None


def normalize_day(item):
    raw_date = str(item.get("t") or "")[:10]
    datetime.strptime(raw_date, "%Y-%m-%d")
    tiers = []
    for key, name, suffix in TIERS:
        row = {"key": key, "name": name}
        for direction, prefix in (("active_buy", "zmb"), ("active_sell", "zms"),
                                  ("passive_buy", "bdmb"), ("passive_sell", "bdms")):
            value = number(item.get(prefix + suffix + "cje"))
            row[direction] = value if value is not None and value >= 0 else None
        row["net"] = (row["active_buy"] - row["active_sell"]
                      if row["active_buy"] is not None and row["active_sell"] is not None else None)
        tiers.append(row)
    buy = total([r["active_buy"] for r in tiers[:2]])
    sell = total([r["active_sell"] for r in tiers[:2]])
    return {"date": raw_date, "as_of": str(item.get("t")), "tiers": tiers,
            "buy": buy, "sell": sell,
            "net": buy - sell if buy is not None and sell is not None else None}


def trading_time(value):
    if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", str(value)):
        return False
    return value == "09:25:00" or "09:30:00" <= value <= "11:30:00" or "13:00:00" <= value <= "15:00:00"


def normalize_trades(data, date):
    rows = []
    excluded = 0
    for seq, item in enumerate(data):
        if not isinstance(item, dict) or str(item.get("d") or "") != date or not trading_time(item.get("t")):
            excluded += 1
            continue
        price, shares = number(item.get("p")), number(item.get("v"))
        if price is None or shares is None or price <= 0 or shares <= 0:
            excluded += 1
            continue
        side = "buy" if item.get("ts") == 1 else "sell" if item.get("ts") == 2 else "neutral"
        amount = price * shares
        if not math.isfinite(amount):
            excluded += 1
            continue
        rows.append({"id": seq, "time": item["t"], "price": price, "shares": shares,
                     "volume": shares / 100, "amount": round(amount, 2), "side": side})
    rows.sort(key=lambda r: (r["time"], r["id"]), reverse=True)
    return rows, excluded


def _request(path, licence, params=None):
    # 证书仅由后端拼接。上层只返回固定错误，不传递含证书的异常URL或原始报错。
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(BASE + path + "/" + licence, params=params, timeout=12)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise ValueError("provider unavailable")
        return data


def get_dataset(code, source):
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("invalid code")
    key = (source["user_id"], source["id"], hashlib.sha256(source["licence"].encode()).hexdigest(), code)
    with _lock:
        entry = _cache.get(key)
        if entry and time.monotonic() - entry[0] < 300:
            return entry[1]
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    warnings = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        daily = pool.submit(_request, "/hsstock/history/transaction/" + code, source["licence"],
                            {"st": (now - timedelta(days=70)).strftime("%Y%m%d"), "et": now.strftime("%Y%m%d")})
        trades = pool.submit(_request, "/hsrl/zbjy/" + code, source["licence"])
        history = []
        try:
            by_date = {}
            for item in daily.result():
                if isinstance(item, dict):
                    day = normalize_day(item)
                    if day["date"] not in by_date or day["as_of"] > by_date[day["date"]]["as_of"]:
                        by_date[day["date"]] = day
            history = sorted(by_date.values(), key=lambda d: d["date"])[-20:]
        except Exception:
            warnings.append("分档资金暂不可用，请检查证书权限或稍后刷新")
        raw = []
        try:
            raw = trades.result()
        except Exception:
            warnings.append("麦蕊成交明细暂不可用，请稍后刷新")
    valid_dates = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            valid_dates.append(datetime.strptime(str(item.get("d")), "%Y-%m-%d").date().isoformat())
        except ValueError:
            continue
    trade_date = max(valid_dates, default=None)
    rows, excluded = normalize_trades(raw, trade_date) if trade_date else ([], len(raw))
    latest = history[-1] if history else None
    detail_amount = sum(r["amount"] for r in rows)
    summary_turnover = total([t[k] for t in latest["tiers"] for k in ("active_buy", "active_sell")]) if latest else None
    if latest and trade_date and latest["date"] != trade_date:
        warnings.append("分档汇总与成交明细日期不同，请分别查看各自日期")
    elif rows and summary_turnover and abs(detail_amount / summary_turnover - 1) > 0.05:
        warnings.append("成交明细总额与分档汇总总额差异超过5%，两接口更新进度或统计范围可能不同")
    if not latest and not rows:
        warnings.append("当前证书或数据源未返回该股的有效资金数据")
    result = {"summary": latest, "history": history, "trades": rows,
              "source": "麦蕊智数", "fetched_at": now.isoformat(timespec="seconds"),
              "trade_date": trade_date, "excluded_count": excluded,
              "detail_amount": detail_amount, "summary_turnover": summary_turnover,
              "raw_count": len(raw), "warnings": warnings,
              "capabilities": {"dark_pool": False,
                               "passive_summary": bool(latest and any(t["passive_buy"] is not None for t in latest["tiers"])),
                               "l2_order_details": False}}
    # 失败不占完整缓存TTL，允许用户及时重试。
    if latest and rows:
        with _lock:
            if len(_cache) >= 64:
                _cache.pop(next(iter(_cache)))
            _cache[key] = (time.monotonic(), result)
    return result


def select_trades(dataset, minimum=0, side="all", page=1, page_size=100, all_rows=False):
    available_rows = dataset["trades"]
    rows = [r for r in available_rows if r["amount"] >= minimum and (side == "all" or r["side"] == side)]
    start = (page - 1) * page_size
    return {k: v for k, v in dataset.items() if k != "trades"} | {
        "rows": rows if all_rows else rows[start:start + page_size], "total": len(rows),
        "available_count": len(available_rows), "page": page, "page_size": page_size,
        "matched_buy": sum(r["amount"] for r in rows if r["side"] == "buy"),
        "matched_sell": sum(r["amount"] for r in rows if r["side"] == "sell"),
        "matched_neutral": sum(r["amount"] for r in rows if r["side"] == "neutral")}
