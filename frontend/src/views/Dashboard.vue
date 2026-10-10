<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowUpRight, RefreshCw } from 'lucide-vue-next'
import { useI18n } from '../composables/useI18n'
import { getHeroImage, getHeroSettings } from '../lib/api/appearance'
import HeroCover from '../components/HeroCover.vue'
import { clampCoverPosition } from '../lib/cover-frame'

const loading = ref(false)
const { t } = useI18n()
const heroImageUrl = ref('')
const heroPositionX = ref(50)
const heroPositionY = ref(50)
let heroObjectUrl = ''
let active = true
let heroRequest: Promise<void> | undefined
let heroReloadPending = false
let heroPositionEdited = false

function showHeroBlob(blob: Blob) {
  if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
  heroObjectUrl = URL.createObjectURL(blob)
  heroImageUrl.value = heroObjectUrl
}

async function fetchHeroImage() {
  try {
    const [blob, settings] = await Promise.all([getHeroImage(), getHeroSettings()])
    if (active) {
      if (!heroPositionEdited) {
        heroPositionX.value = settings.position_x
        heroPositionY.value = settings.position_y
      }
      showHeroBlob(blob)
    }
  } catch {
    if (active) {
      if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
      heroObjectUrl = ''
      heroImageUrl.value = ''
      heroPositionX.value = 50
      heroPositionY.value = 50
    }
  }
}

function loadHeroImage(): Promise<void> {
  if (heroRequest) return heroRequest
  heroRequest = fetchHeroImage().finally(() => {
    heroRequest = undefined
    if (heroReloadPending && active) { heroReloadPending = false; void loadHeroImage() }
  })
  return heroRequest
}

function onHeroChanged() {
  if (heroRequest) heroReloadPending = true
  else void loadHeroImage()
}

function onHeroPositionChanged(event: Event) {
  heroPositionEdited = true
  const detail = (event as CustomEvent<{ x: number; y: number }>).detail
  heroPositionX.value = clampCoverPosition(detail.x)
  heroPositionY.value = clampCoverPosition(detail.y)
}

async function refreshDashboard() {
  loading.value = true
  try { await loadHeroImage() } finally { loading.value = false }
}

onMounted(() => {
  active = true
  window.addEventListener('tg-manage:hero-changed', onHeroChanged)
  window.addEventListener('tg-manage:hero-position-changed', onHeroPositionChanged)
  void loadHeroImage()
})
onUnmounted(() => {
  active = false
  window.removeEventListener('tg-manage:hero-changed', onHeroChanged)
  window.removeEventListener('tg-manage:hero-position-changed', onHeroPositionChanged)
  if (heroObjectUrl) URL.revokeObjectURL(heroObjectUrl)
})
</script>
<template>
  <div class="dashboard panel-stack" :aria-busy="loading">
    <section class="dashboard-hero" :class="{ 'dashboard-hero--custom': !!heroImageUrl }">
      <HeroCover v-if="heroImageUrl" :src="heroImageUrl" :position-x="heroPositionX" :position-y="heroPositionY" />
      <div class="dashboard-hero-actions" :aria-label="t('dashboard.actions')">
        <RouterLink to="/accounts" class="dashboard-hero-primary">{{ t('dashboard.manageAccounts') }} <ArrowUpRight :size="17" aria-hidden="true" /></RouterLink>
        <button type="button" class="dashboard-hero-refresh" :disabled="loading" @click="refreshDashboard"><RefreshCw :size="16" :class="{ 'animate-spin': loading }" aria-hidden="true" />{{ loading ? t('dashboard.refreshing') : t('dashboard.refresh') }}</button>
      </div>
    </section>
  </div>
</template>
