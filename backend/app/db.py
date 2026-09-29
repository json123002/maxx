"""SQLite 访问层：建表、种子管理员、快照读写。

字段沿用东方财富接口字段名（f2 最新价 / f3 涨跌幅 / f6 成交额 / f7 振幅 /
f8 换手率 / f9 市盈率 / f10 量比 / f18 昨收 / f20 总市值 / f21 流通市值 /
f23 市净率 / f24 60日涨幅 / f25 年初至今涨幅 / f350 涨停价 / f351 跌停价），
code/name/industry 对应 f12/f14/f100。limit_up/limit_down 由 fetcher 按
最新价是否达到 f350/f351 判定（0/1）。
"""
import os
import sqlite3
import threading

from . import config

_local = threading.local()

QUOTE_COLS = ["f2", "f3", "f6", "f7", "f8", "f9", "f10", "f18",
              "f20", "f21", "f23", "f24", "f25", "f350", "f351", "f17", "f62"]
LIMIT_COLS = ["limit_up", "limit_down"]
ALL_COLS = ["code", "name", "industry", "market"] + QUOTE_COLS + LIMIT_COLS


def get_conn() -> sqlite3.Connection:
    """每线程一个连接（WAL 模式，读写不互斥）。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
        conn = sqlite3.connect(config.DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS latest (
            code     TEXT PRIMARY KEY,
            name     TEXT,
            industry TEXT,
            market   TEXT,
            f2 REAL, f3 REAL, f6 REAL, f7 REAL, f8 REAL, f9 REAL,
            f10 REAL, f18 REAL, f20 REAL, f21 REAL, f23 REAL, f24 REAL,
            f25 REAL, f350 REAL, f351 REAL, f17 REAL, f62 REAL,
            limit_up INTEGER, limit_down INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_latest_industry ON latest(industry);
        CREATE INDEX IF NOT EXISTS idx_latest_turnover ON latest(f8);

        CREATE TABLE IF NOT EXISTS snapshot_meta (
            id         INTEGER PRIMARY KEY CHECK (id = 1),
            fetched_at TEXT,
            source     TEXT,
            total      INTEGER,
            ok         INTEGER,
            error      TEXT
        );

        CREATE TABLE IF NOT EXISTS history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            code       TEXT NOT NULL,
            name       TEXT,
            industry   TEXT,
            market     TEXT,
            f2 REAL, f3 REAL, f6 REAL, f7 REAL, f8 REAL, f9 REAL,
            f10 REAL, f18 REAL, f20 REAL, f21 REAL, f23 REAL, f24 REAL,
            f25 REAL, f350 REAL, f351 REAL, f17 REAL, f62 REAL,
            limit_up INTEGER, limit_down INTEGER,
            UNIQUE (trade_date, code)
        );
        CREATE INDEX IF NOT EXISTS idx_history_date ON history(trade_date);

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user',
            enabled       INTEGER NOT NULL DEFAULT 1,
            hidden        INTEGER NOT NULL DEFAULT 0,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

        CREATE TABLE IF NOT EXISTS watchlist (
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code       TEXT NOT NULL,
            name       TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, code)
        );

        -- 黑名单：按用户隔离；命中后筛选结果(/api/quote/list)服务端直接剔除
        CREATE TABLE IF NOT EXISTS blacklist (
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code       TEXT NOT NULL,
            name       TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, code)
        );

        -- 行情源设置：每用户独立的第三方行情接口配置（证书编号只回给本人；
        -- is_public 公开后全站用户在未启用自己的源时可用，但只见名称）
        CREATE TABLE IF NOT EXISTS quote_source (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name       TEXT NOT NULL,
            provider   TEXT NOT NULL,
            licence    TEXT NOT NULL,
            enabled    INTEGER NOT NULL DEFAULT 0,
            is_public  INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            UNIQUE (user_id, name)
        );

        CREATE TABLE IF NOT EXISTS desk_star (
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code       TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id, code)
        );

        CREATE TABLE IF NOT EXISTS desk_stock (
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code       TEXT NOT NULL,
            name       TEXT,
            created_at TEXT NOT NULL,
            sort       REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, code)
        );

        CREATE TABLE IF NOT EXISTS desk_group (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name       TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS desk_group_item (
            group_id   INTEGER NOT NULL REFERENCES desk_group(id) ON DELETE CASCADE,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code       TEXT NOT NULL,
            sort       REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (group_id, code)
        );

        CREATE TABLE IF NOT EXISTS desk_note (
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code       TEXT NOT NULL,
            content    TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, code)
        );

        CREATE TABLE IF NOT EXISTS op_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT NOT NULL,
            user_id    INTEGER,
            username   TEXT,
            action     TEXT NOT NULL,
            detail     TEXT,
            ip         TEXT,
            ua         TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_op_logs_ts ON op_logs(ts);

        CREATE TABLE IF NOT EXISTS ip_regions (
            ip         TEXT PRIMARY KEY,
            region     TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kline (
            code    TEXT NOT NULL,
            date    TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            vol REAL, amount REAL, pct REAL,
            PRIMARY KEY (code, date)
        );

        CREATE TABLE IF NOT EXISTS kline_meta (
            code         TEXT PRIMARY KEY,
            fetched_date TEXT NOT NULL
        );

        -- 龙虎榜:每日个股榜单(同股同日可因不同原因多次上榜)
        CREATE TABLE IF NOT EXISTS lhb_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            explain TEXT,
            close_price REAL, change_rate REAL,
            net_amt REAL, buy_amt REAL, sell_amt REAL,
            accum_amount REAL, turnover_rate REAL,
            fetched_at TEXT,
            UNIQUE (trade_date, code, explain)
        );
        CREATE INDEX IF NOT EXISTS idx_lhb_item_date ON lhb_item(trade_date);
        CREATE INDEX IF NOT EXISTS idx_lhb_item_code ON lhb_item(code, trade_date);

        -- 龙虎榜:营业部席位明细 + 次日表现回填(t_close 取 kline 前复权口径,自洽)
        CREATE TABLE IF NOT EXISTS lhb_seat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            side TEXT NOT NULL,          -- 'B' 买榜 / 'S' 卖榜
            dept_code TEXT NOT NULL,
            dept_name TEXT NOT NULL,
            buy REAL, sell REAL, net REAL,
            t_close REAL,
            t1_open REAL, t1_high REAL, t1_low REAL, t1_close REAL,
            filled_at TEXT,
            UNIQUE (trade_date, code, side, dept_code)
        );
        CREATE INDEX IF NOT EXISTS idx_lhb_seat_dept ON lhb_seat(dept_name, trade_date);

        -- 席位画像物化统计(stats_job 每日收盘后重建)
        CREATE TABLE IF NOT EXISTS lhb_seat_stat (
            dept_name TEXT PRIMARY KEY,
            appearances INTEGER NOT NULL,
            win_cnt INTEGER NOT NULL,
            win_rate REAL,               -- 无次日结果样本时为 NULL(勿默认 0 误导)
            avg_open_premium REAL, avg_close_pct REAL, avg_max_premium REAL,
            total_net REAL,
            last_date TEXT,
            top_stocks TEXT,             -- JSON: [{code,name,n}]
            co_seats TEXT,               -- JSON: [{dept,n}]
            updated_at TEXT
        );

        -- 预警中心:规则(每用户上限 50,见 alerts_routes)
        CREATE TABLE IF NOT EXISTS alert_rule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code TEXT NOT NULL,
            name TEXT,
            rule_type TEXT NOT NULL,     -- 白名单见 alerts.RULE_TYPES
            threshold REAL,              -- limit_up/limit_open 类可为空
            enabled INTEGER NOT NULL DEFAULT 1,
            cooldown_min INTEGER NOT NULL DEFAULT 60,
            last_fired_at TEXT,
            fire_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_alert_rule_enabled ON alert_rule(enabled);

        -- 预警中心:触发事件(冗余 user_id,按用户查事件免 join)
        CREATE TABLE IF NOT EXISTS alert_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL REFERENCES alert_rule(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            rule_type TEXT NOT NULL,
            price REAL,
            detail TEXT,
            read INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_alert_event_user ON alert_event(user_id, id);
        """
    )
    _migrate_quote_cols(conn)
    _migrate_users(conn)
    _migrate_op_logs(conn)
    _migrate_quote_source(conn)
    conn.commit()


