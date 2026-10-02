# 前端类型与接口规范

`frontend/tsconfig.app.json` 开启未使用变量/参数与 switch fallthrough 检查，`npm run typecheck` 用 `vue-tsc`。共享模型在 `lib/types.ts`，业务接口与响应类型就近放在 `lib/api/<domain>.ts`；API 调用通过 `core.ts` 的 `request<T>`、`requestBlob` 等，不在页面随意断言 `any`。

```ts
// frontend/src/lib/api/communications.ts
export interface Dialog { id: string; title: string; type: string; unread_count: number; archived: boolean }
export const accountPath = (account: string) => `/communications/${encodeURIComponent(account)}`
```

示例只摘取 `Dialog` 的核心字段；完整类型以源文件为准。Telegram chat ID 用字符串，避免 JS number 精度问题；动态路径 `encodeURIComponent`，查询参数 `URLSearchParams`。后端 Pydantic 验证是输入安全边界，TS 类型只保证本地编译，不替代运行时验证；修改响应格式时同时更新相应 `backend/api/routes/`、业务 API 类型和测试。
