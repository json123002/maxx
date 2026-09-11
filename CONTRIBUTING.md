# 协作指南

## 分支与提交

- `main` 受保护：**禁止直推**，所有改动走 PR。
- 功能分支命名：`feature/xxx`、`fix/xxx`。
- 提交信息用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：
  `feat: ...` / `fix: ...` / `perf: ...` / `docs: ...` / `test: ...` / `chore: ...`
- PR 至少 1 人 review、CI 全绿后 squash merge。

## 环境

- 后端：Python 3.11+，`pip install -r backend/requirements.txt`
- 前端：**只用 pnpm**（仓库以 `web/pnpm-lock.yaml` 为准，不要用 npm/yarn 安装）
- 提交前钩子：`pip install pre-commit && pre-commit install`（自动格式化 + 密钥扫描）

## 本地验证（提 PR 前必跑）

```bash
cd backend && python -m pytest tests/ -q
cd web && pnpm test && pnpm build
```

## 安全红线

密钥管理、漏洞报告与线上访问纪律见 [SECURITY.md](SECURITY.md)。

## 数据库变更指南（schema migration）

本项目不使用 Alembic 等迁移框架，而是采用**幂等启动迁移**：服务每次启动时
`db.init_db()` 自动把库结构补齐到代码期望的最新状态。同一份代码既能初始化
全新空库，也能原地升级线上老库——不存在「迁移脚本执行顺序」问题。

### 原则

1. **一切 schema 变更走代码 + PR**，严禁 SSH 到服务器手改数据库。
2. 迁移必须**幂等**：执行任意多次结果一致（先查 `PRAGMA table_info`，缺列才 `ALTER`）。
3. 数据库文件在服务器上、不进 git，部署只传代码——**线上数据不会因部署丢失**。
4. 每天 03:30 自动热备份（`backend/data/backups/`，滚动 14 份），改坏可回滚。

### 加新列（最常见）

在 `backend/app/db.py` 对应的 `_migrate_<table>()` 函数里追加（没有就新建）：

```python
def _migrate_op_logs(conn) -> None:
    """老库补列（示例：新增 level 列；真实函数见 db.py）。"""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(op_logs)")}
    if "level" not in have:        # ← 缺列才补，保证幂等
        conn.execute(
            "ALTER TABLE op_logs ADD COLUMN level TEXT NOT NULL DEFAULT 'info'")
```

并在 `init_db()` 中登记调用。约束（SQLite 限制）：

- 新列**必须带 `DEFAULT`**（ALTER ADD COLUMN 不支持非常量约束）
- 只用 `ADD COLUMN`；**不要 `DROP`、不要改列类型**——废弃的列留着不用即可
  （SQLite 改列需重建表，风险远大于收益）

### 加新表

直接在 `init_db()` 的 `executescript` 里加 `CREATE TABLE IF NOT EXISTS ...` 即可。

### 流程

1. 改 `db.py`（迁移函数 / 建表语句）
2. 在 `backend/tests/test_api.py` 加覆盖新字段的用例——测试库是全新临时库，
   会完整走一遍 `init_db()`，天然验证迁移可用
3. 一个 PR 只包含一个 schema 变更，标题注明（如 `feat: add level column to op_logs`）
4. 合并后由维护者 Deploy（`all`）——服务重启时自动完成迁移，秒级，无需停服

### 数据变更（非 schema）

修改存量数据的逻辑（如清洗旧行）写成一次性函数，同样要求幂等（可重复执行），
并在 PR 描述里明确说明影响范围，由维护者评审后随部署执行。

### 红线

| ❌ 禁止 | ✅ 做法 |
|---|---|
| SSH 上服务器手改库 | 迁移代码 + PR + 部署 |
| `DROP COLUMN` / 改列类型 | 只加不删，废弃列停用 |
| 新列不加 `DEFAULT` | 必须加，否则老库 ALTER 报错 |
| 一个 PR 多个不相关迁移 | 一个迁移一个 PR，便于回滚 |
| 在迁移里做耗时数据清洗 | schema 与数据清洗分开评审 |

## 部署

只有维护者执行部署；部署对应 main 上的提交，不部署未合并的本地改动。

**首选 CI/CD**：GitHub 仓库 → Actions → Deploy → Run workflow（可选 all / frontend-only）。
流程：跑测试 → 构建前端 → 打包上传 → 服务器解包、装依赖、重启服务、健康检查，前端异常自动回滚。
依赖仓库 Secret `DEPLOY_SSH_KEY`（部署专用私钥，公钥在服务器 authorized_keys 里）。

本地脚本（`deploy/deploy.py` / `publish_frontend.py`）保留为应急通道，需 `TS_PASSWORD` 环境变量。
