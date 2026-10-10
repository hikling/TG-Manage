# Docker 部署与升级

本文适用于 [TG Manage 源码仓库](https://github.com/hikling/TG-Manage) 的 `Dockerfile` 和 `docker-compose.yml`。Compose 使用 `build: .`，从当前源码构建镜像。

## 部署前准备

- Linux 主机安装 Docker Engine 24+、Docker Compose v2 和 Git；主机需能下载 Python/npm 依赖并连接 Telegram。
- 私有仓库需要对应 GitHub 读取权限。
- 小型部署最低支持 1 vCPU / 1 GiB RAM；Compose 不设置固定 CPU 或内存上限。更大的实例可以按账号数量和实际负载扩容，每个运行中的 TeleBox 账号还会启动独立 Node 进程。
- 需要自己的 Telegram API ID/Hash 时，在未提交的 `.env` 中设置 `TG_MANAGE_TG_API_ID` 和 `TG_MANAGE_TG_API_HASH`。旧部署的 `SIGNPULSE_TG_API_*`、`TG_API_*` 仍可读取。

## 首次安装

```bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
bash scripts/install.sh
```

安装脚本执行 `docker compose up -d --build`，等待 `/readyz` 就绪，并输出一次性管理员设置码。浏览器打开 `http://服务器IP:8080`，用设置码创建至少 12 位的管理员密码。已有管理员账号不会被重置。公网访问请配置 [HTTPS 反向代理](nginx.md)。

当前 Compose 的关键约定：

| 配置 | 作用 |
| --- | --- |
| `./data:/data` | 宿主机持久化目录。包含 SQLite、会话、设置、密钥、TeleBox 账号数据和自定义仪表盘封面（`.tg_manage/appearance/` 或旧版 `.signer/appearance/`）。 |
| `container_name: tg-manage` | 容器名称；使用 `docker stats tg-manage` 查看容器资源。 |
| `read_only: true` 与 `/tmp` 临时卷 | 根文件系统只读；`/data` 必须可写。 |
| `/readyz` 健康检查 | 确认服务启动完成。 |

首次启动自动创建 `data/.app_secret_key`。它用于解密账号凭据和 Bot Token，必须与数据库及会话一起保留。

## 无损升级与回退

先确认当前仓库使用的 `./data:/data` 挂载及实际数据目录。若自定义了数据目录或使用外部 PostgreSQL，分别确认挂载源与数据库备份方案。不要只备份 `db.sqlite`，也不要遗漏隐藏文件。

在原仓库目录执行：

```bash
bash scripts/update.sh
```

脚本会短暂停止应用，避免 SQLite 文件及 WAL 在备份期间继续写入。随后检查现有数据目录，调用 `scripts/backup.sh` 将**整个目录**归档到 `backups/tg-manage-data-<时间>.tar.gz`，再运行 `git pull --ff-only` 和 `scripts/install.sh`。备份或拉取失败时会尝试重启原有服务。旧备份不会自动删除；请检查磁盘余量。`git pull --ff-only` 遇到本地提交冲突时会停止，不会强行覆盖。更新后原有 `./data:/data` 挂载保持不变。

若手动升级，顺序相同：停服务、完整备份 `data/`、从本仓库更新代码、运行 `docker compose up -d --build`。`docker compose down` 会删除容器和网络，但不会删除绑定挂载的 `./data`；不可使用 `down -v` 来代替常规升级。

升级后核查：

```bash
docker compose ps
docker compose logs --tail=100 app
curl -fsS http://127.0.0.1:8080/readyz
docker stats --no-stream tg-manage
```

再用原管理员账号登录，检查账号列表、Telegram 会话、系统设置和各账号 TeleBox 状态。使用 `docker stats` 观察整个容器的资源占用。

需要回退时，先 `docker compose stop app`，切回升级前的代码提交，恢复备份中的**完整**数据目录（包括 `.app_secret_key`、`sessions/`、`telebox/` 和隐藏文件），再执行 `docker compose up -d --build`。归档由 `backup.sh` 在数据目录的父目录打包；解压前先用 `tar -tzf <备份文件>` 核对顶层目录，避免解压到错误层级。回退旧代码可能无法读取新版本写入的数据，因此优先使用升级前的整目录备份。使用 PostgreSQL 时还要恢复同一时间点的数据库备份。

## 常用命令

```bash
docker compose ps
docker compose logs --tail=200 app
docker compose stop app
docker compose start app
```

## 排查

| 现象 | 检查项 |
| --- | --- |
| 构建失败 | Docker 磁盘/内存、npm/PyPI 网络和 TeleBox 原生模块错误。 |
| `/readyz` 未就绪 | `docker compose ps`、应用日志及 `./data` 的可写权限。 |
| Telegram 登录失败 | API ID/Hash、验证码/2FA、服务器网络及账号代理。 |
| TeleBox 内存不足 | 观察 `docker stats` 和各账号日志；按实际负载调高内存或减少常驻账号。 |

真实 Telegram 授权、Bot API 和 TeleBox 远程插件安装需要在目标环境验证。
