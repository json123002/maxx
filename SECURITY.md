# 安全政策（Security Policy）

## 报告安全问题

请勿通过公开 Issue 报告。直接联系维护者（GitHub: [@json123002](https://github.com/json123002)），
说明影响范围与复现步骤，确认后由维护者统一修复与披露。

## 密钥与数据红线

- 任何口令、密钥、SSH 密码**绝不入库**（含注释、测试数据）。部署密码走 `TS_PASSWORD` 环境变量，
  CI/CD 密钥走 GitHub Actions Secrets（如 `DEPLOY_SSH_KEY`）。
- 数据库文件（`*.db`）不提交、不外发——内含用户口令哈希。
- 发现密钥误入库：**先轮换该密钥，再清理 git 历史**，顺序不能反——
  已推送的密钥视为已泄露，只清历史不轮换等于没修。

## 线上访问纪律

- 不 SSH 上服务器手改代码或数据库；一切变更走 PR + CI/CD 部署（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。
- 生产日志含真实 IP 与 UA，禁止截图外发或拷贝到第三方工具。
