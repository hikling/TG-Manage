# 前端目录结构

- `frontend/src/main.ts` 挂载应用；`App.vue` 和 `router/index.ts` 定义外壳、路由及登录守卫。
- `views/` 放页面，`views/Layout.vue` 是导航与移动端抽屉，`Chats.vue`、`Accounts.vue` 等由路由懒加载；TeleBox 的账号操作位于 `Accounts.vue`。
- `components/` 放可复用 UI；复杂页面按 `components/accounts/`、`components/settings/` 等拆分。
- `composables/use*.ts` 放跨组件交互逻辑；`stores/` 是 Pinia 跨页状态。
- `lib/api/core.ts` 实现鉴权、超时和统一请求，`lib/api/*.ts` 按业务域定义接口，`lib/api.ts` 导出公共入口；`lib/types.ts` 放共用类型；`locales/` 是中英文文案；`style.css` 包含全局面板样式。
- `src/test/*.spec.ts` 是 Vitest 单元和组件测试。

例如 `views/Chats.vue` 调 `lib/api/communications.ts`，`composables/usePanelAccount.ts` 取得账号选择，`stores/accounts.ts` 缓存账号列表。新功能优先按现有域扩展，别在组件中复制 `fetch` 鉴权逻辑。聊天中心入口常驻，关闭时仅获取 777000 官方验证码，开启时展示群组对话；独立频道、群管理、拓展插件和任务编排页面已从路由删除。TeleBox 的启动、停止、二步验证和退出登录通过 `lib/api/telebox.ts` 管理。
