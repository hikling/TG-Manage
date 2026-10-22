import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '../i18n'
import AboutSettings from '../components/settings/AboutSettings.vue'
import BotNotifySettings from '../components/settings/BotNotifySettings.vue'
import GeneralSettings from '../components/settings/GeneralSettings.vue'
import type { SettingsFormState } from '../lib/settings-form'

const settingsState = (): SettingsFormState => ({
  logDays: 7,
  dataDir: '',
  concurrency: 1,
  deviceKeepaliveEnabled: true,
  deviceKeepaliveIntervalDays: 30,
  botEnabled: false,
  botLoginNotify: false,
  botCodeEnabled: false,
  botToken: '',
  botChatId: '',
  botThreadId: '',
  botWebUrl: '',
  timezone: 'Asia/Hong_Kong',
})

describe('设置页拆分组件契约', () => {
  it('AboutSettings 展示后端 current_rss_mb 字段', () => {
    const wrapper = mount(AboutSettings, {
      props: {
        appVersion: null,
        runtimeStatus: {
          ready: true,
          scheduler_lock_held: true,
          legacy_tasks_writable: false,
          legacy_tasks_removed: true,
          database_is_sqlite: true,
          monitor_shard: '',
          monitor_allowlist: '',
        },
        memoryStats: { available: true, stats: { current_rss_mb: 128.456 } },
        versionBanner: null,
      },
      global: { plugins: [i18n] },
    })

    expect(wrapper.text()).toContain('128.5 MB')
  })

  it('GeneralSettings 清空数字输入时保留空值而不是转换为 0', async () => {
    const wrapper = mount(GeneralSettings, {
      props: {
        modelValue: settingsState(),
        timezoneOptions: [],
      },
      global: { plugins: [i18n] },
    })

    await wrapper.find('input[type="number"]').setValue('')

    const updates = wrapper.emitted('update:modelValue')
    expect(updates).toBeTruthy()
    expect((updates?.at(-1)?.[0] as SettingsFormState).logDays).toBe('')
  })

  it('GeneralSettings 不再提供自动保活开关或间隔输入', () => {
    const wrapper = mount(GeneralSettings, {
      props: { modelValue: settingsState(), timezoneOptions: [] },
      global: { plugins: [i18n] },
    })

    expect(wrapper.find('[role="switch"]').exists()).toBe(false)
    expect(wrapper.find('#settings-proxy').exists()).toBe(false)
    expect(wrapper.findAll('input[type="number"]').map(input => input.attributes('id'))).toEqual([
      'settings-log-retention', 'settings-concurrency',
    ])
    expect(wrapper.text()).not.toContain('170')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it.each(['zh-CN', 'en-US'] as const)('GeneralSettings 在 %s 说明仅零点自动检测规则', (locale) => {
    const previousLocale = i18n.global.locale.value
    i18n.global.locale.value = locale
    try {
      const wrapper = mount(GeneralSettings, {
        props: { modelValue: settingsState(), timezoneOptions: [] },
        global: { plugins: [i18n] },
      })
      const text = wrapper.text()
      if (locale === 'zh-CN') {
        expect(text).toContain('账户状态检测')
        expect(text).toContain('仅在配置时区的每日 00:00 自动检测全部账户')
        expect(text).toContain('其他时间请手动检测')
      } else {
        expect(text).toContain('Account Status Checks')
        expect(text).toContain('automatically only at 00:00 daily in the configured timezone')
        expect(text).toContain('At other times, run checks manually')
        expect(text).not.toMatch(/\p{Script=Han}/u)
      }
      expect(text).not.toContain('170')
    } finally {
      i18n.global.locale.value = previousLocale
    }
  })

  it('GeneralSettings 只展示自动检测规则，不再提供手动保活', () => {
    const wrapper = mount(GeneralSettings, {
      props: {
        modelValue: { ...settingsState(), deviceKeepaliveEnabled: false },
        timezoneOptions: [],
      },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain(i18n.global.t('settings.deviceKeepaliveDesc'))
    expect(wrapper.find('button.ui-btn-secondary').exists()).toBe(false)
    expect(wrapper.emitted('run-keepalive')).toBeUndefined()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('BotNotifySettings 的私人验证码选项支持英文界面', () => {
    const previousLocale = i18n.global.locale.value
    i18n.global.locale.value = 'en-US'
    try {
      const wrapper = mount(BotNotifySettings, {
        props: { modelValue: { ...settingsState(), botCodeEnabled: true }, reveal: { botToken: false } },
        global: { plugins: [i18n] },
      })
      expect(wrapper.text()).toContain('Enable private bot')
      expect(wrapper.text()).toContain('Enter a positive private user ID')
      expect(wrapper.text()).not.toContain('启用私人机器人')
    } finally {
      i18n.global.locale.value = previousLocale
    }
  })

  it('BotNotifySettings only offers saving and the connection test', async () => {
    const wrapper = mount(BotNotifySettings, {
      props: { modelValue: settingsState(), reveal: { botToken: false } },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).not.toContain('静默时段')
    expect(wrapper.find('#bot-quiet-start').exists()).toBe(false)
    const buttons = wrapper.findAll('button.ui-btn-secondary')
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(wrapper.emitted('test')).toBeUndefined()
    expect(wrapper.emitted('test-connection')).toHaveLength(1)
  })
})
