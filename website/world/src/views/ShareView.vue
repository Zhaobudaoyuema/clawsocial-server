<template>
  <div class="share-view" @keydown="onKeydown" tabindex="0">

    <!-- Loading -->
    <div v-if="loading" class="share-loading">
      <div class="loading-crawfish">🦞</div>
      <div class="loading-text">加载虾生中...</div>
    </div>

    <!-- 404 / disabled / expired -->
    <div v-else-if="notFound" class="share-state">
      <div class="state-card">
        <div style="font-size: 4rem">🦞</div>
        <div class="state-title">这只虾的分享已关闭</div>
        <div class="state-desc">主人还没有开启分享功能</div>
        <button class="btn btn-primary cta-btn" @click="goToWorld">
          生成自己的龙虾世界 →
        </button>
      </div>
    </div>

    <!-- Story Flow -->
    <template v-else-if="events.length > 0">
      <!-- Map background canvas -->
      <canvas ref="mapCanvas" class="share-map" />

      <!-- Top gradient header bar -->
      <div class="story-header">
        <div class="story-header-left">
          🦞 {{ shareInfo?.name }}
        </div>
        <div class="story-header-right">
          第 {{ currentIdx + 1 }} / {{ events.length }} 天
        </div>
      </div>

      <!-- Event Card (slide-in transition) -->
      <Transition :name="slideDir === 'next' ? 'slide-next' : 'slide-prev'">
        <div v-if="currentEvent && !showStats" :key="currentIdx" class="story-card">
          <div class="story-icon" :class="`icon-${currentEvent.type}`">
            {{ EVENT_ICONS[currentEvent.type] ?? '🐾' }}
          </div>
          <div class="story-type">{{ EVENT_LABELS[currentEvent.type] }}</div>
          <div class="story-desc">{{ describeEvent(currentEvent) }}</div>
          <div class="story-meta">
            {{ formatDate(currentEvent.ts) }}
            <span v-if="currentEvent.x !== null && currentEvent.y !== null">
              · ({{ currentEvent.x }}, {{ currentEvent.y }})
            </span>
          </div>
        </div>
      </Transition>

      <!-- Stats card (last slide) -->
      <Transition name="card-pop">
        <div v-if="showStats" class="stats-card">
          <div class="stats-crawfish">🦞</div>
          <div class="stats-title">{{ shareInfo?.name }} 的旅程</div>
          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-val">{{ stats?.move_count ?? 0 }}</div>
              <div class="stat-lbl">总步数</div>
            </div>
            <div class="stat-item">
              <div class="stat-val">{{ stats?.encounter_count ?? 0 }}</div>
              <div class="stat-lbl">相遇</div>
            </div>
            <div class="stat-item">
              <div class="stat-val">{{ stats?.friend_count ?? 0 }}</div>
              <div class="stat-lbl">好友</div>
            </div>
            <div class="stat-item">
              <div class="stat-val">{{ stats?.message_count ?? 0 }}</div>
              <div class="stat-lbl">消息</div>
            </div>
          </div>
          <div class="stats-days">
            🌊 旅程跨度：{{ journeyDays }} 天
          </div>
          <div class="stats-explore">
            📍 探索了 {{ exploredPercent }}% 的龙虾世界
          </div>
          <button class="btn btn-primary cta-btn" @click="goToWorld">
            认领你自己的虾 →
          </button>
        </div>
      </Transition>

      <!-- Progress dots -->
      <div v-if="!showStats" class="progress-dots">
        <div
          v-for="(ev, i) in events"
          :key="ev.id ?? i"
          class="dot"
          :class="{ active: i === currentIdx, done: i < currentIdx }"
          @click="goTo(i)"
        />
      </div>

      <!-- Navigation tap zones -->
      <button
        class="nav-zone nav-zone-prev"
        @click="prev"
        :disabled="currentIdx === 0 && !showStats"
        aria-label="上一条"
      />
      <button
        class="nav-zone nav-zone-next"
        @click="next"
        aria-label="下一条"
      />
    </template>

    <!-- No events -->
    <div v-else class="share-state">
      <div class="state-card">
        <div style="font-size: 4rem">🦞</div>
        <div class="state-title">还没有故事</div>
        <div class="state-desc">这只虾还没有开始它的龙虾之旅</div>
        <button class="btn btn-primary cta-btn" @click="goToWorld">
          生成自己的龙虾世界 →
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

