# 常见问题

## 首次登录如何设置密码

运行 `bash scripts/install.sh`，复制输出的一次性设置码，在网页首次登录页设置自己的管理员密码（至少 12 位）。已有管理员继续使用原账号。设置码在 `data/.admin_setup_token`，完成后失效。

## 为什么任务开启了却没有执行

优先检查：

- 执行模式是不是 `listen`
- 定时表达式或时间段是否正确
- 任务是否启用
- 绑定账号是否仍然有效
- `/readyz` 是否正常（含 `scheduler_lock_held`）
- 多实例时是否误配 `APP_MONITOR_SHARD` 导致监听不在本机

## 旧 /api/tasks 接口为什么不可用

旧 ORM 任务 API（`/api/tasks`、`/api/batch/tasks`）已**完全移除**。  
新功能请使用 `/api/sign-tasks` 与 `/api/batch/sign-tasks`。

- 盘点残留 ORM 表（模型已删）：`python tools/check_legacy_tasks.py --json`
- `/readyz` 含 `legacy_tasks_removed: true`
- 旧 SSE `/api/events/logs` 已移除，请改用 `/api/events/sign-history`

## Dashboard 实时日志连不上

优先检查：

- 是否已登录且 token 未过期
- 反向代理是否关闭 SSE 缓冲（见 [Nginx 部署](deploy/nginx.md)）
- 浏览器控制台是否有 EventSource 错误；面板会指数退避重连

## 设置里「导出 JSON」和「完整备份」有什么区别？

| | 配置 JSON | 完整备份 tar.gz |
|--|-----------|-----------------|
| 含任务配置 | ✅ | ✅（在 `.signer`） |
| 含登录会话 | ❌ | ✅ |
| 含数据库 | ❌ | ✅（SQLite） |
| 面板可导入 | ✅ | ❌（需手动解压恢复） |
| 应用密钥与账号凭据 | JSON 不含账号凭据 | 备份整个 `data/` 才能保留密钥与会话 |

- 只想搬任务流程 → 用 **JSON**  
- 换服务器整机恢复 → 用 **完整备份**（可上传 WebDAV），停止服务后解压到 data 目录再启动（见 [WebDAV 备份与恢复](guide/backup-webdav.md)、[运维手册](reference/ops.md)）

## 如何配置 WebDAV 自动备份？

见 [WebDAV 备份与恢复](guide/backup-webdav.md)：设置 → 完整备份 → 填 URL/账号 → 测试连接 → 开启自动备份并保存。上传成功会清理本地副本并按保留份数轮转远端；失败会尽量发 Bot 通知。

## 是否已经改成 PostgreSQL、取消 SQLite？

**没有。** 默认数据库仍是 **SQLite**（数据目录下的 `db.sqlite`，WAL 模式）。

- 不设置 `APP_DATABASE_URL` / `DATABASE_URL` → 使用 SQLite  
- 设置 `APP_DATABASE_URL=postgresql+psycopg2://...` 并安装 `psycopg2-binary` → 可选使用 PostgreSQL  

项目**支持** Postgres，但**不强制**迁移，也未移除 SQLite 路径。

## 为什么重启后数据丢了

通常是因为没有挂载 `/data`，或者 `/data` 不可写导致程序降级到了 `/tmp/tg-signpulse`。

## AI 动作与全局 Telegram API 设置去哪了

这两个设置入口已移除。Telegram API ID/Hash 在每次账号登录时输入；旧 AI 任务应按 [迁移说明](guide/ai.md) 人工检查。

## 测试镜像和正式镜像有什么区别

- `dev` / `dev-*`：dev 分支滚动构建，适合预发
- `main` / `main-<sha>`：main 分支滚动构建，稳定主干镜像
- `vX.Y.Z` + `latest`：仅在推送 Git 标签 `v*` 时一次生成（正式版）

不要长期把 `dev` 当正式版使用。`latest` 只跟随正式 tag；`main` 跟随 main 分支最新提交。

## 监听任务为什么没命中

检查：

- `chat_id` 是否正确
- `message_thread_id` 是否填错
- 匹配模式是 `contains`、`exact` 还是 `regex`
- 正则是否写对
- 账号是否开启 updates

## 什么时候用 `string` 会话模式

当你希望：

- 用 session string 统一迁移
- 更方便做容器化备份
- 避免分散的会话文件

否则默认 `file` 模式就够用。

