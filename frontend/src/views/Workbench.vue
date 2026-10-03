<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Check, Clock3, Search, Send, UsersRound, Workflow } from 'lucide-vue-next'
import { usePanelAccount, errorText } from '../composables/usePanelAccount'
import { listDialogs, sendMessage, type Dialog } from '../lib/api/communications'
import { createTeleBoxTask } from '../lib/api/telebox-tasks'
import { useConfirm } from '../composables/useConfirm'
import ChatAvatar from '../components/ChatAvatar.vue'
import { getGlobalSettings } from '../lib/api/settings'
import { getAuthToken } from '../lib/api/core'

const { store, account, error } = usePanelAccount()
const { confirm } = useConfirm()
const selected = ref<string[]>([])
const dialogs = ref<Dialog[]>([])
const targets = ref<string[]>([])
const search = ref('')
const text = ref('')
const mode = ref<'now' | 'schedule'>('now')
const time = ref('09:00')
const name = ref('')
const busy = ref(false)
const loading = ref(false)
const result = ref('')
const chatCenterEnabled = ref(false)
const settingsReady = ref(false)
const manualTargets = ref('')
const CACHE_LIMIT = 5 * 1024 * 1024
let generation = 0
const parseTargets = (value: string) => [...new Set(value.split(/[\s,，]+/).map(item => item.trim()).filter(Boolean))]
watch(manualTargets, value => { if (!chatCenterEnabled.value) targets.value = parseTargets(value) })
function onChatCenterChanged(event: Event) {
  chatCenterEnabled.value = (event as CustomEvent<boolean>).detail === true
  ++generation; dialogs.value = []; targets.value = []
  if (chatCenterEnabled.value && selected.value.length) void loadDialogs(selected.value)
  else targets.value = parseTargets(manualTargets.value)
}
onMounted(async () => {
  window.addEventListener('chat-center-changed', onChatCenterChanged)
  try {
    chatCenterEnabled.value = (await getGlobalSettings(getAuthToken())).chat_center_enabled === true
    if (chatCenterEnabled.value && selected.value.length) await loadDialogs(selected.value)
  } catch (cause) { error.value = errorText(cause) }
  finally { settingsReady.value = true }
})

const visibleDialogs = computed(() => dialogs.value.filter(dialog =>
  (dialog.title + ' ' + (dialog.username || '')).toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase()),
))
function toggle(list: string[], value: string) {
  const index = list.indexOf(value)
  if (index === -1) list.push(value)
  else list.splice(index, 1)
}
watch(account, value => { if (value && !selected.value.length) selected.value = [value] })
async function loadDialogs(accounts: string[]) {
  if (!chatCenterEnabled.value) return
  const current = ++generation
  targets.value = []
  dialogs.value = []
  error.value = ''
  if (!accounts.length) { loading.value = false; return }
  loading.value = true
  try {
    let cachedBytes = 0
    const pages = await Promise.all(accounts.map(async accountName => {
      const items: Dialog[] = []
      let offset = 0
      for (let page = 0; page < 200; page++) {
        const response = await listDialogs(accountName, '', offset, false, 'groups')
        cachedBytes += new TextEncoder().encode(JSON.stringify(response.items)).byteLength
        if (cachedBytes > CACHE_LIMIT) throw new Error('聊天缓存超过 5 MB，已强制清理。请缩小选择范围。')
        items.push(...response.items)
        if (!response.has_more) break
        offset = response.next_offset ?? offset + response.items.length
      }
      return items
    }))
    if (current !== generation) return
    const otherIds = pages.slice(1).map(items => new Set(items.map(item => item.id)))
    dialogs.value = (pages[0] ?? []).filter(dialog => otherIds.every(ids => ids.has(dialog.id)))
  } catch (cause) {
    if (current === generation) error.value = errorText(cause)
  } finally {
    if (current === generation) loading.value = false
  }
}
watch(selected, accounts => { if (settingsReady.value) void loadDialogs(accounts) }, { deep: true })
onUnmounted(() => { ++generation; window.removeEventListener('chat-center-changed', onChatCenterChanged) })

