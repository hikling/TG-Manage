import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import i18n from '../i18n'
import AccountProxyStatus from '../components/accounts/AccountProxyStatus.vue'
import type { AccountProxyStatus as ProxyState } from '../lib/api/accounts'

afterEach(() => { i18n.global.locale.value = 'zh-CN' })

describe('saved account proxy health', () => {
  it.each([
    ['unconfigured', '', '未配置', 'Not set'],
    ['pending', 'socks5://user:secret@proxy:1080', '待检测', 'Not checked'],
    ['healthy', 'socks5://user:secret@proxy:1080', '正常', 'Healthy'],
    ['error', 'socks5://user:secret@proxy:1080', '异常', 'Unhealthy'],
  ] as const)('renders %s safely and responds to locale changes', async (state, proxy, zh, en) => {
    i18n.global.locale.value = 'zh-CN'
    const wrapper = mount(AccountProxyStatus, {
      props: { account: { proxy, proxy_status: state as ProxyState, proxy_checked_at: '2026-10-14T00:00:00Z' } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain(zh)
    expect(wrapper.html()).not.toContain('secret')
    expect(wrapper.find('.account-tile-status--active').exists()).toBe(state === 'healthy')
    expect(wrapper.find('.account-tile-status--error').exists()).toBe(state === 'error')
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(wrapper.text()).toContain(en)
    expect(wrapper.html()).not.toMatch(/\p{Script=Han}/u)
    if (state === 'healthy' || state === 'error') {
      expect(wrapper.get('.account-tile-status').attributes('title')).toContain('Last checked:')
    }
    wrapper.unmount()
  })

  it('shows pending after a saved edit and unconfigured after clearing', async () => {
    const wrapper = mount(AccountProxyStatus, {
      props: { account: { proxy: 'socks5://proxy:1080', proxy_status: 'healthy' } },
      global: { plugins: [i18n] },
    })
    await wrapper.setProps({ account: { proxy: 'socks5://other:1080', proxy_status: 'pending' } })
    expect(wrapper.text()).toContain('待检测')
    expect(wrapper.get('.account-tile-status').attributes('title')).toContain('00:00')
    await wrapper.setProps({ account: { proxy: '', proxy_status: 'unconfigured' } })
    expect(wrapper.text()).toContain('未配置')
    wrapper.unmount()
  })

  it('never echoes an invalid timestamp and treats unmeasured configured proxies as pending', () => {
    const wrapper = mount(AccountProxyStatus, {
      props: { account: { proxy: 'socks5://secret@proxy:1080', proxy_checked_at: 'secret' } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('待检测')
    expect(wrapper.html()).not.toContain('secret')
    wrapper.unmount()
  })
})
