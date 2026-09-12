"""用户操作埋点：服务端关键动作自动记录 + 前端行为主动上报（/api/track）。

IP 归属地：查询日志时惰性解析并永久缓存进 ip_regions 表（成功才缓存，
失败下次访问重试）。源为太平洋网络 whois.pconline.com.cn 免费接口
（境内可达，逐条 GET），仅 root 拉日志页时触发，调用量极小；
解析失败不影响日志功能本身。
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


# pconline addr 形如 "上海市长宁区 /普陀区电信ADSL"，运营商从末尾关键词提取
_ISP_KW = ("电信", "联通", "移动", "铁通", "长城", "教育网")


def _fmt_region(item: dict) -> str:
    """pconline 单条结果 -> 展示文案，如 '上海 · 电信' / '浙江杭州 · 联通'。"""
    pro = (item.get("pro") or "").strip()      # 省
    city = (item.get("city") or "").strip()
    loc = pro if (not city or city == pro) else pro + city
    if not loc:
        loc = (item.get("region") or "").strip()   # 区/县兜底
    addr = (item.get("addr") or "").strip()
    isp = next((k for k in _ISP_KW if k in addr), "")
    if isp:
        loc = (loc + " · " + isp) if loc else isp
    return loc[:60]


def enrich_regions(rows: list) -> None:
    """就地给日志行补 region 字段：先查缓存表，缺失的公网 IP 逐条查一次外网。

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
            got = []
            for ip in missing:
                try:
                    resp = requests.get(
                        "https://whois.pconline.com.cn/ipJson.jsp",
                        params={"ip": ip, "json": "true"}, timeout=3)
                    resp.encoding = "gbk"   # 接口返回 GBK 编码
                    item = resp.json()
                except Exception:
                    continue
                if not isinstance(item, dict) or item.get("err"):
                    continue
                reg = _fmt_region(item)
                if not reg:
                    continue
                region[ip] = reg
                got.append((ip, reg,
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
