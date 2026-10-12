import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import i18n from '../i18n'
import type { AccountInfo } from '../lib/api'
import { useAccountsStore } from '../stores/accounts'
import { useAuthStore } from '../stores/auth'
import { flushPromises } from './composable-test-utils'

const api = vi.hoisted(() => ({
  listAccounts: vi.fn(),
  listTeleBoxAccounts: vi.fn(),
  getMemoryStats: vi.fn(),
}))

vi.mock('../lib/api', () => ({ listAccounts: api.listAccounts }))
vi.mock('../lib/api/telebox', () => ({ listTeleBoxAccounts: api.listTeleBoxAccounts }))
vi.mock('../lib/api/ops', () => ({ getMemoryStats: api.getMemoryStats }))
vi.mock('../lib/api/appearance', () => ({
  getHeroImage: vi.fn().mockRejectedValue(new Error('no cover')),
  getHeroSettings: vi.fn().mockRejectedValue(new Error('no cover')),
}))

import Dashboard from '../views/Dashboard.vue'

type Listing = { accounts: AccountInfo[]; total: number }
function listing(status = 'connected', reason = ''): Listing {
  return {
    accounts: [{
      name: 'midnight-account', session_file: '', exists: true, size: 1,
      status, status_message: reason, needs_relogin: status === 'invalid',
      status_checked_at: '2026-10-12T00:00:00Z',
    }],
    total: 1,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

function visibility(hidden: boolean) {
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(hidden)
  document.dispatchEvent(new Event('visibilitychange'))
}

let wrapper: VueWrapper | undefined
function mountDashboard() {
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.setToken('current-session')
  const store = useAccountsStore(pinia)
  wrapper = mount(Dashboard, {
    global: { plugins: [pinia, i18n], stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
  return { wrapper, auth, store }
}

describe('dashboard saved account status refresh', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
    api.listAccounts.mockResolvedValue(listing())
    api.listTeleBoxAccounts.mockResolvedValue({ accounts: [] })
    api.getMemoryStats.mockResolvedValue({ available: true, stats: { current_rss_mb: 12 } })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = undefined
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('uses persisted midnight failure and recovery for attention and healthy metrics without probes', async () => {
    api.listAccounts.mockResolvedValueOnce(listing())
      .mockResolvedValueOnce(listing('checking', '检测超时'))
      .mockResolvedValueOnce(listing())
    const { wrapper, store } = mountDashboard()
    await flushPromises()
    expect(wrapper.find('.dashboard-metric--tasks .dashboard-metric-value').text()).toBe('1')
    expect(wrapper.findAll('.dashboard-activity-item')).toHaveLength(0)

    await vi.advanceTimersByTimeAsync(30_000)
    expect(wrapper.find('.dashboard-metric--tasks .dashboard-metric-value').text()).toBe('0')
    expect(wrapper.find('.dashboard-activity-item').text()).toContain('midnight-account')
    expect(wrapper.find('.dashboard-activity-state').text()).toBe('检测超时')
    expect(store.accounts[0]?.status_checked_at).toBe('2026-10-12T00:00:00Z')

    await vi.advanceTimersByTimeAsync(30_000)
    expect(wrapper.find('.dashboard-metric--tasks .dashboard-metric-value').text()).toBe('1')
    expect(wrapper.findAll('.dashboard-activity-item')).toHaveLength(0)
    expect(api.listAccounts).toHaveBeenCalledTimes(3)
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('waits for a slow metadata read to settle before scheduling its next refresh', async () => {
    const slow = deferred<Listing>()
    api.listAccounts.mockResolvedValueOnce(listing()).mockReturnValueOnce(slow.promise)
    mountDashboard()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(30_000)
    await vi.advanceTimersByTimeAsync(90_000)
    expect(api.listAccounts).toHaveBeenCalledTimes(2)
    slow.resolve(listing('invalid', '会话失效，请重新登录'))
    await flushPromises()
    await vi.advanceTimersByTimeAsync(29_999)
    expect(api.listAccounts).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(api.listAccounts).toHaveBeenCalledTimes(3)
    expect(api.getMemoryStats.mock.calls.length).toBeGreaterThan(3)
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
  })

  it('does not read metadata while hidden, and resumes on visibility', async () => {
    visibility(true)
    mountDashboard()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(90_000)
    expect(api.listAccounts).not.toHaveBeenCalled()
    expect(api.getMemoryStats).not.toHaveBeenCalled()
    visibility(false)
    await flushPromises()
    expect(api.listAccounts).toHaveBeenCalledTimes(1)
    expect(api.getMemoryStats).toHaveBeenCalledTimes(1)
    visibility(true)
    await vi.advanceTimersByTimeAsync(90_000)
    expect(api.listAccounts).toHaveBeenCalledTimes(1)
    visibility(false)
    await flushPromises()
    expect(api.listAccounts).toHaveBeenCalledTimes(2)
  })

  it('coalesces visibility changes during a request and ignores its superseded error', async () => {
    const slow = deferred<Listing>()
    api.listAccounts.mockResolvedValueOnce(listing()).mockReturnValueOnce(slow.promise)
      .mockResolvedValueOnce(listing('invalid', '新检测结果'))
    const { wrapper } = mountDashboard()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(30_000)
    visibility(true)
    visibility(false)
    visibility(false)
    expect(api.listAccounts).toHaveBeenCalledTimes(2)
    slow.reject(new Error('old hidden error'))
    await flushPromises()
    expect(api.listAccounts).toHaveBeenCalledTimes(3)
    expect(wrapper.findAll('[role="alert"]')).toHaveLength(0)
    expect(wrapper.find('.dashboard-activity-state').text()).toBe('新检测结果')
  })

  it('retains saved data on refresh errors and does not clear an unrelated TeleBox error', async () => {
    api.listTeleBoxAccounts.mockRejectedValueOnce(new Error('telebox unavailable'))
    api.listAccounts.mockResolvedValueOnce(listing('invalid', '请重新登录'))
      .mockRejectedValueOnce(new Error('metadata unavailable'))
      .mockResolvedValueOnce(listing())
    const { wrapper, store } = mountDashboard()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(store.accounts[0]?.status).toBe('invalid')
    expect(wrapper.find('.dashboard-activity-state').text()).toBe('请重新登录')
    expect(wrapper.findAll('[role="alert"]').map(alert => alert.text()))
      .toEqual(['telebox unavailable', 'metadata unavailable'])
    await vi.advanceTimersByTimeAsync(30_000)
    expect(wrapper.findAll('[role="alert"]').map(alert => alert.text())).toEqual(['telebox unavailable'])
    expect(wrapper.findAll('.dashboard-activity-item')).toHaveLength(0)
  })

  it('localizes a retained metadata error when the language changes without another request', async () => {
    const previousLocale = i18n.global.locale.value
    try {
      i18n.global.locale.value = 'zh-CN'
      api.listAccounts.mockResolvedValueOnce(listing())
        .mockRejectedValueOnce(new Error('账号状态数据读取失败'))
      const { wrapper, store } = mountDashboard()
      await flushPromises()
      await vi.advanceTimersByTimeAsync(30_000)
      expect(wrapper.find('[role="alert"]').text()).toBe('账号状态数据读取失败')

      i18n.global.locale.value = 'en-US'
      await flushPromises()
      expect(wrapper.find('[role="alert"]').text()).toBe(i18n.global.t('common.requestFailed'))
      expect(api.listAccounts).toHaveBeenCalledTimes(2)
      expect(store.accounts[0]?.status).toBe('connected')
    } finally {
      i18n.global.locale.value = previousLocale
    }
  })

  it('stops page refresh ownership on unmount while preserving a same-session shared cache completion', async () => {
    const slow = deferred<Listing>()
    api.listAccounts.mockResolvedValueOnce(listing()).mockReturnValueOnce(slow.promise)
    const { wrapper, store } = mountDashboard()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(30_000)
    wrapper.unmount()
    slow.resolve(listing('invalid', '检测异常'))
    await flushPromises()
    const memoryReads = api.getMemoryStats.mock.calls.length
    visibility(false)
    await vi.advanceTimersByTimeAsync(90_000)
    expect(api.listAccounts).toHaveBeenCalledTimes(2)
    expect(api.getMemoryStats).toHaveBeenCalledTimes(memoryReads)
    expect(vi.getTimerCount()).toBe(0)
    expect(store.accounts[0]?.status).toBe('invalid')
  })

  it('discards an old-session result even when the token changes away and back during a read', async () => {
    const slow = deferred<Listing>()
    const fresh = deferred<Listing>()
    api.listAccounts.mockResolvedValueOnce(listing()).mockReturnValueOnce(slow.promise)
      .mockReturnValueOnce(fresh.promise)
    const { auth, store, wrapper } = mountDashboard()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(30_000)
    auth.clearToken()
    auth.setToken('current-session')
    expect(store.accounts).toEqual([])
    expect(api.listAccounts).toHaveBeenCalledTimes(2)
    slow.resolve(listing('invalid', 'previous session'))
    await flushPromises()
    expect(api.listAccounts).toHaveBeenCalledTimes(3)
    expect(store.accounts).toEqual([])
    expect(wrapper.text()).not.toContain('previous session')
    fresh.resolve(listing('checking', 'current result'))
    await flushPromises()
    expect(wrapper.find('.dashboard-activity-state').text()).toBe('current result')
  })

  it('keeps the attention preview bounded while the shared store retains all saved failures', async () => {
    const failures = Array.from({ length: 12 }, (_, index) => ({ ...listing('error', '检测失败').accounts[0]!, name: `account-${index}` }))
    api.listAccounts.mockResolvedValue({ accounts: failures, total: failures.length })
    const { wrapper, store } = mountDashboard()
    await flushPromises()
    expect(wrapper.findAll('.dashboard-activity-item')).toHaveLength(8)
    expect(store.accounts).toHaveLength(12)
    expect(wrapper.find('.dashboard-section-heading a').exists()).toBe(true)
  })
})
