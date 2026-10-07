# TG Manage 改造进度（2026-10-07）

## 已完成

- 自有 Python 包与应用、前端、PWA、文档、容器、CI 镜像、CSS 变量和新存储键统一为 TG Manage。
- 旧环境变量、`.signer` 工作目录、`.tg_signpulse_data_dir` 标记和浏览器旧键保持读取兼容；原 `./data:/data` 挂载不变。备份清单覆盖新旧工作目录。
- 删除账号工作台页面及路由、导航和专属样式；机器人中心归入系统设置，旧 `/bots` 路径重定向并展开设置分区。
- 仪表盘复用 `/api/ops/memory`，每 15 秒读取当前进程 RSS；隐藏标签页暂停，恢复时刷新，卸载时停止。
- 按 ui-ux-pro-max 规则修复窄屏机器人命令布局、表单标签/触控尺寸、抽屉和设置入口焦点等问题。
- README 和部署文档说明先停服务、备份完整 `data/`、快进拉取、原挂载重建；`scripts/update.sh` 自动执行并在失败时尝试恢复服务。
- GitHub 界面与文档导航指向 `hikling/TG-SignPulse-Private`；上游归属和旧兼容标识仅在对应历史/兼容语境保留。

## 已验证

- `frontend`: `npm run typecheck`、`npm test`（40 文件、255 用例）、`npm run build` 通过。
- 文档：`npm run docs:build`、`npm run docs:verify-agent` 通过；修复了 VitePress 对运维命令中双花括号的解析错误。
- Python：`ruff check backend tg_manage tests` 通过；Python 3.12 AST 检查 147 个文件通过；可在 Windows 运行的存储/安全/工具/版本测试共 86 项通过。
- 静态扫描：运行界面无工作台引用、无 `--sp-*` CSS 变量；剩余旧标识属于真实仓库 slug、上游归属或升级兼容入口。

## 待目标环境验证

- 全量 pytest 的收集会导入 Linux `fcntl`，当前 Windows 主机无法运行；需在 Linux/Docker CI 跑全套测试。
- 真实 Telegram 登录、TeleBox 插件、服务器已有数据的升级/回退、实际浏览器视口视觉验收需在目标环境验证。
- 此源码来自 `main` 的 ZIP 快照，没有 `.git`；通过受权的 GitHub 连接核对基准树后提交 PR。合并前仍需审查变更并等待 Linux CI。
