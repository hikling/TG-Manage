import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import i18n from '../i18n'
import { flushPromises } from './composable-test-utils'

const api = vi.hoisted(() => ({
  getHeroImage: vi.fn(),
  getHeroSettings: vi.fn(),
}))

vi.mock('../lib/api/appearance', () => api)

import Dashboard from '../views/Dashboard.vue'

describe('dashboard actions', () => {
  beforeEach(() => vi.clearAllMocks())
  it('keeps the dashboard to the cover and its two primary actions', async () => {
    api.getHeroImage.mockRejectedValue(new Error('no cover'))
    api.getHeroSettings.mockRejectedValue(new Error('no cover'))
    const previousLocale = i18n.global.locale.value
    i18n.global.locale.value = 'en-US'
    try {
      const wrapper = mount(Dashboard, { global: { plugins: [i18n], stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
      await flushPromises()
      expect(wrapper.findAll('a')).toHaveLength(1)
      expect(wrapper.findAll('button')).toHaveLength(1)
      expect(wrapper.text()).toContain('Manage accounts')
      expect(wrapper.text()).toContain('Refresh')
      expect(wrapper.text()).not.toMatch(/[\u3400-\u9fff]/)
      expect(api.getHeroImage).toHaveBeenCalledTimes(1)
      wrapper.unmount()
    } finally { i18n.global.locale.value = previousLocale }
  })

  it('preserves locally adjusted framing while an older cover read completes', async () => {
    let finish!: (blob: Blob) => void
    api.getHeroImage.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    api.getHeroSettings.mockResolvedValue({ present: true, position_x: 50, position_y: 50 })
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:dashboard-cover')
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const wrapper = mount(Dashboard, { global: { plugins: [i18n], stubs: { RouterLink: true, HeroCover: true } } })
    try {
      window.dispatchEvent(new CustomEvent('tg-manage:hero-position-changed', { detail: { x: 15, y: 75 } }))
      finish(new Blob(['cover']))
      await flushPromises()
      expect(wrapper.findComponent({ name: 'HeroCover' }).props()).toMatchObject({ positionX: 15, positionY: 75 })
      wrapper.unmount()
      expect(revoke).toHaveBeenCalledWith('blob:dashboard-cover')
    } finally { create.mockRestore(); revoke.mockRestore() }
  })
})
