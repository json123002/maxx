"""一键部署到阿里云服务器（在本机执行）：

    cd web && npm run build     # 先构建前端(Vue 产物输出到 frontend/)
    python deploy/deploy.py

步骤：装 python3.11 -> 上传代码到 /home/maxx/turnover-screener -> 建 venv 装依赖
-> 配置 systemd -> 切换 nginx 到前端目录+反代 -> 重启验证。
首次部署后：http://47.94.235.93/  账号 admin / admin123（请立即改密）。

注意：本脚本是全新服务器的一次性初始化工具，需要 root + 密码登录。
现有服务器已完成 SSH 加固（禁用 root/密码登录），日常部署请用
GitHub Actions Deploy 或 publish_frontend.py（maxx + 密钥）。
"""
import os
import posixpath
import sys

import paramiko

HOST = os.environ.get("TS_HOST", "47.94.235.93")
USER = os.environ.get("TS_USER", "root")
# 服务器 SSH 密码不落库:部署前 set TS_PASSWORD=xxx(PowerShell: $env:TS_PASSWORD="xxx")
PASSWORD = os.environ.get("TS_PASSWORD", "")
if not PASSWORD:
    raise SystemExit("缺少 TS_PASSWORD 环境变量(服务器 SSH 密码),拒绝部署")

# 隐藏 root 账号密码(可选):设置后部署时写入服务器 /etc/turnover-screener.env
# (systemd EnvironmentFile 注入,文件权限 600,不进 git);不设置则不动服务器现有值
ROOT_PASSWORD = os.environ.get("TS_ROOT_PASSWORD", "")

ROOT = os.path.dirname(os.path.abspath(__file__))          # deploy/
LOCAL = os.path.dirname(ROOT)                              # maxx/
REMOTE = "/home/maxx/turnover-screener"

PIP_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"


def run(ssh, cmd, check=True, sensitive=False):
    print("$ " + ("[sensitive command]" if sensitive else cmd), flush=True)
    _, out, err = ssh.exec_command(cmd, timeout=600)
    code = out.channel.recv_exit_status()
    o = out.read().decode("utf8", "replace")
    e = err.read().decode("utf8", "replace")
    if o.strip() and not sensitive:
        print(o.rstrip()[-1500:])
    if e.strip():
        print(e.rstrip()[-800:], file=sys.stderr)
    if check and code != 0:
        raise RuntimeError("command failed (%s): %s" % (code, "[sensitive command]" if sensitive else cmd))
    return o


def upload(sftp, local_dir, remote_dir):
    for base, dirs, files in os.walk(local_dir):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", "venv", "data", ".pytest_cache")]
        rel = os.path.relpath(base, local_dir).replace(os.sep, "/")
        rdir = remote_dir if rel == "." else posixpath.join(remote_dir, rel)
        try:
            sftp.mkdir(rdir)
        except OSError:
            pass
        for f in files:
            if f.endswith(".pyc"):
                continue
            lp = os.path.join(base, f)
            rp = posixpath.join(rdir, f)
            sftp.put(lp, rp)
            print("  put %s -> %s" % (lp, rp))


DISABLE_DEFAULT_SERVER = r'''
import re
p = "/etc/nginx/nginx.conf"
s = open(p, encoding="utf8").read()
if "turnover-mark" in s:
    print("already done")
elif "listen       80;" not in s:
    print("no default server on :80, skip")
else:
    m = re.search(r"\n    server \{.*?\n    \}\n", s, re.S)
    if not m:
        raise SystemExit("WARN: default server block not found, check nginx.conf")
    block = m.group(0)
    commented = ("\n    # turnover-mark: default server disabled,"
                 " see conf.d/turnover.conf\n"
                 + "\n".join("    # " + ln for ln in block.strip("\n").splitlines())
                 + "\n")
    open(p, "w", encoding="utf8").write(s.replace(block, commented))
    print("default server block commented")
'''


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASSWORD, timeout=20)
    sftp = ssh.open_sftp()

    print("== 1. install python3.11 ==")
    run(ssh, "dnf install -y python3.11 python3.11-pip")

    print("== 2. upload code ==")
    run(ssh, "mkdir -p %s/data" % REMOTE)
    upload(sftp, os.path.join(LOCAL, "backend"), REMOTE + "/backend")
    upload(sftp, os.path.join(LOCAL, "frontend"), REMOTE + "/frontend")
    sftp.put(os.path.join(ROOT, "turnover-api.service"),
             "/etc/systemd/system/turnover-api.service")
    sftp.put(os.path.join(ROOT, "nginx.conf"),
             "/etc/nginx/conf.d/turnover.conf")

    if ROOT_PASSWORD:
        # 敏感配置走服务器本地环境文件(systemd EnvironmentFile),不进代码库
        import shlex
        run(ssh, "printf 'TS_ROOT_PASSWORD=%s\\n' > /etc/turnover-screener.env"
                 " && chmod 600 /etc/turnover-screener.env"
                 % shlex.quote(ROOT_PASSWORD), sensitive=True)

    print("== 3. venv + deps (aliyun mirror) ==")
    run(ssh, "cd %s/backend && python3.11 -m venv venv && "
             "venv/bin/pip install -q --upgrade pip -i %s && "
             "venv/bin/pip install -q -r requirements.txt -i %s"
             % (REMOTE, PIP_MIRROR, PIP_MIRROR))

    print("== 4. nginx: backup + disable default server ==")
    run(ssh, "cp -n /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak || true")
    stdin, out, err = ssh.exec_command("python3", timeout=60)
    stdin.write(DISABLE_DEFAULT_SERVER)
    stdin.channel.shutdown_write()
    print(out.read().decode("utf8", "replace"))
    e = err.read().decode("utf8", "replace")
    if e.strip():
        raise RuntimeError(e)

    print("== 5. start services ==")
    run(ssh, "systemctl daemon-reload && systemctl enable turnover-api && "
             "systemctl restart turnover-api")
    run(ssh, "nginx -t && systemctl reload nginx")

    print("== 6. verify ==")
    run(ssh, "sleep 3; curl -s http://127.0.0.1:8000/api/health")
    run(ssh, "curl -s -o /dev/null -w 'frontend HTTP %{http_code}\\n' "
             "http://127.0.0.1/login.html")
    print("\nDone. Open http://%s/  login admin / admin123 (change it!)" % HOST)


if __name__ == "__main__":
    main()
