# TG Manage 文档

TG Manage 提供 Telegram 多账号管理、按需开启的聊天中心、账号级 TeleBox 运行时、私人机器人通知，以及账户登录备份。v2.5.0 新增主/兜底 Xray 订阅与账号独占节点、每日零点账号和官方消息报告，并明确区分手动单检、批检的范围。仪表盘保留可自定义的封面与账号管理、刷新两个操作。

先读 [v2.5.0 完整更新说明](releases/v2.5.0.md)，可了解新增功能、节点切换时间、直连边界和升级注意事项。

## 使用

- [快速开始](guide/quick-start.md)
- [账号与聊天](guide/accounts.md)
- [功能介绍](features.md)
- [账户登录备份与恢复](guide/account-login-backup.md)
- [v2.5.0 完整更新说明](releases/v2.5.0.md)

## 部署与维护

- [Docker 部署及无损升级](deploy/docker.md)
- [运维手册](reference/ops.md)
- [配置参考](reference/configuration.md)
- [常见问题](faq.md)

旧签到任务、关键词监听和 AI 动作已退出运行链路。历史数据留在数据目录内，升级前请备份整个 `data/`；“账户管理 → 登录备份”的 `.tglogin` 不包含 TeleBox 或面板配置，不能替代整目录备份。仓库入口见 [README](../README.md)。
