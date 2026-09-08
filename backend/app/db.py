"""SQLite 访问层：建表、种子管理员、快照读写。

字段沿用东方财富接口字段名（f2 最新价 / f3 涨跌幅 / f6 成交额 / f7 振幅 /
f8 换手率 / f9 市盈率 / f10 量比 / f20 总市值 / f21 流通市值 / f23 市净率 /
f24 60日涨幅 / f25 年初至今涨幅），code/name/industry 对应 f12/f14/f100。
"""
import os
import sqlite3
import threading

from . import config

_local = threading.local()

QUOTE_COLS = ["f2", "f3", "f6", "f7", "f8", "f9", "f10",
              "f20", "f21", "f23", "f24", "f25"]
ALL_COLS = ["code", "name", "industry", "market"] + QUOTE_COLS


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
            f10 REAL, f20 REAL, f21 REAL, f23 REAL, f24 REAL, f25 REAL
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
            f10 REAL, f20 REAL, f21 REAL, f23 REAL, f24 REAL, f25 REAL,
            UNIQUE (trade_date, code)
        );
        CREATE INDEX IF NOT EXISTS idx_history_date ON history(trade_date);

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user',
            enabled       INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        """
    )
    conn.commit()


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


def save_history(trade_date: str) -> int:
    """把当前 latest 落一份到 history（每日收盘后调用）。"""
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "INSERT OR REPLACE INTO history"
            " (trade_date, code, name, industry, market, f2, f3, f6, f7, f8,"
            "  f9, f10, f20, f21, f23, f24, f25)"
            " SELECT ?, code, name, industry, market, f2, f3, f6, f7, f8,"
            "        f9, f10, f20, f21, f23, f24, f25 FROM latest",
            (trade_date,),
        )
    return cur.rowcount
