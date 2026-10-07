[根目录](../CLAUDE.md) > **tg_manage**

# Telegram 账号客户端

本目录保留面板账号登录、会话、代理、安全和通知共用的工具。`core/client.py` 提供 Telegram 客户端的连接与引用计数；`core/__init__.py` 只导出账号客户端接口。

历史版本的签到/监控命令行、动作指令和 Python 执行运行时已移除。当前账号操作由后端与 TeleBox 承担；不要重新引用旧签到配置或命令行入口。
