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
    runDeviceKeepalive: vi.fn(),
    testBotNotification: vi.fn(),
    getBotTestReportJob: vi.fn(),
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

  it('testBot starts and polls the full report before announcing delivery', async () => {
    vi.useFakeTimers()
    api.testBotNotification.mockResolvedValue({ success: true, message: 'started', job_id: 'job-1' })
    api.getBotTestReportJob.mockResolvedValue({ status: 'completed', summary: { checked: 2 }, error: null })
    const { save } = setup()
    const pending = save.testBot()
    expect(save.botTestLoading.value).toBe(true)
    await vi.runAllTimersAsync()
    await pending
    expect(api.getBotTestReportJob).toHaveBeenCalledWith('tok', 'job-1')
    expect(toastSpy.success).toHaveBeenCalledWith('settings.botTestStarted', { messageKey: 'settings.botTestStarted', messageParams: undefined })
    expect(toastSpy.success).toHaveBeenCalledWith('settings.botTestSuccess', { messageKey: 'settings.botTestSuccess', messageParams: undefined })
    expect(save.botTestLoading.value).toBe(false)
    vi.useRealTimers()
  })

  it('testBot reports start and background failures', async () => {
    api.testBotNotification.mockResolvedValue({ success: false, message: 'bad' })
    const { save } = setup()
    await save.testBot()
    expect(toastSpy.error).toHaveBeenCalledWith('bad')

    vi.useFakeTimers()
    api.testBotNotification.mockResolvedValue({ success: true, message: 'started', job_id: 'job-2' })
    api.getBotTestReportJob.mockResolvedValue({ status: 'failed', error: '检测未完整完成' })
    const pending = save.testBot()
    await vi.runAllTimersAsync()
    await pending
    expect(toastSpy.error).toHaveBeenCalledWith('检测未完整完成')
    vi.useRealTimers()
  })

  it('runKeepaliveNow formats result', async () => {
    api.runDeviceKeepalive.mockResolvedValue({ kept_alive: 2, checked: 3, failed: 1 })
    const { save } = setup()
    await save.runKeepaliveNow()
    expect(toastSpy.success).toHaveBeenCalled()
    expect(String(toastSpy.success.mock.calls[0][0])).toContain('2')
  })

})
