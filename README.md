<p align="center"><img src="docs/public/logo.svg" width="80" height="80" alt="TG-SignPulse Logo"></p>
<h1 align="center">TG-SignPulse</h1>
<p align="center">Telegram 多账号管理面板 · 内置 TeleBox</p>

> 本仓库是基于 [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse) 的二次开发版本。请务必从**本仓库源码**构建；上游 `ghcr.io/silentely/tg-signpulse` 镜像不包含这里的页面、聊天中心和 TeleBox 集成。

## 目录

- [本次更新](#本次更新)
- [运行环境](#运行环境)
- [Docker Compose 搭建](#docker-compose-搭建推荐)
- [首次使用](#首次使用)
- [本地源码开发](#本地源码开发)
- [环境变量](#环境变量)
- [数据、升级与备份](#数据升级与备份)
- [验证与已知限制](#验证与已知限制)
- [项目结构与开发规范](#项目结构与开发规范)

## 本次更新

| 范围 | 当前实现 |
| --- | --- |
| 管理页面 | 参照提供的截图重做导航、账号卡片、内容面板、浅色/深色主题与移动端布局；保留仪表盘、账号、任务、日志、设置等入口。 |
| 账号与聊天 | 账号管理支持手机验证码/二维码登录、状态检测、代理及登录时启用 TeleBox；聊天中心开启后按账号查看群组对话，显示 Telegram 头像、搜索/翻页、收发文字与附件、回复、编辑/删除消息、已读及归档等。 |
| 账号工作台 | 选择账号与目标群聊执行消息操作，并创建每日定时消息。 |
| 机器人、代理 | 机器人中心提供 Bot Token 接入及资料/命令/消息管理；账号代理可在账号资料中设置，系统设置不再有独立代理管理卡片。群会话保留在聊天中心与账号工作台，不提供单独的群聊管理。Bot Token 在服务端加密存储。 |
| 任务编排与日志 | 旧签到动作与关键词监听不再运行；任务编排只选择 KITT 和当前账号新安装插件的已加载命令，可手动执行；插件自身定时由 TeleBox 管理。工作台的每日消息继续由面板调度。全局 AI 模型与 Telegram API 配置入口已移除。 |
| 内置 TeleBox | 保留 TeleBox 0.2.9 的上游源码、内置插件和 TPM；登录账号时选择启用并自动请求独立会话，拓展插件页查看状态、插件和日志。上游固定提交见 [`telebox/UPSTREAM.json`](telebox/UPSTREAM.json)。 |
| 清理旧功能 | 移除原 Python 自定义插件系统、插件市场/调试入口及其“自定义插件动作”；移除独立频道管理页。聊天中心聚焦群组对话。旧任务数据不自动删除，包含旧插件动作的任务要人工检查并迁移。 |
| 开发流程 | 接入 Trellis 的任务记录、后端/前端规范、Codex 技能与 hooks；搭建过程见 [bootstrap 记录](.trellis/tasks/00-bootstrap-guidelines/progress.md)。 |

**模块边界：**TeleBox 是另一套独立 Telegram 会话与插件运行时。定时任务的插件动作向当前账号的 TeleBox 已加载命令投递一条“收藏夹”消息；任务成功表示命令已投递，插件内部执行结果需看 TeleBox 日志。不要把两个进程的 session 文件手工合并。

## 运行环境

| 项目 | Docker Compose（推荐） | 不使用 Docker 时 |
| --- | --- | --- |
| 系统 | 支持 Docker Engine 和 Compose v2 的 Linux；Windows/macOS 可使用 Docker Desktop | 建议 Linux；macOS/Windows 建议先使用 Docker，TeleBox 运行时依赖原生模块和 POSIX 文件锁 |
| Docker | 建议 Engine 24+、`docker compose` v2 | 不需要 |
| Python | 镜像内 Python 3.11 | Python >=3.10,<3.14，推荐 3.11/3.12 |
| 前端 Node | 构建阶段 Node 22.23.1 | Node 22.23.1，见根目录 `.nvmrc` |
| TeleBox Node | 构建/运行阶段 Node 24 | 另外安装 Node 24.x，并用 `TELEBOX_NODE` 指定可执行文件 |
| 资源 | 当前 `docker-compose.yml` 设置 2 GiB 容器内存与 2 CPU；构建时还需要额外内存和磁盘 | 每增加一个运行中的 TeleBox 账号都会启动一个独立 Node 进程；按账号数量预留内存 |

面板的头像下载并发为 2，单张只在不超过 128 KiB 时保存在浏览器，本页头像 URL 总量最多 2 MiB，离开页面即释放；界面只按需加载页面模块。每个 TeleBox Node 工作进程的 V8 老生代默认上限为 128 MiB，可通过 `TELEBOX_NODE_HEAP_MB` 在 64–512 MiB 间调整。这不是进程 RSS 上限；20 个账号若都同时启用 TeleBox，2 GiB 容器能否承载取决于实际插件和连接开销，须在目标服务器逐步启用并观察内存，不能按堆上限相加保证容量。
| 网络与账号 | 能访问 Telegram、npm/PyPI（构建时）；至少一个可完成验证的 Telegram 账号 | 同左；受限网络需先配置 Telegram 代理 |
| Telegram API | 启用 TeleBox 的账号登录时填写专属 API ID/Hash；不启用时从服务器私有 `.env` 读取 `SIGNPULSE_TG_API_ID/HASH` | 同左；Telegram 登录无论是否启用 TeleBox 都需要一组有效应用凭据 |

TeleBox 插件可能需要自己的外部服务配置；其插件清单在“拓展插件”按账号显示。

## Docker Compose 搭建（推荐）

服务器已安装 Docker Engine 和 Compose v2、Git，并拥有此私有仓库的读取权限后，复制这一行执行：

```bash
git clone https://github.com/hikling/TG-SignPulse-Private.git && cd TG-SignPulse-Private && bash scripts/install.sh
```

脚本从源码构建并启动服务、等待就绪、输出首次设置码。私有仓库克隆会要求 GitHub 授权；服务器也必须能下载 Python/npm 构建依赖并连接 Telegram。打开 `http://服务器IP:8080`，粘贴设置码并自行设定至少 12 位管理员密码。`APP_SECRET_KEY` 首次启动生成到 `data/.app_secret_key`，以后自动复用。已有管理员不会重置密码，也不会显示设置码。公开访问前应配置 [HTTPS 反向代理](docs/deploy/nginx.md)。

脚本调用 `docker compose up -d --build`；查看运行状态用 `docker compose ps`，日志用 `docker compose logs --tail=100 app`。首次构建 TeleBox 的原生模块可能较久。TeleBox 的 `package-lock.json` 必须随仓库提交；若构建报 `npm ci` 缺少锁文件，先更新包含锁文件修复的版本，参见 [构建排查](docs/deploy/docker.md#telebox-构建提示-npm-ci-缺少锁文件)。

### 停止与重启

```bash
docker compose stop       # 暂停服务，保留容器和数据
docker compose start      # 恢复
docker compose down       # 删除容器和网络，保留 ./data
docker compose up -d --build  # 代码更新后重新构建
```

不要删除 `./data`；这里包含数据库、账号会话和 TeleBox 每账号数据。

## 首次使用

1. 首次打开网页，填入安装脚本输出的设置码，自行设置 `admin` 密码；完成后设置码失效。已有部署用原账号登录。建议启用面板 TOTP。
2. 在“账号管理”选择是否启用 TeleBox。勾选时填写该账号 API ID/Hash；不勾选时使用服务器私有 `.env` 中的应用凭据，网页登录无需重复填写。两种方式都通过验证码或二维码授权 Telegram；缺少任何可用 API 凭据时登录会明确报错。
3. 启用 TeleBox 的账号在登录成功后自动申请**独立的新 Telegram 会话**。在“拓展插件”查看状态；如要求两步验证密码，在这里填写。若失败，状态和日志显示失败阶段及脱敏错误，再检查网络、授权、依赖与代理。
4. 左侧“聊天中心”始终可进入，在页面内选择是否开启聊天。关闭时该页只读取 Telegram 官方验证码消息 `777000`；开启后显示群组对话。聊天缓存超过 5 MB 会强制清理。头像从 Telegram 读取；无照片时显示文字占位。发送、删除、编辑消息会触发真实 Telegram 请求；群聊会话也在这里展示，没有单独的群聊管理页面。账号工作台可多选操作账号和共有群，发送消息或创建每日任务。
5. 在“任务编排”点击添加任务后自动识别运行账号已加载的 TeleBox 插件命令。该账号需处于运行中；仅显示 KITT 和新安装插件命令。插件任务不设置每日执行时间，可手动执行，插件自身定时由 TeleBox 管理。任务日志记录投递，插件详细输出在“日志”→“TeleBox 日志”。旧 Python 插件动作不会自动迁移。

每个账号的 TeleBox 数据独立保存在 `data/telebox/` 的散列目录中，不能共用同一个工作目录。TeleBox 上游命令/插件仍受其自身许可及运行规则约束，详见 [`telebox/README.md`](telebox/README.md)。

## 本地源码开发

Docker 是部署首选。本地开发需要**两个 Node 版本**和 Python；下面以 Linux/macOS 的 shell 为例。Windows 推荐 WSL2 或 Docker。

```bash
# 1. 环境与 Python 依赖，仓库根目录
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'

# 2. 前端依赖：切换到 Node 22.23.1
nvm install 22.23.1
nvm use 22.23.1
cd frontend && npm ci && cd ..

# 3. TeleBox 依赖：切换到 Node 24
nvm install 24
nvm use 24
cd telebox && npm ci --include=dev && cd ..
```

`canvas`、`better-sqlite3` 等 Node 原生模块在 Linux 上可能需要 Python、C/C++ 工具链及 Cairo/Pango/JPEG/GIF 开发包；准确的 Debian 包清单在 [`Dockerfile`](Dockerfile) 的 `telebox-builder` 阶段。Node 版本必须与安装依赖时使用的 ABI 匹配。不要从 `telebox/` 单独再启动一个共用账号的服务进程。

本地开发建议设置 `APP_DATA_DIR=./data`，也可不设置而使用程序默认数据目录。不启用 TeleBox 且希望登录时免填凭据，可在本地进程私有环境设置 `SIGNPULSE_TG_API_ID/HASH`；不要提交这些值。启动后端前执行：

```bash
export APP_DATA_DIR=./data
export TELEBOX_NODE="$(command -v node)"  # 此时应指向 Node 24
uvicorn backend.main:app --host 127.0.0.1 --port 8080
```

另开终端运行前端（确保使用 Node 22.23.1）：

```bash
nvm use 22.23.1
cd frontend
npm run dev
```

Vite 开发服务默认在 `http://localhost:5173`，`/api` 代理到 `127.0.0.1:8080`。前端和 TeleBox 的 Node 主版本不同；切换 nvm 后，已启动的后端必须继承指向 Node 24 的 `TELEBOX_NODE`。本地静态构建使用 `cd frontend && npm run build`。

## 环境变量

| 变量 | 用途 | 当前默认/来源 |
| --- | --- | --- |
| `SIGNPULSE_TG_API_ID/HASH` | 不启用 TeleBox 时的服务器私有应用凭据；Compose 从未提交的 `.env` 注入 | 可选；若未配置，登录表单需提供一组 API 凭据 |
| 账号 API ID/Hash | 启用 TeleBox 时在手机/扫码登录表单输入，登录成功后加密保存在账号记录 | 旧账号如未保存专属凭据需重登 |
| `APP_SECRET_KEY` | JWT、Bot Token、账号凭据加密根密钥 | 自动持久化在 `data/.app_secret_key`；备份并保持原值 |
| 初次管理员密码 | 在网页首次设置，服务端一次性设置码见安装脚本输出 | 既有账号保持原密码 |
| `APP_DATA_DIR` | SQLite、session、任务、日志、TeleBox 持久数据目录 | Compose 为 `/data`；本地建议 `./data` |
| `PORT` | Docker 入口脚本监听端口 | Compose 为 `8080` |
| `APP_PORT` | Python Settings 默认端口（直接用 uvicorn 启动时显式 `--port` 覆盖） | `3000` |
| `TZ` / `APP_TIMEZONE` | 时区，任务显示和调度相关 | Compose 为 `Asia/Shanghai`；代码默认 `Asia/Hong_Kong` |
| `TG_SESSION_MODE` | Telegram session 文件或 string 模式 | 默认 `file` |
| `TG_PROXY` | Telegram 全局代理（也可在面板设置） | 未设置 |
| `APP_DATABASE_URL` | 覆盖默认 SQLite，可配置 SQLAlchemy 数据库 URL | 默认 SQLite `data/db.sqlite` |
| `APP_CORS_ALLOW_ORIGINS` | 分离部署的前端来源列表，逗号分隔 | 默认 localhost 开发来源 |
| `LOG_LEVEL` | 服务日志等级 | Compose 为 `INFO` |
| `TELEBOX_NODE` | 本地指定 Node 24 可执行文件；Docker 镜像内 Node 24 已就绪 | 默认查找 `node` |
| `TELEBOX_NODE_HEAP_MB` | 每个 TeleBox Node 进程的 V8 老生代上限，限制在 64–512 MiB | 默认 128 MiB，非进程总内存上限 |
| `ENABLE_API_DOCS` | 开启 Swagger/ReDoc/OpenAPI | 默认关闭 |

实际可配置项还见 [`backend/core/config.py`](backend/core/config.py) 与 [本地配置参考](docs/reference/configuration.md)。不要将真实 API ID、API Hash、密码、session、Bot Token 或导出的数据写进 README、`.env.example` 或 Git。

## 数据、升级与备份

- Compose 将宿主机 `./data` 挂载到容器 `/data`。主库、账号会话、签到数据、日志和 TeleBox 状态均依赖此目录；迁移服务器时应备份整个 `data/`（包括 `.app_secret_key`）。面板的完整/WebDAV/自动备份现在也包含加密根密钥与 TeleBox 账号数据，备份文件包含可恢复敏感凭据，须限制访问。
- 更新前停服务、备份 `data/`，再从**这个私有仓库**获取新代码并执行 `docker compose up -d --build`。不要从上游镜像覆盖本二改版本。
- 恢复时先还原完整数据目录（含密钥文件），再启动；账号是否需要重新登录取决于 Telegram session 的实际有效性。不要向公共仓库上传备份包。
- Dockerfile 在 Python 镜像内嵌入 Node 24 与 TeleBox 依赖；前端使用 Node 22 单独构建。Compose 开启只读根文件系统、`/tmp` 临时卷和 2 GiB 内存限额，`data/` 必须可写。更多见 [Docker 部署指南](docs/deploy/docker.md)。

## 验证与已知限制

### 本地自动检查

```bash
python3 -m ruff check backend tg_signer tests
# 测试文件见 tests/；运行全量 pytest 会执行 pyproject.toml 的覆盖率检查
python3 -m pytest -q
cd frontend && npm run typecheck && npm test && npm run build
cd ../telebox && npx tsc --noEmit
```

前端类型检查、构建与针对性自动测试请以本次变更的检查结果为准；TeleBox TypeScript 检查还需运行。完整 Docker 构建与**真实 Telegram 账号**的验证码/扫码、TeleBox 独立授权、Bot API、TPM 远程安装仍需在你的部署环境验证。功能表说明的是代码实现范围，不代表真实账号端到端验收通过。

- TeleBox 需要额外账号会话和内存，运行多个账号时调高宿主机资源及 Compose 内存限额。
- 旧插件任务保留原数据，但对应动作不会继续运行；迁移前先备份。
- 当前 `docs/` 内保留部分上游功能文档；本二改版本以本 README、当前源码和本仓库的 Docker 指南为准。

## 项目结构与开发规范

```text
TG-SignPulse/
├── backend/              FastAPI API、账号/消息服务、TeleBox 进程管理
├── frontend/             Vue 3/Pinia/Tailwind 管理面板
├── tg_signer/            Kurigram/Pyrogram Telegram 自动化引擎
├── telebox/              固定版本 TeleBox 上游源码、插件与面板适配器
├── tests/                Python 测试
├── docs/                 用户和部署文档
├── .trellis/             任务、开发规范与进度 Markdown
├── .agents/skills/        Trellis 开发技能
├── .codex/               Codex hooks 与任务 agent 配置
├── Dockerfile            Node 22 → Node 24 → Python 多阶段构建
├── docker-compose.yml    本分支源码构建与持久化配置
└── .env.example          不含真实凭据的配置模板
```

开发前阅读 [`AGENTS.md`](AGENTS.md)、[后端规范](.trellis/spec/backend/index.md)、[前端规范](.trellis/spec/frontend/index.md) 和当前 [Trellis 任务记录](.trellis/tasks/10-02-telebox-panel/implement.md)。TeleBox 上游按 LGPL-2.1-only 授权，保留其原始 [`LICENSE`](telebox/LICENSE)；本项目其他部分见根目录 [`LICENSE`](LICENSE)。
