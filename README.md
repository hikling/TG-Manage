<p align="right">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

<h1 align="center">TG Manage</h1>

<p align="center">
  <em>面向自部署场景的 Telegram 多账号运维、代理路由与 TeleBox 管理面板</em>
</p>

<p align="center"><a href="#whats-new">🆕 v2.6.0 更新</a> · <a href="#features">✨ 核心功能</a> · <a href="#quick-start">🚀 快速部署</a> · <a href="#midnight-report">📨 零点日报</a> · <a href="#bot-web">🤖 打开 WEB</a> · <a href="#guides">📚 使用指南</a> · <a href="#reference">🧰 技术参考</a></p>

<p align="center">
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/Python-3.10--3.13-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Vue-3%20%2B%20FastAPI-42B883?logo=vuedotjs&logoColor=white" alt="Vue 3 and FastAPI">
  <img src="https://img.shields.io/badge/Release-v2.6.0-16a34a" alt="Release v2.6.0">
  <img src="https://img.shields.io/badge/License-BSD--3--Clause-0f766e" alt="License">
</p>

---

**TG Manage** 是面向个人与自部署运维的轻量级 Telegram 多账号控制面板，基于 FastAPI + Vue 3 构建，单容器即可管理多账号登录态、独立 Xray 代理线路、777000 官方通知/聊天中心、账号级 TeleBox 进程以及加密登录备份。

<a id="whats-new"></a>
## 🆕 v2.6.0 有什么更新

1. **全新卡牌式 UI 与视觉系统**：
   - **账号卡牌（Showcase Cards）**：账号卡片升级为 20 套循环多段炫丽渐变顶栏、大尺寸头像居中跨线排版、名字与备注分置分隔线上下；卡片中段精简展示 IP 定位与线路归属（主订阅 / 兜底 / 直连），底部直接集成 **TeleBox 启动/停止切换** 与 **检测状态** 按钮，移除冗余的卡片聊天入口并支持运行期 2FA 密码卡片内直输。
   - **主题与封面高度自定义**：外观设置新增 **仪表盘封面高度** 滑块（支持自定义调节与服务端持久化）、封面裁切焦点定位、自定义强调色预设以及双色模式精细适配。
   - **聊天中心独立收纳**：聊天中心统一从左侧主导航进入，保留账号筛选列表、777000 官方验证码一键提取收件箱，以及按需开启的完整会话/媒体管理。
2. **全仓安全审计与稳定性加固**：
   - **认证与输入防线**：阻断 Telegram WebApp 短时令牌访问管理员改密、改用户名与 2FA 变更接口；为登录缺失用户补齐 bcrypt 计时混淆；校验初始化与改密不超过 bcrypt 72 字节 UTF-8 上限；封堵订阅节点解析中的 NAT64 / IPv4-mapped / 本地保留地址 SSRF 绕过；清理通配符 CORS 与过时 TOTP 重放缓存漏洞。
   - **并发与生命周期修复**：为 `accounts.json` 读写/重命名加进程锁与顺序修复；修复账号重命名时头像与状态标记同步迁移；修正聊天中心 Naive 时间戳按本地时区转 UTC 的 8 小时偏差；修复 `Modal` 多层栈关闭顺序、`AddAccountModal` 异步竞态、`useToast` pause/resume 二次计时与账号路径 URL 编码问题；为 TeleBox worker 与 Docker entrypoint 补齐原子写入、符号链接检查与敏感文件权限加固。
3. **死代码与冗余依赖清理**：
   - 移除历史遗留任务表单/日志模型、过期 Pydantic v2 兼容垫片、未使用的前端日期/多选组件与数百条废弃样式及多语言键，并从 [pyproject.toml](pyproject.toml) 精简未使用的后端依赖。

完整发布说明见 **[v2.6.0 更新说明](docs/releases/v2.6.0.md)** 与 [CHANGELOG.md](CHANGELOG.md)；前期零点日报与订阅迁移规则可参考 [v2.5.1 更新说明](docs/releases/v2.5.1.md) 和 [v2.5.0 完整更新说明](docs/releases/v2.5.0.md)。

<a id="features"></a>
## ✨ 核心功能

- **多账号卡牌管理与会话备份**：支持手机号/验证码与扫码登录、加密 `.tglogin` 登录备份导入导出、离线头像缓存、在线设备查看与一键踢出下线。
- **Xray 主/兜底独占代理与测活**：导入主订阅与兜底订阅，每账号分配独占本地 SOCKS5 节点；连续两次异常切换备用，连续两次恢复切回主线；节点不足时剩余账号自动直连并标注出口 IP。
- **账号级 TeleBox 隔离运行**：每账号独立工作目录与加密会话，面板卡片一键启停与登出；内置标准输入帧式 IPC 通信，不共享 Pyrogram SQLite 文件，避免锁库冲突。
- **聊天中心与 777000 官方收件箱**：默认收敛在左侧菜单的聊天中心，未开启完整聊天时仍可按账号快速查看 777000 官方登录验证码并一键复制；开启后支持搜索群聊、收发/编辑/撤回消息及 20MB 内媒体上传下载。
- **零点合并日报与私人机器人**：每天 `00:00` 自动刷新订阅、复检并尝试自愈异常账户，向私人目标发送「账户与官方消息 + 节点统计」合并日报；支持在 Telegram 内通过 Bot 菜单短时免密打开 Web 面板，以及 `/me`、`/code` 指令查询。

<a id="quick-start"></a>
## 🚀 快速部署

