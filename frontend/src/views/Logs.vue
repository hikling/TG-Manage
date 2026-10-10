<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { errorText } from '../composables/usePanelAccount'
import { panelRequest } from '../lib/api/communications'
import { listTeleBoxAccounts, type TeleBoxAccount } from '../lib/api/telebox'
import { useI18n } from '../composables/useI18n'

type Entry = { time: string; level: string; message: string }
const accounts = ref<TeleBoxAccount[]>([])
const selected = ref('')
const logs = ref<Entry[]>([])
const error = ref('')
const loading = ref(false)
const { t, locale } = useI18n()
watch(locale, () => { error.value = '' })
let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0
let active = true
let inFlight = false
let selectionReload = false
let choosingDefault = false

async function load() {
  if (!active || inFlight) return
  if (timer) clearTimeout(timer)
  timer = undefined
  inFlight = true
  const current = generation
  loading.value = true
  try {
    const overview = await listTeleBoxAccounts()
    if (!active || current !== generation) return
    accounts.value = overview.accounts
    if (!accounts.value.some(item => item.account === selected.value)) {
      choosingDefault = true
      selected.value = accounts.value[0]?.account || ''
      choosingDefault = false
    }
    const items = selected.value ? (await panelRequest<{ items: Entry[] }>(`/telebox/${encodeURIComponent(selected.value)}/logs`)).items : []
    if (!active || current !== generation) return
    logs.value = items.slice().reverse()
    error.value = ''
  } catch (cause) { if (active && current === generation) error.value = errorText(cause) }
  finally {
    inFlight = false
    if (active) {
      loading.value = false
      if (selectionReload) {
        selectionReload = false
        void load()
      } else {
        timer = setTimeout(() => void load(), 5000)
      }
    }
  }
}
watch(selected, () => {
  if (choosingDefault) return
  ++generation
  logs.value = []
  if (inFlight) selectionReload = true
  else void load()
}, { flush: 'sync' })
onMounted(() => { void load() })
onUnmounted(() => { active = false; ++generation; if (timer) clearTimeout(timer) })
</script>

<template>
  <div class="panel-stack"><section class="panel-card"><div class="panel-row"><div class="flex-1"><h2 class="panel-title">{{ t('logs.runtimeTitle') }}</h2><p class="panel-muted">{{ t('logs.runtimeDescription') }}</p></div><button class="panel-button" :disabled="loading" @click="load"><RefreshCw :size="17" />{{ t('common.refresh') }}</button></div></section>
    <p v-if="error" class="panel-error" role="alert">{{ error }}</p>
    <section class="panel-card panel-stack"><h3>{{ t('logs.teleboxTitle') }}</h3><label>{{ t('logs.accountLabel') }}<select v-model="selected" class="panel-input mt-2"><option v-if="!accounts.length" value="">{{ t('logs.noAccounts') }}</option><option v-for="item in accounts" :key="item.account" :value="item.account">{{ item.account }} · {{ item.status }}</option></select></label><p v-if="!logs.length" class="panel-empty">{{ t('logs.noTeleboxLogs') }}</p><div class="max-h-[550px] overflow-y-auto panel-stack"><p v-for="(entry, index) in logs" :key="index" class="text-sm break-words border-b border-[var(--tg-border)] pb-2"><time class="panel-muted">{{ new Date(entry.time).toLocaleString(locale === 'en' ? 'en-US' : 'zh-CN') }}</time> · <span :class="entry.level === 'error' ? 'text-rose-600' : ''">{{ entry.message }}</span></p></div></section>
  </div>
</template>
