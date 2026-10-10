import { afterEach, describe, expect, it, vi } from 'vitest'
import { ChatAvatarCache } from '../lib/chat-avatar-cache'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

describe('bounded chat avatar cache', () => {
  afterEach(() => vi.restoreAllMocks())

  it('deduplicates requests and limits active downloads to two', async () => {
    const cache = new ChatAvatarCache(1024, 2, 4)
    const pending = new Map<string, ReturnType<typeof deferred<Blob>>>()
    let active = 0
    let maximum = 0
    const load = (key: string) => {
      active += 1
      maximum = Math.max(maximum, active)
      const request = deferred<Blob>()
      pending.set(key, request)
      return request.promise.finally(() => { active -= 1 })
    }
    const first = cache.acquire('a', () => load('a'))
    const duplicate = cache.acquire('a', () => load('a'))
    const second = cache.acquire('b', () => load('b'))
    const third = cache.acquire('c', () => load('c'))
    expect(pending.size).toBe(2)
    expect(cache.stats).toMatchObject({ active: 2, queued: 1 })
    pending.get('a')!.resolve(new Blob(['a']))
    const firstUrl = await first.promise
    expect(await duplicate.promise).toBe(firstUrl)
    await Promise.resolve()
    expect(pending.has('c')).toBe(true)
    pending.get('b')!.resolve(new Blob(['b']))
    pending.get('c')!.resolve(new Blob(['c']))
    await Promise.all([second.promise, third.promise])
    expect(maximum).toBe(2)
    expect(cache.stats.bytes).toBe(3)
    first.release(); duplicate.release(); second.release(); third.release(); cache.clear()
  })

  it('evicts least-recently-used released blobs while keeping bytes within budget', async () => {
    const cache = new ChatAvatarCache(6, 2, 4)
    const create = vi.spyOn(URL, 'createObjectURL').mockImplementation(blob => `blob:${'size' in blob ? blob.size : 0}`)
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const a = cache.acquire('a', async () => new Blob(['aaaa']))
    const aUrl = await a.promise
    a.release()
    const b = cache.acquire('b', async () => new Blob(['bbbb']))
    const bUrl = await b.promise
    b.release()
    expect(cache.stats.bytes).toBe(4)
    const c = cache.acquire('c', async () => new Blob(['cccccc']))
    const cUrl = await c.promise
    expect(cUrl).toBe('blob:6')
    expect(cache.stats.bytes).toBeLessThanOrEqual(6)
    expect(revoke).toHaveBeenCalledWith(aUrl)
    expect(revoke).toHaveBeenCalledWith(bUrl)
    c.release(); cache.clear()
    expect(create).toHaveBeenCalledTimes(3)
  })

  it('does not create URLs for oversized blobs or results with no remaining consumers', async () => {
    const cache = new ChatAvatarCache(4, 2, 2)
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:unused')
    const huge = cache.acquire('huge', async () => new Blob(['12345']))
    expect(await huge.promise).toBeNull()
    const late = deferred<Blob>()
    const request = cache.acquire('released', () => late.promise)
    request.release()
    late.resolve(new Blob(['data']))
    expect(await request.promise).toBeNull()
    expect(create).not.toHaveBeenCalled()
    expect(cache.stats.bytes).toBe(0)
    cache.clear()
  })

  it('caps queued work and removes released jobs before dispatch', async () => {
    const cache = new ChatAvatarCache(1024, 2, 2)
    const pending = deferred<Blob>()
    const load = vi.fn(() => pending.promise)
    const leases = ['a', 'b', 'c', 'd', 'e'].map(key => cache.acquire(key, load))
    expect(load).toHaveBeenCalledTimes(2)
    expect(cache.stats).toMatchObject({ active: 2, queued: 2 })
    expect(await leases[4]!.promise).toBeNull()
    leases[2]!.release(); leases[3]!.release()
    expect(cache.stats.queued).toBe(0)
    pending.resolve(new Blob(['one']))
    await Promise.all(leases.map(lease => lease.promise))
    expect(load).toHaveBeenCalledTimes(2)
    leases.forEach(lease => lease.release())
    cache.clear()
  })

  it('keeps referenced avatars and rejects additions that would exceed the shared budget', async () => {
    const cache = new ChatAvatarCache(6)
    const first = cache.acquire('pinned', async () => new Blob(['1234']))
    expect(await first.promise).toBeTruthy()
    const second = cache.acquire('overflow', async () => new Blob(['1234']))
    expect(await second.promise).toBeNull()
    expect(cache.stats.bytes).toBe(4)
    first.release(); second.release(); cache.clear()
    expect(cache.stats.bytes).toBe(0)
  })

  it('allows an immediate retry after a failed download settles', async () => {
    const cache = new ChatAvatarCache(1024, 1)
    const first = cache.acquire('retry', async () => { throw new Error('temporary failure') })
    expect(await first.promise).toBeNull()
    const load = vi.fn(async () => new Blob(['retry portrait']))
    const retry = cache.acquire('retry', load)
    const result = vi.fn()
    void retry.promise.then(result)
    for (let turn = 0; turn < 6; turn += 1) await Promise.resolve()
    expect(load).toHaveBeenCalledTimes(1)
    expect(result).toHaveBeenCalledWith(expect.any(String))
    first.release(); retry.release(); cache.clear()
  })

  it('settles synchronous loader failures and continues the request queue', async () => {
    const cache = new ChatAvatarCache(1024, 1)
    const first = cache.acquire('failure', () => { throw new Error('synchronous failure') })
    const second = cache.acquire('next', async () => new Blob(['next portrait']))
    expect(await first.promise).toBeNull()
    expect(await second.promise).toEqual(expect.any(String))
    first.release(); second.release(); cache.clear()
  })

  it('rejects individual avatar blobs larger than 128 KiB', async () => {
    const cache = new ChatAvatarCache()
    const create = vi.spyOn(URL, 'createObjectURL')
    const avatar = cache.acquire('oversize', async () => new Blob([new Uint8Array(128 * 1024 + 1)]))
    expect(await avatar.promise).toBeNull()
    expect(create).not.toHaveBeenCalled()
    expect(cache.stats.bytes).toBe(0)
    avatar.release(); cache.clear()
  })

  it('clears live and queued leases without allocating URLs from late results', async () => {
    const cache = new ChatAvatarCache()
    const pending = deferred<Blob>()
    const load = vi.fn(() => pending.promise)
    const create = vi.spyOn(URL, 'createObjectURL')
    const leases = ['a', 'b', 'c'].map(key => cache.acquire(key, load))
    cache.clear()
    expect(await Promise.all(leases.map(lease => lease.promise))).toEqual([null, null, null])
    expect(cache.stats.queued).toBe(0)
    pending.resolve(new Blob(['late portrait']))
    for (let turn = 0; turn < 6; turn += 1) await Promise.resolve()
    expect(create).not.toHaveBeenCalled()
    expect(cache.stats).toEqual({ bytes: 0, cached: 0, active: 0, queued: 0 })
    expect(load).toHaveBeenCalledTimes(2)
    leases.forEach(lease => lease.release())
  })

  it('loads a fresh avatar when a new page acquires the same key after clear', async () => {
    const cache = new ChatAvatarCache(1024, 1)
    const oldDownload = deferred<Blob>()
    const first = cache.acquire('account:chat', () => oldDownload.promise)
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fresh')
    cache.clear()
    const freshBlob = new Blob(['fresh portrait'])
    const freshLoad = vi.fn(async () => freshBlob)
    const next = cache.acquire('account:chat', freshLoad)
    expect(await first.promise).toBeNull()
    expect(cache.stats).toMatchObject({ active: 1, queued: 1 })
    expect(freshLoad).not.toHaveBeenCalled()
    oldDownload.resolve(new Blob(['stale portrait']))
    expect(await next.promise).toBe('blob:fresh')
    expect(freshLoad).toHaveBeenCalledTimes(1)
    expect(create).toHaveBeenCalledExactlyOnceWith(freshBlob)
    first.release(); next.release(); cache.clear()
  })
})
