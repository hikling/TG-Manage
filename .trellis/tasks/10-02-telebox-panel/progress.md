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

## 服务器构建修复（2026-10-03）

- 用户服务器确认：Compose 没有容器，构建在 TeleBox 的 `npm ci` 阶段报 `EUSAGE`，提示缺少锁文件。
- 根因：本地 `telebox/package-lock.json` 存在，但上游 `.gitignore` 忽略它，之前上传未包含此文件。
- 修复边界：提交现有且匹配 package.json 的锁文件；取消忽略；Dockerfile 显式复制 package.json 和 package-lock.json，让遗漏在 COPY 阶段立即暴露。保留 npm ci，不改用浮动版本安装。
- 修复后从新 PR 分支或合并后的 main 更新，再执行 `bash scripts/install.sh`。无需删除 data/ 或修改密码、API 凭据。
- 验证结果和 PR 地址将在完成检查后补充；本环境仍无 Docker，不宣称完整镜像构建通过。
- 验证：新建空目录仅复制两个依赖文件，使用 Node 24 执行 `npm ci --include=dev --ignore-scripts --dry-run --offline --no-audit --no-fund` 成功（384 包）。锁文件版本 3、根依赖/开发依赖与 package.json 完全匹配，453 个锁定条目仅使用 registry.npmjs.org。此检查验证锁文件可用性，不编译原生模块；完整 Docker 构建由服务器重试验证。

