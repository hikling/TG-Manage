# TG-SignPulse 二改进度与搭建记录

更新日期：2026-10-03（北京时间）

## 本轮目标

1. 仅保留 TeleBox 插件，清掉 SignPulse 原插件残留。
2. 一条命令从私有仓库部署，应用密钥自动生成，首次管理员在网页设置密码。
3. 每次新增/重登 Telegram 账号时输入专属 API ID/Hash，供该账号后续操作使用。
4. 去掉 AI 模型与全局 Telegram API 配置页面和接口。
5. “拓展插件”展示当前账号实际安装的 TeleBox 插件。
6. 交付独立分支与拉取请求，由用户合并受保护的 `main`。

## 实时记录

- [x] 查看当前仓库状态、已有 README、任务文档、账号登录/设置/TeleBox 代码；本轮需求已追加到 `prd.md` 和 `implement.md`。
- [x] 新安装自动生成并持久化 `APP_SECRET_KEY`；首次管理员不再自动产生随机密码，后端建立一次性设置码，网页登录页可提交设置码和新密码。旧用户表有用户时保留原账号并清理设置码。
- [x] 手机验证码/二维码登录输入账号专属 API ID/Hash；成功授权后加密保存在 `sessions/accounts.json`（文件权限 0600），任务、监听、聊天和 TeleBox 通过账号读取。缺凭据的旧账号须重登，API 列表不返回密文或 Hash。
- [x] 系统设置页面不再显示全局 Telegram API、AI 模型卡片；后端相应配置端点已移除。拓展插件菜单指向 TeleBox 账号插件清单；旧任务表单插件注释清理。
- [x] Compose 无需传入密钥/管理员密码/共享 Telegram API；新增 `scripts/install.sh` 一次构建并显示首次设置码。
- [x] README 中英文、快速开始、Docker、配置参考、账号、认证、FAQ、AI 迁移说明与 Trellis 进度同步到新搭建方式；旧全局设置从 JSON 导入/导出排除。
- [x] 首次安装与账号加密存储增加针对性测试；修正 Docker 入口脚本重启后将密钥文件权限放宽的问题。
- [x] 私有仓库 `hikling/TG-SignPulse-Private` 创建功能分支 `feat/telebox-only-onboarding` 与 [PR #12](https://github.com/hikling/TG-SignPulse-Private/pull/12)，目标是受保护的 `main`；未合并。

## 核查发现

- 原 Python 插件 API/运行时代码已在上一轮移除，本轮移除剩余表单/日志注释；TeleBox 插件清单是“拓展插件”的唯一可操作入口。
- 已有账号的旧共享 API 配置不会静默迁移到账号级；该账号须用同名账号重登一次。既有管理员保持原账号和密码。
- 缺少账号级凭据的账号列表显示 `API_CREDENTIALS_MISSING` 与重登提示，方便迁移时定位。
- 旧 AI 动作不会自动改写，历史数据保留；新任务选择器不再提供 AI 动作，配置接口已下线。升级前备份数据。

## 验证与限制

- 前端：`npm run typecheck`、`npm test -- --run`（419 项）、`npm run build` 均通过。
- 后端：`test_onboarding_credentials.py`、`test_telegram_sessions.py`、`test_config_env_sync.py`、`test_config.py`、`test_ai_config.py`、`test_runtime_settings.py` 共 154 项通过（`--no-cov`）。其中新测试检查一次性设置码、账号凭据加密/隔离/重命名/删除；导出与导入不会恢复旧全局 AI 配置。
- Ruff 对本轮改动的后端与测试文件通过，`git diff --check`、`bash -n scripts/install.sh`、`sh -n docker/entrypoint.sh`、Python compileall 通过；TeleBox `npx tsc --noEmit` 通过。
- 当前沙箱没有 Docker CLI；FastAPI `TestClient` 在该沙箱中连最小 FastAPI 应用也会阻塞，因此依赖它的路由集成测试无法在此运行。真实 Telegram 登录、TeleBox 独立会话、插件远程安装和 Docker 构建须在目标服务器验证；本轮未发送 Telegram 消息。
- PR 已提供完整代码和验证记录，服务器上的 Docker 构建、Telegram 授权及 TeleBox 插件操作仍需仓库所有者在合并前核查；合并步骤保留给仓库所有者。

## 继续完善（2026-10-03）

- 清除设置页组合式函数、表单快照和保存请求里的旧 AI/共享 Telegram 凭据状态；全量保存只包含仍可见的通用、通知和备份设置，不再带隐藏的 AI 参数。
- 移除 ConfigService 的全局 AI 模型读写/连通性服务与共享 Telegram API 凭据服务、默认共享凭据和旧解析兼容路径；历史配置文件保留为数据，导入时仍跳过。账号会话迁移工具改为逐账号读取已保存的 API 凭据，缺失时提示重登。
- 完整/WebDAV/自动备份增加 `data/.app_secret_key` 和 `data/telebox/`，同时排除首次管理员设置码；补回归测试。更新功能介绍、任务、监听、架构、运维与备份文档中的旧功能描述。
- 前端 `npm run typecheck`、`npm test -- --run`（415 项）及 `npm run build` 通过；后端 8 组针对性文件共 229 项及备份路径 3 项通过。改动文件 Ruff、Python compileall、`git diff --check` 通过。服务器 Docker 构建、真实 Telegram 和 TeleBox 插件远程安装仍未验证。保护的 `main` 未改动。
