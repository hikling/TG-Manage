import { describe, it, expect } from 'vitest'
import {
  emptyToNull,
  parseNumberInputValue,
  applyGlobalSettingsToForm,
  buildGeneralPayload,
  buildBotPayload,
  buildAdvancedPayload,
  buildBackupPayload,
  snapAllSections,
  isAnySectionDirty,
  dirtySectionLabels,
  type SettingsFormState,
} from '../lib/settings-form'

const baseSettings = (): SettingsFormState => ({
  checkInterval: '30',
  logDays: 7,
  dataDir: '/data',
  proxy: '',
  concurrency: 2,
  deviceKeepaliveEnabled: true,
  chatCenterEnabled: false,
  deviceKeepaliveIntervalDays: 30,
  botEnabled: false,
  botLoginNotify: false,
  botTaskFailure: true,
  botTaskSuccess: false,
  quietEnabled: false,
  quietStart: '23:00',
  quietEnd: '07:00',
  botToken: '',
  botChatId: '',
  botThreadId: '',
  timezone: 'Asia/Hong_Kong',
  autoBackupEnabled: false,
  autoBackupInterval: 24,
  autoBackupKeep: 3,
  webdavUrl: '',
  webdavUsername: '',
  webdavPassword: '',
  webdavRemoteDir: 'tg-signpulse-backups',
})

describe('settings-form', () => {
  it('emptyToNull handles empty and invalid', () => {
    expect(emptyToNull('')).toBeNull()
    expect(emptyToNull('12')).toBe(12)
    expect(emptyToNull('x')).toBeNull()
    expect(emptyToNull(0)).toBe(0)
  })

  it('parseNumberInputValue keeps empty and drops NaN', () => {
    expect(parseNumberInputValue('')).toBe('')
    expect(parseNumberInputValue('3')).toBe(3)
    expect(parseNumberInputValue('1.5')).toBe(1.5)
    expect(parseNumberInputValue('abc')).toBe('')
    expect(parseNumberInputValue('NaN')).toBe('')
  })

  it('buildGeneralPayload maps fields', () => {
    const p = buildGeneralPayload(baseSettings())
    expect(p.sign_interval).toBe(30)
    expect(p.log_retention_days).toBe(7)
    expect(p.timezone).toBe('Asia/Hong_Kong')
  })

  it('buildGeneralPayload normalizes empty numeric fields to safe defaults', () => {
    const s = baseSettings()
    s.logDays = ''
    s.concurrency = ''
    s.deviceKeepaliveIntervalDays = ''

    const p = buildGeneralPayload(s)

    expect(p.log_retention_days).toBe(7)
    expect(p.tg_global_concurrency).toBe(1)
    expect(p.device_keepalive_interval_days).toBe(30)
  })

  it('buildGeneralPayload clamps out-of-range numbers', () => {
    const s = baseSettings()
    s.concurrency = 99
    s.deviceKeepaliveIntervalDays = 500

    const p = buildGeneralPayload(s)

    expect(p.tg_global_concurrency).toBe(10)
    expect(p.device_keepalive_interval_days).toBe(170)
  })

  it('buildBotPayload parses thread id', () => {
    const s = baseSettings()
    s.botThreadId = '42'
    s.botEnabled = true
    const p = buildBotPayload(s)
    expect(p.telegram_bot_message_thread_id).toBe(42)
    expect(p.telegram_bot_notify_enabled).toBe(true)
  })

  it('buildBotPayload omits empty token (keep server value)', () => {
    const s = baseSettings()
    s.botToken = ''
    const p = buildBotPayload(s) as Record<string, unknown>
    expect('telegram_bot_token' in p).toBe(false)
    s.botToken = '123:ABC'
    const p2 = buildBotPayload(s) as Record<string, unknown>
    expect(p2.telegram_bot_token).toBe('123:ABC')
  })

  it('buildAdvancedPayload only contains data management fields', () => {
    const p = buildAdvancedPayload(baseSettings())
    expect(p.auto_backup_keep).toBe(3)
    expect('ai_vision_timeout' in p).toBe(false)
    expect('sign_task_execution_timeout' in p).toBe(false)
  })

  it('buildBackupPayload only includes backup/webdav fields', () => {
    const s = baseSettings()
    s.webdavUrl = 'https://dav.example'
    s.webdavPassword = 'secret'
    const p = buildBackupPayload(s) as Record<string, unknown>
    expect(p.webdav_url).toBe('https://dav.example')
    expect(p.webdav_password).toBe('secret')
    expect('sign_task_execution_timeout' in p).toBe(false)
    expect('ai_vision_timeout' in p).toBe(false)
  })

  it('section dirty is independent', () => {
    const s = baseSettings()
    const baseline = snapAllSections(s)

    const s2 = { ...s, botEnabled: true }
    const cur = snapAllSections(s2)
    expect(isAnySectionDirty(baseline, cur)).toBe(true)
    // 仅 bot 脏：general 快照应相同
    expect(cur.general).toBe(baseline.general)
    expect(cur.bot).not.toBe(baseline.bot)

    const labels = dirtySectionLabels(baseline, cur, {
      general: 'G',
      bot: 'B',
      advanced: 'A',
    })
    expect(labels).toEqual(['B'])
  })

  it('backup fields dirty advanced section', () => {
    const s = baseSettings()
    const baseline = snapAllSections(s)

    const sBackup = { ...s, autoBackupEnabled: true }
    const curBackup = snapAllSections(sBackup)
    expect(curBackup.advanced).not.toBe(baseline.advanced)
  })

  it('secret fields mask in snapshot (bot token)', () => {
    const s = baseSettings()
    s.botToken = '123:ABC'
    const snap = snapAllSections(s)
    expect(snap.bot).toContain('***set***')
    expect(snap.bot).not.toContain('123:ABC')
  })
  it('buildBotPayload ignores invalid thread id', () => {
    const s = baseSettings()
    s.botThreadId = 'abc'
    const p = buildBotPayload(s)
    expect(p.telegram_bot_message_thread_id).toBeNull()
  })

})

describe('applyGlobalSettingsToForm', () => {
  it('maps server payload into form fields without secrets', () => {
    const s = baseSettings()
    const flags = applyGlobalSettingsToForm(s, {
      sign_interval: 45,
      log_retention_days: 14,
      telegram_bot_token_set: true,
      webdav_password_set: true,
      telegram_bot_message_thread_id: 9,
      timezone: 'UTC',
    })
    expect(s.checkInterval).toBe('45')
    expect(s.logDays).toBe(14)
    expect(s.botToken).toBe('')
    expect(s.webdavPassword).toBe('')
    expect(s.botThreadId).toBe('9')
    expect(s.timezone).toBe('UTC')
    expect(flags.botTokenSet).toBe(true)
    expect(flags.webdavPasswordSet).toBe(true)
  })
})
