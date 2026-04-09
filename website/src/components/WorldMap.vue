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

    <!-- Replay mode banner — 醒目提示已进入回放 -->
    <Transition name="replay-banner">
      <div v-if="isReplayMode" class="replay-banner">
        <span class="replay-icon">🔄</span>
        <span class="replay-text">回放模式</span>
        <span v-if="replayTime" class="replay-clock-inline">{{ fmtReplayClock(replayTime) }}</span>
      </div>
    </Transition>

    <!-- Toolbar -->
    <WorldToolbar
      :replay-time="replayTime"
      @enter-replay="showReplayModal = true"
      @exit-replay="exitReplay"
    />

    <!-- Replay bar (only in replay mode) -->
    <ReplayBar
      v-if="isReplayMode"
      class="replay-bar-overlay"
      @range-selected="onRangeSelected"
    />

    <!-- Replay time window modal -->
    <ReplayModal
      v-if="showReplayModal"
      @close="showReplayModal = false"
      @confirm="onReplayConfirm"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, reactive, computed, watch } from 'vue'
import { useWorldStore } from '../stores/world'
import { useReplayStore } from '../stores/replay'
import { useUiStore } from '../stores/ui'
import { createViewport, zoomViewport, panViewport, worldToCanvas } from '../engine/viewport'
import { renderFrame } from '../engine/renderer'
import WorldToolbar from './WorldToolbar.vue'
import ReplayModal from './ReplayModal.vue'
import ReplayBar from './ReplayBar.vue'

const worldStore = useWorldStore()
const uiStore = useUiStore()
const replayStore = useReplayStore()

// Unwrap store refs for use in template props and function calls
const replayTime = computed<Date | null>(() => replayStore.currentTime)

// One place to check replay mode — computed so template tracks it reactively
const isReplayMode = computed<boolean>(() => replayStore.mode === 'replay')

function fmtReplayClock(d: Date | null): string {
  if (!d) return ''
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

const wrapRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const vp = reactive(createViewport(800, 600))
const hoveredUserId = ref<number | null>(null)
const showReplayModal = ref(false)
let animFrame = 0

// ── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  ownerId?: number | null
  token?: string | null
}>()

// ── Drag state ───────────────────────────────────────────────────────────────

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

// ── Trails builders ──────────────────────────────────────────────────────────

function buildTrailsFromPoints(
  points: Array<{ user_id: number; user_name?: string; x: number; y: number; ts: string }>
) {
  const map = new Map<number, { user_id: number; name: string; points: Array<{ x: number; y: number; ts: string }> }>()
  for (const p of points) {
    if (!map.has(p.user_id)) {
      map.set(p.user_id, { user_id: p.user_id, name: p.user_name || '', points: [] })
    }
    map.get(p.user_id)!.points.push({ x: p.x, y: p.y, ts: p.ts })
  }
  return Array.from(map.values())
}

function buildTrailsFromLive() {
  return buildTrailsFromPoints(
    worldStore.livePoints.map(p => ({
      user_id: p.user_id,
      user_name: p.user_name || '',
      x: p.x,
      y: p.y,
      ts: p.ts,
    }))
  )
}

// ── Render ─────────────────────────────────────────────────────────────────

function render() {
  if (!canvasRef.value) return
  const ctx = canvasRef.value.getContext('2d')!
  const isReplay = isReplayMode.value

  // Declare at function scope so both branches can assign
  let users: any[] = []
  let trails: any[] = []
  let rawEvents: any[] = []

  if (isReplay) {
    if (replayStore.filterMyOnly) {
      users = replayStore.myModePositions
      trails = buildTrailsFromPoints(replayStore.myPoints)
      rawEvents = replayStore.myEvents
    } else {
      users = replayStore.crawfishPositions
      trails = buildTrailsFromPoints(replayStore.visiblePoints)
      rawEvents = replayStore.visibleEvents
    }
    const events = rawEvents.map((e: any) => ({ x: e.x, y: e.y, event_type: e.event_type, ts: e.ts }))

    renderFrame(
      ctx, vp,
      users,
      trails,
      events,
      replayStore.allHeatmap,
      props.ownerId ?? null,
      hoveredUserId.value,
      { layer: uiStore.layerMode, mode: 'replay' },
      animFrame,
      replayStore.currentTime ?? undefined,
    )
  } else {
    // Live mode
    worldStore.purgeExpiredEvents()
    const liveTrails = buildTrailsFromLive()
    const liveUsers = worldStore.onlineUsers
    const liveEvts = worldStore.liveEvents.map((e: any) => ({ x: e.x, y: e.y, event_type: e.event_type, ts: e.ts }))

    renderFrame(
      ctx, vp,
      liveUsers,
      liveTrails,
      liveEvts,
      worldStore.liveHeatmap,
      props.ownerId ?? null,
      hoveredUserId.value,
      { layer: uiStore.layerMode, mode: 'live', hideHistory: false },
      animFrame,
    )
  }
}

function loop() {
  animFrame++
  render()
  animFrame = requestAnimationFrame(loop)
}

// ── WS ───────────────────────────────────────────────────────────────────────

