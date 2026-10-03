<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { RefreshCw, Users, Puzzle, Clock3 } from 'lucide-vue-next'
import { useAccountsStore } from '../stores/accounts'
import { errorText } from '../composables/usePanelAccount'
import { listTeleBoxAccounts, listTeleBoxTasks, type TeleBoxAccount, type TeleBoxTask, type TeleBoxTaskRun } from '../lib/api/telebox-tasks'

const store = useAccountsStore()
const telebox = ref<TeleBoxAccount[]>([])
const tasks = ref<TeleBoxTask[]>([])
const history = ref<TeleBoxTaskRun[]>([])
const loading = ref(false)
const error = ref('')
async function load() {
  loading.value = true
  try {
    const [accounts, taskData] = await Promise.all([listTeleBoxAccounts(), listTeleBoxTasks(), store.ensureAccounts(true)])
    telebox.value = accounts.accounts
    tasks.value = taskData.items
    history.value = taskData.history.slice().reverse()
    error.value = ''
  } catch (cause) { error.value = errorText(cause) }
  finally { loading.value = false }
}
onMounted(() => void load())
</script>
<template>
  <div class="panel-stack"><section class="panel-card"><div class="panel-row"><div class="flex-1"><p class="panel-eyebrow">OVERVIEW</p><h2 class="panel-title">账号概览</h2><p class="panel-muted">Telegram 账号、TeleBox 运行状态与新任务执行情况。</p></div><button class="panel-button" :disabled="loading" @click="load"><RefreshCw :size="17" />刷新</button></div></section>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <div class="panel-columns"><RouterLink to="/accounts" class="panel-card"><Users :size="23" /><p class="panel-muted mt-4">已登录账号</p><strong class="text-3xl">{{ store.accounts.length }}</strong></RouterLink><RouterLink to="/telebox" class="panel-card"><Puzzle :size="23" /><p class="panel-muted mt-4">运行中的 TeleBox</p><strong class="text-3xl">{{ telebox.filter(item => item.status === 'running').length }}</strong></RouterLink><RouterLink to="/tasks" class="panel-card"><Clock3 :size="23" /><p class="panel-muted mt-4">启用的任务</p><strong class="text-3xl">{{ tasks.filter(item => item.enabled).length }}</strong></RouterLink></div>
    <section class="panel-card panel-stack"><div class="panel-row"><h3>最近任务执行</h3><RouterLink class="panel-button" to="/logs">查看日志</RouterLink></div><p v-if="!history.length" class="panel-empty">暂无新任务记录</p><p v-for="(entry, index) in history.slice(0, 8)" :key="index" class="text-sm border-b border-[var(--sp-border)] pb-2">{{ entry.task }} · <span :class="entry.success ? 'text-emerald-600' : 'text-rose-600'">{{ entry.success ? '成功' : '失败' }}</span> <time class="panel-muted">{{ new Date(entry.time).toLocaleString() }}</time></p></section>
  </div>
</template>
