"""服务器巡检：服务状态 / 内存 / 数据库行数 / 最近日志（本机执行）。

    set TS_PASSWORD=xxx          # PowerShell: $env:TS_PASSWORD="xxx"
    python deploy/check_server.py
"""
import os

import paramiko

HOST = os.environ.get("TS_HOST", "47.94.235.93")
USER = os.environ.get("TS_USER", "root")
PASSWORD = os.environ.get("TS_PASSWORD", "")
if not PASSWORD:
    raise SystemExit("缺少 TS_PASSWORD 环境变量(服务器 SSH 密码),拒绝连接")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=20)

DB_CHECK = (
    "/opt/turnover-screener/backend/venv/bin/python -c \""
    "import sqlite3;"
    "db=sqlite3.connect('/opt/turnover-screener/backend/data/screener.db');"
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
