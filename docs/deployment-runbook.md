# 部署与运维手册

## 1. 前置条件

Docker 24+ 与 Compose v2；或 Python 3.12+、Node 22+。同一主机至少 2 CPU、4GB RAM；全文和索引规模扩大时增加磁盘。

## 2. Docker

```bash
cp .env.example .env
# 编辑 CORS、数据源与模型；生产关闭 fixture
docker compose -f infra/docker-compose.yml config
docker compose -f infra/docker-compose.yml up --build -d
docker compose -f infra/docker-compose.yml ps
curl http://127.0.0.1:8000/api/health
```

Web：`http://127.0.0.1:8080`。局域网用主机 IP。数据库映射到仓库 `runtime/`，`docker compose down` 不删除。

## 3. Windows

使用 Docker Desktop + WSL2。允许防火墙 TCP 8080；不要把 runtime 放在 OneDrive 同步目录。PowerShell 用 `Copy-Item .env.example .env`。

## 4. macOS/Linux

确认 8080/8000 未占用。macOS 首次局域网访问允许 Docker/终端接收连接。Linux 使用 `ufw allow from <LAN-CIDR> to any port 8080 proto tcp`，不要对公网开放。

## 5. 原生

见 README。必须设置 `PYTHONPATH=apps/api:.`。API 和 worker 使用同一数据库 URL。

## 6. 初始化

用户可网页注册。演示可运行 `scripts/seed_demo.py`，随后修改默认密码。当前管理员提升需数据库或后续管理命令，不能把固定管理员密码写进仓库。

## 7. 备份

```bash
PYTHONPATH=apps/api:. python scripts/backup.py --runtime runtime
```

每周和升级前备份；把 ZIP 复制到不同物理磁盘。当前 ZIP 未加密，包含用户笔记和 PDF，应按敏感数据管理。

## 8. 恢复

```bash
docker compose -f infra/docker-compose.yml down
PYTHONPATH=apps/api:. python scripts/restore.py <backup.zip> --runtime runtime --force
docker compose -f infra/docker-compose.yml up -d
```

恢复后验证用户登录、项目、收藏、PDF chunk 和 gap 状态。

## 9. 升级

1. 备份；2. 查看 CHANGELOG 和 migration；3. `alembic upgrade head`；4. 构建；5. 后端测试；6. 前端 build；7. cold start；8. smoke；9. 保留回滚 ZIP。

## 10. 排错

- `database is locked`：确认只有一个主机写、runtime 非网络盘、worker 数量有限；
- 搜索无结果：查看 `/sources/status`，确认不是 fixture 关闭且所有真实源禁用；
- 429：降低频率、配置 Key、等待额度；
- PDF 422：检查是否扫描件、MIME、大小、加密；
- MCP 启动失败：安装 `mcp[cli]>=2,<3`，设置 token；
- 前端 401：清除 localStorage 后重新登录；
- worker 重试：查看 job events 和 error；
- CORS：把实际 Web Origin 加入 `RN_ALLOWED_ORIGINS`，不要使用通配符+凭据。

## 11. 公网模式

本包默认不满足公网生产门槛。至少增加 TLS、域名、WAF/速率限制、强密码/重置/2FA、审计告警、备份加密、内容安全策略、依赖扫描和隐私/版权流程。

## 12. Docker 冷启动、重启与持久性验收

正式声称 Docker 持久性通过前，必须对**当前 checkout**执行专用验收，而不能复用历史截图或仅检查 Compose 配置：

```bash
python scripts/verify_docker_persistence.py \
  --runtime-dir codex_audit/runtime/docker-acceptance \
  --output codex_audit/DOCKER_PERSISTENCE_REPORT.json
```

该脚本使用 `infra/docker-compose.acceptance.yml` 和独立项目名 `rn-acceptance`，执行以下门控：

1. `docker compose build --no-cache`；
2. API、Worker、Web 冷启动并等待健康检查；
3. 通过 HTTP 注册用户、创建项目、fixture 检索、收藏、上传授权测试 PDF、生成分析和证据工作流；
4. 等待 Worker 将任务推进到 `succeeded` 或 `partial`，而不是把 `pending` 当作成功；
5. 重启 API/Worker 后核对项目、收藏、PDF、chunks、analysis、job 和事件；
6. `compose down` 后重新 `up` 并再次核对；
7. 通过管理员备份 API 创建备份，制造备份后的写入，再执行 `stage-restore`；
8. 重启 API 应用原子恢复，确认备份后的写入被回滚、原状态和文件哈希仍存在；
9. 停止容器后执行 `PRAGMA integrity_check`、表计数和 runtime SHA256。

验收运行使用单独的 bind-mounted runtime。脚本只会自动清理带有 `.rn-acceptance-runtime` 标记的目录；对于非空、无标记目录会 fail closed，避免误删真实数据。默认端口为 API `18000`、Web `18080`，可用 `--api-port` 与 `--web-port` 修改。

若当前主机没有 Docker，脚本退出码为 `2`，报告状态必须是 `BLOCKED`，不能将 Compose 静态检查或非 Docker 测试写成 `PASS`。实时 OpenAlex、商业授权来源和真实专家效果验证仍属于独立验收线，不由 Docker fixture 场景代替。
