<script setup lang="ts">
import { AlertTriangle } from 'lucide-vue-next'
import { useConfirm } from '../composables/useConfirm'
import { useI18n } from '../composables/useI18n'
import Modal from './Modal.vue'

const { state, accept, cancel } = useConfirm()
const { t } = useI18n()
</script>

<template>
  <Modal
    :isOpen="state.open"
    :title="state.title"
    maxWidthClass="max-w-sm"
    zIndexClass="z-[150]"
    @close="cancel"
  >
    <div class="flex gap-3.5 items-start">
      <div
        v-if="state.danger"
        class="shrink-0 w-10 h-10 rounded-xl flex items-center justify-center border border-rose-200/80 dark:border-rose-800/50 bg-rose-50 dark:bg-rose-500/12 text-rose-600 dark:text-rose-400"
        aria-hidden="true"
      >
        <AlertTriangle class="w-4 h-4" />
      </div>
      <p class="text-sm text-[var(--tg-text-muted)] leading-relaxed whitespace-pre-wrap break-words pt-0.5">
        {{ state.message }}
      </p>
    </div>

    <template #footer>
      <button
        type="button"
        class="ui-btn-secondary !border-transparent !bg-transparent !px-4 !py-2"
        @click="cancel"
      >
        {{ state.cancelText || t('common.cancel') }}
      </button>
      <button
        type="button"
        class="!px-4 !py-2"
        :class="state.danger ? 'ui-btn-danger' : 'ui-btn-primary'"
        @click="accept"
      >
        {{ state.confirmText || t('common.confirm') }}
      </button>
    </template>
  </Modal>
</template>
