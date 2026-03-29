<template>
  <div class="world-map-wrap" ref="wrapRef"
    @wheel.prevent="onWheel"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointerleave="onPointerUp"
    @mousemove="onMouseMove"
    @mouseleave="onMouseLeave"
  >
    <canvas ref="canvasRef" class="world-canvas" />

    <!-- Zoom controls -->
    <div class="map-controls">
      <button class="ctrl-btn" @click="zoomIn">+</button>
      <button class="ctrl-btn" @click="zoomOut">−</button>
    </div>

    <!-- Scale display -->
    <div v-if="vp.scale > 0" class="scale-display">
      {{ Math.round(vp.scale / 0.05 * 100) }}%
    </div>

    <!-- Loading overlay -->
    <Transition name="fade">
      <div v-if="worldStore.loading" class="loading-overlay">
        <div class="loading-spinner" />
      </div>
    </Transition>

    <!-- Toolbar -->
    <WorldToolbar
      :replay-time="replay.currentTime.value"
      @enter-replay="showReplayModal = true"
      @exit-replay="exitReplay"
    />

    <!-- Replay bar (only in replay mode) -->
    <ReplayBar
      v-if="worldStore.mode === 'replay'"
      class="replay-bar-overlay"
      @range-selected="onRangeSelected"
    />

    <!-- Replay time selector modal -->
    <ReplayModal
      v-if="showReplayModal"
      @close="showReplayModal = false"
      @confirm="onReplayConfirm"
    />
  </div>
</template>

<script setup lang="ts">
// @ts-nocheck
import { ref, computed, watch, onMounted, onUnmounted, reactive } from 'vue'
import { useWorldStore } from '../stores/world'
import { useCrawlerStore } from '../stores/crawler'
import { useUiStore } from '../stores/ui'
import { useReplay } from '../composables/useReplay'
import { createViewport, zoomViewport, panViewport, worldToCanvas, canvasToWorld } from '../engine/viewport'
import { renderFrame } from '../engine/renderer'
import WorldToolbar from './WorldToolbar.vue'
import ReplayModal from './ReplayModal.vue'
import ReplayBar from './ReplayBar.vue'

// For buildTrailsFromPoints
interface ReplayPoint { x: number; y: number; ts: string; user_id: number; user_name?: string }

const worldStore = useWorldStore()
const crawlerStore = useCrawlerStore()
const uiStore = useUiStore()

const wrapRef = ref(null)
const canvasRef = ref(null)
const vp = reactive(createViewport(800, 600))
const hoveredUserId = ref(null)
const frame = ref(0)
const showReplayModal = ref(false)
const replay = useReplay()
let animFrame = 0
let ws = null

// Drag state
let isDragging = false
let lastX = 0, lastY = 0

function resize() {
  if (!canvasRef.value || !wrapRef.value) return
  const rect = wrapRef.value.getBoundingClientRect()
  canvasRef.value.width = rect.width
  canvasRef.value.height = rect.height
  vp.canvasW = rect.width
  vp.canvasH = rect.height
  render()
}

function buildTrails() {
  // Group livePoints by user_id → { user_id, name, points }
  const map = new Map()
  for (const p of worldStore.livePoints) {
    if (!map.has(p.user_id)) {
      map.set(p.user_id, { user_id: p.user_id, name: p.user_name || '', points: [] })
    }
    map.get(p.user_id).points.push({ x: p.x, y: p.y, ts: p.ts })
  }
  return Array.from(map.values())
}

function buildTrailsFromPoints(points: ReplayPoint[]) {
  const map = new Map()
  for (const p of points) {
    if (!map.has(p.user_id)) {
      map.set(p.user_id, { user_id: p.user_id, name: p.user_name || '', points: [] })
    }
    map.get(p.user_id).points.push({ x: p.x, y: p.y, ts: p.ts })
  }
  return Array.from(map.values())
}

const props = defineProps<{ ownerId?: number | null }>()

function focusUser(userId: number) {
  const u = worldStore.onlineUsers.find(u => u.user_id === userId)
  if (!u) return
  const cx = vp.canvasW / 2, cy = vp.canvasH / 2
  Object.assign(vp, {
    ...vp,
    offsetX: cx - u.x * vp.scale,
    offsetY: cy - u.y * vp.scale,
  })
  render()
}

defineExpose({ focusUser })

function render() {
  if (!canvasRef.value) return
  const ctx = canvasRef.value.getContext('2d')
  const users = worldStore.onlineUsers

  if (worldStore.mode === 'replay') {
    // Replay mode: render from visiblePoints
    const trails = buildTrailsFromPoints(replay.visiblePoints.value)
    renderFrame(
      ctx, vp,
      users,
      trails,
      [],
      null,
      hoveredUserId.value,
      { layer: uiStore.layerMode, mode: 'replay' },
      frame.value,
      replay.currentTime.value || undefined
    )
  } else {
    // Live mode: render from livePoints (history + realtime)
    const trails = buildTrails()
    renderFrame(
      ctx, vp,
      users,
      trails,
      [],
      null,
      hoveredUserId.value,
      { layer: uiStore.layerMode, mode: 'live', hideHistory: worldStore.hideHistory },
      frame.value
    )
  }
}

