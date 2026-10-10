/** Keep one write in flight and retain only the newest value waiting behind it. */
export function createCoalescedSave<T>(write: (value: T) => Promise<unknown>, onError: (error: unknown) => void) {
  let pending: { value: T } | undefined
  let running: Promise<void> | undefined
  function flush(): Promise<void> {
    if (running) return running
    running = Promise.resolve().then(async () => {
      while (pending) {
        const value = pending.value
        pending = undefined
        try { await write(value) } catch (error) { onError(error) }
      }
    }).finally(() => {
      running = undefined
      if (pending) return flush()
    })
    return running
  }
  return {
    enqueue(value: T) { pending = { value }; return flush() },
    discard() { pending = undefined },
    whenIdle() { return running ?? Promise.resolve() },
  }
}
