import { AVATAR_FETCH_CONCURRENCY } from './async-pool'

type Waiter = {
  resolve: (url: string | null) => void
  released: boolean
  entry?: CacheEntry
}

type CacheEntry = { key: string; url: string; size: number; refs: number; touched: number }
type Job = { key: string; load: () => Promise<Blob>; waiters: Set<Waiter>; state: 'queued' | 'active' }

/** Bounded, shared chat-avatar cache and request scheduler for the conversation list. */
export class ChatAvatarCache {
  private readonly entries = new Map<string, CacheEntry>()
  private readonly jobs = new Map<string, Job>()
  private readonly queue: Job[] = []
  private active = 0
  private bytes = 0
  private clock = 0

  private readonly maxBytes: number
  private readonly concurrency: number
  private readonly maxQueued: number

  constructor(maxBytes = 2 * 1024 * 1024, concurrency = AVATAR_FETCH_CONCURRENCY, maxQueued = 12) {
    this.maxBytes = maxBytes
    this.concurrency = concurrency
    this.maxQueued = maxQueued
  }

  acquire(key: string, load: () => Promise<Blob>): { promise: Promise<string | null>; release: () => void } {
    const cached = this.entries.get(key)
    if (cached) {
      cached.refs += 1
      cached.touched = ++this.clock
      let released = false
      return { promise: Promise.resolve(cached.url), release: () => {
        if (released) return
        released = true
        cached.refs = Math.max(0, cached.refs - 1)
      } }
    }

    let job = this.jobs.get(key)
    if (!job) {
      if (this.queue.length >= this.maxQueued) return { promise: Promise.resolve(null), release: () => {} }
      job = { key, load, waiters: new Set(), state: 'queued' }
      this.jobs.set(key, job)
      this.queue.push(job)
    }
    const waiter: Waiter = { resolve: () => {}, released: false }
    const promise = new Promise<string | null>(resolve => { waiter.resolve = resolve })
    job.waiters.add(waiter)
    const release = () => {
      if (waiter.released) return
      waiter.released = true
      if (waiter.entry) {
        waiter.entry.refs = Math.max(0, waiter.entry.refs - 1)
        waiter.entry = undefined
      } else {
        job!.waiters.delete(waiter)
        waiter.resolve(null)
        if (job!.state === 'queued' && job!.waiters.size === 0) {
          this.jobs.delete(job!.key)
          const index = this.queue.indexOf(job!)
          if (index >= 0) this.queue.splice(index, 1)
        }
      }
    }
    this.pump()
    return { promise, release }
  }

  clear(): void {
    for (const entry of this.entries.values()) URL.revokeObjectURL(entry.url)
    this.entries.clear()
    this.bytes = 0
    for (const job of [...this.queue]) {
      this.jobs.delete(job.key)
      for (const waiter of job.waiters) {
        waiter.released = true
        waiter.resolve(null)
      }
    }
    this.queue.length = 0
    for (const job of this.jobs.values()) {
      for (const waiter of job.waiters) {
        waiter.released = true
        waiter.resolve(null)
      }
      job.waiters.clear()
    }
    // Keep active downloads counted until they finish, but detach their keys so
    // new page owners cannot subscribe to a request from the cleared page.
    this.jobs.clear()
  }

  get stats() { return { bytes: this.bytes, cached: this.entries.size, active: this.active, queued: this.queue.length } }

  private pump(): void {
    while (this.active < Math.max(1, this.concurrency) && this.queue.length) {
      const job = this.queue.shift()!
      if (this.jobs.get(job.key) !== job || job.waiters.size === 0) continue
      job.state = 'active'
      this.active += 1
      let download: Promise<Blob>
      try { download = job.load() } catch (error) { download = Promise.reject(error) }
      void download.then(blob => this.finish(job, blob), () => this.finish(job, null)).finally(() => {
        this.active -= 1
        this.pump()
      })
    }
  }

  private finish(job: Job, blob: Blob | null): void {
    // Remove the completed job before resolving consumers so an immediate retry
    // cannot join a finished job while its scheduler slot is still being released.
    if (this.jobs.get(job.key) === job) this.jobs.delete(job.key)
    const waiters = [...job.waiters].filter(waiter => !waiter.released)
    let entry: CacheEntry | undefined
    if (blob && waiters.length && this.makeRoom(blob.size)) {
      try {
        const url = URL.createObjectURL(blob)
        entry = { key: job.key, url, size: blob.size, refs: waiters.length, touched: ++this.clock }
        this.entries.set(job.key, entry)
        this.bytes += blob.size
      } catch {
        entry = undefined
      }
    }
    for (const waiter of job.waiters) {
      if (entry && !waiter.released) {
        waiter.entry = entry
        waiter.resolve(entry.url)
      } else waiter.resolve(null)
    }
    job.waiters.clear()
  }

  private makeRoom(size: number): boolean {
    if (size <= 0 || size > this.maxBytes || size > 128 * 1024) return false
    while (this.bytes + size > this.maxBytes) {
      const victim = [...this.entries.values()]
        .filter(entry => entry.refs === 0)
        .sort((a, b) => a.touched - b.touched)[0]
      if (!victim) return false
      this.entries.delete(victim.key)
      this.bytes -= victim.size
      URL.revokeObjectURL(victim.url)
    }
    return true
  }
}

export const chatAvatarCache = new ChatAvatarCache()