function loop() {
  frame.value++
  render()
  animFrame = requestAnimationFrame(loop)
}

function connectWs() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}/ws/observe?type=world`
  ws = new WebSocket(url)
  ws.onopen = () => {
    // connected
  }
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'snapshot') {
        worldStore.setSnapshot(msg.users || [])
      }
    } catch {}
  }
  ws.onclose = () => {
    setTimeout(connectWs, 3000)
  }
}

async function onReplayConfirm(window: '1h' | '24h' | '7d') {
  // Disconnect WebSocket
  if (ws) { ws.close(); ws = null }
  // Enter replay mode
  worldStore.enterReplayMode()
  // Load replay data
  await replay.loadReplay(window)
  showReplayModal.value = false
}

async function exitReplay() {
  replay.clear()
  worldStore.exitReplayMode()
  worldStore.loading = true
  await worldStore.loadGlobalHistory()
  connectWs()
}

function onRangeSelected(window: string) {
  // User picked a different time window from ReplayBar
  if (ws) { ws.close(); ws = null }
  replay.clear()
  replay.loadReplay(window as '1h' | '24h' | '7d')
}

function onWheel(e) {
  const rect = wrapRef.value.getBoundingClientRect()
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top
  const updated = zoomViewport(vp, e.deltaY, cx, cy)
  Object.assign(vp, updated)
  render()
}

function onPointerDown(e) {
  isDragging = true
  lastX = e.clientX
  lastY = e.clientY
  e.target.setPointerCapture(e.pointerId)
}

function onPointerMove(e) {
  if (isDragging) {
    const dx = e.clientX - lastX
    const dy = e.clientY - lastY
    const updated = panViewport(vp, dx, dy)
    Object.assign(vp, updated)
    lastX = e.clientX
    lastY = e.clientY
    render()
  }
}

function onPointerUp() { isDragging = false }

function onMouseMove(e) {
  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top

  // Find hovered user within 20px
  let found = null
  for (const u of worldStore.onlineUsers) {
    const pt = worldToCanvas(u.x, u.y, vp)
    const dist = Math.hypot(pt.x - cx, pt.y - cy)
    if (dist < 20) { found = u.user_id; break }
  }
  if (hoveredUserId.value !== found) {
    hoveredUserId.value = found
    render()
  }
}

function onMouseLeave() {
  if (hoveredUserId.value !== null) {
    hoveredUserId.value = null
    render()
  }
}

function zoomIn() {
  const cx = vp.canvasW / 2, cy = vp.canvasH / 2
  Object.assign(vp, zoomViewport(vp, -1, cx, cy))
  render()
}

function zoomOut() {
  const cx = vp.canvasW / 2, cy = vp.canvasH / 2
  Object.assign(vp, zoomViewport(vp, 1, cx, cy))
  render()
}

watch(() => replay.currentTime.value, () => {
  render()
})

onMounted(async () => {
  resize()
  window.addEventListener('resize', resize)
  loop()
  await worldStore.loadGlobalHistory()
  connectWs()
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  cancelAnimationFrame(animFrame)
  if (ws) ws.close()
})
</script>

<style scoped>
.world-map-wrap {
  width: 100%;
  height: 100%;
  position: relative;
  cursor: grab;
  overflow: visible;
}
.world-map-wrap:active { cursor: grabbing; }
.world-canvas {
  display: block;
  width: 100%;
  height: 100%;
  background: #fffbf5;
}
.map-controls {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ctrl-btn {
  width: 32px; height: 32px;
  border: 1.5px solid rgba(232, 98, 58, 0.3);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
  color: #E8623A;
  font-size: 1.1rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.ctrl-btn:hover { background: #E8623A; color: #fff; }
.scale-display {
  position: absolute;
  bottom: 16px;
  left: 16px;
  font-family: 'Space Grotesk', monospace;
  font-size: 0.72rem;
  color: rgba(139, 123, 110, 0.7);
  background: rgba(255, 255, 255, 0.8);
  padding: 2px 8px;
  border-radius: 99px;
}
.loading-overlay {
  position: absolute; inset: 0;
  background: rgba(255,251,245,0.7);
  display: flex; align-items: center; justify-content: center;
  z-index: 200;
}
.loading-spinner {
  width: 40px; height: 40px;
  border: 3px solid rgba(232,98,58,0.2);
  border-top-color: #E8623A;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.replay-bar-overlay {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  z-index: 100;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