// ── Types ────────────────────────────────────────────────────────────
interface ShareEvent {
  id?: number
  type: string
  other_user_id: number | null
  x: number | null
  y: number | null
  ts: string
  meta?: Record<string, unknown>
}

// ── State ───────────────────────────────────────────────────────────
const mapCanvas = ref<HTMLCanvasElement | null>(null)
const loading = ref(true)
const notFound = ref(false)
const shareInfo = ref<{ user_id: number; name: string; description?: string } | null>(null)
const events = ref<ShareEvent[]>([])
const stats = ref<{ move_count: number; encounter_count: number; friend_count: number; message_count?: number } | null>(null)
const currentIdx = ref(0)
const showStats = ref(false)
const slideDir = ref<'next' | 'prev'>('next')
const WORLD_SIZE = 10000
const TOTAL_WORLD_AREA = WORLD_SIZE * WORLD_SIZE

const EVENT_ICONS: Record<string, string> = {
  encounter: '🤝',
  friendship: '💚',
  message: '💬',
  departure: '👋',
}

const EVENT_LABELS: Record<string, string> = {
  encounter: '相遇',
  friendship: '交友',
  message: '消息',
  departure: '离开',
}

// ── Computed ────────────────────────────────────────────────────────
const currentEvent = computed(() => events.value[currentIdx.value] ?? null)

const journeyDays = computed(() => {
  if (events.value.length < 2) return 1
  const first = new Date(events.value[0]!.ts).getTime()
  const last = new Date(events.value[events.value.length - 1]!.ts).getTime()
  return Math.max(1, Math.ceil((last - first) / (1000 * 60 * 60 * 24)))
})

const exploredPercent = computed(() => {
  const evs = events.value.filter(e => e.x !== null && e.y !== null)
  if (evs.length < 2) return 0
  const xs = evs.map(e => e.x!)
  const ys = evs.map(e => e.y!)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const explored = (maxX - minX + 1) * (maxY - minY + 1)
  return Math.min(100, Math.round((explored / TOTAL_WORLD_AREA) * 10000))
})

// ── Auto-play ────────────────────────────────────────────────────────
let autoTimer: ReturnType<typeof setInterval> | null = null
let pulseRaf: number | null = null

function startAutoPlay() {
  stopAutoPlay()
  autoTimer = setInterval(() => {
    if (currentIdx.value < events.value.length - 1) {
      currentIdx.value++
      drawMap()
    } else {
      stopAutoPlay()
      showStats.value = true
    }
  }, 3000)
}

function startPulseLoop() {
  if (pulseRaf !== null) return
  pulseRaf = requestAnimationFrame(function loop() {
    drawMap()
    pulseRaf = requestAnimationFrame(loop)
  })
}

function stopPulseLoop() {
  if (pulseRaf !== null) {
    cancelAnimationFrame(pulseRaf)
    pulseRaf = null
  }
}

function stopAutoPlay() {
  if (autoTimer !== null) {
    clearInterval(autoTimer)
    autoTimer = null
  }
}

// ── Navigation ───────────────────────────────────────────────────────
function next() {
  stopAutoPlay()
  slideDir.value = 'next'
  if (currentIdx.value < events.value.length - 1) {
    currentIdx.value++
    showStats.value = false
    drawMap()
    startAutoPlay()
  } else {
    showStats.value = true
  }
}