async function submit() {
  if (busy.value || !selected.value.length || !targets.value.length || !text.value.trim()) return
  if (!chatCenterEnabled.value && targets.value.some(id => !/^-?[0-9]{1,20}$|^@?[A-Za-z][A-Za-z0-9_]{3,31}$/.test(id))) {
    error.value = '目标须是 Telegram 会话 ID 或用户名，每行填写一个'
    return
  }
  const action = mode.value === 'now' ? '立即发送消息' : '创建每日发送任务'
  if (!await confirm({ title: action, message: `将对 ${selected.value.length} 个账号的 ${targets.value.length} 个群聊${action}，是否继续？` })) return
  busy.value = true
  error.value = ''
  result.value = ''
  let sent = 0
  try {
    if (mode.value === 'now') {
      for (const accountName of selected.value) for (const chat of targets.value) {
        await sendMessage(accountName, chat, text.value)
        sent++
      }
      result.value = `已成功发送 ${sent} 条消息`
    } else {
      await createTeleBoxTask({
        name: name.value.trim(), kind: 'message', accounts: selected.value,
        time: time.value, enabled: true, plugin: null, command: null, args: '',
        chats: targets.value, text: text.value,
      })
      result.value = '定时任务已创建，可在任务编排中查看与停用'
    }
  } catch (cause) {
    error.value = (sent ? `已有 ${sent} 条发送成功，剩余未执行。` : '') + errorText(cause)
  } finally { busy.value = false }
}
</script>

