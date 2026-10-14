import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import i18n from '../i18n'
import { flushPromises } from './composable-test-utils'

const mocks = vi.hoisted(() => ({
  exportBackup: vi.fn(),
  importBackup: vi.fn(),
  download: vi.fn(),
  success: vi.fn(),
}))

vi.mock('../lib/api/accounts', () => ({
  exportAccountLoginBackup: mocks.exportBackup,
  importAccountLoginBackup: mocks.importBackup,
}))
vi.mock('../lib/api/core', () => ({ getAuthToken: () => 'token' }))
vi.mock('../lib/download', () => ({ downloadBlob: mocks.download }))
vi.mock('../composables/useToast', () => ({ useToast: () => ({ success: mocks.success }) }))

import LoginBackupModal from '../components/accounts/LoginBackupModal.vue'

async function openModal(initialMode: 'export' | 'import' = 'export') {
  const wrapper = mount(LoginBackupModal, {
    props: { isOpen: false, initialMode },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
  await wrapper.setProps({ isOpen: true })
  await nextTick()
  return wrapper
}

function field(id: string): HTMLInputElement {
  const input = document.querySelector<HTMLInputElement>(`#${id}`)
  if (!input) throw new Error(`Missing ${id}`)
  return input
}

function setValue(input: HTMLInputElement, value: string) {
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

function submit() {
  const form = document.querySelector('form')
  if (!form) throw new Error('Missing form')
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
}

describe('account login backup modal', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'zh-CN'
    mocks.exportBackup.mockReset()
    mocks.importBackup.mockReset()
    mocks.download.mockReset()
    mocks.success.mockReset()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('rejects mismatched export passwords before requesting a backup', async () => {
    const wrapper = await openModal()
    setValue(field('account-login-backup-password'), 'long backup passphrase')
    setValue(field('account-login-backup-confirmation'), 'different passphrase')
    submit()
    await flushPromises()

    expect(mocks.exportBackup).not.toHaveBeenCalled()
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('两次输入的密码不一致')
    wrapper.unmount()
  })

  it('requires both explicit permissions without operating a container', async () => {
    mocks.exportBackup.mockResolvedValue(new Blob(['encrypted']))
    const wrapper = await openModal()
    setValue(field('account-login-backup-password'), 'long backup passphrase')
    setValue(field('account-login-backup-confirmation'), 'long backup passphrase')
    submit()
    await flushPromises()
    expect(mocks.exportBackup).not.toHaveBeenCalled()
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('两项')

    for (const id of ['account-login-backup-allow-stop', 'account-login-backup-allow-restore']) {
      const checkbox = field(id)
      checkbox.checked = true
      checkbox.dispatchEvent(new Event('change', { bubbles: true }))
    }
    submit()
    await flushPromises()
    expect(mocks.exportBackup).toHaveBeenCalledWith('token', 'long backup passphrase', true, true)
    wrapper.unmount()
  })

  it('imports the chosen file and reports restored and skipped accounts', async () => {
    mocks.importBackup.mockResolvedValue({ restored: 2, skipped: 1 })
    const wrapper = await openModal('import')
    const backup = new File(['encrypted'], 'accounts.tglogin')
    const input = field('account-login-backup-file')
    Object.defineProperty(input, 'files', { configurable: true, value: [backup] })
    input.dispatchEvent(new Event('change', { bubbles: true }))
    setValue(field('account-login-backup-password'), 'long backup passphrase')
    submit()
    await flushPromises()

    expect(mocks.importBackup).toHaveBeenCalledWith('token', backup, 'long backup passphrase')
    expect(mocks.success).toHaveBeenCalledWith('已恢复 2 个账户，跳过 1 个同名账户')
    expect(wrapper.emitted('restored')).toHaveLength(1)
    expect(field('account-login-backup-password').value).toBe('')
    wrapper.unmount()
  })
})
