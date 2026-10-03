# 后端目录结构

`backend/main.py` 负责 FastAPI 入口、路由挂载与 lifespan；`backend/api/routes/` 放 HTTP 输入校验和响应转换，`backend/services/` 放业务与 Telegram 调用，`backend/core/` 放配置、认证、数据库，`backend/models/` 是 SQLAlchemy 表，`backend/schemas/` 是共享 Pydantic 模型，`backend/utils/` 放可复用的存储、时间、账号锁等辅助代码。定时任务在 `backend/scheduler/`；底层 Telegram 行为在 `tg_signer/`。

## 实例

- `backend/api/routes/communications.py` 声明 `/communications` 路由、Bearer 认证和 `MessageInput`；实际对话操作交给 `backend/services/communications.py`。
- `backend/api/routes/telebox.py` 与 `backend/services/telebox.py` 分开管理请求和每账号进程；原版 TypeScript 代码保留在 `telebox/`。
- 签到配置不是 ORM 任务表：`backend/services/sign_tasks.py` 是门面，CRUD/运行/历史分散在 `sign_task_*` 模块，底层任务配置为文件。

新增 API 要在 `backend/api/routes/__init__.py` 注册，确认 `backend/main.py` 的 `/api` 前缀。避免把 Telegram 连接、文件读写或调度状态直接塞进路由函数；也不要恢复已移除的 Python 插件目录与频道管理专页。

完整备份路径同时定义在 `backend/services/backup_archive.py::DEFAULT_BACKUP_PATHS`（自动备份）和 `backend/api/routes/ops.py::BACKUP_ARCHIVE_PATHS`（手动/WebDAV）；账号加密依赖 `.app_secret_key`，TeleBox 每账号数据在 `telebox/`。新增持久数据时要同步检查这两套归档路径及状态页路径，验证恢复所需文件一并备份。