<template>
  <div class="panel-stack workbench">
    <header class="panel-card workbench-intro">
      <p class="panel-eyebrow"><Workflow :size="18" /> 账号工作台</p>
      <h2 class="panel-title">一次选择，清楚掌握发送范围</h2>
      <p class="panel-muted">选择操作账号和目标会话，发送消息或建立每日任务。</p>
      <div class="workbench-summary" aria-live="polite"><span><strong>{{ selected.length }}</strong> 个账号</span><span class="workbench-summary-dot" aria-hidden="true" /><span><strong>{{ targets.length }}</strong> 个目标会话</span></div>
    </header>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <p v-if="result" class="panel-success" role="status">{{ result }}</p>
    <section class="workbench-pickers" aria-label="选择发送范围">
      <div class="panel-card workbench-picker">
        <div class="workbench-picker-header"><div class="workbench-step">01</div><div><h3>操作账号</h3><p class="panel-muted">选择一个或多个已登录账号</p></div><span class="panel-badge">{{ selected.length }} 已选</span></div>
        <div v-if="!store.accounts.length" class="panel-empty">暂无账号，请先在账号管理登录。</div>
        <div v-else class="workbench-options" role="group" aria-label="操作账号">
          <label v-for="item in store.accounts" :key="item.name" class="workbench-option" :class="{ selected: selected.includes(item.name) }">
            <input type="checkbox" :checked="selected.includes(item.name)" :disabled="busy" @change="toggle(selected, item.name)" />
            <span class="workbench-account-avatar" aria-hidden="true">{{ item.name.slice(0, 2) }}</span>
            <span class="workbench-option-content"><strong>{{ item.name }}</strong><small>{{ item.status === 'active' ? '已连接' : (item.status_message || '账号已登录') }}</small></span>
            <span class="workbench-check" aria-hidden="true"><Check :size="14" /></span>
          </label>
        </div>
      </div>
      <div class="panel-card workbench-picker">
        <div class="workbench-picker-header"><div class="workbench-step">02</div><div><h3>目标对话</h3><p class="panel-muted">{{ chatCenterEnabled ? '仅显示所选账号共同加入的群聊' : '直接填写目标 ID 或用户名，不读取聊天记录' }}</p></div><span class="panel-badge">{{ targets.length }} 已选</span></div>
        <p v-if="!settingsReady" class="panel-empty" role="status">正在读取设置…</p>
        <label v-else-if="!chatCenterEnabled" class="workbench-message-label">目标会话 ID 或用户名<textarea v-model="manualTargets" rows="5" class="panel-input mt-2" placeholder="每行一个，例如 -1001234567890 或 @example" :disabled="busy" /><small class="panel-muted">关闭聊天中心时不会读取其他 Telegram 消息；发送前请确认账号有权访问这些会话。</small></label>
        <template v-else><label class="workbench-search"><Search :size="18" /><input v-model="search" type="search" placeholder="搜索群名称或用户名" aria-label="搜索目标对话" :disabled="loading || !selected.length" /></label>
        <div v-if="visibleDialogs.length && !loading" class="workbench-select-actions"><button type="button" :disabled="busy" @click="targets = visibleDialogs.map(dialog => dialog.id)">选择当前结果</button><button type="button" :disabled="busy || !targets.length" @click="targets = []">清空选择</button></div>
        <p v-if="loading" class="panel-empty" role="status">正在读取共有群会话…</p>
        <p v-else-if="!selected.length" class="panel-empty">先选择操作账号</p>
        <p v-else-if="!visibleDialogs.length" class="panel-empty">{{ search ? '没有匹配的群会话' : '这些账号没有共有群会话' }}</p>
        <div v-else class="workbench-options" role="group" aria-label="目标对话">
          <label v-for="dialog in visibleDialogs" :key="dialog.id" class="workbench-option" :class="{ selected: targets.includes(dialog.id) }">
            <input type="checkbox" :checked="targets.includes(dialog.id)" :disabled="busy" @change="toggle(targets, dialog.id)" />
            <ChatAvatar :account="selected[0]!" :chat-id="dialog.id" :name="dialog.title" />
            <span class="workbench-option-content"><strong>{{ dialog.title }}</strong><small>{{ dialog.username ? '@' + dialog.username : dialog.type === 'supergroup' ? '超级群组' : '群组' }}</small></span>
            <span class="workbench-check" aria-hidden="true"><Check :size="14" /></span>
          </label>
        </div></template>
      </div>
    </section>
    <form class="panel-card workbench-compose" @submit.prevent="submit">
      <div class="workbench-picker-header"><div class="workbench-step">03</div><div><h3>编写消息</h3><p class="panel-muted">发送前可核对所选账号与会话</p></div></div>
      <fieldset class="workbench-mode" :disabled="busy"><legend>发送方式</legend><label :class="{ selected: mode === 'now' }"><input v-model="mode" type="radio" value="now" /><Send :size="18" />立即发送</label><label :class="{ selected: mode === 'schedule' }"><input v-model="mode" type="radio" value="schedule" /><Clock3 :size="18" />每日定时</label></fieldset>
      <div v-if="mode === 'schedule'" class="panel-columns"><label>任务名称<input v-model="name" required maxlength="80" class="panel-input mt-2" :disabled="busy" placeholder="例如：每日上午问候" /></label><label>执行时间（服务器时区）<input v-model="time" type="time" required class="panel-input mt-2" :disabled="busy" /></label></div>
      <label class="workbench-message-label">消息内容<textarea v-model="text" rows="5" class="panel-input mt-2" required :disabled="busy" placeholder="输入要发送的消息…" /></label>
      <div class="workbench-footer"><p class="panel-muted"><UsersRound :size="17" /> {{ selected.length }} 个账号 · {{ targets.length }} 个目标会话</p><button class="panel-button primary" :disabled="busy || loading || !settingsReady || !targets.length || !selected.length || !text.trim()">{{ busy ? '正在处理…' : mode === 'now' ? '确认并发送' : '创建定时任务' }}</button></div>
    </form>
  </div>
</template>
