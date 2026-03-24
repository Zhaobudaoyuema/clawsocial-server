/**
 * world_map.js — 龙虾世界地图渲染引擎
 * 复用自 /world/index.html 的 Canvas 逻辑
 * 被 HeroMap.vue 和 /world/index.html 共同引用
 */

const WORLD_SIZE = 10000
const LOBSTER_RED = '#E8623A'
const LOBSTER_RED_HOVER = '#D4542B'
const GRID_COLOR = 'rgba(232, 98, 58, 0.06)'
const PAD = 20

export interface WorldUser {
  user_id: number
  name: string
  x: number
  y: number
  description?: string
}

export interface HeatmapCell {
  cell_x: number
  cell_y: number
  count: number
}

export interface WorldBounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

// Cached bounds: recalculated only when the user list changes (not every frame).
let _boundsCache: WorldBounds = { minX: 0, maxX: WORLD_SIZE, minY: 0, maxY: WORLD_SIZE }

/**
 * Recalculate and cache the world bounds from the current user list.
 * Call this on every WebSocket snapshot (users changed), NOT every render frame.
 */
export function updateBoundsCache(users: WorldUser[]): void {
  _boundsCache = getBounds(users)
}

/** Return the cached bounds (set by the most recent `updateBoundsCache` call). */
export function getCachedBounds(): WorldBounds {
  return _boundsCache
}

export interface MapConfig {
  baseUrl?: string
  onOnlineCount?: (count: number) => void
  onTotalCount?: (count: number) => void
  onTodayCount?: (count: number) => void
  onWsConnected?: (connected: boolean) => void
  onMessage?: (msg: string) => void
  onHideMessage?: () => void
}

// ── 坐标转换 ──────────────────────────────────────────────────────────────
export function worldToCanvas(
  wx: number,
  wy: number,
  bounds: WorldBounds
): { x: number; y: number } {
  const cw = (window as any)._mapCanvas?.width - PAD * 2 || 800
  const ch = (window as any)._mapCanvas?.height - PAD * 2 || 600
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

export function getBounds(users: WorldUser[]): WorldBounds {
  if (!users.length) {
    return { minX: 0, maxX: WORLD_SIZE, minY: 0, maxY: WORLD_SIZE }
  }
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity
  for (const u of users) {
    if (u.x < minX) minX = u.x
    if (u.x > maxX) maxX = u.x
    if (u.y < minY) minY = u.y
    if (u.y > maxY) maxY = u.y
  }
  const pad = 100
  return {
    minX: Math.max(0, minX - pad),
    maxX: Math.min(WORLD_SIZE, maxX + pad),
    minY: Math.max(0, minY - pad),
    maxY: Math.min(WORLD_SIZE, maxY + pad),
  }
}

// ── Canvas 渲染 ─────────────────────────────────────────────────────────────
export function drawGrid(ctx: CanvasRenderingContext2D, w: number, h: number) {
  ctx.strokeStyle = GRID_COLOR
  ctx.lineWidth = 0.5
  const step = 30
  for (let x = 0; x < w; x += step) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, h)
    ctx.stroke()
  }
  for (let y = 0; y < h; y += step) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(w, y)
    ctx.stroke()
  }
}

export function drawCrawfishDot(
  ctx: CanvasRenderingContext2D,
  pt: { x: number; y: number },
  name: string,
  isHovered: boolean
) {
  const r = isHovered ? 9 : 6

  ctx.shadowColor = LOBSTER_RED
  ctx.shadowBlur = isHovered ? 12 : 5

  ctx.beginPath()
  ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
  ctx.fillStyle = isHovered ? LOBSTER_RED_HOVER : LOBSTER_RED
  ctx.fill()

  ctx.shadowBlur = 0
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 1.5
  ctx.stroke()

  // 名字气泡（仅悬停）
  if (isHovered) {
    ctx.font = '600 12px Fredoka, sans-serif'
    ctx.textAlign = 'center'
    const textW = ctx.measureText(name).width
    ctx.fillStyle = 'rgba(61,44,36,0.85)'
    ctx.fillRect(pt.x - textW / 2 - 5, pt.y - r - 20, textW + 10, 18)
    ctx.fillStyle = LOBSTER_RED
    ctx.fillText(name, pt.x, pt.y - r - 7)
  }
}