- 修复已上传至 `fix/telebox-docker-lockfile`，创建 [PR #13](https://github.com/hikling/TG-SignPulse-Private/pull/13)。保护的 main 未改动；远端锁文件内容已核对与本地一致。服务器在原目录执行 `git fetch origin && git switch fix/telebox-docker-lockfile && bash scripts/install.sh` 即可合并前验证。

## 本轮五项改造（2026-10-03）

- [x] TeleBox 初始化按依赖、连接、独立会话授权、插件、运行时记录失败阶段和脱敏错误；启动接口短暂等待即时失败，进程异常退出保留 failed 状态及消息，取消前端固定成功提示。截图仅有通用 `Error`，没有服务器异常详情，因此尚无法断言原始网络/授权根因；重试新版本时应检查新的阶段和日志。
- [x] 账号登录时选择是否启用 TeleBox，成功后自动请求启停；关闭时登录表单免填 API，服务端读取私有 `SIGNPULSE_TG_API_ID/HASH`。Telegram 本身仍要求应用凭据，服务器未配置时会明确报错。
- [x] 聊天中心复用现有带鉴权和本地缓存的 Telegram 头像接口；懒加载、资源释放、无头像占位，改善列表、标题、气泡及移动端排版。
- [x] TeleBox 工作进程公布实际加载的插件命令；定时任务动作 10 按账号和命令校验后用 TeleBox 自身会话向“收藏夹”投递，任务记录投递结果，统一日志页增加 TeleBox 标签。插件异步处理结果不当作任务投递成功的证据。
- [x] 系统设置的通用、机器人通知、数据管理改为原生 details 折叠区，点击展开。

当前核查：截图中 TeleBox 在启动后立即报告通用 `Error` 并退出码 0，现有前端却固定提示“已启动授权流程”；原代码在初始化异常时吞掉具体失败阶段。未拿到服务器完整运行上下文，修复时保留有界、脱敏的诊断信息。无 TeleBox 的 Telegram 登录也仍需 API ID/Hash，这不是可省去的 Telegram 协议参数。

验证（离线）：前端 `npm run typecheck`、417 项 Vitest、`npm run build` 通过；TeleBox `npx tsc --noEmit` 通过；后端任务桥接、账号隔离与任务执行相关 44 项测试通过。原 `test_sign_task_runner.py` 夹具缺少上一轮新增的账号 API 凭据，本轮补了模拟凭据后 29 项正常通过。FastAPI TestClient 在本运行环境会阻塞；Docker 和真实 Telegram 会话不可在此验证。README、账号/任务指南、Docker 部署说明同步写入搭建条件和改动。

交付：远端 `main` 已合并上一轮 PR #12/#13。本轮 35 个文本文件与本地暂存文件树 SHA 一致，位于私有分支 `feat/telebox-login-chat-task-logs` 和 [PR #14](https://github.com/hikling/TG-SignPulse-Private/pull/14)；保护的 `main` 未改动。PR 已可审阅，服务器上的真实会话和 Docker 验收仍待完成，合并由仓库所有者决定。

## TeleBox ESM 故障与工作台修订（2026-10-03）

- 收到服务器明确错误：Node ESM 拒绝动态导入 `teleproto/sessions` 目录，失败发生在工作进程的“依赖加载”阶段，早于 API ID/Hash 验证和独立授权。适配器改为与 TeleBox 上游一致的 CommonJS `require`，并统一用同一模块缓存读取运行时、插件管理器、TPM，避免 ESM/CJS 双实例。
- 已有账号的工作目录会刷新面板适配器及受管理的 TypeScript 启动脚本；不覆盖该账号的 `plugins/`、`assets/`、`config.json` 与会话。增加回归测试覆盖旧启动脚本更新和用户插件保留。
- 操作账号、目标对话改为卡片式复选列表，显示选中范围、搜索、群头像、加载和空状态；任务表单可刷新当前账号已加载的 TeleBox 命令，并解释无命令或读取失败。
- 删除专用群聊管理页面、侧边栏入口、账号快捷入口、路由和对应群资料/退出 API。聊天中心继续提供普通群会话，工作台继续使用 `dialogs?kind=groups` 查询共有群。
- 离线验证：真实 Node 24 工作进程加载后用替身 `connect()` 抛出 `OFFLINE_CONNECT_SENTINEL`，错误进入“连接 Telegram”阶段，不再出现 `Directory import`；上游运行时/TPM/插件管理器模块解析通过，TeleBox TypeScript 检查通过。前端类型检查、417 项测试与构建通过；Python 4 项针对性测试和 Ruff 通过。Python `TestClient` 仍在本沙箱阻塞；未使用真实 Telegram 凭据、未发消息，Docker 及插件远程安装需要服务器验收。
- 上一轮 PR #14 已于 2026-10-03 合并到 `main`（合并提交 `033936f`）。本次修复以该提交为基线，使用 `fix/telebox-esm-workbench` 独立分支；需在服务器用此分支重建镜像后观察真实 TeleBox 授权及插件加载。
- 已创建 [PR #15：修复 TeleBox 启动错误并优化账号工作台](https://github.com/hikling/TG-SignPulse-Private/pull/15)，目标为受保护的 `main`，暂未合并。首次远端提交 `2c522da` 的 Git 树与本地暂存树 `eb0b5db` 完全一致；本段后续进度记录将在同一分支追加。

## TeleBox 专属任务体系（2026-10-03）

变更边界：现有任务页面写入 `/sign-tasks` 的旧动作配置，`backend/scheduler` 自动同步并执行这些配置，关键词监听也从中恢复；工作台每日消息复用同一旧动作。因此仅换掉表单会继续执行旧任务。新任务应通过 `/telebox-tasks` 持久化为账号、插件、命令、参数和每日时间；调度器只从该存储注册插件命令和工作台每日消息。工作台立即发送仍走现有通信 API。代理的 API 保留，前端入口迁入系统设置。旧任务文件和历史日志保存在数据目录但不执行、不显示在新编排页。

预计修改：`backend/services/telebox_tasks.py`、`backend/api/routes/telebox_tasks.py` 定义独立接口和存储；`backend/scheduler/__init__.py`、`backend/main.py` 停止旧作业并注册新作业；`frontend/src/views/Tasks.vue`、`Workbench.vue`、`Settings.vue` 及导航/API 类型调整交互；文档和测试验证账号边界、命令识别、旧任务停运与每日发送。登录/聊天、TeleBox 上游源码和原有数据文件不在此任务中改写。

## TeleBox 专属任务与聊天中心开关收尾（2026-10-03）

- 代理管理进入系统设置；旧任务页面、API、调度作业、关键词监听进程及 Python 服务移除，新任务存储只接受 TeleBox 运行时已加载的插件命令与工作台每日文字消息。便携配置导入跳过旧 `signs/monitors`，完整备份包含 `telebox-tasks.json`。
- 按 TeleBox 插件管理器实际加载的 `listCommands/getPluginEntry` 识别命令，支持 Unicode 命令；使用运行时前缀向该账号收藏夹投递，由原生消息事件调用 `cmdHandlers`。原插件 `cronTasks` 生命周期由 TeleBox 自行管理。
- 系统设置新增默认关闭的聊天中心开关；关闭时后端拒绝普通会话、消息、媒体及头像读取，账号管理的官方 `777000` 消息仍可读取。工作台在关闭状态接受手动目标 ID/用户名并保留立即发送和每日定时；开启时列出共有群。聊天页内存数据和磁盘头像缓存超过 5 MiB 清理，关闭时清空。
- 本地验证：前端类型检查、250 项测试、生产构建通过；TeleBox TypeScript 检查通过；后端针对性测试通过，改动文件 Ruff 与 compileall 通过。完整 Python 测试在本环境的 FastAPI TestClient 阻塞，45 秒超时；真实 Telegram、Docker 与插件远程安装仍须服务器验证。

- 收尾检查将旧 `tg_signer` CLI、签到/监听配置模型、动作运行时和对应测试夹具移除，保留账号登录依赖的 `core/client.py`；任务代码不再有旧动作入口。文档同步到本轮功能分支。
- 工作台关闭聊天中心后可手动填写目标；读取共有群时达到 5 MiB 即丢弃结果，聊天头像响应禁用浏览器持久缓存。针对性后端 31 项、前端 250 项测试、TypeScript 检查及前端构建通过，Python 测试可完整收集 655 项。受限运行环境中的 FastAPI TestClient 完整测试及真实 Telegram / Docker 仍待服务器验证。

## 聊天中心与插件命令范围修订（2026-10-03）

- 左侧聊天中心入口常驻，开关移到聊天页面；关闭时本页按账号读取官方服务号 `777000`，开启后再请求普通会话。代理管理独立卡片移除，账号资料仍可设置代理。
- TeleBox 命令上报携带内置/安装来源，任务只接受 KITT 或账号安装插件实际加载的命令。旧插件任务从面板每日调度中移除；插件原生 `cronTasks` 由 TeleBox 自身执行。工作台每日消息继续按时间运行。
- 本轮新增或调整了任务来源与旧定时作业测试；离线测试及构建结果以本轮 PR 检查为准。真实 Telegram 插件运行仍需目标服务器验证。

- 静态验证：TeleBox `npx tsc --noEmit`、前端 `npm run typecheck`、250 项 Vitest 与生产构建通过；后端 29 项相关测试通过，改动文件 Ruff 与 `git diff --check` 通过。未在此环境登录真实 Telegram 账号或运行目标服务器的插件命令。

## Trellis 文档对齐（2026-10-03）

- PR #17 已合并到 `main`（合并提交 `427b87a`）。发现需求和进度已记录最新行为，但设计、实施清单、前端状态规范及后端测试命令仍有旧任务/旧页面描述。
- 对齐 `prd.md` 的权威需求、`design.md` 的当前运行边界和 `implement.md` 的最新清单；更新任务元数据及前后端规范，明确聊天中心开关、777000、群对话、5 MiB 缓存、账号代理、命令来源、插件原生 cron 与工作台每日消息的关系。此前进度作为历史记录保留。
- 当前任务仍为 `in_progress`：Docker 构建、真实 Telegram 授权、已安装插件发现与执行、官方验证码模式和每日发送尚须在目标环境核验。此文档对齐不涉及应用代码，也不声称完成这些验收。

## 面板视觉与 2 GiB 资源收敛（2026-10-03）

- 根据用户参考图调整账号卡片：放大左上头像，名称及备注纵向排列，全部原有操作放入右上三点菜单；保留状态、搜索、批量检测、增删改与确认交互。深蓝侧栏可在桌面收起为彩色图标，移动抽屉保持原逻辑。全局浅色和暗色表面改为有层级的冷色调。
- 删除空闲时对所有路由 chunk 的预热，保留交互时按需预取；头像下载并发 4→2，单图不超过 128 KiB、浏览器页内总量不超过 2 MiB，移除账号和离开页面时回收 Object URL。
- 每个 TeleBox 工作进程 V8 老生代默认上限从 512→128 MiB，`TELEBOX_NODE_HEAP_MB` 可在 64–512 间设置；这不是总进程 RSS 上限。20 个账号能否在 2 GiB 下同时启用 TeleBox，仍需服务器观察内存和插件工作量。
- 离线验证：前端类型检查、251 项 Vitest 和生产构建通过；TeleBox 桥接 4 项 Python 测试、改动 Python 文件 Ruff、Git whitespace 检查通过。无已授权的浏览器/Telegram/Docker 环境，真实页面视觉与 20 账号内存实测尚未完成。
