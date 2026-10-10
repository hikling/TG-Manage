<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import {
  LayoutDashboard,
  Users,
  MessagesSquare,
  Terminal,
  Settings,
  UserCircle,
  Github,
  Globe,
  Moon,
  Sun,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  X,
  Palette,
  ImagePlus,
  RotateCcw,
} from 'lucide-vue-next'
import { ACCENT_PRESETS, useTheme } from '../composables/useTheme'
import { useI18n } from '../composables/useI18n'
import { lockBodyScroll, unlockBodyScroll } from '../lib/body-scroll-lock'
import UserProfileModal from '../components/settings/UserProfileModal.vue'
import Modal from '../components/Modal.vue'
import HeroCover from '../components/HeroCover.vue'
import { clampCoverPosition, type CoverFrame } from '../lib/cover-frame'
import { createCoalescedSave } from '../lib/coalesced-save'
import { createViewPrefetcher } from '../lib/view-prefetch'
import { deleteHeroImage, getHeroImage, getHeroSettings, MAX_HERO_IMAGE_BYTES, saveHeroSettings, uploadHeroImage } from '../lib/api/appearance'
import { getGlobalSettings, saveGlobalSettings } from '../lib/api/settings'
import { getAuthToken } from '../lib/api/core'

const route = useRoute()
const { isDark, toggleTheme, accentColor, setAccentColor } = useTheme()
const { locale, toggleLanguage, t } = useI18n()
const isMobileMenuOpen = ref(false)
const showProfileModal = ref(false)
const showAppearanceModal = ref(false)
const heroInput = ref<HTMLInputElement | null>(null)
const heroBusy = ref(false)
const heroPresent = ref(false)
const heroFeedbackKey = ref('')
const heroFeedbackKind = ref<'error' | 'status'>('status')
const heroFeedback = computed(() => heroFeedbackKey.value ? t(heroFeedbackKey.value) : '')
const heroPreviewUrl = ref('')
const heroPreview = ref<HTMLElement | null>(null)
const heroPositionX = ref(50)
const heroPositionY = ref(50)
const heroDragging = ref(false)
let heroPointerId: number | null = null
let heroDragOrigin = { clientX: 0, clientY: 0, x: 50, y: 50 }
let heroFrame: CoverFrame = { width: 0, height: 0, overflowX: 0, overflowY: 0 }
let appearanceActive = true
let accentEdited = false
let heroPositionEdited = false
let heroMutationVersion = 0
let heroPositionDirty = false
let accentDirty = false
let accentSaveTimer: ReturnType<typeof setTimeout> | undefined
let heroPositionSaveTimer: ReturnType<typeof setTimeout> | undefined
const sidebarCollapsed = ref(true)
const menuButtonRef = ref<HTMLButtonElement | null>(null)
const drawerCloseButtonRef = ref<HTMLButtonElement | null>(null)

// lg 断点（1023px）以下视为移动端：侧栏是抽屉，关闭时应同步对读屏隐藏
const mobileQuery = window.matchMedia('(max-width: 1023px)')
const isMobileView = ref(mobileQuery.matches)
const onViewportChange = () => {
  isMobileView.value = mobileQuery.matches
}
const sidebarHidden = computed(() => isMobileView.value && !isMobileMenuOpen.value)
const heroFeedbackIsError = computed(() => heroFeedbackKind.value === 'error')
function feedback(key: string, kind: 'error' | 'status' = 'status') {
  if (!appearanceActive) return
  heroFeedbackKey.value = `appearance.${key}`
  heroFeedbackKind.value = kind
}
const accentSaves = createCoalescedSave<string>(
  color => saveGlobalSettings(getAuthToken(), { appearance_accent_color: color }),
  () => feedback('accentSaveFailed', 'error'),
)
const positionSaves = createCoalescedSave<{ x: number; y: number }>(
  position => saveHeroSettings(position.x, position.y),
  () => feedback('positionSaveFailed', 'error'),
)
function flushAccentSave() {
  if (accentSaveTimer) clearTimeout(accentSaveTimer)
  accentSaveTimer = undefined
  if (!accentDirty) return
  accentDirty = false
  void accentSaves.enqueue(accentColor.value)
}
function flushHeroPositionSave() {
  if (heroPositionSaveTimer) clearTimeout(heroPositionSaveTimer)
  heroPositionSaveTimer = undefined
  if (!heroPositionDirty) return
  heroPositionDirty = false
  void positionSaves.enqueue({ x: heroPositionX.value, y: heroPositionY.value })
}