export function drawCrawfishLayer(
  ctx: CanvasRenderingContext2D,
  users: WorldUser[],
  hoveredUserId: number | null,
  _w: number,
  _h: number,
  worldToCanvasFn: (wx: number, wy: number, b: WorldBounds) => { x: number; y: number },
  bounds: WorldBounds
) {
  if (!users.length) return

  for (const u of users) {
    const pt = worldToCanvasFn(u.x, u.y, bounds)
    const isHovered = u.user_id === hoveredUserId
    drawCrawfishDot(ctx, pt, u.name, isHovered)
  }

  // 在线数字
  ctx.font = '500 13px Space Grotesk, monospace'
  ctx.textAlign = 'left'
  ctx.fillStyle = 'rgba(139,123,110,0.7)'
  ctx.fillText(`${users.length} 只龙虾在线`, 10, _h - 10)
}

export function drawHeatmapLayer(
  ctx: CanvasRenderingContext2D,
  cells: HeatmapCell[],
  _w: number,
  _h: number,
  worldToCanvasFn: (wx: number, wy: number, b: WorldBounds) => { x: number; y: number }
) {
  if (!cells.length) return
  const bounds = getBounds([])
  const maxCount = Math.max(...cells.map((c) => c.count), 1)
  const CELL = 30

  for (const c of cells) {
    const wx = c.cell_x * CELL
    const wy = c.cell_y * CELL
    const pt = worldToCanvasFn(wx, wy, bounds)
    const pt2 = worldToCanvasFn(wx + CELL, wy + CELL, bounds)
    const cw = Math.abs(pt2.x - pt.x)
    const ch = Math.abs(pt2.y - pt.y)
    const ratio = c.count / maxCount

    if (ratio < 0.2) ctx.fillStyle = 'rgba(244,162,97,0.2)'
    else if (ratio < 0.5) ctx.fillStyle = 'rgba(244,162,97,0.4)'
    else if (ratio < 0.8) ctx.fillStyle = 'rgba(232,98,58,0.5)'
    else ctx.fillStyle = 'rgba(192,57,43,0.6)'

    ctx.fillRect(pt.x, pt.y, cw, ch)
  }
}

// ── 主渲染循环 ─────────────────────────────────────────────────────────────
export function renderMap(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  layer: 'crawfish' | 'heatmap' | 'both',
  users: WorldUser[],
  heatmap: HeatmapCell[],
  hoveredUserId: number | null,
  bounds: WorldBounds
) {
  ctx.clearRect(0, 0, w, h)
  drawGrid(ctx, w, h)

  if (layer === 'heatmap' || layer === 'both') {
    drawHeatmapLayer(ctx, heatmap, w, h, worldToCanvas)
  }
  if (layer === 'crawfish' || layer === 'both') {
    drawCrawfishLayer(ctx, users, hoveredUserId, w, h, worldToCanvas, bounds)
  }
}

// ── WebSocket 连接 ─────────────────────────────────────────────────────────
export interface WsState {
  ws: WebSocket | null
  reconnectTimer: ReturnType<typeof setTimeout> | null
}

export function connectObserverWs(
  wsState: WsState,
  baseUrl: string,
  onSnapshot: (msg: any) => void,
  onConnected: (v: boolean) => void
) {
  if (wsState.ws) wsState.ws.close()

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${baseUrl}/ws/world/observer`
  const ws = new WebSocket(url)
  wsState.ws = ws

  ws.onopen = () => onConnected(true)
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      onSnapshot(msg)
    } catch (_) {}
  }
  ws.onclose = () => {
    onConnected(false)
    wsState.reconnectTimer = setTimeout(
      () => connectObserverWs(wsState, baseUrl, onSnapshot, onConnected),
      3000
    )
  }
  ws.onerror = () => ws.close()
}

export function disconnectWs(wsState: WsState) {
  if (wsState.reconnectTimer) clearTimeout(wsState.reconnectTimer)
  if (wsState.ws) wsState.ws.close()
}

// ── REST 初始化 ─────────────────────────────────────────────────────────────
export async function loadInitData(_baseUrl: string) {
  const [stats, online] = await Promise.all([
    fetch(`/api/world/stats`).then((r) => r.json()),
    fetch(`/api/world/online`).then((r) => r.json()),
  ])
  return {
    total: stats.total || 0,
    today: stats.today_new || 0,
    online: online.count || 0,
    users: (online.online || []).map((u: any) => ({
      user_id: u.user_id,
      name: u.name || `龙虾${u.user_id}`,
      x: u.x,
      y: u.y,
      description: u.description || '',
    })),
  }
}
