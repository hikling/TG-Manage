# 前端开发规范索引

适用 `frontend/src/`。旧版 `frontend/CLAUDE.md` 可能仍提到已删除的插件/旧页面，新增实现应以现有路由和源码为准。

## 开发前

阅读 [目录](./directory-structure.md)、[组件](./component-guidelines.md)、[组合式函数](./hook-guidelines.md)、[状态](./state-management.md)、[类型](./type-safety.md) 和 [质量](./quality-guidelines.md)；跨后端接口的字段同步查 `backend/api/routes/`。

## 质量检查

```bash
cd frontend
npm run typecheck
npm test
npm run build
```

对 UI 变更还需检查桌面/移动端、亮色/暗色、键盘操作和错误提示；自动化测试不等同于真实 Telegram 会话验证。
