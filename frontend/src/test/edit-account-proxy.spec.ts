import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'
import type { AccountUiItem } from '../lib/types'

const mocks = vi.hoisted(() => ({ updateAccount: vi.fn(), success: vi.fn() }))
vi.mock('../lib/api', () => ({ updateAccount: mocks.updateAccount }))
vi.mock('../lib/api/core', () => ({ getAuthToken: () => 'token' }))
vi.mock('../composables/useToast', () => ({ useToast: () => ({ success: mocks.success }) }))
import EditAccountModal from '../components/accounts/EditAccountModal.vue'

const account: AccountUiItem = {
  id: 'alice', name: 'alice', remark: '', status: 'active', message: '', avatarUrl: '',
  raw: { name: 'alice', session_file: '', exists: true, size: 1, proxy: 'socks5://user:secret@proxy:1080' },
}
function mountEditor() {
  return mount(EditAccountModal, {
    props: { isOpen: true, account },
    global: {
      plugins: [i18n],
      stubs: { Modal: { template: '<div><slot /><slot name="footer" /></div>' } },
    },
  })
}

beforeEach(() => { vi.clearAllMocks(); i18n.global.locale.value = 'zh-CN' })

describe('editing an account proxy', () => {
  it('hydrates a logged-in account on initial open, masks proxy credentials, and sends explicit clearing', async () => {
    mocks.updateAccount.mockResolvedValue({ success: true })
    const wrapper = mountEditor()
    const input = wrapper.get<HTMLInputElement>('#edit-account-proxy')
    expect(input.element.value).toBe(account.raw.proxy)
    expect(input.attributes('type')).toBe('password')
    await wrapper.get('button[aria-pressed]').trigger('click')
    expect(input.attributes('type')).toBe('text')
    await input.setValue('')
    await wrapper.get('button.ui-btn-primary').trigger('click')
    await flushPromises()
    expect(mocks.updateAccount).toHaveBeenCalledWith('token', 'alice', expect.objectContaining({ proxy: '' }))
    expect(wrapper.emitted('success')).toHaveLength(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('preserves a changed proxy after validation failure with no duplicate save while busy', async () => {
    let reject!: (error: Error) => void
    mocks.updateAccount.mockImplementation(() => new Promise((_resolve, fail) => { reject = fail }))
    const wrapper = mountEditor()
    const input = wrapper.get<HTMLInputElement>('#edit-account-proxy')
    await input.setValue('socks5://new:1080')
    await wrapper.get('button.ui-btn-primary').trigger('click')
    await wrapper.get('button.ui-btn-primary').trigger('click')
    expect(mocks.updateAccount).toHaveBeenCalledTimes(1)
    reject(new Error('INVALID_ACCOUNT_PROXY'))
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('代理地址无效')
    expect(input.element.value).toBe('socks5://new:1080')
    expect(wrapper.emitted('success')).toBeUndefined()
    wrapper.unmount()
  })
})
