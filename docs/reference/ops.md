# 运维手册

## 健康与资源

| 地址或命令 | 用途 |
| --- | --- |
| `/healthz` | 基础存活检查。 |
| `/readyz` | 服务是否完成启动；Compose 使用它作为健康检查。 |
| `docker compose ps` | 容器状态。 |
| `docker compose logs --tail=200 app` | 应用启动和运行日志。 |
| `docker stats --no-stream tg-manage` | 整个容器的内存、CPU 使用情况。 |
| `docker inspect -f '&#123;&#123;.State.OOMKilled&#125;&#125;' tg-manage` | 检查上次退出是否由内存不足引起。 |

仪表盘显示当前进程内存，适合观察应用自身变化；它与容器总内存不是同一指标。每个运行中的 TeleBox 账号另有 Node 进程，因此评估内存上限时还要看 `docker stats`。

## 数据目录

Compose 固定将宿主机 `./data` 挂载为容器 `/data`。下列内容应作为一个整体备份：

- `db.sqlite` 及可能存在的 `-wal`、`-shm` 文件。
- `sessions/`、`telebox/`、日志、任务历史和其他账号数据。
- 隐藏文件，尤其是 `.app_secret_key`。丢失密钥会使已加密的账号凭据和 Bot Token 无法读取。

若使用外部 PostgreSQL，`data/` 仍需备份，同时对外部数据库单独执行 `pg_dump` 等数据库级备份。备份包能恢复敏感凭据，不要上传公共仓库。

## 升级

从已有部署的仓库目录运行：

```bash
bash scripts/update.sh
```

脚本会停应用、备份完整数据目录、用 `git pull --ff-only` 获取当前仓库代码，再执行 `scripts/install.sh` 重建并启动。它不会自动删除旧备份。升级期间会有短暂停机。详见 [Docker 部署与无损升级](../deploy/docker.md#无损升级与回退)。

升级后运行：

```bash
docker compose ps
curl -fsS http://127.0.0.1:8080/readyz
docker compose logs --tail=100 app
```

再用原管理员账号登录，确认账号列表、登录会话、系统设置和各账号 TeleBox 状态。若需要回退，使用升级前的代码提交和同一时间点的完整数据备份；先检查压缩包内的顶层目录，再解压，避免产生 `data/data/`。恢复时服务必须停止。

## 手动备份

在项目目录下运行：

```bash
docker compose stop app
bash scripts/backup.sh
docker compose start app
```

备份默认存于 `backups/tg-manage-data-<时间>.tar.gz`，包含完整数据目录。`backup.sh` 不会清理旧归档；按磁盘容量自行决定保留策略。面板的 WebDAV 备份见 [WebDAV 备份与恢复](../guide/backup-webdav.md)。

## 常见故障

| 现象 | 首先检查 |
| --- | --- |
| 重启后数据不见 | `docker-compose.yml` 的 `./data:/data` 挂载、宿主机目录和写权限。 |
| 所有账号凭据失效 | `data/.app_secret_key` 是否仍是原文件，以及完整备份是否正确恢复。 |
| 单个账号需重新登录 | Telegram 会话状态、账号 API 凭据与代理。 |
| TeleBox 启动失败 | 账号卡片的 TeleBox 状态与日志、容器内存、插件依赖。 |
| `/readyz` 返回错误 | `docker compose logs --tail=200 app`、数据目录权限和磁盘空间。 |
