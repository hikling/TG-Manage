# 账号与聊天

## 登录账号

TG Manage 支持手机验证码、二维码和 Telegram 两步验证。登录状态保存在持久化数据目录；重新登录时保持原账号名称，可继续关联原有账号数据。

登录时可为该账号启用 TeleBox，并输入专属 API ID/Hash。未启用 TeleBox 的普通账号可以使用服务器私有 `.env` 中的 `TG_MANAGE_TG_API_ID/HASH`；旧版 `SIGNPULSE_TG_API_*`、`TG_API_*` 仍可读取。授权后的凭据按账号加密保存，不会在账号列表 API 中回传明文。

## 代理

账号资料中的代理优先于全局代理。常见地址格式：

```text
socks5://127.0.0.1:1080
socks5://user:pass@127.0.0.1:1080
http://127.0.0.1:7890
```

## 聊天中心

聊天中心的开关默认关闭，此时只读取 Telegram 官方验证码账号 `777000` 的消息。开启后可查看会话、消息与头像，并执行发送、编辑或删除等实际 Telegram 操作。前端缓存有容量上限；长期保存消息应使用自己的备份方案。

## TeleBox 独立会话

TeleBox 不复用主账号的 Telegram 会话。每个启用账号拥有独立的运行目录和 Node 进程；账号卡片显示状态、两步验证要求与日志。停止 TeleBox 进程和退出其 Telegram 登录是两种不同操作。

## 状态与恢复

账号状态检测结果可显示 `connected`、`invalid`、`error` 或 `checking`。出现 `needs_relogin` 时，先确认代理与 API 凭据，再使用原账号名称重新完成 Telegram 授权。迁移或升级服务器时要同时保留 `sessions/`、`telebox/` 和 `.app_secret_key`；见 [无损升级](../deploy/docker.md#无损升级与回退)。
