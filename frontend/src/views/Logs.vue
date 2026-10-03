<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { errorText } from '../composables/usePanelAccount'
import { panelRequest } from '../lib/api/communications'
import { listTeleBoxAccounts, listTeleBoxTasks, type TeleBoxAccount, type TeleBoxTaskRun } from '../lib/api/telebox-tasks'

type Entry = { time: string; level: string; message: string }
const accounts = ref<TeleBoxAccount[]>([])
const selected = ref('')
const logs = ref<Entry[]>([])
const history = ref<TeleBoxTaskRun[]>([])
const error = ref('')
const loading = ref(false)
let timer: ReturnType<typeof setInterval> | undefined
let generation = 0

async function load() {
  const current = ++generation
  loading.value = true
  try {
    const [overview, tasks] = await Promise.all([listTeleBoxAccounts(), listTeleBoxTasks()])
    if (current !== generation) return
    accounts.value = overview.accounts
    history.value = tasks.history.slice().reverse()
    if (!accounts.value.some(item => item.account === selected.value)) selected.value = accounts.value[0]?.account || ''
    logs.value = selected.value ? (await panelRequest<{ items: Entry[] }>(`/telebox/${encodeURIComponent(selected.value)}/logs`)).items.slice().reverse() : []
    if (current === generation) error.value = ''
  } catch (cause) { if (current === generation) error.value = errorText(cause) }
  finally { if (current === generation) loading.value = false }
}
watch(selected, () => { void load() })
onMounted(() => { void load(); timer = setInterval(() => void load(), 5000) })
onUnmounted(() => { ++generation; if (timer) clearInterval(timer) })
</script>

<template>
  <div class="panel-stack"><section class="panel-card"><div class="panel-row"><div class="flex-1"><p class="panel-eyebrow">TELEBOX / LOGS</p><h2 class="panel-title">运行日志</h2><p class="panel-muted">查看 TeleBox 进程输出和新任务的投递记录。</p></div><button class="panel-button" :disabled="loading" @click="load"><RefreshCw :size="17" />刷新</button></div></section>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <section class="panel-card panel-stack"><h3>TeleBox 进程</h3><label>账号<select v-model="selected" class="panel-input mt-2"><option v-if="!accounts.length" value="">暂无账号</option><option v-for="item in accounts" :key="item.account" :value="item.account">{{ item.account }} · {{ item.status }}</option></select></label><p v-if="!logs.length" class="panel-empty">暂无 TeleBox 日志</p><div class="max-h-[550px] overflow-y-auto panel-stack"><p v-for="(entry, index) in logs" :key="index" class="text-sm break-words border-b border-[var(--sp-border)] pb-2"><time class="panel-muted">{{ new Date(entry.time).toLocaleString() }}</time> · <span :class="entry.level === 'error' ? 'text-rose-600' : ''">{{ entry.message }}</span></p></div></section>
    <section class="panel-card panel-stack"><h3>任务执行</h3><p v-if="!history.length" class="panel-empty">暂无新任务记录</p><p v-for="(entry, index) in history.slice(0, 100)" :key="index" class="text-sm border-b border-[var(--sp-border)] pb-2"><time class="panel-muted">{{ new Date(entry.time).toLocaleString() }}</time> · {{ entry.task }} · <span :class="entry.success ? 'text-emerald-600' : 'text-rose-600'">{{ entry.success ? '成功' : '失败' }}</span><span class="block panel-muted mt-1">{{ entry.message }}</span></p></section>
  </div>
</template>
