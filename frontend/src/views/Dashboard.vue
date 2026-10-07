<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Activity, ArrowRight, ArrowUpRight, CheckCircle2, HardDrive, ImagePlus, RefreshCw, RotateCcw, Users } from 'lucide-vue-next'
import { useAccountsStore } from '../stores/accounts'
import { errorText } from '../composables/usePanelAccount'
import { listTeleBoxAccounts, type TeleBoxAccount } from '../lib/api/telebox'
import { isAccountHealthy } from '../lib/account-list-map'
import type { AccountInfo } from '../lib/api'
import { getMemoryStats } from '../lib/api/ops'
import { getAuthToken } from '../lib/api/core'
import { formatMemoryRssFromStats } from '../lib/memory-format'
import { deleteHeroImage, getHeroImage, MAX_HERO_IMAGE_BYTES, uploadHeroImage } from '../lib/api/appearance'

const store = useAccountsStore()
const telebox = ref<TeleBoxAccount[]>([])
const loading = ref(false)
const error = ref('')
const memoryRss = ref('读取中…')
const memoryStatus = ref('正在获取当前服务进程内存')
const memoryUpdatedAt = ref('')
const heroImageUrl = ref('')
const heroError = ref('')
const heroBusy = ref(false)
const heroInput = ref<HTMLInputElement | null>(null)
let heroObjectUrl = ''
let memoryTimer: ReturnType<typeof setTimeout> | undefined
let memoryInFlight = false
let active = true
const MEMORY_REFRESH_MS = 15_000
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

async function refreshMemory() {
  if (memoryInFlight) return
  memoryInFlight = true
  if (memoryTimer) clearTimeout(memoryTimer)
  try {
    const response = await getMemoryStats(getAuthToken())
    if (!active) return
    const value = response.available ? formatMemoryRssFromStats(response.stats, '') : ''
    memoryRss.value = value || '不可用'
    memoryStatus.value = value ? '当前服务进程 RSS' : '服务未提供内存数据'
    memoryUpdatedAt.value = value ? new Date().toLocaleTimeString() : ''
  } catch {
    if (!active) return
    memoryRss.value = '获取失败'
    memoryStatus.value = '内存数据暂不可用，请稍后刷新'
    memoryUpdatedAt.value = ''
  } finally {
    memoryInFlight = false
    if (active && !document.hidden) memoryTimer = setTimeout(() => void refreshMemory(), MEMORY_REFRESH_MS)
  }
}

function onVisibilityChange() {
  if (document.hidden) {
    if (memoryTimer) clearTimeout(memoryTimer)
    memoryTimer = undefined
  } else if (active) {
    void refreshMemory()
  }
}

function refreshDashboard() {
  void load()
  void refreshMemory()
}

function showHeroBlob(blob: Blob) {
  if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
  heroObjectUrl = URL.createObjectURL(blob)
  heroImageUrl.value = heroObjectUrl
}

async function loadHeroImage() {
  try {
    const blob = await getHeroImage()
    if (active) showHeroBlob(blob)
  } catch (cause) {
    if (active && (cause as { status?: number }).status !== 404) heroError.value = '封面读取失败，请稍后重试'
  }
}

async function onHeroSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > MAX_HERO_IMAGE_BYTES || file.size === 0) {
    heroError.value = '请选择不超过 5 MB 的 JPEG、PNG 或 WebP 图片'
    return
  }
  heroBusy.value = true
  heroError.value = ''
  try {
    await uploadHeroImage(file)
    const blob = await getHeroImage()
    if (active) showHeroBlob(blob)
  } catch {
    heroError.value = '封面上传失败，请稍后重试'
  } finally {
    heroBusy.value = false
  }
}

async function resetHeroImage() {
  heroBusy.value = true
  heroError.value = ''
  try {
    await deleteHeroImage()
    if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
    heroObjectUrl = ''
    heroImageUrl.value = ''
  } catch {
    heroError.value = '恢复默认封面失败，请稍后重试'
  } finally {
    heroBusy.value = false
  }
}

