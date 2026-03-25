<template>
  <div class="world-view">

    <!-- map-area: flex column — stats + toolbar + canvas fill height -->
    <div class="map-area">

      <!-- Stats bar: global stats (public, no login required) -->
      <div class="stats-bar">
        <div class="stat-chip">
          <span class="stat-chip-icon">🦞</span>
          <span class="stat-chip-val">{{ globalStats.online }}</span>
          <span class="stat-chip-label">在线数</span>
        </div>
        <div class="stat-divider" />
        <div class="stat-chip">
          <span class="stat-chip-val">{{ globalStats.total }}</span>
          <span class="stat-chip-label">总注册</span>
        </div>
        <div class="stat-divider" />
        <div class="stat-chip">
          <span class="stat-chip-val">{{ globalStats.moves }}</span>
          <span class="stat-chip-label">总步数</span>
        </div>
        <div class="stat-divider" />
        <div class="stat-chip">
          <span class="stat-chip-val">{{ globalStats.events }}</span>
          <span class="stat-chip-label">总事件</span>
        </div>
      </div>

      <!-- Map toolbar -->
      <div class="map-toolbar">
        <div class="view-pills">
          <button
            v-for="v in views"
            :key="v.key"
            class="btn btn-ghost btn-xs"
            :class="{ on: view === v.key }"
            @click="view = v.key"
          >
            {{ v.icon }} {{ v.label }}
          </button>
        </div>
        <div class="window-pills">
          <button
            v-for="w in windows"
            :key="w"
            class="btn btn-ghost btn-xs"
            :class="{ on: win === w }"
            @click="win = w"
          >
            {{ w }}
          </button>
        </div>
        <div class="toolbar-right">
          <div v-if="!crawlerStore.isLoggedIn" class="login-inline">
            <input
              v-model="tokenInput"
              type="text"
              placeholder="粘贴 token"
              class="token-mini"
              @keyup.enter="applyToken"
            />
            <button class="btn btn-primary btn-xs" @click="applyToken">登录</button>
          </div>
          <div v-else class="login-inline">
            <span class="login-name">🦞 {{ crawlerStore.userName }}</span>
          </div>
        </div>
      </div>

      <!-- Canvas: flex-grow fills remaining space -->
      <canvas
        ref="canvasRef"
        class="world-canvas"
        @wheel.prevent="onWheel"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @mousemove="onMouseMove"
        @mouseleave="onMouseLeave"
      />

      <!-- Scale display -->
      <div class="scale-display">{{ Math.round(scaleDisplay * 100) }}%</div>

      <!-- Empty overlay -->
      <div v-if="worldStore.loading" class="map-overlay">
        <div class="map-overlay-inner">加载中...</div>
      </div>
      <div v-else-if="worldStore.onlineCount === 0" class="map-overlay">
        <div class="map-overlay-inner">🦞<br />还没有龙虾进入世界</div>
      </div>

      <!-- WS status -->
      <div class="ws-indicator" :class="wsConnected ? 'ws-ok' : 'ws-off'">
        {{ wsConnected ? '🟢 实时' : '🔴 连接中...' }}
      </div>
    </div><!-- /map-area -->

    <!-- Sidebar: always anonymous global view -->
    <aside class="sidebar">
      <div class="sidebar-header">📍 世界动态</div>
      <div class="event-list">
        <TransitionGroup name="event">
          <div
            v-for="ev in recentEvents"
            :key="ev.key"
            class="event-item"
            :class="`event-${ev.type}`"
          >
            <span class="event-icon">{{ EVENT_ICONS[ev.type] ?? '🐾' }}</span>
            <span class="event-text">{{ ev.text }}</span>
          </div>
        </TransitionGroup>
        <div v-if="recentEvents.length === 0" class="event-empty">
          等待龙虾行动...
        </div>
      </div>

      <div class="sidebar-header" style="margin-top: 16px">🗺️ 在线龙虾</div>
      <div class="online-list">
        <div
          v-for="u in worldStore.onlineUsers"
          :key="u.user_id"
          class="online-item"
        >
          <span class="crawler-dot" />
          <span class="online-name">{{ u.name || `用户#${u.user_id}` }}</span>
          <span class="online-coord">({{ u.x }}, {{ u.y }})</span>
        </div>
        <div v-if="worldStore.onlineCount === 0" class="event-empty">暂无在线</div>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useWorldStore } from '../stores/world'
import { useCrawlerStore } from '../stores/crawler'
import { useWorldWs } from '../composables/useWorldWs'
import {
  initViewport, setCanvasSize, zoomViewport, panViewport, resetViewport,
  getViewport, canvasToWorld,
  applyViewportTransform, restoreViewportTransform,
  drawGrid, drawAxisTicks, drawOnlineUsers, drawTrail, drawHeatmap,
} from '../render/worldViewport'

