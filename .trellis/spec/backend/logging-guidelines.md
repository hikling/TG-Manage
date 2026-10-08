# 后端日志规范

采用 Python `logging`；例如 `backend/core/auth.py` 的 `logging.getLogger("backend.auth")`、`backend/services/users.py` 的 `logging.getLogger("backend.users")`。在启动流程设定日志等级；`debug` 可用于 JWT 解码类别，`warning` 记录需关注但可恢复的状态，`exception` 在处理未知异常时保留栈。

```python
# backend/core/auth.py 的安全日志方式
logger.debug("JWT 解码成功但缺少 sub，按未认证处理")
```

不能记录 API_HASH、session、Bot Token、验证码、TOTP、密码或包含 Token 的外部 URL。`backend/services/official_code_bot.py::_bot_call` 特意不记录 httpx 异常原文；验证码轮询游标只持久化消息 ID 和更新偏移量，不持久化验证码。`backend/services/telebox.py::_log` 经 `redact()` 后只保留每账号最多 300 条日志。`backend/services/users.py` 只记录初始密码文件路径，不写出密码内容。需要新增运行记录时沿用有界日志、UTC 时间和账号隔离。
