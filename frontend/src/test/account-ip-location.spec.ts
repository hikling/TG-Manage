import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import i18n from '../i18n'
import AccountIpLocation from '../components/accounts/AccountIpLocation.vue'
import type { AccountInfo } from '../lib/api/accounts'

const account = (overrides: Partial<AccountInfo> = {}): AccountInfo => ({
  name: 'alice', session_file: '', exists: true, size: 1,
  route_mode: 'primary', route_status: 'healthy', node_label: 'Tokyo node',
  exit_ip: '203.0.113.12', exit_country: 'Japan', exit_region: 'Tokyo',
  exit_checked_at: '2026-10-15T00:00:00Z', ...overrides,
})

afterEach(() => { i18n.global.locale.value = 'zh-CN' })

describe('account IP location', () => {
  it('shows verified country, region, public IP and source in both locales', async () => {
    const wrapper = mount(AccountIpLocation, { props: { account: account() }, global: { plugins: [i18n] } })
    expect(wrapper.text()).toContain('IP定位')
    expect(wrapper.text()).toContain('Japan · Tokyo')
    expect(wrapper.text()).toContain('203.0.113.12')
    expect(wrapper.text()).toContain('主订阅')
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(wrapper.text()).toContain('IP location')
    expect(wrapper.text()).toContain('Primary subscription')
    expect(wrapper.html()).not.toMatch(/SOCKS5|socks5:\/\//)
  })

  it('shows direct source and shared-node marker; unknown IP never falls back to a node address', async () => {
    const wrapper = mount(AccountIpLocation, {
      props: { account: account({ route_mode: 'fallback', shared_node: true, exit_ip: null, exit_checked_at: null, node_label: 'secret.example' }) },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('兜底订阅 · 共用节点')
    expect(wrapper.text()).toContain('未知位置')
    expect(wrapper.text()).toContain('IP 待验证')
    expect(wrapper.text()).not.toContain('secret.example')
    await wrapper.setProps({ account: account({ route_mode: 'direct', shared_node: false, exit_ip: '198.51.100.7' }) })
    expect(wrapper.text()).toContain('直连')
    expect(wrapper.text()).toContain('198.51.100.7')
  })
})
