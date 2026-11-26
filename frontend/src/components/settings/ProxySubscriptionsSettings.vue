<script setup lang="ts">
import { computed, ref } from 'vue'
import { Eye, EyeOff } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import { formatDateTime } from '../../lib/datetime'
import type { ProxySubscriptionSettings, SubscriptionSourceStatus } from '../../lib/api/settings'

export interface SubscriptionDraft {
  primaryUrl: string
  fallbackUrl: string
  clearPrimary: boolean
  clearFallback: boolean
  latencyThresholdMs: number | ''
}

const props = defineProps<{
  modelValue: SubscriptionDraft
  status: ProxySubscriptionSettings | null
  loading?: boolean
  refreshing?: boolean
  error?: string
  dirty?: boolean
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: SubscriptionDraft): void
  (e: 'save'): void
  (e: 'refresh'): void
  (e: 'retry'): void
}>()
const { t, locale } = useI18n()
const visible = ref({ primary: false, fallback: false })

function update(changes: Partial<SubscriptionDraft>) {
  emit('update:modelValue', { ...props.modelValue, ...changes })
}
function sourceStatus(source: SubscriptionSourceStatus | undefined) {
  if (!source?.configured) return t('settings.subscriptions.statuses.unconfigured')
  const code = source.status
  if (['healthy', 'ready', 'degraded', 'error', 'pending', 'refreshing', 'disabled'].includes(code)) {
    return t(`settings.subscriptions.statuses.${code}`)
  }
  if (code.startsWith('SUBSCRIPTION_') || code.startsWith('XRAY_')) {
    return t('settings.subscriptions.statuses.error')
  }
  return t('settings.subscriptions.statuses.unknown')
}
function refreshedAt(source: SubscriptionSourceStatus | undefined) {
  const value = source?.last_refreshed_at
  if (!value || Number.isNaN(Date.parse(value))) return t('settings.subscriptions.neverRefreshed')
  return formatDateTime(value, locale.value === 'en' ? 'en-US' : 'zh-CN')
}
function displayCount(value: number | undefined) {
  return Number.isFinite(value) ? value : '—'
}
function sourceLabel(source: SubscriptionSourceStatus) {
  return source.label && !['主订阅', '兜底订阅'].includes(source.label) ? source.label : null
}
const routeMode = computed(() => {
  const mode = props.status?.route_mode
  if (mode === 'primary' || mode === 'fallback' || mode === 'direct' || mode === 'setup_required' || mode === 'mixed') {
    return t(`settings.subscriptions.routeModes.${mode}`)
  }
  return t('settings.subscriptions.routeModes.unknown')
})
</script>

