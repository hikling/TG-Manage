/**
 * 设置页：通用配置与通知的分块保存。
 */
import { getCurrentScope, onScopeDispose, ref } from 'vue'
import {
  saveGlobalSettings,
  runDeviceKeepalive,
  testBotNotification,
  getBotTestReportJob,
} from '../lib/api'
import { withToken } from '../lib/api/core'
import type { SettingsSection } from '../lib/settings-form'
import { resolveApiErrorMessage } from '../lib/notify'
import { setPanelTimezone } from '../lib/datetime'
import { useI18n } from './useI18n'
import { useToast } from './useToast'

export function useSettingsSave(options: {
  buildGeneralPayload: () => Record<string, unknown>
  buildBotPayload: () => Record<string, unknown>
  markSectionClean: (section: SettingsSection) => void
  afterBotTokenSaved: () => void
}) {
  const { t } = useI18n()
  const toast = useToast()
  const notifySuccess = (key: string, params?: Record<string, unknown>) => toast.success(t(key, params), { messageKey: key, messageParams: params })
  const notifyError = (msg: string) => toast.error(msg)

  const loading = ref(false)
  const botLoading = ref(false)
  const saveAllLoading = ref(false)
  const botTestLoading = ref(false)
  const keepaliveLoading = ref(false)
  let disposed = false
  if (getCurrentScope()) onScopeDispose(() => { disposed = true })

  const saveSettings = async () => {
    return withToken(async (token) => {
      loading.value = true
      try {
        await saveGlobalSettings(token, options.buildGeneralPayload())
        // 保存成功后立即同步面板展示时区，Dashboard/Logs 等页时间格式跟随
        setPanelTimezone(String(options.buildGeneralPayload().timezone || ''))
        options.markSectionClean('general')
        notifySuccess('settings.saveSuccess')
      } catch (e: unknown) {
        notifyError(resolveApiErrorMessage(e, 'settings.saveFailed'))
      } finally {
        loading.value = false
      }
    })
  }

  const runKeepaliveNow = async () => {
    return withToken(async (token) => {
      keepaliveLoading.value = true
      try {
        const res = await runDeviceKeepalive(token)
        // 整句走 i18n 插值：标点与语序交给词条，避免英文界面混入中文全角标点
        notifySuccess(
          'settings.keepaliveSummary', {
            kept: res.kept_alive,
            checked: res.checked,
            failed: res.failed,
          },
        )
      } catch (e: unknown) {
        notifyError(resolveApiErrorMessage(e, 'settings.keepaliveFailed'))
      } finally {
        keepaliveLoading.value = false
      }
    })
  }

  const saveBotSettings = async () => {
    return withToken(async (token) => {
      botLoading.value = true
      try {
        await saveGlobalSettings(token, options.buildBotPayload())
        options.afterBotTokenSaved()
        options.markSectionClean('bot')
        notifySuccess('settings.saveSuccess')
      } catch (e: unknown) {
        notifyError(resolveApiErrorMessage(e, 'settings.saveFailed'))
      } finally {
        botLoading.value = false
      }
    })
  }

  const saveAllSettings = async () => {
    return withToken(async (token) => {
      saveAllLoading.value = true
      try {
        await saveGlobalSettings(token, {
          ...options.buildGeneralPayload(),
          ...options.buildBotPayload(),
        })
        // 保存成功后立即同步面板展示时区，Dashboard/Logs 等页时间格式跟随
        setPanelTimezone(String(options.buildGeneralPayload().timezone || ''))
        options.afterBotTokenSaved()
        options.markSectionClean('general')
        options.markSectionClean('bot')
        notifySuccess('settings.saveAllSuccess')
      } catch (e: unknown) {
        notifyError(resolveApiErrorMessage(e, 'settings.saveFailed'))
      } finally {
        saveAllLoading.value = false
      }
    })
  }

  const testBot = async () => {
    return withToken(async (token) => {
      if (botTestLoading.value) return
      botTestLoading.value = true
      try {
        const res = await testBotNotification(token)
        if (!res.success) {
          notifyError(resolveApiErrorMessage(res.message, 'settings.testFailed'))
          return
        }
        if (!res.job_id) throw new Error('Missing report job ID')
        notifySuccess('settings.botTestStarted')
        while (!disposed) {
          await new Promise((resolve) => setTimeout(resolve, 2000))
          if (disposed) break
          const job = await getBotTestReportJob(token, res.job_id)
          if (job.status === 'completed') {
            notifySuccess('settings.botTestSuccess')
            break
          }
          if (job.status === 'failed' || job.status === 'canceled') {
            notifyError(resolveApiErrorMessage(job.error, 'settings.testFailed'))
            break
          }
        }
      } catch (e: unknown) {
        if (!disposed) notifyError(resolveApiErrorMessage(e, 'settings.testFailed'))
      } finally {
        botTestLoading.value = false
      }
    })
  }

  return {
    loading,
    botLoading,
    saveAllLoading,
    botTestLoading,
    keepaliveLoading,
    saveSettings,
    runKeepaliveNow,
    saveBotSettings,
    saveAllSettings,
    testBot,
  }
}
