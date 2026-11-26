<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { RefreshCw, ShieldCheck, Smartphone, Trash2 } from 'lucide-vue-next'
import Modal from '../Modal.vue'
import { listAccountDevices, terminateAccountDevice, type AccountDeviceInfo } from '../../lib/api'
import { getAuthToken } from '../../lib/api/core'
import { useI18n } from '../../composables/useI18n'
import { useConfirm } from '../../composables/useConfirm'
import { formatDateTime } from '../../lib/datetime'
import { useLatestResponseGuard } from '../../lib/latest-response'
import { getLocalizedErrorMessage } from '../../lib/types'

const props = defineProps<{
  isOpen: boolean
  accountName: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const { t, locale } = useI18n()
const { confirm } = useConfirm()
const devices = ref<AccountDeviceInfo[]>([])
const loading = ref(false)
const error = ref('')
const terminatingHash = ref('')
const devicesGuard = useLatestResponseGuard()

const title = computed(() => `${t('accounts.devices')} · ${props.accountName || ''}`)

const formatDate = (value?: string | null) => formatDateTime(value, locale.value === 'en' ? 'en-US' : 'zh-CN')

const deviceTitle = (device: AccountDeviceInfo) => {
  return [device.device_model, device.platform].filter(Boolean).join(' · ') || t('accounts.unknownDevice')
}

const deviceSubtitle = (device: AccountDeviceInfo) => {
  return [device.app_name, device.app_version, device.system_version].filter(Boolean).join(' · ') || '-'
}

const locationText = (device: AccountDeviceInfo) => {
  return [device.country, device.region, device.ip].filter(Boolean).join(' · ') || '-'
}

const loadDevices = async () => {
  const targetAccount = props.accountName
  if (!props.isOpen || !targetAccount) return
  const token = getAuthToken()
  if (!token) return
  const seq = devicesGuard.next()
  loading.value = true
  error.value = ''
  try {
    const res = await listAccountDevices(token, targetAccount)
    if (!devicesGuard.isCurrent(seq) || !props.isOpen || props.accountName !== targetAccount) return
    devices.value = res.devices || []
  } catch (e: unknown) {
    if (!devicesGuard.isCurrent(seq) || !props.isOpen || props.accountName !== targetAccount) return
    error.value = getLocalizedErrorMessage(e, t, t('accounts.devicesLoadFailed'))
  } finally {
    if (devicesGuard.isCurrent(seq)) loading.value = false
  }
}

const terminateDevice = async (device: AccountDeviceInfo) => {
  if (device.current) return
  const targetAccount = props.accountName
  const ok = await confirm({
    title: t('accounts.terminateDevice'),
    message: t('accounts.terminateDeviceConfirm'),
    confirmText: t('accounts.terminateDevice'),
    danger: true,
  })
  if (!ok || !props.isOpen || props.accountName !== targetAccount) return
  const token = getAuthToken()
  if (!token) return
  terminatingHash.value = device.hash
  error.value = ''
  try {
    await terminateAccountDevice(token, targetAccount, device.hash)
    if (!props.isOpen || props.accountName !== targetAccount) return
    await loadDevices()
  } catch (e: unknown) {
    if (props.isOpen && props.accountName === targetAccount) {
      error.value = getLocalizedErrorMessage(e, t, t('accounts.terminateDeviceFailed'))
    }
  } finally {
    terminatingHash.value = ''
  }
}

watch(() => props.isOpen, (open) => {
  if (open) {
    void loadDevices()
  } else {
    devicesGuard.invalidate()
    devices.value = []
    error.value = ''
    loading.value = false
  }
})

onUnmounted(() => {
  devicesGuard.invalidate()
})
</script>

<template>
  <Modal :isOpen="isOpen" :title="title" maxWidthClass="max-w-3xl" @close="emit('close')">
    <template #header-extra>
      <span class="text-[11px] text-gray-500">{{ devices.length }} {{ t('accounts.deviceCount') }}</span>
    </template>

    <div class="space-y-4">
      <div class="flex items-start justify-between gap-3">
        <p class="text-xs text-gray-500 leading-relaxed">
          {{ t('accounts.devicesHint') }}
        </p>
        <button
          type="button"
          class="ui-btn-secondary shrink-0 !px-3 !py-1.5 !text-xs"
          :disabled="loading"
          @click="loadDevices"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
          {{ t('accounts.refreshDevices') }}
        </button>
      </div>

      <div v-if="error" class="ui-alert-error" role="alert">
        {{ error }}
      </div>

      <div v-if="loading && devices.length === 0" class="ui-page-loading !py-10">
        <div class="ui-spinner" />
      </div>

      <div v-else-if="devices.length === 0" class="ui-empty !py-10">
        <p class="ui-empty-desc">{{ t('accounts.noDevices') }}</p>
      </div>

      <div v-else class="space-y-2.5">
        <div
          v-for="device in devices"
          :key="device.hash"
          class="ui-card !rounded-xl p-4"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0 flex items-start gap-3">
              <div class="mt-0.5 w-9 h-9 rounded-xl shrink-0 border border-[var(--tg-border)] bg-[var(--tg-bg-elevated-2)] flex items-center justify-center text-[var(--tg-text-muted)]">
                <ShieldCheck v-if="device.current" class="w-4 h-4 text-emerald-500" />
                <Smartphone v-else class="w-4 h-4" />
              </div>
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <div class="text-sm font-semibold text-[var(--tg-text)] truncate">
                    {{ deviceTitle(device) }}
                  </div>
                  <span v-if="device.current" class="ui-badge ui-badge-success !text-[10px]">
                    <span class="ui-badge-dot" />
                    {{ t('accounts.currentDevice') }}
                  </span>
                  <span v-if="device.official_app" class="ui-badge !text-[10px] bg-[var(--tg-accent-soft)] text-[var(--tg-accent-text)] border-[var(--tg-accent-border)]">
                    {{ t('accounts.officialApp') }}
                  </span>
                </div>
                <div class="text-xs text-[var(--tg-text-muted)] mt-1 truncate">{{ deviceSubtitle(device) }}</div>
                <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-3 text-[11px] text-[var(--tg-text-muted)]">
                  <div><span class="opacity-70">{{ t('accounts.lastActive') }}：</span>{{ formatDate(device.date_active) }}</div>
                  <div><span class="opacity-70">{{ t('accounts.createdAt') }}：</span>{{ formatDate(device.date_created) }}</div>
                  <div class="truncate" :title="locationText(device)"><span class="opacity-70">{{ t('accounts.location') }}：</span>{{ locationText(device) }}</div>
                </div>
              </div>
            </div>

            <button
              v-if="!device.current"
              @click="terminateDevice(device)"
              :disabled="terminatingHash === device.hash || loading"
              class="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 disabled:opacity-50 transition-colors"
            >
              <RefreshCw v-if="terminatingHash === device.hash" class="w-3.5 h-3.5 animate-spin" />
              <Trash2 v-else class="w-3.5 h-3.5" />
              {{ t('accounts.terminateDevice') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>
