# 配置参考：内置 TeleBox 版本

本页适用于此私有仓库的源码构建。完整搭建命令、环境要求和升级办法见 [README](../../README.md) 与 [Docker 部署](../deploy/docker.md)。

## 必需环境

服务器需 Docker Engine 24+、Compose v2 和 Git，并有私有仓库读取权限；构建需要下载 Python/npm 依赖，运行时需连接 Telegram。Compose 镜像内包含 Python 3.11、前端构建用 Node 22、TeleBox 用 Node 24。默认容器限制 2 GiB 内存、2 CPU；多账号运行 TeleBox 应预留更多资源。

运行 `bash scripts/install.sh` 即可构建并启动。应用密钥首次启动自动生成于 `data/.app_secret_key`（权限 0600）；首次管理员设置码在 `data/.admin_setup_token`，安装脚本会显示，使用后删除。管理员在网页登录页自行设置至少 12 位密码。现有管理员不受影响。

新增或重新登录 Telegram 账号时选择是否启用 TeleBox。启用时在账号管理输入专属 API ID/Hash；关闭时如要免填，需要在服务器私有 `.env` 设置 `SIGNPULSE_TG_API_ID/HASH`。两种授权成功后的凭据均按账号加密保存于 `data/sessions/accounts.json`，不会出现在账号列表 API。旧账号若缺少专属凭据，需要重新登录。网页全局 Telegram API 配置和 AI 模型配置均不再使用。

## 可选配置

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `APP_DATA_DIR` | 容器 `/data` | 数据库、会话、密钥、任务和 TeleBox 状态根目录 |
| `PORT` | Compose `8080` | 容器内 HTTP 端口 |
| `TZ` | Compose `Asia/Shanghai` | 日志和调度时区，可在面板设置显示时区 |
| `APP_DATABASE_URL` | SQLite `data/db.sqlite` | 可选 SQLAlchemy 数据库 URL |
| `TG_SESSION_MODE` | `file` | Telegram 文件会话，或 `string` 模式 |
| `TG_GLOBAL_CONCURRENCY` | CPU 数，最多 5 | Telegram 并发上限 |
| `TG_PROXY` | 空 | 代理；面板也支持按账号配置 |
| `APP_CORS_ALLOW_ORIGINS` | localhost 开发来源 | 分离部署时允许的前端 origin |
| `ENABLE_API_DOCS` | `false` | 允许 `/docs`、`/redoc`、`/openapi.json` |
| `TELEBOX_NODE` | `node` | 本地开发指定 Node 24 可执行文件 |
| `SIGNPULSE_TG_API_ID/HASH` | 空 | 关闭 TeleBox 时账号登录使用的私有应用凭据；Compose 从未提交的 `.env` 读取 |

生产环境备份**整个** `data/`，尤其是 `.app_secret_key` 与账号会话。密钥丢失后已加密的账号凭据和 Bot Token 无法解密，需重新登录或恢复原备份。备份与历史导入中的全局 AI/Telegram API 设置不再重新激活。真实 Telegram 登录、插件安装和 Docker 构建需在服务器上验证。
