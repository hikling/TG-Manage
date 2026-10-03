# Docker 部署：TG-SignPulse 二改版

> 本文档针对当前仓库的 `Dockerfile` 和 `docker-compose.yml`。不要使用上游公开镜像或旧文档中的 `docker compose pull` 更新本版本。完整改动、首次使用、本地开发及环境变量见 [README](../../README.md)。

## 前置环境

- Docker Engine 24+、Docker Compose v2，且主机能访问 npm/PyPI、Telegram；受限网络需为 Telegram 配置代理。
- Compose 默认限制容器使用 2 GiB 内存、2 CPU；构建阶段还需额外磁盘及内存。每运行一个 TeleBox 账号会再启动 Node 进程，应随账号数调高资源。
- Telegram 授权始终需要有效 API ID/Hash：启用 TeleBox 时在账号登录表单填写；不启用时可在服务器私有 `.env` 预设 `SIGNPULSE_TG_API_ID/HASH`，登录页面免填。

Dockerfile 的三个阶段分别为 Node 22.23.1 构建 Vue 前端、Node 24 编译/安装 TeleBox 原生依赖、Python 3.11 运行 FastAPI。生产镜像包含 Node 24 与 TeleBox 源码、插件和依赖。项目默认持久化目录为容器 `/data`。

## 部署步骤

安装 Docker Engine 24+、Docker Compose v2 和 Git，确保服务器有私有仓库读取权限及构建网络。当前 PR 合并前执行：

```bash
git clone --branch feat/telebox-login-chat-task-logs https://github.com/hikling/TG-SignPulse-Private.git && cd TG-SignPulse-Private && bash scripts/install.sh
```

合并后克隆时可省略 `--branch`。脚本构建、启动、检测 `/readyz` 并输出首次设置码；网页 `http://服务器IP:8080` 用设置码设置 `admin` 密码，至少 12 位。程序自动在 `/data/.app_secret_key` 保存应用密钥，已有管理员保留原密码。不启用 TeleBox 且要免填账号 API 时，在构建前复制 `.env.example` 为 `.env` 并填入 `SIGNPULSE_TG_API_ID/HASH`，文件只留在服务器，不提交仓库。域名和 TLS 见 [Nginx 示例](nginx.md)。

## Compose 约定

| 配置 | 当前值与含义 |
| --- | --- |
| `build: .` | 每次 `--build` 从当前源码构建，不使用上游公开镜像。 |
| `./data:/data` | 数据库、session、任务数据、TeleBox 的每账号配置和插件都依赖此卷。 |
| `PORT=8080`, `TZ=Asia/Shanghai` | 容器端口与调度时区。 |
| `mem_limit: 2g`, `cpus: 2.0` | 单容器默认资源上限；多账号运行时评估增长。 |
| `read_only: true`, `tmpfs`, `cap_drop: ALL` | 根文件系统只读，临时目录可写，移除 Linux capabilities。 |
| `healthcheck` | `/readyz` 返回服务就绪状态后标记健康。 |
| `restart: unless-stopped` | 异常退出/重启主机后拉起服务。 |

应用密钥和管理员密码不需注入。可选的服务器 Telegram 应用凭据通过 Compose 从私有 `.env` 注入，仅供关闭 TeleBox 的账号登录。首次启动在 `data/` 生成持久密钥和一次性管理员设置码。备份整个 `data/`，尤其是密钥文件。

## 首次登录与 TeleBox

1. 用安装脚本显示的一次性设置码在网页登录页设置 `admin` 密码，可启用 TOTP。
2. 在账号管理选择是否启用 TeleBox；勾选时输入该账号 API ID/Hash，登录成功后自动请求独立会话。不勾选时若服务器已配应用凭据，表单无需填写。
3. 先在聊天中心用测试会话检查头像、消息读写。启用 TeleBox 的账号在拓展插件页查看启动状态、错误阶段、两步验证及插件。
4. 任务编排可选择已加载的插件命令，日志页提供 TeleBox 日志标签。命令投递不等同于插件执行完成；其数据在 `data/telebox/`，另有 `data/sessions/` 中的面板会话。

## 升级、备份和恢复

```bash
# 更新之前，先停止并备份整个 ./data
docker compose stop
# 使用自己的备份工具保存 data/；不要将其上传公开仓库

# 从本私有仓库更新源码后重新构建
docker compose up -d --build
```

`docker compose down` 删除容器和网络，但不会删除绑定挂载的 `./data`；切勿误删 `data/`。恢复时还原完整数据目录（含 `.app_secret_key`），然后重建容器。若 Telegram session 失效，需要在面板重新授权账号。

## 排查

| 现象 | 检查项 |
| --- | --- |
| 构建失败 | Docker 可用磁盘/内存、npm/PyPI 网络，以及 TeleBox 原生模块在 Node 24 构建阶段的错误。 |
| `/readyz` 未就绪 | `docker compose ps`、`docker compose logs --tail=200 app`、`./data` 是否可写。 |
| 无法登录 Telegram | API ID/Hash、验证码/2FA、服务器访问 Telegram 的网络与代理。 |
| TeleBox 提示未安装依赖 | 必须从本仓库 `docker compose up -d --build`，不要换成上游旧镜像。 |
| TeleBox 内存不足 | 提高宿主机可用内存及 Compose `mem_limit`，减少同时运行的账号数。 |
| 旧自定义插件任务失败 | 旧 Python 插件体系已移除；备份后手工改用现有任务动作或 TeleBox 插件。 |

真实 Telegram 授权、Bot API、TPM 安装和完整 Docker 构建尚需在目标环境逐项验证，不应把离线测试当作上线验收。

### TeleBox 构建提示 npm ci 缺少锁文件

若 `docker compose ps -a` 没有容器，安装时 TeleBox 阶段报 `npm error code EUSAGE` 并提示需要 `package-lock.json`，镜像尚未构建完成，网页服务也没有启动。这时先修复构建，无需先安装 UFW。

本版本应提交 `telebox/package-lock.json`，且 Dockerfile 显式复制两个依赖文件。更新包含此修复的代码后，在原项目目录执行：

```bash
bash scripts/install.sh
```

不要删除 `data/`。若再次报错，保留构建末尾的错误信息；本机 `http://127.0.0.1:8080/` 可访问后再排查公网 TCP 8080 的安全组和防火墙。
