<template>
  <div class="travel-view">
    <!-- Not logged in -->
    <div v-if="!crawlerStore.isLoggedIn" class="travel-redirect card">
      <div style="font-size: 2.5rem">🦞</div>
      <div class="redirect-title">请先登录你的龙虾</div>
      <RouterLink to="/" class="btn btn-primary">去地图登录</RouterLink>
    </div>

    <template v-else>
      <!-- Header -->
      <div class="travel-header">
        <div class="travel-title">
          📽️ 虾生回放：{{ crawlerStore.userName }}
        </div>
        <RouterLink to="/" class="btn btn-ghost btn-sm">← 返回地图</RouterLink>
      </div>

      <!-- Map + Events -->
      <div class="travel-main">
        <div class="travel-map-wrap">
          <canvas ref="canvasRef" class="travel-canvas" @click="onCanvasClick" />

          <!-- Event card -->
          <Transition name="card-pop">
            <div v-if="activeEvent" class="travel-event-card card">
              <div class="event-card-icon" :class="`icon-${activeEvent.type}`">
                {{ EVENT_ICONS[activeEvent.type] ?? '🐾' }}
              </div>
              <div class="event-card-type">{{ EVENT_LABELS[activeEvent.type] }}</div>
              <div class="event-card-desc">{{ describeEvent(activeEvent) }}</div>
              <div class="event-card-meta">{{ formatTime(activeEvent.ts) }}</div>
              <button class="btn btn-ghost btn-xs event-close" @click="activeIdx = -1">✕</button>
            </div>
          </Transition>

          <!-- Empty events -->
          <div v-if="events.length === 0 && !loading" class="travel-empty">
            🦞<br />还没有事件，开始探索世界吧
          </div>
          <div v-if="loading" class="travel-loading">加载中...</div>
        </div>

        <!-- Event timeline -->
        <div class="travel-timeline">
          <div class="timeline-header">
            📖 事件时间线
            <span class="timeline-count">{{ events.length }} 条</span>
          </div>
          <div class="timeline-list" ref="timelineRef">
            <div
              v-for="(ev, i) in events"
              :key="(ev.ts ?? i) + ev.type + (ev.other_user_id ?? 0)"
              class="timeline-item"
              :class="{ 'tl-active': activeIdx === i, 'tl-done': i < activeIdx }"
              @click="jumpTo(i)"
            >
              <div class="tl-dot" :style="{ background: EVENT_COLORS[ev.type] ?? '#E8623A' }">
                <span class="tl-icon">{{ EVENT_ICONS[ev.type] ?? '🐾' }}</span>
              </div>
              <div class="tl-body">
                <div class="tl-time">{{ formatTime(ev.ts) }}</div>
                <div class="tl-desc">{{ describeEvent(ev) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Timeline scrubber -->
      <div class="travel-controls">
        <div class="ctrl-playback">
          <button class="btn btn-primary" @click="togglePlay">
            {{ playing ? '⏸ 暂停' : '▶ 播放' }}
          </button>
          <button class="btn btn-ghost" @click="reset">⏮ 重置</button>
          <select v-model="speed" class="speed-select">
            <option value="0.5">0.5×</option>
            <option value="1">1×</option>
            <option value="2">2×</option>
            <option value="4">4×</option>
          </select>
        </div>
        <div class="ctrl-scrubber">
          <span class="time-label">{{ startLabel }}</span>
          <input
            type="range"
            class="timeline-scrubber"
            min="0"
            :max="Math.max(0, events.length - 1)"
            v-model.number="activeIdx"
          />
          <span class="time-label">{{ endLabel }}</span>
        </div>
        <div class="ctrl-progress">
          {{ activeIdx + 1 }} / {{ events.length }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import { useCrawlerStore } from '../stores/crawler'
import type { SocialEvent } from '../stores/crawler'

const crawlerStore = useCrawlerStore()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const timelineRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const playing = ref(false)
const activeIdx = ref(0)
const activeEvent = computed(() => events.value[activeIdx.value] ?? null)
const speed = ref('1')

const WORLD_SIZE = 10000

const EVENT_ICONS: Record<string, string> = {
  encounter: '🤝', friendship: '💚', message: '💬', departure: '👋',
}
const EVENT_LABELS: Record<string, string> = {
  encounter: '相遇', friendship: '交友', message: '消息', departure: '离开',
}
const EVENT_COLORS: Record<string, string> = {
  encounter: '#E8623A', friendship: '#3FB950', message: '#4A90D9', departure: '#8B7B6E',
}

// events from crawlerStore (already loaded when user logs in)
const events = computed(() => crawlerStore.events)

const startLabel = computed(() =>
  events.value.length > 0 ? formatTime(events.value[0]!.ts) : '--:--',
)
const endLabel = computed(() =>
  events.value.length > 0 ? formatTime(events.value[events.value.length - 1]!.ts) : '--:--',
)

function describeEvent(ev: SocialEvent): string {
  switch (ev.type) {
    case 'encounter':  return `在(${ev.x ?? '?'},${ev.y ?? '?'})相遇了另一只龙虾`
    case 'friendship': return '与某龙虾建立了友谊 💚'
    case 'message':    return '收到了一条消息'
    case 'departure':  return '某龙虾离开了附近'
    default:           return ev.type
  }
}

function formatTime(iso: string): string {
  if (!iso) return '--:--'
  return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// ── Canvas ────────────────────────────────────────────────────
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
  const cells = 20
  ctx.strokeStyle = 'rgba(232,98,58,0.06)'
  ctx.lineWidth = 0.5
  for (let i = 0; i <= cells; i++) {
    ctx.beginPath()
    ctx.moveTo((i / cells) * w, 0)
    ctx.lineTo((i / cells) * w, h)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(0, (i / cells) * h)
    ctx.lineTo(w, (i / cells) * h)
    ctx.stroke()
  }

  const evs = events.value

  // Past events: small dots + line up to active
  const pastWithCoords = evs.slice(0, activeIdx.value + 1).filter(e => e.x !== null && e.y !== null) as SocialEvent[]

  if (pastWithCoords.length > 1) {
    ctx.beginPath()
    ctx.moveTo((pastWithCoords[0]!.x! / WORLD_SIZE) * w, (pastWithCoords[0]!.y! / WORLD_SIZE) * h)
    for (let i = 1; i < pastWithCoords.length; i++) {
      ctx.lineTo((pastWithCoords[i]!.x! / WORLD_SIZE) * w, (pastWithCoords[i]!.y! / WORLD_SIZE) * h)
    }
    ctx.strokeStyle = 'rgba(232,98,58,0.35)'
    ctx.lineWidth = 1.5
    ctx.stroke()
  }

  // All event dots (past = small, future = tiny)
  for (let i = 0; i < evs.length; i++) {
    const ev = evs[i]!
    if (ev.x === null || ev.y === null) continue
    const px = (ev.x / WORLD_SIZE) * w
    const py = (ev.y / WORLD_SIZE) * h
    const color = EVENT_COLORS[ev.type] ?? '#E8623A'

    if (i === activeIdx.value) {
      // Active: big bubble + animated pulse ring
      const phase = (performance.now() % 1500) / 1500
      ctx.beginPath()
      ctx.arc(px, py, 12, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()
      // Pulse ring: expands from 12 to 32px over 1.5s
      const pulseR = 12 + phase * 20
      const pulseAlpha = Math.max(0, 0.6 * (1 - phase))
      ctx.beginPath()
      ctx.arc(px, py, pulseR, 0, Math.PI * 2)
      ctx.strokeStyle = color
      ctx.lineWidth = 1.5
      ctx.globalAlpha = pulseAlpha
      ctx.stroke()
      ctx.globalAlpha = 1
      // Icon
      ctx.font = '14px serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(EVENT_ICONS[ev.type] ?? '🐾', px, py)
    } else if (i < activeIdx.value) {
      // Done: small colored dot
      ctx.beginPath()
      ctx.arc(px, py, 4, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()
    } else {
      // Future: faint tiny dot
      ctx.beginPath()
      ctx.arc(px, py, 2, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(232,98,58,0.2)'
      ctx.fill()
    }
  }
}

function onCanvasClick(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const px = e.clientX - rect.left
  const py = e.clientY - rect.top
  const w = rect.width, h = rect.height

  // Hit test
  for (let i = 0; i < events.value.length; i++) {
    const ev = events.value[i]!
    if (ev.x === null || ev.y === null) continue
    const bx = (ev.x / WORLD_SIZE) * w
    const by = (ev.y / WORLD_SIZE) * h
    if (Math.hypot(px - bx, py - by) < 16) {
      activeIdx.value = i
      return
    }
  }
  activeEvent.value // no-op ref access
}

function jumpTo(i: number) {
  activeIdx.value = i
}

// ── Playback ────────────────────────────────────────────────
let playTimer: ReturnType<typeof setInterval> | null = null
let pulseRaf: number | null = null

function startPulseLoop() {
  stopPulseLoop()
  pulseRaf = requestAnimationFrame(function loop() {
    draw()
    pulseRaf = requestAnimationFrame(loop)
  })
}

function stopPulseLoop() {
  if (pulseRaf !== null) {
    cancelAnimationFrame(pulseRaf)
    pulseRaf = null
  }
}

function startPlayback() {
  stopPlayback()
  playTimer = setInterval(() => {
    if (activeIdx.value < events.value.length - 1) {
      activeIdx.value++
    } else {
      stopPlayback()
      playing.value = false
    }
  }, 2000 / Number(speed.value))
}

function stopPlayback() {
  if (playTimer !== null) {
    clearInterval(playTimer)
    playTimer = null
  }
}

function togglePlay() {
  if (playing.value) {
    stopPlayback()
    playing.value = false
  } else {
    if (activeIdx.value >= events.value.length - 1) activeIdx.value = 0
    startPlayback()
    playing.value = true
  }
}

function reset() {
  stopPlayback()
  playing.value = false
  activeIdx.value = 0
}

watch(activeIdx, async () => {
  draw()
  // Auto-scroll timeline to active item
  await nextTick()
  const list = timelineRef.value
  if (!list) return
  const items = list.querySelectorAll<HTMLElement>('.timeline-item')
  const el = items[activeIdx.value]
  if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})
watch(speed, () => {
  if (playing.value) { stopPlayback(); startPlayback() }
})

onMounted(async () => {
  if (!crawlerStore.events.length) {
    loading.value = true
    await crawlerStore.loadSocial('30d')
    loading.value = false
  }
  draw()
  startPulseLoop()
})

onUnmounted(() => { stopPlayback(); stopPulseLoop() })
</script>

<style scoped>
.travel-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg);
  overflow: hidden;
}

.travel-redirect {
  margin: auto;
  text-align: center;
  padding: var(--space-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
}
.redirect-title {
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 700;
}

.travel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-xs) var(--space-md);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.travel-title {
  font-family: var(--font-display);
  font-size: 0.9rem;
  font-weight: 700;
}
.btn-sm { padding: 2px var(--space-sm); font-size: 0.75rem; min-height: 28px; }

.travel-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.travel-map-wrap {
  flex: 1;
  position: relative;
  overflow: hidden;
}
.travel-canvas {
  width: 100%;
  height: 100%;
  display: block;
  cursor: crosshair;
}
.travel-empty, .travel-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-display);
  font-size: 1rem;
  color: var(--color-text-muted);
  text-align: center;
  pointer-events: none;
}

/* Event card */
.travel-event-card {
  position: absolute;
  top: var(--space-md);
  left: var(--space-md);
  width: min(220px, calc(100vw - 280px));
  padding: var(--space-sm);
  z-index: 20;
}
.event-card-icon { font-size: 1.8rem; margin-bottom: 4px; }
.event-card-type {
  font-family: var(--font-display);
  font-size: 0.9rem;
  font-weight: 700;
  margin-bottom: 2px;
}
.event-card-desc { font-size: 0.75rem; margin-bottom: 4px; }
.event-card-meta { font-size: 0.65rem; color: var(--color-text-muted); font-family: var(--font-data); }
.event-close {
  position: absolute;
  top: 4px;
  right: 4px;
}

/* Timeline */
.travel-timeline {
  width: 220px;
  flex-shrink: 0;
  background: var(--color-surface);
  border-left: 1.5px solid var(--color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.timeline-header {
  padding: var(--space-xs) var(--space-sm);
  font-family: var(--font-display);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-muted);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}
.timeline-count {
  font-size: 0.6rem;
  background: var(--color-border);
  padding: 0 4px;
  border-radius: 99px;
}
.timeline-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-xs);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-xs);
  padding: 4px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
}
.timeline-item:hover { background: var(--color-border); }
.tl-active { background: rgba(232,98,58,0.12); }
.tl-done { opacity: 0.7; }
.tl-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.tl-icon { font-size: 10px; }
.tl-body { flex: 1; min-width: 0; }
.tl-time {
  font-family: var(--font-data);
  font-size: 0.65rem;
  color: var(--color-text-muted);
}
.tl-desc {
  font-size: 0.7rem;
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Controls */
.travel-controls {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-xs) var(--space-md);
  background: var(--color-surface);
  border-top: 1.5px solid var(--color-border);
  flex-shrink: 0;
  flex-wrap: wrap;
}
.ctrl-playback { display: flex; align-items: center; gap: var(--space-xs); }
.ctrl-scrubber {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  min-width: 200px;
}
.time-label {
  font-family: var(--font-data);
  font-size: 0.7rem;
  color: var(--color-text-muted);
  white-space: nowrap;
}
.timeline-scrubber {
  flex: 1;
  cursor: pointer;
  accent-color: var(--color-primary);
  height: 4px;
}
.speed-select {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 2px var(--space-xs);
  font-size: 0.75rem;
  color: var(--color-text);
  cursor: pointer;
}
.ctrl-progress {
  font-family: var(--font-data);
  font-size: 0.7rem;
  color: var(--color-text-muted);
  white-space: nowrap;
}

/* Transitions */
.card-pop-enter-active { transition: opacity 0.2s, transform 0.2s; }
.card-pop-enter-from { opacity: 0; transform: scale(0.9); }
</style>
