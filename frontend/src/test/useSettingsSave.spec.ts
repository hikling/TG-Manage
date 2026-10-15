import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mockI18nPassthrough } from './composable-test-utils'

const { toastSpy, confirmMock, api } = vi.hoisted(() => ({
  toastSpy: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    show: vi.fn(),
  },
  confirmMock: {
    confirm: vi.fn(async () => true),
  },
  api: {
    saveGlobalSettings: vi.fn(),
    testBotConnection: vi.fn(),
  },
}))

vi.mock('../composables/useI18n', () => ({
  useI18n: () => mockI18nPassthrough(),
}))
vi.mock('../composables/useToast', () => ({
  useToast: () => toastSpy,
}))
vi.mock('../composables/useConfirm', () => ({
  useConfirm: () => confirmMock,
}))
vi.mock('../lib/api', () => api)

import { useSettingsSave } from '../composables/useSettingsSave'
import { useAuthStore } from '../stores/auth'

describe('useSettingsSave', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    confirmMock.confirm.mockResolvedValue(true)
    useAuthStore().setToken('tok')
  })

  function setup() {
    const markSectionClean = vi.fn()
    const afterBotTokenSaved = vi.fn()
    const save = useSettingsSave({
      buildGeneralPayload: () => ({ general: 1 }),
      buildBotPayload: () => ({ bot: 1 }),
      markSectionClean,
      afterBotTokenSaved,
    })
    return { save, markSectionClean, afterBotTokenSaved }
  }

  it('saveSettings no-ops without token', async () => {
    useAuthStore().clearToken()
    const { save } = setup()
    await save.saveSettings()
    expect(api.saveGlobalSettings).not.toHaveBeenCalled()
  })

  it('saveSettings success marks general clean', async () => {
    api.saveGlobalSettings.mockResolvedValue({})
    const { save, markSectionClean } = setup()
    await save.saveSettings()
    expect(api.saveGlobalSettings).toHaveBeenCalledWith('tok', { general: 1 })
    expect(markSectionClean).toHaveBeenCalledWith('general')
    expect(toastSpy.success).toHaveBeenCalled()
    expect(save.loading.value).toBe(false)
  })

  it('saveSettings failure notifies error', async () => {
    api.saveGlobalSettings.mockRejectedValue(new Error('fail'))
    const { save } = setup()
    await save.saveSettings()
    expect(toastSpy.error).toHaveBeenCalled()
  })

  it('saveBotSettings runs afterBotTokenSaved', async () => {
    api.saveGlobalSettings.mockResolvedValue({})
    const { save, afterBotTokenSaved, markSectionClean } = setup()
    await save.saveBotSettings()
    expect(afterBotTokenSaved).toHaveBeenCalled()
    expect(markSectionClean).toHaveBeenCalledWith('bot')
  })

  it('saveAllSettings saves only supported global sections', async () => {
    api.saveGlobalSettings.mockResolvedValue({})
    const { save, markSectionClean } = setup()
    await save.saveAllSettings()
    expect(api.saveGlobalSettings).toHaveBeenCalledWith('tok', { general: 1, bot: 1 })
    expect(markSectionClean).toHaveBeenCalledWith('general')
    expect(markSectionClean).toHaveBeenCalledWith('bot')
  })

  it('connection test sends only a lightweight message', async () => {
    api.testBotConnection.mockResolvedValue({ success: true, message: 'ok' })
    const { save } = setup()
    await save.testBotConnection()
    expect(api.testBotConnection).toHaveBeenCalledWith('tok')
    expect(toastSpy.success).toHaveBeenCalledWith('settings.botConnectionSuccess', {
      messageKey: 'settings.botConnectionSuccess', messageParams: undefined,
    })
    expect(save.botConnectionLoading.value).toBe(false)
  })

  it('connection test reports Bot API refusal', async () => {
    api.testBotConnection.mockResolvedValue({ success: false, message: 'rejected' })
    const { save } = setup()
    await save.testBotConnection()
    expect(toastSpy.error).toHaveBeenCalledWith('rejected')
  })

})
