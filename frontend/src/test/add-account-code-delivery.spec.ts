import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../i18n'

const mocks = vi.hoisted(() => ({ startAccountLogin: vi.fn(), resendAccountLogin: vi.fn(), cancelAccountLogin: vi.fn(), info: vi.fn() }))
vi.mock('../lib/api', () => ({
  startAccountLogin: mocks.startAccountLogin,
  resendAccountLogin: mocks.resendAccountLogin,
  cancelAccountLogin: mocks.cancelAccountLogin,
  verifyAccountLogin: vi.fn(), updateAccount: vi.fn(), startQrLogin: vi.fn(),
  getQrLoginStatus: vi.fn(), submitQrPassword: vi.fn(), cancelQrLogin: vi.fn(),
}))
vi.mock('../lib/api/core', () => ({ getAuthToken: () => 'token' }))
vi.mock('../lib/api/communications', () => ({ panelRequest: vi.fn() }))
vi.mock('../composables/useToast', () => ({ useToast: () => ({ info: mocks.info, error: vi.fn(), success: vi.fn() }) }))
import AddAccountModal from '../components/accounts/AddAccountModal.vue'

beforeEach(() => {
  vi.clearAllMocks()
  mocks.cancelAccountLogin.mockResolvedValue({ canceled: true })
  i18n.global.locale.value = 'zh-CN'
})
afterEach(() => vi.useRealTimers())

describe('phone login delivery guidance', () => {
  it.each([
    ['app', '其他已登录设备'],
    ['sms', '短信'],
    ['fragment_sms', 'Fragment'],
    ['firebase_sms', '仅官方手机客户端支持'],
    ['email_code', '邮箱'],
    [null, '未说明验证码送达方式'],
  ])('shows Telegram-selected channel %s', async (deliveryType, expected) => {
    mocks.startAccountLogin.mockResolvedValue({
      account_name: 'one', phone_number: '+12345678900', phone_code_hash: 'hash',
      delivery_type: deliveryType, retry_after: 75,
    })
    const wrapper = mount(AddAccountModal, {
      props: { isOpen: true },
      global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /><slot name="footer" /></div>' } } },
    })
    await wrapper.get('#add-account-name').setValue('one')
    await wrapper.get('#add-account-phone').setValue('+12345678900')
    await wrapper.get('input[name="preferred-code-source"][value="app"]').setValue()
    await wrapper.get('button.ui-btn-secondary').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain(expected)
    expect(wrapper.text()).toContain('75s')
    expect(mocks.startAccountLogin).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    await flushPromises()
    expect(mocks.cancelAccountLogin).toHaveBeenCalledWith('token', {
      account_name: 'one', phone_number: '+12345678900', phone_code_hash: 'hash',
    })
  })

  it('uses the existing hash for Telegram fallback after its wait time', async () => {
    mocks.startAccountLogin.mockResolvedValue({
      account_name: 'one', phone_number: '+12345678900', phone_code_hash: 'hash',
      delivery_type: 'app', next_type: 'sms', retry_after: 75,
    })
    mocks.resendAccountLogin.mockResolvedValue({
      account_name: 'one', phone_number: '+12345678900', phone_code_hash: 'hash-2',
      delivery_type: 'sms', next_type: null, retry_after: 60,
    })
    const wrapper = mount(AddAccountModal, {
      props: { isOpen: true },
      global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /><slot name="footer" /></div>' } } },
    })
    await wrapper.get('#add-account-name').setValue('one')
    await wrapper.get('#add-account-phone').setValue('+12345678900')
    await wrapper.get('input[name="preferred-code-source"][value="sms"]').setValue()
    const button = wrapper.get('button.ui-btn-secondary')
    vi.useFakeTimers()
    await button.trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('短信作为下一种方式')
    expect(wrapper.get('[role="status"]').text()).toContain('未按所选方式投递')
    await vi.advanceTimersByTimeAsync(75_000)
    await button.trigger('click')
    await flushPromises()
    expect(mocks.resendAccountLogin).toHaveBeenCalledWith('token', {
      account_name: 'one', phone_number: '+12345678900', phone_code_hash: 'hash',
    })
    expect(wrapper.get('[role="status"]').text()).toContain('短信')
    wrapper.unmount()
    await flushPromises()
    expect(mocks.cancelAccountLogin).toHaveBeenCalledWith('token', {
      account_name: 'one', phone_number: '+12345678900', phone_code_hash: 'hash-2',
    })
  })

  it('requires one exclusive preference before requesting a code', async () => {
    mocks.startAccountLogin.mockResolvedValue({
      account_name: 'one', phone_number: '+12345678900', phone_code_hash: 'hash',
      delivery_type: 'app', retry_after: 60,
    })
    const wrapper = mount(AddAccountModal, {
      props: { isOpen: true },
      global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /><slot name="footer" /></div>' } } },
    })
    await wrapper.get('#add-account-name').setValue('one')
    await wrapper.get('#add-account-phone').setValue('+12345678900')
    const button = wrapper.get('button.ui-btn-secondary')
    expect(button.attributes('disabled')).toBeDefined()
    expect(mocks.startAccountLogin).not.toHaveBeenCalled()

    const sms = wrapper.get('input[name="preferred-code-source"][value="sms"]')
    const app = wrapper.get('input[name="preferred-code-source"][value="app"]')
    await sms.setValue()
    expect((sms.element as HTMLInputElement).checked).toBe(true)
    await app.setValue()
    expect((sms.element as HTMLInputElement).checked).toBe(false)
    expect((app.element as HTMLInputElement).checked).toBe(true)
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    await flushPromises()
    expect(mocks.startAccountLogin).toHaveBeenCalledTimes(1)
    expect((app.element as HTMLInputElement).disabled).toBe(true)
    wrapper.unmount()
  })

  it('reports when Telegram sends SMS despite app preference', async () => {
    mocks.startAccountLogin.mockResolvedValue({
      account_name: 'one', phone_number: '+12345678900', phone_code_hash: 'hash',
      delivery_type: 'sms', retry_after: 60,
    })
    const wrapper = mount(AddAccountModal, {
      props: { isOpen: true },
      global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /><slot name="footer" /></div>' } } },
    })
    await wrapper.get('#add-account-name').setValue('one')
    await wrapper.get('#add-account-phone').setValue('+12345678900')
    await wrapper.get('input[name="preferred-code-source"][value="app"]').setValue()
    await wrapper.get('button.ui-btn-secondary').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('请查看该手机号的短信')
    expect(wrapper.get('[role="status"]').text()).toContain('未按所选方式投递')
    wrapper.unmount()
  })

  it('clears the preference after switching away from phone login', async () => {
    const wrapper = mount(AddAccountModal, {
      props: { isOpen: true },
      global: { plugins: [i18n], stubs: { Modal: { template: '<div><slot /><slot name="footer" /></div>' } } },
    })
    await wrapper.get('input[name="preferred-code-source"][value="sms"]').setValue()
    const methods = wrapper.findAll('button.ui-segment-btn')
    await methods[1]!.trigger('click')
    await flushPromises()
    await methods[0]!.trigger('click')
    await flushPromises()
    expect((wrapper.get('input[name="preferred-code-source"][value="sms"]').element as HTMLInputElement).checked).toBe(false)
    expect((wrapper.get('input[name="preferred-code-source"][value="app"]').element as HTMLInputElement).checked).toBe(false)
    wrapper.unmount()
  })
})
