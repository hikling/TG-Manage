<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Activity, ArrowRight, ArrowUpRight, CheckCircle2, HardDrive, Users } from 'lucide-vue-next'
import { useI18n } from '../composables/useI18n'
import { errorText } from '../composables/usePanelAccount'
import { getHeroImage, getHeroSettings } from '../lib/api/appearance'
import { getAuthToken } from '../lib/api/core'
import { getMemoryStats } from '../lib/api/ops'
import { listTeleBoxAccounts, type TeleBoxAccount } from '../lib/api/telebox'
import { isAccountHealthy } from '../lib/account-list-map'
import type { AccountInfo } from '../lib/api'
import { formatMemoryRssFromStats } from '../lib/memory-format'
import { clampCoverPosition } from '../lib/cover-frame'
import { useAccountsStore } from '../stores/accounts'
import HeroCover from '../components/HeroCover.vue'

const { t } = useI18n()
const store = useAccountsStore()
const telebox = ref<TeleBoxAccount[]>([])
const loading = ref(false)
const error = ref('')
const memoryRss = ref('')
const memoryStatusKey = ref<'memoryReading' | 'memoryCurrent' | 'memoryUnavailable' | 'memoryFailed'>('memoryReading')
const memoryUpdatedAt = ref('')
const heroImageUrl = ref('')
const heroPositionX = ref(50)
const heroPositionY = ref(50)

let heroObjectUrl = ''
let heroRequest: Promise<void> | undefined
let heroReloadPending = false
let dashboardRequest: Promise<void> | undefined
let memoryTimer: ReturnType<typeof setTimeout> | undefined
let memoryInFlight = false
let active = true
let heroPositionEdited = false
const MEMORY_REFRESH_MS = 15_000

const runningCount = computed(() => telebox.value.filter(item => item.status === 'running').length)
const healthyCount = computed(() => store.accounts.filter(isAccountHealthy).length)
const attention = computed(() => store.accounts.filter(item => !isAccountHealthy(item)).slice(0, 8))

function attentionReason(item: AccountInfo): string {
  if (item.status_message) return item.status_message
  if (item.needs_relogin || item.status === 'invalid') return t('dashboard.attentionRelogin')
  if (item.status === 'checking') return t('dashboard.attentionChecking')
  return item.status === 'error' ? t('dashboard.attentionError') : t('dashboard.attentionPending')
}

async function fetchDashboardData() {
  const [teleboxResult, accountsResult] = await Promise.allSettled([
    listTeleBoxAccounts(),
    store.ensureAccounts(true),
  ])
  if (!active) return
  const failures: string[] = []
  if (teleboxResult.status === 'fulfilled') telebox.value = teleboxResult.value.accounts || []
  else failures.push(errorText(teleboxResult.reason))
  if (accountsResult.status === 'rejected') failures.push(errorText(accountsResult.reason))
  error.value = failures[0] || ''
}

function loadDashboardData(): Promise<void> {
  if (dashboardRequest) return dashboardRequest
  loading.value = true
  dashboardRequest = fetchDashboardData().finally(() => {
    dashboardRequest = undefined
    if (active) loading.value = false
  })
  return dashboardRequest
}

