# 账户登录备份与恢复

在**账户管理 → 登录备份**手动导出 `.tglogin` 文件，输入至少 12 个字符的备份密码并确认。该文件仅保存已授权账户的 Telegram 会话和每个账户继续使用会话所需的 API ID、API Hash；不会保存面板设置、代理、TeleBox 数据、账户备注、状态或消息历史。

在新服务器完成面板安装后，先停止旧服务器上使用这些账户的服务，再进入新面板的**账户管理 → 登录备份 → 导入**，选择文件并输入原备份密码。导入会先解密并验证整个文件，然后恢复不存在的账户；新服务器已有的同名账户保持原样。界面会显示恢复和跳过数量。文件模式与字符串模式的部署都支持导入，导入不主动连接 Telegram；可随后手动点击账户状态检测确认实际授权状态。

请妥善保管文件和密码。文件泄露且密码被猜中后，授权会话可用于访问相应 Telegram 账户。请勿让新旧服务器同时使用同一份会话：Telegram 可能返回 `AUTH_KEY_DUPLICATED` 并使该授权密钥失效。Telegram 的[用户授权说明](https://core.telegram.org/api/auth)说明调用依附于授权密钥，[错误文档](https://core.telegram.org/api/errors)说明密钥重复使用的后果；[Pyrogram 会话字符串文档](https://docs.pyrogram.org/api/methods/export_session_string)说明会话可以序列化以迁移。

TeleBox 有独立登录资料，本备份不包含它；迁移后如需使用 TeleBox，请在新服务器重新授权。
