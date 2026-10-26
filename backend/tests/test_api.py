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
from app.routes import settings_routes as sr  # noqa: E402
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


def test_risk_ack_flow(client):
    """风险声明:未确认 → risk_ack=False;确认后落库 → True;重复确认幂等。"""
    h = login(client, "admin", "admin123")
    me = client.get("/api/auth/me", headers=h).json()["user"]
    assert me["risk_ack"] is False
    r = client.post("/api/auth/risk-ack", headers=h)
    assert r.status_code == 200 and r.json()["ok"] is True
    me = client.get("/api/auth/me", headers=h).json()["user"]
    assert me["risk_ack"] is True
    # 重复确认不报错、时间不被覆盖语义(幂等返回 ok)
    r = client.post("/api/auth/risk-ack", headers=h)
    assert r.status_code == 200
    # 未登录不可确认
    assert client.post("/api/auth/risk-ack").status_code == 401


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
def test_analysis_context_uses_full_market(client):
    h = login(client, "admin", "admin123")
    # 筛选只命中创业板一只，个股分析背景仍覆盖全市场和完整银行行业。
    assert client.get("/api/quote/list?tmin=20", headers=h).json()["total"] == 1
    r = client.get("/api/quote/context/600003", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["market"]["stats"]["valid"] == 4
    assert d["industry"]["n"] == 2
    assert d["industry"]["up"] == 0
    assert client.get("/api/quote/context/600003").status_code == 401
    assert client.get("/api/quote/context/999999", headers=h).json()["industry"] is None


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
        "app.oplog.requests.get",
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
    # pconline 返回 GBK JSON:{"ip","pro","city","region","addr","err"}
    assert _fmt_region({"pro": "上海市", "city": "上海市", "region": "长宁区",
                        "addr": "上海市长宁区 /普陀区电信ADSL"}) == "上海市 · 电信"
    assert _fmt_region({"pro": "浙江省", "city": "杭州市", "region": "西湖区",
                        "addr": "浙江省杭州市西湖区 联通"}) == "浙江省杭州市 · 联通"
    # 省市为空时用 region 兜底；addr 提取不到运营商就不拼
    assert _fmt_region({"pro": "", "city": "", "region": "未知",
                        "addr": "本地局域网"}) == "未知"
    assert _is_public_ip("8.8.8.8") is True
    assert _is_public_ip("127.0.0.1") is False
    assert _is_public_ip("192.168.1.1") is False
    assert _is_public_ip("not-an-ip") is False


def test_track_page_view(client):
    """页面打开埋点已加入白名单；未知动作仍 400。"""
    ha = login(client, "admin", "admin123")
    assert client.post("/api/track", headers=ha,
                       json={"action": "page_view", "detail": "总览"}
                       ).status_code == 200
    assert client.post("/api/track", headers=ha,
                       json={"action": "rm_rf"}).status_code == 400


def test_enrich_regions_pconline(client, monkeypatch):
    """pconline 归属地：格式化 + 成功才缓存 + err/异常静默跳过。"""
    from app import oplog

    class _Resp:
        encoding = None

        def __init__(self, payload):
            self._p = payload

        def json(self):
            return self._p

    payload = {"ip": "8.8.8.8", "pro": "上海市", "city": "上海市",
               "region": "长宁区", "addr": "上海市长宁区 电信", "err": ""}
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["ip"])
        if params["ip"] == "9.9.9.9":
            raise RuntimeError("offline")
        return _Resp(payload)

    monkeypatch.setattr(oplog.requests, "get", fake_get)
    rows = [{"ip": "8.8.8.8"}, {"ip": "9.9.9.9"}, {"ip": "192.168.1.1"}]
    oplog.enrich_regions(rows)
    assert rows[0]["region"] == "上海市 · 电信"
    assert rows[1]["region"] == ""            # 网络异常静默跳过
    assert rows[2]["region"] == "内网/本机"
    # 成功结果已写缓存：第二次查询不再触网
    calls.clear()
    rows2 = [{"ip": "8.8.8.8"}]
    oplog.enrich_regions(rows2)
    assert rows2[0]["region"] == "上海市 · 电信" and not calls


def test_sector_strength(client):
    """板块强度接口：未登录 401；登录后返回 rows 及 summary。"""
    assert client.get("/api/quote/sector-strength").status_code == 401
    ha = login(client, "admin", "admin123")
    r = client.get("/api/quote/sector-strength", headers=ha)
    assert r.status_code == 200
    d = r.json()
    assert "summary" in d
    assert "rows" in d
    assert isinstance(d["rows"], list)


