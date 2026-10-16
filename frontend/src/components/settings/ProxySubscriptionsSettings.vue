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
    <p class="text-sm text-gray-600 dark:text-gray-300">{{ t('settings.subscriptions.description') }}</p>
    <div v-if="error" role="alert" class="ui-alert-error flex flex-wrap items-center justify-between gap-2">
      <span>{{ error }}</span><button type="button" class="ui-btn-secondary" @click="emit('retry')">{{ t('common.retry') }}</button>
    </div>
    <template v-if="status">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div v-for="kind in (['primary', 'fallback'] as const)" :key="kind" class="border border-gray-200 dark:border-gray-700 rounded-md p-4 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="font-semibold text-sm">{{ t(`settings.subscriptions.${kind}`) }}</h3>
            <span class="text-xs text-gray-600 dark:text-gray-300">{{ sourceStatus(status[kind]) }}</span>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400">{{ status[kind].label || t('settings.subscriptions.noLabel') }}</p>
          <label class="ui-label" :for="`subscription-${kind}`">{{ t('settings.subscriptions.url') }}</label>
          <div class="relative">
            <input
              :id="`subscription-${kind}`"
              :value="kind === 'primary' ? modelValue.primaryUrl : modelValue.fallbackUrl"
              :type="visible[kind] ? 'text' : 'password'"
              :placeholder="status[kind].configured ? t('settings.subscriptions.replacePlaceholder') : 'https://…'"
              autocomplete="off"
              spellcheck="false"
              class="ui-input !pr-12"
              :disabled="loading || (kind === 'primary' ? modelValue.clearPrimary : modelValue.clearFallback)"
              @input="update(kind === 'primary' ? { primaryUrl: ($event.target as HTMLInputElement).value } : { fallbackUrl: ($event.target as HTMLInputElement).value })"
            >
            <button type="button" class="absolute right-0 top-0 h-full w-11 flex items-center justify-center text-gray-500 hover:text-gray-900 dark:hover:text-gray-100" :aria-label="visible[kind] ? t('settings.hideSecret') : t('settings.showSecret')" :aria-pressed="visible[kind]" @click="visible[kind] = !visible[kind]"><EyeOff v-if="visible[kind]" class="w-4 h-4" /><Eye v-else class="w-4 h-4" /></button>
          </div>
          <label class="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
            <input type="checkbox" :checked="kind === 'primary' ? modelValue.clearPrimary : modelValue.clearFallback" :disabled="loading" @change="update(kind === 'primary' ? { clearPrimary: ($event.target as HTMLInputElement).checked, primaryUrl: '' } : { clearFallback: ($event.target as HTMLInputElement).checked, fallbackUrl: '' })">
            {{ t('settings.subscriptions.disable') }}
          </label>
          <dl class="grid grid-cols-2 gap-2 text-xs text-gray-500 dark:text-gray-400">
            <div><dt>{{ t('settings.subscriptions.imported') }}</dt><dd class="font-semibold text-gray-800 dark:text-gray-200">{{ status[kind].imported_count }}</dd></div>
            <div><dt>{{ t('settings.subscriptions.usable') }}</dt><dd class="font-semibold text-gray-800 dark:text-gray-200">{{ status[kind].usable_count }}</dd></div>
            <div><dt>{{ t('settings.subscriptions.unsupported') }}</dt><dd class="font-semibold text-gray-800 dark:text-gray-200">{{ status[kind].unsupported_count }}</dd></div>
          </dl>
          <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('settings.subscriptions.lastRefreshed') }}: {{ refreshedAt(status[kind]) }}</p>
        </div>
      </div>
      <div class="flex flex-wrap items-end gap-4">
        <div class="space-y-1.5">
          <label class="ui-label" for="subscription-latency">{{ t('settings.subscriptions.threshold') }}</label>
          <input id="subscription-latency" type="number" min="100" max="10000" step="50" class="ui-input w-36" :value="modelValue.latencyThresholdMs" :disabled="loading" @input="update({ latencyThresholdMs: ($event.target as HTMLInputElement).value === '' ? '' : Number(($event.target as HTMLInputElement).value) })">
        </div>
        <p class="text-xs text-gray-500 dark:text-gray-400 pb-2">{{ t('settings.subscriptions.thresholdHint') }}</p>
      </div>
      <p class="text-sm" role="status">{{ t('settings.subscriptions.currentRoute') }}: <strong>{{ routeMode }}</strong></p>
      <p v-if="status.route_mode === 'direct'" class="text-sm text-amber-700 dark:text-amber-300">{{ t('settings.subscriptions.directWarning') }}</p>
      <p v-if="status.route_mode === 'setup_required'" class="text-sm text-amber-700 dark:text-amber-300">{{ t('settings.subscriptions.setupWarning') }}</p>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="ui-btn-primary" :disabled="loading || refreshing || !dirty" @click="emit('save')">{{ loading ? t('common.saving') : t('settings.subscriptions.save') }}</button>
        <button type="button" class="ui-btn-secondary" :disabled="loading || refreshing || dirty" @click="emit('refresh')">{{ refreshing ? t('settings.subscriptions.refreshing') : t('settings.subscriptions.refresh') }}</button>
      </div>
    </template>
  </div>
</template>
