"""后端接口测试：独立临时库 + 关闭调度器（不触网）。"""
import os
import tempfile
import json

os.environ["TS_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="ts-test-"), "t.db")
os.environ["TS_ADMIN_PASSWORD"] = "admin123"
os.environ["TS_ROOT_PASSWORD"] = "test-root-pw"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config, db, kline, scheduler  # noqa: E402
from app.fetcher import limit_flags  # noqa: E402
from app.main import app  # noqa: E402
from app.routes import radar_routes as rr  # noqa: E402
from app.routes import watchlist_routes as wr  # noqa: E402
from app.routes.quote_routes import build_filter_sql  # noqa: E402

scheduler.start = lambda: None     # 测试不启动抓数调度
scheduler.shutdown = lambda: None


def _row(code, name, industry, market, f2, f3, f350=None, f351=None, **kw):
    """构造快照行,f350/f351 为涨/跌停价,标记与 fetcher 同口径。"""
    lu, ld = limit_flags(f2, f350, f351)
    base = dict(code=code, name=name, industry=industry, market=market,
                f2=f2, f3=f3, f18=None, f350=f350, f351=f351,
                limit_up=lu, limit_down=ld,
                f6=None, f7=None, f8=None, f9=None, f10=None,
                f20=None, f21=None, f23=None, f24=None, f25=None)
    base.update(kw)
    return base


SAMPLE = [
    # 主板涨停:最新价 == 涨停价
    _row("600001", "测试钢铁", "钢铁", "沪主板", 10.0, 10.01, f350=10.0, f351=8.19,
         f6=5e8, f7=8.0, f8=12.0, f9=15.0, f10=2.0,
         f20=100e8, f21=80e8, f23=1.5, f24=20.0, f25=30.0),
    # 主板 ST 跌停:限幅 5%,阈值法漏计的情形
    _row("000001", "ST测试", "银行", "深主板", 5.0, -4.94, f350=5.52, f351=5.0,
         f6=2e8, f7=6.0, f8=9.0, f9=-3.0, f10=1.0,
         f20=50e8, f21=50e8, f23=0.8, f24=-10.0, f25=-20.0),
    # 创业板涨停:20% 限幅
    _row("300001", "测试科技", "半导体", "创业板", 20.0, 19.98, f350=20.0, f351=13.34,
         f6=8e8, f7=15.0, f8=25.0, f9=60.0, f10=3.0,
         f20=200e8, f21=150e8, f23=5.0, f24=50.0, f25=80.0),
    # 停牌：f2/f350/f351 为空
    _row("600002", "停牌股", "钢铁", "沪主板", None, None),
    # 非 ST 跌停（对照 ST 跌停被口径剔除）
    _row("600003", "测试银行", "银行", "沪主板", 4.4, -10.02, f350=5.38, f351=4.4,
         f6=1e8, f7=3.0, f8=5.0, f9=6.0, f10=0.8,
         f20=40e8, f21=40e8, f23=0.7, f24=-8.0, f25=-15.0),
]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        db.replace_latest(SAMPLE, "实时行情")
        yield c


def login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


# ===== 认证 =====
def test_health_public(client):
    assert client.get("/api/health").status_code == 200


def test_quote_requires_auth(client):
    assert client.get("/api/quote/list").status_code == 401


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "x"})
    assert r.status_code == 401


def test_seed_admin_login(client):
    h = login(client, "admin", "admin123")
    me = client.get("/api/auth/me", headers=h).json()["user"]
    assert me["username"] == "admin" and me["role"] == "admin" and me["root"] is True


# ===== 筛选 SQL =====
def _args(**kw):
    base = dict(markets=[], tmin=None, tmax=None, cmin=None, cmax=None,
                industry=None, kw=None, no_st=True, no_suspend=True, metrics=[])
    base.update(kw)
    return base


def test_filter_sql_swap_and_params():
    # 前端 range() 已交换；服务端对自定义指标区间填反也会交换
    sql, params = build_filter_sql(_args(tmin=8.0, cmin=-8.0, cmax=-5.0,
                                         metrics=[{"k": "f21", "min": 100.0, "max": 10.0}]))
    assert "f8 >= ?" in sql and "f3 <= ?" in sql
    assert "(f21 / 100000000.0) >= ?" in sql
    assert params[-2:] == [10.0, 100.0]          # min/max 已交换
    # 行业多选:IN 参数化,单选/多选同一通路
    sql, params = build_filter_sql(_args(industry=["半导体", "钢铁"]))
    assert "industry IN (?,?)" in sql and params == ["半导体", "钢铁"]


def test_quote_list_filters(client):
    h = login(client, "admin", "admin123")
    # 默认剔除 ST + 停牌 → 剩 600001/300001；换手>=20 → 只剩 300001
    r = client.get("/api/quote/list?tmin=20", headers=h).json()
    assert r["total"] == 1 and r["rows"][0]["f12"] == "300001"
    # 不剔 ST → 000001 回来
    r = client.get("/api/quote/list?no_st=false", headers=h).json()
    assert r["total"] == 4
    # 行业 + 关键词
    r = client.get("/api/quote/list?industry=钢铁", headers=h).json()
    assert r["total"] == 1
    r = client.get("/api/quote/list?kw=半导体&no_st=false", headers=h).json()
    assert r["total"] == 0                       # kw 匹配代码/名称,不匹配行业


