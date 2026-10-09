# 快速开始：TG Manage

## 准备

服务器需要 Docker Engine 24+、Docker Compose v2、Git，以及连接 Telegram 和下载构建依赖的网络。TeleBox 账号需要自己的 Telegram API ID/Hash。

## 安装

```bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
bash scripts/install.sh
```

安装脚本从源码构建镜像、启动容器、等待 `/readyz` 就绪，并输出一次性管理员设置码。打开 `http://服务器IP:8080`，用设置码创建至少 12 位的管理员密码。已有部署会保留原管理员密码。

不启用 TeleBox 的普通账号也可使用服务器自己的 Telegram 应用凭据：在私有 `.env` 中设置 `TG_MANAGE_TG_API_ID` 和 `TG_MANAGE_TG_API_HASH`。旧版 `SIGNPULSE_TG_API_*`、`TG_API_*` 在升级时继续读取。

## 开始使用

1. 在“账号管理”用手机验证码或二维码登录账号；需要 TeleBox 时填写该账号专属 API ID/Hash。
2. 在账号卡片查看主会话和 TeleBox 的独立状态；出现两步验证提示时按页面要求补交密码。单检和批检共用每账号成功后 45 秒的检测间隔。
3. 在“聊天中心”按需开启聊天，先用自己的测试对话验证消息收发。
4. 如需私人机器人，在“系统设置 → 机器人通知”填写 Bot Token 和正整数的私人目标 ID，启用后仅该 ID 可以用 `/code 账号名` 查询最近 5 分钟的官方验证码，或用 `/me` 查看账号名称和备注。两种命令共用 45 秒间隔，空闲时不轮询账号消息。
5. 在仪表盘查看当前进程内存，部署在容器内时再用 `docker stats --no-stream tg-manage` 查看总体内存。

## 下次升级

在原仓库目录执行 `bash scripts/update.sh`。脚本会短暂停机并备份整个 `data/`，再拉取当前仓库代码和重建。升级不会清空原挂载目录；检查与回退步骤见 [Docker 部署与升级](../deploy/docker.md#无损升级与回退)。