async function refreshHeroPresence() {
  if (!appearanceActive) return
  const version = heroMutationVersion
  try {
    const [blob, settings] = await Promise.all([getHeroImage(), getHeroSettings()])
    if (!appearanceActive || version !== heroMutationVersion) return
    if (heroPreviewUrl.value) URL.revokeObjectURL(heroPreviewUrl.value)
    heroPreviewUrl.value = URL.createObjectURL(blob)
    heroPresent.value = settings.present
    if (!heroPositionEdited) {
      heroPositionX.value = settings.position_x
      heroPositionY.value = settings.position_y
    }
  } catch {
    if (!appearanceActive || version !== heroMutationVersion) return
    heroPresent.value = false
    if (heroPreviewUrl.value) URL.revokeObjectURL(heroPreviewUrl.value)
    heroPreviewUrl.value = ''
  }
}

async function loadAppearanceSettings() {
  try {
    const settings = await getGlobalSettings(getAuthToken())
    if (!appearanceActive) return
    if (!accentEdited && settings.appearance_accent_color) setAccentColor(settings.appearance_accent_color)
    if (!heroPositionEdited) {
      heroPositionX.value = settings.hero_position_x ?? heroPositionX.value
      heroPositionY.value = settings.hero_position_y ?? heroPositionY.value
    }
  } catch {
    // Keep the browser-local fallback when the settings endpoint is unavailable.
  }
  if (heroMutationVersion === 0) await refreshHeroPresence()
}

function handleAccentChange(color: string) {
  if (!setAccentColor(color)) return
  accentEdited = true
  accentDirty = true
  if (accentSaveTimer) clearTimeout(accentSaveTimer)
  accentSaveTimer = setTimeout(flushAccentSave, 350)
}

function persistHeroPosition() {
  heroPositionEdited = true
  heroPositionX.value = clampCoverPosition(heroPositionX.value)
  heroPositionY.value = clampCoverPosition(heroPositionY.value)
  heroPositionDirty = true
  window.dispatchEvent(new CustomEvent('tg-manage:hero-position-changed', {
    detail: { x: heroPositionX.value, y: heroPositionY.value },
  }))
  if (heroPositionSaveTimer) clearTimeout(heroPositionSaveTimer)
  heroPositionSaveTimer = setTimeout(flushHeroPositionSave, 250)
}

function setHeroPositionFromPointer(event: PointerEvent) {
  if (!heroFrame.overflowX || !heroFrame.overflowY) return
  heroPositionX.value = Math.round(clampCoverPosition(heroDragOrigin.x - (event.clientX - heroDragOrigin.clientX) / heroFrame.overflowX * 100))
  heroPositionY.value = Math.round(clampCoverPosition(heroDragOrigin.y - (event.clientY - heroDragOrigin.clientY) / heroFrame.overflowY * 100))
  persistHeroPosition()
}

function startHeroDrag(event: PointerEvent) {
  if (heroBusy.value || event.button !== 0) return
  event.preventDefault()
  heroDragging.value = true
  heroPointerId = event.pointerId
  heroDragOrigin = { clientX: event.clientX, clientY: event.clientY, x: heroPositionX.value, y: heroPositionY.value }
  heroPreview.value?.setPointerCapture?.(event.pointerId)
}

function moveHeroDrag(event: PointerEvent) {
  if (!heroDragging.value || event.pointerId !== heroPointerId) return
  setHeroPositionFromPointer(event)
}

function stopHeroDrag(event?: PointerEvent) {
  if (event && heroPointerId !== null && event.pointerId !== heroPointerId) return
  if (heroPointerId !== null && heroPreview.value?.hasPointerCapture?.(heroPointerId)) {
    heroPreview.value.releasePointerCapture(heroPointerId)
  }
  heroDragging.value = false
  heroPointerId = null
  flushHeroPositionSave()
}

