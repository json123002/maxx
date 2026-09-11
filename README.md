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
                        · watchlist（自选股）· radar（涨停雷达·一进二粗筛）
                        · log（操作日志，仅隐藏 root）
    tests/            pytest（26 个用例，独立临时库，不触网）
  web/                Vue3 前端工程（Vite + vue-router + ant-design-vue，包管理只用 pnpm）
    src/views/        LoginView(转盘登录) / HomeView(工作台) / ScreenerView(换手率筛选)
                        / WatchlistView(自选股) / StockView(个股详情+日K阶段标注)
                        / HistoryView(历史榜单) / RadarView(涨停雷达·一进二)
                        / LogView(操作日志) / AdminView(用户管理)
    src/layout/       MainLayout(左侧菜单+顶栏) / PwdModal(修改密码)
    src/screener/     筛选页组合式函数与组件（FilterPanel / ResultsPanel / metrics）
    src/stock/        K 线图与日K阶段识别（phases.js，含 node --test 回归）
    src/analysis/     个股分析弹窗（取数三级兜底 + 指标 + 各战法评估，AnalysisModal 组件）
  frontend/           前端构建产物（web/ 执行 pnpm build 生成，勿手改；部署上传的就是它）
  deploy/
    nginx.conf        站点配置（/api 反代 127.0.0.1:8000，gzip）
    turnover-api.service  systemd 单元
    deploy.py         一键部署脚本（本机执行，先构建前端再跑）
    publish_frontend.py / verify_frontend.py   仅发布前端 / 只读核对线上前端（应急通道）
    check_server.py   服务器巡检（服务/内存/库行数/日志，需 TS_PASSWORD）
  .github/workflows/  CI：后端 pytest + 前端 pnpm test & build
```

## 本地开发

环境要求：Python 3.11+ · Node.js ≥ 22.13 · pnpm（`npm i -g pnpm`）

```bash
cd backend
pip install -r requirements.txt
python -m pytest tests/ -q          # 跑测试
python -m uvicorn app.main:app --reload --port 8000

cd web
pnpm install                        # 首次(只用 pnpm,勿用 npm/yarn)
pnpm dev                            # 前端热更新(:5173,/api 默认代理本机 :8000)
pnpm dev:remote                     # 改为代理线上 47.94.235.93(数据落服务器库,慎操作)
pnpm test                           # 日K阶段规则回归(node --test)
pnpm build                          # 构建到 frontend/(uvicorn 直接托管也是它)
```

打开 http://127.0.0.1:8000/ ，首次启动自动建库并创建管理员 **admin / admin123**。

## 部署（服务器 47.94.235.93）

首选 CI/CD：仓库 **Actions → Deploy → Run workflow**（可选 `all` 或 `frontend-only`），
自动跑测试、构建、上传、重启服务并健康检查（前端异常自动回滚）。

应急通道（本机执行，需 `TS_PASSWORD` 环境变量）：

```bash
python deploy/deploy.py              # 全量部署（后端 + 前端 + nginx 配置）
python deploy/publish_frontend.py    # 仅发布前端：本地先 pnpm build，脚本备份线上首页、
                                     # 校验资源后原子切换；公网验证失败自动回退
python deploy/verify_frontend.py     # 只读核对线上前端版本及全部资源（回退无法确认时用）
```

首次部署后请立即登录并在右上角「修改密码」改掉默认口令。

## API 一览

| 接口 | 说明 |
|---|---|
| POST /api/auth/login | 登录，返回 Bearer token |
| POST /api/auth/logout · GET /api/auth/me · POST /api/auth/change-password | 会话与改密 |
| GET /api/quote/list | 筛选列表（markets/tmin/tmax/cmin/cmax/industry/kw/no_st/no_suspend/metrics/limit） |
| GET /api/quote/meta | 行业计数 + 情绪统计（按所选市场） |
| GET /api/quote/stock/{code} | 个股详情（名称/行业/最新快照字段） |
| GET /api/quote/history?date= · GET /api/quote/history/dates | 历史榜单回看（收盘落库数据） |
| GET /api/radar/1to2 | 涨停雷达：昨日首板 × 今日竞价/量能/资金/空间六维粗筛 |
| GET /api/health | 服务与最近抓取状态（公开） |
| GET/POST/PATCH/DELETE /api/admin/users | 用户管理（仅管理员） |
| GET/POST /api/watchlist · DELETE /api/watchlist/{code} · GET /api/watchlist/search | 自选股（登录用户） |
| POST /api/track · GET /api/logs | 行为埋点 / 操作日志（后者仅隐藏 root） |

## 数据说明

- 行情来自东方财富公开接口，服务器交易时段（9:15-11:30 / 13:00-15:05）每 3 分钟抓一次全市场快照。
- `latest` 表供实时查询；`history` 表每交易日收盘落库一份，供后续复盘扩展。
- 抓数失败时保留上一份快照，接口返回 `stale: true`，页面徽标会标注「抓取失败中」。
- 个股分析弹窗的 K 线/资金流仍由浏览器直连东财/腾讯/新浪 JSONP（与本服务无关）。

本项目仅作客观数据筛选，不构成投资建议。

## 日K阶段标注

个股详情页的「周期」按钮默认开启，可按横盘整理、横盘后上涨、触底反弹筛选。
框选采用阶段实际高低价；箭头和竖虚线表示确认日。图下可选择历史阶段定位，查看日期、交易日数、收盘区间涨跌、确认日成交量相对前5日均量。

- 平台：8～19日为短平台，20日及以上为中期横盘；整体振幅不超过12%，首尾分组均价偏移不超过4%，净位移与逐日收盘位移总和之比不超过0.55，过滤单边慢涨。
- 突破：结束后10日内收盘越过箱顶加较大者（箱顶1.5%、0.5倍14日平均真实波幅）；再满足收盘突破3%、放量1.5倍、连续两日站稳中的一项。最多跟踪40日，跌回平台标记突破失效；或收盘回撤达到确认日冻结的波动阈值（8%～15%）结束。
- 反弹：创新的20日低点且较前20日最高价回落至少15%；等待至少2日，在低点后20日内收盘反弹8%确认。创新低或较最高收盘回撤8%结束，最长观察至低点后20日。
- 待确认底部可能消失；已确认区间会继续延伸。历史起点不是当时的交易信号；日内未收盘K线和行情复权更新仍可能改变结果。

规则回归测试：`node --test web/src/stock/phases.test.js`。
回归样本包含腾讯前复权海鸥股份日K快照（截至2026-09-11），验证8月13～26日短平台、8月27日突破及逐日确认时间稳定性。面板优先展示当前可见阶段，历史阶段需选择定位；无可见阶段时明确提示。规则属于可解释的启发式识别，未经过收益或胜率校准。

## 协作与安全

- 分支、提交、PR、数据库变更规范见 [CONTRIBUTING.md](CONTRIBUTING.md)
- 漏洞报告与密钥红线见 [SECURITY.md](SECURITY.md)
