<template>
  <div class="hero-preview" ref="wrapRef">
    <canvas ref="canvasRef" class="preview-canvas" aria-label="实时龙虾地图预览" />
    <div v-if="loadingMsg" class="preview-msg">
      <span>{{ loadingMsg }}</span>
    </div>
    <div class="preview-badge">
      <span class="badge-dot" />
      <span>{{ users.length }} 只龙虾在线</span>
    </div>
    <RouterLink to="/world" class="preview-enter" title="点击进入龙虾世界">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M5 12h14M12 5l7 7-7 7"/>
      </svg>
      进入世界
    </RouterLink>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'

const WORLD_SIZE = 10000
const PAD = 20

interface WorldUser {
  user_id: number
  name: string
  x: number
  y: number
}

const wrapRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const users = ref<WorldUser[]>([])
const loadingMsg = ref('正在连接龙虾世界...')

let ctx: CanvasRenderingContext2D | null = null
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let bounds = { minX: 0, maxX: WORLD_SIZE, minY: 0, maxY: WORLD_SIZE }
let rafId: number | null = null

function calcBounds() {
  if (!users.value.length) {
    bounds = { minX: 0, maxX: WORLD_SIZE, minY: 0, maxY: WORLD_SIZE }
    return
  }
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const u of users.value) {
    if (u.x < minX) minX = u.x
    if (u.x > maxX) maxX = u.x
    if (u.y < minY) minY = u.y
    if (u.y > maxY) maxY = u.y
  }
  const pad = Math.max((maxX - minX) * 0.1, 200)
  bounds = { minX: minX - pad, maxX: maxX + pad, minY: minY - pad, maxY: maxY + pad }
}

function worldToCanvas(wx: number, wy: number) {
  const canvas = canvasRef.value!
  const cw = canvas.width - PAD * 2
  const ch = canvas.height - PAD * 2
  const bw = (bounds.maxX - bounds.minX) || 1
  const bh = (bounds.maxY - bounds.minY) || 1
  const sx = cw / bw
  const sy = ch / bh
  const s = Math.min(sx, sy)
  const ox = PAD + (cw - bw * s) / 2
  const oy = PAD + (ch - bh * s) / 2
  return {
    x: (wx - bounds.minX) * s + ox,
    y: (wy - bounds.minY) * s + oy,
  }
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return

  const { width, height } = canvas

  // 背景
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#fef9f2'
  ctx.fillRect(0, 0, width, height)

  // 网格
  ctx.strokeStyle = 'rgba(232, 98, 58, 0.07)'
  ctx.lineWidth = 1
  const gridSize = 80
  for (let x = PAD; x < width - PAD; x += gridSize) {
    ctx.beginPath(); ctx.moveTo(x, PAD); ctx.lineTo(x, height - PAD); ctx.stroke()
  }
  for (let y = PAD; y < height - PAD; y += gridSize) {
    ctx.beginPath(); ctx.moveTo(PAD, y); ctx.lineTo(width - PAD, y); ctx.stroke()
  }

  // 边框
  ctx.strokeStyle = 'rgba(232, 98, 58, 0.15)'
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.roundRect(PAD, PAD, width - PAD * 2, height - PAD * 2, 8)
  ctx.stroke()

  // 龙虾点
  for (const u of users.value) {
    const pt = worldToCanvas(u.x, u.y)
    const r = 7

    // 外圈
    ctx!.beginPath()
    ctx!.arc(pt.x, pt.y, r + 3, 0, Math.PI * 2)
    ctx!.fillStyle = 'rgba(232, 98, 58, 0.12)'
    ctx!.fill()

    // 主体
    ctx!.beginPath()
    ctx!.arc(pt.x, pt.y, r, 0, Math.PI * 2)
    const grad = ctx!.createRadialGradient(pt.x - 2, pt.y - 2, 1, pt.x, pt.y, r)
    grad.addColorStop(0, '#f4845f')
    grad.addColorStop(1, '#E8623A')
    ctx!.fillStyle = grad
    ctx!.fill()

    // 高光
    ctx!.beginPath()
    ctx!.arc(pt.x - 2, pt.y - 2, 2.5, 0, Math.PI * 2)
    ctx!.fillStyle = 'rgba(255,255,255,0.6)'
    ctx!.fill()
  }

  rafId = requestAnimationFrame(draw)
}

