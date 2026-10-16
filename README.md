<p align="center"><img src="docs/public/logo.svg" width="80" height="80" alt="TG Manage 图标"></p>
<h1 align="center">🚀 TG Manage</h1>
<p align="center">一个清爽的 Telegram 多账号管理面板，内置独立运行的 TeleBox。</p>
<p align="center"><a href="README.md"><strong>简体中文</strong></a> · <a href="README_EN.md">English</a></p>
<p align="center"><a href="#whats-new">🆕 v2.5.0 更新</a> · <a href="#features">✨ 核心功能</a> · <a href="#quick-start">🚀 快速部署</a> · <a href="#guides">📚 使用指南</a> · <a href="#reference">🧰 技术参考</a></p>


> 本项目源于 [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse)，集成 [TeleBoxOrg/TeleBox](https://github.com/TeleBoxOrg/TeleBox)。当前项目源码位于 [hikling/TG-Manage](https://github.com/hikling/TG-Manage)；请从本仓库构建，上游镜像不包含这里的界面和集成改动。

<a id="whats-new"></a>
## 🆕 v2.5.0 有什么更新

- **Xray 订阅与每账号独立线路：**支持 HTTPS 主订阅和可选兜底订阅。每个账号优先独占一个健康节点，主订阅节点不足时使用兜底订阅，仍不足才直连；旧版手填 SOCKS5 不再控制连接。
- **线路自动检测与切换：**节点每 5 分钟检测，首次超时、连接失败、IP 定位失败或延迟超限后 1 分钟复检，连续两次异常自动换线。账号卡片显示出口国家、公网 IP 以及主订阅、兜底订阅或直连来源。
- **零点检测报告：**每天按系统时区 00:00 检测全部账号和线路；启用 Bot 通知时，再读取前 24 小时 Telegram 官方消息，汇总账号状态、线路来源和有无新消息，并转发消息详情。
- **明确的手动检测范围：**卡片检测只处理当前账号的 Telegram、TeleBox 和出口 IP；批量检测处理所选账号，并清理服务器孤立账号及 TeleBox 数据。两者都不会读取官方消息或触发零点报告。
- **登录、授权与迁移：**支持手机验证码、二维码和二步验证；验证码页展示 Telegram 实际送达方式与重发倒计时。可用密码加密的 `.tglogin` 文件导出、导入主账号授权。
- **私人 Bot 按需取码：**使用 `/me` 查看账号编号，再用 `/code 编号` 或 `/code 账号名` 查询最近 5 分钟验证码；空闲时不会扫描账号消息。
- **界面与长期运行优化：**移除重复检测、单账号日志、TeleBox 运行日志和手动保活入口；限制节点探测、头像加载与日志缓冲规模，并修正版本显示和更新判断。

功能边界、切换时序、迁移注意事项和验证范围见 **[v2.5.0 完整更新说明](docs/releases/v2.5.0.md)**。

<a id="features"></a>
## ✨ 核心功能

<table>
  <tr>
    <td valign="top" width="50%">
      <h3>👥 多账号管理</h3>
      <p>支持验证码、二维码和二步验证登录，并可用加密 <code>.tglogin</code> 文件迁移主账号授权。</p>
    </td>
    <td valign="top" width="50%">
      <h3>🌐 Xray 独立线路</h3>
      <p>每个账号优先独占健康节点，按主订阅、兜底订阅、直连的顺序自动分配。</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>🔄 自动故障切换</h3>
      <p>定时检测延迟、连通性和出口 IP；连续两次异常自动换线，恢复稳定后再回切。</p>
    </td>
    <td valign="top" width="50%">
      <h3>🩺 分级状态检测</h3>
      <p>卡片单检只处理当前账号；手动批检可检查所选账号并清理服务器孤立数据。</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>📨 每日零点报告</h3>
      <p>每天 00:00 检查全部账号和线路，并通过 Bot 汇总前 24 小时的官方消息。</p>
    </td>
    <td valign="top" width="50%">
      <h3>🤖 私人 Bot 取码</h3>
      <p>使用 <code>/me</code> 查看账号编号，再用 <code>/code 编号</code> 或账号名按需查询验证码。</p>
    </td>
  </tr>
  <tr>
    <td valign="top" width="50%">
      <h3>🔌 独立 TeleBox</h3>
      <p>每个账号使用独立会话、目录和进程；退出 TeleBox 不影响账号管理中的主授权。</p>
    </td>
    <td valign="top" width="50%">
      <h3>💬 聊天与面板工具</h3>
      <p>提供可选聊天中心、主题与封面、TOTP、备份升级，以及有边界的缓存和日志。</p>
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
2. **🌐 配置订阅：**在「设置 → 机场订阅」填写 HTTPS 主订阅，可选填兜底订阅并刷新。首次配置前账号网络保持「待配置」；每个健康节点只分配给一个账号，节点不足或全部失效时，多出的账号会明确标为直连。详见 [Xray 与订阅说明](docs/deploy/docker.md#机场订阅与-xray)。
3. **➕ 添加账号：**在「账号管理」选择验证码或二维码登录。普通账号可免填 API ID/Hash；启用 TeleBox 时，请填写该账号的专属 API ID/Hash，并按提示完成二步验证。
4. **🗂️ 按需使用：**账号卡片只检测当前账户的状态、TeleBox 和 IP；手动批量检测还会清理服务器孤立数据。每日 00:00 自动检测全部账户和过去 24 小时的官方消息，完成后按通知设置推送机器人。「聊天中心」打开后再启用聊天。
5. **💾 按需迁移登录：**在「账户管理 → 登录备份」手动导出、导入加密的 `.tglogin` 主账号会话。该文件不包含 TeleBox 或面板配置；跨服务器使用前先停止旧服务器，详见 [登录备份指南](docs/guide/account-login-backup.md)。

TeleBox 的插件和命令由 TeleBox 自身管理。内置系统插件随镜像提供；社区插件见 [TeleBox-Plugins](https://github.com/TeleBoxOrg/TeleBox-Plugins)，具体使用方式见 [`telebox/README.md`](telebox/README.md)。

<a id="guides"></a>
## 📚 使用与部署指南

- **📦 [Docker 部署与无损升级](docs/deploy/docker.md)** — 安装、检查、备份、回退与构建排查。
- **🧭 [快速入门](docs/guide/quick-start.md)** — 首次设置和账号接入。
- **🆕 [v2.5.0 完整更新说明](docs/releases/v2.5.0.md)** — 新功能、检测时序、迁移与验证范围。
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

