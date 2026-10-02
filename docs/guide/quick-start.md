# 快速开始：TG-SignPulse + 内置 TeleBox

> 此文档适用于本二改仓库。**不要使用**上游 `ghcr.io/silentely/tg-signpulse` 镜像；它不含聊天中心和 TeleBox 面板。完整改动、环境变量、本地开发与验证说明见仓库根目录 [README](../../README.md)。

## 环境

- Docker Engine 24+ 和 Docker Compose v2；能构建/下载 Node 与 Python 依赖。
- 宿主机至少能运行当前 Compose 配置的 2 GiB 容器；多账号 TeleBox 每个账号另有 Node 进程。
- 可连接 Telegram、能接收验证码/使用手机扫码的 Telegram 账号，以及你自己的 API ID/Hash。
- Windows/macOS 建议 Docker Desktop；本地源码开发所需 Python 3.10–3.13、Node 22.23.1 和另一个 Node 24，详见 README。

## 1. 从本仓库获取源码

```bash
git clone https://github.com/hikling/TG-SignPulse-Private.git
cd TG-SignPulse-Private
cp .env.example .env
```

该仓库是私有仓库，克隆时需要 GitHub 授权；已持有源码的用户直接在源码根目录开始。

## 2. 配置本地 `.env`

```dotenv
TG_API_ID=your_api_id
TG_API_HASH=your_api_hash
APP_SECRET_KEY=replace_with_a_long_random_secret
ADMIN_PASSWORD=replace_with_a_strong_password
```

`APP_SECRET_KEY` 可通过 `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` 生成。不要把真实值写入 Markdown、截图或 Git。若服务器连接 Telegram 需要代理，先看 [README 环境变量](../../README.md#环境变量) 和面板代理设置。

## 3. 构建、启动、检查

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 app
curl -f http://127.0.0.1:8080/readyz
```

浏览器访问 `http://服务器IP:8080`，首次用户名 `admin`，密码为 `ADMIN_PASSWORD`。未设置管理员密码时查看 `data/.admin_bootstrap_password`。公网部署请配置 HTTPS 反向代理。

## 4. 登录账号并试用

1. “账号管理”：使用手机验证码或二维码登录自己的 Telegram 测试账号；启用两步验证的账号还需密码。
2. “聊天中心”：选择账号，查看私聊、群组、频道及机器人会话；先用测试会话尝试发送、编辑、归档等操作。
3. “任务编排”：检查原有签到任务并创建新任务。已移除的 Python 自定义插件动作不会自动迁移。
4. “TeleBox”：选择已登录账号启动独立会话，等待状态变为运行中；如提示 `password_required`，在面板输入 Telegram 两步验证密码。每账号独立运行，插件管理与日志都在此页。

完整目录与升级/备份说明见 [README](../../README.md#数据升级与备份) 和 [Docker 部署](../deploy/docker.md)。真实 Telegram 授权、Bot API 和 TPM 远程安装需要在你自己的环境中检验。
