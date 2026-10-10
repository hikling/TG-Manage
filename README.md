<p align="center"><img src="docs/public/logo.svg" width="80" height="80" alt="TG Manage 图标"></p>
<h1 align="center">🚀 TG Manage</h1>
<p align="center">一个清爽的 Telegram 多账号管理面板，内置独立运行的 TeleBox。</p>
<p align="center"><a href="README.md"><strong>简体中文</strong></a> · <a href="README_EN.md">English</a></p>
<p align="center"><a href="#features">✨ 功能</a> · <a href="#quick-start">🚀 快速部署</a> · <a href="#guides">📚 使用指南</a> · <a href="#reference">🧰 技术参考</a></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-BSD--3--Clause-0b7285?style=flat-square" alt="BSD 3-Clause license"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%E2%80%933.13-3776AB?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10 to 3.13"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.109%2B-009688?style=flat-square&amp;logo=fastapi&amp;logoColor=white" alt="FastAPI 0.109 or later"></a>
  <a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue.js-3.5-42B883?style=flat-square&amp;logo=vuedotjs&amp;logoColor=white" alt="Vue.js 3.5"></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-6%20%7C%207-3178C6?style=flat-square&amp;logo=typescript&amp;logoColor=white" alt="TypeScript 6 and 7"></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-22%20%7C%2024-339933?style=flat-square&amp;logo=nodedotjs&amp;logoColor=white" alt="Node.js 22 and 24"></a>
  <a href="https://github.com/TeleBoxOrg/TeleBox"><img src="https://img.shields.io/badge/TeleBox-0.2.9-6f42c1?style=flat-square" alt="TeleBox 0.2.9"></a>
</p>

