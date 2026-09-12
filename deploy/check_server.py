"""服务器巡检：服务状态 / 内存 / 数据库行数 / 最近日志（本机执行）。

    python deploy/check_server.py

使用 maxx 账号 + 本机 ~/.ssh/id_ed25519 密钥登录（免密码，服务器已禁用密码登录）。
"""
import os
from pathlib import Path

import paramiko

HOST = os.environ.get("TS_HOST", "47.94.235.93")
USER = os.environ.get("TS_USER", "maxx")
KEY = os.environ.get("TS_KEY", str(Path.home() / ".ssh" / "id_ed25519"))
if not Path(KEY).exists():
    raise SystemExit(f"缺少 SSH 私钥 {KEY}，拒绝连接")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, key_filename=KEY, timeout=20)

DB_CHECK = (
    "/home/maxx/turnover-screener/backend/venv/bin/python -c \""
    "import sqlite3;"
    "db=sqlite3.connect('/home/maxx/turnover-screener/backend/data/screener.db');"
    "print('latest rows:', db.execute('SELECT COUNT(*) FROM latest').fetchone()[0]);"
    "print('users:', db.execute('SELECT username,role,enabled FROM users').fetchall());"
    "print('meta:', db.execute('SELECT fetched_at,source,total,ok FROM snapshot_meta').fetchone())"
    "\""
)

for cmd in [
    "systemctl is-active turnover-api nginx",
    "systemctl show turnover-api -p MemoryCurrent",
    "free -h | head -2",
    DB_CHECK,
    "journalctl -u turnover-api --since '10 min ago' --no-pager | tail -6",
]:
    print("$ " + cmd[:70])
    print(c.exec_command(cmd)[1].read().decode("utf8", "replace"))
