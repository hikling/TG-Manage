---
name: quick-start
description: 引导用户部署 TG Manage、创建管理员、登录 Telegram 账号，并确认数据持久化。
---

# TG Manage 快速开始

## 步骤

1. 阅读 [快速开始](https://github.com/hikling/TG-Manage/blob/main/docs/guide/quick-start.md)。
2. 按 [Docker 部署](https://github.com/hikling/TG-Manage/blob/main/docs/deploy/docker.md) 安装，并为私有仓库准备读取权限。
3. 按 [配置参考](https://github.com/hikling/TG-Manage/blob/main/docs/reference/configuration.md) 设置可选环境变量。
4. 在账号管理登录一个 Telegram 账号，检查会话状态。
5. 确认 `./data:/data` 挂载和 `data/.app_secret_key` 存在；升级前使用 `bash scripts/update.sh`。

## 最小验收

- `/readyz` 返回正常。
- 管理员可以用原账号登录。
- 至少一个 Telegram 账号在线。
- `data/` 目录和密钥得到完整备份。
