import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ChatAvatar from '../components/ChatAvatar.vue'
import { chatAvatarCache } from '../lib/chat-avatar-cache'

const api = vi.hoisted(() => ({ chatAvatar: vi.fn() }))
vi.mock('../lib/api/communications', () => ({ chatAvatar: api.chatAvatar }))

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = []
  readonly targets = new Set<Element>()
  private readonly callback: IntersectionObserverCallback
  constructor(callback: IntersectionObserverCallback) { this.callback = callback; MockIntersectionObserver.instances.push(this) }
  observe = (element: Element) => { this.targets.add(element) }
  unobserve = (element: Element) => { this.targets.delete(element) }
  disconnect = () => { this.targets.clear() }
  notify(element: Element, isIntersecting: boolean) {
    this.callback([{ target: element, isIntersecting } as IntersectionObserverEntry], this as unknown as IntersectionObserver)
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

describe('ChatAvatar viewport lifecycle', () => {
  let create: ReturnType<typeof vi.spyOn>
  let revoke: ReturnType<typeof vi.spyOn>
  beforeEach(() => {
    chatAvatarCache.clear()
    MockIntersectionObserver.instances.length = 0
    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver)
    api.chatAvatar.mockReset()
    create = vi.spyOn(URL, 'createObjectURL').mockImplementation(blob => `blob:chat-${'size' in blob ? blob.size : 0}`)
    revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  })
  afterEach(() => { chatAvatarCache.clear(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

  it('reuses one fetched avatar through repeated viewport entry and releases it on exit', async () => {
    api.chatAvatar.mockResolvedValue(new Blob(['saved portrait']))
    const wrapper = mount(ChatAvatar, { props: { account: 'a', chatId: '1', name: 'Alpha' } })
    const element = wrapper.element
    const observer = MockIntersectionObserver.instances.at(-1)!
    observer.notify(element, true)
    await flushPromises()
    expect(api.chatAvatar).toHaveBeenCalledTimes(1)
    expect(wrapper.find('img').exists()).toBe(true)
    observer.notify(element, false)
    await flushPromises()
    observer.notify(element, true)
    await flushPromises()
    expect(api.chatAvatar).toHaveBeenCalledTimes(1)
    expect(create).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    chatAvatarCache.clear()
    expect(revoke).toHaveBeenCalledTimes(1)
  })

  it('keeps only two avatar requests active and cancels offscreen queued work', async () => {
    const requests = new Map<string, ReturnType<typeof deferred<Blob>>>()
    let active = 0
    let maximum = 0
    api.chatAvatar.mockImplementation((_account: string, chatId: string) => {
      active += 1
      maximum = Math.max(maximum, active)
      const request = deferred<Blob>()
      requests.set(chatId, request)
      return request.promise.finally(() => { active -= 1 })
    })
    const wrappers = ['1', '2', '3', '4'].map(chatId => mount(ChatAvatar, { props: { account: 'a', chatId, name: 'A' } }))
    const observers = MockIntersectionObserver.instances.slice(-4)
    for (const [index, wrapper] of wrappers.entries()) observers[index]!.notify(wrapper.element, true)
    expect(api.chatAvatar).toHaveBeenCalledTimes(2)
    observers[2]!.notify(wrappers[2]!.element, false)
    observers[3]!.notify(wrappers[3]!.element, false)
    requests.get('1')!.resolve(new Blob(['first']))
    requests.get('2')!.resolve(new Blob(['second']))
    await flushPromises()
    expect(api.chatAvatar).toHaveBeenCalledTimes(2)
    expect(maximum).toBe(2)
    wrappers.forEach(wrapper => wrapper.unmount())
  })

  it('discards a late response after the owning avatar unmounts without allocating an ObjectURL', async () => {
    const request = deferred<Blob>()
    api.chatAvatar.mockReturnValue(request.promise)
    const wrapper = mount(ChatAvatar, { props: { account: 'a', chatId: 'late', name: 'Late' } })
    MockIntersectionObserver.instances.at(-1)!.notify(wrapper.element, true)
    expect(api.chatAvatar).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    request.resolve(new Blob(['late result']))
    await flushPromises()
    expect(create).not.toHaveBeenCalled()
    expect(chatAvatarCache.stats.bytes).toBe(0)
  })
})
