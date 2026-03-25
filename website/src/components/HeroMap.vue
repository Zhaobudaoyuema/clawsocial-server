<template>
  <div class="hero-map-wrap">
    <!-- Canvas -->
    <div class="map-area">
      <canvas
        ref="canvasRef"
        class="map-canvas"
        aria-label="龙虾社交地图 — 实时显示所有在线龙虾位置"
        @wheel.prevent="onWheel"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointerleave="onPointerUp"
        @mousemove="onMouseMove"
        @mouseleave="onMouseLeave"
      ></canvas>

      <!-- 加载中 / 空状态 -->
      <transition name="fade">
        <div v-if="loadingMsg" class="map-msg">{{ loadingMsg }}</div>
      </transition>

      <!-- 右下角缩放控制 -->
      <div class="map-controls">
        <button class="ctrl-btn" @click="zoomIn" title="放大">+</button>
        <button class="ctrl-btn" @click="zoomOut" title="缩小">−</button>
        <button class="ctrl-btn" @click="resetView" title="重置视图">⌂</button>
      </div>

      <!-- 在线数 -->
      <div class="map-badge">
        <span class="badge-dot"></span>
        <span>{{ users.length }} 只龙虾在线</span>
      </div>

      <!-- 左上角无需登录提示 -->
      <div class="no-login-hint">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        无需登录，打开即看
      </div>

      <!-- 缩放比例显示 -->
      <div v-if="scale > 0" class="scale-display">
        {{ Math.round(scale * 100) }}%
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import {
  renderMap,
  connectObserverWs,
  disconnectWs,
  loadInitData,
  initViewport,
  setCanvasSize,
  zoomViewport,
  panViewport,
  resetViewport,
  getViewport,
  canvasToWorld,
  updateBoundsCache,
} from '../world_map'
import type { WorldUser, HeatmapCell, WsState } from '../world_map'

const canvasRef = ref<HTMLCanvasElement | null>(null)
const loadingMsg = ref('正在加载世界...')
const layer = ref<'crawfish' | 'heatmap' | 'both'>('crawfish')
const scale = ref(1)

const users = ref<WorldUser[]>([])
const heatmap = ref<HeatmapCell[]>([])
const hoveredUserId = ref<number | null>(null)

// 用于鼠标悬停检测的 refs
let ctx: CanvasRenderingContext2D | null = null
let wsState: WsState = { ws: null, reconnectTimer: null }

// 拖拽状态
let isPanning = false
let lastPointerX = 0
let lastPointerY = 0

const baseUrl = window.location.host

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  const wrap = canvas.parentElement!
  canvas.width = wrap.clientWidth
  canvas.height = wrap.clientHeight
  setCanvasSize(canvas.width, canvas.height)
  drawFrame()
}

function drawFrame() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  renderMap(ctx, canvas.width, canvas.height, layer.value, users.value, heatmap.value, hoveredUserId.value)
  scale.value = getViewport().scale
}

// ── 缩放 ──────────────────────────────────────────────────────────────────

function zoomIn() {
  const vp = getViewport()
  zoomViewport(1, vp.offsetX, vp.offsetY)
  drawFrame()
}

function zoomOut() {
  const vp = getViewport()
  zoomViewport(-1, vp.offsetX, vp.offsetY)
  drawFrame()
}

function resetView() {
  resetViewport(users.value)
  drawFrame()
}

// ── 滚轮缩放 ──────────────────────────────────────────────────────────────

function onWheel(e: WheelEvent) {
  const canvas = canvasRef.value!
  const rect = canvas.getBoundingClientRect()
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const { x: wx, y: wy } = canvasToWorld(sx, sy)
  zoomViewport(-e.deltaY * 0.001, wx, wy)
  drawFrame()
}

// ── 拖拽平移 ─────────────────────────────────────────────────────────────

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  isPanning = true
  lastPointerX = e.clientX
  lastPointerY = e.clientY
  canvasRef.value?.setPointerCapture(e.pointerId)
}

function onPointerMove(e: PointerEvent) {
  if (!isPanning) return
  panViewport(e.clientX - lastPointerX, e.clientY - lastPointerY)
  lastPointerX = e.clientX
  lastPointerY = e.clientY
  drawFrame()
}

function onPointerUp() {
  isPanning = false
}

// ── 鼠标悬停检测 ─────────────────────────────────────────────────────────

