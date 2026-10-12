import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({ listTeleBoxAccounts: vi.fn(), panelRequest: vi.fn() }))
vi.mock('../lib/api/telebox', () => ({ listTeleBoxAccounts: api.listTeleBoxAccounts }))
vi.mock('../lib/api/communications', () => ({ panelRequest: api.panelRequest }))
vi.mock('../composables/usePanelAccount', () => ({ errorText: (cause: unknown) => String(cause) }))
vi.mock('../composables/useI18n', async () => {
  const { ref } = await import('vue')
  return { useI18n: () => ({ t: (key: string) => key, locale: ref('en') }) }
})

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

  it('lists only enabled accounts, including failed and stopped workers', async () => {
    api.listTeleBoxAccounts.mockResolvedValue({ accounts: [
      { account: 'disabled', status: 'running', enabled: false, authorized: true },
      { account: 'failed', status: 'failed', enabled: true, authorized: true },
      { account: 'stopped', status: 'stopped', enabled: true, authorized: true },
    ] })
    api.panelRequest.mockResolvedValue({ items: [entry('diagnostic failure')] })
    const wrapper = mount(Logs)
    await flushPromises()

    expect(wrapper.findAll('option').map(option => option.element.value)).toEqual(['failed', 'stopped'])
    expect(api.panelRequest).toHaveBeenCalledExactlyOnceWith('/telebox/failed/logs')
    expect(wrapper.text()).toContain('diagnostic failure')
    expect(wrapper.text()).not.toContain('disabled')
    wrapper.unmount()
  })

  it('does not request logs when every account is disabled', async () => {
    api.listTeleBoxAccounts.mockResolvedValue({ accounts: accounts.accounts.map(account => ({ ...account, enabled: false })) })
    const wrapper = mount(Logs)
    await flushPromises()

    expect(api.panelRequest).not.toHaveBeenCalled()
    expect(wrapper.find('select').element.disabled).toBe(true)
    expect(wrapper.find('select').element.value).toBe('')
    expect(wrapper.find('.panel-empty').text()).toBe('logs.enableTeleboxForLogs')
    expect(wrapper.text()).not.toContain('logs.noTeleboxLogs')
    await vi.advanceTimersByTimeAsync(5000)
    expect(api.panelRequest).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('clears a disabled selection before waiting for the replacement account logs', async () => {
    api.panelRequest.mockResolvedValueOnce({ items: [entry('previous alpha')] })
    const wrapper = mount(Logs)
    await flushPromises()
    expect(wrapper.text()).toContain('previous alpha')

    const replacement = deferred<{ items: ReturnType<typeof entry>[] }>()
    api.listTeleBoxAccounts.mockResolvedValue({ accounts: accounts.accounts.map(account => ({
      ...account, enabled: account.account === 'beta',
    })) })
    api.panelRequest.mockReturnValueOnce(replacement.promise)
    await vi.advanceTimersByTimeAsync(5000)
    expect(wrapper.find('select').element.value).toBe('beta')
    expect(wrapper.text()).not.toContain('previous alpha')
    expect(api.panelRequest).toHaveBeenLastCalledWith('/telebox/beta/logs')

    replacement.resolve({ items: [entry('replacement beta')] })
    await flushPromises()
    expect(wrapper.text()).toContain('replacement beta')
    wrapper.unmount()
  })

  it.each([false, true])('discards a delayed payload after disable, with enabled fallback %s', async (hasFallback) => {
    const stale = deferred<{ items: ReturnType<typeof entry>[] }>()
    api.panelRequest.mockReturnValueOnce(stale.promise)
    const wrapper = mount(Logs)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(20_000)
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
    expect(api.panelRequest).toHaveBeenCalledTimes(1)

    api.listTeleBoxAccounts.mockResolvedValue({ accounts: accounts.accounts.map(account => ({
      ...account, enabled: hasFallback && account.account === 'beta',
    })) })
    api.panelRequest.mockResolvedValueOnce({ items: [entry('current beta')] })
    stale.resolve({ items: [entry('disabled alpha payload')] })
    await flushPromises()

    expect(wrapper.text()).not.toContain('disabled alpha payload')
    expect(wrapper.find('select').element.value).toBe(hasFallback ? 'beta' : '')
    expect(api.panelRequest).toHaveBeenCalledTimes(hasFallback ? 2 : 1)
    if (hasFallback) {
      expect(api.panelRequest).toHaveBeenLastCalledWith('/telebox/beta/logs')
      expect(wrapper.text()).toContain('current beta')
    } else {
      expect(wrapper.find('select').element.disabled).toBe(true)
      expect(wrapper.find('.panel-empty').text()).toBe('logs.enableTeleboxForLogs')
    }
    expect(vi.getTimerCount()).toBe(1)
    wrapper.unmount()
  })

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
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(3)
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

  it('ignores enabled-state revalidation that finishes after unmount', async () => {
    const latest = deferred<typeof accounts>()
    api.listTeleBoxAccounts.mockReturnValueOnce(Promise.resolve(accounts)).mockReturnValueOnce(latest.promise)
    api.panelRequest.mockResolvedValueOnce({ items: [entry('unvalidated alpha')] })
    const wrapper = mount(Logs)
    await flushPromises()
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('unvalidated alpha')
    await vi.advanceTimersByTimeAsync(20_000)
    expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(2)
    wrapper.unmount()

    latest.resolve({ accounts: [] })
    await flushPromises()
    expect(api.panelRequest).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('keeps the current selection when an older revalidation resolves after an account change', async () => {
    const latest = deferred<typeof accounts>()
    api.listTeleBoxAccounts.mockReturnValueOnce(Promise.resolve(accounts)).mockReturnValueOnce(latest.promise)
    api.panelRequest.mockResolvedValueOnce({ items: [entry('unvalidated alpha')] })
    const wrapper = mount(Logs)
    await flushPromises()
    await wrapper.find('select').setValue('beta')
    api.panelRequest.mockResolvedValueOnce({ items: [entry('current beta')] })

    latest.resolve({ accounts: [] })
    await flushPromises()
    expect(wrapper.find('select').element.value).toBe('beta')
    expect(wrapper.text()).not.toContain('unvalidated alpha')
    expect(wrapper.text()).toContain('current beta')
    expect(api.panelRequest).toHaveBeenLastCalledWith('/telebox/beta/logs')
    expect(vi.getTimerCount()).toBe(1)
    wrapper.unmount()
  })

  it('does not display an unvalidated payload on metadata failure and recovers on the next poll', async () => {
    api.panelRequest.mockResolvedValueOnce({ items: [entry('validated previous logs')] })
    const wrapper = mount(Logs)
    await flushPromises()
    api.panelRequest.mockResolvedValue({ items: [entry('new logs')] })
    api.listTeleBoxAccounts.mockResolvedValueOnce(accounts).mockRejectedValueOnce(new Error('metadata offline'))
    await vi.advanceTimersByTimeAsync(5000)

    expect(wrapper.text()).toContain('validated previous logs')
    expect(wrapper.text()).not.toContain('new logs')
    expect(wrapper.find('[role="alert"]').text()).toContain('metadata offline')
    expect(vi.getTimerCount()).toBe(1)

    await vi.advanceTimersByTimeAsync(5000)
    expect(wrapper.text()).toContain('new logs')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
