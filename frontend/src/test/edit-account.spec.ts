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
  raw: { name: 'alice', session_file: '', exists: true, size: 1 },
}
function mountEditor() {
  return mount(EditAccountModal, {
    props: { isOpen: true, account },
    global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /><slot name="footer" /></div>' } } },
  })
}

beforeEach(() => { vi.clearAllMocks(); i18n.global.locale.value = 'zh-CN' })

describe('editing an account', () => {
  it('saves name and remark without exposing or sending a manual proxy', async () => {
    mocks.updateAccount.mockResolvedValue({ success: true })
    const wrapper = mountEditor()
    expect(wrapper.find('#edit-account-proxy').exists()).toBe(false)
    await wrapper.get('#edit-account-remark').setValue('note')
    await wrapper.get('button.ui-btn-primary').trigger('click')
    await flushPromises()
    expect(mocks.updateAccount).toHaveBeenCalledWith('token', 'alice', { new_account_name: 'alice', remark: 'note' })
    expect(wrapper.emitted('success')).toHaveLength(1)
  })

  it('prevents duplicate saves while a request is in flight', async () => {
    let reject!: (error: Error) => void
    mocks.updateAccount.mockImplementation(() => new Promise((_resolve, fail) => { reject = fail }))
    const wrapper = mountEditor()
    await wrapper.get('button.ui-btn-primary').trigger('click')
    await wrapper.get('button.ui-btn-primary').trigger('click')
    expect(mocks.updateAccount).toHaveBeenCalledTimes(1)
    reject(new Error('NETWORK_ERROR'))
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBeTruthy()
  })
})
