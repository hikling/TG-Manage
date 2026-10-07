# 后端开发规范索引

适用 `backend/`，涉及 Telegram 客户端时也阅读 `tg_manage/CLAUDE.md`。以实际源码为准；不要把已删除的 Python 插件与工作台路由重新引入。

## 开发前

1. 阅读 [目录结构](./directory-structure.md)、[数据库](./database-guidelines.md)、[错误处理](./error-handling.md)、[日志](./logging-guidelines.md)、[质量](./quality-guidelines.md)。
2. 搜索相邻路由、服务和测试；跨层变更同时核对 `frontend/src/lib/api/` 类型。
3. 涉及账号或 TeleBox 时，核对账号隔离、认证依赖和敏感信息边界。

## 质量检查

```bash
python3 -m ruff check backend tg_manage tests
python3 -m pytest -q tests/<相关测试文件>.py
```

全量 pytest 使用 `pyproject.toml` 的覆盖率门槛；没有真实 Telegram 会话时，只能报告模拟或隔离测试通过。