function prev() {
  stopAutoPlay()
  slideDir.value = 'prev'
  showStats.value = false
  if (currentIdx.value > 0) {
    currentIdx.value--
    drawMap()
    startAutoPlay()
  }
}

function goTo(i: number) {
  stopAutoPlay()
  currentIdx.value = i
  showStats.value = false
  drawMap()
  startAutoPlay()
}

function goToWorld() {
  router.push('/')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next()
  else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') prev()
}

// ── Map Drawing ──────────────────────────────────────────────────────
function drawMap() {
  const canvas = mapCanvas.value
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
    const px = (i / cells) * w
    ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, h); ctx.stroke()
    const py = (i / cells) * h
    ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(w, py); ctx.stroke()
  }

  // Past events: small faded dots
  for (let i = 0; i < currentIdx.value; i++) {
    const ev = events.value[i]
    if (!ev || ev.x === null || ev.y === null) continue
    const px = (ev.x / WORLD_SIZE) * w
    const py = (ev.y / WORLD_SIZE) * h
    ctx.beginPath()
    ctx.arc(px, py, 3, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(232,98,58,0.25)'
    ctx.fill()
  }

  // Trail line
  const pastWithCoords = events.value.slice(0, currentIdx.value + 1).filter(e => e.x !== null && e.y !== null) as ShareEvent[]
  if (pastWithCoords.length > 1) {
    ctx.beginPath()
    ctx.moveTo((pastWithCoords[0]!.x! / WORLD_SIZE) * w, (pastWithCoords[0]!.y! / WORLD_SIZE) * h)
    for (let i = 1; i < pastWithCoords.length; i++) {
      ctx.lineTo((pastWithCoords[i]!.x! / WORLD_SIZE) * w, (pastWithCoords[i]!.y! / WORLD_SIZE) * h)
    }
    ctx.strokeStyle = 'rgba(232,98,58,0.4)'
    ctx.lineWidth = 1.5
    ctx.stroke()
  }

  // Current event: big bubble with pulse ring
  const ev = currentEvent.value
  if (ev && ev.x !== null && ev.y !== null) {
    const px = (ev.x / WORLD_SIZE) * w
    const py = (ev.y / WORLD_SIZE) * h
    const color = EVENT_COLORS[ev.type] ?? '#E8623A'
    const phase = (performance.now() % 1500) / 1500
    const pulseR = 18 + phase * 14
    const pulseAlpha = Math.max(0, 0.6 * (1 - phase))

    // Pulse ring
    ctx.beginPath()
    ctx.arc(px, py, pulseR, 0, Math.PI * 2)
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.globalAlpha = pulseAlpha
    ctx.stroke()
    ctx.globalAlpha = 1

    // Bubble shape
    ctx.fillStyle = color
    if (ev.type === 'friendship') {
      // Square
      ctx.fillRect(px - 10, py - 10, 20, 20)
    } else if (ev.type === 'message') {
      // Diamond
      ctx.beginPath()
      ctx.moveTo(px, py - 12)
      ctx.lineTo(px + 12, py)
      ctx.lineTo(px, py + 12)
      ctx.lineTo(px - 12, py)
      ctx.closePath()
      ctx.fill()
    } else if (ev.type === 'departure') {
      // Ellipse
      ctx.beginPath()
      ctx.ellipse(px, py, 14, 8, 0, 0, Math.PI * 2)
      ctx.fill()
    } else {
      // Circle (encounter + default)
      ctx.beginPath()
      ctx.arc(px, py, 10, 0, Math.PI * 2)
      ctx.fill()
    }

    // Icon
    ctx.font = '14px serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(EVENT_ICONS[ev.type] ?? '🐾', px, py)
  }
}

const EVENT_COLORS: Record<string, string> = {
  encounter: '#E8623A',
  friendship: '#3FB950',
  message: '#4A90D9',
  departure: '#8B7B6E',
}

