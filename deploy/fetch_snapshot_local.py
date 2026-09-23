"""一次性应急脚本：本机低速代抓东财全市场收盘快照,存 JSON 供灌入服务器。

服务器 IP 被东财封禁期间使用(2026-09-23 封禁事件);本机也可能被限流,
故 1s 间隔 + 指数退避重试 + 断点续抓(progress 文件存在则跳过已抓页)。
用法: cd backend && python ../deploy/fetch_snapshot_local.py
输出: deploy/snapshot_local.json
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))

from app import fetcher  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PROGRESS = os.path.join(HERE, "snapshot_progress.json")
OUT = os.path.join(HERE, "snapshot_local.json")

state = {"pages": {}, "total": 0, "host": None}
def _save():
    with open(PROGRESS, "w", encoding="utf8") as f:
        json.dump(state, f, ensure_ascii=False)


if os.path.exists(PROGRESS):
    raw = open(PROGRESS, "rb").read()
    for enc in ("utf8", "gbk"):
        try:
            state = json.loads(raw.decode(enc))
            break
        except (UnicodeDecodeError, ValueError):
            continue

if not state["pages"]:
    first, host = fetcher._fetch_page_retry(1)
    state["total"] = first.get("total") or 0
    state["host"] = host
    state["pages"]["1"] = first.get("diff") or []
    _save()
    print("page 1 ok, total=%s" % state["total"], flush=True)

pages = (state["total"] + fetcher.PAGE_SIZE - 1) // fetcher.PAGE_SIZE
for pn in range(2, pages + 1):
    if str(pn) in state["pages"]:
        continue
    wait = 1.0
    for attempt in range(6):
        try:
            data, host = fetcher._fetch_page_retry(
                pn, preferred=state["host"])
            state["host"] = host
            state["pages"][str(pn)] = data.get("diff") or []
            break
        except Exception as e:  # noqa: BLE001
            print("page %s fail(%s): %s, sleep %ss"
                  % (pn, attempt, e, wait), flush=True)
            time.sleep(wait)
            wait = min(wait * 2, 60)
    else:
        raise SystemExit("page %s gave up, rerun to resume" % pn)
    _save()
    print("page %s/%s ok" % (pn, pages), flush=True)
    time.sleep(1.0)

rows = []
for pn in range(1, pages + 1):
    rows.extend(fetcher._normalize(x) for x in state["pages"][str(pn)])
seen, uniq = set(), []
for r in rows:
    if r["code"] and r["code"] not in seen:
        seen.add(r["code"])
        uniq.append(r)
with open(OUT, "w", encoding="utf8") as f:
    json.dump(uniq, f, ensure_ascii=False)
ok = sum(1 for r in uniq if (r.get("f8") or 0) > 0)
print("fetched %s rows, f8>0: %s -> %s" % (len(uniq), ok, OUT))
os.remove(PROGRESS)
