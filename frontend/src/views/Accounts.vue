<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Play, FileText, Edit2, Trash2, Plus, QrCode, Phone, MonitorSmartphone, MessageCircle, MessagesSquare, CheckCircle2, Search, RefreshCw, XCircle, X, Users, MoreVertical, LogOut, Power, ShieldCheck, ArrowUpRight } from 'lucide-vue-next'
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
import AddAccountModal from '../components/accounts/AddAccountModal.vue'
import EditAccountModal from '../components/accounts/EditAccountModal.vue'
import DeviceManagerModal from '../components/accounts/DeviceManagerModal.vue'
import OfficialMessagesModal from '../components/accounts/OfficialMessagesModal.vue'
import PageRetry from '../components/PageRetry.vue'
import FilterEmptyState from '../components/FilterEmptyState.vue'
import { devLog } from '../lib/devLog'
import { AVATAR_FETCH_CONCURRENCY, mapPool } from '../lib/async-pool'
import { AvatarUrlCache } from '../lib/avatar-cache'
import {
  filterAccountsByQuery,
  mapAccountInfoToUiItem,
} from '../lib/account-list-map'

const router = useRouter()
const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()
const accountsStore = useAccountsStore()
const accounts = ref<AccountUiItem[]>([])
const teleboxStates = ref<Record<string, TeleBoxAccount>>({})
const teleboxBusy = ref('')
const teleboxPasswords = ref<Record<string, string>>({})
let statusTimer: ReturnType<typeof setInterval> | undefined
const pageLoading = ref(true)
// 会话内头像 URL 缓存：避免每次刷新重复请求与重复创建 ObjectURL
const avatarCache = new AvatarUrlCache()
const avatarLoads = new Set<string>()
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
const officialMessagesAccountName = ref('')
const searchQuery = ref('')
const loadError = ref(false)
const openActionsName = ref<string | null>(null)
const onOutsideClick = () => { openActionsName.value = null }
const onMenuKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && openActionsName.value) {
    document.querySelector<HTMLButtonElement>('.account-tile--menu-open .account-more')?.focus()
    openActionsName.value = null
  }
}
const runCardAction = (action: () => void) => {
  openActionsName.value = null
  action()
}

const filteredAccounts = computed(() =>
  filterAccountsByQuery(accounts.value, searchQuery.value),
)

const hasListFilters = computed(() => searchQuery.value.trim().length > 0)

const clearListFilters = () => {
  searchQuery.value = ''
}

async function loadTeleBoxStates() {
  try {
    const result = await listTeleBoxAccounts()
    if (!disposed) teleboxStates.value = Object.fromEntries(result.accounts.map(item => [item.account, item]))
  } catch (error) { devLog.error('Failed to load TeleBox status', error) }
}

function teleboxLabel(name: string) {
  const state = teleboxStates.value[name]
  if (!state) return '未启用'
  return ({ running: '正在运行', starting: '正在启动', password_required: '等待二步验证', failed: '运行异常', stopped: '已停止' } as Record<string, string>)[state.status] || state.status
}

async function setTeleBoxEnabled(name: string, enabled: boolean) {
  teleboxBusy.value = name
  try {
    if (enabled) await startTeleBox(name)
    else await stopTeleBox(name)
    await loadTeleBoxStates()
    toast.success(enabled ? 'TeleBox 已请求启动' : 'TeleBox 已停止')
  } catch (error) { notifyApiError(error, 'TeleBox 操作失败') }
  finally { teleboxBusy.value = '' }
}

async function enterTeleBoxPassword(name: string) {
  const password = teleboxPasswords.value[name]?.trim()
  if (!password) return
  teleboxBusy.value = name
  try {
    await submitTeleBoxPassword(name, password)
    delete teleboxPasswords.value[name]
    toast.success('已提交二步验证密码')
    await loadTeleBoxStates()
  } catch (error) { notifyApiError(error, 'TeleBox 二步验证失败') }
  finally { teleboxBusy.value = '' }
}

