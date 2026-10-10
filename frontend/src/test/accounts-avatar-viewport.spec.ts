import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { flushPromises } from './composable-test-utils'

const mocks = vi.hoisted(() => ({
  refreshAccounts: vi.fn(),
  fetchAccountAvatar: vi.fn(),
  listTeleBoxAccounts: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../composables/useI18n', () => ({ useI18n: () => ({ t: (key: string) => key, locale: ref('zh') }) }))
vi.mock('../composables/useToast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }))
vi.mock('../composables/useConfirm', () => ({ useConfirm: () => ({ confirm: vi.fn() }) }))
vi.mock('../stores/accounts', () => ({ useAccountsStore: () => ({ refreshAccounts: mocks.refreshAccounts }) }))
vi.mock('../lib/api/core', () => ({ getAuthToken: () => 'token' }))
vi.mock('../lib/api', () => ({ fetchAccountAvatar: mocks.fetchAccountAvatar, deleteAccount: vi.fn() }))
vi.mock('../lib/api/telebox', () => ({
  listTeleBoxAccounts: mocks.listTeleBoxAccounts,
  startTeleBox: vi.fn(),
  stopTeleBox: vi.fn(),
  logoutTeleBox: vi.fn(),
  submitTeleBoxPassword: vi.fn(),
}))
vi.mock('../composables/useAccountBatchCheck', () => ({
  useAccountBatchCheck: () => ({
    checkingAccount: ref(''),
    batchChecking: ref(false),
    batchJob: ref(null),
    batchProgressPct: ref(0),
    lastFailedAccountNames: ref([]),
    handleCheck: vi.fn(),
    handleBatchCheck: vi.fn(),
    handleCancelBatchCheck: vi.fn(),
    handleRecheckFailed: vi.fn(),
    resumeActiveBatchJob: vi.fn(),
  }),
}))

import Accounts from '../views/Accounts.vue'

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = []
  private readonly callback: IntersectionObserverCallback
  readonly nodes = new Set<Element>()

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    MockIntersectionObserver.instances.push(this)
  }

  observe = (element: Element) => { this.nodes.add(element) }
  unobserve = (element: Element) => { this.nodes.delete(element) }
  disconnect = () => { this.nodes.clear() }

  enter(names: string[]) {
    const entries = [...this.nodes]
      .filter(element => names.includes((element as HTMLElement).dataset.accountAvatarName || ''))
      .map(target => ({ target, isIntersecting: true }) as IntersectionObserverEntry)
    this.callback(entries, this as unknown as IntersectionObserver)
  }
}

function mountAccounts() {
  return mount(Accounts, {
    attachTo: document.body,
    global: {
      stubs: {
        AddAccountModal: true,
        EditAccountModal: true,
        DeviceManagerModal: true,
        OfficialMessagesModal: true,
      },
    },
  })
}

describe('account avatar viewport cache loading', () => {
  let originalCreateObjectURL: PropertyDescriptor | undefined
  let originalRevokeObjectURL: PropertyDescriptor | undefined

  beforeEach(() => {
    MockIntersectionObserver.instances.length = 0
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
    originalCreateObjectURL = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
    originalRevokeObjectURL = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => `blob:avatar-${Math.random()}`),
    })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    mocks.refreshAccounts.mockReset().mockResolvedValue(
      Array.from({ length: 20 }, (_, index) => ({
        name: `acc-${index}`,
        remark: '',
        status: 'connected',
        needs_relogin: false,
      })),
    )
    mocks.listTeleBoxAccounts.mockReset().mockResolvedValue({ accounts: [] })
    mocks.fetchAccountAvatar.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    if (originalCreateObjectURL) Object.defineProperty(URL, 'createObjectURL', originalCreateObjectURL)
    else delete (URL as { createObjectURL?: typeof URL.createObjectURL }).createObjectURL
    if (originalRevokeObjectURL) Object.defineProperty(URL, 'revokeObjectURL', originalRevokeObjectURL)
    else delete (URL as { revokeObjectURL?: typeof URL.revokeObjectURL }).revokeObjectURL
  })

  it('shows saved avatars only for visible cards, with at most two simultaneous requests', async () => {
    const pending = new Map<string, (blob: Blob) => void>()
    mocks.fetchAccountAvatar.mockImplementation((_token: string, name: string) =>
      new Promise<Blob>(resolve => { pending.set(name, resolve) }),
    )
    const wrapper = mountAccounts()
    await flushPromises()
    await nextTick()

    expect(mocks.fetchAccountAvatar).not.toHaveBeenCalled()
    const observer = MockIntersectionObserver.instances.at(-1)!
    expect(observer.nodes.size).toBe(20)
    observer.enter(['acc-0', 'acc-1', 'acc-2', 'acc-3', 'acc-4'])
    expect(mocks.fetchAccountAvatar).toHaveBeenCalledTimes(2)

    pending.get('acc-0')!(new Blob(['saved avatar'], { type: 'image/jpeg' }))
    await flushPromises()
    await nextTick()
    expect(mocks.fetchAccountAvatar).toHaveBeenCalledTimes(3)
    expect(wrapper.find('[data-account-avatar-name="acc-0"] img').exists()).toBe(true)

    wrapper.unmount()
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1)
    pending.get('acc-1')!(new Blob(['late avatar'], { type: 'image/jpeg' }))
    await flushPromises()
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('drops old observer entries and hidden in-flight results after filtering', async () => {
    const pending = new Map<string, (blob: Blob) => void>()
    mocks.fetchAccountAvatar.mockImplementation((_token: string, name: string) =>
      new Promise<Blob>(resolve => { pending.set(name, resolve) }),
    )
    const wrapper = mountAccounts()
    await flushPromises()
    await nextTick()
    const originalObserver = MockIntersectionObserver.instances.at(-1)!
    originalObserver.enter(['acc-0'])

    await wrapper.find('input[type="search"]').setValue('acc-19')
    await nextTick()
    originalObserver.enter(['acc-1'])
    expect(mocks.fetchAccountAvatar).toHaveBeenCalledTimes(1)
    const filteredObserver = MockIntersectionObserver.instances.at(-1)!
    expect(filteredObserver.nodes.size).toBe(1)
    filteredObserver.enter(['acc-19'])
    expect(mocks.fetchAccountAvatar).toHaveBeenCalledTimes(2)

    pending.get('acc-0')!(new Blob(['hidden'], { type: 'image/jpeg' }))
    pending.get('acc-19')!(new Blob(['visible'], { type: 'image/jpeg' }))
    await flushPromises()
    await nextTick()
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-account-avatar-name="acc-19"] img').exists()).toBe(true)
    wrapper.unmount()
  })

  it('does not stack TeleBox status polls while a prior request is unresolved', async () => {
    let resolveStatus!: (value: { accounts: [] }) => void
    mocks.listTeleBoxAccounts.mockImplementationOnce(() =>
      new Promise<{ accounts: [] }>(resolve => { resolveStatus = resolve }),
    )
    vi.useFakeTimers()
    try {
      const wrapper = mountAccounts()
      await flushPromises()
      expect(mocks.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(30000)
      expect(mocks.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
      resolveStatus({ accounts: [] })
      await flushPromises()
      await vi.advanceTimersByTimeAsync(10000)
      expect(mocks.listTeleBoxAccounts).toHaveBeenCalledTimes(2)
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })
})
