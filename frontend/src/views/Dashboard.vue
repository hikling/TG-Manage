<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Activity, ArrowRight, ArrowUpRight, CheckCircle2, Clock3, Puzzle, RefreshCw, Users, XCircle } from 'lucide-vue-next'
import { useAccountsStore } from '../stores/accounts'
import { errorText } from '../composables/usePanelAccount'
import { listTeleBoxAccounts, listTeleBoxTasks, type TeleBoxAccount, type TeleBoxTask, type TeleBoxTaskRun } from '../lib/api/telebox-tasks'

const store = useAccountsStore()
const telebox = ref<TeleBoxAccount[]>([])
const tasks = ref<TeleBoxTask[]>([])
const history = ref<TeleBoxTaskRun[]>([])
const loading = ref(false)
const error = ref('')
const runningCount = computed(() => telebox.value.filter(item => item.status === 'running').length)
const enabledCount = computed(() => tasks.value.filter(item => item.enabled).length)
const recentHistory = computed(() => history.value.slice(0, 8))
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
  <div class="dashboard panel-stack" :aria-busy="loading">
    <section class="dashboard-hero">
      <div class="dashboard-hero-copy">
        <p class="dashboard-kicker"><span class="dashboard-kicker-dot" /> TG SIGNPULSE / CONTROL CENTER</p>
        <h2>一眼掌握，<br><span>每一次运行。</span></h2>
        <p>账号、插件和任务状态汇聚于此。需要处理的变化，随时清晰可见。</p>
        <div class="dashboard-hero-actions">
          <RouterLink to="/workbench" class="dashboard-hero-primary">进入账号工作台 <ArrowUpRight :size="17" aria-hidden="true" /></RouterLink>
          <button type="button" class="dashboard-hero-refresh" :disabled="loading" @click="load">
            <RefreshCw :size="16" :class="{ 'animate-spin': loading }" aria-hidden="true" />
            {{ loading ? '正在刷新' : '刷新数据' }}
          </button>
        </div>
      </div>
      <div class="dashboard-hero-visual" aria-hidden="true">
        <div class="dashboard-orbit dashboard-orbit--outer" />
        <div class="dashboard-orbit dashboard-orbit--inner" />
        <div class="dashboard-core"><Activity :size="42" :stroke-width="1.4" /></div>
        <span class="dashboard-satellite dashboard-satellite--one" />
        <span class="dashboard-satellite dashboard-satellite--two" />
      </div>
    </section>

    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>

    <section aria-label="运行概览" class="dashboard-metrics">
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--accounts">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Users :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span>
        <span class="dashboard-metric-value">{{ store.accounts.length }}</span>
        <span class="dashboard-metric-label">已登录账号</span>
        <span class="dashboard-metric-foot">查看账号 <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
      <RouterLink to="/telebox" class="dashboard-metric dashboard-metric--telebox">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Puzzle :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span>
        <span class="dashboard-metric-value">{{ runningCount }}</span>
        <span class="dashboard-metric-label">运行中的 TeleBox</span>
        <span class="dashboard-metric-foot">管理插件 <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
      <RouterLink to="/tasks" class="dashboard-metric dashboard-metric--tasks">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Clock3 :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span>
        <span class="dashboard-metric-value">{{ enabledCount }}</span>
        <span class="dashboard-metric-label">启用的任务</span>
        <span class="dashboard-metric-foot">查看任务 <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
    </section>

    <section class="dashboard-activity panel-card" aria-labelledby="recent-activity-title">
      <div class="dashboard-section-heading">
        <div><p class="panel-eyebrow">ACTIVITY / 近期动态</p><h3 id="recent-activity-title">最近任务执行</h3></div>
        <RouterLink to="/logs" class="panel-button">查看全部日志 <ArrowRight :size="16" aria-hidden="true" /></RouterLink>
      </div>
      <div v-if="loading && !recentHistory.length" class="dashboard-activity-loading" role="status">正在读取任务记录…</div>
      <div v-else-if="!recentHistory.length" class="dashboard-activity-empty"><Activity :size="26" aria-hidden="true" /><strong>暂无任务记录</strong><span>任务执行后，最近的结果会显示在这里。</span></div>
      <ol v-else class="dashboard-activity-list">
        <li v-for="(entry, index) in recentHistory" :key="index" class="dashboard-activity-item">
          <span class="dashboard-activity-icon" :class="entry.success ? 'is-success' : 'is-error'">
            <CheckCircle2 v-if="entry.success" :size="19" aria-hidden="true" /><XCircle v-else :size="19" aria-hidden="true" />
          </span>
          <span class="dashboard-activity-name">{{ entry.task }}</span>
          <span class="dashboard-activity-state" :class="entry.success ? 'is-success' : 'is-error'">{{ entry.success ? '成功' : '失败' }}</span>
          <time class="dashboard-activity-time" :datetime="entry.time">{{ new Date(entry.time).toLocaleString() }}</time>
        </li>
      </ol>
    </section>
  </div>
</template>
