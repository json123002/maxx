# maxx · Turnover Screener（前后端分离版）

A 股换手率筛选器：FastAPI + SQLite 后端定时抓数，静态前端经 `/api` 查询，带登录与管理员用户管理。

## 结构

```
maxx/
  backend/            FastAPI 后端
    app/
      main.py         入口（路由挂载、建库、调度启动；本地开发顺带托管 frontend/ 构建产物）
      config.py       环境变量配置（TS_DB_PATH / TS_ADMIN_PASSWORD / TS_FETCH_INTERVAL_MIN ...）
      db.py           SQLite（latest 实时快照 / history 收盘落库 / users / sessions）
      security.py     PBKDF2 口令哈希、Bearer 会话（存库可吊销）
      fetcher.py      东方财富全市场快照抓取（分页重试、去重、忽略系统代理）
      scheduler.py    交易时段每 3 分钟抓数 + 每交易日 15:06 落历史
      routes/         auth（登录/改密）· admin（用户管理）· quote（行情查询）
    tests/            pytest（10 个用例，独立临时库，不触网）
  web/                Vue3 前端工程（Vite + vue-router + ant-design-vue）
    src/views/        LoginView(转盘登录) / HomeView(工作台) / ScreenerView(换手率筛选) / AdminView(用户管理)
    src/layout/       MainLayout(左侧菜单+顶栏) / PwdModal(修改密码)
    src/screener/     筛选页组合式函数与组件（FilterPanel / ResultsPanel / metrics）
    src/analysis/     个股分析弹窗（取数三级兜底 + 指标 + 各战法评估，AnalysisModal 组件）
  frontend/           前端构建产物（web/ 执行 npm run build 生成，勿手改；部署上传的就是它）
  deploy/
    nginx.conf        站点配置（/api 反代 127.0.0.1:8000，gzip）
    turnover-api.service  systemd 单元
    deploy.py         一键部署脚本（本机执行，先构建前端再跑）
```

## 本地开发

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -q          # 跑测试
python -m uvicorn app.main:app --reload --port 8000

cd web
npm install                         # 首次
npm run dev                         # 前端热更新(:5173,/api 默认代理到线上 47.94.235.93,数据落服务器库)
npm run dev:local                   # 改为代理本机 :8000 后端(需先按上面启动 uvicorn)
npm run build                       # 构建到 frontend/(uvicorn 直接托管也是它)
```

打开 http://127.0.0.1:8000/ ，首次启动自动建库并创建管理员 **admin / admin123**。

## 部署（服务器 47.94.235.93）

```bash
python deploy/deploy.py
```

首次部署后请立即登录并在右上角「修改密码」改掉默认口令。

## API 一览

| 接口 | 说明 |
|---|---|
| POST /api/auth/login | 登录，返回 Bearer token |
| POST /api/auth/logout · GET /api/auth/me · POST /api/auth/change-password | 会话与改密 |
| GET /api/quote/list | 筛选列表（markets/tmin/tmax/cmin/cmax/industry/kw/no_st/no_suspend/metrics/limit） |
| GET /api/quote/meta | 行业计数 + 情绪统计（按所选市场） |
| GET /api/health | 服务与最近抓取状态（公开） |
| GET/POST/PATCH/DELETE /api/admin/users | 用户管理（仅管理员） |

## 数据说明

- 行情来自东方财富公开接口，服务器交易时段（9:15-11:30 / 13:00-15:05）每 3 分钟抓一次全市场快照。
- `latest` 表供实时查询；`history` 表每交易日收盘落库一份，供后续复盘扩展。
- 抓数失败时保留上一份快照，接口返回 `stale: true`，页面徽标会标注「抓取失败中」。
- 个股分析弹窗的 K 线/资金流仍由浏览器直连东财/腾讯/新浪 JSONP（与本服务无关）。

本项目仅作客观数据筛选，不构成投资建议。
