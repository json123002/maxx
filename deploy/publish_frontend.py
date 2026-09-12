"""仅发布静态前端。使用 maxx 账号 + 本机 ~/.ssh/id_ed25519 密钥登录（免密码）。"""
import hashlib
import os
from pathlib import Path
import time

import paramiko


def main():
    host = os.environ.get('TS_HOST', '47.94.235.93')
    user = os.environ.get('TS_USER', 'maxx')
    key = os.environ.get('TS_KEY', str(Path.home() / '.ssh' / 'id_ed25519'))
    if not Path(key).exists():
        raise SystemExit(f'缺少 SSH 私钥 {key}，拒绝发布')
    remote = '/home/maxx/turnover-screener/frontend'
    local = Path(__file__).resolve().parents[1] / 'frontend'
    index = (local / 'index.html').read_bytes()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    # 与项目现有发布脚本使用相同的首次主机连接策略。
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, username=user, key_filename=key, timeout=20,
                    allow_agent=False, look_for_keys=False)
        ssh.get_transport().set_keepalive(10)
        print('SSH connected', flush=True)
        with ssh.open_sftp() as sftp:
            old = sftp.open(remote + '/index.html', 'rb').read()
            stamp = str(time.time_ns())
            backup = remote + '/index.html.backup-' + stamp
            with sftp.open(backup, 'wb') as f:
                f.write(old)
            print('Backup: ' + backup, flush=True)
            files = sorted((local / 'assets').iterdir())
            for file in files:
                if not file.is_file():
                    continue
                data = file.read_bytes()
                target = remote + '/assets/' + file.name
                sftp.put(str(file), target)
                with sftp.open(target, 'rb') as f:
                    actual = f.read()
                if hashlib.sha256(actual).digest() != hashlib.sha256(data).digest():
                    raise RuntimeError('Asset checksum mismatch: ' + file.name)
            pending = remote + '/index.html.pending-' + stamp
            with sftp.open(pending, 'wb') as f:
                f.write(index)
            sftp.posix_rename(pending, remote + '/index.html')
            print('Index switched; assets verified: ' + str(len(files)), flush=True)
            try:
                from verify_frontend import main as verify
                verify()
                print('PUBLISHED http://' + host + '/ ; all public assets verified', flush=True)
            except Exception:
                rollback = remote + '/index.html.rollback-' + stamp
                try:
                    with sftp.open(rollback, 'wb') as f:
                        f.write(old)
                    sftp.posix_rename(rollback, remote + '/index.html')
                    print('Verification failed; previous index restored', flush=True)
                except Exception:
                    print('Rollback could not be confirmed. Run verify_frontend.py; backup: ' + backup, flush=True)
                raise
    finally:
        ssh.close()


if __name__ == '__main__':
    main()
