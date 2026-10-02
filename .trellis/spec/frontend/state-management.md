# 前端状态管理

Pinia 只维护跨页共享状态：`stores/auth.ts` 管令牌与退出，`stores/accounts.ts` 管账号列表、30 秒 TTL、并发请求合并和强制刷新，`stores/activeRuns.ts` 管运行任务。局部表单、筛选、选中会话和分页指针留在页面或 composable（如 `views/Chats.vue`）。服务端数据源始终是 API，前端缓存失效后重新请求。

```ts
// frontend/src/stores/accounts.ts
if (!inFlight) {
  inFlight = fetchAccounts().finally(() => { inFlight = null })
}
```

账号变更后用 `refreshAccounts()` 让写操作后的列表更新；退出时 `auth` 清令牌，`accounts` 监听 token 同步清空旧数据，避免跨会话残留。令牌持久化经过 `lib/safe-storage.ts`，401 统一由 `lib/api/core.ts` 控制单次跳转。不要把 Telegram API_HASH、session 或 Bot Token 存入浏览器状态。
