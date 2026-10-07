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
} from 'lucide-vue-next'
import { ACCENT_PRESETS, useTheme } from '../composables/useTheme'
import { useI18n } from '../composables/useI18n'
import { lockBodyScroll, unlockBodyScroll } from '../lib/body-scroll-lock'
import UserProfileModal from '../components/settings/UserProfileModal.vue'
import Modal from '../components/Modal.vue'
import { createViewPrefetcher } from '../lib/view-prefetch'
import { storageGetMigrated, storageSet } from '../lib/safe-storage'

const route = useRoute()
const { isDark, toggleTheme, accentColor, setAccentColor } = useTheme()
const { locale, toggleLanguage, t } = useI18n()
const isMobileMenuOpen = ref(false)
const showProfileModal = ref(false)
const showAppearanceModal = ref(false)
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
  sidebarCollapsed.value = storageGetMigrated('tg-manage-sidebar-collapsed', 'tg-sidebar-collapsed') !== '0'
  window.addEventListener('keydown', onKeydown)
  mobileQuery.addEventListener('change', onViewportChange)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  mobileQuery.removeEventListener('change', onViewportChange)
  if (menuScrollLocked) {
    unlockBodyScroll()
    menuScrollLocked = false
  }
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
  storageSet('tg-manage-sidebar-collapsed', sidebarCollapsed.value ? '1' : '0')
}

const navigation = computed(() => [
  { id: 'dashboard', name: 'dashboard', icon: LayoutDashboard, labelKey: 'nav.dashboard', color: 'cyan' },
  { id: 'accounts', name: 'accounts', icon: Users, labelKey: 'nav.accounts', color: 'blue' },
  { id: 'chats', name: 'chats', icon: MessagesSquare, labelKey: '聊天中心', color: 'green' },
  { id: 'logs', name: 'logs', icon: Terminal, labelKey: 'nav.logs', color: 'slate' },
  { id: 'settings', name: 'settings', icon: Settings, labelKey: 'nav.settings', color: 'teal' },
])

const currentTitle = computed(() => {
  const current = navigation.value.find(n => n.name === route.name)
  if (!current) return 'TG Manage'
  return current.labelKey.startsWith('nav.') ? t(current.labelKey) : current.labelKey
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
        <img src="/favicon.svg" alt="" class="ui-brand-logo w-7 h-7 shrink-0" />
        <div class="sidebar-label min-w-0 flex-1">
          <div class="font-semibold text-gray-900 dark:text-gray-100 text-sm leading-none">TG Manage</div>
        </div>
        <button type="button" class="sidebar-collapse-toggle hidden lg:inline-flex" :aria-label="sidebarCollapsed ? '展开侧栏' : '收起侧栏'" :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'" :aria-expanded="!sidebarCollapsed" @click="toggleSidebar">
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
        <p class="sidebar-label sidebar-section-title">WORKSPACE / 工作空间</p>
        <router-link 
          v-for="nav in navigation" 
          :key="nav.id"
          :to="{ name: nav.name }"
          class="sidebar-link flex items-center h-11 px-2.5 whitespace-nowrap rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
          :class="[{ 'ui-nav-active': route.name === nav.name }, `sidebar-link--${nav.color}`]"
          :aria-current="route.name === nav.name ? 'page' : undefined"
          :title="nav.labelKey.startsWith('nav.') ? t(nav.labelKey) : nav.labelKey"
          :aria-label="nav.labelKey.startsWith('nav.') ? t(nav.labelKey) : nav.labelKey"
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
          title="自定义主题"
          aria-label="自定义主题"
          @click="showAppearanceModal = true; isMobileMenuOpen = false"
        >
          <span class="sidebar-link-icon"><Palette class="w-[19px] h-[19px]" stroke-width="1.9" aria-hidden="true" /></span>
          <span class="sidebar-label ml-3 text-sm font-medium">自定义主题</span>
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
            <p class="header-kicker">TG MANAGE / WORKSPACE</p>
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
      <Modal :isOpen="showAppearanceModal" title="自定义主题" maxWidthClass="max-w-lg" @close="showAppearanceModal = false">
        <div class="appearance-picker">
          <p>选择一种 2026 趋势配色，或使用下方色盘。仅影响当前浏览器的界面，不改动账号数据。</p>
          <div class="appearance-preset-grid" role="group" aria-label="2026 趋势配色">
            <button v-for="preset in ACCENT_PRESETS" :key="preset.color" type="button" class="appearance-preset" :aria-pressed="accentColor === preset.color" @click="setAccentColor(preset.color)">
              <span class="appearance-swatch" :style="{ backgroundColor: preset.color }" aria-hidden="true" />{{ preset.name }}
            </button>
          </div>
          <label class="appearance-custom-label" for="accent-custom-color">自定义颜色</label>
          <div class="appearance-custom-control"><input id="accent-custom-color" type="color" :value="accentColor" @input="setAccentColor(($event.target as HTMLInputElement).value)" /><code>{{ accentColor.toUpperCase() }}</code></div>
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
