import { ref } from 'vue'
import { storageGet, storageSet } from '../lib/safe-storage'

// 主题色常量与 index.html / PWA manifest 保持一致
const LIGHT_THEME_COLOR = '#ffffff'
const DARK_THEME_COLOR = '#0f172a'

/** 同步浏览器标签栏/地址栏主题色（含 PWA 安装后运行时），跟随实际主题而非系统偏好 */
const applyThemeColor = (dark: boolean) => {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (meta) meta.content = dark ? DARK_THEME_COLOR : LIGHT_THEME_COLOR
}

// 存储不可用时按「未设置」处理，回退系统偏好
const savedTheme = storageGet('theme')
const prefersDark = typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches
const initDark = savedTheme === 'dark' || (savedTheme === null && prefersDark)
const isDark = ref(initDark)
export const DEFAULT_ACCENT = '#3367a6'
export const ACCENT_PRESETS = [
  { nameKey: 'appearance.presetBlue', color: '#3367a6' },
  { nameKey: 'appearance.presetTidal', color: '#1b7a75' },
  { nameKey: 'appearance.presetViolet', color: '#8f447b' },
  { nameKey: 'appearance.presetMist', color: '#5d60a6' },
  { nameKey: 'appearance.presetCocoa', color: '#8f5839' },
  { nameKey: 'appearance.presetSand', color: '#a37224' },
] as const
const validHex = (value: string): boolean => /^#[0-9a-f]{6}$/i.test(value)
const savedAccent = storageGet('tg-manage-accent-color')
const accentColor = ref(savedAccent && validHex(savedAccent) ? savedAccent.toLowerCase() : DEFAULT_ACCENT)

const luminanceOf = (rgb: number[]) => rgb.map(channel => {
  const normalized = channel / 255
  return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
}).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0)

const toHex = (rgb: number[]) => `#${rgb.map(channel => channel.toString(16).padStart(2, '0')).join('')}`
const mixRgb = (color: number[], background: number[], amount: number) =>
  color.map((channel, index) => Math.round(channel * amount + background[index] * (1 - amount)))

// 独立于普通强调色按钮：账号检测始终使用白字，背景按需压暗到 WCAG AA。
export function whiteTextActionColor(color: string): string {
  if (!validHex(color)) return '#23568d'
  const channels = [1, 3, 5].map(index => parseInt(color.slice(index, index + 2), 16))
  for (let step = 0; step <= 100; step += 1) {
    const candidate = channels.map(channel => Math.round(channel * (100 - step) / 100))
    if (1.05 / (luminanceOf(candidate) + 0.05) >= 4.5) return toHex(candidate)
  }
  return '#000000'
}

function applyAccent(color: string) {
  const channels = [1, 3, 5].map(index => parseInt(color.slice(index, index + 2), 16))
  const luminance = luminanceOf(channels)
  const foreground = 1.05 / (luminance + 0.05) >= (luminance + 0.05) / 0.05 ? '#ffffff' : '#000000'
  // 兼顾浅色带色调表面、暗色深石板灰及回归测试底色，确保强调色文字满足 WCAG AA。
  const surfaces = isDark.value
    ? [
        [21, 28, 39],
        [27, 36, 51],
        [25, 40, 50],
        [30, 48, 58],
        mixRgb(channels, [21, 28, 39], 0.16),
        mixRgb(channels, [25, 40, 50], 0.15),
        mixRgb(channels, [16, 27, 36], 0.14),
      ]
    : [
        [255, 255, 255],
        [238, 243, 250],
        mixRgb(channels, [255, 255, 255], 0.15),
        mixRgb(channels, [248, 250, 252], 0.09),
        mixRgb(channels, [238, 243, 250], 0.14),
      ]
  const surfaceLuminance = isDark.value
    ? Math.max(...surfaces.map(luminanceOf))
    : Math.min(...surfaces.map(luminanceOf))
  const contrast = (left: number, right: number) => (Math.max(left, right) + 0.05) / (Math.min(left, right) + 0.05)
  let textChannels = channels
  if (contrast(luminance, surfaceLuminance) < 4.5) {
    const target = isDark.value ? 255 : 0
    for (let step = 1; step <= 20; step += 1) {
      textChannels = channels.map(channel => Math.round(channel + (target - channel) * step / 20))
      if (contrast(luminanceOf(textChannels), surfaceLuminance) >= 4.5) break
    }
  }
  const textColor = toHex(textChannels)
  const root = document.documentElement.style
  root.setProperty('--tg-accent', color)
  root.setProperty('--tg-accent-text', textColor)
  root.setProperty('--tg-accent-soft', `color-mix(in srgb, ${color} ${isDark.value ? '15%' : '9%'}, var(--tg-bg-elevated))`)
  root.setProperty('--tg-accent-ring', `color-mix(in srgb, ${color} ${isDark.value ? '24%' : '16%'}, transparent)`)
  root.setProperty('--tg-accent-border', `color-mix(in srgb, ${color} ${isDark.value ? '32%' : '24%'}, var(--tg-border))`)
  root.setProperty('--tg-on-accent', foreground)
  root.setProperty('--tg-accent-hover', `color-mix(in srgb, ${color} 87%, ${foreground === '#ffffff' ? '#000000' : '#ffffff'})`)
  const accountAction = whiteTextActionColor(color)
  const actionChannels = [1, 3, 5].map(index => parseInt(accountAction.slice(index, index + 2), 16))
  root.setProperty('--tg-account-action', accountAction)
  root.setProperty('--tg-account-action-hover', toHex(actionChannels.map(channel => Math.round(channel * 0.87))))
}

if (initDark) {
  document.documentElement.classList.add('dark')
} else {
  document.documentElement.classList.remove('dark')
}
applyThemeColor(initDark)
applyAccent(accentColor.value)

export const useTheme = () => {
  const setAccentColor = (color: string) => {
    if (!validHex(color)) return false
    accentColor.value = color.toLowerCase()
    storageSet('tg-manage-accent-color', accentColor.value)
    applyAccent(accentColor.value)
    return true
  }
  const toggleTheme = (event?: MouseEvent) => {
    const prefersReducedMotion = typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const isAppearanceTransition = typeof document !== 'undefined' && typeof document.startViewTransition === 'function' && !prefersReducedMotion

    if (!isAppearanceTransition || !event) {
      isDark.value = !isDark.value
      updateDOM()
      return
    }

    const x = event.clientX
    const y = event.clientY
    const endRadius = Math.hypot(
      Math.max(x, innerWidth - x),
      Math.max(y, innerHeight - y)
    )

    const transition = document.startViewTransition(() => {
      isDark.value = !isDark.value
      updateDOM()
    })

    transition.ready.then(() => {
      const clipPath = [
        `circle(0px at ${x}px ${y}px)`,
        `circle(${endRadius}px at ${x}px ${y}px)`
      ]

      document.documentElement.animate(
        {
          clipPath: clipPath
        },
        {
          duration: 380,
          easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
          pseudoElement: '::view-transition-new(root)'
        }
      )
    }).catch(() => {
      // View Transition 被跳过（如页面不可见）时 ready 会 reject，此处静默降级
    })
  }

  const updateDOM = () => {
    if (isDark.value) {
      document.documentElement.classList.add('dark')
      storageSet('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      storageSet('theme', 'light')
    }
    applyThemeColor(isDark.value)
    applyAccent(accentColor.value)
  }

  return { isDark, toggleTheme, accentColor, setAccentColor }
}
