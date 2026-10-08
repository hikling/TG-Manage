# 后端错误处理

在请求边界先通过 Pydantic/FastAPI 验证：`backend/api/routes/communications.py` 中 `chat_id`、消息长度、分页上限和媒体大小均有界；不合规输入返回 422。业务对象不存在返回 404，未认证请求由 `get_current_user` 返回 401；服务调用 Telegram 失败时转换为可读的 HTTP 错误，保留可排障的上下文而不泄露凭据。

```python
# backend/services/official_code_bot.py：外部 Bot API 错误
try:
    response = await client.post(bot_api_url, json=payload)
except httpx.RequestError as exc:
    raise CodeBotError(f"Bot API 网络或响应错误（{type(exc).__name__}）") from None
```

外部 Bot API 的响应或底层异常可能含 Token；`official_code_bot.py::_bot_call` 用固定安全消息返回，不直接转发 URL/异常文本。`telebox.py::redact` 在把 worker 输出放入内存日志前擦除敏感字段。清理资源放在 `finally`（如 `communications.py::upload` 关闭 UploadFile，`core/database.py::get_db` 关闭 Session）。不要用无提示的 `except: pass` 掩盖用户操作失败；维持已有错误状态语义和前端 `ApiError` 解析约定。