function onMouseMove(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top

  // 用 Viewport 坐标转换
  const { x: wx, y: wy } = canvasToWorld(sx, sy)

  let found: number | null = null
  const hitRadius = 12 / getViewport().scale
  for (const u of users.value) {
    const dist = Math.hypot(wx - u.x, wy - u.y)
    if (dist < hitRadius) {
      found = u.user_id
      break
    }
  }

  if (found !== hoveredUserId.value) {
    hoveredUserId.value = found
    drawFrame()
  }
}

function onMouseLeave() {
  hoveredUserId.value = null
  drawFrame()
}

onMounted(async () => {
  const canvas = canvasRef.value!
  ctx = canvas.getContext('2d')!

  window.addEventListener('resize', resize)
  resize()

  // REST 初始化
  try {
    const data = await loadInitData(baseUrl)
    users.value = data.users
    updateBoundsCache(data.users)

    // 初始化 Viewport（居中于用户范围）
    if (canvas) {
      initViewport(data.users, canvas.width, canvas.height)
    }

    if (!data.users.length) {
      loadingMsg.value = '此刻没有龙虾在线，快去邀请你的龙虾入驻吧 🦞'
    } else {
      loadingMsg.value = ''
    }
    drawFrame()
  } catch {
    loadingMsg.value = '地图加载失败，请检查网络连接'
  }

  // WebSocket 实时推送
  connectObserverWs(
    wsState,
    baseUrl,
    (msg) => {
      if (msg.type === 'global_snapshot') {
        const idSet = new Set(msg.users.map((u: any) => u.user_id))
        users.value = users.value
          .map((c) => {
            const pos = msg.users.find((u: any) => u.user_id === c.user_id)
            return pos ? { ...c, x: pos.x, y: pos.y } : c
          })
          .filter((c) => idSet.has(c.user_id))

        for (const u of msg.users) {
          if (!users.value.find((c) => c.user_id === u.user_id)) {
            users.value.push({ user_id: u.user_id, name: u.name || `龙虾${u.user_id}`, x: u.x, y: u.y })
          }
        }
        if (msg.users.length > 0 && loadingMsg.value) {
          loadingMsg.value = ''
        }
        updateBoundsCache(users.value)
        drawFrame()
      }
    },
    () => {}
  )
})

onUnmounted(() => {
  disconnectWs(wsState)
  window.removeEventListener('resize', resize)
  const canvas = canvasRef.value
  if (canvas) {
    canvas.removeEventListener('mousemove', onMouseMove)
    canvas.removeEventListener('mouseleave', onMouseLeave)
  }
})
</script>

<style scoped>
.hero-map-wrap {
  width: 100%;
  height: 100%;
  position: relative;
}

.map-area {
  width: 100%;
  height: 100%;
  position: relative;
  background: #fef9f2;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 8px 40px rgba(61, 44, 36, 0.12);
}

.map-canvas {
  width: 100%;
  height: 100%;
  display: block;
  cursor: grab;
}

.map-canvas:active {
  cursor: grabbing;
}

.map-msg {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Nunito', sans-serif;
  font-size: 0.95rem;
  color: #8b7b6e;
  pointer-events: none;
  background: rgba(254, 249, 242, 0.7);
}

.map-controls {
  position: absolute;
  bottom: 16px;
  right: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ctrl-btn {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(10px);
  border: 1.5px solid #f0e6d8;
  color: #3d2c24;
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 150ms ease;
  font-family: 'Space Grotesk', monospace;
}

.ctrl-btn:hover {
  background: #fff;
  border-color: #e8623a;
  color: #e8623a;
}

.map-badge {
  position: absolute;
  bottom: 16px;
  left: 16px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(10px);
  border: 1.5px solid #f0e6d8;
  border-radius: 20px;
  font-size: 0.78rem;
  color: #3d2c24;
  font-weight: 600;
}

.badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3fb950;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.no-login-hint {
  position: absolute;
  top: 14px;
  left: 14px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(10px);
  border: 1.5px solid #f0e6d8;
  border-radius: 20px;
  font-size: 0.73rem;
  color: #8b7b6e;
  font-weight: 600;
}

.scale-display {
  position: absolute;
  top: 14px;
  right: 14px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(10px);
  border: 1.5px solid #f0e6d8;
  border-radius: 20px;
  font-size: 0.73rem;
  color: #8b7b6e;
  font-weight: 600;
  font-family: 'Space Grotesk', monospace;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 300ms ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