> 本项目源于 [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse)，集成 [TeleBoxOrg/TeleBox](https://github.com/TeleBoxOrg/TeleBox)。当前项目源码位于 [hikling/TG-Manage](https://github.com/hikling/TG-Manage)；请从本仓库构建，上游镜像不包含这里的界面和集成改动。

<a id="features"></a>
## ✨ 核心功能

<table>
  <tr>
    <td valign="top" width="50%">
      <h3>👥 多账号管理</h3>
      <p>支持手机验证码或二维码登录，按需检测账号、刷新头像和配置代理。单检与批检共用每个账号成功后 45 秒的检测间隔。</p>
    </td>
    <td valign="top" width="50%">
      <h3>💬 聊天中心</h3>
      <p>按账号浏览群组对话，支持搜索、收发附件、回复、编辑和删除消息。聊天能力可以独立开启或关闭。</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>🤖 私人机器人</h3>
      <p>配置的私人目标 ID 可用 <code>/code 账号名</code> 查询 <code>777000</code> 最近 5 分钟内的验证码，也可用 <code>/me</code> 查看本地账号名称和备注。两种命令共用 45 秒间隔，空闲时不扫描账号消息。</p>
    </td>
    <td valign="top" width="50%">
      <h3>🎨 仪表盘与外观</h3>
      <p>仪表盘提供封面、账号管理和刷新入口。主题色与自定义封面同步保存到服务器，封面支持位置调整、恢复默认和 1 MiB 上传限制。</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>🔌 内置 TeleBox</h3>
      <p>每个启用的账号使用独立 Telegram 会话和运行目录，可在账号卡片查看状态、日志并启动、停止或退出登录。上游版本见 <a href="telebox/UPSTREAM.json"><code>telebox/UPSTREAM.json</code></a>。</p>
    </td>
    <td valign="top" width="50%">
      <h3>🔐 独立会话边界</h3>
      <p>退出 TeleBox 只清除它的独立授权，不会退出账号管理中的主账号。两套 session 文件必须保持独立。</p>
    </td>
  </tr>
</table>


<a id="quick-start"></a>
## 🚀 快速部署

小型部署最低支持 1 vCPU / 1 GiB RAM，项目没有固定的配置上限；按账号数量和实际负载扩容。准备好 Docker Engine、Compose v2 和 Git，确保服务器可以访问 Telegram 及构建依赖，然后运行：

```bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
bash scripts/install.sh
```

安装脚本会从本仓库源码构建、启动服务并输出一次性设置码。打开 `http://服务器IP:8080`，输入设置码并设置至少 12 位的管理员密码。对外开放前请配置 [HTTPS 反向代理](docs/deploy/nginx.md)。

> **⚠️ 已有部署升级时不要重新初始化或删除数据。**在原仓库目录运行 `bash scripts/update.sh`；脚本会先备份，再快进拉取、重建并启动。务必保留完整的 `data/`，包括隐藏文件 `data/.app_secret_key`、数据库、账号会话和 TeleBox 数据。详情见下方「数据、升级与备份」。

<a id="first-use"></a>
## 🧭 首次使用

1. **🔐 设置管理员：**使用安装时显示的一次性设置码；已有部署仍用原账号登录，建议启用面板 TOTP。
2. **➕ 添加账号：**在「账号管理」选择验证码或二维码登录。普通账号可免填 API ID/Hash；启用 TeleBox 时，请填写该账号的专属 API ID/Hash，并按提示完成二步验证。
3. **🗂️ 按需使用：**账号卡片可检测状态和刷新头像，也可管理独立的 TeleBox 进程。「聊天中心」打开后再启用聊天；关闭时仅处理官方验证码消息。

TeleBox 的插件和命令由 TeleBox 自身管理。内置系统插件随镜像提供；社区插件见 [TeleBox-Plugins](https://github.com/TeleBoxOrg/TeleBox-Plugins)，具体使用方式见 [`telebox/README.md`](telebox/README.md)。

<a id="guides"></a>
## 📚 使用与部署指南

- **📦 [Docker 部署与无损升级](docs/deploy/docker.md)** — 安装、检查、备份、回退与构建排查。
- **🧭 [快速入门](docs/guide/quick-start.md)** — 首次设置和账号接入。
- **⚙️ [配置参考](docs/reference/configuration.md)** — 环境变量与数据目录。
- **🛠️ [本地开发](docs/reference/development.md)** — 源码运行和开发命令。

<a id="reference"></a>
## 🧰 技术参考

以下内容默认收起，需要时点击展开。

<a id="environment"></a>
<details>
<summary><strong>⚙️ 环境变量</strong></summary>

| 变量 | 用途 |
| --- | --- |
| `TG_MANAGE_TG_API_ID/HASH` | 可选的服务器私有 Telegram 应用凭据；普通账号可免填，启用 TeleBox 时应使用账号专属凭据。 |
| `SIGNPULSE_TG_API_ID/HASH`、`TG_API_ID/HASH` | 旧部署兼容别名，升级后仍可读取。 |
| `APP_SECRET_KEY` | 凭据加密和认证密钥；默认持久化为 `data/.app_secret_key`，必须随数据备份。 |
| `APP_DATA_DIR` | 数据库、会话、日志及 TeleBox 数据目录；Compose 使用 `/data`。 |
| `TG_PROXY` | Telegram 全局代理；账号代理也可在界面中单独设置。 |
| `APP_DATABASE_URL` | 覆盖默认 SQLite 数据库连接。 |
| `TG_GLOBAL_CONCURRENCY` | Telegram 操作的并发上限，与已登录账号总数无关。 |
| `TELEBOX_NODE` | 本地开发时指定 TeleBox 使用的 Node 24 可执行文件。 |

完整选项和默认值以 [`backend/core/config.py`](backend/core/config.py) 及 [配置参考](docs/reference/configuration.md) 为准。不要把真实密钥、session、Bot Token 或备份提交到 Git。

</details>

<a id="data-upgrade-backup"></a>
<details>
<summary><strong>💾 数据、升级与备份</strong></summary>

Compose 把宿主机 `./data` 挂载到容器 `/data`。数据库、账号会话、设置、日志、TeleBox 每账号目录、自定义封面及 `data/.app_secret_key` 均在其中。旧部署的封面也可能位于 `data/.signer/appearance/`。**保留整个目录及隐藏文件**；密钥丢失会导致已加密的账号凭据和 Bot Token 无法解密。

在现有仓库目录升级：

```bash
bash scripts/update.sh
```

该脚本调用 `scripts/backup.sh` 将完整数据目录归档到 `backups/`，然后执行 `git pull --ff-only` 并重新构建启动。它不会自动清理旧备份。自定义数据目录必须先确认 `APP_DATA_DIR` 与 Compose 挂载源一致；外部 PostgreSQL 数据库还需单独备份。手动升级和回退见 [Docker 部署指南](docs/deploy/docker.md#无损升级与回退)。

恢复时先停止服务，再还原完整数据目录，最后启动并核对账号、会话和设置。备份含敏感凭据，不要上传公共仓库。TeleBox 核心代码可随项目更新，用户插件、配置和独立会话应保留。

</details>

<a id="verification-limitations"></a>
<details>
<summary><strong>🧪 验证与已知限制</strong></summary>

本地自动检查：

```bash
python3 -m ruff check backend tg_manage tests
python3 -m pytest -q
cd frontend && npm run typecheck && npm test && npm run build
cd ../telebox && npx tsc --noEmit
```

真实 Telegram 账号的验证码或扫码、TeleBox 独立授权、Bot API、远程插件安装及完整 Docker 构建，仍需在自己的部署环境验证。旧任务数据仍可留存，但已移除的签到、监听和任务动作不会继续执行。运行 TeleBox 会增加独立进程和会话，部署时请按实际负载预留资源。

</details>

<a id="project-development"></a>
<details>
<summary><strong>🗂️ 项目结构与开发规范</strong></summary>

```text
TG-Manage/
├── backend/       FastAPI API、账号与消息服务
├── frontend/      Vue 3 管理面板
├── tg_manage/     Telegram 客户端与会话工具
├── telebox/       TeleBox 上游源码和集成适配
├── docs/          使用、部署与运维文档
└── tests/         后端测试
```

源码开发需 Python 3.10–3.13、前端 Node 22.23.1 和 TeleBox Node 24；Node 原生模块依赖见 [`Dockerfile`](Dockerfile)。本地 AI 工作流、技能与任务记录不随源码发布。TeleBox 保留其 [LGPL-2.1-only 许可证](telebox/LICENSE)，本项目其他部分见根目录 [`LICENSE`](LICENSE)。

</details>