def test_quote_meta_stats(client):
    h = login(client, "admin", "admin123")
    m = client.get("/api/quote/meta", headers=h).json()
    assert m["stats"]["valid"] == 4              # 停牌股不计
    assert m["stats"]["up"] == 2
    assert m["stats"]["down"] == 2               # 平盘不计入下跌
    assert m["stats"]["flat"] == 0               # 平盘单独计数(无 f3=0 的行)
    assert m["stats"]["limit_up"] == 2           # 主板/创业板封板各 1
    assert m["stats"]["limit_down"] == 1         # 非 ST 跌停计入;ST 跌停按口径剔除
    names = {x["name"] for x in m["industries"]}
    assert names == {"钢铁", "银行", "半导体"}


# ===== 涨跌停判定（最新价 vs 东财涨/跌停价）=====
def test_limit_flags():
    assert limit_flags(10.0, 10.0, 8.19) == (1, 0)        # 封涨停
    assert limit_flags(9.0, 10.0, 8.19) == (0, 0)         # 差一截不算
    assert limit_flags(5.0, 5.52, 5.0) == (0, 1)          # 封跌停(ST 5%)
    assert limit_flags(40.0, None, None) == (0, 0)        # 新股无涨跌停价
    assert limit_flags(None, None, None) == (None, None)  # 停牌


# ===== 用户管理 =====
def test_admin_user_lifecycle(client):
    h = login(client, "admin", "admin123")
    r = client.post("/api/admin/users", headers=h,
                    json={"username": "bob", "password": "bob123456"})
    assert r.status_code == 201
    uid = r.json()["id"]
    # 普通用户不能访问管理接口
    hb = login(client, "bob", "bob123456")
    assert client.get("/api/admin/users", headers=hb).status_code == 403
    assert client.get("/api/quote/list", headers=hb).status_code == 200
    # 停用后立即失效（会话被吊销 → 401/403）
    client.patch(f"/api/admin/users/{uid}", headers=h, json={"enabled": False})
    assert client.get("/api/quote/list", headers=hb).status_code in (401, 403)
    # 删除
    assert client.delete(f"/api/admin/users/{uid}", headers=h).status_code == 200


def test_admin_cannot_disable_self(client):
    hs = login(client, "admin", "admin123")
    _mkuser(client, hs, "selfmgr", "mgr123456", role="admin")
    h = login(client, "selfmgr", "mgr123456")
    me = client.get("/api/auth/me", headers=h).json()["user"]
    r = client.patch(f"/api/admin/users/{me['id']}", headers=h, json={"enabled": False})
    assert r.status_code == 400
    # 清理
    client.delete(f"/api/admin/users/{me['id']}", headers=hs)


# ===== 权限层级：root(admin账号) > 管理员 > 普通用户 =====
def _mkuser(client, h, username, password, role="user"):
    r = client.post("/api/admin/users", headers=h,
                    json={"username": username, "password": password, "role": role})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_role_hierarchy(client):
    hs = login(client, "admin", "admin123")          # root(种子账号)
    root_id = client.get("/api/auth/me", headers=hs).json()["user"]["id"]
    mgr_id = _mkuser(client, hs, "mgr01", "mgr123456", role="admin")
    hm = login(client, "mgr01", "mgr123456")          # 普通管理员
    me_mgr = client.get("/api/auth/me", headers=hm).json()["user"]
    assert me_mgr["role"] == "admin" and me_mgr["root"] is False

    # 管理员可以访问管理接口、创建普通用户
    assert client.get("/api/admin/users", headers=hm).status_code == 200
    # 管理员的列表里看不到 root 账号;root 自己能看到
    names_mgr = {u["username"] for u in client.get("/api/admin/users", headers=hm).json()["users"]}
    names_root = {u["username"] for u in client.get("/api/admin/users", headers=hs).json()["users"]}
    assert "admin" not in names_mgr and "admin" in names_root
    uid = _mkuser(client, hm, "usr01", "usr123456")
    # 管理员不能创建管理员
    r = client.post("/api/admin/users", headers=hm,
                    json={"username": "usr02", "password": "usr123456", "role": "admin"})
    assert r.status_code == 403
    # 管理员不能动 root：改角色 / 停用 / 重置密码 / 删除全部 403
    assert client.patch(f"/api/admin/users/{root_id}", headers=hm,
                        json={"role": "user"}).status_code == 403
    assert client.patch(f"/api/admin/users/{root_id}", headers=hm,
                        json={"enabled": False}).status_code == 403
    assert client.patch(f"/api/admin/users/{root_id}", headers=hm,
                        json={"password": "hack123456"}).status_code == 403
    assert client.delete(f"/api/admin/users/{root_id}", headers=hm).status_code == 403
    # 管理员不能动其他管理员
    mgr2_id = _mkuser(client, hs, "mgr02", "mgr123456", role="admin")
    assert client.patch(f"/api/admin/users/{mgr2_id}", headers=hm,
                        json={"role": "user"}).status_code == 403
    assert client.patch(f"/api/admin/users/{mgr2_id}", headers=hm,
                        json={"enabled": False}).status_code == 403
    assert client.delete(f"/api/admin/users/{mgr2_id}", headers=hm).status_code == 403
    # 管理员不能提升普通用户为管理员
    assert client.patch(f"/api/admin/users/{uid}", headers=hm,
                        json={"role": "admin"}).status_code == 403
    # 管理员可以停用/删除普通用户
    assert client.patch(f"/api/admin/users/{uid}", headers=hm,
                        json={"enabled": False}).status_code == 200
    assert client.delete(f"/api/admin/users/{uid}", headers=hm).status_code == 200
    # root 自己也不能通过管理接口被降权（包括自己）
    assert client.patch(f"/api/admin/users/{root_id}", headers=hs,
                        json={"role": "user"}).status_code == 403
    # root 可以降级/删除管理员
    assert client.patch(f"/api/admin/users/{mgr_id}", headers=hs,
                        json={"role": "user"}).status_code == 200
    assert client.delete(f"/api/admin/users/{mgr_id}", headers=hs).status_code == 200
    assert client.delete(f"/api/admin/users/{mgr2_id}", headers=hs).status_code == 200


