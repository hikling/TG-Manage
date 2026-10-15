import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import i18n from '../i18n'
import ProxySubscriptionsSettings, { type SubscriptionDraft } from '../components/settings/ProxySubscriptionsSettings.vue'
import type { ProxySubscriptionSettings } from '../lib/api/settings'

const status: ProxySubscriptionSettings = {
  primary: { configured: true, status: 'healthy', last_refreshed_at: '2026-10-15T00:00:00Z', usable_count: 3, unsupported_count: 1, label: 'Primary provider' },
  fallback: { configured: false, status: 'unconfigured', last_refreshed_at: null, usable_count: 0, unsupported_count: 0, label: null },
  latency_threshold_ms: 800,
  route_mode: 'primary',
}
const draft: SubscriptionDraft = {
  primaryUrl: '', fallbackUrl: '', clearPrimary: false, clearFallback: false, latencyThresholdMs: 800,
}
const mountSettings = (overrides: Record<string, unknown> = {}) => mount(ProxySubscriptionsSettings, {
  props: { modelValue: draft, status, dirty: false, ...overrides },
  global: { plugins: [i18n] },
})

afterEach(() => { i18n.global.locale.value = 'zh-CN' })

describe('Xray subscription settings', () => {
  it('shows sanitized source status, counts and routing mode without stored URL', () => {
    const wrapper = mountSettings()
    expect(wrapper.text()).toContain('Primary provider')
    expect(wrapper.text()).toContain('可用节点')
    expect(wrapper.text()).toContain('主订阅')
    expect(wrapper.get<HTMLInputElement>('#subscription-primary').element.value).toBe('')
    expect(wrapper.get('#subscription-primary').attributes('type')).toBe('password')
    expect(wrapper.html()).not.toContain('https://secret.example/sub')
    expect(wrapper.get('button.ui-btn-primary').attributes('disabled')).toBeDefined()
  })

  it('emits replacement and explicit clear edits, while refresh waits for save', async () => {
    const wrapper = mountSettings({ dirty: true })
    await wrapper.get('#subscription-primary').setValue('https://new.example/sub')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ primaryUrl: 'https://new.example/sub' })
    const clear = wrapper.findAll('input[type="checkbox"]')[0]
    await clear?.setValue(true)
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ clearPrimary: true, primaryUrl: '' })
    expect(wrapper.get('button.ui-btn-secondary').attributes('disabled')).toBeDefined()
    await wrapper.get('button.ui-btn-primary').trigger('click')
    expect(wrapper.emitted('save')).toHaveLength(1)
  })

  it('labels direct mode clearly in both locales', async () => {
    const wrapper = mountSettings({ status: { ...status, route_mode: 'direct' } })
    expect(wrapper.text()).toContain('账户正在直连')
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(wrapper.text()).toContain('Accounts are using direct connections')
    expect(wrapper.text()).not.toMatch(/\p{Script=Han}/u)
  })
})
