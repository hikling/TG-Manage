/**
 * 设置页：通用配置与通知的分块保存。
 */
import { ref } from 'vue'
import {
  saveGlobalSettings,
  testBotConnection as testBotConnectionRequest,
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
  const botConnectionLoading = ref(false)

  const saveSettings = async () => {
    return withToken(async (token) => {
      loading.value = true
      try {
        await saveGlobalSettings(token, options.buildGeneralPayload())
        // 保存成功后立即同步面板展示时区，Dashboard 等页时间格式跟随
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

  const saveBotSettings = async () => {
    return withToken(async (token) => {
      botLoading.value = true
      try {
        const result = await saveGlobalSettings(token, options.buildBotPayload())
        options.afterBotTokenSaved()
        options.markSectionClean('bot')
        notifySuccess('settings.saveSuccess')
        if (result.telegram_web_menu_synced === false) notifyError(t('settings.botWebMenuSyncFailed'))
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
        const result = await saveGlobalSettings(token, {
          ...options.buildGeneralPayload(),
          ...options.buildBotPayload(),
        })
        // 保存成功后立即同步面板展示时区，Dashboard 等页时间格式跟随
        setPanelTimezone(String(options.buildGeneralPayload().timezone || ''))
        options.afterBotTokenSaved()
        options.markSectionClean('general')
        options.markSectionClean('bot')
        notifySuccess('settings.saveAllSuccess')
        if (result.telegram_web_menu_synced === false) notifyError(t('settings.botWebMenuSyncFailed'))
      } catch (e: unknown) {
        notifyError(resolveApiErrorMessage(e, 'settings.saveFailed'))
      } finally {
        saveAllLoading.value = false
      }
    })
  }

  const testBotConnection = async () => {
    return withToken(async (token) => {
      if (botConnectionLoading.value) return
      botConnectionLoading.value = true
      try {
        const res = await testBotConnectionRequest(token)
        if (res.success) notifySuccess('settings.botConnectionSuccess')
        else notifyError(resolveApiErrorMessage(res.message, 'settings.botConnectionFailed'))
      } catch (e: unknown) {
        notifyError(resolveApiErrorMessage(e, 'settings.botConnectionFailed'))
      } finally {
        botConnectionLoading.value = false
      }
    })
  }

  return {
    loading,
    botLoading,
    saveAllLoading,
    botConnectionLoading,
    saveSettings,
    saveBotSettings,
    saveAllSettings,
    testBotConnection,
  }
}