onMounted(() => {
  active = true
  document.addEventListener('visibilitychange', onVisibilityChange)
  void load()
  void loadHeroImage()
  if (!document.hidden) void refreshMemory()
})
onUnmounted(() => {
  active = false
  document.removeEventListener('visibilitychange', onVisibilityChange)
  if (memoryTimer) clearTimeout(memoryTimer)
  if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
})
</script>
<template>
  <div class="dashboard panel-stack" :aria-busy="loading">
    <section class="dashboard-hero" :class="{ 'dashboard-hero--custom': !!heroImageUrl }">
      <div v-if="heroImageUrl" class="dashboard-hero-image" :style="{ backgroundImage: `url('${heroImageUrl}')` }" aria-hidden="true" />
      <div class="dashboard-hero-copy">
        <h2>一眼掌握，<br><span>每一次运行。</span></h2>
        <p>账号与 TeleBox 状态汇聚于此。需要处理的变化，随时清晰可见。</p>
        <div class="dashboard-hero-actions">
          <RouterLink to="/accounts" class="dashboard-hero-primary">管理账号 <ArrowUpRight :size="17" aria-hidden="true" /></RouterLink>
          <button type="button" class="dashboard-hero-refresh" :disabled="loading" @click="refreshDashboard"><RefreshCw :size="16" :class="{ 'animate-spin': loading }" aria-hidden="true" />{{ loading ? '正在刷新' : '刷新数据' }}</button>
        </div>
      </div>
      <div v-if="!heroImageUrl" class="dashboard-hero-visual" aria-hidden="true"><div class="dashboard-orbit dashboard-orbit--outer" /><div class="dashboard-orbit dashboard-orbit--inner" /><div class="dashboard-core"><Activity :size="42" :stroke-width="1.4" /></div><span class="dashboard-satellite dashboard-satellite--one" /><span class="dashboard-satellite dashboard-satellite--two" /></div>
      <div class="dashboard-hero-customize">
        <input ref="heroInput" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" tabindex="-1" aria-label="选择仪表盘封面图片" @change="onHeroSelected" />
        <button type="button" :disabled="heroBusy" @click="heroInput?.click()"><ImagePlus :size="16" aria-hidden="true" />{{ heroImageUrl ? '更换封面' : '上传封面' }}</button>
        <button v-if="heroImageUrl" type="button" :disabled="heroBusy" @click="resetHeroImage"><RotateCcw :size="15" aria-hidden="true" />恢复默认</button>
      </div>
    </section>
    <p v-if="heroError" class="panel-error" role="alert">{{ heroError }}</p>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <section aria-label="运行概览" class="dashboard-metrics">
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--accounts"><span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Users :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span><span class="dashboard-metric-value">{{ store.accounts.length }}</span><span class="dashboard-metric-label">已登录账号</span><span class="dashboard-metric-foot">查看账号 <ArrowRight :size="14" aria-hidden="true" /></span></RouterLink>
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--telebox"><span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Activity :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span><span class="dashboard-metric-value">{{ runningCount }}</span><span class="dashboard-metric-label">运行中的 TeleBox</span><span class="dashboard-metric-foot">管理账号 <ArrowRight :size="14" aria-hidden="true" /></span></RouterLink>
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--tasks"><span class="dashboard-metric-top"><span class="dashboard-metric-icon"><CheckCircle2 :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span><span class="dashboard-metric-value">{{ healthyCount }}</span><span class="dashboard-metric-label">状态正常的账号</span><span class="dashboard-metric-foot">查看状态 <ArrowRight :size="14" aria-hidden="true" /></span></RouterLink>
      <div class="dashboard-metric dashboard-metric--memory" aria-label="当前服务进程内存">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><HardDrive :size="21" aria-hidden="true" /></span><span class="dashboard-live-badge">每 15 秒更新</span></span>
        <span class="dashboard-metric-value dashboard-memory-value">{{ memoryRss }}</span>
        <span class="dashboard-metric-label">当前服务进程 RSS</span>
        <span class="dashboard-metric-foot">{{ memoryStatus }}<span v-if="memoryUpdatedAt"> · {{ memoryUpdatedAt }}</span></span>
      </div>
    </section>
    <section class="dashboard-activity panel-card" aria-labelledby="recent-activity-title">
      <div class="dashboard-section-heading"><div><p class="panel-eyebrow">ACCOUNTS / 健康状态</p><h3 id="recent-activity-title">需要关注的账号</h3></div><RouterLink to="/accounts" class="panel-button">查看全部账号 <ArrowRight :size="16" aria-hidden="true" /></RouterLink></div>
      <div v-if="loading && !store.accounts.length" class="dashboard-activity-loading" role="status">正在读取账号状态…</div>
      <div v-else-if="!attention.length" class="dashboard-activity-empty"><CheckCircle2 :size="26" aria-hidden="true" /><strong>目前没有异常账号</strong><span>账号状态变化会在这里显示。</span></div>
      <ol v-else class="dashboard-activity-list"><li v-for="item in attention" :key="item.name" class="dashboard-activity-item"><span class="dashboard-activity-icon is-error"><Activity :size="19" aria-hidden="true" /></span><span class="dashboard-activity-name">{{ item.name }}</span><span class="dashboard-activity-state is-error">{{ attentionReason(item) }}</span></li></ol>
    </section>
  </div>
</template>
