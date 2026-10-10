import { describe, it, expect, beforeEach } from 'vitest'
import i18n from '../i18n'
import { useConfirm } from '../composables/useConfirm'

describe('useConfirm', () => {
  beforeEach(() => {
    const { state, cancel } = useConfirm()
    if (state.value.open) cancel()
  })

  it('opens dialog and resolves true on accept', async () => {
    const { state, confirm, accept } = useConfirm()
    const p = confirm({ title: 'T', message: 'M', danger: true })
    expect(state.value.open).toBe(true)
    expect(state.value.title).toBe('T')
    expect(state.value.danger).toBe(true)
    accept()
    await expect(p).resolves.toBe(true)
    expect(state.value.open).toBe(false)
  })

  it('resolves false on cancel', async () => {
    const { confirm, cancel } = useConfirm()
    const p = confirm({ title: 'T', message: 'M' })
    cancel()
    await expect(p).resolves.toBe(false)
  })

  it('cancels previous pending when a new confirm starts', async () => {
    const { confirm, accept } = useConfirm()
    const first = confirm({ title: 'A', message: '1' })
    const second = confirm({ title: 'B', message: '2' })
    await expect(first).resolves.toBe(false)
    accept()
    await expect(second).resolves.toBe(true)
  })

  it('cancels a pending localized decision when the UI language changes', async () => {
    const previous = i18n.global.locale.value
    const { confirm, state } = useConfirm()
    const pending = confirm({ title: '确认删除', message: '是否继续？' })
    i18n.global.locale.value = previous === 'zh-CN' ? 'en-US' : 'zh-CN'
    await expect(pending).resolves.toBe(false)
    expect(state.value.open).toBe(false)
    i18n.global.locale.value = previous
  })
})
