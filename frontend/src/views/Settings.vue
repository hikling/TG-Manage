<script setup lang="ts">
import GeneralSettings from '../components/settings/GeneralSettings.vue'
import BotNotifySettings from '../components/settings/BotNotifySettings.vue'
import DataManagementSettings from '../components/settings/DataManagementSettings.vue'
import AboutSettings from '../components/settings/AboutSettings.vue'
import PageRetry from '../components/PageRetry.vue'
import { useSettingsPage } from '../composables/useSettingsPage'

const {
  t,
  settings,
  timezoneOptions,
  loading,
  dataLoading,
  backupLoading,
  backupStatus,
  runtimeStatus,
  memoryStats,
  advancedLoading,
  botTestLoading,
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
  keepaliveLoading,
  saveAllLoading,
  webdavTestLoading,
  webdavListLoading,
  remoteWebdavFiles,
  remoteWebdavMessage,
  webdavPasswordSet,
  botTokenSet,
  remoteDownloadName,
  saveSettings,
  runKeepaliveNow,
  saveBotSettings,
  saveAdvancedSettings,
  saveAllSettings,
  testBot,
  handleExport,
  handleImportFile,
  handleBackupExport,
  handleWebdavTest,
  handleListRemoteBackups,
  handleDownloadRemoteBackup,
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
        :disabled="saveAllLoading || loading || botLoading || advancedLoading"
        @click="saveAllSettings"
      >
        {{ saveAllLoading ? t('common.saving') : t('settings.saveAll') }}
      </button>
    </div>
    <div v-if="pageLoading" class="grid grid-cols-1 lg:grid-cols-2 gap-6" aria-busy="true">
      <div v-for="i in 4" :key="i" class="ui-card p-6 space-y-4">
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
          <summary>通用设置 <span>时区、运行与基础配置</span></summary>
          <GeneralSettings
            v-model="settings"
            :timezone-options="timezoneOptions"
            :loading="loading"
            :keepalive-loading="keepaliveLoading"
            @save="saveSettings"
            @run-keepalive="runKeepaliveNow"
          />
        </details>
        <details class="settings-accordion">
          <summary>数据管理 <span>导出、恢复与远程备份</span></summary>
          <DataManagementSettings
            v-model="settings"
            :webdav-password-set="webdavPasswordSet"
            :backup-status="backupStatus"
            :remote-files="remoteWebdavFiles"
            :remote-message="remoteWebdavMessage"
            :remote-download-name="remoteDownloadName"
            :data-loading="dataLoading"
            :backup-loading="backupLoading"
            :webdav-test-loading="webdavTestLoading"
            :webdav-list-loading="webdavListLoading"
            :advanced-loading="advancedLoading"
            @export-json="handleExport"
            @import-json="handleImportFile"
            @backup-export="handleBackupExport"
            @webdav-test="handleWebdavTest"
            @webdav-list="handleListRemoteBackups"
            @webdav-download="handleDownloadRemoteBackup"
            @save-advanced="saveAdvancedSettings"
          />
        </details>

        <details class="settings-accordion">
          <summary>机器人通知 <span>通知配置与连通性测试</span></summary>
          <BotNotifySettings
            v-model="settings"
            :bot-token-set="botTokenSet"
            :reveal="{ botToken: revealSecrets.botToken }"
            :bot-loading="botLoading"
            :bot-test-loading="botTestLoading"
            @save="saveBotSettings"
            @test="testBot"
            @toggle-reveal="toggleReveal"
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
