# 账号检测、私人验证码与仪表盘封面契约

## 1. Scope / Trigger

修改账号显式检测、机器人通知设置、`777000` 验证码读取或封面存储/API 时使用本契约。三者均跨前端、API、服务和持久化目录；普通打开账号页不得因此触发 Telegram 资料请求。

## 2. Signatures

- `POST /api/accounts/status/check` 接收 `AccountStatusCheckRequest`，返回 `AccountStatusCheckResponse.results[]`；批量 Job 使用 `POST /api/accounts/status/check-jobs`，两条检测路径都应刷新头像。
- `GET/POST /api/config/settings` 读写通知配置；`run_code_bot()` 仅由持有调度锁的实例运行，Bot API 使用 `getUpdates`，不新建 Webhook。
- `GET/PUT/DELETE /api/appearance/hero-image` 读取、替换、移除封面。

## 3. Contracts

- 检测结果新增 `avatar_refreshed: bool`、`avatar_refresh_error: bool`；检测成功才尝试下载 Telegram 头像，下载失败保留旧缓存；账号名、备注、标签仍是本地字段。
- `telegram_bot_code_enabled` 默认 `false`；启用必须同时有已保存的 `telegram_bot_token` 和正整数私人 `telegram_bot_chat_id`（至多 19 位且不超过 `2^63-1`）。GET 返回 `telegram_bot_token: null`、`telegram_bot_token_set` 与 `telegram_bot_code_status`，不可返回 Token 明文。
- 仅从账号的 `777000` 聊天读取验证码。自动推送只处理新消息；`/code 账号名` 只允许 `chat.type == private` 且 `chat.id == from.id == 配置目标 ID`，只返回最近五分钟内的验证码。工作目录 `bots/official-code-cursors.json` 只存消息 ID 和 Bot API offset，绝不存验证码或消息正文。
- 新封面 `PUT` 上限 `1 * 1024 * 1024` 字节；为保护原数据，旧封面 `GET` 仍接受至多 `5 * 1024 * 1024` 字节。封面保存在现有备份覆盖的工作目录，升级不得清空 `data/`。

## 4. Validation & Error Matrix

| 条件 | 边界行为 |
| --- | --- |
| 非法/群组/其他发送者的 Bot 更新 | 静默忽略，不查账号、不回复 |
| 关闭功能或目标 ID/Token 改变 | 不向旧目标发送；重新建立历史基线 |
| 旧于五分钟的官方码 | `/code` 回复“暂无有效验证码”；不自动推送 |
| Bot API 报错或已有 Webhook | 安全状态/日志，不能包含 Token、URL、验证码正文 |
| 头像下载瞬时失败 | `avatar_refresh_error=true`，保留旧缓存与本地字段 |
| 新封面超过 1 MiB、空文件或非 JPEG/PNG/WebP | `PUT` 返回 400；既有较大封面仍可读取 |

## 5. Good / Base / Bad Cases

- Good：持锁实例发现 `777000` 的新码，仅推送给私人目标；目标在五分钟内 `/code account` 可按需获取。
- Base：启动时先用现有消息建立基线、无新码；普通账号列表只读头像缓存。
- Bad：群聊或另一用户发命令、旧码、过大封面、头像网络异常；分别按上表处理，不泄露数据或覆盖旧封面。

## 6. Tests Required

- `tests/test_official_code_bot.py`：权限、五分钟、启动基线、至多一次、无正文持久化、Bot 错误不含 Token。
- `tests/test_account_status_jobs.py`、`tests/test_accounts_routes_extended.py`、`tests/test_avatar_cache.py`：单/批量检测与头像成功、无头像、失败保旧图。
- `tests/test_appearance.py` 与前端设置/布局测试：1 MiB 上传、旧 5 MiB 读取、控件入口与提示。
- `tests/test_log_optimization.py`：`httpx` 和 `httpcore` 在 DEBUG 应用日志下仍至少为 WARNING，阻止 Bot Token URL 写日志。

## 7. Wrong vs Correct

```python
# Wrong: 外部异常消息可能含 Bot Token URL；页面加载也可能触发 Telegram 请求。
logger.warning("Bot 请求失败: %s", exc)
await refresh_account_avatar(name, download_fn)  # ordinary list GET

# Correct: 只记录安全类型；仅显式检测后刷新头像。
logger.warning("Bot 请求失败（%s）", type(exc).__name__)
if status_result.get("ok"):
    await refresh_account_avatar(name, download_fn)
```
