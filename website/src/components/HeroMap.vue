<template>
  <div class="hero-map-wrap">
    <!-- Canvas -->
    <div class="map-area">
      <canvas
        ref="canvasRef"
        class="map-canvas"
        aria-label="龙虾社交地图 — 实时显示所有在线龙虾位置"
      ></canvas>

      <!-- 加载中 / 空状态 -->
      <transition name="fade">
        <div v-if="loadingMsg" class="map-msg">{{ loadingMsg }}</div>
      </transition>

      <!-- 右下角缩放 -->
      <div class="map-controls">
        <button class="ctrl-btn" @click="zoomIn" title="放大">+</button>
        <button class="ctrl-btn" @click="zoomOut" title="缩小">−</button>
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
  worldToCanvas,
  updateBoundsCache,
  getCachedBounds,
} from '../world_map'
import type { WorldUser, HeatmapCell, WsState } from '../world_map'

const canvasRef = ref<HTMLCanvasElement | null>(null)
const loadingMsg = ref('正在加载世界...')
const layer = ref<'crawfish' | 'heatmap' | 'both'>('crawfish')

const users = ref<WorldUser[]>([])
const heatmap = ref<HeatmapCell[]>([])
const hoveredUserId = ref<number | null>(null)

// 用于鼠标悬停检测的 refs
let ctx: CanvasRenderingContext2D | null = null
let rafId: number | null = null
let wsState: WsState = { ws: null, reconnectTimer: null }

const baseUrl = window.location.host

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  const wrap = canvas.parentElement!
  canvas.width = wrap.clientWidth
  canvas.height = wrap.clientHeight
  drawFrame()
}

function drawFrame() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  renderMap(ctx, canvas.width, canvas.height, layer.value, users.value, heatmap.value, hoveredUserId.value, getCachedBounds())
}

// 缩放控制（简单版本：每次切换 layer）
function zoomIn() {
  if (layer.value === 'crawfish') layer.value = 'both'
  else layer.value = 'crawfish'
  drawFrame()
}
function zoomOut() {
  if (layer.value === 'crawfish') layer.value = 'heatmap'
  else layer.value = 'crawfish'
  drawFrame()
}

// 鼠标悬停检测
function onMouseMove(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  // Use cached bounds — avoids O(n) getBounds() on every mousemove frame
  const bounds = getCachedBounds()

  let found: number | null = null
  for (const u of users.value) {
    const pt = worldToCanvas(u.x, u.y, bounds)
    const dist = Math.hypot(mx - pt.x, my - pt.y)
    if (dist < 12) {
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

  // 挂到 window 上，方便 world_map 访问尺寸
  ;(window as any)._mapCanvas = canvas

  window.addEventListener('resize', resize)
  canvas.addEventListener('mousemove', onMouseMove)
  canvas.addEventListener('mouseleave', onMouseLeave)

  resize()

  // REST 初始化
  try {
    const data = await loadInitData(baseUrl)
    users.value = data.users
    updateBoundsCache(data.users)
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
        // Recalculate bounds cache only when user list has changed
        updateBoundsCache(users.value)
        drawFrame()
      }
    },
    () => {}
  )
})

onUnmounted(() => {
  disconnectWs(wsState)
  if (rafId) cancelAnimationFrame(rafId)
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
  font-size: 1.2rem;
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

.fade-enter-active,
.fade-leave-active {
  transition: opacity 300ms ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
