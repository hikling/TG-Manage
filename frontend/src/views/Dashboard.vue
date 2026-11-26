<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
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
import { useAuthStore } from '../stores/auth'
import HeroCover from '../components/HeroCover.vue'

const { t } = useI18n()
const store = useAccountsStore()
const auth = useAuthStore()
const telebox = ref<TeleBoxAccount[]>([])
const loading = ref(false)
const error = ref('')
const accountsFailure = ref<{ cause: unknown } | null>(null)
const accountsError = computed(() => accountsFailure.value ? errorText(accountsFailure.value.cause) : '')
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
let accountsRequest: Promise<void> | undefined
let accountsTimer: ReturnType<typeof setTimeout> | undefined
let accountsGeneration = 0
let accountsRefreshPending = false
let memoryTimer: ReturnType<typeof setTimeout> | undefined
let memoryInFlight = false
let active = true
let heroPositionEdited = false
const MEMORY_REFRESH_MS = 15_000
const ACCOUNTS_REFRESH_MS = 30_000

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
  const [teleboxResult] = await Promise.allSettled([
    listTeleBoxAccounts(),
    refreshAccountMetadata(),
  ])
  if (!active) return
  const failures: string[] = []
  if (teleboxResult.status === 'fulfilled') telebox.value = teleboxResult.value.accounts || []
  else failures.push(errorText(teleboxResult.reason))
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

function clearAccountsTimer() {
  if (accountsTimer) clearTimeout(accountsTimer)
  accountsTimer = undefined
}

function refreshAccountMetadata(): Promise<void> {
  if (!active || document.hidden || !getAuthToken()) return Promise.resolve()
  if (accountsRequest) return accountsRequest
  clearAccountsTimer()
  const generation = accountsGeneration
  const token = getAuthToken()
  const ownsRequest = () => active && !document.hidden
    && generation === accountsGeneration && token === getAuthToken()
  // Only read persisted results. Account probing remains manual or midnight scheduled.
  accountsRequest = store.ensureAccounts(true).then(() => {
    if (ownsRequest()) accountsFailure.value = null
  }).catch(cause => {
    if (ownsRequest()) accountsFailure.value = { cause }
  }).finally(() => {
    accountsRequest = undefined
    if (!active || document.hidden || !getAuthToken()) return
    if (accountsRefreshPending) {
      accountsRefreshPending = false
      void refreshAccountMetadata()
    } else {
      accountsTimer = setTimeout(() => void refreshAccountMetadata(), ACCOUNTS_REFRESH_MS)
    }
  })
  return accountsRequest
}

function resumeAccountMetadata() {
  if (accountsRequest) accountsRefreshPending = true
  else void refreshAccountMetadata()
}

watch(() => auth.token, () => {
  ++accountsGeneration
  clearAccountsTimer()
  accountsFailure.value = null
  accountsRefreshPending = false
  if (active && !document.hidden && getAuthToken()) resumeAccountMetadata()
}, { flush: 'sync' })

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
    ++accountsGeneration
    accountsRefreshPending = false
    clearAccountsTimer()
    if (memoryTimer) clearTimeout(memoryTimer)
    memoryTimer = undefined
  } else if (active) {
    void refreshMemory()
    resumeAccountMetadata()
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
  ++accountsGeneration
  accountsRefreshPending = false
  clearAccountsTimer()
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('tg-manage:hero-changed', onHeroChanged)
  window.removeEventListener('tg-manage:hero-position-changed', onHeroPositionChanged)
  if (memoryTimer) clearTimeout(memoryTimer)
  if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
})
</script>

