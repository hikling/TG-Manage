<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { coverFrame, clampCoverPosition, type CoverFrame } from '../lib/cover-frame'

const props = defineProps<{ src: string; positionX: number; positionY: number }>()
const emit = defineEmits<{ geometry: [frame: CoverFrame] }>()
const container = ref<HTMLElement | null>(null)
const width = ref(0), height = ref(0), imageWidth = ref(0), imageHeight = ref(0)
const frame = computed(() => coverFrame(width.value, height.value, imageWidth.value, imageHeight.value))
const imageStyle = computed(() => frame.value.width ? {
  width: `${frame.value.width}px`,
  height: `${frame.value.height}px`,
  left: `${-frame.value.overflowX * clampCoverPosition(props.positionX) / 100}px`,
  top: `${-frame.value.overflowY * clampCoverPosition(props.positionY) / 100}px`,
} : { visibility: 'hidden' as const })
let observer: ResizeObserver | undefined
function measure() {
  const bounds = container.value?.getBoundingClientRect()
  width.value = bounds?.width ?? 0
  height.value = bounds?.height ?? 0
}
function imageLoaded(event: Event) {
  const image = event.target as HTMLImageElement
  imageWidth.value = image.naturalWidth
  imageHeight.value = image.naturalHeight
  measure()
}
watch(frame, value => emit('geometry', value), { immediate: true })
watch(() => props.src, () => { imageWidth.value = 0; imageHeight.value = 0 })
onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure)
    if (container.value) observer.observe(container.value)
  } else window.addEventListener('resize', measure)
})
onUnmounted(() => { observer?.disconnect(); window.removeEventListener('resize', measure) })
</script>

<template>
  <div ref="container" class="hero-cover" aria-hidden="true">
    <img :src="src" :style="imageStyle" alt="" draggable="false" decoding="async" @load="imageLoaded" />
  </div>
</template>

<style scoped>
.hero-cover { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
.hero-cover img { position: absolute; max-width: none; user-select: none; }
</style>
