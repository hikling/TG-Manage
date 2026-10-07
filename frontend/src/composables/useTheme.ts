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
export const DEFAULT_ACCENT = '#3d6fa8'
export const ACCENT_PRESETS = [
  { name: '蓝韵', color: '#3d6fa8' },
  { name: '潮汐青', color: '#247e83' },
  { name: '电光紫红', color: '#a83d8f' },
  { name: '柔雾紫', color: '#765ba7' },
  { name: '可可棕', color: '#866044' },
  { name: '暖沙金', color: '#9b702e' },
] as const
const validHex = (value: string): boolean => /^#[0-9a-f]{6}$/i.test(value)
const savedAccent = storageGet('tg-manage-accent-color')
const accentColor = ref(savedAccent && validHex(savedAccent) ? savedAccent.toLowerCase() : DEFAULT_ACCENT)

function applyAccent(color: string) {
  const channels = [1, 3, 5].map(index => parseInt(color.slice(index, index + 2), 16))
  const luminanceOf = (rgb: number[]) => rgb.map(channel => {
    const normalized = channel / 255
    return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4
  }).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0)
  const luminance = luminanceOf(channels)
  const foreground = 1.05 / (luminance + 0.05) >= (luminance + 0.05) / 0.05 ? '#ffffff' : '#000000'
  const surface = isDark.value ? [25, 40, 50] : [255, 255, 255]
  const surfaceLuminance = luminanceOf(surface)
  const contrast = (left: number, right: number) => (Math.max(left, right) + 0.05) / (Math.min(left, right) + 0.05)
  let textChannels = channels
  if (contrast(luminance, surfaceLuminance) < 4.5) {
    const target = isDark.value ? 255 : 0
    for (let step = 1; step <= 20; step += 1) {
      textChannels = channels.map(channel => Math.round(channel + (target - channel) * step / 20))
      if (contrast(luminanceOf(textChannels), surfaceLuminance) >= 4.5) break
    }
  }
  const textColor = `#${textChannels.map(channel => channel.toString(16).padStart(2, '0')).join('')}`
  const root = document.documentElement.style
  root.setProperty('--tg-accent', color)
  root.setProperty('--tg-accent-text', textColor)
  root.setProperty('--tg-accent-soft', `color-mix(in srgb, ${color} 15%, var(--tg-bg-elevated))`)
  root.setProperty('--tg-on-accent', foreground)
  root.setProperty('--tg-accent-hover', `color-mix(in srgb, ${color} 85%, ${foreground === '#ffffff' ? '#000000' : '#ffffff'})`)
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
          duration: 500,
          easing: 'ease-in-out',
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
