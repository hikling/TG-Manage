<script setup lang="ts">
/**
 * 通用设置区块：日志保留、数据目录、并发、账户检测说明、时区。
 * 父组件 Settings.vue 持有表单状态，本组件通过 v-model 双向同步并触发保存事件。
 */
import { Settings2 } from 'lucide-vue-next'
import CustomSelect from '../CustomSelect.vue'
import { useI18n } from '../../composables/useI18n'
import { parseNumberInputValue, type SettingsFormState } from '../../lib/settings-form'

interface TimezoneOption {
  label: string
  value: string
}

const props = defineProps<{
  /** 表单状态（v-model） */
  modelValue: SettingsFormState
  /** 时区选项列表 */
  timezoneOptions: TimezoneOption[]
  /** 主保存中 */
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: SettingsFormState): void
  (e: 'save'): void
}>()

const { t } = useI18n()

type NumberInputKey = 'logDays' | 'concurrency'

/** 字段级更新：浅拷贝并覆盖单个字段，保证父组件 ref 收到新对象引用 */
const update = <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => {
  emit('update:modelValue', { ...props.modelValue, [key]: value } as SettingsFormState)
}

const onNumberInput = (key: NumberInputKey, e: Event) => {
  const value = (e.target as HTMLInputElement).value
  update(key, parseNumberInputValue(value))
}

const onStringInput = (key: keyof SettingsFormState, e: Event) => {
  update(key, (e.target as HTMLInputElement).value as never)
}
</script>

<template>
  <section class="ui-card p-5 sm:p-6">
    <div class="mb-5 border-b border-[var(--tg-border)] pb-3.5 flex items-center justify-between gap-3">
      <div class="flex items-start gap-3 min-w-0">
        <span class="ui-section-icon" aria-hidden="true"><Settings2 class="w-4 h-4" /></span>
        <div class="min-w-0">
          <h2 class="text-sm font-bold text-[var(--tg-text)]">{{ t('settings.general') }}</h2>
          <p class="text-xs text-[var(--tg-text-muted)] mt-0.5">{{ t('settings.generalDesc') }}</p>
        </div>
      </div>
      <span v-if="loading" class="text-xs text-[var(--tg-text-muted)] shrink-0">{{ t('common.saving') }}</span>
    </div>
    <div class="space-y-4">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="space-y-1.5">
          <label class="ui-label" for="settings-log-retention">{{ t('settings.logRetention') }}</label>
          <input id="settings-log-retention" :value="modelValue.logDays" @input="onNumberInput('logDays', $event)" type="number" :placeholder="t('settings.logRetentionPlaceholder')" class="ui-input">
          <p class="text-xs text-[var(--tg-text-muted)]">{{ t('settings.logRetentionHint') }}</p>
        </div>
        <div class="space-y-1.5">
          <label class="ui-label" for="settings-concurrency">{{ t('settings.concurrency') }}</label>
          <input id="settings-concurrency" :value="modelValue.concurrency" @input="onNumberInput('concurrency', $event)" type="number" min="1" max="10" :placeholder="t('settings.concurrencyPlaceholder')" class="ui-input">
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="space-y-1.5">
          <label class="ui-label" for="settings-data-dir">{{ t('settings.dataDir') }}</label>
          <input id="settings-data-dir" :value="modelValue.dataDir" @input="onStringInput('dataDir', $event)" type="text" placeholder="/data" class="ui-input font-mono">
        </div>
        <div class="space-y-1.5">
          <label class="ui-label">{{ t('settings.timezone') }}</label>
          <CustomSelect
            :modelValue="modelValue.timezone"
            :aria-label="t('settings.timezone')"
            @update:modelValue="update('timezone', String($event ?? ''))"
            :options="timezoneOptions"
            className="w-full"
          />
        </div>
      </div>
      <div class="p-3.5 rounded-xl bg-[var(--tg-bg-elevated-2)] border border-[var(--tg-border)]">
        <h3 class="text-xs font-semibold text-[var(--tg-text)]">{{ t('settings.deviceKeepalive') }}</h3>
        <p class="text-xs text-[var(--tg-text-muted)] mt-1 leading-relaxed">{{ t('settings.deviceKeepaliveDesc') }}</p>
      </div>
      <div class="pt-1 flex justify-end">
        <button type="button" class="ui-btn-primary w-full sm:w-auto sm:min-w-[160px] py-2.5" :disabled="loading" @click="emit('save')">{{ loading ? t('common.saving') : t('settings.saveGeneral') }}</button>
      </div>
    </div>
  </section>
</template>