服务器需安装 **Docker Engine 24+**、**Docker Compose v2** 与 **Git**，且具备拉取依赖与连接 Telegram 的网络环境。

### 方式一：安装脚本（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/hikling/TG-Manage/main/scripts/install.sh -o install.sh
bash install.sh
```

脚本会检查前置环境、准备数据目录与权限（`./data`），生成随机 `APP_SECRET_KEY`，并拉起容器。默认监听 `http://127.0.0.1:8080`；首次登录需从数据目录读取一次性初始化令牌后在网页设置管理员密码：

```bash
cat ./data/.admin_setup_token
```

### 方式二：手动 Docker Compose 部署

```bash
git clone https://github.com/hikling/TG-Manage.git
cd TG-Manage
APP_SECRET_KEY=$(openssl rand -hex 32)
echo "APP_SECRET_KEY=${APP_SECRET_KEY}" > .env
mkdir -p data/.tg_manage data/sessions data/logs data/plugins
docker compose up -d --build
```

### 升级与备份

已有部署同步 `main` 最新代码并重建镜像：

```bash
cd /root/TG-SignPulse-Private # 或你的部署目录
bash scripts/update.sh
```

数据备份与公网 Nginx 反向代理参考：[Docker 无损升级说明](docs/deploy/docker.md) · [Nginx 反向代理示例](docs/deploy/nginx.md) · [备份脚本](scripts/backup.sh)

<a id="midnight-report"></a>
## 📨 每日零点日报

启用私人 Telegram Bot 通知后，系统每日 `00:00`（按全局设置时区）自动执行一次完整巡检与汇报：

1. **刷新订阅并测活节点**：拉取主/兜底订阅，校验并更新各节点健康状态。
2. **账户自愈与状态复检**：对异常账户先执行一轮复检；若开启换线且存在其它可用出口节点，则自动尝试切换备用线路并复检，结果统一汇总。
3. **合并发送一条日报**：上半部分展示各账号健康状态、切换动作与近 24 小时 777000 官方消息摘要；下半部分汇总主/兜底订阅健康节点数、可用端口与分配情况。

<a id="bot-web"></a>
## 🤖 Telegram 机器人内「打开 WEB」

当你在 **系统设置 → Telegram Bot 通知** 中填入了 `Bot Token` 与单个数字 `目标 Chat ID` 并开启菜单开关，保存配置后：

1. 该私人聊天的机器人会注册 **「打开 WEB」** 菜单按钮。
2. 点击菜单后通过 Telegram `initData` HMAC-SHA256 签名校验，且仅放行配置的目标用户 ID，签发短时会话令牌直接免输入账号密码进入面板。
3. 为保障安全，通过 Telegram WebApp 登录的短时会话默认仅允许日常巡检与运维查看，无法修改管理员密码、用户名或 2FA 密钥。

> 请通过 HTTPS 域名访问面板，并在面板设置页正确配置外部可访问的 `PANEL_PUBLIC_URL`（或 `APP_PUBLIC_URL`）。详细说明见 [设备与 WebApp 安全参考](docs/reference/device-management.md)。

<a id="guides"></a>
## 📚 使用指南

- **[v2.6.0 更新说明](docs/releases/v2.6.0.md)** — 卡牌 UI 升级、安全修复清单与代码精简说明。
- **[v2.5.1 更新说明](docs/releases/v2.5.1.md)** — 零点合并日报、机器人 Web 入口与版本检查。
- **[v2.5.0 完整更新说明](docs/releases/v2.5.0.md)** — 主/兜底订阅架构、节点切换阈值与登录迁移。
- **[快速开始](docs/guide/quick-start.md)** — 部署前置条件、初次登录与账号添加。
- **[账号与线路管理](docs/guide/accounts.md)** — 卡牌状态、TeleBox 启停与 Xray 代理绑定。
- **[账号登录备份](docs/guide/account-login-backup.md)** — 加密 `.tglogin` 文件导出与跨机无损迁移。
- **[运维与排查](docs/reference/ops.md)** — 服务日志、版本检查与常见故障排查。
- **[全部功能](docs/features.md)** · **[配置参考](docs/reference/configuration.md)** · **[常见问题](docs/faq.md)**

<a id="reference"></a>
## 🧰 技术参考

- **后端栈**：Python 3.10–3.13 · FastAPI · SQLAlchemy · APScheduler · Kurigram · Xray-core
- **前端栈**：Vue 3 · TypeScript · Pinia · Vite · Tailwind CSS · Vue I18n（简中 / English）
- **开发验证**：

```bash
# 后端单元测试（建议 Python 3.10 / 3.11 环境）
pytest tests -q

# 前端类型检查、Vitest 单测与生产构建
cd frontend && npm run typecheck && npm run test && npm run build
```

<details>
<summary>📂 目录结构与核心模块</summary>

```text
TG-Manage/
├── backend/              # FastAPI 路由、认证限流、Xray 路由、TeleBox 监管、定时任务与通知
├── tg_manage/            # Pyrogram 客户端共享连接池、加密与日志脱敏核心库
├── frontend/             # Vue 3 + Vite + TypeScript Web 控制面板与 Vitest 测试
├── telebox/              # 隔离运行的 TeleBox TypeScript Worker 适配层
├── docker/               # entrypoint、Nginx 反代配置与容器构建辅助
├── scripts/              # install.sh / update.sh / backup.sh 运维脚本
├── docs/                 # VitePress 中文文档与版本发行说明
└── tests/                # pytest 后端回归与集成测试套件
```

</details>

## 📄 开源协议

基于 [BSD-3-Clause](LICENSE) 协议开源。
