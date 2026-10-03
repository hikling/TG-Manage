# 快速开始：TG-SignPulse + 内置 TeleBox

> 此文档适用于本二改仓库。**不要使用**上游 `ghcr.io/silentely/tg-signpulse` 镜像；它不含聊天中心和 TeleBox 面板。完整改动、环境变量、本地开发与验证说明见仓库根目录 [README](../../README.md)。

## 环境

- Docker Engine 24+ 和 Docker Compose v2；能构建/下载 Node 与 Python 依赖。
- 宿主机至少能运行当前 Compose 配置的 2 GiB 容器；多账号 TeleBox 每个账号另有 Node 进程。
- 可连接 Telegram、能接收验证码/使用手机扫码的 Telegram 账号，以及你自己的 API ID/Hash。
- Windows/macOS 建议 Docker Desktop；本地源码开发所需 Python 3.10–3.13、Node 22.23.1 和另一个 Node 24，详见 README。

## 一条命令部署

服务器准备 Docker Engine 24+、Compose v2、Git 和本私有仓库的读取权限。当前 PR 合并前执行：

```bash
git clone --branch fix/telebox-esm-workbench https://github.com/hikling/TG-SignPulse-Private.git && cd TG-SignPulse-Private && bash scripts/install.sh
```

合并至 main 后可省略 `--branch fix/telebox-esm-workbench`。脚本构建镜像、启动容器、检测就绪并打印首次设置码。应用密钥自动生成并保存在 `data/.app_secret_key`。浏览器打开 `http://服务器IP:8080`，输入一次性设置码并自行设置管理员密码（至少 12 位）。不启用 TeleBox 且希望登录页免填 API 时，先在服务器私有 `.env` 设置 `SIGNPULSE_TG_API_ID/HASH`；Telegram 授权仍需应用凭据。已有账号不会被重置。公网访问请配置 HTTPS。

查看状态：`docker compose ps`；查看日志：`docker compose logs --tail=100 app`。克隆私有仓库需要 GitHub 授权。

## 4. 登录账号并试用

1. “账号管理”：选择是否启用 TeleBox。勾选时输入该账号专属 API ID/Hash，登录后自动请求启动；不勾选时使用服务器私有凭据。再用手机验证码或二维码登录测试账号。
2. “聊天中心”：选择账号，查看带头像的私聊、群组、频道及机器人会话；先用测试会话尝试发送、编辑、归档等操作。
3. “任务编排”：可选当前账号已加载的 TeleBox 插件命令。已移除的 Python 自定义插件动作不会自动迁移。
4. “拓展插件”：查看独立会话状态、插件清单和错误阶段；如提示 `password_required`，输入 Telegram 两步验证密码。统一“日志”页也显示 TeleBox 运行记录。

完整目录与升级/备份说明见 [README](../../README.md#数据升级与备份) 和 [Docker 部署](../deploy/docker.md)。真实 Telegram 授权、Bot API 和 TPM 远程安装需要在你自己的环境中检验。
