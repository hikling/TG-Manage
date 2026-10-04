<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Activity, Clock3, ExternalLink, MessageSquare, Pause, Play, RefreshCw, Trash2, Zap } from 'lucide-vue-next'
import { RouterLink, useRoute } from 'vue-router'
import { useConfirm } from '../composables/useConfirm'
import { errorText } from '../composables/usePanelAccount'
import {
  deleteTeleBoxTask, listTeleBoxAccounts, listTeleBoxTasks, runTeleBoxTask, updateTeleBoxTask,
  type TeleBoxAccount, type TeleBoxTask, type TeleBoxTaskRun, type TaskInput,
} from '../lib/api/telebox-tasks'

const route = useRoute()
const { confirm } = useConfirm()
const tasks = ref<TeleBoxTask[]>([])
const history = ref<TeleBoxTaskRun[]>([])
const accounts = ref<TeleBoxAccount[]>([])
const selectedAccount = ref('')
const error = ref('')
const notice = ref('')
const loading = ref(false)
const busy = ref(false)
let poller: ReturnType<typeof setInterval> | undefined

const dailyTasks = computed(() => tasks.value.filter(item => item.kind === 'message'))
// Older command records cannot be converted into listeners: their trigger conditions
// live inside the plugin, and running the command repeatedly would be unsafe.
const legacyCommands = computed(() => tasks.value.filter(item => item.kind === 'plugin'))
const automations = computed(() => accounts.value
  .filter(account => !selectedAccount.value || account.account === selectedAccount.value)
  .flatMap(account => (account.automations || [])
    .filter(item => item.source === 'installed' || item.name === 'kitt')
    .map(item => ({ ...item, account: account.account, running: account.enabled && account.status === 'running' }))))
const filteredDailyTasks = computed(() => dailyTasks.value.filter(item =>
  !selectedAccount.value || item.accounts.includes(selectedAccount.value)))