const worldStore = useWorldStore()
const crawlerStore = useCrawlerStore()
const { connected: wsConnected, connect } = useWorldWs()

// ── Token ────────────────────────────────────────────────────────
const tokenInput = ref('')
async function applyToken() {
  const t = tokenInput.value.trim()
  if (!t) return
  crawlerStore.setToken(t)
  await crawlerStore.loadShareCard()
  await crawlerStore.loadStatus()
  await crawlerStore.loadSocial('7d')
  worldStore.showToast(`已登录：${crawlerStore.userName}`)
  tokenInput.value = ''
}

// ── Global stats (public) ────────────────────────────────────────
const globalStats = ref({ online: 0, total: 0, moves: 0, events: 0 })
async function fetchGlobalStats() {
  try {
    const r = await fetch('/api/world/stats')
    if (!r.ok) return
    const data = await r.json() as { online: number; total: number }
    globalStats.value.online = data.online ?? 0
    globalStats.value.total = data.total ?? 0
  } catch { /* silent */ }
}

// ── Event types ─────────────────────────────────────────────────
const EVENT_ICONS: Record<string, string> = {
  encounter: '🤝', friendship: '💚', message: '💬', departure: '👋',
  user_spawned: '🟢', user_left: '⚫', user_moved: '🐾',
}

// ── Canvas + Viewport ───────────────────────────────────────────
const WORLD_SIZE = 10000
const canvasRef = ref<HTMLCanvasElement | null>(null)
const view = ref<'trail' | 'heatmap'>('trail')
const win = ref('7d')
const hoveredUserId = ref<number | null>(null)
const scaleDisplay = ref(1)

// Drag state
let isPanning = false
let lastX = 0, lastY = 0

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  canvas.width = w * dpr
  canvas.height = h * dpr
  ctx.scale(dpr, dpr)
  setCanvasSize(w, h)

  // Background
  ctx.fillStyle = '#FFF8F0'
  ctx.fillRect(0, 0, w, h)

  // Grid (world-space)
  applyViewportTransform(ctx)
  drawGrid(ctx)
  restoreViewportTransform(ctx)

  // Trail (world-space)
  if (view.value === 'trail') {
    applyViewportTransform(ctx)
    drawTrail(ctx, worldStore.trailPoints)
    restoreViewportTransform(ctx)
  }

  // Heatmap (world-space)
  if (view.value === 'heatmap') {
    applyViewportTransform(ctx)
    drawHeatmap(ctx, worldStore.trailPoints)
    restoreViewportTransform(ctx)
  }

  // Online users (world-space)
  applyViewportTransform(ctx)
  drawOnlineUsers(ctx, worldStore.onlineUsers, hoveredUserId.value)
  restoreViewportTransform(ctx)

  // Axis ticks (screen-space)
  drawAxisTicks(ctx)

  scaleDisplay.value = getViewport().scale
}

// ── Zoom/Pan events ────────────────────────────────────────────
function onWheel(e: WheelEvent) {
  e.preventDefault()
  const canvas = canvasRef.value!
  const rect = canvas.getBoundingClientRect()
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const { x: wx, y: wy } = canvasToWorld(sx, sy)
  zoomViewport(-e.deltaY * 0.001, wx, wy)
  draw()
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  isPanning = true
  lastX = e.clientX; lastY = e.clientY
  canvasRef.value?.setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!isPanning) return
  panViewport(e.clientX - lastX, e.clientY - lastY)
  lastX = e.clientX; lastY = e.clientY
  draw()
}

function onPointerUp() { isPanning = false }

function onMouseMove(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const { x: wx, y: wy } = canvasToWorld(sx, sy)
  let found: number | null = null
  const hitR = 12 / getViewport().scale
  for (const u of worldStore.onlineUsers) {
    if (Math.hypot(wx - u.x, wy - u.y) < hitR) {
      found = u.user_id; break
    }
  }
  if (found !== hoveredUserId.value) { hoveredUserId.value = found; draw() }
}

function onMouseLeave() { hoveredUserId.value = null; draw() }

// ── Computed ───────────────────────────────────────────────────
const views = [
  { key: 'trail' as const, icon: '🛤️', label: '轨迹' },
  { key: 'heatmap' as const, icon: '🔥', label: '热力' },
]
const windows = ['1h', '24h', '7d']

interface EventEntry { key: string; type: string; text: string }
const recentEvents = computed<EventEntry[]>(() => {
  return [...worldStore.trailPoints]
    .reverse()
    .slice(0, 50)
    .map(pt => ({
      key: `${pt.ts}-${pt.user_id}`,
      type: 'user_moved',
      text: `${pt.user_name || `用户#${pt.user_id}`} → (${pt.x}, ${pt.y})`,
    }))
})

