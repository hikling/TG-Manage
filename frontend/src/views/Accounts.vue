<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import {
  Edit2,
  Trash2,
  Plus,
  QrCode,
  Phone,
  MonitorSmartphone,
  MessageCircle,
  CheckCircle2,
  Search,
  RefreshCw,
  XCircle,
  X,
  Users,
  MoreHorizontal,
  LogOut,
  Power,
  ShieldCheck,
  HardDriveDownload,
  ChevronDown,
} from 'lucide-vue-next'
import { accountAvatarToneClass, passBannerToneClass } from '../lib/avatar-palette'
import {
  deleteAccount,
  fetchAccountAvatar,
} from '../lib/api'
import { getAuthToken } from '../lib/api/core'
import { listTeleBoxAccounts, startTeleBox, stopTeleBox, logoutTeleBox, submitTeleBoxPassword, type TeleBoxAccount } from '../lib/api/telebox'
import { useI18n } from '../composables/useI18n'
import { useToast } from '../composables/useToast'
import { useConfirm } from '../composables/useConfirm'
import { useAccountsStore } from '../stores/accounts'
import { useAccountBatchCheck } from '../composables/useAccountBatchCheck'
import type { AccountUiItem } from '../lib/types'
import { notifyApiError } from '../lib/notify'
import { getLocalizedErrorMessage } from '../lib/types'
import AddAccountModal from '../components/accounts/AddAccountModal.vue'
import EditAccountModal from '../components/accounts/EditAccountModal.vue'
import AccountIpLocation from '../components/accounts/AccountIpLocation.vue'
import DeviceManagerModal from '../components/accounts/DeviceManagerModal.vue'
import OfficialMessagesModal from '../components/accounts/OfficialMessagesModal.vue'
import LoginBackupModal from '../components/accounts/LoginBackupModal.vue'
import PageRetry from '../components/PageRetry.vue'
import FilterEmptyState from '../components/FilterEmptyState.vue'
import { devLog } from '../lib/devLog'
import { AvatarLoadGate, AvatarUrlCache } from '../lib/avatar-cache'
import {
  filterAccountsByQuery,
  mapAccountInfoToUiItem,
} from '../lib/account-list-map'

const { t, locale } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const accountsStore = useAccountsStore()
const accounts = ref<AccountUiItem[]>([])
const teleboxStates = ref<Record<string, TeleBoxAccount>>({})
const teleboxBusy = ref('')
const teleboxPasswords = ref<Record<string, string>>({})
let statusTimer: ReturnType<typeof setInterval> | undefined
let routeStatusTimer: ReturnType<typeof setInterval> | undefined
let teleboxStatesInFlight = false
let routeStatesInFlight = false
const pageLoading = ref(true)
// 会话内头像 URL 缓存：避免每次刷新重复请求与重复创建 ObjectURL
const avatarCache = new AvatarUrlCache()
const avatarLoadGate = new AvatarLoadGate()
const avatarCacheMisses = new Set<string>()
const pendingAvatarNames: string[] = []
const queuedAvatarNames = new Set<string>()
const activeAvatarNames = new Set<string>()
const MAX_VISIBLE_AVATAR_FETCHES = 2
let avatarObserver: IntersectionObserver | undefined
let avatarObserverVersion = 0
let fallbackAvatarFrame: number | undefined
// 卸载标记：在途头像请求完成后不再创建 ObjectURL，避免 blob 泄漏
let disposed = false
/** 重登弹窗延时句柄：卸载时清理，避免关闭组件后仍打开新弹窗 */
let reloginTimer: number | undefined
const showAddModal = ref(false)
const showEditModal = ref(false)
const showAddMenu = ref(false)
const initialMethod = ref<'code' | 'qr'>('code')
const initialAccountName = ref('')
const editingAccount = ref<AccountUiItem | null>(null)
const showDeviceModal = ref(false)
const deviceAccountName = ref('')
const showOfficialMessagesModal = ref(false)
const showLoginBackupModal = ref(false)
const officialMessagesAccountName = ref('')
const searchQuery = ref('')
const statusFilter = ref<'all' | 'active' | 'error' | 'telebox'>('all')
const loadError = ref(false)
const openActionsName = ref<string | null>(null)

const onOutsideClick = () => {
  openActionsName.value = null
  showAddMenu.value = false
}
const onMenuKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    if (openActionsName.value) {
      document.querySelector<HTMLButtonElement>('.account-tile--menu-open .account-more')?.focus()
      openActionsName.value = null
    }
    showAddMenu.value = false
  }
}
const runCardAction = (action: () => void) => {
  openActionsName.value = null
  action()
}

