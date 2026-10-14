<script setup lang="ts">
import { computed } from 'vue'
import type { AccountInfo } from '../../lib/api/accounts'
import { useI18n } from '../../composables/useI18n'
import { formatDateTime } from '../../lib/datetime'

const props = defineProps<{
  account: Pick<AccountInfo, 'proxy' | 'proxy_status' | 'proxy_checked_at'>
}>()
const { t, locale } = useI18n()
// Missing saved health means pending, never infer success from account login.
const status = computed(() => {
  if (!props.account.proxy?.trim()) return 'unconfigured'
  return props.account.proxy_status === 'healthy' || props.account.proxy_status === 'error'
    ? props.account.proxy_status : 'pending'
})
const hint = computed(() => {
  const message = t(`accounts.proxyStatusHints.${status.value}`)
  const checked = props.account.proxy_checked_at
  if (!['healthy', 'error'].includes(status.value) || !checked || Number.isNaN(Date.parse(checked))) return message
  return `${message} ${t('accounts.proxyLastChecked', { time: formatDateTime(checked, locale.value === 'en' ? 'en-US' : 'zh-CN') })}`
})
</script>

<template>
  <div class="account-proxy-signal">
    <span class="account-signal-label">{{ t('accounts.proxyStatusLabel') }}</span>
    <span
      class="account-tile-status"
      :class="{
        'account-tile-status--active': status === 'healthy',
        'account-tile-status--error': status === 'error',
      }"
      :title="hint"
    >
      <span class="account-status-dot" aria-hidden="true" />
      {{ t(`accounts.proxyStatuses.${status}`) }}
    </span>
  </div>
</template>
