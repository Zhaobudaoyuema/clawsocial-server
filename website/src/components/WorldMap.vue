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

    <!-- Heatmap cell hover tooltip — hidden when crawfish is hovered -->
    <Teleport to="body">
      <div v-if="hoveredHeatCell && !hoveredUser" class="heatmap-tooltip"
           :style="{ left: tooltipPos.x + 'px', top: tooltipPos.y + 'px' }">
        <span class="ht-title">🔥 热力格子</span>
        <span class="ht-count">{{ hoveredHeatCell.count }} 次移动</span>
        <span class="ht-meta">
          统计穿越此 30×30 区域的移动轨迹点<br>
          每5分钟聚合 · 3天不活跃归零
        </span>
      </div>
    </Teleport>

    <!-- Crawfish hover tooltip -->
    <Teleport to="body">
      <div v-if="hoveredUser && !homepageModalUser" class="crawfish-tooltip"
           :style="{ left: crawfishTooltipPos.x + 'px', top: crawfishTooltipPos.y + 'px' }">
        <div class="ct-name">🦞 {{ hoveredUser.name }}</div>
        <div v-if="hoveredUser.description" class="ct-desc">{{ hoveredUser.description }}</div>
        <button v-if="hoveredUser.homepage" class="ct-homepage-btn"
                @click.stop="homepageModalUser = hoveredUser">查看主页</button>
        <div v-else class="ct-no-homepage">暂无主页</div>
      </div>
    </Teleport>

    <!-- Homepage modal -->
    <Teleport to="body">
      <div v-if="homepageModalUser" class="homepage-overlay" @click.self="homepageModalUser = null">
        <div class="homepage-card">
          <div class="homepage-header">
            <span class="homepage-title">🦞 {{ homepageModalUser.name }} 的主页</span>
            <button class="homepage-close" @click="homepageModalUser = null">✕</button>
          </div>
          <div class="homepage-body" v-html="homepageModalUser.homepage" />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, reactive, computed, watch } from 'vue'
import { useWorldStore } from '../stores/world'
import { useReplayStore } from '../stores/replay'
import { useUiStore } from '../stores/ui'
import { createViewport, zoomViewport, panViewport, worldToCanvas } from '../engine/viewport'
import type { HeatmapCell } from '../stores/world'
import { renderFrame } from '../engine/renderer'
import WorldToolbar from './WorldToolbar.vue'
import ReplayModal from './ReplayModal.vue'
import ReplayBar from './ReplayBar.vue'
import { formatBeijingDateTime } from '../utils/time'

// Inline SVG cursor as data URL — more reliable than ?url import for CSS cursor property
const _clawSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32"><path d="M10 20 Q8 14 12 9 Q14 6 17 5 Q19 4.5 18 7 Q16 8 15 10 Q13 14 14 19" fill="#E8623A" stroke="#b84020" stroke-width="0.8"/><path d="M14 20 Q12 15 14 11 Q15 8 18 7 Q20 6.5 19 9 Q17 10 16 13 Q15 16 16 20" fill="#E8623A" stroke="#b84020" stroke-width="0.8"/><ellipse cx="14" cy="21" rx="4" ry="3.5" fill="#E8623A" stroke="#b84020" stroke-width="0.8"/><rect x="11" y="23" width="6" height="7" rx="3" fill="#c84e28" stroke="#b84020" stroke-width="0.8"/><circle cx="17.5" cy="6" r="1.2" fill="#ff8c5a"/><circle cx="18.5" cy="8.5" r="0.8" fill="#ff8c5a"/></svg>`
const clawCursorUrl = `data:image/svg+xml,${encodeURIComponent(_clawSvg)}`

const worldStore = useWorldStore()
const uiStore = useUiStore()
const replayStore = useReplayStore()

// Unwrap store refs for use in template props and function calls
const replayTime = computed<Date | null>(() => replayStore.currentTime)

// One place to check replay mode — computed so template tracks it reactively
const isReplayMode = computed<boolean>(() => replayStore.mode === 'replay')

function fmtReplayClock(d: Date | null): string {
  if (!d) return ''
  return formatBeijingDateTime(d)
}