def test_change_password(client):
    h = login(client, "admin", "admin123")
    r = client.post("/api/auth/change-password", headers=h,
                    json={"old_password": "admin123", "new_password": "admin456"})
    assert r.status_code == 200
    login(client, "admin", "admin456")
    # 改回，避免影响其它用例
    client.post("/api/auth/change-password", headers=h,
                json={"old_password": "admin456", "new_password": "admin123"})


# ===== 自选 =====
def test_watchlist_requires_auth(client):
    assert client.get("/api/watchlist").status_code == 401
    assert client.post("/api/watchlist", json={"code": "600001"}).status_code == 401


def test_watchlist_lifecycle(client):
    h = login(client, "admin", "admin123")
    # 空列表
    assert client.get("/api/watchlist", headers=h).json()["rows"] == []
    # 添加:停牌股(不在快照默认筛选里,但快照中存在)也能加
    r = client.post("/api/watchlist", headers=h, json={"code": "600001"})
    assert r.status_code == 200 and r.json()["name"] == "测试钢铁"
    # 重复添加幂等
    assert client.post("/api/watchlist", headers=h,
                       json={"code": "600001"}).status_code == 200
    rows = client.get("/api/watchlist", headers=h).json()["rows"]
    assert len(rows) == 1
    assert rows[0]["f12"] == "600001" and rows[0]["f2"] == 10.0  # 关联到快照行情
    # 不存在的代码 → 404;非法代码 → 400/422
    assert client.post("/api/watchlist", headers=h,
                       json={"code": "999999"}).status_code == 404
    assert client.post("/api/watchlist", headers=h,
                       json={"code": "abc123"}).status_code in (400, 422)
    # 搜索:按名称/代码,附带 added 标记
    r = client.get("/api/watchlist/search?kw=测试", headers=h).json()["rows"]
    assert any(x["f12"] == "600001" and x["added"] for x in r)
    assert any(x["f12"] == "300001" and not x["added"] for x in r)
    assert client.get("/api/watchlist/search?kw=", headers=h).json()["rows"] == []
    # 删除(幂等)
    assert client.delete("/api/watchlist/600001", headers=h).status_code == 200
    assert client.delete("/api/watchlist/600001", headers=h).status_code == 200
    assert client.get("/api/watchlist", headers=h).json()["rows"] == []


def test_watchlist_search_pinyin(client, monkeypatch):
    """纯字母输入走东财拼音联想：合并去重、仅 A 股、须在本地快照中。"""
    h = login(client, "admin", "admin123")
    client.post("/api/watchlist", headers=h, json={"code": "600001"})

    payload = {"QuotationCodeTable": {"Data": [
        {"Code": "300001", "Name": "测试科技", "PinYin": "CSKJ",
         "Classify": "AStock"},
        {"Code": "600001", "Name": "测试钢铁", "PinYin": "CSGT",
         "Classify": "AStock"},
        {"Code": "09999", "Name": "某港股", "PinYin": "MGG",
         "Classify": "HK"},          # 非 A 股：过滤
        {"Code": "999999", "Name": "不在快照", "PinYin": "BZK",
         "Classify": "AStock"},       # 不在本地快照：过滤
    ]}}

    class _Resp:
        text = json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(wr._suggest, "get", lambda *a, **k: _Resp())
    rows = client.get("/api/watchlist/search?kw=cs", headers=h).json()["rows"]
    assert [r["f12"] for r in rows] == ["300001", "600001"]  # 保持联想相关度序
    assert rows[0]["pinyin"] == "CSKJ" and not rows[0]["added"]
    assert rows[1]["added"]                    # 已加自选的联想项带标记

    # 部分东财节点返回 JSONP 壳(jQuery…({...})),剥壳后同样可解析
    class _RespJsonp:
        text = "jQuery3510_1(" + json.dumps(payload, ensure_ascii=False) + ")"

    monkeypatch.setattr(wr._suggest, "get", lambda *a, **k: _RespJsonp())
    rows = client.get("/api/watchlist/search?kw=cs", headers=h).json()["rows"]
    assert [r["f12"] for r in rows] == ["300001", "600001"]