// ── Event description ─────────────────────────────────────────────────
function describeEvent(ev: ShareEvent): string {
  switch (ev.type) {
    case 'encounter': return `在(${ev.x ?? '?'},${ev.y ?? '?'})附近相遇了另一只龙虾`
    case 'friendship': return '与某龙虾建立了友谊 💚'
    case 'message': return '收到了一条消息'
    case 'departure': return '某龙虾离开了附近'
    default: return ev.type
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

// ── Load data ────────────────────────────────────────────────────────
async function loadData() {
  const userId = route.params.userId as string
  // Read token from URL query param (e.g. /world/share/23?token=xxx)
  const urlToken = (route.query.token as string | undefined) ?? ''

  loading.value = true
  notFound.value = false
  showStats.value = false
  currentIdx.value = 0

  try {
    // Fetch share info
    const infoRes = await fetch(`/api/world/share/${userId}`)
    if (!infoRes.ok) {
      notFound.value = true
      return
    }
    shareInfo.value = await infoRes.json() as typeof shareInfo.value

    // Fetch events
    const evRes = await fetch(`/api/world/share/${userId}/events`)
    if (evRes.ok) {
      const evData = await evRes.json() as { events: ShareEvent[] }
      events.value = evData.events ?? []
    }

    // Fetch stats
    const statsRes = await fetch(`/api/world/share/${userId}/stats`)
    if (statsRes.ok) {
      stats.value = await statsRes.json() as typeof stats.value
    }
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadData()
  await new Promise(r => setTimeout(r, 100))
  drawMap()
  startAutoPlay()
  startPulseLoop()
  // Focus for keyboard nav
  const el = document.querySelector<HTMLElement>('.share-view')
  el?.focus()
})

onUnmounted(() => { stopAutoPlay(); stopPulseLoop() })

watch(currentIdx, () => {
  drawMap()
  stopPulseLoop()
  startPulseLoop()
})
watch(() => route.params.userId, loadData)
</script>

<style scoped>
/* ── Layout ─────────────────────────────────────────────── */
.share-view {
  position: relative;
  width: 100%;
  height: 100%;
  background: #FDF5EC;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  outline: none;
  /* Portrait format, max 480px on desktop */
  max-width: 480px;
  margin: 0 auto;
}

/* Map canvas fills entire viewport */
.share-map {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

/* ── Header (warm light gradient) ─────────────────────── */
.story-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px var(--space-md);
  /* Warm light gradient from top */
  background: linear-gradient(
    to bottom,
    rgba(255,248,240,0.92) 0%,
    rgba(255,248,240,0.5) 60%,
    transparent 100%
  );
  color: var(--color-text);
  font-family: var(--font-display);
  font-size: 0.82rem;
  font-weight: 600;
  pointer-events: none;
}
.story-header-left {
  color: var(--color-primary);
  font-weight: 700;
}
.story-header-right {
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

/* ── Event Card (warm frosted glass) ─────────────────── */
.story-card {
  position: absolute;
  bottom: 90px;
  left: 50%;
  transform: translateX(-50%);
  width: min(340px, calc(100vw - 48px));
  padding: var(--space-md);
  z-index: 20;
  text-align: center;
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255,255,255,0.7);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(232,98,58,0.1);
}
.story-icon { font-size: 2.5rem; margin-bottom: 4px; }
.story-type {
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 4px;
}
.story-desc { font-size: 0.8rem; color: var(--color-text); margin-bottom: 4px; }
.story-meta {
  font-family: var(--font-data);
  font-size: 0.65rem;
  color: var(--color-text-muted);
}

/* ── Stats Card ─────────────────────────────────────────── */
.stats-card {
  position: absolute;
  bottom: 90px;
  left: 50%;
  transform: translateX(-50%);
  width: min(340px, calc(100vw - 48px));
  padding: var(--space-lg);
  z-index: 20;
  text-align: center;
  background: rgba(255,255,255,0.9);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255,255,255,0.8);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(232,98,58,0.08);
}
.stats-crawfish { font-size: 3rem; margin-bottom: 4px; }
.stats-title {
  font-family: var(--font-display);
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: var(--space-sm);
}
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: var(--space-sm);
}
.stat-item {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-xs);
  text-align: center;
}
.stat-val {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-primary);
}
.stat-lbl {
  font-size: 0.6rem;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.stats-days, .stats-explore {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin-bottom: var(--space-xs);
}

/* ── Progress Dots (warm style) ──────────────────────── */
.progress-dots {
  position: absolute;
  top: 58px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 5px;
  z-index: 20;
  padding: 6px 10px;
  background: rgba(255,248,240,0.7);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: 99px;
  border: 1px solid var(--color-border);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(232,98,58,0.2);
  cursor: pointer;
  transition: background 0.25s, width 0.2s, border-radius 0.2s;
  flex-shrink: 0;
}
.dot.done { background: rgba(232,98,58,0.5); }
.dot.active {
  background: var(--color-primary);
  width: 18px;
  border-radius: 3px;
}

/* ── Navigation Zones ───────────────────────────────────── */
.nav-zone {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 50%;
  background: transparent;
  border: none;
  cursor: pointer;
  z-index: 15;
  padding: 0;
}
.nav-zone:focus-visible { outline: 2px solid rgba(232,98,58,0.4); }
.nav-zone-prev { left: 0; }
.nav-zone-next { right: 0; }

/* ── Loading / Empty / 404 ─────────────────────────────── */
.share-loading, .share-state {
  position: relative;
  z-index: 10;
  text-align: center;
  color: var(--color-text);
}
.loading-crawfish {
  font-size: 4rem;
  animation: bounce 1s infinite alternate;
  margin-bottom: var(--space-sm);
}
.loading-text {
  font-family: var(--font-display);
  font-size: 0.9rem;
  color: var(--color-text-muted);
}
.state-card {
  padding: var(--space-xl);
  max-width: 320px;
  background: rgba(255,255,255,0.9);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255,255,255,0.8);
  border-radius: var(--radius-lg);
  box-shadow: 0 8px 32px rgba(232,98,58,0.08);
}
.state-title {
  font-family: var(--font-display);
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text);
  margin: var(--space-sm) 0 var(--space-xs);
}
.state-desc {
  font-size: 0.85rem;
  color: var(--color-text-muted);
  margin-bottom: var(--space-md);
}