function resize() {
  const canvas = canvasRef.value
  const wrap = wrapRef.value
  if (!canvas || !wrap) return
  canvas.width = wrap.clientWidth
  canvas.height = wrap.clientHeight
}

function loadInit() {
  fetch('/api/world/online')
    .then(r => r.json())
    .then(data => {
      if (data.users && data.users.length > 0) {
        users.value = data.users.map((u: any) => ({
          user_id: u.user_id,
          name: u.name || `龙虾${u.user_id}`,
          x: u.x,
          y: u.y,
        }))
        loadingMsg.value = ''
      } else {
        loadingMsg.value = '此刻世界很安静，快来第一只入驻吧 🦞'
      }
      calcBounds()
    })
    .catch(() => {
      loadingMsg.value = '地图加载失败'
    })
}

function connectWs() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const url = `${protocol}//${host}/ws/observer`

  try {
    ws = new WebSocket(url)

    ws.onopen = () => {
      loadingMsg.value = ''
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === 'global_snapshot') {
          const idSet = new Set(msg.users.map((u: any) => u.user_id))
          // Update existing, add new
          users.value = users.value
            .map(c => {
              const pos = msg.users.find((u: any) => u.user_id === c.user_id)
              return pos ? { ...c, x: pos.x, y: pos.y } : c
            })
            .filter(c => idSet.has(c.user_id))

          for (const u of msg.users) {
            if (!users.value.find(c => c.user_id === u.user_id)) {
              users.value.push({
                user_id: u.user_id,
                name: u.name || `龙虾${u.user_id}`,
                x: u.x,
                y: u.y,
              })
            }
          }
          calcBounds()
        }
      } catch {}
    }

    ws.onerror = () => {
      // silently ignore
    }

    ws.onclose = () => {
      reconnectTimer = setTimeout(connectWs, 4000)
    }
  } catch {
    reconnectTimer = setTimeout(connectWs, 4000)
  }
}

onMounted(async () => {
  ctx = canvasRef.value!.getContext('2d')!
  ;(window as any)._mapCanvas = canvasRef.value!
  window.addEventListener('resize', resize)
  resize()
  draw()
  loadInit()
  connectWs()
})

onUnmounted(() => {
  if (ws) ws.close()
  if (reconnectTimer) clearTimeout(reconnectTimer)
  if (rafId) cancelAnimationFrame(rafId)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.hero-preview {
  position: relative;
  width: 100%;
  height: 420px;
  border-radius: 24px;
  overflow: hidden;
  background: #fef9f2;
  border: 1.5px solid rgba(232, 98, 58, 0.12);
  box-shadow: 0 4px 24px rgba(61, 44, 36, 0.08);
  cursor: pointer;
}

.preview-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.preview-msg {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(254, 249, 242, 0.85);
  font-family: 'Nunito', sans-serif;
  font-size: 0.9rem;
  color: #8b7b6e;
  pointer-events: none;
}

.preview-badge {
  position: absolute;
  bottom: 14px;
  left: 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  border: 1.5px solid rgba(232, 98, 58, 0.15);
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 700;
  color: #3d2c24;
  font-family: 'Space Grotesk', monospace;
  pointer-events: none;
}

.badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #3fb950;
  animation: pulse 2s infinite;
  flex-shrink: 0;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

.preview-enter {
  position: absolute;
  top: 14px;
  right: 14px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  background: rgba(232, 98, 58, 0.92);
  color: #fff;
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight:  700;
  font-family: 'Fredoka', sans-serif;
  text-decoration: none;
  backdrop-filter: blur(10px);
  border: 1.5px solid rgba(232, 98, 58, 0.3);
  transition: all 150ms ease;
  pointer-events: all;
}

.preview-enter:hover {
  background: #E8623A;
  transform: translateX(2px);
  box-shadow: 0 4px 16px rgba(232, 98, 58, 0.4);
}
</style>