const healthyAccountsCount = computed(() => accounts.value.filter(acc => acc.status === 'active').length)
const errorAccountsCount = computed(() => accounts.value.filter(acc => acc.status !== 'active').length)
const runningTeleboxCount = computed(() => accounts.value.filter(acc => teleboxStates.value[acc.name]?.status === 'running').length)

const filteredAccounts = computed(() => {
  const byQuery = filterAccountsByQuery(accounts.value, searchQuery.value)
  if (statusFilter.value === 'active') return byQuery.filter(acc => acc.status === 'active')
  if (statusFilter.value === 'error') return byQuery.filter(acc => acc.status !== 'active')
  if (statusFilter.value === 'telebox') return byQuery.filter(acc => teleboxStates.value[acc.name]?.status === 'running')
  return byQuery
})

const hasListFilters = computed(() => searchQuery.value.trim().length > 0 || statusFilter.value !== 'all')

const clearListFilters = () => {
  searchQuery.value = ''
  statusFilter.value = 'all'
}

const accountToneIndexMap = computed(() =>
  new Map(accounts.value.map((acc, index) => [acc.name, index])),
)

function passToneClass(name: string, fallbackIndex: number): string {
  const index = accountToneIndexMap.value.get(name) ?? fallbackIndex
  return passBannerToneClass(index)
}

async function loadTeleBoxStates() {
  if (disposed || teleboxStatesInFlight) return
  teleboxStatesInFlight = true
  try {
    const result = await listTeleBoxAccounts()
    if (!disposed) teleboxStates.value = Object.fromEntries(result.accounts.map(item => [item.account, item]))
  } catch (error) { devLog.error('Failed to load TeleBox status', error) }
  finally { teleboxStatesInFlight = false }
}

function teleboxLabel(name: string) {
  const state = teleboxStates.value[name]
  if (!state) return t('common.disabled')
  const key = `accounts.teleboxStatus.${state.status}`
  const label = t(key)
  return label === key ? t('accounts.statusUnknown') : label
}

function accountMessage(acc: AccountUiItem) {
  const message = mapAccountInfoToUiItem(acc.raw, {
    loginExpired: t('accounts.loginExpired'), checking: t('accounts.checking'),
  }).message
  return locale.value === 'en' && /\p{Script=Han}/u.test(message)
    ? getLocalizedErrorMessage(message, t, t('accounts.statusUnknown'))
    : message
}

function teleboxMessage(name: string) {
  const message = teleboxStates.value[name]?.message || ''
  return locale.value === 'en' && /\p{Script=Han}/u.test(message)
    ? getLocalizedErrorMessage(message, t, t('accounts.teleboxOperationFailed'))
    : message
}

async function setTeleBoxEnabled(name: string, enabled: boolean) {
  teleboxBusy.value = name
  try {
    if (enabled) await startTeleBox(name)
    else await stopTeleBox(name)
    await loadTeleBoxStates()
    toast.success(t(enabled ? 'accounts.teleboxStarted' : 'accounts.teleboxStopped'))
  } catch (error) { notifyApiError(error, 'accounts.teleboxOperationFailed') }
  finally { teleboxBusy.value = '' }
}

async function enterTeleBoxPassword(name: string) {
  const password = teleboxPasswords.value[name]?.trim()
  if (!password) return
  teleboxBusy.value = name
  try {
    await submitTeleBoxPassword(name, password)
    delete teleboxPasswords.value[name]
    toast.success(t('accounts.teleboxPasswordSubmitted'))
    await loadTeleBoxStates()
  } catch (error) { notifyApiError(error, 'accounts.teleboxPasswordFailed') }
  finally { teleboxBusy.value = '' }
}

async function handleTeleBoxLogout(name: string) {
  if (!await confirm({
    title: t('accounts.teleboxLogout'),
    message: t('accounts.teleboxLogoutConfirm', { name }),
    confirmText: t('accounts.teleboxLogoutAction'),
    danger: true,
  })) return
  teleboxBusy.value = name
  try {
    const result = await logoutTeleBox(name)
    await loadTeleBoxStates()
    if (result.remote_revoked) toast.success(t('accounts.teleboxLoggedOut'))
    else toast.info(t('accounts.teleboxLocalLogout'))
  } catch (error) { notifyApiError(error, 'accounts.teleboxLogoutFailed') }
  finally { teleboxBusy.value = '' }
}

