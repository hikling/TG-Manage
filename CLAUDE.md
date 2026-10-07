# TG Manage 开发说明

本仓库为 Telegram 多账号管理面板。当前 Web UI 包括仪表盘、账号管理、聊天中心、日志、系统设置；机器人中心位于系统设置内。账号工作台和旧版 Python 签到/监听运行时已移除，不要从历史变更记录中恢复这些入口。

## 代码地图

| 位置 | 当前职责 |
| --- | --- |
| `frontend/` | Vue 3、TypeScript、Vite 面板；路由在 `src/router/index.ts`，页面在 `src/views/`，API 客户端在 `src/lib/api/`。 |
| `backend/` | FastAPI 路由、认证、账号、TeleBox、机器人、日志、备份与运维；路由在 `api/routes/`，业务逻辑在 `services/`。 |
| `tg_manage/` | Telegram 客户端、会话、安全与通知共用工具；不再含旧签到 CLI 与动作配置模型。 |
| `telebox/` | 隔离运行的 TeleBox 运行时及插件；`panel/worker.ts` 是本项目的集成适配层。 |
| `docs/` | VitePress 文档与部署、无损升级指南。 |
| `tests/` | 后端 pytest 与部分浏览器边界检查。 |

各模块细节见 [前端](./frontend/CLAUDE.md)、[后端](./backend/CLAUDE.md)、[Telegram 客户端](./tg_manage/CLAUDE.md)、[文档](./docs/CLAUDE.md)、[测试](./tests/CLAUDE.md)。实施前先阅读 `.trellis/workflow.md` 与相应 `.trellis/spec/`；以实际源码为准。

## 持久化与兼容

Docker Compose 始终使用 `./data:/data`；数据库、账号会话、密钥、TeleBox 用户插件和配置均在数据卷中。新内部包名为 `tg_manage`，新工作目录为 `.tg_manage`，但现有 `.signer` 与 `.tg_signpulse_data_dir` 会继续读取，不能在升级时直接删除。新 Telegram 应用凭据环境变量为 `TG_MANAGE_TG_API_ID/HASH`，读取时仍兼容 `SIGNPULSE_TG_API_ID/HASH` 与 `TG_API_ID/HASH`。浏览器旧存储键迁移逻辑也应保留。

升级现有 Docker Compose 部署请使用 `bash scripts/update.sh`：停应用、备份整个数据目录、快进拉取代码、重建并启动。独立 PostgreSQL 不属于 `./data`，需另行备份。详见 [Docker 部署与升级](./docs/deploy/docker.md)。不要用 `docker compose down -v` 清除数据卷。

## 本地开发与检查

- Python 版本：3.10–3.13；依赖见 `pyproject.toml`。后端入口为 `uvicorn backend.main:app --host 127.0.0.1 --port 8080`。
- 前端使用 `.nvmrc` 指定的 Node.js 22.23.1；`cd frontend && npm ci && npm run typecheck && npm test && npm run build`。
- 后端检查：`python -m ruff check backend tg_manage tests` 与 `python -m pytest -q tests`。
- 文档检查：根目录 `npm ci && npm run docs:build && npm run docs:verify-agent`。
- Docker 镜像从当前源码构建；CI 目标镜像为 `ghcr.io/hikling/tg-manage`。

敏感会话、Bot Token 与密钥不能写入日志、文档或测试快照。版本号来源是 `tg_manage/__init__.py`；发布规则见 `.github/RELEASE_RULES.md`，历史变更见 `CHANGELOG.md`。