function moveHeroWithKeyboard(event: KeyboardEvent) {
  if (heroBusy.value || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  const step = event.shiftKey ? 10 : 2
  if (event.key === 'ArrowLeft') heroPositionX.value -= step
  if (event.key === 'ArrowRight') heroPositionX.value += step
  if (event.key === 'ArrowUp') heroPositionY.value -= step
  if (event.key === 'ArrowDown') heroPositionY.value += step
  persistHeroPosition()
}

watch(showAppearanceModal, open => {
  if (!open) { stopHeroDrag(); flushAccentSave() }
})

async function onHeroSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size === 0 || file.size > MAX_HERO_IMAGE_BYTES) {
    feedback('invalidCover', 'error')
    return
  }
  ++heroMutationVersion
  heroBusy.value = true
  feedback('uploadingCover')
  try {
    await uploadHeroImage(file)
    if (!appearanceActive) return
    if (heroPreviewUrl.value) URL.revokeObjectURL(heroPreviewUrl.value)
    heroPreviewUrl.value = URL.createObjectURL(file)
    heroPresent.value = true
    feedback('coverUpdated')
    window.dispatchEvent(new Event('tg-manage:hero-changed'))
  } catch {
    feedback('uploadFailed', 'error')
  } finally {
    heroBusy.value = false
  }
}

async function resetHeroImage() {
  ++heroMutationVersion
  heroPositionEdited = true
  heroBusy.value = true
  feedback('resettingCover')
  stopHeroDrag()
  if (heroPositionSaveTimer) clearTimeout(heroPositionSaveTimer)
  heroPositionSaveTimer = undefined
  heroPositionDirty = false
  positionSaves.discard()
  try {
    await positionSaves.whenIdle()
    await deleteHeroImage()
    if (!appearanceActive) return
    heroPresent.value = false
    heroPositionX.value = 50
    heroPositionY.value = 50
    if (heroPreviewUrl.value) URL.revokeObjectURL(heroPreviewUrl.value)
    heroPreviewUrl.value = ''
    feedback('coverReset')
    window.dispatchEvent(new Event('tg-manage:hero-changed'))
  } catch {
    feedback('resetFailed', 'error')
  } finally {
    heroBusy.value = false
  }
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && isMobileMenuOpen.value) {
    isMobileMenuOpen.value = false
  }
}

let menuScrollLocked = false
watch(isMobileMenuOpen, async (open, prev) => {
  if (open) {
    if (!menuScrollLocked) {
      lockBodyScroll()
      menuScrollLocked = true
    }
    // 打开抽屉后把焦点移入（关闭按钮），避免焦点停留在被 inert 隐藏的页面主体
    await nextTick()
    drawerCloseButtonRef.value?.focus()
  } else if (menuScrollLocked) {
    unlockBodyScroll()
    menuScrollLocked = false
  }
  // 抽屉关闭时把焦点归还给汉堡按钮，保证键盘用户的 Tab 起点可预期
  if (!open && prev) {
    await nextTick()
    menuButtonRef.value?.focus()
  }
})

onMounted(() => {
  void loadAppearanceSettings()
  window.addEventListener('keydown', onKeydown)
  mobileQuery.addEventListener('change', onViewportChange)
})
onUnmounted(() => {
  stopHeroDrag()
  flushAccentSave()
  appearanceActive = false
  window.removeEventListener('keydown', onKeydown)
  mobileQuery.removeEventListener('change', onViewportChange)
  if (menuScrollLocked) {
    unlockBodyScroll()
    menuScrollLocked = false
  }
  if (accentSaveTimer) clearTimeout(accentSaveTimer)
  if (heroPositionSaveTimer) clearTimeout(heroPositionSaveTimer)
  if (heroPreviewUrl.value) URL.revokeObjectURL(heroPreviewUrl.value)
})

const viewLoaders: Record<string, () => Promise<unknown>> = {
  dashboard: () => import('../views/Dashboard.vue'),
  accounts: () => import('../views/Accounts.vue'),
  logs: () => import('../views/Logs.vue'),
  settings: () => import('../views/Settings.vue'),
}

const { prefetch: prefetchLoadedView } = createViewPrefetcher(viewLoaders)

