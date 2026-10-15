/**
 * 系统设置页业务逻辑：加载/保存/脏检查/版本检查。
 * Settings.vue 仅负责布局与子组件接线。
 */
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import {
  getGlobalSettings,
  getRuntimeStatus,
  getMemoryStats,
  getProxySubscriptions,
  saveProxySubscriptions,
  refreshProxySubscriptions,
} from '../lib/api'
import { getAuthToken } from '../lib/api/core'
import type { RuntimeStatus, MemoryStatsResponse } from '../lib/api'
import type { ProxySubscriptionSettings, ProxySubscriptionUpdate } from '../lib/api/settings'
import type { SubscriptionDraft } from '../components/settings/ProxySubscriptionsSettings.vue'
import { useI18n } from './useI18n'
import { useToast } from './useToast'
import { useConfirm } from './useConfirm'
import { resolveApiErrorMessage } from '../lib/notify'
import { setPanelTimezone } from '../lib/datetime'
import { devLog } from '../lib/devLog'
import {
  applyGlobalSettingsToForm,
  buildBotPayload as buildBotPayloadOf,
  buildGeneralPayload as buildGeneralPayloadOf,
  dirtySectionLabels,
  isAnySectionDirty,
  snapAllSections,
  type SettingsSection,
  type SettingsFormState,
} from '../lib/settings-form'
import { useSettingsVersionCheck } from './useSettingsVersionCheck'
import { useSettingsSave } from './useSettingsSave'