async function handleTeleBoxLogout(name: string) {
  if (!await confirm({
    title: '退出 TeleBox 登录',
    message: `将退出 ${name} 的 TeleBox 独立 Telegram 会话，并停止其进程。账号管理中的主账号登录不受影响。是否继续？`,
    confirmText: '退出 TeleBox',
    danger: true,
  })) return
  teleboxBusy.value = name
  try {
    const result = await logoutTeleBox(name)
    await loadTeleBoxStates()
    if (result.remote_revoked) toast.success('已退出 TeleBox 登录并撤销远端会话')
    else toast.info('已清除本地 TeleBox 登录；离线状态下无法确认远端会话撤销')
  } catch (error) { notifyApiError(error, '退出 TeleBox 失败') }
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
      // 复用已加载的头像 URL，未缓存项交由 loadAvatars 补充
      const cached = avatarCache.get(acc.name)
      if (cached) ui.avatarUrl = cached
      return ui
    })
    avatarCache.retainOnly(new Set(list.map(acc => acc.name)))
    // 限流加载头像，避免账号多时并发打满连接
    void loadAvatars(accounts.value)
  } catch (e: unknown) {
    devLog.error('Failed to fetch accounts', e)
    loadError.value = true
    notifyApiError(e, 'accounts.loadFailed')
  } finally {
    pageLoading.value = false
  }
}

const loadAvatar = async (acc: AccountUiItem) => {
  if (disposed || avatarLoads.has(acc.name)) return
  avatarLoads.add(acc.name)
  const token = getAuthToken()
  try {
    let url = avatarCache.get(acc.name)
    if (!url) {
      const blob = await fetchAccountAvatar(token, acc.name)
      if (disposed || !accounts.value.some(item => item.name === acc.name)) return
      if (blob.size > 128 * 1024 || !avatarCache.canStore(acc.name, blob.size)) return
      url = URL.createObjectURL(blob)
      avatarCache.set(acc.name, url, blob.size)
    }
    acc.avatarUrl = url
  } catch {
    // 头像下载失败/无头像：保留首字母占位，不影响列表
    devLog.info('头像加载失败，保留占位:', acc.name)
  } finally {
    avatarLoads.delete(acc.name)
  }
}

const loadAvatars = async (list: AccountUiItem[]) => {
  await mapPool(list, AVATAR_FETCH_CONCURRENCY, async (acc) => {
    await loadAvatar(acc)
  })
}

onMounted(async () => {
  document.addEventListener('click', onOutsideClick)
  document.addEventListener('keydown', onMenuKeydown)
  await loadAccounts()
  void loadTeleBoxStates()
  statusTimer = setInterval(() => void loadTeleBoxStates(), 10000)
  // 刷新页面后恢复未完成的批量检测
  void resumeActiveBatchJob()
})

