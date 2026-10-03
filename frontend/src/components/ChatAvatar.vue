<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { chatAvatar } from '../lib/api/communications'

const props = defineProps<{ account: string; chatId: string; name: string }>()
const root = ref<HTMLElement | null>(null)
const source = ref('')
let observer: IntersectionObserver | undefined
let requestId = 0

async function load() {
  if (!props.account || !props.chatId) return
  const id = ++requestId
  try {
    const blob = await chatAvatar(props.account, props.chatId)
    if (id !== requestId) return
    if (source.value) URL.revokeObjectURL(source.value)
    source.value = URL.createObjectURL(blob)
  } catch {
    // Chats without a photo use the initials fallback.
  }
}

function observe() {
  observer?.disconnect()
  if (!root.value) return
  if (!('IntersectionObserver' in window)) { void load(); return }
  observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      observer?.disconnect()
      void load()
    }
  }, { rootMargin: '100px' })
  observer.observe(root.value)
}

watch(() => [props.account, props.chatId], () => {
  ++requestId
  if (source.value) URL.revokeObjectURL(source.value)
  source.value = ''
  observe()
})
onMounted(observe)
onUnmounted(() => { ++requestId; observer?.disconnect(); if (source.value) URL.revokeObjectURL(source.value) })
</script>

<template>
  <span ref="root" class="panel-avatar" aria-hidden="true">
    <img v-if="source" :src="source" alt="" class="h-full w-full object-cover" />
    <span v-else>{{ name.slice(0, 2) }}</span>
  </span>
</template>
