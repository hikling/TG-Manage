# 旧关键词监听迁移

历史关键词监听任务不再由 TG Manage 启动或导入。数据文件留在原数据目录，供离线备份；升级不会自动删除。

需要消息监听时，按 [TeleBox 开发指南](https://github.com/TeleBoxOrg/TeleBox/blob/main/TELEBOX_DEVELOPMENT.md) 使用插件的 `listenMessageHandler`，并通过 TeleBox 的 TPM 安装或维护插件。插件自身的定时处理使用 `cronTasks`。旧动作编号和配置不能自动转换为 TeleBox 插件，请逐项检查原规则后重新实现。
