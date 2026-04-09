<template>
  <div class="share-map-wrap">
    <canvas ref="canvasRef" class="share-canvas" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { createViewport } from '../engine/viewport'
import { renderFrame } from '../engine/renderer'

const props = defineProps<{ userId?: number | null }>()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const onlineUsers = ref<any[]>([])

let vp = createViewport(600, 300)
let animFrame = 0

function render() {
  if (!canvasRef.value) return
  const ctx = canvasRef.value.getContext('2d')!
  renderFrame(ctx, vp, onlineUsers.value, [], [], [], props.userId || null, null, { layer: 'both', mode: 'live' }, 0)
}

function loop() {
  animFrame = requestAnimationFrame(loop)
}

function connectWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocol}//${location.host}/ws/observe`)
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'snapshot') {
        onlineUsers.value = msg.users || []
        render()
      }
    } catch {}
  }
}

function resize() {
  if (!canvasRef.value) return
  const rect = canvasRef.value.parentElement!.getBoundingClientRect()
  canvasRef.value.width = rect.width
  canvasRef.value.height = rect.height
  vp.canvasW = rect.width
  vp.canvasH = rect.height
  render()
}

onMounted(() => {
  resize()
  loop()
  connectWs()
  window.addEventListener('resize', resize)
})
onUnmounted(() => {
  cancelAnimationFrame(animFrame)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.share-map-wrap { width: 100%; height: 100%; background: #fffbf5; }
.share-canvas { display: block; width: 100%; height: 100%; }
</style>
