"""预警中心:服务端规则评估引擎。

挂载点:scheduler.fetch_job 在快照落库成功后调用 evaluate()(随行情节拍,
默认 3 分钟)。评估失败绝不外抛——调用方已 try/except,但本模块自身也不主动 raise。

去重策略:连续阈值类(价格/涨幅/换手/量比)按每规则 cooldown_min 时间冷却;
离散事件类(涨停/开板)每交易日最多触发一次。

limit_open(开板)依赖模块级 _prev_limit 记录上一轮封板状态:进程重启会丢失
当轮状态(封板中重启 → 开板不触发),可接受,不为此引入持久化。
"""
import logging
from datetime import datetime

from . import db

log = logging.getLogger("alerts")

RULE_TYPES = {"price_above", "price_below", "pct_above", "pct_below",
              "turnover_above", "volratio_above", "limit_up", "limit_open"}
LIMIT_TYPES = {"limit_up", "limit_open"}        # 无需阈值 + 每日一次
MAX_RULES_PER_USER = 50

_prev_limit: dict = {}   # code -> 上轮评估时是否封板


def _now_shanghai() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    except Exception:
        return datetime.now()


def _in_eval_window(now: datetime) -> bool:
    """评估窗口:09:25-15:05 工作日(竞价尾声到收盘后,覆盖集合竞价与全天)。"""
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return 9 * 60 + 25 <= mins <= 15 * 60 + 5


def _check(rule: dict, row: dict, prev_limit: bool):
    """命中返回 detail 文案,未命中返回 None。"""
    t, th = rule["rule_type"], rule["threshold"]
    f2, f3 = row["f2"], row["f3"]
    if t == "price_above" and f2 >= th:
        return f"现价 {f2} ≥ 预警价 {th}"
    if t == "price_below" and f2 <= th:
        return f"现价 {f2} ≤ 预警价 {th}"
    if t == "pct_above" and f3 is not None and f3 >= th:
        return f"涨幅 {f3:+.2f}% ≥ {th}%"
    if t == "pct_below" and f3 is not None and f3 <= th:
        return f"跌幅 {f3:+.2f}% ≤ {th}%"
    if t == "turnover_above" and row["f8"] is not None and row["f8"] >= th:
        return f"换手率 {row['f8']:.2f}% ≥ {th}%"
    if t == "volratio_above" and row["f10"] is not None and row["f10"] >= th:
        return f"量比 {row['f10']:.2f} ≥ {th}"
    if t == "limit_up" and row["limit_up"] == 1:
        return f"封涨停,现价 {f2}"
    if t == "limit_open" and prev_limit and row["limit_up"] != 1:
        return f"涨停打开,现价 {f2}(涨幅 {f3:+.2f}%)" if f3 is not None else "涨停打开"
    return None


def _parse_ts(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def evaluate(now: datetime = None) -> int:
    """对全部启用规则评估一轮,返回触发数。快照陈旧/非评估窗口直接返回 0。"""
    now = now or _now_shanghai()
    if not _in_eval_window(now):
        return 0
    meta = db.snapshot_meta()
    today = now.date().isoformat()
    if not meta.get("ok") or not str(meta.get("fetched_at") or "").startswith(today):
        return 0   # 陈旧快照不评估(2026-09-23 封禁事件教训:旧数据不能当实时)

    conn = db.get_conn()
    rules = [dict(r) for r in conn.execute(
        "SELECT * FROM alert_rule WHERE enabled = 1").fetchall()]
    if not rules:
        return 0
    rows = {r["code"]: dict(r) for r in conn.execute(
        "SELECT code, name, f2, f3, f8, f10, limit_up FROM latest").fetchall()}

    fired = 0
    ts = now.replace(tzinfo=None).isoformat(timespec="seconds")
    for rule in rules:
        row = rows.get(rule["code"])
        if not row or row["f2"] is None:
            continue
        # 冷却/每日去重先行,避免无效计算
        last = _parse_ts(rule["last_fired_at"])
        if rule["rule_type"] in LIMIT_TYPES:
            if (rule["last_fired_at"] or "")[:10] == today:
                continue
        elif last and (now.replace(tzinfo=None) - last).total_seconds() < rule["cooldown_min"] * 60:
            continue
        detail = _check(rule, row, bool(_prev_limit.get(rule["code"])))
        if not detail:
            continue
        with conn:
            conn.execute(
                "INSERT INTO alert_event"
                " (rule_id, user_id, ts, code, name, rule_type, price, detail)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (rule["id"], rule["user_id"], ts, rule["code"],
                 row["name"] or rule["name"], rule["rule_type"], row["f2"], detail))
            conn.execute(
                "UPDATE alert_rule SET last_fired_at = ?, fire_count = fire_count + 1"
                " WHERE id = ?", (ts, rule["id"]))
        fired += 1

    # 更新封板状态快照(供下一轮开板判定)
    for code, row in rows.items():
        _prev_limit[code] = row["limit_up"] == 1
    if fired:
        log.info("alerts fired: %d", fired)
    return fired