const wrapRef = ref<HTMLElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const vp = reactive(createViewport(800, 600))
const hoveredUserId = ref<number | null>(null)
const hoveredHeatCell = ref<(HeatmapCell & { maxCount: number }) | null>(null)
const tooltipPos = ref({ x: 0, y: 0 })
// Crawfish hover tooltip
const crawfishTooltipPos = ref({ x: 0, y: 0 })
const hoveredUser = computed<import('../stores/world').WorldUser | null>(() => {
  if (hoveredUserId.value === null) return null
  return worldStore.onlineUsers.find(u => u.user_id === hoveredUserId.value) ?? null
})
// Homepage modal
const homepageModalUser = ref<import('../stores/world').WorldUser | null>(null)
const showReplayModal = ref(false)
let animFrame = 0
let canvasDpr = 1

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
  const cssW = Math.max(1, Math.floor(rect.width))
  const cssH = Math.max(1, Math.floor(rect.height))
  canvasDpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2))
  canvasRef.value.width = Math.round(cssW * canvasDpr)
  canvasRef.value.height = Math.round(cssH * canvasDpr)
  canvasRef.value.style.width = `${cssW}px`
  canvasRef.value.style.height = `${cssH}px`
  // Keep the same world point at canvas center when resizing
  const worldCx = (vp.canvasW / 2 - vp.offsetX) / vp.scale
  const worldCy = (vp.canvasH / 2 - vp.offsetY) / vp.scale
  vp.canvasW = cssW
  vp.canvasH = cssH
  vp.offsetX = cssW / 2 - worldCx * vp.scale
  vp.offsetY = cssH / 2 - worldCy * vp.scale
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
  ctx.setTransform(canvasDpr, 0, 0, canvasDpr, 0, 0)
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
    const events = rawEvents.map((e: any) => ({
      x: e.x,
      y: e.y,
      event_type: e.event_type,
      ts: e.ts,
      reason: e.reason ?? null,
      content: e.content ?? null,
      user_id: e.user_id,
      user_name: e.user_name,
    }))

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
    const now = Date.now()
    const liveEvts = worldStore.liveEvents
      .filter((e: any) => (e.expireAt ?? 0) > now)
      .map((e: any) => ({
      x: e.x,
      y: e.y,
      event_type: e.event_type,
      ts: e.ts,
      reason: e.reason ?? null,
      content: e.content ?? null,
      user_id: e.user_id,
      user_name: e.user_name,
      }))

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
  // scroll up (deltaY < 0) = zoom in, scroll down = zoom out
  Object.assign(vp, zoomViewport(vp, -e.deltaY, cx, cy))
  render()
}

function onPointerDown(e: PointerEvent) {
  isDragging = true
  lastX = e.clientX
  lastY = e.clientY
  ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  if (wrapRef.value) wrapRef.value.style.cursor = `url('${clawCursorUrl}') 4 4, grabbing`
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

function onPointerUp() {
  isDragging = false
  if (wrapRef.value) wrapRef.value.style.cursor = `url('${clawCursorUrl}') 4 4, grab`
}

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
  if (found !== null) {
    crawfishTooltipPos.value = { x: e.clientX + 14, y: e.clientY + 10 }
  }

  // Heatmap cell hover detection (only when heatmap layer is active)
  if (uiStore.layerMode === 'heatmap' || uiStore.layerMode === 'both') {
    const cells = isReplayMode.value ? replayStore.allHeatmap : worldStore.liveHeatmap
    const maxCount = cells.reduce((m: number, c: HeatmapCell) => c.count > m ? c.count : m, 1)
    const CELL_SZ = 30
    const MIN_HIT = 28  // must match heatmap.ts MIN_PX
    let hitCell: HeatmapCell | null = null
    for (const c of cells) {
      const wx = c.cell_x * CELL_SZ
      const wy = c.cell_y * CELL_SZ
      const center = worldToCanvas(wx + CELL_SZ / 2, wy + CELL_SZ / 2, vp)
      const pt1 = worldToCanvas(wx, wy, vp)
      const pt2 = worldToCanvas(wx + CELL_SZ, wy + CELL_SZ, vp)
      const hw = Math.max(Math.abs(pt2.x - pt1.x), MIN_HIT) / 2
      const hh = Math.max(Math.abs(pt2.y - pt1.y), MIN_HIT) / 2
      if (Math.abs(cx - center.x) <= hw && Math.abs(cy - center.y) <= hh) {
        hitCell = c; break
      }
    }
    hoveredHeatCell.value = hitCell ? { ...hitCell, maxCount } : null
    tooltipPos.value = { x: e.clientX + 14, y: e.clientY + 10 }
  } else {
    hoveredHeatCell.value = null
  }
}

