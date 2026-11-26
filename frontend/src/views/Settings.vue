<script setup lang="ts">
import { computed, ref } from 'vue'
import { Bot, Globe, Info, Settings2 } from 'lucide-vue-next'
import GeneralSettings from '../components/settings/GeneralSettings.vue'
import BotNotifySettings from '../components/settings/BotNotifySettings.vue'
import ProxySubscriptionsSettings from '../components/settings/ProxySubscriptionsSettings.vue'
import AboutSettings from '../components/settings/AboutSettings.vue'
import PageRetry from '../components/PageRetry.vue'
import { useSettingsPage } from '../composables/useSettingsPage'

type SettingsTab = 'general' | 'bot' | 'subscriptions' | 'about'

const activeTab = ref<SettingsTab>('general')

const {
  t,
  settings,
  timezoneOptions,
  loading,
  runtimeStatus,
  memoryStats,
  subscriptions,
  subscriptionDraft,
  subscriptionDirty,
  subscriptionError,
  subscriptionLoading,
  subscriptionRefreshing,
  loadSubscriptions,
  saveSubscriptions,
  refreshSubscriptions,
  botConnectionLoading,
  pageLoading,
  loadFailed,
  revealSecrets,
  isDirty,
  dirtyLabels,
  appVersion,
  versionLoading,
  checkLoading,
  versionBanner,
  botLoading,
  saveAllLoading,
  botTokenSet,
  botCodeStatus,
  saveSettings,
  saveBotSettings,
  saveAllSettings,
  testBotConnection,
  handleCheckUpdate,
  toggleReveal,
  reload: reloadData,
} = useSettingsPage()

const navItems = computed(() => [
  {
    id: 'general' as const,
    icon: Settings2,
    tone: 'cobalt',
    title: t('settings.general'),
    summary: t('settings.generalSummary'),
    dirty: dirtyLabels.value.includes(t('settings.general')),
  },
  {
    id: 'bot' as const,
    icon: Bot,
    tone: 'violet',
    title: t('settings.botNotify'),
    summary: t('settings.botNotifySummary'),
    dirty: dirtyLabels.value.includes(t('settings.botNotify')),
  },
  {
    id: 'subscriptions' as const,
    icon: Globe,
    tone: 'teal',
    title: t('settings.subscriptions.title'),
    summary: t('settings.subscriptions.summary'),
    dirty: subscriptionDirty.value,
  },
  {
    id: 'about' as const,
    icon: Info,
    tone: 'amber',
    title: t('settings.aboutTitle'),
    summary: appVersion.value?.version ? `v${appVersion.value.version}` : t('settings.aboutDesc'),
    dirty: false,
  },
])
</script>

<template>
  <div class="max-w-7xl pb-10">
    <div
      v-if="isDirty && !pageLoading"
      class="sticky top-[4.25rem] z-20 mb-4 flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-xs rounded-xl border border-amber-300/70 dark:border-amber-600/50 bg-amber-50/95 dark:bg-amber-950/90 backdrop-blur-md text-amber-900 dark:text-amber-200 shadow-[var(--tg-shadow-md)]"
      role="status"
    >
      <div class="min-w-0">
        <div class="font-semibold">{{ t('settings.unsavedBanner') }}</div>
        <div v-if="dirtyLabels.length" class="mt-0.5 text-[11px] opacity-85">
          {{ t('settings.dirtySections') }}: {{ dirtyLabels.join(' · ') }}
        </div>
      </div>
      <button
        type="button"
        class="ui-btn-primary !px-3.5 !py-1.5 !text-xs shrink-0"
        :disabled="saveAllLoading || loading || botLoading || subscriptionLoading || subscriptionRefreshing"
        @click="saveAllSettings"
      >
        {{ saveAllLoading ? t('common.saving') : t('settings.saveAll') }}
      </button>
    </div>

    <div v-if="pageLoading" class="settings-studio" aria-busy="true">
      <div class="settings-nav-skeleton ui-card p-3 space-y-2">
        <div v-for="i in 4" :key="i" class="ui-skeleton h-14 w-full" />
      </div>
      <div class="ui-card p-6 space-y-4">
        <div class="ui-skeleton h-5 w-36" />
        <div class="ui-skeleton h-3 w-56" />
        <div class="ui-skeleton h-10 w-full" />
        <div class="ui-skeleton h-10 w-full" />
        <div class="ui-skeleton h-10 w-2/3" />
      </div>
    </div>

    <!-- 加载失败：错误态 + 重试，而非渲染默认空表单 -->
    <div v-else-if="loadFailed" class="max-w-xl mx-auto my-12">
      <PageRetry @retry="reloadData" />
    </div>

    <!-- Re-Architected 2-Column Settings Studio -->
    <div v-else class="settings-studio">
      <nav class="settings-nav" :aria-label="t('nav.settings')">
        <button
          v-for="item in navItems"
          :key="item.id"
          type="button"
          class="settings-nav-item"
          :class="[`settings-nav-item--${item.tone}`, { 'is-active': activeTab === item.id }]"
          :aria-current="activeTab === item.id ? 'page' : undefined"
          @click="activeTab = item.id"
        >
          <span class="settings-nav-icon" aria-hidden="true">
            <component :is="item.icon" class="w-4 h-4" />
          </span>
          <span class="settings-nav-copy">
            <span class="settings-nav-title-row">
              <strong>{{ item.title }}</strong>
              <span v-if="item.dirty" class="settings-nav-dirty" :title="t('settings.unsavedTitle')" aria-hidden="true" />
            </span>
            <span class="settings-nav-summary">{{ item.summary }}</span>
          </span>
        </button>
      </nav>

      <div class="settings-stage">
        <div v-show="activeTab === 'general'">
          <GeneralSettings
            v-model="settings"
            :timezone-options="timezoneOptions"
            :loading="loading"
            @save="saveSettings"
          />
        </div>

        <div v-show="activeTab === 'bot'">
          <BotNotifySettings
            v-model="settings"
            :bot-token-set="botTokenSet"
            :code-status="botCodeStatus"
            :reveal="{ botToken: revealSecrets.botToken }"
            :bot-loading="botLoading"
            :bot-connection-loading="botConnectionLoading"
            @save="saveBotSettings"
            @test-connection="testBotConnection"
            @toggle-reveal="toggleReveal"
          />
        </div>

        <div v-show="activeTab === 'subscriptions'">
          <ProxySubscriptionsSettings
            v-model="subscriptionDraft"
            :status="subscriptions"
            :loading="subscriptionLoading"
            :refreshing="subscriptionRefreshing"
            :error="subscriptionError"
            :dirty="subscriptionDirty"
            @save="saveSubscriptions"
            @refresh="refreshSubscriptions"
            @retry="loadSubscriptions"
          />
        </div>

        <div v-show="activeTab === 'about'">
          <AboutSettings
            :app-version="appVersion"
            :runtime-status="runtimeStatus"
            :memory-stats="memoryStats"
            :version-banner="versionBanner"
            :version-loading="versionLoading"
            :check-loading="checkLoading"
            @check-update="handleCheckUpdate(true)"
          />
        </div>
      </div>
    </div>
  </div>
</template>
