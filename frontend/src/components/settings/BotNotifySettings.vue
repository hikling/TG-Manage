<script setup lang="ts">
/**
 * Telegram Bot 通知区块：botToken / chatId / threadId / 通知开关 / 免打扰时段。
 * 父组件 Settings.vue 持有 settings 状态与 revealSecrets，通过 v-model 同步并触发保存/测试。
 */
import { Bot, Eye, EyeOff } from 'lucide-vue-next'
import { useI18n } from '../../composables/useI18n'
import type { SettingsFormState } from '../../lib/settings-form'

interface RevealSecrets {
  botToken: boolean
}

const props = defineProps<{
  /** 全局表单状态（v-model） */
  modelValue: SettingsFormState
  /** 服务端是否已保存 Bot Token */
  botTokenSet?: boolean
  /** 密钥显隐（仅 botToken） */
  reveal: Pick<RevealSecrets, 'botToken'>
  /** 保存中 */
  botLoading?: boolean
  /** 测试 Bot 中 */
  botTestLoading?: boolean
  codeStatus?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: SettingsFormState): void
  (e: 'save'): void
  (e: 'test'): void
  (e: 'toggle-reveal', key: 'botToken'): void
}>()

const { t, locale } = useI18n()
const botStatusLabel = () => {
  const status = props.codeStatus || ''
  const keys: Record<string, string> = {
    '未启用': 'disabled',
    '未启用或当前实例未取得调度锁': 'waitingLock',
    '检测到已有 Webhook；请先在该 Bot 的原管理端停用 Webhook': 'webhookActive',
    '运行中（按需查询）': 'running',
    '运行异常，请检查服务日志': 'error',
  }
  const key = keys[status]
  if (key) return t(`settings.privateBotStatus.${key}`)
  return locale.value === 'en' && /\p{Script=Han}/u.test(status) ? t('settings.privateBotStatus.error') : status
}

const update = <K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) => {
  emit('update:modelValue', { ...props.modelValue, [key]: value } as SettingsFormState)
}

const onStringInput = (key: keyof SettingsFormState, e: Event) => {
  update(key, (e.target as HTMLInputElement).value as never)
}

const onCheckbox = (key: keyof SettingsFormState, e: Event) => {
  update(key, (e.target as HTMLInputElement).checked as never)
}

const isPrivateTarget = (value: string) => {
  const trimmed = value.trim()
  return /^[1-9][0-9]{0,18}$/.test(trimmed) && BigInt(trimmed) <= 9223372036854775807n
}
</script>