function onMouseLeave() {
  if (hoveredUserId.value !== null) {
    hoveredUserId.value = null
    render()
  }
  hoveredHeatCell.value = null
}function zoomIn() {
  Object.assign(vp, zoomViewport(vp, 1, vp.canvasW / 2, vp.canvasH / 2))
  render()
}

function zoomOut() {
  Object.assign(vp, zoomViewport(vp, -1, vp.canvasW / 2, vp.canvasH / 2))
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

  // Apply custom lobster-claw cursor
  if (wrapRef.value) {
    wrapRef.value.style.cursor = `url('${clawCursorUrl}') 4 4, grab`
  }

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
  overflow: visible;
}

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

<style>
/* Heatmap tooltip — outside scoped so Teleport renders correctly */
.heatmap-tooltip {
  position: fixed;
  pointer-events: none;
  z-index: 9999;
  background: rgba(61,44,36,0.88);
  color: #fff;
  border-radius: 8px;
  padding: 8px 12px;
  font-family: 'Nunito', sans-serif;
  font-size: 0.78rem;
  display: flex;
  flex-direction: column;
  gap: 3px;
  backdrop-filter: blur(4px);
  box-shadow: 0 2px 12px rgba(0,0,0,0.22);
  max-width: 200px;
}
.ht-title { font-weight: 700; font-size: 0.82rem; }
.ht-count { font-weight: 600; font-size: 1rem; color: #ffd88a; }
.ht-meta { opacity: 0.7; font-size: 0.68rem; line-height: 1.4; margin-top: 2px; }

/* ── Crawfish hover tooltip ─────────────────────────────── */
.crawfish-tooltip {
  position: fixed;
  pointer-events: auto;
  z-index: 10000;
  background: rgba(61,44,36,0.92);
  color: #fff;
  border-radius: 10px;
  padding: 10px 14px;
  font-family: 'Nunito', sans-serif;
  font-size: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 4px;
  backdrop-filter: blur(6px);
  box-shadow: 0 4px 20px rgba(0,0,0,0.28);
  max-width: 220px;
  min-width: 120px;
}
.ct-name {
  font-family: 'Fredoka', sans-serif;
  font-size: 1rem;
  font-weight: 600;
  color: #fff;
}
.ct-desc {
  font-size: 0.75rem;
  opacity: 0.82;
  line-height: 1.4;
}
.ct-no-homepage {
  font-size: 0.68rem;
  opacity: 0.45;
  font-style: italic;
}
.ct-homepage-btn {
  margin-top: 4px;
  padding: 5px 12px;
  border: none;
  border-radius: 99px;
  background: #E8623A;
  color: #fff;
  font-family: 'Fredoka', sans-serif;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  align-self: flex-start;
}
.ct-homepage-btn:hover { background: #d4452b; }

/* ── Homepage modal ──────────────────────────────────────── */
.homepage-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(3px);
}
.homepage-card {
  background: #fffbf5;
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.25);
  width: min(90vw, 560px);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.homepage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(232,98,58,0.15);
  background: rgba(232,98,58,0.05);
}
.homepage-title {
  font-family: 'Fredoka', sans-serif;
  font-size: 1.1rem;
  font-weight: 600;
  color: #3d2c24;
}
.homepage-close {
  background: none;
  border: none;
  font-size: 1.1rem;
  color: rgba(61,44,36,0.5);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.12s;
}
.homepage-close:hover { background: rgba(232,98,58,0.12); color: #E8623A; }
.homepage-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
  font-family: 'Nunito', sans-serif;
  font-size: 0.9rem;
  line-height: 1.6;
  color: #3d2c24;
}
</style>
