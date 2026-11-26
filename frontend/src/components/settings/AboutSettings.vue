<script setup lang="ts">
/**
 * 关于 / 版本信息区块：版本号、Git SHA、构建时间、Python 运行时、运行状态、更新检查。
 * 父组件 Settings.vue 持有版本数据并实现检查更新逻辑；本组件仅负责展示与触发刷新。
 */
import { computed } from 'vue'
import { Info, RefreshCw, ExternalLink } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import type { AppVersionInfo, RuntimeStatus, MemoryStatsResponse } from '../../lib/api'
import { formatMemoryRssFromStats } from '../../lib/memory-format'
import { formatDateTime } from '../../lib/datetime'

type VersionBannerKind = 'update' | 'latest' | 'error' | 'info'
interface VersionBanner {
  kind: VersionBannerKind
  text: string
  url?: string | null
}

const props = defineProps<{
  appVersion: AppVersionInfo | null
  runtimeStatus: RuntimeStatus | null
  memoryStats: MemoryStatsResponse | null
  versionBanner: VersionBanner | null
  versionLoading?: boolean
  checkLoading?: boolean
}>()

const emit = defineEmits<{
  (e: 'check-update'): void
}>()

const { t } = useI18n()

const shortSha = (sha?: string) => {
  if (!sha) return t('settings.unknownValue')
  return sha.length > 12 ? sha.slice(0, 12) : sha
}

const formatMemoryRss = () => {
  return formatMemoryRssFromStats(
    props.memoryStats?.stats,
    t('settings.unknownValue'),
  )
}

const formatUptime = (seconds?: number) => {
  if (seconds === undefined || seconds === null || seconds < 0) return t('settings.unknownValue')
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(seconds / 3600)
  const remMinutes = minutes % 60
  if (hours < 24) return `${hours}h ${remMinutes}m`
  const days = Math.floor(seconds / 86400)
  const remHours = hours % 24
  return `${days}d ${remHours}h`
}

const memoryHealthText = computed(() => {
  if (!props.memoryStats?.available) return t('settings.unknownValue')
  if (props.memoryStats.stats?.in_alert) return t('settings.memoryInAlert')
  return props.memoryStats.stats?.gc_enabled ? t('settings.gcActive') : t('settings.gcInactive')
})
</script>