/** 账号管理页为单一事实来源：每次调用都强制刷新（增删改/检测后保持一致） */
const loadAccounts = async () => {
  const token = getAuthToken()
  if (!token) return

  try {
    loadError.value = false
    const list = await accountsStore.refreshAccounts()
    const labels = {
      loginExpired: t('accounts.loginExpired'),
      checking: t('accounts.checking'),
    }
    accounts.value = list.map((acc) => {
      const ui = mapAccountInfoToUiItem(acc, labels)
      // 仅复用已加载头像；未点击单卡检测时不发起头像请求。
      const cached = avatarCache.get(acc.name)
      if (cached) ui.avatarUrl = cached
      return ui
    })
    avatarCache.retainOnly(new Set(list.map(acc => acc.name)))
    const currentNames = new Set(list.map(acc => acc.name))
    for (const name of avatarCacheMisses) {
      if (!currentNames.has(name)) avatarCacheMisses.delete(name)
    }
  } catch (e: unknown) {
    devLog.error('Failed to fetch accounts', e)
    loadError.value = true
    notifyApiError(e, 'accounts.loadFailed')
  } finally {
    pageLoading.value = false
  }
}

const loadSavedRouteStates = async () => {
  const token = getAuthToken()
  if (!token || disposed || document.hidden || routeStatesInFlight || pageLoading.value) return
  routeStatesInFlight = true
  try {
    const latest = await accountsStore.refreshAccounts()
    if (disposed || token !== getAuthToken()) return
    const byName = new Map(latest.map(item => [item.name, item]))
    for (const account of accounts.value) {
      const route = byName.get(account.name)
      if (!route || !account.raw) continue
      account.raw.route_mode = route.route_mode
      account.raw.route_status = route.route_status
      account.raw.node_label = route.node_label
      account.raw.latency_ms = route.latency_ms
      account.raw.route_checked_at = route.route_checked_at
      account.raw.exit_ip = route.exit_ip
      account.raw.exit_country = route.exit_country
      account.raw.exit_region = route.exit_region
      account.raw.exit_checked_at = route.exit_checked_at
      account.raw.exit_lookup_status = route.exit_lookup_status
      account.raw.shared_node = route.shared_node
    }
  } catch {
    // Leave the last saved state visible until a later successful GET.
  } finally {
    routeStatesInFlight = false
  }
}

const loadAvatar = async (acc: AccountUiItem, cacheOnly = false) => {
  if (disposed) return
  const version = avatarLoadGate.start(acc.name)
  if (version === null) return
  const token = getAuthToken()
  try {
    let url = avatarCache.get(acc.name)
    if (!url) {
      const blob = await fetchAccountAvatar(token, acc.name)
      if (disposed || !avatarLoadGate.isCurrent(acc.name, version)) return
      const current = accounts.value.find(item => item.name === acc.name)
      if (!current) return
      if (cacheOnly && !filteredAccounts.value.some(item => item.name === acc.name)) return
      if (blob.size > 128 * 1024 || !avatarCache.canStore(acc.name, blob.size)) {
        if (cacheOnly) avatarCacheMisses.add(acc.name)
        return
      }
      url = URL.createObjectURL(blob)
      avatarCache.set(acc.name, url, blob.size)
    }
    if (disposed || !avatarLoadGate.isCurrent(acc.name, version)) return
    const current = accounts.value.find(item => item.name === acc.name)
    if (current) current.avatarUrl = url
  } catch {
    if (cacheOnly && !disposed && avatarLoadGate.isCurrent(acc.name, version)) {
      avatarCacheMisses.add(acc.name)
    }
    devLog.info('头像加载失败，保留占位:', acc.name)
  } finally {
    avatarLoadGate.finish(acc.name, version)
  }
}

/** 只读取进入视口的磁盘缓存，且同时最多进行两个头像 HTTP 请求。 */
const drainVisibleAvatarQueue = () => {
  while (!disposed && activeAvatarNames.size < MAX_VISIBLE_AVATAR_FETCHES && pendingAvatarNames.length) {
    const name = pendingAvatarNames.shift()!
    queuedAvatarNames.delete(name)
    if (activeAvatarNames.has(name) || avatarCacheMisses.has(name) || avatarCache.get(name)) continue
    const acc = filteredAccounts.value.find(item => item.name === name)
    if (!acc) continue
    activeAvatarNames.add(name)
    void loadAvatar(acc, true).finally(() => {
      activeAvatarNames.delete(name)
      drainVisibleAvatarQueue()
    })
  }
}

const enqueueVisibleAvatar = (name: string) => {
  if (disposed || queuedAvatarNames.has(name) || activeAvatarNames.has(name)
    || avatarCacheMisses.has(name) || avatarCache.get(name)) return
  if (!filteredAccounts.value.some(item => item.name === name)) return
  queuedAvatarNames.add(name)
  pendingAvatarNames.push(name)
  drainVisibleAvatarQueue()
}

const scanFallbackVisibleAvatars = () => {
  const cards = document.querySelectorAll<HTMLElement>('[data-account-avatar-name]')
  for (const card of cards) {
    const bounds = card.getBoundingClientRect()
    if (bounds.bottom >= 0 && bounds.top <= window.innerHeight) {
      enqueueVisibleAvatar(card.dataset.accountAvatarName || '')
    }
  }
}

