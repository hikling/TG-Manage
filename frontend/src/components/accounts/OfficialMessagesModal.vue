<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Copy, RefreshCw, ShieldCheck } from 'lucide-vue-next'
import Modal from '../Modal.vue'
import { listAccountOfficialMessages, type OfficialMessageInfo } from '../../lib/api'
import { getAuthToken } from '../../lib/api/core'
import { useI18n } from '../../composables/useI18n'
import { useToast } from '../../composables/useToast'
import { copyToClipboard } from '../../lib/clipboard'
import { formatDateTime } from '../../lib/datetime'

const props = defineProps<{
  isOpen: boolean
  accountName: string
}>()

const emit = defineEmits<{
  close: []
}>()

const { t } = useI18n()
const toast = useToast()
const loading = ref(false)
const error = ref('')
const messages = ref<OfficialMessageInfo[]>([])

const extractLoginCode = (text?: string | null): string => {
  if (!text) return ''
  const match = text.match(/(?:code[:\s]+|验证码[：:\s]*)(\d{5,6})\b/i) || text.match(/\b(\d{5,6})\b/)
  return match?.[1] ?? ''
}

const copyLoginCode = async (code: string) => {
  const ok = await copyToClipboard(code)
  if (ok) toast.success(t('common.copied'))
  else toast.error(t('common.copyFailed'))
}

const title = computed(() => `${t('accounts.officialMessages')} · ${props.accountName || '-'}`)

const formatTime = (value?: string | null) => formatDateTime(value)

const loadMessages = async () => {
  const token = getAuthToken()
  if (!token || !props.accountName) return

  loading.value = true
  error.value = ''
  try {
    const res = await listAccountOfficialMessages(token, props.accountName, 20)
    messages.value = res.messages || []
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : t('accounts.officialMessagesFailed')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      loadMessages()
    } else {
      // 关闭时清空数据：换账号重开不应闪现上一账号的消息（与 DeviceManagerModal 对齐）
      messages.value = []
      error.value = ''
    }
  }
)
</script>

<template>
  <Modal :isOpen="isOpen" :title="title" @close="emit('close')">
    <div class="space-y-4">
      <div class="flex items-start justify-between gap-3 p-3.5 rounded-xl bg-[var(--tg-accent-soft)] border border-[var(--tg-accent-border)]">
        <div class="flex items-start gap-2.5 min-w-0">
          <ShieldCheck class="w-4 h-4 text-[var(--tg-accent-text)] mt-0.5 shrink-0" />
          <div class="text-xs text-[var(--tg-accent-text)] leading-relaxed">
            <div class="font-semibold">{{ t('accounts.officialMessagesHintTitle') }}</div>
            <div class="mt-0.5 opacity-90">{{ t('accounts.officialMessagesHint') }}</div>
          </div>
        </div>
        <button
          type="button"
          class="ui-btn-secondary !min-h-[32px] !px-2.5 !py-1 !text-xs shrink-0"
          :disabled="loading"
          @click="loadMessages"
        >
          <RefreshCw class="w-3 h-3" :class="loading ? 'animate-spin' : ''" />
          {{ t('common.refresh') }}
        </button>
      </div>

      <div v-if="error" class="ui-alert-error" role="alert">
        {{ error }}
      </div>

      <div v-if="loading && !messages.length" class="ui-page-loading !py-10">
        <div class="ui-spinner" />
      </div>

      <div v-else-if="!messages.length" class="ui-empty !py-10">
        <p class="ui-empty-desc">{{ t('accounts.noOfficialMessages') }}</p>
      </div>

      <div v-else class="max-h-[60vh] overflow-auto space-y-2.5 pr-1">
        <div
          v-for="message in messages"
          :key="message.id || `${message.date}-${message.text}`"
          class="chat-official-message"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center justify-between gap-3 mb-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-xs font-semibold text-[var(--tg-text)]">Telegram · 777000</span>
                <button
                  v-if="extractLoginCode(message.text)"
                  type="button"
                  class="chat-code-pill"
                  :title="t('common.copy')"
                  @click="copyLoginCode(extractLoginCode(message.text))"
                >
                  {{ extractLoginCode(message.text) }}
                  <Copy class="w-3 h-3" aria-hidden="true" />
                </button>
              </div>
              <span class="text-[11px] font-mono text-[var(--tg-text-muted)] shrink-0">{{ formatTime(message.date) }}</span>
            </div>
            <pre class="whitespace-pre-wrap break-words text-sm leading-relaxed text-[var(--tg-text)] font-sans">{{ message.text || t('accounts.emptyMessage') }}</pre>
          </div>
        </div>
      </div>
    </div>
  </Modal>
</template>