function onReplayConfirm(window: '1h' | '24h' | '7d') {
  worldStore.loading = true
  worldStore.mode = 'replay'
  replayStore.enterReplayMode()
  replayStore.setMyUserId(worldStore.myUserId)
  replayStore.loadReplay(window, props.token ?? undefined).then(() => {
    worldStore.loading = false
  })
  showReplayModal.value = false
}

async function exitReplay() {
  worldStore.mode = 'live'
  replayStore.exitReplayMode()
  worldStore.loading = true
  await worldStore.loadGlobalHistory('24h', props.token ?? undefined)
  worldStore.loading = false
  worldStore.connect(props.token ?? undefined)
}

async function onRangeSelected(window: string) {
  replayStore.clear()
  replayStore.enterReplayMode()
  replayStore.setMyUserId(worldStore.myUserId)
  worldStore.mode = 'replay'
  worldStore.loading = true
  await replayStore.loadReplay(window as '1h' | '24h' | '7d', props.token ?? undefined)
  worldStore.loading = false
}

// ── Zoom & Pan ──────────────────────────────────────────────────────────────

function onWheel(e: WheelEvent) {
  const rect = wrapRef.value!.getBoundingClientRect()
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top
  Object.assign(vp, zoomViewport(vp, e.deltaY, cx, cy))
  render()
}

function onPointerDown(e: PointerEvent) {
  isDragging = true
  lastX = e.clientX
  lastY = e.clientY
  ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!isDragging) return
  const dx = e.clientX - lastX
  const dy = e.clientY - lastY
  Object.assign(vp, panViewport(vp, dx, dy))
  lastX = e.clientX
  lastY = e.clientY
  render()
}

function onPointerUp() { isDragging = false }

// ── Hover ──────────────────────────────────────────────────────────────────

function onMouseMove(e: MouseEvent) {
  if (!canvasRef.value) return
  const rect = canvasRef.value.getBoundingClientRect()
  const cx = e.clientX - rect.left
  const cy = e.clientY - rect.top
  let found: number | null = null
  // replay 模式用回放位置，live 模式用在线用户
  const hoverUsers = isReplayMode.value ? replayStore.crawfishPositions : worldStore.onlineUsers
  for (const u of hoverUsers) {
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
  Object.assign(vp, zoomViewport(vp, -1, vp.canvasW / 2, vp.canvasH / 2))
  render()
}

function zoomOut() {
  Object.assign(vp, zoomViewport(vp, 1, vp.canvasW / 2, vp.canvasH / 2))
  render()
}

// ── Focus ──────────────────────────────────────────────────────────────────

function focusUser(userId: number) {
  const u = worldStore.onlineUsers.find(u => u.user_id === userId)
  if (!u) return
  Object.assign(vp, {
    offsetX: vp.canvasW / 2 - u.x * vp.scale,
    offsetY: vp.canvasH / 2 - u.y * vp.scale,
  })
  render()
}

defineExpose({ focusUser })

// ── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  resize()
  window.addEventListener('resize', resize)

  // Init myUserId from token if provided
  if (props.token) {
    // Resolve userId from token via API — simpler: just store token, let WS resolve
    worldStore.setMyUserId(null)  // WS will inject isMe
  }

  // Load initial data
  await worldStore.loadGlobalHistory('24h', props.token ?? undefined)
  await worldStore.loadHeatmap('24h')

  // Connect WS
  worldStore.connect(props.token ?? undefined)

  // Watch replay state changes → re-render immediately
  watch(
    () => [
      replayStore.currentTime,
      replayStore.replaying,
      replayStore.filterMyOnly,
      worldStore.mode,
    ],
    () => { render() },
    { deep: true },
  )

  // Start render loop
  animFrame = requestAnimationFrame(loop)
})

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  cancelAnimationFrame(animFrame)
  worldStore.disconnect()
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
  border: 1.5px solid rgba(232,98,58,0.3);
  border-radius: 8px;
  background: rgba(255,255,255,0.9);
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
  color: rgba(139,123,110,0.7);
  background: rgba(255,255,255,0.8);
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

/* 回放模式顶部 banner */
.replay-banner {
  position: absolute;
  top: 0; left: 0; right: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 10px 20px;
  background: linear-gradient(135deg, #e65100 0%, #e8623a 100%);
  color: #fff;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.95rem;
  font-weight: 600;
  z-index: 300;
  box-shadow: 0 2px 12px rgba(230, 81, 0, 0.4);
  pointer-events: none;
}
.replay-icon { font-size: 1.1rem; }
.replay-text { letter-spacing: 0.03em; }
.replay-clock-inline {
  font-family: 'Space Grotesk', monospace;
  font-size: 0.82rem;
  font-weight: 400;
  background: rgba(255,255,255,0.2);
  padding: 2px 10px;
  border-radius: 99px;
}
.replay-exit-btn {
  pointer-events: all;
  margin-left: 8px;
  padding: 4px 14px;
  border-radius: 99px;
  border: 1.5px solid rgba(255,255,255,0.6);
  background: rgba(255,255,255,0.15);
  color: #fff;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}
.replay-exit-btn:hover { background: rgba(255,255,255,0.3); }

.replay-banner-enter-active, .replay-banner-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}
.replay-banner-enter-from, .replay-banner-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
