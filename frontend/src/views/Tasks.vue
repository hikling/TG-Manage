<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Clock3, Pause, Play, Plus, RefreshCw, Trash2, X } from 'lucide-vue-next'
import { useRoute } from 'vue-router'
import { useConfirm } from '../composables/useConfirm'
import { errorText } from '../composables/usePanelAccount'
import {
  createTeleBoxTask, deleteTeleBoxTask, listTeleBoxAccounts, listTeleBoxTasks,
  runTeleBoxTask, updateTeleBoxTask,
  type TeleBoxAccount, type TeleBoxTask, type TeleBoxTaskRun, type TaskInput,
} from '../lib/api/telebox-tasks'

const route = useRoute()
const { confirm } = useConfirm()
const tasks = ref<TeleBoxTask[]>([])
const history = ref<TeleBoxTaskRun[]>([])
const accounts = ref<TeleBoxAccount[]>([])
const error = ref('')
const notice = ref('')
const loading = ref(false)
const busy = ref(false)
const adding = ref(false)
const editing = ref<string | null>(null)
const account = ref('')
const command = ref('')
const name = ref('')
const args = ref('')
const current = computed(() => accounts.value.find(item => item.account === account.value))
const commands = computed(() => current.value?.commands ?? [])
const accountOptions = computed(() => accounts.value.filter(item => item.enabled))
const commandOptions = computed(() => {
  return commands.value.filter(item => (item.source === 'installed' || (item.source === 'builtin' && item.plugin === 'kitt')) &&
    /^[A-Za-z0-9_-]{1,80}$/.test(item.plugin) && item.command.length <= 80 && !/[\x00-\x1f\x7f]/.test(item.command))
})

async function load() {
  loading.value = true
  try {
    const [taskData, accountData] = await Promise.all([listTeleBoxTasks(), listTeleBoxAccounts()])
    tasks.value = taskData.items
    history.value = taskData.history.slice().reverse()
    accounts.value = accountData.accounts
    error.value = ''
  } catch (cause) { error.value = errorText(cause) }
  finally { loading.value = false }
}

async function openCreate() {
  await load()
  if (error.value) return
  editing.value = null
  const requested = typeof route.query.account === 'string' ? route.query.account : ''
  account.value = accountOptions.value.find(item => item.account === requested)?.account || accountOptions.value[0]?.account || ''
  command.value = ''
  name.value = ''
  args.value = ''
  adding.value = true
}

async function openEdit(task: TeleBoxTask) {
  if (task.kind !== 'plugin') return
  await load()
  if (error.value) return
  editing.value = task.id
  account.value = task.accounts[0] || ''
  command.value = String(commandOptions.value.findIndex(item => item.plugin === task.plugin && item.command === task.command))
  name.value = task.name
  args.value = task.args
  adding.value = true
}

