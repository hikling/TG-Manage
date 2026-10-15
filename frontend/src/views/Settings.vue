<script setup lang="ts">
import GeneralSettings from '../components/settings/GeneralSettings.vue'
import BotNotifySettings from '../components/settings/BotNotifySettings.vue'
import ProxySubscriptionsSettings from '../components/settings/ProxySubscriptionsSettings.vue'
import AboutSettings from '../components/settings/AboutSettings.vue'
import PageRetry from '../components/PageRetry.vue'
import { useSettingsPage } from '../composables/useSettingsPage'

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

</script>

<template>
  <div class="max-w-7xl pb-10">
    <div
      v-if="isDirty && !pageLoading"
      class="sticky top-[3.75rem] z-20 mb-4 flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs border border-amber-200 dark:border-amber-800/50 bg-amber-50/95 dark:bg-amber-950/90 backdrop-blur-xs text-amber-800 dark:text-amber-200 shadow-sm"
      role="status"
    >
      <div class="min-w-0">
        <div>{{ t('settings.unsavedBanner') }}</div>
        <div v-if="dirtyLabels.length" class="mt-0.5 text-[10px] opacity-90">
          {{ t('settings.dirtySections') }}: {{ dirtyLabels.join(' · ') }}
        </div>
      </div>
      <button
        type="button"
        class="ui-btn-primary !px-3 !py-1.5 !text-xs shrink-0"
        :disabled="saveAllLoading || loading || botLoading || subscriptionLoading || subscriptionRefreshing"
        @click="saveAllSettings"
      >
        {{ saveAllLoading ? t('common.saving') : t('settings.saveAll') }}
      </button>
    </div>
    <div v-if="pageLoading" class="grid grid-cols-1 lg:grid-cols-2 gap-6" aria-busy="true">
      <div v-for="i in 3" :key="i" class="ui-card p-6 space-y-4">
        <div class="ui-skeleton h-5 w-32" />
        <div class="ui-skeleton h-3 w-48" />
        <div class="ui-skeleton h-10 w-full" />
        <div class="ui-skeleton h-10 w-full" />
        <div class="ui-skeleton h-10 w-2/3" />
      </div>
    </div>
    <!-- 加载失败：错误态 + 重试，而非渲染默认空表单 -->
    <div v-else-if="loadFailed" class="max-w-xl mx-auto my-12">
      <PageRetry @retry="reloadData" />
    </div>
    <div v-else class="space-y-6">

      <div class="settings-accordions">
        <details class="settings-accordion">
          <summary>{{ t('settings.general') }} <span>{{ t('settings.generalSummary') }}</span></summary>
          <GeneralSettings
            v-model="settings"
            :timezone-options="timezoneOptions"
            :loading="loading"
            @save="saveSettings"
          />
        </details>
        <details class="settings-accordion">
          <summary>{{ t('settings.botNotify') }} <span>{{ t('settings.botNotifySummary') }}</span></summary>
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
        </details>
        <details class="settings-accordion">
          <summary>{{ t('settings.subscriptions.title') }} <span>{{ t('settings.subscriptions.summary') }}</span></summary>
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
        </details>
      </div>

      <!-- 关于 / 版本：始终固定在所有配置卡片的最底部 -->
      <div>
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
</template>