const scheduleFallbackAvatarScan = () => {
  if (disposed || fallbackAvatarFrame !== undefined) return
  fallbackAvatarFrame = window.requestAnimationFrame(() => {
    fallbackAvatarFrame = undefined
    scanFallbackVisibleAvatars()
  })
}

const observeVisibleAvatars = () => {
  avatarObserver?.disconnect()
  avatarObserver = undefined
  avatarObserverVersion += 1
  pendingAvatarNames.length = 0
  queuedAvatarNames.clear()
  if (disposed) return

  const cards = document.querySelectorAll<HTMLElement>('[data-account-avatar-name]')
  if (typeof IntersectionObserver === 'undefined') {
    scanFallbackVisibleAvatars()
    return
  }

  const version = avatarObserverVersion
  avatarObserver = new IntersectionObserver((entries) => {
    if (disposed || version !== avatarObserverVersion) return
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      avatarObserver?.unobserve(entry.target)
      enqueueVisibleAvatar((entry.target as HTMLElement).dataset.accountAvatarName || '')
    }
  }, { rootMargin: '100px 0px' })
  for (const card of cards) avatarObserver.observe(card)
}

watch(filteredAccounts, observeVisibleAvatars, { flush: 'post' })

const invalidateAvatars = (names: string[]) => {
  for (const name of names) {
    avatarLoadGate.invalidate(name)
    avatarCache.delete(name)
    avatarCacheMisses.delete(name)
    const current = accounts.value.find(item => item.name === name)
    if (current) current.avatarUrl = ''
  }
}

const loadAvatarForAccount = async (name: string) => {
  const acc = accounts.value.find(item => item.name === name)
  if (acc) await loadAvatar(acc)
}

onMounted(async () => {
  document.addEventListener('click', onOutsideClick)
  document.addEventListener('keydown', onMenuKeydown)
  if (typeof IntersectionObserver === 'undefined') {
    window.addEventListener('scroll', scheduleFallbackAvatarScan, { passive: true, capture: true })
    window.addEventListener('resize', scheduleFallbackAvatarScan, { passive: true })
  }
  await loadAccounts()
  void loadTeleBoxStates()
  statusTimer = setInterval(() => void loadTeleBoxStates(), 10000)
  routeStatusTimer = setInterval(() => void loadSavedRouteStates(), 30000)
  void resumeActiveBatchJob()
})

onUnmounted(() => {
  document.removeEventListener('click', onOutsideClick)
  document.removeEventListener('keydown', onMenuKeydown)
  window.removeEventListener('scroll', scheduleFallbackAvatarScan, true)
  window.removeEventListener('resize', scheduleFallbackAvatarScan)
  disposed = true
  if (fallbackAvatarFrame !== undefined) window.cancelAnimationFrame(fallbackAvatarFrame)
  avatarObserver?.disconnect()
  avatarObserverVersion += 1
  pendingAvatarNames.length = 0
  queuedAvatarNames.clear()
  if (statusTimer) clearInterval(statusTimer)
  if (routeStatusTimer) clearInterval(routeStatusTimer)
  if (reloginTimer !== undefined) {
    window.clearTimeout(reloginTimer)
    reloginTimer = undefined
  }
  avatarCache.release()
})

const handleDelete = async (name: string) => {
  const ok = await confirm({
    title: t('common.dangerConfirm'),
    message: t('accounts.deleteConfirm', { name }),
    confirmText: t('common.delete'),
    danger: true,
  })
  if (!ok) return
  const token = getAuthToken()
  try {
    await deleteAccount(token, name)
    toast.success(t('accounts.deleteSuccess'))
    await loadAccounts()
  } catch (e: unknown) {
    notifyApiError(e, 'accounts.deleteFailed')
  }
}

const {
  checkingAccount,
  batchChecking,
  batchJob,
  batchProgressPct,
  lastFailedAccountNames,
  handleCheck,
  handleBatchCheck,
  handleCancelBatchCheck,
  handleRecheckFailed,
  resumeActiveBatchJob,
} = useAccountBatchCheck({
  accounts,
  filteredAccounts,
  searchQuery,
  loadAccounts,
  invalidateAvatars,
  loadAvatarForAccount,
  updateTeleBoxState: (state) => {
    teleboxStates.value = { ...teleboxStates.value, [state.account]: state }
  },
})

const openEdit = (acc: AccountUiItem) => {
  editingAccount.value = acc
  showEditModal.value = true
}

const openDevices = (name: string) => {
  deviceAccountName.value = name
  showDeviceModal.value = true
}

