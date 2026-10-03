# 任务编排

当前任务编排只创建两类任务：TeleBox 插件命令，以及账号工作台的每日定时消息。原 TG-SignPulse 的动作编号、签到流程、关键词监听和旧 `/api/sign-tasks` 接口不再执行。旧数据文件不会自动删除，升级前请做好备份。

## TeleBox 插件任务

1. 在账号管理登录账号并启用 TeleBox，完成该账号的独立会话授权。
2. 在「拓展插件」安装需要的插件，等待状态变为「运行中」。
3. 在「任务编排」点击「添加任务」。面板读取该账号运行时已经加载的命令及其所属插件；选择账号、插件命令、参数和名称。只显示 KITT 与当前账号新安装插件的已加载命令，保存后可手动执行。
4. 保存后点击「执行一次」可投递命令；需要插件定时运行时，在 TeleBox 插件中定义 `cronTasks`。

插件的 `cmdHandlers` 是 TeleBox 的命令入口；面板从运行中的 `pluginManager.listCommands()` 和 `getPluginEntry()` 获取命令及插件对应关系。手动执行时，适配器使用该账号 TeleBox 自身的会话，按照运行时 `getPrefixes()` 的前缀向「收藏夹」投递命令，交给原有消息事件处理。它不会调用旧 Python 动作指令。投递成功表示命令已被接受发送，插件内部执行结果在「拓展插件」或「日志」中查看。插件卸载、重载或账号停用后，后续执行会重新校验当前已加载的命令。

TeleBox 插件自身定义的 `cronTasks` 仍由 TeleBox 原生 `cronManager` 管理；面板不再定时投递插件命令，已有插件任务的旧每日时间也不会继续生效。插件开发请参照 [TeleBox 开发指南](https://github.com/TeleBoxOrg/TeleBox/blob/main/TELEBOX_DEVELOPMENT.md)，尤其是 `cmdHandlers`、`listenMessageHandler` 和 `cronTasks` 的生命周期约定。

## 账号工作台每日消息

在「账号工作台」选择账号、目标对话与文字后，可以立即发送，或保存为每日定时消息。它保留原本的发送能力，不经过 TeleBox 插件命令。关闭聊天中心后普通聊天读取被禁止；账号工作台的主动发送与已有每日发送计划仍可执行。

## 数据与接口

任务与最近 500 条运行记录存放在 `telebox-tasks.json`，备份包含该文件。前端调用 `/api/telebox-tasks` 列表、创建、更新、删除，以及 `/api/telebox-tasks/{id}/run` 手动触发。每日时间使用系统设置时区；任务执行失败时记录状态与简要错误，敏感信息不会作为运行记录返回。
