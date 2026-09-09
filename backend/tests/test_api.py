"""后端接口测试：独立临时库 + 关闭调度器（不触网）。"""
import os
import tempfile

os.environ["TS_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="ts-test-"), "t.db")
os.environ["TS_ADMIN_PASSWORD"] = "admin123"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, scheduler  # noqa: E402
from app.fetcher import limit_flags  # noqa: E402
from app.main import app  # noqa: E402
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
