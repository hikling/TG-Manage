# 前端目录结构

- `frontend/src/main.ts` 挂载应用；`App.vue` 和 `router/index.ts` 定义外壳、路由及登录守卫。
- `views/` 放页面，`views/Layout.vue` 是导航与移动端抽屉，`Chats.vue`、`Accounts.vue`、`TeleBox.vue` 等由路由懒加载。
- `components/` 放可复用 UI；复杂页面按 `components/accounts/`、`components/settings/` 等拆分。
- `composables/use*.ts` 放跨组件交互逻辑；`stores/` 是 Pinia 跨页状态。
- `lib/api/core.ts` 实现鉴权、超时和统一请求，`lib/api/*.ts` 按业务域定义接口，`lib/api.ts` 导出公共入口；`lib/types.ts` 放共用类型；`locales/` 是中英文文案；`style.css` 包含全局面板样式。
- `src/test/*.spec.ts` 是 Vitest 单元和组件测试。

例如 `views/Chats.vue` 调 `lib/api/communications.ts`，`composables/usePanelAccount.ts` 取得账号选择，`stores/accounts.ts` 缓存账号列表。新功能优先按现有域扩展，别在组件中复制 `fetch` 鉴权逻辑；独立频道管理页已从路由删除，频道会话仍可在聊天中心展示。
