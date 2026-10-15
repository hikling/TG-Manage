import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import Layout from '../views/Layout.vue'
import i18n from '../i18n'
import { getBodyScrollLockCount, resetBodyScrollLock } from '../lib/body-scroll-lock'

const mediaQuery = (matches = false) => ({
  matches,
  media: '(max-width: 1023px)',
  addEventListener: vi.fn<(event: string, listener: () => void) => void>(),
  removeEventListener: vi.fn(),
  addListener: vi.fn(),
  removeListener: vi.fn(),
  dispatchEvent: vi.fn(),
})

async function changeViewport(query: ReturnType<typeof mediaQuery>, matches: boolean) {
  query.matches = matches
  for (const [event, listener] of query.addEventListener.mock.calls) {
    if (event === 'change') listener()
  }
  await nextTick()
}

async function mountLayout() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboard', name: 'dashboard', component: { template: '<div />' } },
      { path: '/accounts', name: 'accounts', component: { template: '<div />' } },
      { path: '/chats', name: 'chats', component: { template: '<div />' } },
      { path: '/settings', name: 'settings', component: { template: '<div />' } },
    ],
  })
  await router.push('/dashboard')
  await router.isReady()
  return mount(Layout, {
    attachTo: document.body,
    global: {
      plugins: [router, i18n],
      stubs: { UserProfileModal: true, Modal: true, RouterView: true },
    },
  })
}

enableAutoUnmount(afterEach)

describe('layout responsive navigation', () => {
  afterEach(() => {
    resetBodyScrollLock()
    vi.unstubAllGlobals()
  })

  it('does not expose the retired runtime logs page', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery()))
    const wrapper = await mountLayout()
    expect(wrapper.find('a[href="/logs"]').exists()).toBe(false)
  })

  it('keeps the desktop collapse control without a header menu button, and resets after remount', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery()))
    localStorage.setItem('tg-manage-sidebar-collapsed', '0')
    localStorage.setItem('tg-sidebar-collapsed', '0')

    const first = await mountLayout()
    expect(first.find('header button[aria-label="打开菜单"]').exists()).toBe(false)
    expect(first.classes()).toContain('sidebar-collapsed')
    const toggle = first.find('button.sidebar-collapse-toggle')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    await toggle.trigger('click')
    expect(first.classes()).not.toContain('sidebar-collapsed')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(first.find('header button[aria-label="打开菜单"]').exists()).toBe(false)
    first.unmount()

    const second = await mountLayout()
    expect(second.classes()).toContain('sidebar-collapsed')
    expect(localStorage.getItem('tg-manage-sidebar-collapsed')).toBe('0')
    second.unmount()
  })

  it('opens the mobile drawer and supports its close button, Escape, backdrop and navigation', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => mediaQuery(true)))
    const wrapper = await mountLayout()
    const sidebar = wrapper.find('aside.ui-sidebar')
    const menu = wrapper.find('header button[aria-label="打开菜单"]')
    const close = sidebar.find('button[aria-label="关闭"]')
    expect(sidebar.attributes('aria-hidden')).toBe('true')
    expect(sidebar.attributes('inert')).toBeDefined()
    expect(menu.attributes('aria-expanded')).toBe('false')

    await menu.trigger('click')
    await nextTick()
    expect(sidebar.attributes('aria-hidden')).toBeUndefined()
    expect(sidebar.attributes('inert')).toBeUndefined()
    expect(menu.attributes('aria-expanded')).toBe('true')
    expect(document.activeElement).toBe(close.element)
    expect(document.body.style.overflow).toBe('hidden')
    await close.trigger('click')
    await nextTick()
    expect(sidebar.attributes('aria-hidden')).toBe('true')
    expect(document.activeElement).toBe(menu.element)
    expect(getBodyScrollLockCount()).toBe(0)

    await menu.trigger('click')
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(menu.attributes('aria-expanded')).toBe('false')
    expect(document.body.style.overflow).toBe('')

    await menu.trigger('click')
    await wrapper.find('div.fixed.inset-0[aria-hidden="true"]').trigger('click')
    expect(sidebar.attributes('aria-hidden')).toBe('true')
    expect(getBodyScrollLockCount()).toBe(0)

    await menu.trigger('click')
    await sidebar.find('a[href="/accounts"]').trigger('click')
    expect(menu.attributes('aria-expanded')).toBe('false')
    expect(sidebar.attributes('aria-hidden')).toBe('true')
    expect(getBodyScrollLockCount()).toBe(0)
  })

  it('removes the menu and releases the drawer lock when crossing to desktop, then returns closed on mobile', async () => {
    const query = mediaQuery(true)
    const matchMedia = vi.fn(() => query)
    vi.stubGlobal('matchMedia', matchMedia)
    const wrapper = await mountLayout()
    expect(matchMedia).toHaveBeenCalledWith('(max-width: 1023px)')
    await wrapper.find('header button[aria-label="打开菜单"]').trigger('click')
    expect(getBodyScrollLockCount()).toBe(1)

    await changeViewport(query, false)
    expect(wrapper.find('header button[aria-label="打开菜单"]').exists()).toBe(false)
    expect(wrapper.find('aside.ui-sidebar').attributes('aria-hidden')).toBeUndefined()
    expect(wrapper.find('button.sidebar-collapse-toggle').exists()).toBe(true)
    expect(wrapper.find('div.fixed.inset-0[aria-hidden="true"]').exists()).toBe(false)
    expect(getBodyScrollLockCount()).toBe(0)
    expect(document.body.style.overflow).toBe('')

    await changeViewport(query, true)
    const menu = wrapper.find('header button[aria-label="打开菜单"]')
    expect(menu.exists()).toBe(true)
    expect(menu.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('aside.ui-sidebar').attributes('aria-hidden')).toBe('true')
    await menu.trigger('click')
    expect(wrapper.find('aside.ui-sidebar').attributes('aria-hidden')).toBeUndefined()
    wrapper.unmount()
    expect(getBodyScrollLockCount()).toBe(0)
    expect(query.removeEventListener).toHaveBeenCalledWith('change', query.addEventListener.mock.calls[0]?.[1])
  })
})