# ===== 登录失败不锁定账号或 IP =====
def test_login_failures_do_not_lock_out(client):
    h = {"X-Forwarded-For": "198.51.100.9"}
    for _ in range(12):
        r = client.post("/api/auth/login", headers=h,
                        json={"username": "admin", "password": "x"})
        assert r.status_code == 401
    # 连续输错后，同一账号和 IP 使用正确密码仍能立即登录。
    r = client.post("/api/auth/login", headers=h,
                    json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    r = client.post("/api/auth/login", headers=h,
                    json={"username": "other", "password": "x"})
    assert r.status_code == 401
    # 不同 IP 的正常用户也可登录。
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

    # 新增扩展筛选测试:板块(主板/创业板)、股价范围、ST过滤、动态服务端排序
    # 1. 板块过滤: "主板" 包含沪主板 + 深主板 (4只)
    d_mb = client.get("/api/quote/history?date=2026-09-10&market=主板", headers=h).json()
    assert d_mb["total"] == 4
    assert all(x["market"] in ("沪主板", "深主板") for x in d_mb["rows"])
    # 创业板 (1只)
    d_cyb = client.get("/api/quote/history?date=2026-09-10&market=创业板", headers=h).json()
    assert d_cyb["total"] == 1 and d_cyb["rows"][0]["f12"] == "300001"

    # 2. 股价范围过滤: 8.0 ~ 15.0 元 (只有 600001 价格 10.0)
    d_px = client.get("/api/quote/history?date=2026-09-10&pmin=8&pmax=15", headers=h).json()
    assert d_px["total"] == 1 and d_px["rows"][0]["f12"] == "600001"

    # 3. 剔除 ST
    d_nost = client.get("/api/quote/history?date=2026-09-10&no_st=true", headers=h).json()
    assert not any("ST" in x["f14"] for x in d_nost["rows"])

    # 4. 服务端按价格排序 (降序 & 升序, NULLS LAST)
    d_sort_px_desc = client.get("/api/quote/history?date=2026-09-10&sort_by=f2&order=desc", headers=h).json()
    pxs = [x["f2"] for x in d_sort_px_desc["rows"] if x["f2"] is not None]
    assert pxs == [20.0, 10.0, 5.0, 4.4]

    d_sort_px_asc = client.get("/api/quote/history?date=2026-09-10&sort_by=f2&order=asc", headers=h).json()
    pxs_asc = [x["f2"] for x in d_sort_px_asc["rows"] if x["f2"] is not None]
    assert pxs_asc == [4.4, 5.0, 10.0, 20.0]

    # 5. 服务端按涨幅排序 (降序)
    d_sort_chg = client.get("/api/quote/history?date=2026-09-10&sort_by=f3&order=desc", headers=h).json()
    chgs = [x["f3"] for x in d_sort_chg["rows"] if x["f3"] is not None]
    assert chgs == [19.98, 10.01, -4.94, -10.02]


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


def test_radar_1to2(client, monkeypatch):
    h = login(client, "admin", "admin123")
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
    # f18(昨收) == t0 收盘 ⇒ 快照已推进到次日,实盘口径;
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
    assert d["review"] is False                        # 快照 f18 == t0 收盘 → 实盘口径


def test_radar_review_mode(client, monkeypatch):
    """复盘视角(快照仍是首板日数据:收盘后/周末/节假日/盘前):
    竞价/额比降级为待确认,不参与否决。"""
    h = login(client, "admin", "admin123")
    monkeypatch.setattr(kline, "get_bars", lambda code, days=250: [])
    # 600006:09-11 未涨停、09-12 首板;快照 f18=9.2(t1 收盘)≠ t0 收盘
    # ⇒ 快照未推进到次日 → 复盘口径,竞价/额比降级 warn
    _hist("2026-09-11", "600006", "复盘股", 9.2, 0, f6=4e8)
    _hist("2026-09-12", "600006", "复盘股", 10.12, 1, f6=5e8)
    db.replace_latest([
        _row("600006", "复盘股", "钢铁", "沪主板", 11.0, 8.7,
             f350=11.11, f351=9.1, f6=6e8, f8=15.0, f17=10.3, f18=9.2,
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
    boards = [r["board"] > 1 for r in d["rows"]]
    assert boards == sorted(boards)
    assert d["stat"]["候选"] == sum(
        1 for r in d["rows"] if r["board"] == 1 and r["verdict"] == "候选")


def test_radar_ladder(client, monkeypatch):
    """连板天梯榜接口：未登录 401，登录后返回今日涨停阶梯与概览。"""
    assert client.get("/api/radar/ladder").status_code == 401
    h = login(client, "admin", "admin123")
    monkeypatch.setattr(kline, "get_bars",
                        lambda code, days=250: [])  # 无日K → 退化 history 口径
    res = client.get("/api/radar/ladder", headers=h)
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "tiers" in data
    assert "tier1" in data["tiers"]
    assert "total_limit_up" in data["summary"]


def test_radar_ladder_streak_with_history_gap(client, monkeypatch):
    """history 断档时,天梯连板数以日K为准,断档两侧的涨停不得拼接:
    600011 断档前 3 个落库日全涨停(旧 history 口径会拼成 4 连板),但日K
    显示昨日未涨停 → 真实首板 streak=1;600012 日K确认前两日连续涨停
    → streak=3。"""
    from datetime import datetime, timedelta
    h = login(client, "admin", "admin123")
    today = datetime.now().date()
    d = lambda n: (today - timedelta(days=n)).isoformat()
    fill = [_bar(d(n), 9.0, 0.5) for n in range(25, 5, -1)]  # 20 根非涨停填充
    bars = {
        # 日K:昨日(及之前)都未涨停 → 今日是首板
        "600011": fill + [_bar(d(5), 9.5, 1.0), _bar(d(4), 9.6, 1.0),
                          _bar(d(3), 9.7, 1.0), _bar(d(2), 9.8, 1.0),
                          _bar(d(1), 9.9, 1.0)],
        # 日K:昨日/前日连续涨停 → 今日 3 连板
        "600012": fill + [_bar(d(5), 9.5, 1.0), _bar(d(4), 9.6, 1.0),
                          _bar(d(3), 9.7, 1.0), _bar(d(2), 10.67, 10.0),
                          _bar(d(1), 11.74, 10.0)],
    }
    # 模块级共享库:其它用例的票也可能在历史里,日K只覆盖本例两只
    monkeypatch.setattr(kline, "get_bars",
                        lambda code, days=250: bars.get(code, []))
    # history 断档(中间有未落库日):600011 断档前 3 个落库日全涨停
    for n in (5, 4, 3):
        _hist(d(n), "600011", "断档假连板", 9.0, 1, f6=3e8)
    db.replace_latest([
        _row("600011", "断档假连板", "钢铁", "沪主板", 10.67, 10.0,
             f350=10.67, f351=8.73, f6=5e8, f62=2e8, f21=50e8),
        _row("600012", "真三连板", "钢铁", "沪主板", 12.91, 10.0,
             f350=12.91, f351=10.56, f6=6e8, f62=3e8, f21=60e8),
    ], "实时行情")
    data = client.get("/api/radar/ladder", headers=h).json()
    items = {s["code"]: s for t in data["tiers"].values() for s in t}
    assert items["600011"]["streak"] == 1   # 日K口径:昨日未涨停,断档不拼接
    assert items["600012"]["streak"] == 3
    assert data["summary"]["max_streak"] == 3


def test_radar_ladder_long_holiday_gap(client, monkeypatch):
    """长假休市（如国庆 8 天、春节 10 天）：日K末根离今日超过 7 天，
    只要是上一交易日或在长假容差期内，连板数应正常承接而非退化。"""
    from datetime import datetime, timedelta
    h = login(client, "admin", "admin123")
    today = datetime.now().date()
    # 模拟节前最后交易日为 8 天前（国庆节后首日）
    pre_holiday = (today - timedelta(days=8)).isoformat()
    d_pre1 = (today - timedelta(days=9)).isoformat()
    d_pre2 = (today - timedelta(days=10)).isoformat()
    fill = [_bar((today - timedelta(days=n)).isoformat(), 9.0, 0.5) for n in range(35, 11, -1)]
    bars = {
        # 节前 3 连板
        "600825": fill + [_bar(d_pre2, 8.0, 10.0), _bar(d_pre1, 8.8, 10.0), _bar(pre_holiday, 9.68, 10.0)],
    }
    monkeypatch.setattr(kline, "get_bars", lambda code, days=250: bars.get(code, []))
    # 节前落库
    _hist(pre_holiday, "600825", "长假连板龙头", 9.68, 1, f6=3e8)
    # 今日快照（第 4 板）
    db.replace_latest([
        _row("600825", "长假连板龙头", "出版", "沪主板", 10.65, 10.0,
             f350=10.65, f351=8.71, f6=5e8, f62=2e8, f21=50e8),
    ], "实时行情")
    data = client.get("/api/radar/ladder", headers=h).json()
    items = {s["code"]: s for t in data["tiers"].values() for s in t}
    # 节前 3 连板 + 今日 1 板 = 4 连板，绝不能因超过 7 天误判
    assert items["600825"]["streak"] == 4
    assert data["summary"]["max_streak"] == 4



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


# ===== 工作台 =====
def test_desk_op_logs(client):
    """工作台各写操作都要留审计日志(09-12 新增的模块曾整体漏埋点)。"""
    db.replace_latest(SAMPLE, "实时行情")   # 前面 radar 用例换过快照,重置回样本
    hr = login(client, config.ROOT_USERNAME, config.ROOT_PASSWORD)
    ha = login(client, "admin", "admin123")
    # 加股票 / 星标 / 分组 / 组成员 / 删股票
    assert client.post("/api/desk/stocks", headers=ha,
                       json={"code": "600001"}).status_code == 200
    assert client.post("/api/desk/star", headers=ha,
                       json={"code": "600001"}).status_code == 200
    gid = client.post("/api/desk/groups", headers=ha,
                      json={"name": "测试组"}).json()["id"]
    assert client.post("/api/desk/groups/%d/items" % gid, headers=ha,
                       json={"code": "600001"}).status_code == 200
    assert client.delete("/api/desk/stocks/600001", headers=ha).status_code == 200
    for act in ("desk_stock_add", "desk_star_add", "desk_group_add",
                "desk_gitem_add", "desk_stock_del"):
        r = client.get("/api/logs", headers=hr, params={"action": act}).json()
        assert any(x["username"] == "admin" for x in r["rows"]), act
    # 删股票详情带名称(与自选删除同口径)
    r = client.get("/api/logs", headers=hr,
                   params={"action": "desk_stock_del", "kw": "600001"}).json()
    assert any("测试钢铁" in x["detail"] for x in r["rows"])
    # 改密属安全敏感操作,也要留痕(改完立刻改回,不影响其它用例)
    client.post("/api/auth/change-password", headers=ha,
                json={"old_password": "admin123", "new_password": "admin456"})
    client.post("/api/auth/change-password", headers=ha,
                json={"old_password": "admin456", "new_password": "admin123"})
    r = client.get("/api/logs", headers=hr,
                   params={"action": "change_password"}).json()
    assert any(x["username"] == "admin" for x in r["rows"])
    # 工作台与雷达天梯、偏好设置新埋点动作已在白名单内
    assert client.post("/api/track", headers=ha,
                       json={"action": "desk_view", "detail": "3 只"}
                       ).status_code == 200
    assert client.post("/api/track", headers=ha,
                       json={"action": "f10_view", "detail": "600001 测试钢铁"}
                       ).status_code == 200
    assert client.post("/api/track", headers=ha,
                       json={"action": "ladder_view", "detail": "2026-09-25 涨停:25 最高:4板"}
                       ).status_code == 200
    assert client.post("/api/track", headers=ha,
                       json={"action": "setting_change", "detail": "副图指标: MACD"}
                       ).status_code == 200
    assert client.post("/api/track", headers=ha,
                       json={"action": "setting_modal_open", "detail": "qsource"}
                       ).status_code == 200


# ===== 行情源设置 + 首页实时行情（第三方请求全部 mock，不触网） =====
def _mr_ok(codes):
    """麦蕊 ssjy_more 批量返回体：dm/p/pc/hs(或 tr)/cje/t。"""
    return [{"dm": c, "p": 10.0, "pc": 1.23, "hs": 2.5, "cje": 1e8,
             "t": "2026-09-14 15:00:00"} for c in codes]


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def test_quotesource_lifecycle(client, monkeypatch):
    """配置 CRUD：首个自动启用、单启用互斥、按用户隔离、证书只回本人。"""
    h = login(client, "admin", "admin123")
    assert client.get("/api/quotesettings").status_code == 401
    assert client.get("/api/quotesettings", headers=h).json()["rows"] == []
    # 非法服务商 / 证书格式不对 / 同名冲突
    assert client.post("/api/quotesettings", headers=h, json={
        "name": "x", "provider": "others", "licence": "LIC-AAAA-1234"}).status_code == 400
    assert client.post("/api/quotesettings", headers=h, json={
        "name": "x", "provider": "mairui", "licence": "短证号"}).status_code in (400, 422)
    # 首个配置自动启用
    assert client.post("/api/quotesettings", headers=h, json={
        "name": "我的麦蕊", "provider": "mairui",
        "licence": "LIC-AAAA-1234"}).status_code == 201
    rows = client.get("/api/quotesettings", headers=h).json()["rows"]
    assert len(rows) == 1 and rows[0]["enabled"] == 1
    assert rows[0]["licence"] == "LIC-AAAA-1234"     # 证书只回给本人
    sid1 = rows[0]["id"]
    # 第二个不自动启用；启用它则第一个自动停用（同时只启用一个）
    assert client.post("/api/quotesettings", headers=h, json={
        "name": "备用", "provider": "mairui",
        "licence": "LIC-BBBB-5678"}).status_code == 201
    sid2 = [r for r in client.get("/api/quotesettings",
                                  headers=h).json()["rows"] if r["name"] == "备用"][0]["id"]
    assert client.patch(f"/api/quotesettings/{sid2}", headers=h,
                        json={"enabled": True}).status_code == 200
    rows = client.get("/api/quotesettings", headers=h).json()["rows"]
    assert {r["name"]: r["enabled"] for r in rows} == {"我的麦蕊": 0, "备用": 1}
    # 同名冲突 / 改证书
    assert client.post("/api/quotesettings", headers=h, json={
        "name": "备用", "provider": "mairui",
        "licence": "LIC-CCCC-9012"}).status_code == 409
    client.patch(f"/api/quotesettings/{sid1}", headers=h,
                 json={"licence": "LIC-CCDD-3456"})
    rows = {r["id"]: r for r in client.get("/api/quotesettings", headers=h).json()["rows"]}
    assert rows[sid1]["licence"] == "LIC-CCDD-3456"
    # 按用户隔离：bob 看不到 admin 的配置，也不能改动
    hs = login(client, "admin", "admin123")
    _mkuser(client, hs, "src_user", "user123")
    hb = login(client, "src_user", "user123")
    assert client.get("/api/quotesettings", headers=hb).json()["rows"] == []
    assert client.patch(f"/api/quotesettings/{sid2}", headers=hb,
                        json={"enabled": True}).status_code == 404
    assert client.delete(f"/api/quotesettings/{sid2}", headers=hb).status_code == 200  # 幂等
    rows = {r["id"]: r for r in client.get("/api/quotesettings", headers=h).json()["rows"]}
    assert rows[sid2]["enabled"] == 1                 # bob 的删除动不到 admin 的配置
    # 清理 bob
    uid = [u["id"] for u in client.get("/api/admin/users",
                                       headers=hs).json()["users"]
           if u["username"] == "src_user"][0]
    client.delete(f"/api/admin/users/{uid}", headers=hs)
    # 收尾停用，让 realtime 用例从"无启用源"状态开始
    client.patch(f"/api/quotesettings/{sid2}", headers=h, json={"enabled": False})


def test_quote_realtime_fallback_and_live(client, monkeypatch):
    """/api/quote/realtime：启用源走实时(归一化东财字段)，失败/无源回落快照。"""
    h = login(client, "admin", "admin123")
    client.post("/api/watchlist", headers=h, json={"code": "600001"})

    def fake_get(url, params=None, timeout=None):
        return _Resp(_mr_ok(params["stock_codes"].split(",")))

    monkeypatch.setattr(sr._mr, "get", fake_get)
    # 无启用源 → 快照兜底（600001 在 SAMPLE 里 f2=10.0）
    d = client.get("/api/quote/realtime", headers=h).json()
    assert d["live"] is False and d["source"] == "东方财富快照"
    assert d["rows"][0]["f12"] == "600001" and d["rows"][0]["f14"] == "测试钢铁"
    assert d["rows"][0]["f2"] == 10.0

    # 启用源 → 实时，字段归一化 + 名称从快照补齐
    sid = client.get("/api/quotesettings", headers=h).json()["rows"][0]["id"]
    client.patch(f"/api/quotesettings/{sid}", headers=h, json={"enabled": True})
    d = client.get("/api/quote/realtime", headers=h).json()
    assert d["live"] is True and "麦蕊智数" in d["source"]
    row = d["rows"][0]
    assert (row["f12"], row["f2"], row["f3"], row["f8"]) == ("600001", 10.0, 1.23, 2.5)
    assert row["f14"] == "测试钢铁" and row["f6"] == 1e8

    # 批量接口换手字段是 tr 的老接口形态：hs 缺失时 tr 兜底
    def fake_tr(url, params=None, timeout=None):
        items = _mr_ok(params["stock_codes"].split(","))
        for it in items:
            it.pop("hs")
            it["tr"] = 3.7
        return _Resp(items)

    monkeypatch.setattr(sr._mr, "get", fake_tr)
    d = client.get("/api/quote/realtime?codes=600001,300001", headers=h).json()
    assert [r["f8"] for r in d["rows"]] == [3.7, 3.7]

    # 源调用失败 → 报错信息透出，行情回落快照，页面不空窗
    def boom(*a, **k):
        raise ConnectionError("mairui down")
    monkeypatch.setattr(sr._mr, "get", boom)
    d = client.get("/api/quote/realtime", headers=h).json()
    assert d["live"] is False and d["error"] and "mairui down" not in d["error"]
    assert d["rows"][0]["f2"] == 10.0

    # 配额用尽等业务错误（返回非列表体）同样回落
    def quota(url, params=None, timeout=None):
        return _Resp({"msg": "101"})

    monkeypatch.setattr(sr._mr, "get", quota)
    d = client.get("/api/quote/realtime", headers=h).json()
    assert d["live"] is False and d["error"] and d["rows"][0]["f3"] == 10.01

    # 参数校验 + 测试端点（恢复可用 mock 后再测）
    assert client.get("/api/quote/realtime?codes=abc", headers=h).status_code == 400
    assert client.get("/api/quote/realtime").status_code == 401
    monkeypatch.setattr(sr._mr, "get", fake_get)
    d = client.post(f"/api/quotesettings/{sid}/test", headers=h).json()
    assert d["ok"] is True and d["sample"]["p"] == 10.0

    # 清理：删除源与自选，不影响其它用例
    client.delete(f"/api/quotesettings/{sid}", headers=h)
    client.delete("/api/watchlist/600001", headers=h)
    assert client.get("/api/quote/realtime", headers=h).json()["rows"] == []


def test_public_quotesource_sharing(client, monkeypatch):
    """公开源：全站可用但他人只见名称；仅属主可改公开性；停用即全网停。"""
    def fake_get(url, params=None, timeout=None):
        return _Resp(_mr_ok(params["stock_codes"].split(",")))

    monkeypatch.setattr(sr._mr, "get", fake_get)
    hs = login(client, "admin", "admin123")
    assert client.post("/api/quotesettings", headers=hs, json={
        "name": "公共源", "provider": "mairui",
        "licence": "LIC-SHARE-9999"}).status_code == 201
    sid = [r for r in client.get("/api/quotesettings",
                                 headers=hs).json()["rows"]
           if r["name"] == "公共源"][0]["id"]
    client.patch(f"/api/quotesettings/{sid}", headers=hs,
                 json={"enabled": True, "is_public": True})
    row = [r for r in client.get("/api/quotesettings",
                                 headers=hs).json()["rows"] if r["id"] == sid][0]
    assert row["enabled"] == 1 and row["is_public"] == 1
    assert row["licence"] == "LIC-SHARE-9999"        # 证书只回属主

    # 其他用户：自己的列表为空；public 只给名称，整个响应不含证书
    _mkuser(client, hs, "pub_user", "user123")
    hu = login(client, "pub_user", "user123")
    d = client.get("/api/quotesettings", headers=hu).json()
    assert d["rows"] == [] and d["public"] == ["公共源"]
    assert "LIC-" not in client.get("/api/quotesettings", headers=hu).text

    # 未启用自己的源 → 实时行情自动走公共源
    client.post("/api/watchlist", headers=hu, json={"code": "600001"})
    d = client.get("/api/quote/realtime", headers=hu).json()
    assert d["live"] is True and "公共源" in d["source"] and "公共" in d["source"]

    # 属主隔离：他人改不了 admin 的公开性/启停（404）
    assert client.patch(f"/api/quotesettings/{sid}", headers=hu,
                        json={"is_public": False}).status_code == 404
    assert client.patch(f"/api/quotesettings/{sid}", headers=hu,
                        json={"enabled": False}).status_code == 404

    # 属主停用 → 公共源全网不可用（列表消失，行情回落快照）
    client.patch(f"/api/quotesettings/{sid}", headers=hs, json={"enabled": False})
    assert client.get("/api/quotesettings", headers=hu).json()["public"] == []
    d = client.get("/api/quote/realtime", headers=hu).json()
    assert d["live"] is False and d["source"] == "东方财富快照"

    # 恢复启用后取消公开 → 同样回落
    client.patch(f"/api/quotesettings/{sid}", headers=hs,
                 json={"enabled": True, "is_public": False})
    d = client.get("/api/quote/realtime", headers=hu).json()
    assert d["live"] is False and d["source"] == "东方财富快照"

    # 公开/取消公开动作有审计日志
    hr = login(client, config.ROOT_USERNAME, config.ROOT_PASSWORD)
    r = client.get("/api/logs", headers=hr, params={"action": "qsource_share"}).json()
    assert any("公共源" in x["detail"] for x in r["rows"])

    # 清理：删源删自选
    client.delete(f"/api/quotesettings/{sid}", headers=hs)
    client.delete("/api/watchlist/600001", headers=hu)


def test_quote_intraday(client, monkeypatch):
    """分时线：无启用源 400；启用源走 history 按日分组取最新交易日；失败 502；公共源可用。"""
    h = login(client, "admin", "admin123")

    def fake_hist(url, params=None, timeout=None):
        assert "/hsstock/history/600001.SH/5/n/" in url and params["lt"] == 96
        bars = [{"t": t, "o": 10.0, "h": 10.2, "l": 9.9, "c": 10.1,
                 "v": 1000, "a": 1e6, "pc": 9.8, "sf": 0}
                for t in ["2026-09-11 14:55:00", "2026-09-11 15:00:00",
                          "2026-09-14 09:35:00", "2026-09-14 09:40:00",
                          "2026-09-14 09:45:00"]]
        return _Resp(bars)

    # 无启用源（自己的/公共的都没有）→ 400，前端据此置灰分时页签
    assert client.get("/api/quote/intraday/600001", headers=h).status_code == 400
    # 代码格式校验
    assert client.get("/api/quote/intraday/abc", headers=h).status_code == 400

    # 启用自己的源 → history 接口，跨日返回按日期分组只留最新交易日（09-14）
    sid = [x for x in client.get("/api/quotesettings", headers=h).json()["rows"]
           if x["name"] == "备用"][0]["id"]
    client.patch(f"/api/quotesettings/{sid}", headers=h, json={"enabled": True})
    monkeypatch.setattr(sr._mr, "get", fake_hist)
    r = client.get("/api/quote/intraday/600001", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["period"] == "5m" and d["date"] == "2026-09-14"
    assert len(d["points"]) == 3 and d["points"][0]["t"] == "09:35"
    assert d["points"][0]["c"] == 10.1 and d["prev_close"] == 9.8
    assert "麦蕊智数" in d["source"] and "公共" not in d["source"]

    # 源调用失败 → 502
    def boom(*a, **k):
        raise ConnectionError("mairui down")
    monkeypatch.setattr(sr._mr, "get", boom)
    assert client.get("/api/quote/intraday/600001", headers=h).status_code == 502

    # 公共源：其他用户未启用自己的源 → 走公共源，来源标注带（公共）
    _mkuser(client, h, "min_user", "user123")
    hm = login(client, "min_user", "user123")
    client.patch(f"/api/quotesettings/{sid}", headers=h, json={"is_public": True})
    monkeypatch.setattr(sr._mr, "get", fake_hist)
    d = client.get("/api/quote/intraday/600001", headers=hm).json()
    assert "公共" in d["source"]

    # 清理：删源删临时用户，不影响其它用例
    client.delete(f"/api/quotesettings/{sid}", headers=h)
    uid = [u["id"] for u in client.get("/api/admin/users",
                                       headers=h).json()["users"]
           if u["username"] == "min_user"][0]
    client.delete(f"/api/admin/users/{uid}", headers=h)


# ===== 黑名单 =====
def test_blacklist_requires_auth(client):
    assert client.get("/api/blacklist").status_code == 401
    assert client.post("/api/blacklist", json={"code": "600001"}).status_code == 401


def test_blacklist_lifecycle_and_quote_exclusion(client):
    h = login(client, "admin", "admin123")
    assert client.get("/api/blacklist", headers=h).json()["rows"] == []
    # 加入(快照中存在的代码),重复加入幂等
    r = client.post("/api/blacklist", headers=h, json={"code": "600001"})
    assert r.status_code == 200 and r.json()["name"] == "测试钢铁"
    assert client.post("/api/blacklist", headers=h,
                       json={"code": "600001"}).status_code == 200
    # 非法代码 / 快照中不存在
    assert client.post("/api/blacklist", headers=h,
                       json={"code": "123"}).status_code == 422
    assert client.post("/api/blacklist", headers=h,
                       json={"code": "999999"}).status_code == 404
    rows = client.get("/api/blacklist", headers=h).json()["rows"]
    assert [r["code"] for r in rows] == ["600001"]
    # 筛选结果服务端剔除:600001 不再出现且不计入 total(no_st=false 时原本 4 只)
    r = client.get("/api/quote/list?no_st=false", headers=h).json()
    assert r["total"] == 3
    assert all(x["f12"] != "600001" for x in r["rows"])
    # 移出后恢复
    assert client.delete("/api/blacklist/600001", headers=h).status_code == 200
    assert client.delete("/api/blacklist/600001", headers=h).status_code == 200  # 幂等
    r = client.get("/api/quote/list?no_st=false", headers=h).json()
    assert r["total"] == 4


# ===== 工作台个股笔记 =====
def test_desk_note(client):
    assert client.get("/api/desk/note/600001").status_code == 401
    assert client.put("/api/desk/note/600001", json={"content": "abc"}).status_code == 401

    h1 = login(client, "admin", "admin123")
    # 初始为空
    r = client.get("/api/desk/note/600001", headers=h1)
    assert r.status_code == 200
    assert r.json()["content"] == ""

    # 保存笔记
    r = client.put("/api/desk/note/600001", headers=h1, json={"content": "突破回踩介入，目标前高"})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 查回笔记
    r = client.get("/api/desk/note/600001", headers=h1)
    assert r.status_code == 200
    assert r.json()["content"] == "突破回踩介入，目标前高"
    assert "updated_at" in r.json()

    # 用户隔离：另一用户读取该股笔记为空
    _mkuser(client, h1, "note_user", "pass123")
    h2 = login(client, "note_user", "pass123")
    r2 = client.get("/api/desk/note/600001", headers=h2)
    assert r2.status_code == 200
    assert r2.json()["content"] == ""

    # 清理测试用户
    uid = [u["id"] for u in client.get("/api/admin/users", headers=h1).json()["users"]
           if u["username"] == "note_user"][0]
    client.delete(f"/api/admin/users/{uid}", headers=h1)


# ===== 神经网络实验室 =====
def test_neural_predict_unauthorized(client):
    r = client.post("/api/neural/predict", json={})
    assert r.status_code == 401


def test_neural_predict_success(client):
    db.replace_latest(SAMPLE, "实时行情")
    h = login(client, "admin", "admin123")
    payload = {
        "data_source": "latest",
        "exclude_st": True,
        "exclude_suspended": True,
        "min_turnover": 1.0,
        "max_turnover": 80.0,
        "min_amount_yi": 0.1,
        "weight_turnover": 70.0,
        "weight_capital": 80.0,
        "weight_volume_ratio": 50.0,
        "weight_momentum": 60.0,
        "activation": "gelu",
        "temperature": 0.8,
        "stagflation_penalty": True,
        "top_k": 10
    }
    r = client.post("/api/neural/predict", headers=h, json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "telemetry" in data
    assert len(data["telemetry"]) == 5
    assert "network_topology" in data
    assert "results" in data
    assert isinstance(data["results"], list)
    if len(data["results"]) > 0:
        top = data["results"][0]
        assert "confidence" in top
        assert "grade" in top
        assert "attribution" in top
        assert "summary" in top["attribution"]


def test_neural_dates_and_backtest(client):
    h = login(client, "admin", "admin123")
    # 自给自足：把当前样本快照落一份到历史基准日，不依赖其它用例的执行顺序
    db.replace_latest(SAMPLE, "实时行情")
    n = db.save_history("2026-09-18")
    assert n == len(SAMPLE)
    r = client.get("/api/neural/dates", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "latest" in d
    assert "history_dates" in d
    assert any(x["date"] == "2026-09-18" for x in d["history_dates"])

    payload = {
        "base_date": "2026-09-18",
        "top_k": 5
    }
    r2 = client.post("/api/neural/backtest", headers=h, json=payload)
    assert r2.status_code == 200
    d2 = r2.json()
    assert "win_rate" in d2
    assert "avg_return" in d2
    assert "benchmark_return" in d2
    assert "alpha" in d2
    assert "results" in d2


def test_neural_optimize(client):
    """回测寻优：历史截面不足时报 400；样本充足时返回最优权重与指标，且可缓存。"""
    h = login(client, "admin", "admin123")
    db.replace_latest(SAMPLE, "实时行情")
    # 测试库历史样本只有 5 行（< 30 只门槛）→ 明确拒绝
    db.save_history("2026-09-17")
    r = client.post("/api/neural/optimize", headers=h, json={"samples": 20})
    assert r.status_code == 400

    # 造两个充足的历史截面（同一天复制样本并扰动代码，凑够 >=30 只）
    conn = db.get_conn()
    for dt in ("2026-09-18", "2026-09-19"):
        for i in range(8):
            for j, s in enumerate(SAMPLE):
                if s["f2"] is None:
                    continue
                conn.execute(
                    "INSERT OR REPLACE INTO history"
                    " (trade_date, code, name, industry, market, f2, f3, f6, f7, f8,"
                    "  f10, f17, f18, f21, f24, f62, limit_up)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (dt, f"60{i}{j}04", f"寻优{i}{j}", s["industry"], s["market"],
                     s["f2"] * (1 + i * 0.01), s["f3"], s["f6"], s["f7"], s["f8"],
                     s["f10"], s["f2"], s["f2"], s["f21"], s["f24"],
                     (s["f6"] or 0) * 0.05, 0))
        conn.commit()
    r = client.post("/api/neural/optimize", headers=h,
                    json={"samples": 40, "top_k": 10, "force": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["samples_evaluated"] >= 40
    assert "weights" in d["best"] and "win_rate" in d["best"]
    assert len(d["leaderboard"]) >= 1
    assert d["cached"] is False
    # 相同条件再次调用 → 命中缓存
    r2 = client.post("/api/neural/optimize", headers=h,
                     json={"samples": 40, "top_k": 10})
    assert r2.status_code == 200 and r2.json()["cached"] is True




# ===== 龙虎榜 =====
from app import lhb  # noqa: E402

_LHB_ITEMS = [
    {"SECURITY_CODE": "600111", "SECURITY_NAME_ABBR": "测试稀土",
     "TRADE_DATE": "2026-09-28 00:00:00", "EXPLAIN": "日涨幅偏离值达7%",
     "CLOSE_PRICE": 30.0, "CHANGE_RATE": 10.0, "BILLBOARD_NET_AMT": 2e8,
     "BILLBOARD_BUY_AMT": 3e8, "BILLBOARD_SELL_AMT": 1e8,
     "ACCUM_AMOUNT": 8e8, "TURNOVERRATE": 12.5},
    # 同股同日第二原因(多条上榜)
    {"SECURITY_CODE": "600111", "SECURITY_NAME_ABBR": "测试稀土",
     "TRADE_DATE": "2026-09-28 00:00:00", "EXPLAIN": "连续三日涨幅偏离值达20%",
     "CLOSE_PRICE": 30.0, "CHANGE_RATE": 10.0, "BILLBOARD_NET_AMT": 1.5e8,
     "BILLBOARD_BUY_AMT": 2.5e8, "BILLBOARD_SELL_AMT": 1e8,
     "ACCUM_AMOUNT": 8e8, "TURNOVERRATE": 12.5},
    {"SECURITY_CODE": "000222", "SECURITY_NAME_ABBR": "测试化工",
     "TRADE_DATE": "2026-09-28 00:00:00", "EXPLAIN": "日跌幅偏离值达7%",
     "CLOSE_PRICE": 9.0, "CHANGE_RATE": -9.9, "BILLBOARD_NET_AMT": -5e7,
     "BILLBOARD_BUY_AMT": 2e7, "BILLBOARD_SELL_AMT": 7e7,
     "ACCUM_AMOUNT": 3e8, "TURNOVERRATE": 6.1},
]
_LHB_SEATS = [
    {"SECURITY_CODE": "600111", "SECURITY_NAME_ABBR": "测试稀土",
     "TRADE_DATE": "2026-09-28 00:00:00", "OPERATEDEPT_CODE": "10001",
     "OPERATEDEPT_NAME": "测试证券上海分公司", "EXPLANATION": "日涨幅偏离值达7%",
     "BUY": 1.2e8, "SELL": 1e7, "NET": 1.1e8},
    {"SECURITY_CODE": "600111", "SECURITY_NAME_ABBR": "测试稀土",
     "TRADE_DATE": "2026-09-28 00:00:00", "OPERATEDEPT_CODE": "10002",
     "OPERATEDEPT_NAME": "测试证券北京营业部", "EXPLANATION": "日涨幅偏离值达7%",
     "BUY": 8e7, "SELL": 2e7, "NET": 6e7},
    {"SECURITY_CODE": "000222", "SECURITY_NAME_ABBR": "测试化工",
     "TRADE_DATE": "2026-09-28 00:00:00", "OPERATEDEPT_CODE": "10001",
     "OPERATEDEPT_NAME": "测试证券上海分公司", "EXPLANATION": "日跌幅偏离值达7%",
     "BUY": 3e7, "SELL": 5e7, "NET": -2e7},
]


def _lhb_ingest(conn, date="2026-09-28", monkeypatch=None):
    if monkeypatch:
        monkeypatch.setattr(lhb, "fetch_daily", lambda d: _LHB_ITEMS)
        # 真实 fetch_seats 会给每条加 side;夹具同样补 B/S 两侧
        monkeypatch.setattr(lhb, "fetch_seats",
                            lambda d: [dict(r, side=s) for s in ("B", "S")
                                       for r in _LHB_SEATS])
    return lhb.ingest_date(conn, date)


def test_lhb_requires_auth(client):
    assert client.get("/api/lhb/daily?date=2026-09-28").status_code == 401


def test_lhb_ingest_idempotent_and_daily(client, monkeypatch):
    conn = db.get_conn()
    assert _lhb_ingest(conn, monkeypatch=monkeypatch) == 3
    _lhb_ingest(conn)   # 重复采集幂等(INSERT OR REPLACE)
    n = conn.execute("SELECT COUNT(*) AS c FROM lhb_item"
                     " WHERE trade_date='2026-09-28'").fetchone()["c"]
    assert n == 3   # 同股多原因各算一条,重复采集不翻倍
    nseat = conn.execute("SELECT COUNT(*) AS c FROM lhb_seat"
                         " WHERE trade_date='2026-09-28'").fetchone()["c"]
    assert nseat == 6   # 3 条明细 × 买卖两侧(side 不同,unique 不冲突)

    h = login(client, "admin", "admin123")
    r = client.get("/api/lhb/daily?date=2026-09-28", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 3
    assert abs(d["rows"][0]["net_amt"]) >= abs(d["rows"][1]["net_amt"])   # 按绝对值降序
    assert d["summary"]["buy"] > 0 and d["summary"]["sell"] > 0
    assert "2026-09-28" in client.get("/api/lhb/dates", headers=h).json()["dates"]


def test_lhb_bad_date(client):
    h = login(client, "admin", "admin123")
    assert client.get("/api/lhb/daily?date=20260928", headers=h).status_code == 400


def test_lhb_stock_seats(client):
    h = login(client, "admin", "admin123")
    r = client.get("/api/lhb/stock/600111/seats?date=2026-09-28", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["buy"]) == 2 and d["buy"][0]["dept_name"] == "测试证券上海分公司"
    assert len(d["sell"]) == 2   # 同一批明细在卖榜侧(side='S')
    assert client.get("/api/lhb/stock/60011/seats?date=2026-09-28",
                      headers=h).status_code == 400


def test_lhb_fill_outcomes_and_stats(client, monkeypatch):
    conn = db.get_conn()
    # kline 序列:T 日收 30,T+1 开 31 / 高 33 / 低 29.5 / 收 32 → 胜
    bars = [{"date": "2026-09-25", "open": 27, "high": 28, "low": 26.5,
             "close": 27.5, "vol": 1, "amount": 1, "pct": None},
            {"date": "2026-09-28", "open": 28, "high": 30.2, "low": 27.8,
             "close": 30.0, "vol": 1, "amount": 1, "pct": None},
            {"date": "2026-09-29", "open": 31.0, "high": 33.0, "low": 29.5,
             "close": 32.0, "vol": 1, "amount": 1, "pct": None}]
    monkeypatch.setattr(lhb.kline, "get_bars", lambda code, days=60: bars)
    filled = lhb.fill_outcomes(conn, "2026-09-29")
    assert filled == 6   # 两只股的买卖两侧席位行全部回填(同股同日按 code+date 批量更新)

    row = conn.execute(
        "SELECT * FROM lhb_seat WHERE code='600111' AND side='B'"
        " AND dept_code='10001'").fetchone()
    assert row["t_close"] == 30.0 and row["t1_close"] == 32.0
    assert row["t1_high"] == 33.0

    lhb.recompute_stats(conn)
    h = login(client, "admin", "admin123")
    r = client.get("/api/lhb/seats?min_apps=1", headers=h)
    assert r.status_code == 200, r.text
    stats = {s["dept_name"]: s for s in r.json()["rows"]}
    sh = stats["测试证券上海分公司"]
    assert sh["appearances"] == 4          # 两股 × 买卖两侧(各侧独立计)
    # 全部样本次日收涨(夹具 kline 对两股同一生效):胜率 = 1
    assert sh["win_rate"] == 1.0
    assert abs(sh["avg_open_premium"] - (31 / 30 - 1)) < 1e-6

    r2 = client.get("/api/lhb/seat/测试证券上海分公司", headers=h)
    assert r2.status_code == 200, r2.text
    d = r2.json()
    assert d["stat"]["appearances"] == 4
    assert len(d["recent"]) >= 2
    assert client.get("/api/lhb/seat/不存在席位", headers=h).status_code == 404


def test_lhb_seat_tags(client):
    """席位标签:名称推导(机构/北向/自营) + 网传游资映射(优先)。"""
    conn = db.get_conn()
    famous = lhb.famous_map(conn)
    assert famous == {}
    assert lhb.tag_of("机构专用", famous)["tag"] == "机构"
    assert lhb.tag_of("深股通专用", famous)["tag"] == "北向"
    assert lhb.tag_of("沪股通专用", famous)["tag"] == "北向"
    assert lhb.tag_of("测试证券自营部", famous)["tag"] == "自营"
    assert lhb.tag_of("测试证券上海分公司", famous) is None

    h = login(client, "admin", "admin123")
    dept = "测试证券上海分公司"
    # 维护映射:网传游资,优先级高于名称推导
    r = client.post("/api/lhb/famous", headers=h,
                    json={"dept_name": dept, "alias": "养家测试", "note": "网传"})
    assert r.status_code == 201, r.text
    famous = lhb.famous_map(conn)
    assert lhb.tag_of(dept, famous) == {"tag": "游资", "alias": "养家测试",
                                        "src": "网传"}
    # upsert 覆盖别名
    r = client.post("/api/lhb/famous", headers=h,
                    json={"dept_name": dept, "alias": "养家二号"})
    assert r.status_code == 201
    assert lhb.famous_map(conn)[dept] == "养家二号"
    # 映射透传到各查询接口
    seats = client.get("/api/lhb/stock/600111/seats?date=2026-09-28",
                       headers=h).json()
    assert seats["buy"][0]["seat_tag"]["alias"] == "养家二号"
    assert seats["buy"][1]["seat_tag"] is None
    st = client.get("/api/lhb/seat/" + dept, headers=h).json()
    assert st["stat"]["seat_tag"]["tag"] == "游资"
    lst = client.get("/api/lhb/famous", headers=h).json()["rows"]
    assert any(x["dept_name"] == dept and x["alias"] == "养家二号" for x in lst)

    # 普通用户可读映射但不可写
    _mkuser(client, h, "lhb_viewer", "pw123456", role="user")
    hu = login(client, "lhb_viewer", "pw123456")
    assert client.get("/api/lhb/famous", headers=hu).status_code == 200
    assert client.post("/api/lhb/famous", headers=hu,
                       json={"dept_name": "x证券y营业部", "alias": "z"}
                       ).status_code == 403
    assert client.delete("/api/lhb/famous/" + dept, headers=hu).status_code == 403

    r = client.delete("/api/lhb/famous/" + dept, headers=h)
    assert r.status_code == 200
    assert lhb.famous_map(conn) == {}
    assert client.delete("/api/lhb/famous/" + dept, headers=h).status_code == 404


# ===== 预警中心 =====
from datetime import datetime  # noqa: E402
from app import alerts  # noqa: E402


def _admin_id():
    return db.get_conn().execute(
        "SELECT id FROM users WHERE username='admin'").fetchone()["id"]


def _mk_rule(rule_type, code="600001", threshold=None, cooldown=60, user_id=None):
    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO alert_rule"
            " (user_id, code, name, rule_type, threshold, cooldown_min, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (user_id or _admin_id(), code, "测试钢铁", rule_type, threshold,
             cooldown, datetime.now().isoformat(timespec="seconds")))
    return cur.lastrowid


def test_alerts_eval_window():
    assert alerts._in_eval_window(datetime(2026, 9, 29, 10, 0)) is True    # 周二盘中
    assert alerts._in_eval_window(datetime(2026, 9, 29, 9, 20)) is False   # 竞价前半段不评估
    assert alerts._in_eval_window(datetime(2026, 9, 29, 15, 10)) is False
    assert alerts._in_eval_window(datetime(2026, 9, 27, 10, 0)) is False   # 周日


def test_alert_rule_crud(client):
    h = login(client, "admin", "admin123")
    assert client.get("/api/alerts/rules").status_code == 401
    # 校验:坏代码 / 坏类型 / 缺阈值 / 不存在的股票
    assert client.post("/api/alerts/rules", headers=h,
                       json={"code": "60001", "rule_type": "price_above",
                             "threshold": 9}).status_code == 422
    assert client.post("/api/alerts/rules", headers=h,
                       json={"code": "600001", "rule_type": "magic"}).status_code == 400
    assert client.post("/api/alerts/rules", headers=h,
                       json={"code": "600001",
                             "rule_type": "price_above"}).status_code == 400
    assert client.post("/api/alerts/rules", headers=h,
                       json={"code": "699999", "rule_type": "price_above",
                             "threshold": 9}).status_code == 400
    # 正常创建(limit_up 无需阈值)
    r = client.post("/api/alerts/rules", headers=h,
                    json={"code": "600001", "rule_type": "price_above",
                          "threshold": 9.5})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    rows = client.get("/api/alerts/rules", headers=h).json()["rows"]
    assert any(x["id"] == rid and x["name"] == "测试钢铁" for x in rows)
    # 更新:改阈值/停用
    assert client.patch(f"/api/alerts/rules/{rid}", headers=h,
                        json={"threshold": 9.0, "enabled": False}).status_code == 200
    row = [x for x in client.get("/api/alerts/rules", headers=h).json()["rows"]
           if x["id"] == rid][0]
    assert row["threshold"] == 9.0 and row["enabled"] == 0
    # limit 类规则拒绝阈值更新
    r2 = client.post("/api/alerts/rules", headers=h,
                     json={"code": "600001", "rule_type": "limit_up"})
    assert client.patch(f"/api/alerts/rules/{r2.json()['id']}", headers=h,
                        json={"threshold": 1}).status_code == 400
    # 删除
    assert client.delete(f"/api/alerts/rules/{rid}", headers=h).status_code == 200
    assert not any(x["id"] == rid
                   for x in client.get("/api/alerts/rules", headers=h).json()["rows"])
    assert client.delete(f"/api/alerts/rules/{rid}", headers=h).status_code == 404


def test_alert_rule_cap_and_isolation(client, monkeypatch):
    h = login(client, "admin", "admin123")
    conn = db.get_conn()
    cnt = conn.execute("SELECT COUNT(*) AS c FROM alert_rule WHERE user_id=?",
                       (_admin_id(),)).fetchone()["c"]
    monkeypatch.setattr("app.routes.alerts_routes.MAX_RULES_PER_USER", cnt + 1)
    assert client.post("/api/alerts/rules", headers=h,
                       json={"code": "600001", "rule_type": "pct_above",
                             "threshold": 5}).status_code == 201
    assert client.post("/api/alerts/rules", headers=h,
                       json={"code": "600001", "rule_type": "pct_above",
                             "threshold": 6}).status_code == 400   # 达到上限

    # 跨用户隔离:新用户看不到也动不了 admin 的规则
    r = client.post("/api/admin/users", headers=h,
                    json={"username": "alertu", "password": "pw123456", "role": "user"})
    uid = r.json()["id"]
    hb = login(client, "alertu", "pw123456")
    admin_rule = client.get("/api/alerts/rules", headers=h).json()["rows"][0]
    assert client.get("/api/alerts/rules", headers=hb).json()["rows"] == []
    assert client.delete(f"/api/alerts/rules/{admin_rule['id']}",
                         headers=hb).status_code == 404
    client.delete(f"/api/admin/users/{uid}", headers=h)


def test_alerts_evaluate_and_events(client, monkeypatch):
    monkeypatch.setattr(alerts, "_in_eval_window", lambda n: True)
    now = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    db.replace_latest(SAMPLE, "实时行情")   # 保证快照新鲜且 ok=1
    conn = db.get_conn()
    conn.execute("DELETE FROM alert_event")
    conn.execute("DELETE FROM alert_rule")
    conn.commit()
    alerts._prev_limit.clear()

    rid_price = _mk_rule("price_above", threshold=9.5)   # f2=10.0 命中
    rid_limit = _mk_rule("limit_up")                     # SAMPLE 600001 封板中
    rid_open = _mk_rule("limit_open")                    # 首轮不触发(无封板前态)

    n1 = alerts.evaluate(now=now)
    assert n1 == 2   # price_above + limit_up
    evs = [dict(r) for r in conn.execute(
        "SELECT * FROM alert_event ORDER BY id").fetchall()]
    assert {e["rule_id"] for e in evs} == {rid_price, rid_limit}
    assert "10" in evs[0]["detail"]

    # 第二轮:冷却/每日去重,都不重复触发
    assert alerts.evaluate(now=now) == 0

    # 开板:上一轮 600001 封板状态已记录,解除封板后触发 limit_open
    conn.execute("UPDATE latest SET limit_up = 0, f2 = 9.8 WHERE code = '600001'")
    conn.commit()
    assert alerts.evaluate(now=now) == 1
    ev = conn.execute("SELECT * FROM alert_event WHERE rule_id = ?",
                      (rid_open,)).fetchone()
    assert ev and "涨停打开" in ev["detail"]

    # 陈旧快照不评估
    db.replace_latest([], "", error="blocked")
    assert alerts.evaluate(now=now) == 0
    db.replace_latest(SAMPLE, "实时行情")   # 还原,不影响后续其它测试

    # 事件 API:增量轮询 + 已读 + 归属
    h = login(client, "admin", "admin123")
    d = client.get("/api/alerts/events?since_id=0", headers=h).json()
    assert len(d["events"]) == 3 and d["max_id"] == d["events"][-1]["id"]
    d2 = client.get(f"/api/alerts/events?since_id={d['max_id']}", headers=h).json()
    assert d2["events"] == [] and d2["max_id"] == d["max_id"]
    first_id = d["events"][0]["id"]
    client.post("/api/alerts/events/read", headers=h, json={"ids": [first_id]})
    hist = client.get("/api/alerts/events/history", headers=h).json()
    assert hist["total"] == 3
    assert [r for r in hist["rows"] if r["id"] == first_id][0]["read"] == 1
    client.post("/api/alerts/events/read", headers=h, json={"ids": []})   # 全部已读
    assert all(r["read"] == 1
               for r in client.get("/api/alerts/events/history",
                                   headers=h).json()["rows"])
