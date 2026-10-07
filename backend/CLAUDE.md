[根目录](../CLAUDE.md) > **backend**

# TG Manage 后端

FastAPI 提供认证、账号、聊天、TeleBox、机器人、设置、日志及运维 API。SQLite 和持久化文件保存账号与设置；APScheduler 负责维护性后台任务。

## 代码入口

| 路径 | 职责 |
|------|------|
| `main.py` | 应用初始化、生命周期、异常处理 |
| `api/routes/` | HTTP API；在 `__init__.py` 挂载路由 |
| `core/` | 环境配置、数据库、认证与限流 |
| `models/` | SQLAlchemy 模型 |
| `schemas/` | 公共请求及响应模型 |
| `services/telegram/` | Telegram 登录、会话、账号、设备与凭据 |
| `services/telebox.py` | 每账号 TeleBox 进程及插件状态 |
| `services/config.py`、`config_mixins.py` | 设置读写、导入导出 |
| `services/backup_archive.py`、`webdav_client.py` | 本地归档与 WebDAV 备份 |
| `utils/storage.py`、`utils/paths.py` | 数据目录发现及创建 |
| `utils/version_info.py` | 本地版本和 GitHub 更新检查 |

共享的 Telegram 客户端、安全和日志工具位于根目录 `tg_manage/` Python 包。不要恢复历史签到任务运行链路；目前聊天与 TeleBox API 承担相关账号操作。

## 数据与升级兼容

- `APP_DATA_DIR` 指定持久化目录；默认 Docker 卷位置为 `/data`。数据库、`sessions/`、`telebox/` 和 `.app_secret_key` 必须在升级时保持原值。
- 新安装的工作目录是 `.tg_manage/`。若已有 `.signer/`，`Settings.resolve_workdir()` 继续使用它，避免账号设置、机器人注册表及头像缓存丢失。备份清单同时包含两者。
- 新数据目录标记为 `.tg_manage_data_dir`；读取时兼容 `.tg_signpulse_data_dir`。显式 `APP_DATA_DIR_OVERRIDE_FILE` 不读取默认旧标记。
- `APP_TG_MANAGE_WORKDIR` 可指定工作目录；旧 `APP_SIGNER_WORKDIR` 仍可读取。
- Telegram API 凭据环境变量优先级：`TG_MANAGE_TG_API_ID/HASH`、`SIGNPULSE_TG_API_ID/HASH`、`TG_API_ID/HASH`。每组必须成对填写；已有账号加密凭据保持原位。
- 已保存的 WebDAV 远端目录值不重写；新默认值为 `tg-manage-backups`。

## 开发验证

先阅读项目 `.trellis/spec/backend/` 及任务文档。修改后运行相关 `tests/test_*.py`、`ruff check backend tg_manage tests`；涉及数据路径或备份时验证旧目录读写和备份内容。项目要求 Python 3.10 至 3.13。
