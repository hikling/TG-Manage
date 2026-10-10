import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({ listTeleBoxAccounts: vi.fn(), panelRequest: vi.fn() }))
vi.mock('../lib/api/telebox', () => ({ listTeleBoxAccounts: api.listTeleBoxAccounts }))
vi.mock('../lib/api/communications', () => ({ panelRequest: api.panelRequest }))
vi.mock('../composables/usePanelAccount', () => ({ errorText: (cause: unknown) => String(cause) }))
vi.mock('../composables/useI18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))

import Logs from '../views/Logs.vue'

const accounts = { accounts: [
  { account: 'alpha', status: 'running', enabled: true, authorized: true },
  { account: 'beta', status: 'running', enabled: true, authorized: true },
] }
const entry = (message: string) => ({ time: '2026-10-10T00:00:00Z', level: 'info', message })

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('log polling resource ownership', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    api.listTeleBoxAccounts.mockReset().mockResolvedValue(accounts)
    api.panelRequest.mockReset().mockResolvedValue({ items: [] })
  })
  afterEach(() => { vi.useRealTimers() })

  it('waits for slow requests and owns only one polling timer', async () => {
    const overview = deferred<typeof accounts>()
    api.listTeleBoxAccounts.mockReturnValueOnce(overview.promise)
    const wrapper = mount(Logs)
    await vi.advanceTimersByTimeAsync(20_000)
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
    expect(api.panelRequest).not.toHaveBeenCalled()

    overview.resolve(accounts)
    await flushPromises()
    expect(api.panelRequest).toHaveBeenCalledTimes(1)
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(20_000)
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(2)
  })

  it('coalesces account changes and discards the previous account response', async () => {
    const stale = deferred<{ items: ReturnType<typeof entry>[] }>()
    api.panelRequest.mockReturnValueOnce(stale.promise)
    const wrapper = mount(Logs)
    await flushPromises()
    await wrapper.find('select').setValue('beta')
    await wrapper.find('select').setValue('alpha')
    await wrapper.find('select').setValue('beta')
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
    stale.resolve({ items: [entry('stale alpha')] })
    api.panelRequest.mockResolvedValueOnce({ items: [entry('latest beta')] })
    await flushPromises()
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(2)
    expect(api.panelRequest).toHaveBeenLastCalledWith('/telebox/beta/logs')
    expect(wrapper.text()).not.toContain('stale alpha')
    expect(wrapper.text()).toContain('latest beta')
    wrapper.unmount()
  })

  it('does not create a follow-up request or timer after unmount', async () => {
    const stale = deferred<{ items: ReturnType<typeof entry>[] }>()
    api.panelRequest.mockReturnValueOnce(stale.promise)
    const wrapper = mount(Logs)
    await flushPromises()
    await wrapper.find('select').setValue('beta')
    wrapper.unmount()
    stale.resolve({ items: [entry('late response')] })
    await flushPromises()
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
    expect(api.panelRequest).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })
})