<template>
  <section class="ui-card p-6">
    <div class="mb-6 border-b border-gray-200 dark:border-gray-800/60 pb-3 flex items-center justify-between gap-3">
      <div class="flex items-start gap-3 min-w-0">
        <span class="ui-section-icon" aria-hidden="true"><Bot class="w-3.5 h-3.5" /></span>
        <div class="min-w-0">
          <h2 class="text-base font-medium text-gray-900 dark:text-gray-100">{{ t('settings.botNotify') }}</h2>
          <p class="text-[10px] text-gray-500 mt-1">{{ t('settings.botDesc') }}</p>
        </div>
      </div>
      <button
        type="button"
        class="ui-switch shrink-0"
        role="switch"
        :aria-label="t('settings.botNotify')"
        :aria-checked="modelValue.botEnabled"
        :class="modelValue.botEnabled ? 'ui-switch-on' : ''"
        @click="update('botEnabled', !modelValue.botEnabled)"
      >
        <span class="ui-switch-knob" />
      </button>
    </div>

    <div class="space-y-5">
      <div class="space-y-1.5">
        <label class="ui-label" for="bot-token">{{ t('settings.botToken') }}</label>
        <div class="relative">
          <input
            id="bot-token"
            :value="modelValue.botToken"
            @input="onStringInput('botToken', $event)"
            :type="reveal.botToken ? 'text' : 'password'"
            :placeholder="botTokenSet ? t('settings.botTokenSavedHint') : '123456:ABC-DEF...'"
            class="ui-input pr-10"
          >
          <button type="button" class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" :aria-label="reveal.botToken ? t('settings.hideSecret') : t('settings.showSecret')" @click="emit('toggle-reveal', 'botToken')">
            <EyeOff v-if="reveal.botToken" class="w-4 h-4" /><Eye v-else class="w-4 h-4" />
          </button>
        </div>
      </div>
      <div class="space-y-1.5">
        <label class="ui-label" for="bot-chat-id">{{ t('settings.targetChatId') }}</label>
        <input id="bot-chat-id" :value="modelValue.botChatId" @input="onStringInput('botChatId', $event)" type="text" inputmode="numeric" aria-describedby="bot-chat-id-help" :placeholder="modelValue.botCodeEnabled ? t('settings.privateTargetPlaceholder') : '-1001234567890'" class="ui-input">
        <p id="bot-chat-id-help" class="text-xs text-gray-500 dark:text-gray-400">{{ t('settings.privateTargetHint') }}</p>
      </div>
      <div class="space-y-1.5">
        <label class="ui-label" for="bot-thread-id">{{ t('settings.threadId') }}</label>
        <input id="bot-thread-id" :value="modelValue.botThreadId" @input="onStringInput('botThreadId', $event)" type="text" :placeholder="t('settings.threadIdPlaceholder')" class="ui-input">
      </div>
      <div class="flex flex-wrap gap-x-6 gap-y-3 pt-2">
        <label class="flex items-center gap-2 cursor-pointer group">
          <input :checked="modelValue.botLoginNotify" @change="onCheckbox('botLoginNotify', $event)" type="checkbox" class="w-4 h-4 accent-sky-500 bg-gray-100 border-gray-300 rounded focus:ring-0 dark:bg-gray-800 dark:border-gray-600">
          <span class="text-sm text-gray-700 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-gray-100 transition-colors">{{ t('settings.loginFailNotify') }}</span>
        </label>
      </div>
      <div class="p-3 bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800/60 space-y-2">
        <label class="flex items-center gap-2 cursor-pointer">
          <input :checked="modelValue.botCodeEnabled" @change="onCheckbox('botCodeEnabled', $event)" type="checkbox" class="w-4 h-4 accent-sky-500 rounded">
          <span class="text-sm text-gray-700 dark:text-gray-200">{{ t('settings.privateCodeBot') }}</span>
        </label>
        <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('settings.privateCodeBotHint') }}</p>
        <p v-if="modelValue.botCodeEnabled && !isPrivateTarget(modelValue.botChatId)" class="text-xs text-red-600 dark:text-red-400" role="alert">{{ t('settings.privateTargetInvalid') }}</p>
        <p v-if="modelValue.botCodeEnabled && codeStatus" class="text-xs text-gray-500 dark:text-gray-400" role="status">{{ t('settings.privateCodeStatus', { status: botStatusLabel() }) }}</p>
      </div>
      <div class="p-3 bg-gray-50 dark:bg-white/[0.02] border border-gray-200 dark:border-gray-800/60 space-y-3">
        <div class="flex items-center justify-between gap-3">
          <div>
            <label class="text-xs text-gray-600 dark:text-gray-300 block">{{ t('settings.quietHours') }}</label>
            <p class="text-[10px] text-gray-500 mt-1">{{ t('settings.quietHoursDesc') }}</p>
          </div>
          <button
            type="button"
            class="ui-switch"
            role="switch"
            :aria-label="t('settings.quietHours')"
            :aria-checked="modelValue.quietEnabled"
            :class="modelValue.quietEnabled ? 'ui-switch-on' : ''"
            @click="update('quietEnabled', !modelValue.quietEnabled)"
          >
            <span class="ui-switch-knob" />
          </button>
        </div>
        <div class="grid grid-cols-2 gap-2" v-if="modelValue.quietEnabled">
          <div class="space-y-1">
            <label class="text-[10px] text-gray-500" for="bot-quiet-start">{{ t('settings.quietStart') }}</label>
            <input id="bot-quiet-start" :value="modelValue.quietStart" @input="onStringInput('quietStart', $event)" type="text" placeholder="23:00" class="ui-input" />
          </div>
          <div class="space-y-1">
            <label class="text-[10px] text-gray-500" for="bot-quiet-end">{{ t('settings.quietEnd') }}</label>
            <input id="bot-quiet-end" :value="modelValue.quietEnd" @input="onStringInput('quietEnd', $event)" type="text" placeholder="07:00" class="ui-input" />
          </div>
        </div>
      </div>
      <div class="pt-2 flex flex-col sm:flex-row gap-2">
        <button type="button" class="ui-btn-primary flex-1 py-2.5" :disabled="botLoading" @click="emit('save')">{{ botLoading ? t('common.saving') : t('settings.saveChanges') }}</button>
        <button type="button" class="ui-btn-secondary flex-1 py-2.5" :disabled="botTestLoading" @click="emit('test')">{{ botTestLoading ? t('settings.testing') : t('settings.testBot') }}</button>
      </div>
    </div>
  </section>
</template>