const selectedRuntime = computed(() => accounts.value.find(item => item.account === selectedAccount.value))

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const [taskData, accountData] = await Promise.all([listTeleBoxTasks(), listTeleBoxAccounts()])
    tasks.value = taskData.items
    history.value = taskData.history.slice().reverse()
    accounts.value = accountData.accounts
    if (!selectedAccount.value) {
      const requested = typeof route.query.account === 'string' ? route.query.account : ''
      selectedAccount.value = accounts.value.find(item => item.account === requested)?.account || ''
    }
    error.value = ''
  } catch (cause) { if (!silent) error.value = errorText(cause) }
  finally { if (!silent) loading.value = false }
}
function asInput(task: TeleBoxTask): TaskInput {
  const { id: _id, ...payload } = task
  void _id
  return payload
}
async function toggle(task: TeleBoxTask) {
  busy.value = true; error.value = ''
  try {
    await updateTeleBoxTask(task.id, { ...asInput(task), enabled: !task.enabled })
    await load()
  } catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
async function remove(task: TeleBoxTask) {
  if (!await confirm({ title: '删除任务记录', message: `删除「${task.name}」？已有运行记录会保留。`, danger: true })) return
  busy.value = true; error.value = ''
  try { await deleteTeleBoxTask(task.id); await load() }
  catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
async function run(task: TeleBoxTask) {
  if (!await confirm({ title: '立即发送', message: `现在执行「${task.name}」？` })) return
  busy.value = true; error.value = ''
  try {
    const result = await runTeleBoxTask(task.id)
    notice.value = result.message
    await load()
  } catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
function triggerLabel(triggers: string[]) {
  return triggers.map(trigger => ({ message: '消息监听', event: '事件处理', cron: '插件定时' })[trigger as 'message' | 'event' | 'cron'] || trigger).join(' · ')
}
onMounted(() => { void load(); poller = setInterval(() => void load(true), 10000) })
onUnmounted(() => { if (poller) clearInterval(poller) })
</script>

<template>
  <div class="panel-stack">
    <header class="panel-card">
      <p class="panel-eyebrow">TELEBOX / AUTOMATION</p>
      <div class="panel-row">
        <div class="flex-1 min-w-56">
          <h2 class="panel-title">自动化任务</h2>
          <p class="panel-muted">已加载插件的消息监听、事件和定时规则由 TeleBox 常驻运行；每日群消息由面板调度。</p>
        </div>
        <button type="button" class="panel-button" :disabled="loading" @click="load()"><RefreshCw :size="17" aria-hidden="true" />刷新</button>
        <RouterLink class="panel-button primary" :to="{ name: 'telebox', query: selectedAccount ? { account: selectedAccount } : {} }">
          <Zap :size="17" aria-hidden="true" />添加常驻任务
        </RouterLink>
      </div>
    </header>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="panel-success" role="status">{{ notice }}</p>
    <section class="panel-card panel-stack" aria-label="任务账号">
      <label for="task-account" class="font-semibold">运行账号</label>
      <select id="task-account" v-model="selectedAccount" class="panel-input" :disabled="loading">
        <option value="">全部账号</option>
        <option v-for="item in accounts" :key="item.account" :value="item.account">{{ item.account }} · {{ item.status }}</option>
      </select>
      <p v-if="selectedRuntime && selectedRuntime.status !== 'running'" class="panel-error">此账号 TeleBox 未运行，插件监听器当前未工作。请到拓展插件检查运行状态。</p>
    </section>
    <section class="panel-card panel-stack">
      <div class="panel-row"><h3>常驻插件</h3><span class="panel-badge">{{ automations.length }} 项</span></div>
      <p class="panel-muted text-sm">插件加载后由其自身的触发条件运行。只展示实际声明了消息监听、事件处理或 cron 的插件；安装仅有命令的插件不会自动执行命令。</p>
      <p v-if="loading" class="panel-empty" role="status">正在读取插件…</p>
      <p v-else-if="!automations.length" class="panel-empty">暂无已加载的常驻插件。前往插件中心安装带监听或定时能力的插件。</p>
      <article v-for="item in automations" :key="item.account + ':' + item.name" class="workbench-option flex-wrap">
        <span class="workbench-step"><Activity :size="18" aria-hidden="true" /></span>
        <div class="flex-1 min-w-40">
          <strong class="block">{{ item.name }}</strong>
          <p class="panel-muted text-sm">{{ item.account }} · {{ triggerLabel(item.triggers) }}</p>
        </div>
        <span class="panel-badge">{{ item.running ? '监听器已加载' : '未运行' }}</span>
        <RouterLink class="panel-button" :to="{ name: 'telebox', query: { account: item.account } }">
          管理插件 <ExternalLink :size="15" aria-hidden="true" />
        </RouterLink>
      </article>
    </section>
    <section class="panel-card panel-stack">
      <div class="panel-row"><h3>每日群消息</h3><span class="panel-badge">{{ filteredDailyTasks.length }} 项</span></div>
      <p v-if="!filteredDailyTasks.length" class="panel-empty">暂无每日群消息。可在账号工作台创建。</p>
      <article v-for="task in filteredDailyTasks" :key="task.id" class="workbench-option flex-wrap">
        <span class="workbench-step"><MessageSquare :size="17" aria-hidden="true" /></span>
        <div class="flex-1 min-w-40"><strong class="block">{{ task.name }}</strong><p class="panel-muted text-sm">{{ task.accounts.join('、') }} · 每日 {{ task.time }} · {{ task.chats.length }} 个群会话</p></div>
        <span class="panel-badge">{{ task.enabled ? '已启用' : '已暂停' }}</span>
        <div class="panel-row">
          <button type="button" class="panel-button" :disabled="busy" @click="toggle(task)"><Pause v-if="task.enabled" :size="15" aria-hidden="true" /><Play v-else :size="15" aria-hidden="true" />{{ task.enabled ? '暂停' : '启用' }}</button>
          <button type="button" class="panel-button" :disabled="busy" @click="run(task)">发送一次</button>
          <button type="button" class="panel-button danger" :disabled="busy" :aria-label="'删除 ' + task.name" @click="remove(task)"><Trash2 :size="15" aria-hidden="true" /></button>
        </div>
      </article>
    </section>
    <details v-if="legacyCommands.length" class="panel-card">
      <summary class="cursor-pointer font-semibold">旧版命令记录（{{ legacyCommands.length }}）</summary>
      <p class="panel-muted text-sm mt-3">这些记录没有自动触发条件，不会持续执行。相应插件若有内置监听或 cron，会在上方按实际加载状态显示。确认后可删除旧记录，不会卸载插件。</p>
      <div v-for="task in legacyCommands" :key="task.id" class="panel-row border-b border-[var(--sp-border)] py-3">
        <span class="flex-1">{{ task.name }} <small class="panel-muted">{{ task.plugin }} / {{ task.command }}</small></span>
        <button type="button" class="panel-button danger" :disabled="busy" @click="remove(task)">删除旧记录</button>
      </div>
    </details>
    <section class="panel-card panel-stack">
      <div class="panel-row"><h3>面板任务执行记录</h3><Clock3 :size="18" class="panel-muted" aria-hidden="true" /></div>
      <p class="panel-muted text-sm">此处记录每日群消息和旧版命令调用；插件内部事件与定时执行由 TeleBox 自己管理。</p>
      <p v-if="!history.length" class="panel-empty">暂无运行记录</p>
      <p v-for="(entry, index) in history.slice(0, 20)" :key="index" class="text-sm border-b border-[var(--sp-border)] pb-3">
        <time class="panel-muted">{{ new Date(entry.time).toLocaleString() }}</time> · {{ entry.task }} ·
        <span :class="entry.success ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'">{{ entry.success ? '成功' : '失败' }}</span>
        <span class="block panel-muted mt-1">{{ entry.message }}</span>
      </p>
    </section>
  </div>
</template>