<template>
  <div class="ui-card p-5 sm:p-6 space-y-5">
    <p class="text-sm text-[var(--tg-text-muted)] leading-relaxed">{{ t('settings.subscriptions.description') }}</p>
    <div v-if="error" role="alert" class="ui-alert-error flex flex-wrap items-center justify-between gap-2">
      <span>{{ error }}</span><button type="button" class="ui-btn-secondary" @click="emit('retry')">{{ t('common.retry') }}</button>
    </div>
    <template v-if="status">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div v-for="kind in (['primary', 'fallback'] as const)" :key="kind" class="min-w-0 rounded-2xl border border-[var(--tg-border)] bg-[var(--tg-bg-elevated-2)] p-4 sm:p-5">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="font-bold text-sm text-[var(--tg-text)]">{{ t(`settings.subscriptions.${kind}`) }}</h3>
            <span class="rounded-full border border-[var(--tg-border)] bg-[var(--tg-bg-elevated)] px-2.5 py-0.5 text-xs font-semibold text-[var(--tg-text-muted)]">{{ sourceStatus(status[kind]) }}</span>
          </div>
          <p v-if="sourceLabel(status[kind])" class="mt-1 text-xs text-[var(--tg-text-muted)]">{{ sourceLabel(status[kind]) }}</p>
          <label class="ui-label mt-4 block" :for="`subscription-${kind}`">{{ t('settings.subscriptions.url') }}</label>
          <div class="relative mt-1.5">
            <input
              :id="`subscription-${kind}`"
              :value="kind === 'primary' ? modelValue.primaryUrl : modelValue.fallbackUrl"
              :type="visible[kind] ? 'text' : 'password'"
              :placeholder="status[kind].configured ? t('settings.subscriptions.replacePlaceholder') : 'https://…'"
              autocomplete="off"
              spellcheck="false"
              class="ui-input !pr-11"
              :disabled="loading || (kind === 'primary' ? modelValue.clearPrimary : modelValue.clearFallback)"
              @input="update(kind === 'primary' ? { primaryUrl: ($event.target as HTMLInputElement).value } : { fallbackUrl: ($event.target as HTMLInputElement).value })"
            >
            <button type="button" class="absolute right-0 top-0 h-full w-10 flex items-center justify-center text-[var(--tg-text-muted)] hover:text-[var(--tg-text)]" :aria-label="visible[kind] ? t('settings.hideSecret') : t('settings.showSecret')" :aria-pressed="visible[kind]" @click="visible[kind] = !visible[kind]"><EyeOff v-if="visible[kind]" class="w-4 h-4" /><Eye v-else class="w-4 h-4" /></button>
          </div>
          <label class="mt-3 flex items-center gap-2 text-xs text-[var(--tg-text-muted)] cursor-pointer">
            <input type="checkbox" class="ui-checkbox" :checked="kind === 'primary' ? modelValue.clearPrimary : modelValue.clearFallback" :disabled="loading" @change="update(kind === 'primary' ? { clearPrimary: ($event.target as HTMLInputElement).checked, primaryUrl: '' } : { clearFallback: ($event.target as HTMLInputElement).checked, fallbackUrl: '' })">
            {{ t('settings.subscriptions.disable') }}
          </label>
          <dl class="mt-4 grid grid-cols-3 overflow-hidden rounded-xl border border-[var(--tg-border)] bg-[var(--tg-bg-elevated)]">
            <div class="min-w-0 px-3 py-3 sm:px-4">
              <dt class="min-h-8 text-[11px] leading-4 text-[var(--tg-text-muted)]">{{ t('settings.subscriptions.imported') }}</dt>
              <dd class="mt-1 text-xl font-bold leading-6 tabular-nums text-[var(--tg-text)]">{{ displayCount(status[kind].imported_count) }}</dd>
            </div>
            <div class="min-w-0 border-l border-[var(--tg-border)] px-3 py-3 sm:px-4">
              <dt class="min-h-8 text-[11px] leading-4 text-[var(--tg-text-muted)]">{{ t('settings.subscriptions.usable') }}</dt>
              <dd class="mt-1 text-xl font-bold leading-6 tabular-nums text-[var(--tg-accent-text)]">{{ displayCount(status[kind].usable_count) }}</dd>
            </div>
            <div class="min-w-0 border-l border-[var(--tg-border)] px-3 py-3 sm:px-4">
              <dt class="min-h-8 text-[11px] leading-4 text-[var(--tg-text-muted)]">{{ t('settings.subscriptions.unsupported') }}</dt>
              <dd class="mt-1 text-xl font-bold leading-6 tabular-nums text-[var(--tg-text)]">{{ displayCount(status[kind].unsupported_count) }}</dd>
            </div>
          </dl>
          <p class="mt-3 text-xs text-[var(--tg-text-muted)]">{{ t('settings.subscriptions.lastRefreshed') }}: <span class="font-mono">{{ refreshedAt(status[kind]) }}</span></p>
        </div>
      </div>
      <p class="text-xs leading-5 text-[var(--tg-text-muted)]">{{ t('settings.subscriptions.unavailableHint') }}</p>
      <div class="flex flex-wrap items-end gap-4">
        <div class="space-y-1.5">
          <label class="ui-label" for="subscription-latency">{{ t('settings.subscriptions.threshold') }}</label>
          <input id="subscription-latency" type="number" min="100" max="10000" step="50" class="ui-input w-36 font-mono" :value="modelValue.latencyThresholdMs" :disabled="loading" @input="update({ latencyThresholdMs: ($event.target as HTMLInputElement).value === '' ? '' : Number(($event.target as HTMLInputElement).value) })">
        </div>
        <p class="text-xs text-[var(--tg-text-muted)] pb-2">{{ t('settings.subscriptions.thresholdHint') }}</p>
      </div>
      <p class="text-sm text-[var(--tg-text)]" role="status">{{ t('settings.subscriptions.currentRoute') }}: <strong class="font-semibold text-[var(--tg-accent-text)]">{{ routeMode }}</strong></p>
      <p v-if="status.route_mode === 'direct'" class="text-sm text-amber-700 dark:text-amber-300">{{ t('settings.subscriptions.directWarning') }}</p>
      <p v-if="status.route_mode === 'setup_required'" class="text-sm text-amber-700 dark:text-amber-300">{{ t('settings.subscriptions.setupWarning') }}</p>
      <div class="flex flex-wrap gap-2.5">
        <button type="button" class="ui-btn-primary" :disabled="loading || refreshing || !dirty" @click="emit('save')">{{ loading ? t('common.saving') : t('settings.subscriptions.save') }}</button>
        <button type="button" class="ui-btn-secondary" :disabled="loading || refreshing || dirty" @click="emit('refresh')">{{ refreshing ? t('settings.subscriptions.refreshing') : t('settings.subscriptions.refresh') }}</button>
      </div>
    </template>
  </div>
</template>
