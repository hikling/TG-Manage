<p align="center"><img src="docs/public/logo.svg" width="80" height="80" alt="TG Manage 图标"></p>
<h1 align="center">TG Manage</h1>
<p align="center">Telegram 多账号管理面板，集成独立运行的 TeleBox。</p>
<p align="center"><strong>简体中文</strong> · <a href="README_EN.md">English</a></p>
<p align="center"><a href="#whats-new">2.5.1 更新</a> · <a href="#features">功能</a> · <a href="#quick-start">部署</a> · <a href="#bot-web">机器人入口</a> · <a href="#docs">文档</a></p>

> 源自 [Silentely/TG-SignPulse](https://github.com/Silentely/TG-SignPulse)，并集成 [TeleBoxOrg/TeleBox](https://github.com/TeleBoxOrg/TeleBox)。请从本仓库 [hikling/TG-Manage](https://github.com/hikling/TG-Manage) 构建；上游镜像不包含本项目的界面与集成改动。

<a id="whats-new"></a>
## 2.5.1 更新

| 功能 | 现在的行为 |
| --- | --- |
| 每日订阅刷新 | 按面板时区每天 00:00 拉取主订阅和兜底订阅，更新节点并统计可用及不可用/不支持的数量。常规订阅刷新与节点健康检查仍会运行。 |
| 账户异常恢复 | 零点检测发现账户异常时先复检；仍异常且适合换线时，尝试可用的其他出口 IP 节点并再次检测。最终结果和恢复动作写入日报。 |
| 合并零点日报 | 账户状态、过去 24 小时的 Telegram 官方消息与机场订阅节点统计合并推送；账户部分在前、节点部分在后，两处标题加粗。消息过长时会分段发送；官方消息详情仍可单独转发。 |
| 机器人“打开WEB” | 给通知设置中指定的私人目标 ID 配置聊天菜单入口。该用户从 Telegram 打开面板时使用 Telegram 签名自动验证；其他 ID 不会获得面板授权，也不能使用该机器人的私人命令。 |

详细变化与升级检查见 [v2.5.1 更新说明](docs/releases/v2.5.1.md)。

<a id="features"></a>
## 功能一览

- **多账号与授权：**手机号验证码、二维码及二步验证登录；支持用密码加密的 <code>.tglogin</code> 文件迁移主账号会话。
- **独立线路：**内置 Xray，支持 HTTPS 主订阅和可选兜底订阅。每个账号优先独占健康节点；节点不足时按主订阅、兜底订阅、直连的顺序分配。
- **检测与换线：**定时检查节点连通性、延迟和出口 IP；异常复检后换线，稳定后回切。账号卡片显示国家、公网 IP 和线路来源。
- **每日汇总：**零点刷新订阅、复检异常账户并推送账户、官方消息与节点合并日报。卡片单检和手动批检范围见 [v2.5.0 说明](docs/releases/v2.5.0.md)。
- **私人通知机器人：**向指定目标发送通知；支持 <code>/me</code> 查看账号编号、<code>/code 编号</code> 或账号名按需获取最近 5 分钟验证码，并提供“打开WEB”入口。
- **TeleBox 与面板：**每账号独立 TeleBox 会话和进程；另有可选聊天中心、TOTP、主题、备份与升级工具。

<a id="quick-start"></a>
## 快速部署

准备 Docker Engine、Compose v2 和 Git。小型部署最低支持 1 vCPU / 1 GiB RAM；账号和插件较多时请按负载扩容。服务器需要能访问 Telegram 及构建依赖。

~~~bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
bash scripts/install.sh
~~~

安装脚本会构建并启动服务，输出一次性设置码。访问 <code>http://服务器IP:8080</code>，用设置码创建至少 12 位的管理员密码；对外开放前配置 [HTTPS 反向代理](docs/deploy/nginx.md)。

**已有部署升级**：在原仓库目录运行以下命令。脚本会先备份，再快进拉取、重建并启动。

~~~bash
bash scripts/update.sh
docker compose ps
docker compose logs --tail=100 app
~~~

请保留完整的 <code>data/</code>，包括隐藏文件 <code>data/.app_secret_key</code>、数据库、账号会话和 TeleBox 数据。不要重新初始化或删除数据。手动升级、备份及回退步骤见 [Docker 部署指南](docs/deploy/docker.md)。

## 首次配置

1. 在“设置 → 机场订阅”填入 HTTPS 主订阅，可选填兜底订阅并刷新。首次配置前，账号线路显示“待配置”。
2. 在“账号管理”通过验证码或二维码添加账号。普通账号可免填 API ID/Hash；使用 TeleBox 时按界面提示为该账号填写专属凭据。
3. 在“设置 → Telegram 机器人通知”配置 Bot Token 与私人目标 ID，并按需启用通知和“打开WEB”。
4. 如需跨服务器迁移主账号授权，使用“账号管理 → 登录备份”导出/导入加密 <code>.tglogin</code>；它不包含 TeleBox 或面板配置。

<a id="bot-web"></a>
## 机器人“打开WEB”

这个入口使用**通知设置里的同一个机器人**，与 TeleBox 插件无关。启用前需要：

- 已配置 Bot Token；“目标 ID”为**正整数的私人 Telegram 用户 ID**，不能是群组或频道 ID。
- 面板有可从 Telegram 访问的 **HTTPS 根地址**，并在通知设置中填写，例如 <code>https://example.com</code>。保存后系统会为目标私聊设置“打开WEB”菜单；设置页会提示菜单同步结果。
- 目标用户先与机器人建立私聊，再从该私聊左下角菜单打开。Telegram 提供短时签名，后端核对签名和目标 ID 后自动登录面板。

只有配置的目标 ID 能使用该入口；启用私人取码功能后，也只有该 ID 能使用 <code>/me</code> 和 <code>/code</code>。更换 Bot Token、目标 ID 或 Web 地址后，原入口授权会失效。公开网址仍可能被任何人访问，但不会因此获得面板登录权限；普通网页访问继续走管理员登录。请妥善保护 Bot Token 和管理员凭据。

## 零点日报

每天按**面板配置的时区**运行，顺序为：刷新主/兜底订阅 → 检测全部账户，异常时复检并尝试换线 → 查询过去 24 小时官方消息 → 推送合并摘要。通知内容大致如下：

~~~text
零点账户状态与官方消息日报
总计 2 · 正常 1 · 异常 1
🟢 @account_a — 账户正常 · 主订阅 · 无官方新消息
🔴 @account_b — 账户异常（...） · 兜底订阅 · 有官方新消息 · 换线复检后仍异常

零点机场订阅节点报告
主订阅（已刷新）：可用 ... · 不可用/不支持 ...
兜底订阅（已刷新）：可用 ... · 不可用/不支持 ...
~~~

实际推送中两个标题会**加粗**。如果刷新或检测失败，日报会说明失败或沿用的节点状态，不会把旧数据误写成此次刷新成功。合并摘要过长时可能分段，官方消息详情仍按通知流程单独发送。

<a id="docs"></a>
## 文档

- [v2.5.1 更新说明](docs/releases/v2.5.1.md) · [v2.5.0 功能与检测时序](docs/releases/v2.5.0.md)
- [Docker 部署、升级与回退](docs/deploy/docker.md) · [Nginx HTTPS](docs/deploy/nginx.md)
- [快速入门](docs/guide/quick-start.md) · [账号登录备份](docs/guide/account-login-backup.md)
- [配置参考](docs/reference/configuration.md) · [本地开发](docs/reference/development.md) · [TeleBox](telebox/README.md)

<details>
<summary>数据、配置与开发参考</summary>

Compose 将宿主机 <code>./data</code> 挂载到容器 <code>/data</code>。数据库、账号会话、设置、日志、TeleBox 数据、自定义封面和 <code>data/.app_secret_key</code> 都需随目录备份。密钥丢失会导致已加密的凭据和 Bot Token 无法解密；外部 PostgreSQL 数据库需另外备份。

常用环境变量：<code>TG_MANAGE_TG_API_ID/HASH</code>、<code>APP_SECRET_KEY</code>、<code>APP_DATA_DIR</code>、<code>APP_DATABASE_URL</code>、<code>TG_GLOBAL_CONCURRENCY</code>。旧别名 <code>SIGNPULSE_TG_API_ID/HASH</code> 与 <code>TG_API_ID/HASH</code> 仍可读取。完整选项以 [配置参考](docs/reference/configuration.md) 和 [后端配置](backend/core/config.py) 为准。不要将真实密钥、会话、Bot Token 或备份提交到 Git。

源码开发需 Python 3.10–3.13、前端 Node 22.23.1 和 TeleBox Node 24。检查命令：

~~~bash
python3 -m ruff check backend tg_manage tests
python3 -m pytest -q
cd frontend && npm run typecheck && npm test && npm run build
cd ../telebox && npx tsc --noEmit
~~~

真实 Telegram 登录、Bot API 和 Docker 构建仍需在部署环境验证。TeleBox 保留 [LGPL-2.1-only 许可证](telebox/LICENSE)，项目其他部分见 [LICENSE](LICENSE)。

</details>