<template>
  <section class="ui-card p-5 sm:p-6">
    <div class="mb-5 border-b border-[var(--tg-border)] pb-4 flex items-center justify-between gap-3">
      <div class="flex items-start gap-3 min-w-0">
        <span class="ui-section-icon" aria-hidden="true"><Info class="w-4 h-4" /></span>
        <div class="min-w-0">
          <h2 class="text-base font-bold tracking-tight text-[var(--tg-text)]">{{ t('settings.aboutTitle') }}</h2>
          <p class="text-xs text-[var(--tg-text-muted)] mt-0.5">{{ t('settings.aboutDesc') }}</p>
        </div>
      </div>
      <button
        type="button"
        class="ui-btn-secondary shrink-0 !px-3.5 !py-1.5 !text-xs inline-flex items-center gap-1.5"
        :disabled="checkLoading || versionLoading || !appVersion"
        @click="emit('check-update')"
      >
        <RefreshCw class="w-3.5 h-3.5" :class="checkLoading ? 'animate-spin' : ''" />
        {{ checkLoading ? t('settings.checkingUpdate') : t('settings.checkUpdate') }}
      </button>
    </div>

    <div class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- 版本与构建信息 (7项) -->
        <div v-if="appVersion" class="about-telemetry-panel">
          <div class="about-telemetry-head">{{ t('settings.versionBuildTitle') }}</div>
          <div class="about-telemetry-rows">
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.appName') }}</span>
              <span class="about-telemetry-val font-semibold">{{ appVersion.app_name || 'TG Manage' }}</span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.currentVersion') }}</span>
              <span class="about-telemetry-val font-mono px-2 py-0.5 rounded-md bg-[var(--tg-accent-soft)] text-[var(--tg-accent-text)] font-semibold">v{{ appVersion.version }}</span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.osPlatform') }}</span>
              <span class="about-telemetry-val font-mono">{{ appVersion.os_platform || t('settings.unknownValue') }}</span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.gitSha') }}</span>
              <span class="about-telemetry-val font-mono">{{ shortSha(appVersion.git_sha) }}</span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.gitBranch') }}</span>
              <span class="about-telemetry-val font-mono">{{ appVersion.git_branch || t('settings.unknownValue') }}</span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.buildTime') }}</span>
              <span class="about-telemetry-val font-mono">{{ appVersion.build_time ? formatDateTime(appVersion.build_time) : t('settings.unknownValue') }}</span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.pythonRuntime') }}</span>
              <span class="about-telemetry-val font-mono">{{ appVersion.python }}</span>
            </div>
          </div>
        </div>
        <p v-else-if="versionLoading" class="text-xs text-[var(--tg-text-muted)]">{{ t('common.processing') }}</p>

        <!-- 运行状态 (7项) -->
        <div v-if="runtimeStatus" class="about-telemetry-panel">
          <div class="about-telemetry-head">{{ t('settings.runtimeStatus') }}</div>
          <div class="about-telemetry-rows">
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.serviceStatus') }}</span>
              <span class="about-telemetry-val">
                <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold" :class="runtimeStatus.ready ? 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300' : 'bg-amber-500/12 text-amber-700 dark:text-amber-300'">
                  <span class="w-1.5 h-1.5 rounded-full" :class="runtimeStatus.ready ? 'bg-emerald-500' : 'bg-amber-500'"></span>
                  {{ runtimeStatus.ready ? t('settings.serviceReady') : t('settings.serviceNotReady') }}
                </span>
              </span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.uptime') }}</span>
              <span class="about-telemetry-val font-mono">{{ formatUptime(runtimeStatus.uptime_seconds) }}</span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.schedulerRole') }}</span>
              <span class="about-telemetry-val font-medium" :class="runtimeStatus.scheduler_lock_held ? 'text-emerald-600 dark:text-emerald-400' : 'text-[var(--tg-accent-text)]'">
                {{ runtimeStatus.scheduler_lock_held ? t('settings.rolePrimary') : t('settings.roleReplica') }}
              </span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.schedulerLock') }}</span>
              <span class="about-telemetry-val" :class="runtimeStatus.scheduler_lock_held ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'">
                {{ runtimeStatus.scheduler_lock_held ? t('settings.lockHeld') : t('settings.lockNotHeld') }}
              </span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.dbLabel') }}</span>
              <span class="about-telemetry-val">
                <span>{{ runtimeStatus.database_is_sqlite ? t('settings.dbSqlite') : t('settings.dbExternal') }}</span>
                <span v-if="runtimeStatus.monitor_shard"> · {{ t('settings.monitorShard', { shard: runtimeStatus.monitor_shard }) }}</span>
                <span v-if="runtimeStatus.monitor_allowlist" class="text-[11px] text-[var(--tg-text-muted)]"> ({{ runtimeStatus.monitor_allowlist }})</span>
              </span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.memoryRss') }}</span>
              <span class="about-telemetry-val flex items-center justify-end gap-1.5 flex-wrap">
                <span class="font-mono font-semibold" :class="memoryStats?.stats?.in_alert ? 'text-rose-600 dark:text-rose-400' : 'text-[var(--tg-text)]'">
                  {{ formatMemoryRss() }}
                </span>
                <span v-if="memoryStats?.stats?.threshold_mb" class="text-[11px] text-[var(--tg-text-muted)] font-mono">
                  ({{ t('settings.memoryThreshold') }} {{ memoryStats.stats.threshold_mb }} MB)
                </span>
                <span v-if="memoryStats?.stats?.in_alert" class="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/15 text-rose-600 dark:text-rose-400">
                  {{ t('common.warning') }}
                </span>
              </span>
            </div>
            <div class="about-telemetry-row">
              <span class="about-telemetry-key">{{ t('settings.memoryHealth') }}</span>
              <span class="about-telemetry-val" :class="memoryStats?.stats?.in_alert ? 'text-rose-600 dark:text-rose-400 font-semibold' : 'text-emerald-600 dark:text-emerald-400 font-medium'">
                {{ memoryHealthText }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="versionBanner"
        class="text-xs rounded-xl px-4 py-3 border"
        :class="{
          'border-[var(--tg-accent-border)] bg-[var(--tg-accent-soft)] text-[var(--tg-accent-text)]': versionBanner.kind === 'update' || versionBanner.kind === 'info',
          'border-emerald-300/60 bg-emerald-50/90 text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/12 dark:text-emerald-200': versionBanner.kind === 'latest',
          'border-amber-300/60 bg-amber-50/90 text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/12 dark:text-amber-200': versionBanner.kind === 'error',
        }"
      >
        <div class="font-semibold">{{ versionBanner.text }}</div>
        <p v-if="versionBanner.kind === 'update'" class="mt-1 opacity-90">{{ t('settings.updateAvailableHint') }}</p>
        <a
          v-if="versionBanner.url"
          :href="versionBanner.url"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1 mt-1.5 font-semibold underline hover:no-underline"
        >
          {{ t('settings.openRelease') }}
          <ExternalLink class="w-3 h-3" />
        </a>
      </div>
    </div>
  </section>
</template>