def _migrate_quote_cols(conn) -> None:
    """老库补列:昨收/涨跌停价 + 涨跌停标记 + 今开/主力净流入（幂等）。"""
    added = {"f18": "REAL", "f350": "REAL", "f351": "REAL",
             "f17": "REAL", "f62": "REAL",
             "limit_up": "INTEGER", "limit_down": "INTEGER"}
    for table in ("latest", "history"):
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, decl in added.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _migrate_users(conn) -> None:
    """老库补列:hidden 标记(隐藏 root 不出现在用户管理列表);
    risk_ack_at 风险声明确认时间(空 = 未确认,前端据此弹强制确认窗)。"""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "hidden" not in have:
        conn.execute(
            "ALTER TABLE users ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
    if "risk_ack_at" not in have:
        conn.execute(
            "ALTER TABLE users ADD COLUMN risk_ack_at TEXT")


def _migrate_op_logs(conn) -> None:
    """老库补列:ua 浏览器指纹(辅助定位操作来源)。"""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(op_logs)")}
    if "ua" not in have:
        conn.execute(
            "ALTER TABLE op_logs ADD COLUMN ua TEXT NOT NULL DEFAULT ''")


def _migrate_quote_source(conn) -> None:
    """老库补列:is_public 公开共享标记(公开后全站可用,他人仅见名称)。"""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(quote_source)")}
    if "is_public" not in have:
        conn.execute(
            "ALTER TABLE quote_source ADD COLUMN is_public INTEGER NOT NULL DEFAULT 0")


def seed_root(hash_password) -> None:
    """确保隐藏 root 账号存在(hidden=1,用户管理列表与管理接口均不可见/不可触碰)。

    密码只从环境变量 TS_ROOT_PASSWORD 取(不落代码):未设置时跳过创建并告警;
    账号已存在则只校正 hidden 标记,不动密码。
    """
    import logging
    from datetime import datetime

    conn = get_conn()
    row = conn.execute(
        "SELECT id, hidden FROM users WHERE username = ?",
        (config.ROOT_USERNAME,)).fetchone()
    if row:
        if not row["hidden"]:
            with conn:
                conn.execute("UPDATE users SET hidden = 1 WHERE id = ?",
                             (row["id"],))
        return
    if not config.ROOT_PASSWORD:
        logging.getLogger("db").warning(
            "TS_ROOT_PASSWORD 未设置,跳过创建隐藏 root 账号(%s)",
            config.ROOT_USERNAME)
        return
    with conn:
        conn.execute(
            "INSERT INTO users"
            " (username, password_hash, role, enabled, hidden, created_at)"
            " VALUES (?, ?, 'admin', 1, 1, ?)",
            (config.ROOT_USERNAME, hash_password(config.ROOT_PASSWORD),
             datetime.now().isoformat(timespec="seconds")),
        )


def seed_admin(hash_password) -> None:
    """首次启动时写入管理员；已有任何用户则跳过。"""
    from datetime import datetime

    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if n:
        return
    conn.execute(
        "INSERT INTO users (username, password_hash, role, enabled, created_at)"
        " VALUES (?, ?, 'admin', 1, ?)",
        (config.ADMIN_USERNAME, hash_password(config.ADMIN_PASSWORD),
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def replace_latest(rows, source: str, error: str = None) -> None:
    """原子替换最新快照；失败时仅记录错误、保留旧数据（前端可标记陈旧）。"""
    from datetime import datetime

    conn = get_conn()
    now = datetime.now().isoformat(timespec="seconds")
    with conn:
        if error is None:
            conn.execute("DELETE FROM latest")
            conn.executemany(
                "INSERT OR REPLACE INTO latest (" + ",".join(ALL_COLS) + ")"
                " VALUES (" + ",".join("?" for _ in ALL_COLS) + ")",
                [[r.get(c) for c in ALL_COLS] for r in rows],
            )
        conn.execute(
            "INSERT INTO snapshot_meta (id, fetched_at, source, total, ok, error)"
            " VALUES (1, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " fetched_at=excluded.fetched_at, source=excluded.source,"
            " total=excluded.total, ok=excluded.ok, error=excluded.error",
            (now, source, 0 if error else len(rows), 0 if error else 1, error),
        )


def latest_static() -> list:
    """上一轮快照的 code/name/industry 清单（腾讯兜底源的抓取清单与静态字段）。"""
    rows = get_conn().execute(
        "SELECT code, name, industry FROM latest").fetchall()
    return [dict(r) for r in rows]


def snapshot_meta() -> dict:
    """快照元信息（调度器据此判断上次抓取成败）。"""
    row = get_conn().execute(
        "SELECT * FROM snapshot_meta WHERE id = 1").fetchone()
    return dict(row) if row else {}


def save_history(trade_date: str) -> int:
    """把当前 latest 落一份到 history（每日收盘后调用）。"""
    conn = get_conn()
    cols = ",".join(ALL_COLS)
    with conn:
        cur = conn.execute(
            "INSERT OR REPLACE INTO history (trade_date, " + cols + ")"
            " SELECT ?, " + cols + " FROM latest",
            (trade_date,),
        )
    return cur.rowcount


def prune_op_logs(days: int) -> int:
    """清理过期的操作日志（每日维护任务调用）。"""
    from datetime import datetime, timedelta

    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM op_logs WHERE ts < ?", (cutoff,))
    return cur.rowcount


def backup_db(backup_dir: str = None, keep: int = None) -> str:
    """在线热备份整个数据库（sqlite backup API，WAL 下安全），滚动保留 N 份。

    备份含 users/history 等全部数据，是防磁盘故障的唯一副本——
    重要时期建议再异地下载一份。
    """
    from datetime import datetime

    keep = config.BACKUP_KEEP if keep is None else keep
    bdir = backup_dir or os.path.join(
        os.path.dirname(config.DB_PATH), "backups")
    os.makedirs(bdir, exist_ok=True)
    dst_path = os.path.join(
        bdir, "screener-%s.db" % datetime.now().strftime("%Y%m%d"))
    dst = sqlite3.connect(dst_path)
    try:
        with dst:
            get_conn().backup(dst)
    finally:
        dst.close()
    # 滚动清理最旧的备份
    files = sorted(f for f in os.listdir(bdir) if f.startswith("screener-"))
    for f in files[:-keep]:
        os.remove(os.path.join(bdir, f))
    return dst_path
