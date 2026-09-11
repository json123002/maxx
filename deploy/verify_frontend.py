"""只读核验公网首页和构建资源，不需要SSH凭据。"""
import hashlib
import http.client
import json
import os
from pathlib import Path
import time


def main():
    host = os.environ.get('TS_HOST', '47.94.235.93')
    local = Path(__file__).resolve().parents[1] / 'frontend'
    conn = http.client.HTTPConnection(host, timeout=15)

    def fetch(path):
        nonlocal conn
        for attempt in range(3):
            try:
                conn.request('GET', path, headers={'Cache-Control': 'no-cache'})
                response = conn.getresponse()
                body = response.read()
                if response.status != 200:
                    raise RuntimeError('HTTP ' + str(response.status))
                return body
            except Exception:
                conn.close()
                conn = http.client.HTTPConnection(host, timeout=15)
                if attempt == 2:
                    raise
                time.sleep(1)

    try:
        if fetch('/?verify=' + str(time.time_ns())) != (local / 'index.html').read_bytes():
            raise RuntimeError('Public index does not match final build')
        print('Public index matches FINAL build', flush=True)
        files = sorted((local / 'assets').iterdir())
        for i, file in enumerate(files, 1):
            body = fetch('/assets/' + file.name)
            if hashlib.sha256(body).digest() != hashlib.sha256(file.read_bytes()).digest():
                raise RuntimeError('Asset mismatch: ' + file.name)
            if i % 6 == 0:
                print('Public assets verified: ' + str(i), flush=True)
        health = json.loads(fetch('/api/health'))
        if health.get('status') != 'ok':
            raise RuntimeError('API unhealthy')
        print('API health: ' + json.dumps(health, ensure_ascii=True), flush=True)
        print('VERIFIED final release http://' + host + '/', flush=True)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
