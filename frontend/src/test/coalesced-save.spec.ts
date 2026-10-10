import { describe, expect, it, vi } from 'vitest'
import { createCoalescedSave } from '../lib/coalesced-save'
import { flushPromises } from './composable-test-utils'

describe('serialized appearance saves', () => {
  it('keeps one request in flight and saves the latest pending position', async () => {
    let finish!: () => void
    const write = vi.fn().mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve })).mockResolvedValue(undefined)
    const save = createCoalescedSave(write, vi.fn())
    const completion = save.enqueue({ x: 10, y: 20 })
    await flushPromises()
    void save.enqueue({ x: 30, y: 40 })
    void save.enqueue({ x: 80, y: 90 })
    expect(write).toHaveBeenCalledTimes(1)
    finish()
    await completion
    expect(write.mock.calls).toEqual([[{ x: 10, y: 20 }], [{ x: 80, y: 90 }]])
  })

  it('lets reset discard pending positions after the current write finishes', async () => {
    let finish!: () => void
    const write = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
    const save = createCoalescedSave(write, vi.fn())
    void save.enqueue(10)
    await flushPromises()
    void save.enqueue(90)
    save.discard()
    finish()
    await save.whenIdle()
    expect(write).toHaveBeenCalledTimes(1)
  })

  it('continues with the latest value when an earlier request fails', async () => {
    const onError = vi.fn()
    const write = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
    const save = createCoalescedSave(write, onError)
    await save.enqueue('first')
    await save.enqueue('latest')
    expect(onError).toHaveBeenCalledTimes(1)
    expect(write.mock.calls).toEqual([['first'], ['latest']])
  })
})