async function submit() {
  if (busy.value) return
  const selected = commandOptions.value[Number(command.value)]
  if (!current.value || current.value.status !== 'running' || !selected ||
      !commands.value.some(item => item.plugin === selected.plugin && item.command === selected.command)) {
    error.value = '请先运行该账号的 TeleBox 并选择已加载的插件命令'
    return
  }
  busy.value = true; error.value = ''; notice.value = ''
  const payload: TaskInput = {
    name: name.value.trim(), kind: 'plugin', accounts: [account.value],
    time: null, enabled: editing.value ? tasks.value.find(task => task.id === editing.value)?.enabled ?? true : true,
    plugin: selected.plugin, command: selected.command, args: args.value.trim(), chats: [], text: '',
  }
  try {
    if (editing.value) await updateTeleBoxTask(editing.value, payload)
    else await createTeleBoxTask(payload)
    adding.value = false
    notice.value = 'TeleBox 任务已保存'
    await load()
  } catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
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
  if (!await confirm({ title: '删除任务', message: `删除「${task.name}」？已有运行记录会保留。`, danger: true })) return
  busy.value = true; error.value = ''
  try { await deleteTeleBoxTask(task.id); await load() }
  catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
async function run(task: TeleBoxTask) {
  if (!await confirm({ title: '立即执行任务', message: `现在执行「${task.name}」？` })) return
  busy.value = true; error.value = ''
  try {
    const result = await runTeleBoxTask(task.id)
    notice.value = result.message
    await load()
  } catch (cause) { error.value = errorText(cause) }
  finally { busy.value = false }
}
onMounted(() => void load())
</script>

<template>
  <div class="panel-stack">
    <header class="panel-card">
      <p class="panel-eyebrow">TELEBOX / AUTOMATION</p>
      <div class="panel-row"><div class="flex-1"><h2 class="panel-title">任务编排</h2><p class="panel-muted">只使用当前账号已加载的 TeleBox 插件命令。工作台创建的每日群消息也显示在这里。</p></div><button class="panel-button" :disabled="loading" @click="load"><RefreshCw :size="17" />刷新</button><button class="panel-button primary" :disabled="loading" @click="openCreate"><Plus :size="17" />添加任务</button></div>
    </header>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="panel-success" role="status">{{ notice }}</p>

    <section v-if="adding" class="panel-card panel-stack" aria-label="TeleBox 任务编辑">
      <div class="panel-row"><h3>{{ editing ? '编辑 TeleBox 任务' : '添加 TeleBox 任务' }}</h3><button class="panel-button" aria-label="关闭任务编辑" @click="adding = false"><X :size="17" /></button></div>
      <p v-if="!accountOptions.length" class="panel-empty">没有启用 TeleBox 的账号。请先在账号管理登录并启用 TeleBox。</p>
      <form v-else class="panel-stack" @submit.prevent="submit">
        <label>运行账号<select v-model="account" class="panel-input mt-2" :disabled="busy" @change="command = ''"><option v-for="item in accountOptions" :key="item.account" :value="item.account">{{ item.account }} · {{ item.status }}</option></select></label>
        <p v-if="current?.status !== 'running'" class="panel-error">此账号的 TeleBox 尚未运行，请到拓展插件检查启动状态。</p>
        <label>插件命令<select v-model="command" class="panel-input mt-2" required :disabled="busy || current?.status !== 'running'"><option value="" disabled>选择当前账号已加载的命令</option><option v-for="(item, index) in commandOptions" :key="item.plugin + ':' + item.command" :value="String(index)">{{ item.plugin }} · {{ item.command }}</option></select></label>
        <p v-if="current?.status === 'running' && !commandOptions.length" class="panel-muted">该账号暂无 KITT 或新安装插件的可用命令。安装或重载插件后点击“添加任务”重新识别。</p>
        <label>任务名称<input v-model="name" class="panel-input mt-2" required maxlength="80" :disabled="busy" placeholder="例如：插件指令" /></label>
        <label>命令参数（可选）<input v-model="args" class="panel-input mt-2" maxlength="500" :disabled="busy" placeholder="按插件命令格式填写" /></label>
        <p class="panel-muted text-sm">保存后可手动执行命令；插件自行管理的定时规则由 TeleBox 运行。插件输出请查看 TeleBox 日志。</p>
        <div class="panel-row"><button class="panel-button primary" :disabled="busy || current?.status !== 'running' || !commandOptions.length">{{ busy ? '保存中…' : '保存任务' }}</button></div>
      </form>
    </section>

    <section class="panel-card panel-stack"><div class="panel-row"><h3>任务列表</h3><span class="panel-badge">{{ tasks.length }} 项</span></div>
      <p v-if="loading" class="panel-empty" role="status">正在读取任务…</p><p v-else-if="!tasks.length" class="panel-empty">暂无任务。点击“添加任务”选择已加载的插件命令。</p>
      <article v-for="task in tasks" :key="task.id" class="workbench-option flex-wrap">
        <span class="workbench-step"><Clock3 :size="17" /></span><div class="flex-1 min-w-40"><strong class="block">{{ task.name }}</strong><p class="panel-muted text-sm">{{ task.accounts.join('、') }} · {{ task.kind === 'plugin' ? task.plugin + ' / ' + task.command + ' · 手动执行' : '每日 ' + task.time + ' · ' + task.chats.length + ' 个群会话' }}</p></div><span class="panel-badge">{{ task.enabled ? '已启用' : '已暂停' }}</span>
        <div class="panel-row"><button v-if="task.kind === 'plugin'" class="panel-button" :disabled="busy" @click="openEdit(task)">编辑</button><button class="panel-button" :disabled="busy" @click="toggle(task)"><Pause v-if="task.enabled" :size="15" /><Play v-else :size="15" />{{ task.enabled ? '暂停' : '启用' }}</button><button class="panel-button" :disabled="busy" @click="run(task)">执行一次</button><button class="panel-button danger" :disabled="busy" :aria-label="'删除 ' + task.name" @click="remove(task)"><Trash2 :size="15" /></button></div>
      </article>
    </section>
    <section class="panel-card panel-stack"><h3>最近执行</h3><p v-if="!history.length" class="panel-empty">暂无运行记录</p><p v-for="(entry, index) in history.slice(0, 30)" :key="index" class="text-sm border-b border-[var(--sp-border)] pb-3"><time class="panel-muted">{{ new Date(entry.time).toLocaleString() }}</time> · {{ entry.task }} · <span :class="entry.success ? 'text-emerald-600' : 'text-rose-600'">{{ entry.success ? '成功' : '失败' }}</span><span class="block panel-muted mt-1">{{ entry.message }}</span></p></section>
  </div>
</template>
