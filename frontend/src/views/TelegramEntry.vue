<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { loginFromTelegram } from '../lib/api/auth'
import { useAuthStore } from '../stores/auth'

type TelegramBridge = { WebApp?: { initData?: string; ready?: () => void } }

const router = useRouter()
const auth = useAuthStore()
const pending = ref(true)

function loadBridge(): Promise<TelegramBridge | undefined> {
  const existing = (window as Window & { Telegram?: TelegramBridge }).Telegram
  if (existing?.WebApp) return Promise.resolve(existing)
  return new Promise((resolve) => {
    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-web-app.js'
    script.onload = () => resolve((window as Window & { Telegram?: TelegramBridge }).Telegram)
    script.onerror = () => resolve(undefined)
    document.head.appendChild(script)
  })
}

onMounted(async () => {
  try {
    const bridge = await loadBridge()
    bridge?.WebApp?.ready?.()
    const initData = bridge?.WebApp?.initData
    if (!initData) return
    const result = await loginFromTelegram(initData)
    if (!result.access_token) return
    auth.setToken(result.access_token)
    await router.replace('/dashboard')
  } catch {
    // Do not reveal whether a bot, target ID or Telegram signature was accepted.
  } finally {
    pending.value = false
  }
})
</script>

<template>
  <main class="min-h-screen flex items-center justify-center" aria-live="polite">
    <span v-if="pending" class="sr-only">Opening</span>
  </main>
</template>
