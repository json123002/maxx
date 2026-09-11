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

- 任何口令、密钥、SSH 密码**绝不入库**（含注释）。部署密码走 `TS_PASSWORD` 环境变量。
- 数据库文件（`*.db`）不提交、不外发——内含用户口令哈希。
- 发现密钥误入库：先轮换该密钥，再清理历史，顺序不能反。

## 部署

只有维护者执行部署；部署对应 main 上的提交，不部署未合并的本地改动。

**首选 CI/CD**：GitHub 仓库 → Actions → Deploy → Run workflow（可选 all / frontend-only）。
流程：跑测试 → 构建前端 → 打包上传 → 服务器解包、装依赖、重启服务、健康检查，前端异常自动回滚。
依赖仓库 Secret `DEPLOY_SSH_KEY`（部署专用私钥，公钥在服务器 authorized_keys 里）。

本地脚本（`deploy/deploy.py` / `publish_frontend.py`）保留为应急通道，需 `TS_PASSWORD` 环境变量。
