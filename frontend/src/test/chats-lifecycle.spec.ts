import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import i18n from '../i18n'
import { useConfirm } from '../composables/useConfirm'

const api = vi.hoisted(() => ({
  getGlobalSettings: vi.fn(), saveGlobalSettings: vi.fn(), listAccountOfficialMessages: vi.fn(),
  listDialogs: vi.fn(), listMessages: vi.fn(), sendMessage: vi.fn(), uploadMedia: vi.fn(),
  downloadMedia: vi.fn(), editMessage: vi.fn(), deleteMessage: vi.fn(), dialogAction: vi.fn(),
}))
const state = { account: ref('alpha'), error: ref(''), store: { accounts: [{ name: 'alpha' }] } }
vi.mock('../composables/usePanelAccount', () => ({ usePanelAccount: () => state, errorText: (error: unknown) => String(error) }))
vi.mock('../lib/api/communications', () => api)
vi.mock('../lib/api/settings', () => api)
vi.mock('../lib/api/accounts', () => api)
import Chats from '../views/Chats.vue'

function mountChats() {
  return mount(Chats, { global: { plugins: [i18n], stubs: { ChatAvatar: true } } })
}

describe('chat page request ownership', () => {
  beforeEach(() => {
    useConfirm().cancel()
    api.deleteMessage.mockReset().mockResolvedValue({})
    api.listMessages.mockReset().mockResolvedValue({ items: [], has_more: false })
    state.account.value = 'alpha'
    state.error.value = ''
    api.getGlobalSettings.mockReset().mockResolvedValue({ chat_center_enabled: true })
    api.listDialogs.mockReset().mockResolvedValue({ items: [], has_more: false })
    api.listAccountOfficialMessages.mockReset().mockResolvedValue({ messages: [] })
    api.dialogAction.mockReset().mockResolvedValue({})
    api.sendMessage.mockReset().mockResolvedValue({})
  })

  it('does not start chat or official-message requests after settings finish on an unmounted page', async () => {
    let finish!: (settings: { chat_center_enabled: boolean }) => void
    api.getGlobalSettings.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mountChats()
    wrapper.unmount()
    finish({ chat_center_enabled: true })
    await flushPromises()
    expect(api.listDialogs).not.toHaveBeenCalled()
    expect(api.listAccountOfficialMessages).not.toHaveBeenCalled()
  })

  it('ignores a stale dialog response after the selected account becomes empty', async () => {
    let finish!: (page: unknown) => void
    api.listDialogs.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mountChats()
    await flushPromises()
    state.account.value = ''
    await flushPromises()
    finish({ items: [{ id: '1', title: 'Stale account dialog', type: 'group', unread_count: 0 }], has_more: false })
    await flushPromises()
    expect(wrapper.findAll('.chat-dialog')).toHaveLength(0)
    wrapper.unmount()
  })

  it('renders the empty conversation state with a translated English label', async () => {
    const previous = i18n.global.locale.value
    i18n.global.locale.value = 'en-US'
    const wrapper = mountChats()
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('Choose a conversation to start chatting')
      expect(wrapper.text()).not.toMatch(/\p{Script=Han}/u)
    } finally { wrapper.unmount(); i18n.global.locale.value = previous }
  })

  it.each(['conversation', 'account', 'unmount'])('cancels pending deletion after the owning %s changes', async (change) => {
    api.listDialogs.mockResolvedValue({ items: [
      { id: '1', title: 'First', type: 'group', unread_count: 0, archived: false },
      { id: '2', title: 'Second', type: 'group', unread_count: 0, archived: false },
    ], has_more: false })
    api.listMessages.mockResolvedValue({ items: [
      { id: 7, chat_id: '1', text: 'Original message', date: '2026-10-10T00:00:00Z', outgoing: true, sender_name: 'Me', has_media: false },
    ], has_more: false })
    const wrapper = mountChats()
    await flushPromises()
    await wrapper.findAll('.chat-dialog')[0]!.trigger('click')
    await flushPromises()
    const deleteLabel = String(i18n.global.t('chats.delete'))
    await wrapper.find(`button[aria-label="${deleteLabel}"]`).trigger('click')
    if (change === 'conversation') await wrapper.findAll('.chat-dialog')[1]!.trigger('click')
    else if (change === 'account') state.account.value = ''
    else wrapper.unmount()
    await flushPromises()
    useConfirm().accept()
    await flushPromises()
    expect(api.deleteMessage).not.toHaveBeenCalled()
    expect(state.error.value).toBe('')
    if (change !== 'unmount') wrapper.unmount()
  })

  it.each(['conversation', 'account', 'unmount'])('does not change a new selection after the previous %s finishes archiving', async change => {
    api.listDialogs.mockResolvedValue({ items: [
      { id: '1', title: 'First', type: 'group', unread_count: 0, archived: false },
      { id: '2', title: 'Second', type: 'group', unread_count: 0, archived: false },
    ], has_more: false })
    let finish!: (result: unknown) => void
    api.dialogAction.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mountChats()
    await flushPromises()
    await wrapper.findAll('.chat-dialog')[0]!.trigger('click')
    await flushPromises()
    await wrapper.find(`button[aria-label="${i18n.global.t('chats.archive')}"]`).trigger('click')
    expect(api.dialogAction).toHaveBeenCalledWith('alpha', '1', 'archive')
    if (change === 'conversation') await wrapper.findAll('.chat-dialog')[1]!.trigger('click')
    else if (change === 'account') state.account.value = ''
    else wrapper.unmount()
    await flushPromises()
    api.listDialogs.mockClear()
    finish({})
    await flushPromises()
    if (change === 'conversation') expect(wrapper.find('.chat-heading h2').text()).toBe('Second')
    else expect(api.listDialogs).not.toHaveBeenCalled()
    expect(state.error.value).toBe('')
    if (change !== 'unmount') wrapper.unmount()
  })

  it.each(['conversation', 'account', 'unmount'])('ignores a send failure after its owning %s changes', async change => {
    api.listDialogs.mockResolvedValue({ items: [
      { id: '1', title: 'First', type: 'group', unread_count: 0, archived: false },
      { id: '2', title: 'Second', type: 'group', unread_count: 0, archived: false },
    ], has_more: false })
    let fail!: (reason: Error) => void
    api.sendMessage.mockImplementationOnce(() => new Promise((_resolve, reject) => { fail = reject }))
    const wrapper = mountChats()
    await flushPromises()
    await wrapper.findAll('.chat-dialog')[0]!.trigger('click')
    await flushPromises()
    await wrapper.find('textarea').setValue('Original message')
    await wrapper.find('form').trigger('submit')
    expect(api.sendMessage).toHaveBeenCalledWith('alpha', '1', 'Original message', undefined)
    if (change === 'conversation') await wrapper.findAll('.chat-dialog')[1]!.trigger('click')
    else if (change === 'account') state.account.value = ''
    else wrapper.unmount()
    await flushPromises()
    fail(new Error('old send failed'))
    await flushPromises()
    expect(state.error.value).toBe('')
    if (change !== 'unmount') wrapper.unmount()
  })

  it('does not refresh accounts after a send completes on an unmounted page', async () => {
    api.listDialogs.mockResolvedValue({ items: [
      { id: '1', title: 'First', type: 'group', unread_count: 0, archived: false },
    ], has_more: false })
    let finish!: (result: unknown) => void
    api.sendMessage.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mountChats()
    await flushPromises()
    await wrapper.find('.chat-dialog').trigger('click')
    await flushPromises()
    await wrapper.find('textarea').setValue('Original message')
    await wrapper.find('form').trigger('submit')
    wrapper.unmount()
    api.listMessages.mockClear()
    api.listDialogs.mockClear()
    finish({})
    await flushPromises()
    expect(api.listMessages).not.toHaveBeenCalled()
    expect(api.listDialogs).not.toHaveBeenCalled()
  })
})
