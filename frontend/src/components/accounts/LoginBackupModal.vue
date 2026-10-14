<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Download, Upload, ShieldCheck } from 'lucide-vue-next'
import Modal from '../Modal.vue'
import { exportAccountLoginBackup, importAccountLoginBackup } from '../../lib/api/accounts'
import { getAuthToken } from '../../lib/api/core'
import { downloadBlob } from '../../lib/download'
import { getLocalizedErrorMessage } from '../../lib/types'
import { useI18n } from '../../composables/useI18n'
import { useToast } from '../../composables/useToast'

const props = defineProps<{ isOpen: boolean; initialMode?: 'export' | 'import' }>()
const emit = defineEmits<{ close: []; restored: [] }>()
const { t } = useI18n()
const toast = useToast()
const mode = ref<'export' | 'import'>('export')
const password = ref('')
const confirmation = ref('')
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const busy = ref(false)
const error = ref<unknown>(null)
const localErrorKey = ref('')

const errorText = computed(() => localErrorKey.value
  ? t(localErrorKey.value)
  : error.value
    ? getLocalizedErrorMessage(error.value, t, t(mode.value === 'export'
    ? 'accounts.loginBackupExportFailed'
    : 'accounts.loginBackupImportFailed'))
    : '')

function clearSensitiveFields() {
  password.value = ''
  confirmation.value = ''
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
  error.value = null
  localErrorKey.value = ''
}

function selectMode(next: 'export' | 'import') {
  if (busy.value || mode.value === next) return
  clearSensitiveFields()
  mode.value = next
}

function onFileChange(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  error.value = null
  localErrorKey.value = ''
}

function close() {
  if (busy.value) return
  clearSensitiveFields()
  emit('close')
}

function backupFilename(): string {
  const date = new Date()
  const stamp = [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('')
  return `telegram-login-backup-${stamp}.tglogin`
}

async function submit() {
  if (busy.value) return
  const token = getAuthToken()
  if (!token) return
  if (password.value.length < 12) {
    localErrorKey.value = 'accounts.loginBackupPasswordShort'
    return
  }
  if (mode.value === 'export' && password.value !== confirmation.value) {
    localErrorKey.value = 'accounts.loginBackupPasswordMismatch'
    return
  }
  if (mode.value === 'import' && !file.value) {
    localErrorKey.value = 'accounts.loginBackupFileRequired'
    return
  }

  busy.value = true
  error.value = null
  localErrorKey.value = ''
  try {
    if (mode.value === 'export') {
      const blob = await exportAccountLoginBackup(token, password.value)
      downloadBlob(blob, backupFilename())
      toast.success(t('accounts.loginBackupExportSuccess'))
      clearSensitiveFields()
    } else if (file.value) {
      const result = await importAccountLoginBackup(token, file.value, password.value)
      toast.success(t('accounts.loginBackupImportSuccess', {
        restored: result.restored,
        skipped: result.skipped,
      }))
      clearSensitiveFields()
      emit('restored')
      emit('close')
    }
  } catch (cause: unknown) {
    error.value = cause
  } finally {
    busy.value = false
  }
}

watch(() => props.isOpen, open => {
  if (open) mode.value = props.initialMode ?? 'export'
  else if (!busy.value) clearSensitiveFields()
})
</script>

<template>
  <Modal :isOpen="isOpen" :title="t('accounts.loginBackupTitle')" maxWidthClass="max-w-lg" @close="close">
    <div class="space-y-4">
      <div class="flex gap-2" role="group" :aria-label="t('accounts.loginBackupTitle')">
        <button type="button" class="ui-btn-secondary flex-1 justify-center !text-xs" :class="mode === 'export' ? '!border-sky-500 !text-sky-600 dark:!text-sky-300' : ''" :aria-pressed="mode === 'export'" :disabled="busy" @click="selectMode('export')">
          <Download class="w-4 h-4" /> {{ t('accounts.loginBackupExport') }}
        </button>
        <button type="button" class="ui-btn-secondary flex-1 justify-center !text-xs" :class="mode === 'import' ? '!border-sky-500 !text-sky-600 dark:!text-sky-300' : ''" :aria-pressed="mode === 'import'" :disabled="busy" @click="selectMode('import')">
          <Upload class="w-4 h-4" /> {{ t('accounts.loginBackupImport') }}
        </button>
      </div>

      <div class="flex gap-2.5 rounded-md bg-sky-50 dark:bg-sky-500/10 border border-sky-100 dark:border-sky-800/40 p-3 text-xs leading-relaxed text-sky-800 dark:text-sky-200">
        <ShieldCheck class="w-4 h-4 shrink-0 mt-0.5" />
        <p>{{ t('accounts.loginBackupScope') }}</p>
      </div>
      <p v-if="mode === 'import'" class="text-xs leading-relaxed text-amber-800 dark:text-amber-300" role="note">
        {{ t('accounts.loginBackupMigrationWarning') }}
      </p>
      <p v-else class="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
        {{ t('accounts.loginBackupSecurityHint') }}
      </p>

      <form class="space-y-3" @submit.prevent="submit">
        <div v-if="mode === 'import'">
          <label for="account-login-backup-file" class="block text-xs font-medium mb-1.5">{{ t('accounts.loginBackupFile') }}</label>
          <input id="account-login-backup-file" ref="fileInput" type="file" accept=".tglogin" required class="ui-input !text-xs" :disabled="busy" @change="onFileChange">
        </div>
        <div>
          <label for="account-login-backup-password" class="block text-xs font-medium mb-1.5">{{ t('accounts.loginBackupPassword') }}</label>
          <input id="account-login-backup-password" v-model="password" type="password" autocomplete="new-password" minlength="12" required class="ui-input" :disabled="busy" :placeholder="t('accounts.loginBackupPasswordHint')">
        </div>
        <div v-if="mode === 'export'">
          <label for="account-login-backup-confirmation" class="block text-xs font-medium mb-1.5">{{ t('accounts.loginBackupConfirmPassword') }}</label>
          <input id="account-login-backup-confirmation" v-model="confirmation" type="password" autocomplete="new-password" minlength="12" required class="ui-input" :disabled="busy">
        </div>
        <div v-if="errorText" class="ui-alert-error" role="alert">{{ errorText }}</div>
        <div class="flex justify-end gap-2 pt-1">
          <button type="button" class="ui-btn-secondary" :disabled="busy" @click="close">{{ t('common.cancel') }}</button>
          <button type="submit" class="ui-btn-primary" :disabled="busy">
            <span v-if="busy" class="ui-spinner !w-4 !h-4 !border-2" />
            {{ t(mode === 'export' ? 'accounts.loginBackupDownload' : 'accounts.loginBackupRestore') }}
          </button>
        </div>
      </form>
    </div>
  </Modal>
</template>