const openOfficialMessages = (name: string) => {
  officialMessagesAccountName.value = name
  showOfficialMessagesModal.value = true
}

const handleRelogin = (name: string) => {
  showEditModal.value = false
  reloginTimer = window.setTimeout(() => {
    initialAccountName.value = name
    initialMethod.value = 'code'
    showAddModal.value = true
  }, 300)
}

const openAddModal = (method: 'code' | 'qr') => {
  initialAccountName.value = ''
  initialMethod.value = method
  showAddMenu.value = false
  showAddModal.value = true
}
</script>

<template>
  <div class="relative min-h-[80vh]">
    <!-- Page Loading Skeleton -->
    <div v-if="pageLoading" class="space-y-5" aria-busy="true">
      <div class="flex justify-between items-center gap-3">
        <div class="ui-skeleton h-9 w-64" />
        <div class="ui-skeleton h-9 w-48" />
      </div>
      <div class="account-deck">
        <div v-for="i in 4" :key="i" class="ui-card overflow-hidden">
          <div class="ui-skeleton h-16 w-full !rounded-none" />
          <div class="p-5 space-y-4">
            <div class="ui-skeleton h-4 w-28" />
            <div class="ui-skeleton h-14 w-full" />
            <div class="ui-skeleton h-9 w-full" />
          </div>
        </div>
      </div>
    </div>

    <!-- 加载失败 -->
    <div v-else-if="loadError" class="space-y-4">
      <PageRetry
        :message="t('accounts.loadFailed')"
        :loading="pageLoading"
        @retry="pageLoading = true; loadAccounts()"
      />
    </div>

    <!-- Empty State -->
    <div v-else-if="accounts.length === 0" class="ui-empty">
      <div class="ui-empty-icon">
        <Users class="w-8 h-8" />
      </div>
      <p class="ui-empty-title">{{ t('accounts.empty') }}</p>
      <p class="ui-empty-desc mb-4">{{ t('accounts.emptyHint') }}</p>
      <div class="flex flex-wrap items-center justify-center gap-2">
        <button type="button" class="ui-btn-primary !text-xs !px-3.5 !py-2" @click="openAddModal('code')">
          <Phone class="w-3.5 h-3.5" /> {{ t('accounts.codeLogin') }}
        </button>
        <button type="button" class="ui-btn-secondary !text-xs !px-3.5 !py-2" @click="openAddModal('qr')">
          <QrCode class="w-3.5 h-3.5" /> {{ t('accounts.qrLogin') }}
        </button>
        <button type="button" class="ui-btn-secondary !text-xs !px-3.5 !py-2" @click="showLoginBackupModal = true">
          <HardDriveDownload class="w-3.5 h-3.5" /> {{ t('accounts.loginBackupImport') }}
        </button>
      </div>
    </div>

    <div v-else class="space-y-5 pb-12">
      <!-- Sleek Toolbar -->
      <div class="accounts-bar">
        <div class="accounts-filter-bar" role="group" :aria-label="t('accounts.total')">
          <button type="button" class="accounts-filter-tab" :class="{ 'is-active': statusFilter === 'all' }" @click="statusFilter = 'all'">
            {{ t('accounts.filterAll') }}
            <span class="accounts-filter-num">{{ accounts.length }}</span>
          </button>
          <button type="button" class="accounts-filter-tab" :class="{ 'is-active': statusFilter === 'active' }" @click="statusFilter = 'active'">
            <span class="accounts-dot bg-emerald-500" aria-hidden="true" />
            {{ t('accounts.statusOk') }}
            <span class="accounts-filter-num">{{ healthyAccountsCount }}</span>
          </button>
          <button type="button" class="accounts-filter-tab" :class="{ 'is-active': statusFilter === 'error' }" @click="statusFilter = 'error'">
            <span class="accounts-dot bg-rose-500" aria-hidden="true" />
            {{ t('accounts.checkFailedCount') }}
            <span class="accounts-filter-num">{{ errorAccountsCount }}</span>
          </button>
          <button type="button" class="accounts-filter-tab" :class="{ 'is-active': statusFilter === 'telebox' }" @click="statusFilter = 'telebox'">
            <span class="accounts-dot bg-violet-500" aria-hidden="true" />
            TeleBox
            <span class="accounts-filter-num">{{ runningTeleboxCount }}</span>
          </button>
        </div>

        <div class="accounts-bar-right">
          <div class="relative flex-1 sm:flex-none sm:w-56 md:w-60 min-w-0">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--tg-text-muted)] pointer-events-none" />
            <input
              v-model="searchQuery"
              type="search"
              class="ui-input !pl-8 !min-h-[36px] !h-[36px] !text-xs"
              :class="searchQuery.trim() ? '!pr-8' : ''"
              :placeholder="t('common.searchPlaceholder')"
              :aria-label="t('common.search')"
            >
            <button
              v-if="searchQuery.trim()"
              type="button"
              class="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-[var(--tg-text-muted)] hover:text-[var(--tg-text)] rounded-md"
              :title="t('common.clearFilters')"
              :aria-label="t('common.clearFilters')"
              @click="clearListFilters"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </div>

          <button type="button" class="ui-btn-secondary !px-3 !py-1.5 !text-xs inline-flex items-center gap-1.5 shrink-0" @click="showLoginBackupModal = true">
            <HardDriveDownload class="w-3.5 h-3.5" />
            <span class="hidden md:inline">{{ t('accounts.loginBackupTitle') }}</span>
          </button>

          <button
            v-if="batchChecking && batchJob?.job_id"
            type="button"
            class="ui-btn-secondary !px-3 !py-1.5 !text-xs inline-flex items-center gap-1.5 shrink-0"
            @click="handleCancelBatchCheck"
          >
            <XCircle class="w-3.5 h-3.5" />
            {{ t('accounts.batchCheckCancel') }}
          </button>
          <button
            v-if="!batchChecking && lastFailedAccountNames.length > 0"
            type="button"
            class="ui-btn-secondary !px-3 !py-1.5 !text-xs inline-flex items-center gap-1.5 shrink-0"
            :title="t('accounts.batchRecheckFailedHint')"
            @click="handleRecheckFailed"
          >
            <RefreshCw class="w-3.5 h-3.5" />
            {{ t('accounts.batchRecheckFailed') }}
            <span class="font-mono opacity-80">({{ lastFailedAccountNames.length }})</span>
          </button>
          <button
            type="button"
            class="ui-btn-secondary !px-3 !py-1.5 !text-xs inline-flex items-center gap-1.5 shrink-0"
            :disabled="batchChecking"
            :title="batchChecking ? t('accounts.batchChecking') : undefined"
            @click="handleBatchCheck"
          >
            <span v-if="batchChecking" class="ui-spinner !w-3.5 !h-3.5 !border-2" />
            <CheckCircle2 v-else class="w-3.5 h-3.5" />
            {{ batchChecking ? t('accounts.batchChecking') : t('accounts.batchCheck') }}
          </button>

          <div class="relative shrink-0" @click.stop>
            <button
              type="button"
              class="ui-btn-primary !px-3.5 !py-1.5 !text-xs inline-flex items-center gap-1.5"
              :aria-expanded="showAddMenu"
              :aria-label="t('accounts.addAccount')"
              @click="showAddMenu = !showAddMenu"
            >
              <Plus class="w-3.5 h-3.5" />
              {{ t('accounts.addAccount') }}
              <ChevronDown class="w-3.5 h-3.5 opacity-80 transition-transform" :class="{ 'rotate-180': showAddMenu }" />
            </button>
            <transition enter-active-class="transition duration-150 ease-out" enter-from-class="opacity-0 -translate-y-1" enter-to-class="opacity-100 translate-y-0" leave-active-class="transition duration-100 ease-in" leave-from-class="opacity-100 translate-y-0" leave-to-class="opacity-0 -translate-y-1">
              <div v-if="showAddMenu" class="account-add-popover">
                <button type="button" @click="openAddModal('code')">
                  <Phone class="w-4 h-4 text-[var(--tg-text-muted)]" />
                  <span>{{ t('accounts.codeLogin') }}</span>
                </button>
                <button type="button" @click="openAddModal('qr')">
                  <QrCode class="w-4 h-4 text-[var(--tg-text-muted)]" />
                  <span>{{ t('accounts.qrLogin') }}</span>
                </button>
              </div>
            </transition>
          </div>
        </div>
      </div>

      <!-- Batch Check Progress -->
      <div v-if="batchChecking && batchJob" class="accounts-batch-progress">
        <div class="flex items-center justify-between gap-2 text-xs">
          <span class="font-mono font-medium text-[var(--tg-text)]">
            {{ t('accounts.batchCheckProgress', {
              done: batchJob.progress?.done ?? 0,
              total: batchJob.progress?.total ?? accounts.length,
            }) }}
            <template v-if="(batchJob.progress?.ok ?? 0) + (batchJob.progress?.fail ?? 0) > 0">
              · {{ t('accounts.batchCheckOkFail', {
                ok: batchJob.progress?.ok ?? 0,
                fail: batchJob.progress?.fail ?? 0,
              }) }}
            </template>
          </span>
          <span class="font-mono text-[var(--tg-text-muted)]">{{ batchProgressPct }}%</span>
        </div>
        <div
          class="w-full h-1.5 rounded-full bg-[var(--tg-bg-muted)] overflow-hidden"
          role="progressbar"
          :aria-valuenow="batchProgressPct"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="t('accounts.batchCheckProgress', {
            done: batchJob.progress?.done ?? 0,
            total: batchJob.progress?.total ?? accounts.length,
          })"
        >
          <div
            class="h-full rounded-full transition-all duration-300"
            :style="{ width: `${batchProgressPct}%`, backgroundColor: 'var(--tg-accent)' }"
            aria-hidden="true"
          />
        </div>
      </div>

      <!-- Filter Empty State -->
      <div v-if="filteredAccounts.length === 0" class="ui-empty !py-14">
        <FilterEmptyState
          v-if="accounts.length > 0 && hasListFilters"
          :title="t('common.filterNoResults')"
          :hint="t('common.filterNoResultsHint')"
          :action-text="t('common.clearFilters')"
          @action="clearListFilters"
        />
        <p v-else class="ui-empty-desc">{{ t('common.noData') }}</p>
      </div>

      <!-- Showcase Card Deck (卡牌式设计) -->
      <div v-else class="account-deck">
        <article
          v-for="(acc, accIndex) in filteredAccounts"
          :key="acc.id"
          class="account-pass"
          :data-account-avatar-name="acc.name"
          :class="[
            passToneClass(acc.name, accIndex),
            `account-pass--${acc.status}`,
            { 'account-tile--menu-open': openActionsName === acc.name },
          ]"
        >
          <!-- Card Top Cover Header -->
          <div class="account-pass-banner">
            <div class="account-pass-banner-bg" aria-hidden="true" />
            <div class="account-pass-banner-actions">
              <span class="account-pass-status" :class="`is-${acc.status}`" :title="accountMessage(acc)">
                <span class="account-pass-status-dot" aria-hidden="true" />
                {{ acc.status === 'active' ? t('accounts.statusOk') : (accountMessage(acc) || t('accounts.statusUnknown')) }}
              </span>

              <div class="relative" @click.stop>
                <button
                  type="button"
                  class="account-more account-pass-more"
                  :aria-label="t('accounts.actions', { name: acc.name })"
                  :title="t('accounts.actions', { name: acc.name })"
                  :aria-expanded="openActionsName === acc.name"
                  aria-haspopup="true"
                  @click="openActionsName = openActionsName === acc.name ? null : acc.name"
                >
                  <MoreHorizontal class="w-4 h-4" />
                </button>
                <div v-if="openActionsName === acc.name" class="account-action-menu" :aria-label="t('accounts.actions', { name: acc.name })">
                  <button v-if="teleboxStates[acc.name]?.enabled" type="button" :disabled="teleboxBusy === acc.name" @click="runCardAction(() => setTeleBoxEnabled(acc.name, false))"><Power class="w-4 h-4" />{{ t('accounts.teleboxStop') }}</button>
                  <button v-else type="button" :disabled="teleboxBusy === acc.name" @click="runCardAction(() => setTeleBoxEnabled(acc.name, true))"><Power class="w-4 h-4" />{{ t('accounts.teleboxStart') }}</button>
                  <button v-if="teleboxStates[acc.name]?.authorized || teleboxStates[acc.name]?.enabled" type="button" class="account-action-danger" :disabled="teleboxBusy === acc.name" @click="runCardAction(() => handleTeleBoxLogout(acc.name))"><LogOut class="w-4 h-4" />{{ t('accounts.teleboxLogout') }}</button>
                  <button type="button" @click="runCardAction(() => openDevices(acc.name))"><MonitorSmartphone class="w-4 h-4" />{{ t('accounts.devicesShort') }}</button>
                  <button type="button" @click="runCardAction(() => openOfficialMessages(acc.name))"><MessageCircle class="w-4 h-4" />{{ t('accounts.officialMessagesShort') }}</button>
                  <button type="button" @click="runCardAction(() => openEdit(acc))"><Edit2 class="w-4 h-4" />{{ t('accounts.editBtn') }}</button>
                  <button type="button" class="account-action-danger" @click="runCardAction(() => handleDelete(acc.name))"><Trash2 class="w-4 h-4" />{{ t('accounts.deleteBtn') }}</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Large Straddling Avatar + Name Above Line / Remark Below Line -->
          <div class="account-pass-identity">
            <div class="account-pass-avatar-ring" aria-hidden="true">
              <div class="account-pass-avatar" :class="acc.avatarUrl ? '' : accountAvatarToneClass(acc.name)">
                <img v-if="acc.avatarUrl" :src="acc.avatarUrl" alt="" class="w-full h-full object-cover" width="76" height="76" loading="lazy" decoding="async" />
                <span v-else>{{ acc.name.substring(0, 2).toUpperCase() }}</span>
              </div>
              <span class="account-pass-online-dot" :class="`is-${acc.status}`" />
            </div>

            <div class="account-pass-meta">
              <div class="account-pass-name-slot">
                <h2 :title="acc.name">{{ acc.name }}</h2>
              </div>
              <div class="account-pass-remark-slot">
                <p :title="acc.remark || t('accounts.noRemark')">{{ acc.remark || t('accounts.noRemark') }}</p>
              </div>
            </div>
          </div>

          <!-- Simplified Flat Telemetry Rows -->
          <div class="account-pass-specs">
            <div class="account-pass-spec-item">
              <AccountIpLocation :account="acc.raw" />
            </div>

            <div class="account-pass-spec-item account-pass-telebox" :title="teleboxMessage(acc.name)">
              <span class="account-pass-tb-label">TeleBox</span>
              <span
                class="account-tb-status"
                :class="{
                  'is-running': teleboxStates[acc.name]?.status === 'running',
                  'is-error': teleboxStates[acc.name]?.status === 'failed',
                  'is-starting': teleboxStates[acc.name]?.status === 'starting' || teleboxStates[acc.name]?.status === 'password_required',
                }"
              >
                <span class="account-tb-dot" aria-hidden="true" />
                {{ teleboxLabel(acc.name) }}
              </span>
            </div>
          </div>

          <!-- Optional 2FA Password Prompt -->
          <form v-if="teleboxStates[acc.name]?.status === 'password_required'" class="account-pass-password" @submit.prevent="enterTeleBoxPassword(acc.name)">
            <label :for="`telebox-password-${acc.id}`">{{ t('accounts.teleboxPassword') }}</label>
            <div>
              <input :id="`telebox-password-${acc.id}`" v-model="teleboxPasswords[acc.name]" type="password" autocomplete="current-password" class="panel-input" required />
              <button type="submit" class="panel-button" :disabled="teleboxBusy === acc.name">{{ t('common.confirm') }}</button>
            </div>
          </form>

          <!-- Card Footer Action Dock -->
          <div class="account-pass-foot">
            <button type="button" class="account-pass-action-main" :disabled="checkingAccount === acc.name" @click="handleCheck(acc.name)">
              <ShieldCheck :size="15" aria-hidden="true" />
              <span>{{ checkingAccount === acc.name ? t('accounts.checking') : t('accounts.checkStatus') }}</span>
            </button>
            <button
              type="button"
              class="account-pass-action-sub account-pass-action-tb"
              :class="{ 'is-on': teleboxStates[acc.name]?.enabled }"
              :disabled="teleboxBusy === acc.name"
              :title="teleboxStates[acc.name]?.enabled ? t('accounts.teleboxStop') : t('accounts.teleboxStart')"
              :aria-label="teleboxStates[acc.name]?.enabled ? t('accounts.teleboxStop') : t('accounts.teleboxStart')"
              @click="setTeleBoxEnabled(acc.name, !teleboxStates[acc.name]?.enabled)"
            >
              <Power :size="15" aria-hidden="true" />
              <span>{{ teleboxStates[acc.name]?.enabled ? t('accounts.teleboxStop') : t('accounts.teleboxStart') }}</span>
            </button>
            <button
              type="button"
              class="account-pass-icon-btn"
              :title="t('accounts.officialMessages')"
              :aria-label="t('accounts.officialMessages')"
              @click="openOfficialMessages(acc.name)"
            >
              <MessageCircle :size="15" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="account-pass-icon-btn"
              :title="t('accounts.devices')"
              :aria-label="t('accounts.devices')"
              @click="openDevices(acc.name)"
            >
              <MonitorSmartphone :size="15" aria-hidden="true" />
            </button>
          </div>
        </article>
      </div>
    </div>

    <!-- Modals -->
    <AddAccountModal :isOpen="showAddModal" :initialMethod="initialMethod" :initialAccountName="initialAccountName" @close="showAddModal = false" @success="loadAccounts" />
    <EditAccountModal v-if="editingAccount" :isOpen="showEditModal" :account="editingAccount" @close="showEditModal = false" @success="loadAccounts" @relogin="handleRelogin" />
    <DeviceManagerModal :isOpen="showDeviceModal" :accountName="deviceAccountName" @close="showDeviceModal = false" />
    <OfficialMessagesModal :isOpen="showOfficialMessagesModal" :accountName="officialMessagesAccountName" @close="showOfficialMessagesModal = false" />
    <LoginBackupModal :isOpen="showLoginBackupModal" :initialMode="accounts.length ? 'export' : 'import'" @close="showLoginBackupModal = false" @restored="loadAccounts" />
  </div>
</template>