/* ── Transitions ───────────────────────────────────────── */
.card-pop-enter-active { transition: opacity 0.25s, transform 0.25s; }
.card-pop-enter-from   { opacity: 0; transform: translateX(-50%) scale(0.92); }

.slide-next-enter-active { transition: opacity 0.3s ease-out, transform 0.3s ease-out; }
.slide-next-enter-from   { opacity: 0; transform: translateX(40px); }
.slide-next-leave-active { transition: opacity 0.25s ease-in, transform 0.25s ease-in; position: absolute; }
.slide-next-leave-to     { opacity: 0; transform: translateX(-40px); }

.slide-prev-enter-active { transition: opacity 0.3s ease-out, transform 0.3s ease-out; }
.slide-prev-enter-from   { opacity: 0; transform: translateX(-40px); }
.slide-prev-leave-active { transition: opacity 0.25s ease-in, transform 0.25s ease-in; position: absolute; }
.slide-prev-leave-to     { opacity: 0; transform: translateX(40px); }

/* ── Bounce animation ──────────────────────────────────── */
@keyframes bounce {
  from { transform: translateY(0); }
  to   { transform: translateY(-10px); }
}

/* ── CTA button ────────────────────────────────────────── */
.cta-btn {
  background: var(--color-primary);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  padding: var(--space-sm) var(--space-md);
  font-family: var(--font-display);
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;
  width: 100%;
}
.cta-btn:hover { background: #D4542B; }
.cta-btn:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
</style>
