[根目录](../CLAUDE.md) > **tg_signer**

# Telegram 账号客户端

本目录保留面板账号登录、会话、代理、安全和通知共用的工具。`core/client.py` 提供 Telegram 客户端的连接与引用计数；`core/__init__.py` 只导出账号客户端接口。

旧 `tg-signer` 签到/监控命令行、动作指令和 Python 执行运行时已移除。面板任务只在 `backend/services/telebox_tasks.py` 调度 TeleBox 加载的插件命令，账号工作台另有每日文字消息。不要重新引用旧签到配置或命令行入口。
