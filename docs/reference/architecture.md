# 系统架构

TG Manage 由 Vue 3 管理界面、FastAPI API、Telegram 账号服务、每账号独立的 TeleBox Node 运行时，以及持久化数据目录组成。

## 请求路径

| 组件 | 职责 |
| --- | --- |
| 前端 | 登录、仪表盘、账号与聊天、系统设置中的机器人中心、日志。 |
| FastAPI | 鉴权、账号和消息 API、Bot API、TeleBox 进程管理、备份及运维。 |
| Telegram 账号服务 | 管理主账号的授权、会话、代理和消息操作。 |
| TeleBox | 每个启用账号使用独立的 Node 进程、Telegram 会话和插件目录。 |

主要 API 前缀包括 `/api/auth`、`/api/accounts`、`/api/communications`、`/api/bots`、`/api/telebox`、`/api/config`、`/api/ops` 和 `/api/logs`。当前版本不运行旧签到、关键词监听或 AI 动作链路。

## 数据与密钥

Compose 把宿主机 `./data` 挂载到容器 `/data`。SQLite 默认保存在数据目录内；`sessions/` 保存主账号会话，`telebox/` 为各账号提供独立数据目录。账号 API 凭据和 Bot Token 由 `data/.app_secret_key` 加密。升级时保留整个挂载目录，详见 [无损升级](../deploy/docker.md#无损升级与回退)。

外部 PostgreSQL 可通过 `APP_DATABASE_URL` 配置；此时还需单独备份数据库。单个 Telegram 账号的会话不应由多个写入进程同时使用。

## 资源

默认 Compose 限制容器使用 2 GiB 内存和 2 CPU。仪表盘显示当前进程内存，容器总内存还包括各账号 TeleBox 子进程。部署多个常驻账号时，按实际运行情况观察 `docker stats` 并调整资源。
