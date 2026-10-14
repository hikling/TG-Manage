<script setup lang="ts">
import { ref, watch } from 'vue'
import { Eye, EyeOff } from 'lucide-vue-next'
import Modal from '../Modal.vue'
import { updateAccount } from '../../lib/api'
import { getAuthToken } from '../../lib/api/core'
import { useI18n } from '../../composables/useI18n'
import { useToast } from '../../composables/useToast'
import type { AccountUiItem } from '../../lib/types'
import { getLocalizedErrorMessage } from '../../lib/types'

const { t } = useI18n()
const toast = useToast()

const props = defineProps<{
  isOpen: boolean
  account: AccountUiItem
}>()

const emit = defineEmits<{ (e: 'close'): void, (e: 'success'): void, (e: 'relogin', name: string): void }>()

const form = ref({
  new_account_name: '',
  remark: '',
  proxy: ''
})
const loading = ref(false)
const error = ref('')
const revealProxy = ref(false)

watch(() => props.isOpen, (val) => {
  if (val && props.account) {
    form.value = {
      new_account_name: props.account.name || '',
      remark: props.account.remark || '',
      proxy: props.account.raw.proxy || ''
    }
    error.value = ''
    revealProxy.value = false
  }
}, { immediate: true })

const handleSave = async () => {
  const token = getAuthToken()
  if (!token || !props.account || loading.value) return

  loading.value = true
  error.value = ''
  try {
    await updateAccount(token, props.account.name, {
      new_account_name: form.value.new_account_name || null,
      remark: form.value.remark || null,
      proxy: form.value.proxy.trim()
    })
    toast.success(t('editAccount.saveSuccess'))
    emit('success')
    emit('close')
  } catch (e: unknown) {
    error.value = getLocalizedErrorMessage(e, t, t('editAccount.saveFailed'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <Modal :isOpen="isOpen" @close="$emit('close')" :title="t('editAccount.title')">
    <div class="space-y-4">
      <div v-if="error" class="ui-alert-error" role="alert">
        {{ error }}
      </div>

      <div class="space-y-1.5">
        <label class="ui-label" for="edit-account-name">{{ t('editAccount.nameLabel') }}</label>
        <input 
          id="edit-account-name"
          v-model="form.new_account_name"
          type="text" 
          :placeholder="t('editAccount.namePlaceholder')"
          class="ui-input"
        >
      </div>

      <div class="space-y-1.5">
        <label class="ui-label" for="edit-account-remark">{{ t('editAccount.remarkLabel') }}</label>
        <input 
          id="edit-account-remark"
          v-model="form.remark"
          type="text" 
          :placeholder="t('editAccount.remarkPlaceholder')"
          class="ui-input"
        >
      </div>

      <div class="space-y-1.5">
        <label class="ui-label" for="edit-account-proxy">{{ t('editAccount.proxyLabel') }}</label>
        <div class="relative">
          <input
            id="edit-account-proxy"
            v-model="form.proxy"
            :type="revealProxy ? 'text' : 'password'"
            autocomplete="off"
            spellcheck="false"
            placeholder="socks5://..."
            aria-describedby="edit-account-proxy-hint"
            class="ui-input !pr-12"
          >
          <button
            type="button"
            class="absolute right-0 top-0 h-full w-11 flex items-center justify-center text-gray-500 hover:text-gray-900 dark:hover:text-gray-100"
            :aria-label="revealProxy ? t('settings.hideSecret') : t('settings.showSecret')"
            :aria-pressed="revealProxy"
            @click="revealProxy = !revealProxy"
          ><EyeOff v-if="revealProxy" class="w-4 h-4" /><Eye v-else class="w-4 h-4" /></button>
        </div>
        <p id="edit-account-proxy-hint" class="text-xs text-gray-500">{{ t('editAccount.proxyHint') }}</p>
      </div>
    </div>

    <template #footer>
      <div class="flex-1">
        <button 
          type="button"
          class="ui-btn-danger !px-4 !py-2"
          @click="$emit('relogin', account?.name)"
        >
          {{ t('editAccount.relogin') }}
        </button>
      </div>
      <button 
        type="button"
        class="ui-btn-secondary !border-transparent !bg-transparent !px-4 !py-2"
        @click="$emit('close')"
      >
        {{ t('common.cancel') }}
      </button>
      <button 
        type="button"
        class="ui-btn-primary !px-4 !py-2"
        :disabled="loading"
        @click="handleSave"
      >
        {{ loading ? t('common.saving') : t('editAccount.saveChanges') }}
      </button>
    </template>
  </Modal>
</template>
