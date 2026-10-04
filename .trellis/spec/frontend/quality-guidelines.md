# 前端质量规范

运行 Node 22.23.1（`.nvmrc` 和 `frontend/package.json` engines），Vue 3 + Pinia 3 + TypeScript + Vite 8；测试在 `frontend/src/test/*.spec.ts`，Vitest 与 Vue Test Utils 覆盖 store、API、路由守卫、键盘与可访问性行为（如 `accountsStore.spec.ts`、`custom-select-aria.spec.ts`）。项目没有单独的 ESLint 脚本，不应凭空要求它通过。

```bash
cd frontend
npm run typecheck
npm test
npm run build
```

删除 API 导出或页面时，必须在整个 `frontend/src/` 中检查其组件、类型和测试引用，并删除不再挂载的专用组件。`vue-tsc` 会检查 tsconfig 包含的所有 Vue 文件，包括未被路由或页面导入的文件；仅移除页面入口不能避免旧组件触发构建错误。完成清理后运行上述类型检查、测试和生产构建。

共享文案查 `locales/zh-CN.json` 与 `en-US.json`；已有页面可能保留直接中文文案，改动时保持对应页面的一致做法。网络错误通过 API 核心传递，页面提供可见反馈。增删接口同时覆盖失败和空态，重要交互检查手机断点、暗色主题和焦点管理。`src/test/api-request.spec.ts` 验证超时和 401，`accountsStore.spec.ts` 验证缓存与登出清理。不要将旧 Python 插件页面或频道管理页加回导航。
