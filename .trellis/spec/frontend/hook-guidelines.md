# 组合式函数规范

该仓库以 `composables/use*.ts` 命名 Vue composable，而不是 React hook：`usePanelAccount.ts` 从 `useAccountsStore()` 取账号，并读取路由 query；`useConfirm.ts` 把确认弹窗封装成 `Promise<boolean>`；`useTheme.ts` 和 `useI18n.ts` 分别处理外观和语言。

```ts
// frontend/src/composables/usePanelAccount.ts 的已有调用方式
const { store, account, error } = usePanelAccount()
```

跨多个页面复用相同生命周期/数据流时抽到 composable；单页的临时输入、选中消息仍可留在 `views/Chats.vue`。对外返回清晰的 `ref`、`computed` 和方法；异步异常转为用户可读错误；在 composable 挂载的事件监听和定时器于 `onUnmounted` 清理。确认操作复用 `useConfirm`，不要新增 `window.confirm`。避免在 composable 内偷偷维护第二套账号列表缓存；跨页账号状态归 `stores/accounts.ts`。