def test_watchlist_search_pinyin_fallback(client, monkeypatch):
    """联想接口异常时静默降级为纯本地搜索，不报错不触网。"""
    def _boom(*a, **k):
        raise ConnectionError("suggest down")
    monkeypatch.setattr(wr._suggest, "get", _boom)
    h = login(client, "admin", "admin123")
    assert client.get("/api/watchlist/search?kw=zz", headers=h).json()["rows"] == []
    # 数字/中文输入不走联想,本地结果不受影响
    rows = client.get("/api/watchlist/search?kw=测试", headers=h).json()["rows"]
    codes = {r["f12"] for r in rows}
    assert {"600001", "300001"} <= codes


def test_watchlist_per_user(client):
    hs = login(client, "admin", "admin123")
    r = client.post("/api/admin/users", headers=hs,
                    json={"username": "wl_user", "password": "user123", "role": "user"})
    assert r.status_code == 201
    hu = login(client, "wl_user", "user123")
    client.post("/api/watchlist", headers=hs, json={"code": "600001"})
    client.post("/api/watchlist", headers=hu, json={"code": "300001"})
    a = client.get("/api/watchlist", headers=hs).json()["rows"]
    u = client.get("/api/watchlist", headers=hu).json()["rows"]
    assert [x["f12"] for x in a] == ["600001"]
    assert [x["f12"] for x in u] == ["300001"]
    # 删除用户级联清掉自选
    uid = client.get("/api/admin/users", headers=hs).json()["users"]
    uid = [x["id"] for x in uid if x["username"] == "wl_user"][0]
    client.delete(f"/api/admin/users/{uid}", headers=hs)
    conn = db.get_conn()
    n = conn.execute("SELECT COUNT(*) AS c FROM watchlist WHERE user_id = ?",
                     (uid,)).fetchone()["c"]
    assert n == 0


def test_quote_stock(client):
    h = login(client, "admin", "admin123")
    r = client.get("/api/quote/stock/600001", headers=h)
    assert r.status_code == 200
    row = r.json()["row"]
    assert row["f12"] == "600001" and row["f14"] == "测试钢铁" and row["f2"] == 10.0
    assert client.get("/api/quote/stock/999999", headers=h).status_code == 404
    assert client.get("/api/quote/stock/abc", headers=h).status_code == 400
    assert client.get("/api/quote/stock/600001").status_code == 401


# ===== 隐藏 root 账号 =====
def test_hidden_root_invisible(client):
    hr = login(client, config.ROOT_USERNAME, config.ROOT_PASSWORD)
    me = client.get("/api/auth/me", headers=hr).json()["user"]
    assert me["hidden"] is True
    # 任何人(含种子 admin 和 root 自己)的用户列表都看不到隐藏账号
    ha = login(client, "admin", "admin123")
    for h in (ha, hr):
        names = {u["username"] for u in
                 client.get("/api/admin/users", headers=h).json()["users"]}
        assert config.ROOT_USERNAME not in names
    # 管理接口触碰隐藏账号 → 404(不暴露其存在)
    rid = db.get_conn().execute(
        "SELECT id FROM users WHERE username = ?",
        (config.ROOT_USERNAME,)).fetchone()["id"]
    assert client.patch(f"/api/admin/users/{rid}", headers=ha,
                        json={"enabled": False}).status_code == 404
    assert client.delete(f"/api/admin/users/{rid}", headers=ha).status_code == 404
    # 同名账号不可再创建
    assert client.post("/api/admin/users", headers=ha,
                       json={"username": config.ROOT_USERNAME,
                             "password": "xxxxxx"}).status_code == 409


