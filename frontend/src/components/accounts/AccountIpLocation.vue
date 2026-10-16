<script setup lang="ts">
import { computed } from 'vue'
import type { AccountInfo } from '../../lib/api/accounts'
import { useI18n } from '../../composables/useI18n'
import { formatDateTime } from '../../lib/datetime'

const props = defineProps<{ account: AccountInfo }>()
const { t, locale } = useI18n()

const source = computed(() => {
  const mode = props.account.route_mode
  return mode === 'primary' || mode === 'fallback' || mode === 'direct' || mode === 'setup_required'
    ? t(`accounts.ipLocation.sources.${mode}`)
    : t('accounts.ipLocation.sources.unknown')
})
const location = computed(() => {
  if (props.account.exit_lookup_status === 'failed') return t('accounts.ipLocation.failedLocation')
  if (!props.account.exit_ip || !props.account.exit_checked_at) {
    return t('accounts.ipLocation.unknown')
  }
  return props.account.exit_country || t('accounts.ipLocation.unknown')
})
const address = computed(() => props.account.exit_ip && props.account.exit_checked_at
  ? props.account.exit_ip : t(props.account.exit_lookup_status === 'failed' ? 'accounts.ipLocation.failedIp' : 'accounts.ipLocation.pendingIp'))
const details = computed(() => {
  const parts = [source.value]
  if (props.account.node_label) parts.push(props.account.node_label)
  if (props.account.exit_lookup_status === 'failed') parts.push(t('accounts.ipLocation.failedHint'))
  if (props.account.latency_ms != null) parts.push(t('accounts.ipLocation.latency', { ms: props.account.latency_ms }))
  const checked = props.account.exit_checked_at
  if (checked && !Number.isNaN(Date.parse(checked))) {
    parts.push(t('accounts.ipLocation.checkedAt', { time: formatDateTime(checked, locale.value === 'en' ? 'en-US' : 'zh-CN') }))
  }
  return parts.join(' · ')
})
</script>

<template>
  <div class="account-ip-signal" :title="details">
    <div class="account-ip-heading">
      <span class="account-signal-label">{{ t('accounts.ipLocation.label') }}</span>
      <span class="account-ip-route">{{ source }}</span>
    </div>
    <span class="account-tile-status" :class="{
      'account-tile-status--active': account.route_status === 'healthy' && !!account.exit_ip && !!account.exit_country && account.exit_lookup_status !== 'failed',
      'account-tile-status--error': account.route_status === 'error' || account.route_status === 'unavailable' || account.exit_lookup_status === 'failed',
    }">
      <span class="account-status-dot" aria-hidden="true" />{{ location }}
    </span>
    <span class="account-ip-address">{{ address }}</span>
    <span v-if="account.shared_node" class="account-ip-shared">{{ t('accounts.ipLocation.shared') }}</span>
  </div>
</template>