async function refreshMemory() {
  if (memoryInFlight) return
  memoryInFlight = true
  if (memoryTimer) clearTimeout(memoryTimer)
  try {
    memoryStatusKey.value = 'memoryReading'
    const response = await getMemoryStats(getAuthToken())
    if (!active) return
    const value = response.available ? formatMemoryRssFromStats(response.stats, '') : ''
    memoryRss.value = value
    memoryStatusKey.value = value ? 'memoryCurrent' : 'memoryUnavailable'
    memoryUpdatedAt.value = value ? new Date().toLocaleTimeString() : ''
  } catch {
    if (!active) return
    memoryRss.value = ''
    memoryStatusKey.value = 'memoryFailed'
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

function showHeroBlob(blob: Blob) {
  if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
  heroObjectUrl = URL.createObjectURL(blob)
  heroImageUrl.value = heroObjectUrl
}

async function fetchHeroImage() {
  try {
    const [blob, settings] = await Promise.all([getHeroImage(), getHeroSettings()])
    if (active) {
      if (!heroPositionEdited) {
        heroPositionX.value = settings.position_x
        heroPositionY.value = settings.position_y
      }
      showHeroBlob(blob)
    }
  } catch {
    if (active) {
      if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
      heroObjectUrl = ''
      heroImageUrl.value = ''
      heroPositionX.value = 50
      heroPositionY.value = 50
    }
  }
}

function loadHeroImage(): Promise<void> {
  if (heroRequest) return heroRequest
  heroRequest = fetchHeroImage().finally(() => {
    heroRequest = undefined
    if (heroReloadPending && active) {
      heroReloadPending = false
      void loadHeroImage()
    }
  })
  return heroRequest
}

function onHeroChanged() {
  if (heroRequest) heroReloadPending = true
  else void loadHeroImage()
}

function onHeroPositionChanged(event: Event) {
  heroPositionEdited = true
  const detail = (event as CustomEvent<{ x: number; y: number }>).detail
  heroPositionX.value = clampCoverPosition(detail.x)
  heroPositionY.value = clampCoverPosition(detail.y)
}


onMounted(() => {
  active = true
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('tg-manage:hero-changed', onHeroChanged)
  window.addEventListener('tg-manage:hero-position-changed', onHeroPositionChanged)
  void loadDashboardData()
  void loadHeroImage()
  if (!document.hidden) void refreshMemory()
})

onUnmounted(() => {
  active = false
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('tg-manage:hero-changed', onHeroChanged)
  window.removeEventListener('tg-manage:hero-position-changed', onHeroPositionChanged)
  if (memoryTimer) clearTimeout(memoryTimer)
  if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
})
</script>

<template>
  <div class="dashboard panel-stack" :aria-busy="loading">
    <section class="dashboard-hero" aria-hidden="true">
      <HeroCover v-if="heroImageUrl" :src="heroImageUrl" :position-x="heroPositionX" :position-y="heroPositionY" />
    </section>

    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>

    <section :aria-label="t('dashboard.overview')" class="dashboard-metrics">
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--accounts">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Users :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span>
        <span class="dashboard-metric-value">{{ store.accounts.length }}</span><span class="dashboard-metric-label">{{ t('dashboard.loggedAccounts') }}</span><span class="dashboard-metric-foot">{{ t('dashboard.viewAccounts') }} <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--telebox">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Activity :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span>
        <span class="dashboard-metric-value">{{ runningCount }}</span><span class="dashboard-metric-label">{{ t('dashboard.runningTelebox') }}</span><span class="dashboard-metric-foot">{{ t('dashboard.manageAccounts') }} <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--tasks">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><CheckCircle2 :size="21" aria-hidden="true" /></span><ArrowUpRight :size="18" aria-hidden="true" /></span>
        <span class="dashboard-metric-value">{{ healthyCount }}</span><span class="dashboard-metric-label">{{ t('dashboard.healthyAccounts') }}</span><span class="dashboard-metric-foot">{{ t('dashboard.viewStatus') }} <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
      <div class="dashboard-metric dashboard-metric--memory" :aria-label="t('dashboard.memoryAriaLabel')">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><HardDrive :size="21" aria-hidden="true" /></span><span class="dashboard-live-badge">{{ t('dashboard.memoryLive') }}</span></span>
        <span class="dashboard-metric-value dashboard-memory-value">{{ memoryRss || t('dashboard.memoryUnavailableValue') }}</span>
        <span class="dashboard-metric-label">{{ t('dashboard.memoryLabel') }}</span><span class="dashboard-metric-foot">{{ t(`dashboard.${memoryStatusKey}`) }}<span v-if="memoryUpdatedAt">  /  {{ memoryUpdatedAt }}</span></span>
      </div>
    </section>

    <section class="dashboard-activity panel-card" aria-labelledby="dashboard-attention-title">
      <div class="dashboard-section-heading"><h3 id="dashboard-attention-title">{{ t('dashboard.attentionTitle') }}</h3><RouterLink to="/accounts" class="panel-button">{{ t('dashboard.viewAllAccounts') }} <ArrowRight :size="16" aria-hidden="true" /></RouterLink></div>
      <div v-if="loading && !store.accounts.length" class="dashboard-activity-loading" role="status">{{ t('dashboard.attentionLoading') }}</div>
      <div v-else-if="!attention.length" class="dashboard-activity-empty"><CheckCircle2 :size="26" aria-hidden="true" /><strong>{{ t('dashboard.attentionEmpty') }}</strong><span>{{ t('dashboard.attentionEmptyHint') }}</span></div>
      <ol v-else class="dashboard-activity-list"><li v-for="item in attention" :key="item.name" class="dashboard-activity-item"><span class="dashboard-activity-icon is-error"><Activity :size="19" aria-hidden="true" /></span><span class="dashboard-activity-name">{{ item.name }}</span><span class="dashboard-activity-state is-error">{{ attentionReason(item) }}</span></li></ol>
    </section>
  </div>
</template>
