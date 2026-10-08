# 组件与页面规范

现有页面使用 Vue 3 单文件组件及 `<script setup lang="ts">`，使用 `ref/computed/watch` 管理局部状态，模板中引用显式导入的 `lucide-vue-next` 图标。例如 `views/Layout.vue` 负责导航、主题/语言切换、移动抽屉焦点与 body 滚动锁；`components/ConfirmDialog.vue` 配合 `useConfirm()` 承担危险操作确认。

```vue
<!-- views/Chats.vue 中的真实用法 -->
<p v-if="error" class="panel-error" role="alert">{{ error }}</p>
<button :disabled="loading" @click="loadDialogs()">刷新</button>
```

新页面采用 `panel-*` 全局样式和现有布局断点；显式显示加载、空态和失败态，按钮在请求中禁用。输入控件应有 label/aria-label，图标按钮应有可读名称；弹窗和移动抽屉保持 Escape、初始焦点与关闭后焦点归还（参考 `Layout.vue`）。销毁时清理 timer/监听器，并对旧请求响应做账号/会话一致性检查（参考 `Chats.vue` 的 generation guard）。不要直接在模板里拼敏感数据或将凭据展示出来。

`Modal.vue` 的初始焦点只选可键盘进入的表单控件：隐藏的封面上传 `<input type="file" class="sr-only" tabindex="-1">` 必须跳过，否则打开“自定义主题”会把焦点放到不可见控件。对应回归测试是 `frontend/src/test/modal-initial-focus.spec.ts`。

桌面侧栏收起后图标必须保留文字 `title`/`aria-label`，移动端仍按抽屉处理。账号卡片的三点菜单一次只展开一个，支持点击外部和 Escape 关闭；离开账号页回收头像 Object URL，不以白底堆叠或模糊滤镜代替层级。
