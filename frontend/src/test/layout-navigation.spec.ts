import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Layout from '../views/Layout.vue'
import i18n from '../i18n'

const mediaQuery = (matches = false) => ({
  matches,
  media: '(max-width: 1023px)',
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  addListener: vi.fn(),
  removeListener: vi.fn(),
  dispatchEvent: vi.fn(),
})

async function mountLayout() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard', name: 'dashboard', component: { template: '<div />' } },
      { path: '/accounts', name: 'accounts', component: { template: '<div />' } },
      { path: '/chats', name: 'chats', component: { template: '<div />' } },
      { path: '/logs', name: 'logs', component: { template: '<div />' } },
      { path: '/settings', name: 'settings', component: { template: '<div />' } },
    ],
  })
  await router.push('/dashboard')
  await router.isReady()
  return mount(Layout, {
    global: {
      plugins: [router, i18n],
      stubs: { UserProfileModal: true, Modal: true, RouterView: true },
    },
  })
}

describe('layout sidebar startup', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('starts collapsed even with a legacy expanded preference, and resets after remount', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery()))
    localStorage.setItem('tg-manage-sidebar-collapsed', '0')
    localStorage.setItem('tg-sidebar-collapsed', '0')

    const first = await mountLayout()
    expect(first.classes()).toContain('sidebar-collapsed')
    const toggle = first.find('button.sidebar-collapse-toggle')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(first.classes()).not.toContain('sidebar-collapsed')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    first.unmount()

    const second = await mountLayout()
    expect(second.classes()).toContain('sidebar-collapsed')
    expect(localStorage.getItem('tg-manage-sidebar-collapsed')).toBe('0')
    second.unmount()
  })

  it('keeps mobile drawer hidden until explicitly opened', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery(true)))
    const wrapper = await mountLayout()
    const sidebar = wrapper.find('aside.ui-sidebar')
    expect(sidebar.attributes('aria-hidden')).toBe('true')
    await wrapper.find('button[aria-label="打开菜单"]').trigger('click')
    expect(sidebar.attributes('aria-hidden')).toBeUndefined()
    wrapper.unmount()
  })
})
