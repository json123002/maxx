"""用户操作埋点：服务端关键动作自动记录 + 前端行为主动上报（/api/track）。

IP 归属地：查询日志时惰性解析并永久缓存进 ip_regions 表（成功才缓存，
失败下次访问重试）。源为 ip-api.com 免费批量接口，仅 root 拉日志页时
触发，调用量极小；解析失败不影响日志功能本身。
"""
import ipaddress
from datetime import datetime

import requests

from .db import get_conn

_UA_MAX = 200


def client_ip(request) -> str:
    """取真实客户端 IP。

    经 nginx 反代后 request.client.host 恒为回环地址 127.0.0.1，
    必须读反代头：X-Forwarded-For 取链路第一跳，X-Real-IP 兜底。
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    xri = request.headers.get("x-real-ip", "").strip()
    if xri:
        return xri
    return request.client.host if request.client else ""


def user_agent(request) -> str:
    """浏览器 UA（截断保存，辅助识别设备/来源）。"""
    return (request.headers.get("user-agent", "") or "")[:_UA_MAX]


def log_op(user, action: str, detail: str = "", ip: str = "", ua: str = "") -> None:
    """写一条操作日志。埋点绝不能影响业务：任何失败都静默吞掉。"""
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO op_logs (ts, user_id, username, action, detail, ip, ua)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"),
                 user.get("id"), user.get("username"), action,
                 (detail or "")[:300], ip or "", (ua or "")[:_UA_MAX]),
            )
    except Exception:
        pass


# ===== IP 归属地 =====

def _is_public_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local
                or a.is_multicast or a.is_reserved or a.is_unspecified)


def _fmt_region(item: dict) -> str:
    """ip-api 单条结果 -> 展示文案，如 '上海 · 电信' / '美国 加利福尼亚 · Cloudflare'。"""
    region = (item.get("regionName") or "").strip()   # 省/州
    city = (item.get("city") or "").strip()
    loc = region if (not city or city == region) else region + city
    country = (item.get("country") or "").strip()
    if not loc:
        loc = country
    elif country and country != "中国":
        loc = country + " " + loc
    isp = (item.get("isp") or "").strip()
    if isp and isp not in loc:
        loc = (loc + " · " + isp) if loc else isp
    return loc[:60]


def enrich_regions(rows: list) -> None:
    """就地给日志行补 region 字段：先查缓存表，缺失的公网 IP 批量查一次外网。

    任何网络/解析失败都静默降级（region 留空），不影响日志查询。
    """
    for r in rows:
        r["region"] = ""
    pub = set()
    for r in rows:
        ip = r.get("ip") or ""
        if not ip:
            continue
        if _is_public_ip(ip):
            pub.add(ip)
        elif ipaddress_safe(ip):
            r["region"] = "内网/本机"
    if not pub:
        return
    try:
        conn = get_conn()
        cached = conn.execute(
            "SELECT ip, region FROM ip_regions WHERE ip IN (%s)"
            % ",".join("?" * len(pub)), tuple(pub)).fetchall()
        region = {c["ip"]: c["region"] for c in cached}
        missing = [ip for ip in pub if ip not in region][:100]
        if missing:
            resp = requests.post(
                "http://ip-api.com/batch?lang=zh-CN",
                json=[{"query": ip,
                       "fields": "status,country,regionName,city,isp,query"}
                      for ip in missing],
                timeout=3)
            got = []
            for item in resp.json():
                if item.get("status") == "success":
                    reg = _fmt_region(item)
                    region[item["query"]] = reg
                    got.append((item["query"], reg,
                                datetime.now().isoformat(timespec="seconds")))
            if got:
                with conn:
                    conn.executemany(
                        "INSERT OR REPLACE INTO ip_regions (ip, region, fetched_at)"
                        " VALUES (?, ?, ?)", got)
        for r in rows:
            ip = r.get("ip") or ""
            if ip in region:
                r["region"] = region[ip]
    except Exception:
        pass


def ipaddress_safe(ip: str) -> bool:
    """是合法 IP 但不是公网（内网/回环等）。"""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False
