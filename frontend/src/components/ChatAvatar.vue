<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { chatAvatar } from '../lib/api/communications'
import { chatAvatarCache } from '../lib/chat-avatar-cache'

const props = defineProps<{ account: string; chatId: string; name: string }>()
const root = ref<HTMLElement | null>(null)
const source = ref('')
let observer: IntersectionObserver | undefined
let requestId = 0
let releaseAvatar: (() => void) | undefined

function releaseCurrent() {
  ++requestId
  releaseAvatar?.()
  releaseAvatar = undefined
  source.value = ''
}

function leaveViewport() {
  releaseCurrent()
}

function enterViewport() {
  if (source.value || releaseAvatar || !props.account || !props.chatId) return
  const id = ++requestId
  const account = props.account
  const chatId = props.chatId
  const lease = chatAvatarCache.acquire(`${account}:${chatId}`, () => chatAvatar(account, chatId))
  releaseAvatar = lease.release
  void lease.promise.then(url => {
    if (id !== requestId || !url) return
    source.value = url
  })
}

function observe() {
  observer?.disconnect()
  if (!root.value) return
  if (!('IntersectionObserver' in window)) { enterViewport(); return }
  observer = new IntersectionObserver(entries => {
    const entry = entries.find(item => item.target === root.value)
    if (entry?.isIntersecting) enterViewport()
    else if (entry) leaveViewport()
  }, { rootMargin: '100px' })
  observer.observe(root.value)
}

watch(() => [props.account, props.chatId], () => {
  releaseCurrent()
  observe()
})
onMounted(observe)
onUnmounted(() => { releaseCurrent(); observer?.disconnect() })
</script>

<template>
  <span ref="root" class="panel-avatar" aria-hidden="true">
    <img v-if="source" :src="source" alt="" class="h-full w-full object-cover" />
    <span v-else>{{ name.slice(0, 2) }}</span>
  </span>
</template>