const prefetchView = (name: string) => {
  if (route.name === name) return
  prefetchLoadedView(name)
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

const navigation = computed(() => [
  { id: 'dashboard', name: 'dashboard', icon: LayoutDashboard, labelKey: 'nav.dashboard', color: 'cyan' },
  { id: 'accounts', name: 'accounts', icon: Users, labelKey: 'nav.accounts', color: 'blue' },
  { id: 'chats', name: 'chats', icon: MessagesSquare, labelKey: 'nav.chats', color: 'green' },
  { id: 'logs', name: 'logs', icon: Terminal, labelKey: 'nav.logs', color: 'slate' },
  { id: 'settings', name: 'settings', icon: Settings, labelKey: 'nav.settings', color: 'teal' },
])

const currentTitle = computed(() => {
  const current = navigation.value.find(n => n.name === route.name)
  if (!current) return 'TG Manage'
  return t(current.labelKey)
})

// 浏览器标签页标题跟随当前页面，便于多标签切换时识别
watch(
  currentTitle,
  (title) => {
    document.title = title && title !== 'TG Manage' ? `${title} - TG Manage` : 'TG Manage'
  },
  { immediate: true },
)

const openGithub = () => {
  window.open('https://github.com/hikling/TG-Manage', '_blank', 'noopener,noreferrer')
}

const handleNavClick = () => {
  isMobileMenuOpen.value = false
}
</script>

<template>
  <div class="panel-shell flex min-h-screen w-full overflow-x-hidden font-sans" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <!-- 移动端遮罩：点击关闭侧栏 -->
    <div
      v-if="isMobileMenuOpen"
      class="fixed inset-0 bg-gray-900/40 dark:bg-black/60 backdrop-blur-sm z-40 lg:hidden"
      aria-hidden="true"
      @click="isMobileMenuOpen = false"
    />

    <aside 
      class="ui-sidebar fixed inset-y-0 left-0 z-50 flex flex-col transition-[width,transform] duration-200 ease-in-out w-64"
      :class="isMobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'"
      :aria-hidden="sidebarHidden ? 'true' : undefined"
      :inert="sidebarHidden || undefined"
    >
      <div class="sidebar-brand flex items-center h-16 px-4 gap-2">
        <img :src="'/favicon.svg'" alt="" class="ui-brand-logo w-7 h-7 shrink-0" />
        <div class="sidebar-label min-w-0 flex-1">
          <div class="font-semibold text-gray-900 dark:text-gray-100 text-sm leading-none">TG Manage</div>
        </div>
        <button type="button" class="sidebar-collapse-toggle hidden lg:inline-flex" :aria-label="sidebarCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')" :title="sidebarCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')" :aria-expanded="!sidebarCollapsed" @click="toggleSidebar">
          <PanelLeftOpen v-if="sidebarCollapsed" class="w-4 h-4" /><PanelLeftClose v-else class="w-4 h-4" />
        </button>
        <!-- 仅移动端抽屉显示关闭；提高可点区域与层级 -->
        <button
          ref="drawerCloseButtonRef"
          type="button"
          class="lg:hidden shrink-0 inline-flex items-center justify-center w-11 h-11 rounded-md text-gray-500 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-white/[0.06] relative z-[60]"
          :aria-label="t('common.close')"
          @click.stop="isMobileMenuOpen = false"
        >
          <X class="w-5 h-5" stroke-width="2" />
        </button>
      </div>

      <nav class="flex-1 py-5 flex flex-col gap-1 px-3 overflow-y-auto custom-scrollbar" :aria-label="t('nav.mainNav')">
        <router-link 
          v-for="nav in navigation" 
          :key="nav.id"
          :to="{ name: nav.name }"
          class="sidebar-link flex items-center h-11 px-2.5 whitespace-nowrap rounded-xl"
          :class="[{ 'ui-nav-active': route.name === nav.name }, `sidebar-link--${nav.color}`]"
          :aria-current="route.name === nav.name ? 'page' : undefined"
          :title="t(nav.labelKey)"
          :aria-label="t(nav.labelKey)"
          @click="handleNavClick"
          @mouseenter="prefetchView(nav.name)"
          @focus="prefetchView(nav.name)"
          @pointerdown="prefetchView(nav.name)"
        >
          <span class="sidebar-link-icon"><component :is="nav.icon" class="w-[19px] h-[19px]" stroke-width="1.9" /></span>
          <span class="sidebar-label ml-3 text-sm font-medium">{{ nav.labelKey.startsWith('nav.') ? t(nav.labelKey) : nav.labelKey }}</span>
        </router-link>
      </nav>

      <div class="border-t border-[var(--tg-border)] p-3">
        <button
          type="button"
          class="sidebar-link flex items-center w-full h-11 px-2.5 whitespace-nowrap rounded-xl"
          :title="t('appearance.title')"
          :aria-label="t('appearance.title')"
          @click="showAppearanceModal = true; isMobileMenuOpen = false"
        >
          <span class="sidebar-link-icon"><Palette class="w-[19px] h-[19px]" stroke-width="1.9" aria-hidden="true" /></span>
          <span class="sidebar-label ml-3 text-sm font-medium">{{ t('appearance.title') }}</span>
        </button>
        <button
          type="button"
          class="sidebar-link flex items-center w-full h-11 px-2.5 whitespace-nowrap rounded-xl"
          :title="t('nav.profile')"
          :aria-label="t('nav.profile')"
          @click="showProfileModal = true; isMobileMenuOpen = false"
        >
          <span class="sidebar-link-icon"><UserCircle class="w-[19px] h-[19px]" stroke-width="1.9" /></span>
          <span class="sidebar-label ml-3 text-sm font-medium">{{ t('nav.profile') }}</span>
        </button>
      </div>
    </aside>

    <main class="panel-main flex-1 w-full pl-0 lg:pl-64 flex flex-col min-h-screen transition-[padding] duration-200 max-w-[100vw]">
      <header class="ui-header-glass sticky top-0 z-30 h-14 flex items-center justify-between px-4 lg:px-8 shrink-0">
        <div class="flex items-center gap-3 min-w-0">
          <button
            ref="menuButtonRef"
            type="button"
            class="ui-icon-btn lg:hidden"
            :aria-label="t('nav.openMenu')"
            :aria-expanded="isMobileMenuOpen"
            @click="isMobileMenuOpen = true"
          >
            <Menu class="w-5 h-5" />
          </button>
          <div class="min-w-0">
            <h1 class="text-base sm:text-lg font-medium text-gray-900 dark:text-gray-100 tracking-wide truncate">{{ currentTitle }}</h1>
          </div>
        </div>
        <div class="flex items-center gap-1 sm:gap-1.5">
          <button
            type="button"
            class="ui-icon-btn"
            :title="t('common.github')"
            :aria-label="t('common.github')"
            @click="openGithub"
          >
            <Github class="w-4 h-4" />
          </button>
          <button
            type="button"
            class="ui-icon-btn"
            :title="locale === 'zh' ? t('language.switchToEn') : t('language.switchToZh')"
            :aria-label="t('common.changeLanguage')"
            @click="toggleLanguage"
          >
            <Globe class="w-4 h-4" />
          </button>
          <button
            type="button"
            class="ui-icon-btn"
            :title="isDark ? t('common.lightMode') : t('common.darkMode')"
            :aria-label="isDark ? t('common.lightMode') : t('common.darkMode')"
            @click="toggleTheme($event)"
          >
            <Moon v-if="!isDark" class="w-4 h-4" />
            <Sun v-else class="w-4 h-4" />
          </button>
        </div>
      </header>

      <!-- 避免 overflow-x-hidden 破坏子元素 sticky；用 clip 裁切即可 -->
      <div class="panel-content flex-1 px-4 lg:px-8 py-6 pb-12 overflow-x-clip">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </div>

      <UserProfileModal :isOpen="showProfileModal" @close="showProfileModal = false" />
      <Modal :isOpen="showAppearanceModal" :title="t('appearance.title')" maxWidthClass="max-w-lg" @close="showAppearanceModal = false">
        <div class="appearance-picker">
          <p>{{ t('appearance.description') }}</p>
          <div class="appearance-preset-grid" role="group" :aria-label="t('appearance.presets')">
            <button v-for="preset in ACCENT_PRESETS" :key="preset.color" type="button" class="appearance-preset" :aria-pressed="accentColor === preset.color" @click="handleAccentChange(preset.color)">
              <span class="appearance-swatch" :style="{ backgroundColor: preset.color }" aria-hidden="true" />{{ t(preset.nameKey) }}
            </button>
          </div>
          <label class="appearance-custom-label" for="accent-custom-color">{{ t('appearance.customColor') }}</label>
          <div class="appearance-custom-control"><input id="accent-custom-color" type="color" :value="accentColor" @input="handleAccentChange(($event.target as HTMLInputElement).value)" /><code>{{ accentColor.toUpperCase() }}</code></div>
          <div class="appearance-cover-control">
            <h3 class="text-sm font-medium">{{ t('appearance.coverTitle') }}</h3>
            <p class="text-xs">{{ t('appearance.coverDescription') }}</p>
            <input ref="heroInput" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" tabindex="-1" :aria-label="t('appearance.chooseCover')" @change="onHeroSelected" />
            <div v-if="heroPreviewUrl" ref="heroPreview" class="appearance-cover-preview" :class="{ 'appearance-cover-preview--dragging': heroDragging }" :aria-label="t('appearance.coverPreviewPosition', { x: heroPositionX, y: heroPositionY })" role="group" tabindex="0" aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown" :aria-busy="heroBusy" @keydown="moveHeroWithKeyboard" @pointerdown="startHeroDrag" @pointermove="moveHeroDrag" @pointerup="stopHeroDrag" @pointercancel="stopHeroDrag">
              <HeroCover :src="heroPreviewUrl" :position-x="heroPositionX" :position-y="heroPositionY" @geometry="heroFrame = $event" />
              <span>{{ t('appearance.coverPreviewHint') }}</span>
            </div>
            <div v-if="heroPreviewUrl" class="appearance-cover-position">
              <label>{{ t('appearance.horizontalPosition') }} <input v-model.number="heroPositionX" type="range" min="0" max="100" step="1" :disabled="heroBusy" :aria-label="t('appearance.horizontalPosition')" @input="persistHeroPosition" @change="flushHeroPositionSave" /><output>{{ heroPositionX }}%</output></label>
              <label>{{ t('appearance.verticalPosition') }} <input v-model.number="heroPositionY" type="range" min="0" max="100" step="1" :disabled="heroBusy" :aria-label="t('appearance.verticalPosition')" @input="persistHeroPosition" @change="flushHeroPositionSave" /><output>{{ heroPositionY }}%</output></label>
            </div>
            <div class="flex flex-wrap gap-2">
              <button type="button" class="ui-btn-secondary min-h-11 inline-flex items-center gap-2" :disabled="heroBusy" :aria-describedby="heroFeedback ? 'hero-cover-feedback' : undefined" @click="heroInput?.click()"><ImagePlus :size="16" aria-hidden="true" />{{ heroPresent ? t('appearance.replaceCover') : t('appearance.uploadCover') }}</button>
              <button v-if="heroPresent" type="button" class="ui-btn-secondary min-h-11 inline-flex items-center gap-2" :disabled="heroBusy" :aria-describedby="heroFeedback ? 'hero-cover-feedback' : undefined" @click="resetHeroImage"><RotateCcw :size="16" aria-hidden="true" />{{ t('appearance.resetCover') }}</button>
            </div>
            <p v-if="heroFeedback" id="hero-cover-feedback" class="text-xs" :class="heroFeedbackIsError ? 'panel-error' : 'text-[var(--tg-text-muted)]'" :role="heroFeedbackIsError ? 'alert' : 'status'" aria-live="polite">{{ heroFeedback }}</p>
          </div>
        </div>
      </Modal>
    </main>
  </div>
</template>

<style>
::view-transition-old(root),
::view-transition-new(root) {
  animation: none;
  mix-blend-mode: normal;
}
</style>
<style scoped>
.fade-enter-active {
  transition: opacity 0.12s ease-out, transform 0.12s cubic-bezier(0.16, 1, 0.3, 1);
  will-change: opacity, transform;
}
.fade-leave-active {
  transition: opacity 0.08s ease-in, transform 0.08s ease-in;
  will-change: opacity, transform;
}
.fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.fade-leave-to {
  opacity: 0;
  transform: translateY(-2px);
}
@media (prefers-reduced-motion: reduce) {
  .fade-enter-active,
  .fade-leave-active {
    transition: opacity 0.01ms;
    will-change: auto;
  }
  .fade-enter-from,
  .fade-leave-to {
    transform: none;
  }
}
</style>
