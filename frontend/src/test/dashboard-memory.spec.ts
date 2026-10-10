import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import i18n from '../i18n'
import { useAccountsStore } from '../stores/accounts'
import { flushPromises } from './composable-test-utils'

const api = vi.hoisted(() => ({
  getHeroImage: vi.fn(),
  getHeroSettings: vi.fn(),
  listTeleBoxAccounts: vi.fn(),
  getMemoryStats: vi.fn(),
  listAccounts: vi.fn(),
}))

vi.mock('../lib/api/appearance', () => ({
  getHeroImage: api.getHeroImage,
  getHeroSettings: api.getHeroSettings,
}))
vi.mock('../lib/api/telebox', () => ({ listTeleBoxAccounts: api.listTeleBoxAccounts }))
vi.mock('../lib/api/ops', () => ({ getMemoryStats: api.getMemoryStats }))
vi.mock('../lib/api/core', () => ({ getAuthToken: () => 'test-token' }))
vi.mock('../lib/api', () => ({ listAccounts: api.listAccounts }))

import Dashboard from '../views/Dashboard.vue'

function mountDashboard() {
  const pinia = createPinia()
  const store = useAccountsStore(pinia)
  const wrapper = mount(Dashboard, {
    global: {
      plugins: [i18n, pinia],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
  return { wrapper, store }
}

describe('dashboard data and cover lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getHeroImage.mockRejectedValue(new Error('no cover'))
    api.getHeroSettings.mockRejectedValue(new Error('no cover'))
    api.listTeleBoxAccounts.mockResolvedValue({
      accounts: [
        { account: 'work', status: 'running', enabled: true, authorized: true },
        { account: 'idle', status: 'stopped', enabled: false, authorized: true },
      ],
    })
    api.getMemoryStats.mockResolvedValue({
      available: true,
      stats: { current_rss_mb: 123.4 },
    })
    api.listAccounts.mockResolvedValue({
      total: 2,
      accounts: [
        { name: 'work', session_file: '', exists: true, size: 1, status: 'connected', needs_relogin: false },
        { name: 'expired', session_file: '', exists: true, size: 1, status: 'invalid', needs_relogin: true },
      ],
    })
  })

  it('restores four metric cards and the attention section', async () => {
    const previousLocale = i18n.global.locale.value
    i18n.global.locale.value = 'en-US'
    const { wrapper } = mountDashboard()
    try {
      await flushPromises()
      expect(wrapper.find('.dashboard-hero-copy').exists()).toBe(false)
      expect(wrapper.find('.dashboard-hero-actions').exists()).toBe(false)
      expect(wrapper.findAll('.dashboard-metric')).toHaveLength(4)
      expect(wrapper.find('.dashboard-metric--accounts').text()).toContain('2')
      expect(wrapper.find('.dashboard-metric--telebox').text()).toContain('1')
      expect(wrapper.find('.dashboard-metric--tasks').text()).toContain('1')
      expect(wrapper.find('.dashboard-metric--memory').text()).toContain('123.4 MB')
      expect(wrapper.find('.dashboard-activity').text()).toContain('Accounts needing attention')
      expect(wrapper.find('.dashboard-activity').text()).toContain('expired')
      expect(wrapper.find('.dashboard-activity').text()).toContain('Sign in again')
      expect(api.listTeleBoxAccounts).toHaveBeenCalledTimes(1)
      expect(api.listAccounts).toHaveBeenCalledTimes(1)
    } finally {
      wrapper.unmount()
      i18n.global.locale.value = previousLocale
    }
  })

  it('shows a readable load error when the dashboard data requests fail', async () => {
    api.listTeleBoxAccounts.mockRejectedValue(new Error('telebox unavailable'))
    api.listAccounts.mockRejectedValue(new Error('accounts unavailable'))
    const { wrapper } = mountDashboard()
    try {
      await flushPromises()
      expect(wrapper.find('[role="alert"]').exists()).toBe(true)
      expect(wrapper.find('[role="alert"]').text()).toContain('telebox unavailable')
    } finally {
      wrapper.unmount()
    }
  })

  it('preserves locally adjusted framing while an older cover read completes', async () => {
    let finish!: (blob: Blob) => void
    api.getHeroImage.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    api.getHeroSettings.mockResolvedValue({ present: true, position_x: 50, position_y: 50 })
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:dashboard-cover')
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const { wrapper } = mountDashboard()
    try {
      window.dispatchEvent(new CustomEvent('tg-manage:hero-position-changed', { detail: { x: 15, y: 75 } }))
      finish(new Blob(['cover']))
      await flushPromises()
      expect(wrapper.findComponent({ name: 'HeroCover' }).props()).toMatchObject({ positionX: 15, positionY: 75 })
      wrapper.unmount()
      expect(revoke).toHaveBeenCalledWith('blob:dashboard-cover')
    } finally {
      create.mockRestore()
      revoke.mockRestore()
    }
  })
})