onUnmounted(() => {
  document.removeEventListener('click', onOutsideClick)
  document.removeEventListener('keydown', onMenuKeydown)
  disposed = true
  if (statusTimer) clearInterval(statusTimer)
  if (reloginTimer !== undefined) {
    window.clearTimeout(reloginTimer)
    reloginTimer = undefined
  }
  // 离开页面时统一回收会话内头像 ObjectURL，避免 blob 泄漏
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

const goLogs = (name: string) => {
  router.push({ name: 'logs', query: { account: name } })
}

</script>

<template>
  <div class="relative min-h-[80vh]">
    <!-- Page Loading skeleton -->
    <div v-if="pageLoading" class="space-y-4" aria-busy="true">
      <div class="ui-card p-3 flex justify-between">
        <div class="ui-skeleton h-4 w-24" />
        <div class="ui-skeleton h-8 w-28" />
      </div>
      <div class="account-grid">
        <div v-for="i in 4" :key="i" class="ui-card p-5 space-y-4">
          <div class="flex items-center gap-3">
            <div class="ui-skeleton w-10 h-10 shrink-0" />
            <div class="flex-1 space-y-2">
              <div class="ui-skeleton h-3.5 w-24" />
              <div class="ui-skeleton h-3 w-16" />
            </div>
          </div>
          <div class="ui-skeleton h-10 w-full" />
        </div>
      </div>
    </div>

    <!-- 加载失败（空列表时也要能重试，不能误显示 empty） -->
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
        <button type="button" class="ui-btn-primary !text-xs !px-3 !py-2" @click="openAddModal('code')">
          <Phone class="w-3.5 h-3.5" /> {{ t('accounts.codeLogin') }}
        </button>
        <button type="button" class="ui-btn-secondary !text-xs !px-3 !py-2" @click="openAddModal('qr')">
          <QrCode class="w-3.5 h-3.5" /> {{ t('accounts.qrLogin') }}
        </button>
      </div>
    </div>

    <div v-else class="space-y-4 pb-20">
      <div class="ui-card flex flex-col sm:flex-row sm:items-center gap-3 p-3">
        <div class="text-xs text-gray-500 shrink-0">
          {{ t('accounts.total') }}：<span class="font-mono text-gray-800 dark:text-gray-200">{{ filteredAccounts.length }}</span>
          <span v-if="searchQuery.trim()" class="text-gray-400"> / {{ accounts.length }}</span>
        </div>
        <div class="relative flex-1 min-w-0 max-w-md">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
          <input
            v-model="searchQuery"
            type="search"
            class="ui-input !pl-8 !h-9 !text-xs"
            :class="searchQuery.trim() ? '!pr-8' : ''"
            :placeholder="t('common.searchPlaceholder')"
            :aria-label="t('common.search')"
          >
          <button
            v-if="searchQuery.trim()"
            type="button"
            class="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 rounded-sm"
            :title="t('common.clearFilters')"
            :aria-label="t('common.clearFilters')"
            @click="clearListFilters"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <div
            v-if="batchChecking && batchJob"
            class="flex flex-col items-end gap-0.5 min-w-0 sm:min-w-[7rem]"
          >
            <span class="text-[11px] font-mono text-sky-700 dark:text-sky-300 whitespace-nowrap">
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
            <div
              class="hidden sm:block w-full h-1 rounded-full bg-sky-100 dark:bg-sky-950/50 overflow-hidden"
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
                class="h-full bg-sky-500 transition-all duration-300"
                :style="{ width: `${batchProgressPct}%` }"
                aria-hidden="true"
              />
            </div>
          </div>
          <button
            v-if="batchChecking && batchJob?.job_id"
            type="button"
            class="ui-btn-secondary !px-3 !py-2 !text-xs inline-flex items-center gap-1"
            @click="handleCancelBatchCheck"
          >
            <XCircle class="w-3.5 h-3.5" />
            {{ t('accounts.batchCheckCancel') }}
          </button>
          <button
            v-if="!batchChecking && lastFailedAccountNames.length > 0"
            type="button"
            class="ui-btn-secondary !px-3 !py-2 !text-xs inline-flex items-center gap-1"
            :title="t('accounts.batchRecheckFailedHint')"
            @click="handleRecheckFailed"
          >
            <RefreshCw class="w-3.5 h-3.5" />
            {{ t('accounts.batchRecheckFailed') }}
            <span class="font-mono opacity-80">({{ lastFailedAccountNames.length }})</span>
          </button>
          <button
            type="button"
            class="ui-btn-primary !px-3 !py-2 !text-xs inline-flex items-center gap-1"
            :disabled="batchChecking"
            :title="batchChecking ? t('accounts.batchChecking') : undefined"
            @click="handleBatchCheck"
          >
            <span v-if="batchChecking" class="ui-spinner !w-3.5 !h-3.5 !border-2" />
            <CheckCircle2 v-else class="w-3.5 h-3.5" />
            {{ batchChecking ? t('accounts.batchChecking') : t('accounts.batchCheck') }}
          </button>
        </div>
      </div>
      <div v-if="filteredAccounts.length === 0" class="ui-empty !py-12">
        <FilterEmptyState
          v-if="accounts.length > 0 && hasListFilters"
          :title="t('common.filterNoResults')"
          :hint="t('common.filterNoResultsHint')"
          :action-text="t('common.clearFilters')"
          @action="clearListFilters"
        />
        <p v-else class="ui-empty-desc">{{ t('common.noData') }}</p>
      </div>
      <div v-else class="account-grid">
    <article v-for="acc in filteredAccounts" :key="acc.id" class="account-tile" :class="{ 'account-tile--menu-open': openActionsName === acc.name }">
      <div class="account-tile-top">
        <div class="account-tile-avatar">
          <img v-if="acc.avatarUrl" :src="acc.avatarUrl" :alt="acc.name" class="w-full h-full object-cover" loading="lazy" decoding="async" />
          <span v-else>{{ acc.name.substring(0, 2) }}</span>
        </div>
        <div class="account-tile-info"><p class="account-tile-eyebrow">TELEGRAM ACCOUNT</p><h2 :title="acc.name">{{ acc.name }}</h2><p :title="acc.remark || t('accounts.noRemark')">{{ acc.remark || t('accounts.noRemark') }}</p></div>
        <div class="account-tile-actions" @click.stop>
          <button type="button" class="account-more" :aria-label="`${acc.name} 操作`" :title="`${acc.name} 操作`" :aria-expanded="openActionsName === acc.name" aria-haspopup="true" @click="openActionsName = openActionsName === acc.name ? null : acc.name"><MoreVertical class="w-5 h-5" /></button>
          <div v-if="openActionsName === acc.name" class="account-action-menu" :aria-label="`${acc.name} 操作`">
            <button type="button" :disabled="checkingAccount === acc.name" @click="runCardAction(() => handleCheck(acc.name))"><Play class="w-4 h-4" />{{ t('accounts.check') }}</button>
            <button type="button" @click="runCardAction(() => goLogs(acc.name))"><FileText class="w-4 h-4" />{{ t('accounts.logs') }}</button>
            <button type="button" @click="runCardAction(() => router.push({ name: 'chats', query: { account: acc.name } }))"><MessagesSquare class="w-4 h-4" />聊天中心</button>
            <button v-if="teleboxStates[acc.name]?.enabled" type="button" :disabled="teleboxBusy === acc.name" @click="runCardAction(() => setTeleBoxEnabled(acc.name, false))"><Power class="w-4 h-4" />停止 TeleBox</button>
            <button v-else type="button" :disabled="teleboxBusy === acc.name" @click="runCardAction(() => setTeleBoxEnabled(acc.name, true))"><Power class="w-4 h-4" />启动 TeleBox</button>
            <button v-if="teleboxStates[acc.name]?.authorized || teleboxStates[acc.name]?.enabled" type="button" class="account-action-danger" :disabled="teleboxBusy === acc.name" @click="runCardAction(() => handleTeleBoxLogout(acc.name))"><LogOut class="w-4 h-4" />退出 TeleBox 登录</button>
            <button type="button" @click="runCardAction(() => openDevices(acc.name))"><MonitorSmartphone class="w-4 h-4" />{{ t('accounts.devicesShort') }}</button>
            <button type="button" @click="runCardAction(() => openOfficialMessages(acc.name))"><MessageCircle class="w-4 h-4" />{{ t('accounts.officialMessagesShort') }}</button>
            <button type="button" @click="runCardAction(() => openEdit(acc))"><Edit2 class="w-4 h-4" />{{ t('accounts.editBtn') }}</button>
            <button type="button" class="account-action-danger" @click="runCardAction(() => handleDelete(acc.name))"><Trash2 class="w-4 h-4" />{{ t('accounts.deleteBtn') }}</button>
          </div>
        </div>
      </div>
      <div class="account-tile-divider" />
      <div class="account-tile-signals">
        <div><span class="account-signal-label">账号状态</span><span class="account-tile-status" :class="`account-tile-status--${acc.status}`" :title="acc.message || ''"><span class="account-status-dot" />{{ acc.status === 'active' ? t('accounts.statusOk') : (acc.message || t('accounts.statusUnknown')) }}</span></div>
        <div><span class="account-signal-label">TELEBOX</span><span class="account-tile-status" :class="{ 'account-tile-status--active': teleboxStates[acc.name]?.status === 'running', 'account-tile-status--error': teleboxStates[acc.name]?.status === 'failed' }" :title="teleboxStates[acc.name]?.message || ''"><span class="account-status-dot" />{{ teleboxLabel(acc.name) }}</span></div>
      </div>
      <form v-if="teleboxStates[acc.name]?.status === 'password_required'" class="account-tile-password" @submit.prevent="enterTeleBoxPassword(acc.name)"><label :for="`telebox-password-${acc.id}`">TeleBox 二步验证密码</label><div><input :id="`telebox-password-${acc.id}`" v-model="teleboxPasswords[acc.name]" type="password" autocomplete="current-password" class="panel-input" required /><button type="submit" class="panel-button" :disabled="teleboxBusy === acc.name">提交</button></div></form>
      <div class="account-tile-footer"><button type="button" class="account-card-primary" :disabled="checkingAccount === acc.name" @click="handleCheck(acc.name)"><ShieldCheck :size="17" aria-hidden="true" />{{ checkingAccount === acc.name ? '检测中…' : '检测账号' }}</button><button type="button" class="account-card-secondary" @click="router.push({ name: 'chats', query: { account: acc.name } })">聊天中心 <ArrowUpRight :size="16" aria-hidden="true" /></button></div>
    </article>
    </div>
    </div>

    <!-- FAB for Adding Account -->
    <div class="fixed ui-safe-fab z-40 flex flex-col items-end gap-2">
      <transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0 translate-y-2" enter-to-class="opacity-100 translate-y-0" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100 translate-y-0" leave-to-class="opacity-0 translate-y-2">
        <div v-if="showAddMenu" class="flex flex-col gap-1.5 mb-1">
          <button type="button" class="ui-card ui-card-hover flex items-center gap-2.5 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 shadow-[var(--sp-shadow-md)]" @click="openAddModal('qr')">
            <QrCode class="w-4 h-4 text-gray-500" /> {{ t('accounts.qrLogin') }}
          </button>
          <button type="button" class="ui-card ui-card-hover flex items-center gap-2.5 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-200 shadow-[var(--sp-shadow-md)]" @click="openAddModal('code')">
            <Phone class="w-4 h-4 text-gray-500" /> {{ t('accounts.codeLogin') }}
          </button>
        </div>
      </transition>
      
      <button 
        type="button"
        class="ui-fab"
        :aria-expanded="showAddMenu"
        :aria-label="showAddMenu ? t('common.close') : t('accounts.addAccount')"
        :title="showAddMenu ? t('common.close') : t('accounts.addAccount')"
        @click="showAddMenu = !showAddMenu"
      >
        <Plus class="w-5 h-5 transition-transform duration-200" :class="{ 'rotate-45': showAddMenu }" />
      </button>
    </div>

    <!-- Modals -->
    <AddAccountModal :isOpen="showAddModal" :initialMethod="initialMethod" :initialAccountName="initialAccountName" @close="showAddModal = false" @success="loadAccounts" />
    <EditAccountModal v-if="editingAccount" :isOpen="showEditModal" :account="editingAccount" @close="showEditModal = false" @success="loadAccounts" @relogin="handleRelogin" />
    <DeviceManagerModal :isOpen="showDeviceModal" :accountName="deviceAccountName" @close="showDeviceModal = false" />
    <OfficialMessagesModal :isOpen="showOfficialMessagesModal" :accountName="officialMessagesAccountName" @close="showOfficialMessagesModal = false" />
  </div>
</template>