# ===== 操作日志(仅隐藏 root 可见)=====
def test_op_logs(client):
    hr = login(client, config.ROOT_USERNAME, config.ROOT_PASSWORD)
    ha = login(client, "admin", "admin123")
    # 非 root 访问 → 404;未登录 → 401
    assert client.get("/api/logs", headers=ha).status_code == 404
    assert client.get("/api/logs").status_code == 401
    # 登录动作已被记录
    rows = client.get("/api/logs", headers=hr).json()["rows"]
    acts = {(r["username"], r["action"]) for r in rows}
    assert (config.ROOT_USERNAME, "login") in acts
    assert ("admin", "login") in acts
    # 前端埋点上报:白名单内记录,白名单外 400
    assert client.post("/api/track", headers=ha, json={
        "action": "screener_run", "detail": "min_tov=3 → 42 只"}).status_code == 200
    assert client.post("/api/track", headers=ha,
                       json={"action": "rm_rf"}).status_code == 400
    r = client.get("/api/logs", headers=hr,
                   params={"username": "admin", "action": "screener_run"}).json()
    assert r["total"] == 1 and r["rows"][0]["detail"] == "min_tov=3 → 42 只"
    assert "screener_run" in r["actions"]
    # 自选加/删被服务端记录(删除详情带股票名称)
    client.post("/api/watchlist", headers=ha, json={"code": "600001"})
    client.delete("/api/watchlist/600001", headers=ha)
    r = client.get("/api/logs", headers=hr,
                   params={"action": "watchlist_add"}).json()
    assert any(x["username"] == "admin" and "600001" in x["detail"]
               for x in r["rows"])
    r = client.get("/api/logs", headers=hr,
                   params={"kw": "600001", "action": "watchlist_del"}).json()
    assert any("测试钢铁" in x["detail"] for x in r["rows"])
    # 登录失败也被记录(安全信号)
    client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    r = client.get("/api/logs", headers=hr,
                   params={"action": "login_fail"}).json()
    assert any(x["username"] == "admin" for x in r["rows"])