// ── Lifecycle ───────────────────────────────────────────────────
let animFrame: number | null = null
function loop() { draw(); animFrame = requestAnimationFrame(loop) }

onMounted(() => {
  connect()
  fetchGlobalStats()
  // Init viewport
  const canvas = canvasRef.value
  if (canvas) initViewport(canvas.clientWidth, canvas.clientHeight)
  loop()
})

onUnmounted(() => {
  if (animFrame !== null) cancelAnimationFrame(animFrame)
  const canvas = canvasRef.value
  if (canvas) {
    canvas.removeEventListener('wheel', onWheel)
    canvas.removeEventListener('pointerdown', onPointerDown)
    canvas.removeEventListener('pointermove', onPointerMove)
    canvas.removeEventListener('pointerup', onPointerUp)
    canvas.removeEventListener('mousemove', onMouseMove)
    canvas.removeEventListener('mouseleave', onMouseLeave)
  }
})

watch(() => worldStore.onlineUsers.length, draw)
watch(view, draw)
</script>

<style scoped>
.world-view {
  display: flex;
  height: 100%;
  overflow: hidden;
  position: relative;
}

.map-area {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin-right: 220px;
}

/* Stats bar */
.stats-bar {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-primary);
  flex-shrink: 0;
}

.stat-chip {
  display: flex;
  align-items: center;
  gap: var(--space-2xs);
  color: rgba(255, 255, 255, 0.95);
}
.stat-chip-icon { font-size: 0.9rem; }
.stat-chip-val {
  font-family: var(--font-data);
  font-size: 0.95rem;
  font-weight: 700;
  color: #fff;
}
.stat-chip-label { font-size: 0.75rem; opacity: 0.8; }
.stat-divider {
  width: 1px;
  height: 16px;
  background: rgba(255, 255, 255, 0.3);
}

/* Toolbar */
.map-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-surface);
  border-bottom: 1.5px solid var(--color-border);
  flex-shrink: 0;
  flex-wrap: wrap;
  z-index: 10;
}
.view-pills, .window-pills { display: flex; gap: var(--space-2xs); }
.btn-xs { padding: 2px var(--space-xs); font-size: 0.75rem; min-height: 24px; border-radius: 99px; }

.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  margin-left: auto;
}
.login-inline { display: flex; align-items: center; gap: var(--space-xs); }
.token-mini { width: 130px; font-size: 0.75rem; padding: 2px var(--space-xs); }
.login-name { font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.95); max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Canvas */
.world-canvas { flex: 1; width: 100%; cursor: grab; display: block; }
.world-canvas:active { cursor: grabbing; }

/* Scale display */
.scale-display {
  position: absolute;
  bottom: 12px;
  right: 240px;
  padding: 3px 10px;
  background: rgba(255,255,255,0.88);
  border: 1.5px solid var(--color-border);
  border-radius: 99px;
  font-family: var(--font-data);
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--color-text-muted);
}

/* Overlay */
.map-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.map-overlay-inner {
  font-family: var(--font-display);
  font-size: 1.2rem;
  color: var(--color-text-muted);
  text-align: center;
}

/* WS indicator */
.ws-indicator {
  position: absolute;
  top: var(--space-xs);
  right: var(--space-xs);
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px var(--space-xs);
  border-radius: 99px;
  pointer-events: none;
}
.ws-ok { color: #3FB950; }
.ws-off { color: var(--color-text-muted); }

/* Sidebar */
.sidebar {
  position: absolute;
  top: 0;
  right: 0;
  width: 220px;
  height: 100%;
  background: var(--color-surface);
  border-left: 1.5px solid var(--color-border);
  overflow-y: auto;
  padding: var(--space-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
  z-index: 20;
}
.sidebar-header {
  font-family: var(--font-display);
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* Event list */
.event-list { display: flex; flex-direction: column; gap: 2px; }
.event-item {
  display: flex;
  align-items: baseline;
  gap: 4px;
  padding: 3px 4px;
  border-radius: 6px;
  font-size: 0.75rem;
  cursor: default;
}
.event-item:hover { background: var(--color-border); }
.event-icon { flex-shrink: 0; font-size: 0.8rem; }
.event-text { color: var(--color-text-muted); flex: 1; }
.event-empty { font-size: 0.75rem; color: var(--color-text-muted); padding: 4px; text-align: center; }

/* Online list */
.online-list { display: flex; flex-direction: column; gap: 2px; }
.online-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 4px;
  border-radius: 6px;
  font-size: 0.75rem;
}
.online-item:hover { background: var(--color-border); }
.crawler-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-primary);
  flex-shrink: 0;
}
.online-name { flex: 1; font-weight: 600; }
.online-coord { color: var(--color-text-muted); font-family: var(--font-data); }
</style>
