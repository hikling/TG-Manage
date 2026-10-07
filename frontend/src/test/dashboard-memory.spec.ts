import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({
  getMemoryStats: vi.fn(),
  listTeleBoxAccounts: vi.fn(),
  ensureAccounts: vi.fn(),
}))

vi.mock('../lib/api/ops', () => ({ getMemoryStats: api.getMemoryStats }))
vi.mock('../lib/api/telebox', () => ({ listTeleBoxAccounts: api.listTeleBoxAccounts }))
vi.mock('../lib/api/core', () => ({ getAuthToken: () => 'token' }))
vi.mock('../stores/accounts', () => ({
  useAccountsStore: () => ({ accounts: [], ensureAccounts: api.ensureAccounts }),
}))

import Dashboard from '../views/Dashboard.vue'

describe('dashboard process memory', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    api.getMemoryStats.mockReset().mockResolvedValue({ available: true, stats: { current_rss_mb: 123.45 } })
    api.listTeleBoxAccounts.mockReset().mockResolvedValue({ accounts: [] })
    api.ensureAccounts.mockReset().mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('shows backend RSS and refreshes without overlapping requests', async () => {
    const wrapper = mount(Dashboard, { global: { stubs: { RouterLink: true } } })
    await Promise.resolve()
    await Promise.resolve()
    expect(wrapper.text()).toContain('123.5 MB')
    expect(wrapper.text()).toContain('当前服务进程 RSS')
    expect(api.getMemoryStats).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(15_000)
    expect(api.getMemoryStats).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.getMemoryStats).toHaveBeenCalledTimes(2)
  })

  it('shows unavailable state and does not update an unmounted view', async () => {
    let finish!: (value: { available: boolean; stats: Record<string, unknown> }) => void
    api.getMemoryStats.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const wrapper = mount(Dashboard, { global: { stubs: { RouterLink: true } } })
    wrapper.unmount()
    finish({ available: false, stats: {} })
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.getMemoryStats).toHaveBeenCalledTimes(1)
  })

  it('pauses polling in a hidden tab and refreshes when visible again', async () => {
    let hidden = false
    vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden)
    const wrapper = mount(Dashboard, { global: { stubs: { RouterLink: true } } })
    await Promise.resolve()
    await Promise.resolve()
    hidden = true
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(30_000)
    expect(api.getMemoryStats).toHaveBeenCalledTimes(1)

    hidden = false
    document.dispatchEvent(new Event('visibilitychange'))
    await Promise.resolve()
    expect(api.getMemoryStats).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