def test_track_records_real_ip_and_ua(client, monkeypatch):
    """反代场景：client.host 恒为回环地址，真实 IP 必须来自 X-Forwarded-For/X-Real-IP。"""
    monkeypatch.setattr(  # 测试不触网：归属地解析失败须静默降级
        "app.oplog.requests.post",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    ha = login(client, "admin", "admin123")
    client.post("/api/track",
                headers={**ha, "X-Forwarded-For": "203.0.113.7, 10.0.0.1",
                         "User-Agent": "pytest-ua/1.0"},
                json={"action": "stock_view", "detail": "600001 测试钢铁"})
    hr = login(client, config.ROOT_USERNAME, config.ROOT_PASSWORD)
    r = client.get("/api/logs", headers=hr,
                   params={"action": "stock_view", "kw": "600001"}).json()
    row = r["rows"][0]
    assert row["ip"] == "203.0.113.7"      # 取 XFF 链路第一跳,不是 127.0.0.1
    assert row["ua"] == "pytest-ua/1.0"
    assert row["region"] == "内网/本机"     # 保留地址(TEST-NET)不查外网


def test_ip_region_format():
    from app.oplog import _fmt_region, _is_public_ip
    assert _fmt_region({"country": "中国", "regionName": "上海",
                        "city": "上海", "isp": "电信"}) == "上海 · 电信"
    assert _fmt_region({"country": "中国", "regionName": "浙江",
                        "city": "杭州", "isp": "阿里云"}) == "浙江杭州 · 阿里云"
    assert _fmt_region({"country": "美国", "regionName": "California",
                        "city": "", "isp": ""}) == "美国 California"
    assert _is_public_ip("8.8.8.8") is True
    assert _is_public_ip("127.0.0.1") is False
    assert _is_public_ip("192.168.1.1") is False
    assert _is_public_ip("not-an-ip") is False


# ===== 登录防爆破限流 =====
def test_login_rate_limit(client):
    # 用独立 IP + 独立用户名，不影响套件里 admin 的正常登录
    h = {"X-Forwarded-For": "198.51.100.9"}
    for _ in range(10):
        r = client.post("/api/auth/login", headers=h,
                        json={"username": "brute", "password": "x"})
        assert r.status_code == 401
    # 第 11 次触发 429;同 IP 换一个用户名也被限(IP 维度)
    r = client.post("/api/auth/login", headers=h,
                    json={"username": "brute", "password": "x"})
    assert r.status_code == 429
    r = client.post("/api/auth/login", headers=h,
                    json={"username": "other", "password": "x"})
    assert r.status_code == 429
    # 不同 IP 的正常用户不受影响
    r = client.post("/api/auth/login", headers={"X-Forwarded-For": "198.51.100.10"},
                    json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200


# ===== 每日维护：备份 + 日志清理 =====
def test_backup_and_prune(client, tmp_path):
    # 备份文件可打开且含业务表
    p = db.backup_db(backup_dir=str(tmp_path), keep=2)
    import sqlite3
    chk = sqlite3.connect(p)
    assert chk.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='users'").fetchone()[0] == 1
    chk.close()
    # 滚动清理:再备两份,最旧的被删
    db.backup_db(backup_dir=str(tmp_path), keep=2)
    db.backup_db(backup_dir=str(tmp_path), keep=2)
    assert len([f for f in os.listdir(tmp_path) if f.startswith("screener-")]) == 1
    # 日志清理:过期删除,近期保留
    conn = db.get_conn()
    with conn:
        conn.execute("INSERT INTO op_logs (ts, username, action) VALUES"
                     " ('2020-01-01T00:00:00', 'old', 'login')")
    assert db.prune_op_logs(180) == 1
    assert conn.execute(
        "SELECT COUNT(*) AS c FROM op_logs WHERE username = 'old'").fetchone()["c"] == 0


# ===== 历史榜单回看 =====
def test_history_endpoints(client):
    h = login(client, "admin", "admin123")
    # 落一天历史(用 latest 里的样本数据)
    n = db.save_history("2026-09-10")
    assert n == len(SAMPLE)
    r = client.get("/api/quote/history/dates", headers=h).json()
    assert "2026-09-10" in r["dates"]
    # 榜单:换手降序、统计正确、涨跌停标记透出
    d = client.get("/api/quote/history?date=2026-09-10", headers=h).json()
    assert d["total"] == len(SAMPLE)
    f8s = [x["f8"] for x in d["rows"] if x["f8"] is not None]
    assert f8s == sorted(f8s, reverse=True)
    assert d["stats"]["limit_up"] == 2 and d["stats"]["limit_down"] == 2  # 历史统计不剔 ST
    assert any(x["f12"] == "600001" and x["limit_up"] == 1 for x in d["rows"])
    # 关键词过滤 + 参数校验 + 未登录
    assert client.get("/api/quote/history?date=2026-09-10&kw=钢铁",
                      headers=h).json()["total"] == 1  # kw 只匹配代码/名称,600002 名称是"停牌股"
    assert client.get("/api/quote/history?date=2026/09/10",
                      headers=h).status_code == 400
    assert client.get("/api/quote/history/dates").status_code == 401


# ===== 涨停雷达（一进二粗筛） =====
def _hist(date, code, name, f2, lu, ld=0, f6=None):
    """直接插一行历史(基因/前高判定需要多日序列,replace_latest 造不出来)。"""
    conn = db.get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO history"
        " (trade_date, code, name, industry, market, f2, f6, limit_up, limit_down)"
        " VALUES (?,?,?, '钢铁', '沪主板', ?,?,?,?)",
        (date, code, name, f2, f6, lu, ld))
    conn.commit()


def _pin_radar_today(monkeypatch, iso):
    """把雷达路由的"今天"钉成指定日期,与真实跑测日期解耦。

    radar_routes 以 `from datetime import datetime` 引入,替换其模块级
    datetime 即可;只需支持 now().date().isoformat() 调用链。
    """
    class _FakeDate:
        @staticmethod
        def isoformat():
            return iso

    class _FakeNow:
        @staticmethod
        def date():
            return _FakeDate

    class _FakeDatetime:
        @staticmethod
        def now():
            return _FakeNow

    monkeypatch.setattr(rr, "datetime", _FakeDatetime)


def test_radar_1to2(client, monkeypatch):
    h = login(client, "admin", "admin123")
    _pin_radar_today(monkeypatch, "2026-09-11")  # t0=09-12 ≠ 今天 → 实盘口径
    monkeypatch.setattr(kline, "get_bars",
                        lambda code, days=250: [])  # 无日K → 退化 history 口径
    # 基因序列:600005 在 09-08/09-09 两连板后 09-10/09-11 连续跌停 = A杀一次
    _hist("2026-09-08", "600005", "测试基因", 7.5, 1, f6=8e7)
    _hist("2026-09-09", "600005", "测试基因", 8.25, 1, f6=9e7)
    _hist("2026-09-10", "600005", "测试基因", 7.43, 0, ld=1, f6=1.1e8)
    # 600001 的前高锚点(收盘 10.0):自给自足,不依赖其它用例落库的 SAMPLE 行
    _hist("2026-09-09", "600001", "测试钢铁", 10.0, 0, f6=3e8)
    # 前日(t1=09-11):候选票都不涨停(首板判定);300001 涨停(→ 次日算连板,列末标注)
    _hist("2026-09-11", "600001", "测试钢铁", 9.5, 0, f6=4e8)
    _hist("2026-09-11", "600005", "测试基因", 6.69, 0, ld=1, f6=1e8)
    _hist("2026-09-11", "300001", "测试科技", 18.0, 1, f6=5e8)
    # 昨日(t0=09-12)涨停:600001/600005 首板、300001 连板;ST 涨停被名称过滤
    _hist("2026-09-12", "600001", "测试钢铁", 10.45, 1, f6=5e8)
    _hist("2026-09-12", "600005", "测试基因", 7.36, 1, f6=1.2e8)
    _hist("2026-09-12", "300001", "测试科技", 19.8, 1, f6=6e8)
    _hist("2026-09-12", "000001", "ST测试", 5.25, 1, f6=2e8)
    # 今日快照:600001 六维全好(高开4.3% 换手15 额比1.2 主力2亿 突破前高10.0);
    # 600005 缺 f18 → 用昨收兜底,基因 A杀 → 放弃
    db.replace_latest([
        _row("600001", "测试钢铁", "钢铁", "沪主板", 11.5, 10.05,
             f350=11.5, f351=9.4, f6=6e8, f8=15.0, f17=10.9, f18=10.45,
             f62=2e8, f21=80e8),
        _row("600005", "测试基因", "化工", "沪主板", 8.1, 10.03,
             f350=8.1, f351=6.62, f6=1.5e8, f8=12.0, f17=8.9, f18=None,
             f62=5e7, f21=30e8),
        _row("300001", "测试科技", "半导体", "创业板", 21.0, 6.06,
             f350=23.76, f351=15.84, f6=7e8, f8=20.0, f17=20.0, f18=19.8,
             f62=1e8, f21=150e8),
    ], "实时行情")

    assert client.get("/api/radar/1to2").status_code == 401
    d = client.get("/api/radar/1to2", headers=h).json()
    assert d["date"] == "2026-09-12"
    codes = [r["f12"] for r in d["rows"]]
    # ST 000001 仍被排除;连板 300001 不剔除,标注 board=2 排末尾
    assert codes == ["600001", "600005", "300001"]
    assert [r["board"] for r in d["rows"]] == [1, 1, 2]
    a, b = d["rows"][0], d["rows"][1]
    assert a["verdict"] == "候选" and all(v == "good" for v in a["dims"].values())
    assert a["open_pct"] == 4.31 and a["amt_ratio"] == 1.2
    assert a["main_net_yi"] == 2.0 and a["dist_high"] == 15.0
    assert b["verdict"] == "放弃" and b["dims"]["gene"] == "bad"
    assert b["kill_a"] == 1 and b["max_streak"] == 2
    assert d["stat"] == {"候选": 1, "观察": 0, "放弃": 1}  # 统计只算首板
    assert d["rules"]["open"].startswith("高开 3~6%")  # 阈值口径随响应下发
    assert d["review"] is False                        # t0 是"明天",实盘口径


def test_radar_review_mode(client, monkeypatch):
    """复盘视角(首板日 == 今天):竞价/额比降级为待确认,不参与否决。"""
    h = login(client, "admin", "admin123")
    # 把"今天"钉在 09-12(t0 必然 == 今天 → 复盘视角,与真实跑测日期解耦)
    _pin_radar_today(monkeypatch, "2026-09-12")
    monkeypatch.setattr(kline, "get_bars", lambda code, days=250: [])
    # 600006:09-11 未涨停、09-12 首板;竞价 +1%(实盘口径 bad)→ 复盘应降级 warn
    _hist("2026-09-11", "600006", "复盘股", 9.2, 0, f6=4e8)
    _hist("2026-09-12", "600006", "复盘股", 10.12, 1, f6=5e8)
    db.replace_latest([
        _row("600006", "复盘股", "钢铁", "沪主板", 11.0, 8.7,
             f350=11.11, f351=9.1, f6=6e8, f8=15.0, f17=10.3, f18=10.12,
             f62=2e8, f21=60e8),
    ], "实时行情")
    d = client.get("/api/radar/1to2", headers=h).json()
    assert d["review"] is True and d["date"] == "2026-09-12"
    r = [x for x in d["rows"] if x["f12"] == "600006"][0]
    assert r["dims"]["open"] == "warn" and r["dims"]["amt"] == "warn"
    assert r["verdict"] != "放弃"   # 结构维度健康 → 复盘不给死刑


def _bar(date, close, pct, high=None):
    """造一根日K bar(与 kline.get_bars 返回结构一致)。"""
    return {"date": date, "open": close, "high": high if high is not None else close,
            "low": close, "close": close, "vol": 1e6, "amount": 1e8, "pct": pct}


def test_radar_kline_gene(client, monkeypatch):
    """日K路径:前高取区间最高价,基因含炸板——均来自日K而非 history。"""
    h = login(client, "admin", "admin123")
    bars = []
    px = 10.5
    for n in list(range(20, 27)) + list(range(3, 8)):  # 12 根填充 K 线
        for prefix in ("2026-07-", "2026-08-"):
            dt = prefix + "%02d" % n
            if (prefix == "2026-07-") == (n >= 20):
                bars.append(_bar(dt, px, 0.5))
                px += 0.02
    bars += [
        _bar("2026-08-09", 11.0, 2.6),                # 前一日收 11.0 → 锚点日涨幅够不到涨停
        _bar("2026-08-10", 10.0, 1.0, high=12.0),   # 前高锚点(最高价 12.0,涨幅 9.1% 不算炸板)
        _bar("2026-08-11", 10.5, 5.0, high=11.02),  # 炸板:盘中触板 10.2% 未封
        _bar("2026-08-12", 10.8, 2.86, high=11.55), # 炸板
        _bar("2026-08-13", 10.9, 0.93, high=11.88), # 炸板(累计 3 次 → 基因不合格)
        _bar("2026-08-14", 10.45, 10.0),            # 两连板(高点始终低于 12.0 锚点)…
        _bar("2026-08-15", 11.50, 10.0),
        _bar("2026-08-16", 10.35, -10.0),           # … 后连续两跌停 = A杀
        _bar("2026-08-17", 9.32, -10.0),
        _bar("2026-09-11", 9.5, 1.0),
        _bar("2026-09-12", 10.45, 10.0),            # t0 首板
    ]
    monkeypatch.setattr(kline, "get_bars", lambda code, days=250: bars)
    _hist("2026-09-11", "600007", "日K股", 9.5, 0, f6=4e8)
    _hist("2026-09-12", "600007", "日K股", 10.45, 1, f6=5e8)
    # 快照其余维度全部健康;f350=11.0 < 前高 12.0 → 距前高 -8.3% 落入阻力区
    db.replace_latest([
        _row("600007", "日K股", "钢铁", "沪主板", 10.9, 4.31,
             f350=11.0, f351=9.4, f6=6e8, f8=15.0, f17=10.9, f18=10.45,
             f62=2e8, f21=50e8),
    ], "实时行情")
    d = client.get("/api/radar/1to2", headers=h).json()
    r = [x for x in d["rows"] if x["f12"] == "600007"][0]
    assert r["prev_high"] == 12.0 and r["dist_high"] == -8.3  # 最高价口径
    assert (r["kill_a"], r["max_streak"], r["zhaban"]) == (1, 2, 3)
    assert r["dims"]["gene"] == "bad" and r["dims"]["dist"] == "bad"
    assert r["verdict"] == "放弃"


def test_radar_board_streak_with_history_gap(client, monkeypatch):
    """history 断档(09-09~09-11 未落库)时,连板数以日K为准:
    600009 实际昨日(09-11)也涨停 → board=2 列末;600010 真首板 → board=1。"""
    h = login(client, "admin", "admin123")
    _pin_radar_today(monkeypatch, "2026-09-11")  # t0=09-12 ≠ 今天 → 实盘口径
    fill = [_bar("2026-08-%02d" % n, 9.0, 0.5) for n in range(1, 20)]
    bars = {
        # 09-11 涨停(pct 10.0):history 没落库这天,旧口径会误判首板
        "600009": fill + [_bar("2026-09-11", 9.9, 10.0),
                          _bar("2026-09-12", 10.89, 10.0)],
        "600010": fill + [_bar("2026-09-11", 9.5, 1.0),
                          _bar("2026-09-12", 10.45, 10.0)],
    }
    # 模块级共享库:其它用例的票也可能在候选池里,日K只覆盖本例两只
    monkeypatch.setattr(kline, "get_bars",
                        lambda code, days=250: bars.get(code, []))
    # t1=09-08(断档前最后一天)两只都未涨停 → 退化口径会以为都是首板
    _hist("2026-09-08", "600009", "断档连板", 9.0, 0, f6=3e8)
    _hist("2026-09-08", "600010", "断档首板", 9.2, 0, f6=3e8)
    _hist("2026-09-12", "600009", "断档连板", 10.89, 1, f6=5e8)
    _hist("2026-09-12", "600010", "断档首板", 10.45, 1, f6=5e8)
    db.replace_latest([
        _row("600009", "断档连板", "钢铁", "沪主板", 11.5, 5.6,
             f350=11.98, f351=9.8, f6=6e8, f8=15.0, f17=11.3, f18=10.89,
             f62=2e8, f21=50e8),
        _row("600010", "断档首板", "钢铁", "沪主板", 11.5, 10.05,
             f350=11.5, f351=9.4, f6=6e8, f8=15.0, f17=10.9, f18=10.45,
             f62=2e8, f21=80e8),
    ], "实时行情")
    d = client.get("/api/radar/1to2", headers=h).json()
    rows = {r["f12"]: r for r in d["rows"]}
    assert rows["600010"]["board"] == 1 and rows["600009"]["board"] == 2
    # 排序不变式:所有首板在所有连板之前;统计只含首板
    boards = [r["board"] > 1 for r in d["rows"]]
    assert boards == sorted(boards)
    assert d["stat"]["候选"] == sum(
        1 for r in d["rows"] if r["board"] == 1 and r["verdict"] == "候选")


def test_kline_cache(client, monkeypatch):
    """日K缓存:首次触网落库,当天内重复查询直接读缓存不再触网。"""
    calls = []
    payload = {"klines": [
        "2026-09-10,9.20,9.30,9.45,9.10,100000,93000000,0.54,1.09,0.10,1.2",
        "2026-09-11,9.35,9.50,9.60,9.28,120000,114000000,2.44,2.15,0.20,1.5",
    ]}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": payload}

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(kline._session, "get", fake_get)
    bars = kline.get_bars("600999")
    assert [b["date"] for b in bars] == ["2026-09-10", "2026-09-11"]
    assert bars[1]["close"] == 9.50 and bars[1]["high"] == 9.60
    assert bars[1]["pct"] == 2.15            # f59 官方涨跌幅
    again = kline.get_bars("600999")
    assert again == bars and len(calls) == 1  # 当天内第二次不触网
