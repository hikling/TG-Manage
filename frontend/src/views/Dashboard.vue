<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Activity, ArrowRight, ArrowUpRight, CheckCircle2, RefreshCw, Users } from 'lucide-vue-next'
import { useAccountsStore } from '../stores/accounts'
import { errorText } from '../composables/usePanelAccount'
import { listTeleBoxAccounts, type TeleBoxAccount } from '../lib/api/telebox'
import { isAccountHealthy } from '../lib/account-list-map'
import type { AccountInfo } from '../lib/api'

const store = useAccountsStore()
const telebox = ref<TeleBoxAccount[]>([])
const loading = ref(false)
const error = ref('')
const runningCount = computed(() => telebox.value.filter(item => item.status === 'running').length)
const healthyCount = computed(() => store.accounts.filter(isAccountHealthy).length)
const attention = computed(() => store.accounts.filter(item => !isAccountHealthy(item)).slice(0, 8))

function attentionReason(item: AccountInfo): string {
  if (item.status_message) return item.status_message
  if (item.needs_relogin || item.status === 'invalid') return '需要重新登录'
  if (item.status === 'checking') return '检测中'
  return item.status === 'error' ? '状态异常' : '待检测'
}

async function load() {
  loading.value = true
  try {
    const [accounts] = await Promise.all([listTeleBoxAccounts(), store.ensureAccounts(true)])
    telebox.value = accounts.accounts
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
        <p>账号与 TeleBox 状态汇聚于此。需要处理的变化，随时清晰可见。</p>
        <div class="dashboard-hero-actions">
          <RouterLink to="/accounts" class="dashboard-hero-primary">管理账号 <ArrowUpRight :size="17" aria-hidden="true" /></RouterLink>
          <button type="button" class="dashboard-hero-refresh" :disabled="loading" @click="load"><RefreshCw :size="16" :class="{ 'animate-spin': loading }" aria-hidden="true" />{{ loading ? '正在刷新' : '刷新数据' }}</button>
        </div>
      </div>
      <div class="dashboard-hero-visual" aria-hidden="true"><div class="dashboard-orbit dashboard-orbit--outer" /><div class="dashboard-orbit dashboard-orbit--inner" /><div class="dashboard-core"><Activity :size="42" :stroke-width="1.4" /></div><span class="dashboard-satellite dashboard-satellite--one" /><span class="dashboard-satellite dashboard-satellite--two" /></div>
    </section>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <section aria-label="运行概览" class="dashboard-metrics">
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--accounts"><span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Users :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span><span class="dashboard-metric-value">{{ store.accounts.length }}</span><span class="dashboard-metric-label">已登录账号</span><span class="dashboard-metric-foot">查看账号 <ArrowRight :size="14" aria-hidden="true" /></span></RouterLink>
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--telebox"><span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Activity :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span><span class="dashboard-metric-value">{{ runningCount }}</span><span class="dashboard-metric-label">运行中的 TeleBox</span><span class="dashboard-metric-foot">管理账号 <ArrowRight :size="14" aria-hidden="true" /></span></RouterLink>
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--tasks"><span class="dashboard-metric-top"><span class="dashboard-metric-icon"><CheckCircle2 :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span><span class="dashboard-metric-value">{{ healthyCount }}</span><span class="dashboard-metric-label">状态正常的账号</span><span class="dashboard-metric-foot">查看状态 <ArrowRight :size="14" aria-hidden="true" /></span></RouterLink>
    </section>
    <section class="dashboard-activity panel-card" aria-labelledby="recent-activity-title">
      <div class="dashboard-section-heading"><div><p class="panel-eyebrow">ACCOUNTS / 健康状态</p><h3 id="recent-activity-title">需要关注的账号</h3></div><RouterLink to="/accounts" class="panel-button">查看全部账号 <ArrowRight :size="16" aria-hidden="true" /></RouterLink></div>
      <div v-if="loading && !store.accounts.length" class="dashboard-activity-loading" role="status">正在读取账号状态…</div>
      <div v-else-if="!attention.length" class="dashboard-activity-empty"><CheckCircle2 :size="26" aria-hidden="true" /><strong>目前没有异常账号</strong><span>账号状态变化会在这里显示。</span></div>
      <ol v-else class="dashboard-activity-list"><li v-for="item in attention" :key="item.name" class="dashboard-activity-item"><span class="dashboard-activity-icon is-error"><Activity :size="19" aria-hidden="true" /></span><span class="dashboard-activity-name">{{ item.name }}</span><span class="dashboard-activity-state is-error">{{ attentionReason(item) }}</span></li></ol>
    </section>
  </div>
</template>
