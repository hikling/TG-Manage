import { afterEach, describe, expect, it } from 'vitest'
import { ACCENT_PRESETS, useTheme, whiteTextActionColor } from '../composables/useTheme'

function luminanceOf(color: string): number {
  const channels = [1, 3, 5].map(index => parseInt(color.slice(index, index + 2), 16))
  return channels.map(channel => {
    const value = channel / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0)
}

function contrast(left: string, right: string): number {
  const values = [luminanceOf(left), luminanceOf(right)]
  return (Math.max(...values) + 0.05) / (Math.min(...values) + 0.05)
}

const whiteContrast = (color: string) => contrast(color, '#ffffff')

function mixHex(color: string, background: string, amount: number): string {
  const channels = [1, 3, 5].map(index => {
    const foreground = parseInt(color.slice(index, index + 2), 16)
    const behind = parseInt(background.slice(index, index + 2), 16)
    return Math.round(foreground * amount + behind * (1 - amount)).toString(16).padStart(2, '0')
  })
  return `#${channels.join('')}`
}

describe('custom accent theme', () => {
  afterEach(() => {
    useTheme().setAccentColor('#3d6fa8')
    localStorage.removeItem('tg-manage-accent-color')
  })

  it('applies a valid accent and chooses readable foreground', () => {
    const theme = useTheme()
    expect(theme.setAccentColor('#FFF000')).toBe(true)
    expect(theme.accentColor.value).toBe('#fff000')
    expect(document.documentElement.style.getPropertyValue('--tg-on-accent')).toBe('#000000')
    expect(localStorage.getItem('tg-manage-accent-color')).toBe('#fff000')
    expect(theme.setAccentColor('#not-a-color')).toBe(false)
    expect(theme.accentColor.value).toBe('#fff000')
  })

  it('keeps account-check white text at AA contrast for presets and custom colors', () => {
    const theme = useTheme()
    for (const color of [...ACCENT_PRESETS.map(preset => preset.color), '#fff000', '#ffffff', '#111111', '#82d0ff']) {
      expect(theme.setAccentColor(color)).toBe(true)
      const action = document.documentElement.style.getPropertyValue('--tg-account-action')
      const hover = document.documentElement.style.getPropertyValue('--tg-account-action-hover')
      expect(action).toBe(whiteTextActionColor(color))
      expect(whiteContrast(action)).toBeGreaterThanOrEqual(4.5)
      expect(whiteContrast(hover)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('keeps accent text readable on tinted sidebar, hero and soft card surfaces', () => {
    const theme = useTheme()
    const wasDark = theme.isDark.value
    try {
      if (theme.isDark.value) theme.toggleTheme()
      for (const color of ['#ee0022', '#fff000', '#765ba7']) {
        theme.setAccentColor(color)
        const text = document.documentElement.style.getPropertyValue('--tg-accent-text')
        expect(contrast(text, mixHex(color, '#f8fafc', 0.09))).toBeGreaterThanOrEqual(4.5)
        expect(contrast(text, mixHex(color, '#ffffff', 0.15))).toBeGreaterThanOrEqual(4.5)
      }
      theme.toggleTheme()
      for (const color of ['#000000', '#ee0022', '#ffffff']) {
        theme.setAccentColor(color)
        const text = document.documentElement.style.getPropertyValue('--tg-accent-text')
        expect(contrast(text, mixHex(color, '#101b24', 0.14))).toBeGreaterThanOrEqual(4.5)
        expect(contrast(text, mixHex(color, '#192832', 0.15))).toBeGreaterThanOrEqual(4.5)
      }
    } finally {
      if (theme.isDark.value !== wasDark) theme.toggleTheme()
    }
  })
})