<template>
  <div class="dashboard panel-stack" :aria-busy="loading">
    <section class="dashboard-hero" :class="{ 'dashboard-hero--custom': Boolean(heroImageUrl) }" aria-hidden="true">
      <HeroCover v-if="heroImageUrl" :src="heroImageUrl" :position-x="heroPositionX" :position-y="heroPositionY" />
      <div v-else class="dashboard-hero-ambient">
        <div class="dashboard-hero-orb dashboard-hero-orb--a" />
        <div class="dashboard-hero-orb dashboard-hero-orb--b" />
        <div class="dashboard-hero-grid" />
        <svg class="dashboard-hero-pulse-line" viewBox="0 0 680 120" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="tg-hero-wave" x1="0" y1="60" x2="680" y2="60" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.1" />
              <stop offset="22%" stop-color="#60a5fa" stop-opacity="0.9" />
              <stop offset="52%" stop-color="#a78bfa" stop-opacity="1" />
              <stop offset="78%" stop-color="#34d399" stop-opacity="0.85" />
              <stop offset="100%" stop-color="#34d399" stop-opacity="0.05" />
            </linearGradient>
            <linearGradient id="tg-hero-area" x1="340" y1="24" x2="340" y2="120" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#60a5fa" stop-opacity="0.22" />
              <stop offset="100%" stop-color="#60a5fa" stop-opacity="0" />
            </linearGradient>
          </defs>
          <path d="M0 70H120L148 28L174 96L200 44L220 70H340L364 36L386 86L408 52L426 70H540L562 48L582 78L600 70H680V120H0V70Z" fill="url(#tg-hero-area)" />
          <path d="M0 70H120L148 28L174 96L200 44L220 70H340L364 36L386 86L408 52L426 70H540L562 48L582 78L600 70H680" stroke="url(#tg-hero-wave)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="148" cy="28" r="4.5" fill="#93c5fd" />
          <circle cx="148" cy="28" r="10" fill="#93c5fd" fill-opacity="0.22" />
          <circle cx="364" cy="36" r="4.5" fill="#c4b5fd" />
          <circle cx="364" cy="36" r="10" fill="#c4b5fd" fill-opacity="0.22" />
          <circle cx="562" cy="48" r="4" fill="#6ee7b7" />
          <circle cx="562" cy="48" r="9" fill="#6ee7b7" fill-opacity="0.22" />
        </svg>
        <div class="dashboard-hero-rings">
          <span class="dashboard-hero-ring dashboard-hero-ring--1" />
          <span class="dashboard-hero-ring dashboard-hero-ring--2" />
          <span class="dashboard-hero-ring dashboard-hero-ring--3" />
        </div>
      </div>
    </section>

    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <p v-if="accountsError" class="panel-error" role="alert">{{ accountsError }}</p>

    <section :aria-label="t('dashboard.overview')" class="dashboard-metrics">
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--accounts">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Users :size="19" aria-hidden="true" /></span><span class="dashboard-metric-arrow"><ArrowUpRight :size="16" aria-hidden="true" /></span></span>
        <span class="dashboard-metric-value">{{ store.accounts.length }}</span><span class="dashboard-metric-label">{{ t('dashboard.loggedAccounts') }}</span><span class="dashboard-metric-foot">{{ t('dashboard.viewAccounts') }} <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--telebox">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><Activity :size="19" aria-hidden="true" /></span><span class="dashboard-metric-arrow"><ArrowUpRight :size="16" aria-hidden="true" /></span></span>
        <span class="dashboard-metric-value">{{ runningCount }}</span><span class="dashboard-metric-label">{{ t('dashboard.runningTelebox') }}</span><span class="dashboard-metric-foot">{{ t('dashboard.manageAccounts') }} <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
      <RouterLink to="/accounts" class="dashboard-metric dashboard-metric--tasks">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><CheckCircle2 :size="19" aria-hidden="true" /></span><span class="dashboard-metric-arrow"><ArrowUpRight :size="16" aria-hidden="true" /></span></span>
        <span class="dashboard-metric-value">{{ healthyCount }}</span><span class="dashboard-metric-label">{{ t('dashboard.healthyAccounts') }}</span><span class="dashboard-metric-foot">{{ t('dashboard.viewStatus') }} <ArrowRight :size="14" aria-hidden="true" /></span>
      </RouterLink>
      <div class="dashboard-metric dashboard-metric--memory" :aria-label="t('dashboard.memoryAriaLabel')">
        <span class="dashboard-metric-top"><span class="dashboard-metric-icon"><HardDrive :size="19" aria-hidden="true" /></span><span class="dashboard-live-badge"><span class="ui-pulse-dot" aria-hidden="true" />{{ t('dashboard.memoryLive') }}</span></span>
        <span class="dashboard-metric-value dashboard-memory-value">{{ memoryRss || t('dashboard.memoryUnavailableValue') }}</span>
        <span class="dashboard-metric-label">{{ t('dashboard.memoryLabel') }}</span><span class="dashboard-metric-foot">{{ t(`dashboard.${memoryStatusKey}`) }}<span v-if="memoryUpdatedAt">  /  {{ memoryUpdatedAt }}</span></span>
      </div>
    </section>

    <section class="dashboard-activity panel-card" aria-labelledby="dashboard-attention-title">
      <div class="dashboard-section-heading"><h3 id="dashboard-attention-title">{{ t('dashboard.attentionTitle') }}</h3><RouterLink to="/accounts" class="panel-button">{{ t('dashboard.viewAllAccounts') }} <ArrowRight :size="15" aria-hidden="true" /></RouterLink></div>
      <div v-if="loading && !store.accounts.length" class="dashboard-activity-loading" role="status">{{ t('dashboard.attentionLoading') }}</div>
      <div v-else-if="!attention.length" class="dashboard-activity-empty"><span class="dashboard-activity-empty-badge"><CheckCircle2 :size="22" aria-hidden="true" /></span><strong>{{ t('dashboard.attentionEmpty') }}</strong><span>{{ t('dashboard.attentionEmptyHint') }}</span></div>
      <ol v-else class="dashboard-activity-list"><li v-for="item in attention" :key="item.name" class="dashboard-activity-item"><span class="dashboard-activity-icon is-error"><Activity :size="18" aria-hidden="true" /></span><span class="dashboard-activity-name">{{ item.name }}</span><span class="dashboard-activity-state is-error">{{ attentionReason(item) }}</span></li></ol>
    </section>
  </div>
</template>
