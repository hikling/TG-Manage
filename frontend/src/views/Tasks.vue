<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { Activity, Clock3, ExternalLink, MessageSquare, Pause, Play, RefreshCw, Search, Trash2, X, Zap } from 'lucide-vue-next'
import { RouterLink, useRoute } from 'vue-router'
import { useConfirm } from '../composables/useConfirm'
import { errorText } from '../composables/usePanelAccount'
import { panelRequest } from '../lib/api/communications'
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
type CatalogItem = { name: string; description: string }
const showAdd = ref(false)
const addAccount = ref('')
const catalog = ref<CatalogItem[]>([])
const catalogLoading = ref(false)
const catalogError = ref('')
const catalogStale = ref(false)
const addError = ref('')
const search = ref('')
const visibleCount = ref(24)
const installingName = ref('')
const addButton = ref<HTMLButtonElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
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
const addRuntime = computed(() => accounts.value.find(item => item.account === addAccount.value))
const installedNames = computed(() => new Set(addRuntime.value?.plugins
  .filter(item => item.kind !== 'builtin').map(item => item.name) || []))
const filteredCatalog = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  return catalog.value.filter(item => !term || item.name.toLocaleLowerCase().includes(term) ||
    item.description.toLocaleLowerCase().includes(term))
})
const shownCatalog = computed(() => filteredCatalog.value.slice(0, visibleCount.value))

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
async function loadCatalog() {
  catalogLoading.value = true; catalogError.value = ''
  try {
    const data = await panelRequest<{ items: CatalogItem[]; stale: boolean }>('/telebox/catalog')
    catalog.value = data.items
    catalogStale.value = data.stale
  } catch (cause) { catalogError.value = errorText(cause) }
  finally { catalogLoading.value = false }
}
function openAdd() {
  if (showAdd.value) {
    closeAdd()
    return
  }
  addAccount.value = accounts.value.find(item => item.account === selectedAccount.value)?.account ||
    accounts.value.find(item => item.enabled && item.status === 'running')?.account ||
    accounts.value[0]?.account || ''
  addError.value = ''
  showAdd.value = true
  if (!catalog.value.length) void loadCatalog()
  void nextTick(() => searchInput.value?.focus())
}
function closeAdd() {
  showAdd.value = false
  void nextTick(() => addButton.value?.focus())
}
async function install(item: CatalogItem) {
  const account = addAccount.value
  if (!account || installingName.value || addRuntime.value?.status !== 'running') return
  installingName.value = item.name; addError.value = ''; notice.value = ''
  try {
    const status = await panelRequest<TeleBoxAccount>(`/telebox/${encodeURIComponent(account)}/plugins`, 'POST',
      { action: 'install', name: item.name })
    accounts.value = accounts.value.map(current => current.account === account ? status : current)
    await load(true)
    const triggers = status.automations?.find(plugin => plugin.name === item.name && plugin.source === 'installed')?.triggers || []
    if (triggers.length) {
      selectedAccount.value = account
      notice.value = `已为 ${account} 添加 ${item.name}，${triggerLabel(triggers)}已加载。`
      closeAdd()
    } else {
      addError.value = `${item.name} 已安装，但未检测到已加载的消息监听、事件处理或定时规则，当前不能作为常驻任务。它可能只提供手动命令，请选择带自动触发器的插件。`
    }
  } catch (cause) { addError.value = errorText(cause) }
  finally { installingName.value = '' }
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
        <button ref="addButton" type="button" class="panel-button primary" aria-controls="task-add-panel" :aria-expanded="showAdd" :disabled="loading || !!installingName" @click="openAdd">
          <Zap :size="17" aria-hidden="true" />添加常驻任务
        </button>
      </div>
    </header>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="panel-success" role="status">{{ notice }}</p>
    <section v-if="showAdd" id="task-add-panel" class="panel-card panel-stack" aria-labelledby="task-add-title">
      <div class="panel-row">
        <div class="flex-1 min-w-40"><p class="panel-eyebrow">NEW AUTOMATION</p><h3 id="task-add-title">添加常驻任务</h3></div>
        <button type="button" class="panel-button" :disabled="!!installingName" @click="closeAdd"><X :size="16" aria-hidden="true" />关闭</button>
      </div>
      <p class="panel-muted text-sm">选择账号和插件，安装后由插件内置的消息、事件或定时条件自动触发。安装结果会在下方的常驻插件列表显示。</p>
      <div class="task-add-fields">
        <div><label for="task-add-account" class="font-semibold">运行账号</label>
          <select id="task-add-account" v-model="addAccount" class="panel-input w-full mt-2" :disabled="!!installingName" @change="addError = ''">
            <option v-for="item in accounts" :key="item.account" :value="item.account">{{ item.account }} · {{ item.status }}</option>
          </select>
        </div>
        <div><label for="task-add-search" class="font-semibold">查找插件</label>
          <div class="task-add-search mt-2"><Search :size="17" aria-hidden="true" /><input id="task-add-search" ref="searchInput" v-model="search" type="search" placeholder="搜索名称或功能" :disabled="!!installingName" @input="visibleCount = 24" /></div>
        </div>
      </div>
      <p v-if="!accounts.length" class="panel-empty">请先在账号管理添加并启用 TeleBox 账号。</p>
      <p v-else-if="addRuntime?.status !== 'running'" class="panel-error" role="status">当前账号的 TeleBox 未运行，请先启动后再添加常驻任务。</p>
      <p v-if="addError" class="panel-error" role="alert">{{ addError }}</p>
      <div class="panel-row"><strong>官方插件目录</strong><button type="button" class="panel-button" :disabled="catalogLoading || !!installingName" @click="loadCatalog"><RefreshCw :size="16" aria-hidden="true" />刷新目录</button></div>
      <p v-if="catalogError" class="panel-error" role="alert">{{ catalogError }} <button type="button" class="underline" @click="loadCatalog">重试</button></p>
      <p v-if="catalogStale" class="panel-muted text-sm" role="status">当前展示缓存目录，官方源暂时不可用。</p>
      <p v-if="catalogLoading && !catalog.length" class="panel-empty" role="status">正在加载插件目录…</p>
      <p v-else-if="!filteredCatalog.length && !catalogError" class="panel-empty">没有找到匹配的插件。</p>
      <div v-else-if="shownCatalog.length" class="task-add-list">
        <article v-for="item in shownCatalog" :key="item.name" class="workbench-option task-add-item">
          <div class="flex-1 min-w-0"><strong class="block">{{ item.name }}</strong><p class="panel-muted text-sm">{{ item.description || '官方插件' }}</p></div>
          <span v-if="installedNames.has(item.name)" class="panel-badge">{{ addRuntime?.automations?.some(plugin => plugin.name === item.name && plugin.source === 'installed') ? '已添加' : '已安装 · 未检测到自动触发' }}</span>
          <button v-else type="button" class="panel-button primary" :disabled="!!installingName || addRuntime?.status !== 'running'" :aria-label="`为 ${addAccount} 添加 ${item.name} 常驻任务`" @click="install(item)">{{ installingName === item.name ? '正在安装…' : '添加' }}</button>
        </article>
        <button v-if="shownCatalog.length < filteredCatalog.length" type="button" class="panel-button w-full" @click="visibleCount += 24">显示更多（{{ filteredCatalog.length - shownCatalog.length }}）</button>
      </div>
    </section>
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
      <p v-else-if="!automations.length" class="panel-empty">暂无已加载的常驻插件。点击“添加常驻任务”选择账号和插件。</p>
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

<style scoped>
.task-add-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.task-add-search { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 12px; border: 1px solid var(--sp-border-strong); border-radius: 10px; color: var(--sp-text-muted); background: var(--sp-bg-elevated); }
.task-add-search:focus-within { outline: 2px solid var(--sp-accent); outline-offset: 2px; }
.task-add-search input { width: 100%; min-width: 0; outline: none; color: var(--sp-text); background: transparent; }
.task-add-list { display: grid; gap: 8px; }
.task-add-item { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.task-add-item .panel-button { flex: none; }
@media (max-width: 640px) { .task-add-fields { grid-template-columns: 1fr; } .task-add-item .panel-button { width: 100%; } }
</style>
