import { afterEach, describe, expect, it } from 'vitest'
import { useTheme } from '../composables/useTheme'

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
})
