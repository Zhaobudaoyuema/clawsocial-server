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
      <canvas ref="canvasRef" class="world-canvas" />

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

// ── Canvas draw ──────────────────────────────────────────────────
const WORLD_SIZE = 10000
const canvasRef = ref<HTMLCanvasElement | null>(null)
const view = ref<'trail' | 'heatmap'>('trail')
const win = ref('7d')

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

  // Background
  ctx.fillStyle = '#FDF5EC'
  ctx.fillRect(0, 0, w, h)

  // Grid
  const cells = Math.ceil(WORLD_SIZE / 100)
  ctx.strokeStyle = 'rgba(232,98,58,0.06)'
  ctx.lineWidth = 0.5
  for (let i = 0; i <= cells; i++) {
    const px = (i / cells) * w
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, h); ctx.stroke()
    const py = (i / cells) * h
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(w, py); ctx.stroke()
  }

  // Trail
  if (view.value === 'trail') {
    const pts = worldStore.trailPoints
    if (pts.length > 1) {
      ctx.beginPath()
      ctx.moveTo((pts[0]!.x / WORLD_SIZE) * w, (pts[0]!.y / WORLD_SIZE) * h)
      for (let i = 1; i < pts.length; i++) {
        ctx.lineTo((pts[i]!.x / WORLD_SIZE) * w, (pts[i]!.y / WORLD_SIZE) * h)
      }
      ctx.strokeStyle = 'rgba(232,98,58,0.25)'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
    for (const pt of pts) {
      ctx.beginPath()
      ctx.arc((pt.x / WORLD_SIZE) * w, (pt.y / WORLD_SIZE) * h, 2, 0, Math.PI * 2)
      ctx.fillStyle = '#E8623A'
      ctx.fill()
    }
  }

  // Heatmap
  if (view.value === 'heatmap') {
    const density = new Map<string, number>()
    for (const pt of worldStore.trailPoints) {
      const cx = Math.floor(pt.x / 100)
      const cy = Math.floor(pt.y / 100)
      const key = `${cx},${cy}`
      density.set(key, (density.get(key) ?? 0) + 1)
    }
    const maxD = Math.max(...density.values(), 1)
    for (const [key, count] of density) {
      const [cxStr, cyStr] = key.split(',')
      const cx = Number(cxStr), cy = Number(cyStr)
      const px = (cx * 100 / WORLD_SIZE) * w
      const py = (cy * 100 / WORLD_SIZE) * h
      const alpha = 0.3 + 0.7 * (count / maxD)
      ctx.fillStyle = `rgba(232,98,58,${alpha})`
      ctx.fillRect(px, py, (100 / WORLD_SIZE) * w, (100 / WORLD_SIZE) * h)
    }
  }

  // Online users
  for (const u of worldStore.onlineUsers) {
    const px = (u.x / WORLD_SIZE) * w
    const py = (u.y / WORLD_SIZE) * h
    const grad = ctx.createRadialGradient(px, py, 0, px, py, 8)
    grad.addColorStop(0, 'rgba(232,98,58,0.4)')
    grad.addColorStop(1, 'rgba(232,98,58,0)')
    ctx.beginPath()
    ctx.arc(px, py, 8, 0, Math.PI * 2)
    ctx.fillStyle = grad
    ctx.fill()
    ctx.beginPath()
    ctx.arc(px, py, 4, 0, Math.PI * 2)
    ctx.fillStyle = '#E8623A'
    ctx.fill()
    ctx.fillStyle = '#3D2C24'
    ctx.font = '600 10px Nunito, sans-serif'
    ctx.fillText(u.name || `用户#${u.user_id}`, px + 6, py + 4)
  }
}

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
function loop() {
  draw()
  animFrame = requestAnimationFrame(loop)
}

onMounted(() => {
  connect()
  fetchGlobalStats()
  loop()
})

onUnmounted(() => {
  if (animFrame !== null) cancelAnimationFrame(animFrame)
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
.world-canvas { flex: 1; width: 100%; cursor: crosshair; display: block; }

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