export function useSettingsPage() {
  const { t } = useI18n()
  const toast = useToast()
  const { confirm } = useConfirm()

  const settings = ref<SettingsFormState>({
    logDays: 7,
    dataDir: '',
    concurrency: '',
    deviceKeepaliveEnabled: true,
    deviceKeepaliveIntervalDays: 30,
    botEnabled: false,
    botLoginNotify: false,
    botCodeEnabled: false,
    botToken: '',
    botChatId: '',
    botThreadId: '',
    timezone: 'Asia/Hong_Kong',
  })

  // 时区选项列表
  const timezoneOptions = [
    { label: 'Asia/Shanghai (UTC+8)', value: 'Asia/Shanghai' },
    { label: 'Asia/Hong_Kong (UTC+8)', value: 'Asia/Hong_Kong' },
    { label: 'Asia/Tokyo (UTC+9)', value: 'Asia/Tokyo' },
    { label: 'Asia/Seoul (UTC+9)', value: 'Asia/Seoul' },
    { label: 'Asia/Singapore (UTC+8)', value: 'Asia/Singapore' },
    { label: 'Asia/Taipei (UTC+8)', value: 'Asia/Taipei' },
    { label: 'Asia/Bangkok (UTC+7)', value: 'Asia/Bangkok' },
    { label: 'Asia/Dubai (UTC+4)', value: 'Asia/Dubai' },
    { label: 'Asia/Kolkata (UTC+5:30)', value: 'Asia/Kolkata' },
    { label: 'Australia/Sydney (UTC+10/+11)', value: 'Australia/Sydney' },
    { label: 'America/New_York (UTC-5/-4)', value: 'America/New_York' },
    { label: 'America/Chicago (UTC-6/-5)', value: 'America/Chicago' },
    { label: 'America/Denver (UTC-7/-6)', value: 'America/Denver' },
    { label: 'America/Los_Angeles (UTC-8/-7)', value: 'America/Los_Angeles' },
    { label: 'America/Sao_Paulo (UTC-3)', value: 'America/Sao_Paulo' },
    { label: 'Europe/London (UTC+0/+1)', value: 'Europe/London' },
    { label: 'Europe/Berlin (UTC+1/+2)', value: 'Europe/Berlin' },
    { label: 'Europe/Paris (UTC+1/+2)', value: 'Europe/Paris' },
    { label: 'Europe/Moscow (UTC+3)', value: 'Europe/Moscow' },
    { label: 'Africa/Cairo (UTC+2)', value: 'Africa/Cairo' },
    { label: 'Pacific/Auckland (UTC+12/+13)', value: 'Pacific/Auckland' },
    { label: 'UTC', value: 'UTC' },
  ]

  const runtimeStatus = ref<RuntimeStatus | null>(null)
  const memoryStats = ref<MemoryStatsResponse | null>(null)
  const subscriptions = ref<ProxySubscriptionSettings | null>(null)
  const subscriptionDraft = ref<SubscriptionDraft>({
    primaryUrl: '', fallbackUrl: '', clearPrimary: false, clearFallback: false, latencyThresholdMs: 800,
  })
  const subscriptionBaseline = ref<string | null>(null)
  const subscriptionError = ref('')
  const subscriptionLoading = ref(false)
  const subscriptionRefreshing = ref(false)
  const pageLoading = ref(true)
  /** 全局设置加载失败标记：失败时展示错误态与重试，而非默认空表单 */
  const loadFailed = ref(false)
  // 卸载标记：异步加载期间离开页面时停止后续副作用
  let disposed = false
  const botTokenSet = ref(false)
  const botCodeStatus = ref('')
  let botStatusTimer: ReturnType<typeof setInterval> | undefined
  const afterBotTokenSaved = () => {
    if (settings.value.botToken) {
      botTokenSet.value = true
      settings.value.botToken = ''
    }
  }
  /** 密钥字段显隐（默认隐藏） */
  const revealSecrets = ref({
    botToken: false,
  })

  /** 分段脏检查基线（分块保存只清对应段） */
  const sectionBaseline = ref<Record<SettingsSection, string> | null>(null)

  const currentSectionSnaps = () =>
    snapAllSections(settings.value)

  const markAllClean = () => {
    sectionBaseline.value = currentSectionSnaps()
  }

  const markSectionClean = (section: SettingsSection) => {
    if (!sectionBaseline.value) {
      markAllClean()
      return
    }
    sectionBaseline.value = {
      ...sectionBaseline.value,
      [section]: snapSectionFor(section),
    }
  }

  const snapSectionFor = (section: SettingsSection) =>
    currentSectionSnaps()[section]

  const subscriptionSnapshot = () => JSON.stringify(subscriptionDraft.value)
  const subscriptionDirty = computed(() => subscriptionBaseline.value !== null && subscriptionBaseline.value !== subscriptionSnapshot())
  const isDirty = computed(() =>
    isAnySectionDirty(sectionBaseline.value, currentSectionSnaps()) || subscriptionDirty.value,
  )

  const dirtyLabels = computed(() =>
    [...dirtySectionLabels(sectionBaseline.value, currentSectionSnaps(), {
      general: t('settings.general'),
      bot: t('settings.botNotify'),
    }), ...(subscriptionDirty.value ? [t('settings.subscriptions.title')] : [])],
  )

  const onBeforeUnload = (e: BeforeUnloadEvent) => {
    if (!isDirty.value) return
    e.preventDefault()
    e.returnValue = ''
  }

  onBeforeRouteLeave(async () => {
    if (!isDirty.value) return true
    const ok = await confirm({
      title: t('settings.unsavedTitle'),
      message: t('settings.unsavedMessage'),
      confirmText: t('settings.leaveAnyway'),
      danger: true,
    })
    return ok
  })

  const {
    appVersion,
    versionLoading,
    checkLoading,
    versionBanner,
    loadVersion,
    handleCheckUpdate,
  } = useSettingsVersionCheck()

  const buildGeneralPayload = () => buildGeneralPayloadOf(settings.value)
  const buildBotPayload = () => buildBotPayloadOf(settings.value)
  const {
    loading,
    botLoading,
    saveAllLoading,
    botConnectionLoading,
    keepaliveLoading,
    saveSettings,
    runKeepaliveNow,
    saveBotSettings,
    saveAllSettings: saveGlobalSections,
    testBotConnection,
  } = useSettingsSave({
    buildGeneralPayload,
    buildBotPayload,
    markSectionClean,
    afterBotTokenSaved,
  })

  const applySubscriptionSettings = (value: ProxySubscriptionSettings) => {
    subscriptions.value = value
    // URLs never come back from GET/PUT; an empty input always means "keep".
    subscriptionDraft.value = {
      primaryUrl: '', fallbackUrl: '', clearPrimary: false, clearFallback: false,
      latencyThresholdMs: value.latency_threshold_ms,
    }
    subscriptionBaseline.value = subscriptionSnapshot()
    subscriptionError.value = ''
  }

  const loadSubscriptions = async () => {
    const token = getAuthToken()
    if (!token) return
    try {
      const result = await getProxySubscriptions(token)
      if (!disposed) applySubscriptionSettings(result)
    } catch (error: unknown) {
      if (!disposed) subscriptionError.value = resolveApiErrorMessage(error, 'settings.subscriptions.loadFailed')
    }
  }

  const saveSubscriptions = async (): Promise<boolean> => {
    const token = getAuthToken()
    if (!token || !subscriptions.value || subscriptionLoading.value || !subscriptionDirty.value) return false
    const draft = subscriptionDraft.value
    const update: ProxySubscriptionUpdate = {}
    if (draft.clearPrimary) update.primary_url = null
    else if (draft.primaryUrl.trim()) update.primary_url = draft.primaryUrl.trim()
    if (draft.clearFallback) update.fallback_url = null
    else if (draft.fallbackUrl.trim()) update.fallback_url = draft.fallbackUrl.trim()
    if (draft.latencyThresholdMs !== subscriptions.value.latency_threshold_ms) {
      if (typeof draft.latencyThresholdMs !== 'number' || !Number.isInteger(draft.latencyThresholdMs)) {
        subscriptionError.value = t('settings.subscriptions.invalidThreshold')
        return false
      }
      update.latency_threshold_ms = draft.latencyThresholdMs
    }
    subscriptionLoading.value = true
    subscriptionError.value = ''
    try {
      const result = await saveProxySubscriptions(token, update)
      if (!disposed) {
        applySubscriptionSettings(result)
        toast.success(t('settings.subscriptions.saved'), { messageKey: 'settings.subscriptions.saved' })
      }
      return true
    } catch (error: unknown) {
      if (!disposed) subscriptionError.value = resolveApiErrorMessage(error, 'settings.subscriptions.saveFailed')
      return false
    } finally {
      subscriptionLoading.value = false
    }
  }

  const refreshSubscriptions = async () => {
    const token = getAuthToken()
    if (!token || subscriptionRefreshing.value || subscriptionDirty.value) return
    subscriptionRefreshing.value = true
    subscriptionError.value = ''
    try {
      const result = await refreshProxySubscriptions(token)
      if (!disposed) {
        applySubscriptionSettings(result)
        toast.success(t('settings.subscriptions.refreshed'), { messageKey: 'settings.subscriptions.refreshed' })
      }
    } catch (error: unknown) {
      if (!disposed) subscriptionError.value = resolveApiErrorMessage(error, 'settings.subscriptions.refreshFailed')
    } finally {
      subscriptionRefreshing.value = false
    }
  }

  const saveAllSettings = async () => {
    // Each endpoint owns its section; a failed save retains that section's dirty state.
    if (isAnySectionDirty(sectionBaseline.value, currentSectionSnaps())) await saveGlobalSections()
    if (subscriptionDirty.value) await saveSubscriptions()
  }

  const loadAllSettings = async () => {
    const token = getAuthToken()
    if (!token) {
      pageLoading.value = false
      return
    }

    try {
      const res = await getGlobalSettings(token)
      const flags = applyGlobalSettingsToForm(settings.value, res)
      botTokenSet.value = flags.botTokenSet
      botCodeStatus.value = res.telegram_bot_code_status || ''
      // 同步面板展示时区：Settings 加载后，Dashboard/Logs 等页的时间格式跟随
      setPanelTimezone(res.timezone)


      // 运行信息互不依赖，并行请求可以减少设置页首屏等待；单项失败仍然降级。
      const [runtimeResult, memoryResult, versionResult, subscriptionResult] =
        await Promise.allSettled([
          getRuntimeStatus(token),
          getMemoryStats(token),
          loadVersion(token),
          getProxySubscriptions(token),
        ])
      if (runtimeResult.status === 'fulfilled') {
        runtimeStatus.value = runtimeResult.value
      } else {
        devLog.error('Failed to load runtime status', runtimeResult.reason)
      }
      if (memoryResult.status === 'fulfilled') {
        memoryStats.value = memoryResult.value
      } else {
        devLog.error('Failed to load memory stats', memoryResult.reason)
      }
      if (versionResult.status === 'rejected') {
        devLog.error('Failed to load app version', versionResult.reason)
      }
      if (subscriptionResult.status === 'fulfilled') {
        applySubscriptionSettings(subscriptionResult.value)
      } else {
        subscriptionError.value = resolveApiErrorMessage(subscriptionResult.reason, 'settings.subscriptions.loadFailed')
      }
      if (disposed) return // 加载期间已卸载：不再标记干净或注册监听
      markAllClean()
      loadFailed.value = false
    } catch (e: unknown) {
      devLog.error('Failed to load settings', e)
      loadFailed.value = true
      toast.error(resolveApiErrorMessage(e, 'settings.loadFailed'))
    } finally {
      if (!disposed) pageLoading.value = false
    }
  }

  onMounted(async () => {
    // 同步注册 beforeunload：避免异步加载期间卸载导致监听器永久泄漏
    window.addEventListener('beforeunload', onBeforeUnload)
    await loadAllSettings()
    botStatusTimer = setInterval(async () => {
      const token = getAuthToken()
      if (!token || disposed || document.hidden) return
      try {
        const latest = await getGlobalSettings(token)
        if (!disposed) botCodeStatus.value = latest.telegram_bot_code_status || ''
      } catch {
        // Keep the last known status; normal settings load owns error feedback.
      }
    }, 20_000)
  })

  onUnmounted(() => {
    disposed = true
    window.removeEventListener('beforeunload', onBeforeUnload)
    if (botStatusTimer) clearInterval(botStatusTimer)
  })


  const toggleReveal = (key: 'botToken') => {
    revealSecrets.value = {
      ...revealSecrets.value,
      [key]: !revealSecrets.value[key],
    }
  }

  return {
    t,
    settings,
    timezoneOptions,
    loading,
    runtimeStatus,
    memoryStats,
    subscriptions,
    subscriptionDraft,
    subscriptionDirty,
    subscriptionError,
    subscriptionLoading,
    subscriptionRefreshing,
    loadSubscriptions,
    saveSubscriptions,
    refreshSubscriptions,
    botConnectionLoading,
    pageLoading,
    loadFailed,
    /** 重新加载全局设置（失败重试入口） */
    reload: loadAllSettings,
    revealSecrets,
    isDirty,
    dirtyLabels,
    appVersion,
    versionLoading,
    checkLoading,
    versionBanner,
    botLoading,
    keepaliveLoading,
    saveAllLoading,
    botTokenSet,
    botCodeStatus,
    saveSettings,
    runKeepaliveNow,
    saveBotSettings,
    saveAllSettings,
    testBotConnection,
    handleCheckUpdate,
    toggleReveal,
  }
}
