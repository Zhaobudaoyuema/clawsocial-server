/**
 * world_map.ts — 龙虾世界地图渲染引擎
 * Viewport-based rendering: offset + scale transform
 * 被 HeroMap.vue 调用
 */

const WORLD_SIZE = 10000
const GRID_COLOR = 'rgba(232, 98, 58, 0.06)'
const PAD = 24

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

// ── Viewport ──────────────────────────────────────────────────────────────

export interface Viewport {
  offsetX: number
  offsetY: number
  scale: number
}

let _viewport: Viewport = { offsetX: WORLD_SIZE / 2, offsetY: WORLD_SIZE / 2, scale: 1 }
let _canvasW = 800
let _canvasH = 600

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

/**
 * Initialize viewport centered on user bounds.
 * Call once when user list first arrives.
 */
export function initViewport(users: WorldUser[], canvasW: number, canvasH: number): Viewport {
  _canvasW = canvasW
  _canvasH = canvasH
  const bounds = getBounds(users)
  _viewport = {
    offsetX: (bounds.minX + bounds.maxX) / 2,
    offsetY: (bounds.minY + bounds.maxY) / 2,
    scale: 1,
  }
  return _viewport
}

export function getViewport(): Viewport {
  return _viewport
}

export function setCanvasSize(w: number, h: number) {
  _canvasW = w
  _canvasH = h
}

export function applyViewportTransform(ctx: CanvasRenderingContext2D) {
  ctx.save()
  ctx.translate(_canvasW / 2, _canvasH / 2)
  ctx.scale(_viewport.scale, _viewport.scale)
  ctx.translate(-_viewport.offsetX, -_viewport.offsetY)
}

export function restoreViewportTransform(ctx: CanvasRenderingContext2D) {
  ctx.restore()
}

/**
 * Zoom centered on a world coordinate (pinch-to-zoom semantics).
 */
export function zoomViewport(delta: number, centerWorldX: number, centerWorldY: number): void {
  const newScale = Math.min(5, Math.max(0.2, _viewport.scale * (1 + delta * 0.15)))
  _viewport.offsetX = centerWorldX - (centerWorldX - _viewport.offsetX) * (newScale / _viewport.scale)
  _viewport.offsetY = centerWorldY - (centerWorldY - _viewport.offsetY) * (newScale / _viewport.scale)
  _viewport.scale = newScale
}

export function panViewport(dx: number, dy: number): void {
  _viewport.offsetX -= dx / _viewport.scale
  _viewport.offsetY -= dy / _viewport.scale
}

export function resetViewport(users: WorldUser[]): void {
  const bounds = getBounds(users)
  _viewport = {
    offsetX: (bounds.minX + bounds.maxX) / 2,
    offsetY: (bounds.minY + bounds.maxY) / 2,
    scale: 1,
  }
}

// ── 坐标转换（Viewport-based）───────────────────────────────────────────────

/**
 * Convert world coordinates to canvas pixel coordinates using current viewport.
 */
export function worldToCanvas(
  wx: number,
  wy: number,
  _bounds?: WorldBounds
): { x: number; y: number } {
  return {
    x: (wx - _viewport.offsetX) * _viewport.scale + _canvasW / 2,
    y: (wy - _viewport.offsetY) * _viewport.scale + _canvasH / 2,
  }
}

/**
 * Convert canvas pixel coordinates back to world coordinates.
 */
export function canvasToWorld(sx: number, sy: number): { x: number; y: number } {
  return {
    x: (sx - _canvasW / 2) / _viewport.scale + _viewport.offsetX,
    y: (sy - _canvasH / 2) / _viewport.scale + _viewport.offsetY,
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

// ── Canvas 渲染（手绘风）────────────────────────────────────────────────────

/**
 * Draw grid with seed-based jitter — lines never flicker.
 */
export function drawGrid(ctx: CanvasRenderingContext2D, w: number, h: number) {
  ctx.strokeStyle = GRID_COLOR
  ctx.lineWidth = 0.5
  const step = 30
  const jitter = (i: number) => ((i * 7919) % 17 - 8) * 0.5 // ±3.5px max

  for (let x = 0; x < w; x += step) {
    const jx = jitter(Math.floor(x / step))
    ctx.beginPath()
    ctx.moveTo(x + jx, 0)
    ctx.lineTo(x + jx, h)
    ctx.stroke()
  }
  for (let y = 0; y < h; y += step) {
    const jy = jitter(Math.floor(y / step))
    ctx.beginPath()
    ctx.moveTo(0, y + jy)
    ctx.lineTo(w, y + jy)
    ctx.stroke()
  }
}

/**
 * Draw coordinate axis ticks on canvas edges (hand-drawn jitter).
 */
export function drawAxisTicks(ctx: CanvasRenderingContext2D) {
  const TICK = 6
  const PAD_VAL = PAD
  const TICK_STEP = 100

  // X axis ticks (top and bottom)
  const worldLeft = _viewport.offsetX - (_canvasW / 2 - PAD_VAL) / _viewport.scale
  const worldRight = _viewport.offsetX + (_canvasW / 2 - PAD_VAL) / _viewport.scale
  const firstTickX = Math.ceil(worldLeft / TICK_STEP) * TICK_STEP

  for (let wx = firstTickX; wx <= worldRight; wx += TICK_STEP) {
    const sx = (wx - _viewport.offsetX) * _viewport.scale + _canvasW / 2
    if (sx < PAD_VAL || sx > _canvasW - PAD_VAL) continue

    const jx = (((wx / TICK_STEP) * 7919) % 11 - 5) * 0.4

    ctx.font = '500 10px Space Grotesk, monospace'
    ctx.fillStyle = 'rgba(139, 123, 110, 0.7)'

    // Bottom
    ctx.beginPath()
    ctx.strokeStyle = 'rgba(232, 98, 58, 0.25)'
    ctx.lineWidth = 1
    ctx.moveTo(sx + jx, _canvasH - PAD_VAL)
    ctx.lineTo(sx + jx, _canvasH - PAD_VAL + TICK)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillText(String(Math.round(wx)), sx + jx, _canvasH - PAD_VAL + TICK + 2)
    ctx.restore()

    // Top
    ctx.beginPath()
    ctx.moveTo(sx + jx, PAD_VAL - TICK)
    ctx.lineTo(sx + jx, PAD_VAL)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'bottom'
    ctx.fillText(String(Math.round(wx)), sx + jx, PAD_VAL - TICK - 2)
    ctx.restore()
  }

  // Y axis ticks (left and right)
  const worldTop = _viewport.offsetY - (_canvasH / 2 - PAD_VAL) / _viewport.scale
  const worldBottom = _viewport.offsetY + (_canvasH / 2 - PAD_VAL) / _viewport.scale
  const firstTickY = Math.ceil(worldTop / TICK_STEP) * TICK_STEP

  for (let wy = firstTickY; wy <= worldBottom; wy += TICK_STEP) {
    const sy = (wy - _viewport.offsetY) * _viewport.scale + _canvasH / 2
    if (sy < PAD_VAL || sy > _canvasH - PAD_VAL) continue

    const jy = (((wy / TICK_STEP) * 7919) % 11 - 5) * 0.4

    ctx.font = '500 10px Space Grotesk, monospace'
    ctx.fillStyle = 'rgba(139, 123, 110, 0.7)'

    // Left
    ctx.beginPath()
    ctx.strokeStyle = 'rgba(232, 98, 58, 0.25)'
    ctx.lineWidth = 1
    ctx.moveTo(PAD_VAL, sy + jy)
    ctx.lineTo(PAD_VAL + TICK, sy + jy)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    ctx.fillText(String(Math.round(wy)), PAD_VAL + TICK + 3, sy + jy)
    ctx.restore()

    // Right
    ctx.beginPath()
    ctx.moveTo(_canvasW - PAD_VAL - TICK, sy + jy)
    ctx.lineTo(_canvasW - PAD_VAL, sy + jy)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'right'
    ctx.textBaseline = 'middle'
    ctx.fillText(String(Math.round(wy)), _canvasW - PAD_VAL - TICK - 3, sy + jy)
    ctx.restore()
  }
}

/**
 * Deterministic color from username hash.
 */
export function hashToColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const hue = Math.abs(hash) % 360
  return `hsl(${hue}, 65%, 55%)`
}

/**
 * Hand-drawn speech bubble for crawfish hover.
 */
function drawCrawfishBubble(
  ctx: CanvasRenderingContext2D,
  pt: { x: number; y: number },
  name: string,
  r: number
) {
  ctx.save()
  ctx.translate(pt.x, pt.y - r - 16)

  const text = name.length > 12 ? name.slice(0, 11) + '…' : name
  ctx.font = '600 13px Fredoka, sans-serif'
  const tw = ctx.measureText(text).width
  const bw = tw + 20
  const bh = 28
  const br = 8

  // Bubble body
  ctx.beginPath()
  ctx.moveTo(-bw / 2 + br, -bh / 2)
  ctx.lineTo(bw / 2 - br, -bh / 2)
  ctx.quadraticCurveTo(bw / 2, -bh / 2, bw / 2, -bh / 2 + br)
  ctx.lineTo(bw / 2, bh / 2 - br)
  ctx.quadraticCurveTo(bw / 2, bh / 2, bw / 2 - br, bh / 2)
  ctx.lineTo(-bw / 2 + br, bh / 2)
  ctx.quadraticCurveTo(-bw / 2, bh / 2, -bw / 2, bh / 2 - br)
  ctx.lineTo(-bw / 2, -bh / 2 + br)
  ctx.quadraticCurveTo(-bw / 2, -bh / 2, -bw / 2 + br, -bh / 2)
  ctx.closePath()
  ctx.fillStyle = 'rgba(255, 245, 230, 0.96)'
  ctx.fill()
  ctx.strokeStyle = 'rgba(232, 98, 58, 0.35)'
  ctx.lineWidth = 1.5
  ctx.stroke()

  ctx.fillStyle = '#3d2c24'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 0, 0)

  ctx.restore()
}

/**
 * Draw a single crawfish avatar (with viewport-aware scaling).
 */
export function drawCrawfishDot(
  ctx: CanvasRenderingContext2D,
  pt: { x: number; y: number },
  name: string,
  isHovered: boolean
) {
  const BASE_R = 10
  const r = Math.max(3, BASE_R / _viewport.scale)

  if (_viewport.scale < 0.5) {
    // Far zoom: simple dot
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, Math.max(3, 4 / _viewport.scale), 0, Math.PI * 2)
    ctx.fillStyle = hashToColor(name)
    ctx.fill()
    return
  }

  // Avatar circle
  ctx.beginPath()
  ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
  ctx.fillStyle = hashToColor(name)
  ctx.fill()
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = Math.max(1, 1.5 / _viewport.scale)
  ctx.stroke()

  // First letter
  const letterSize = Math.max(6, r * 0.7)
  ctx.font = `700 ${letterSize}px Fredoka, sans-serif`
  ctx.fillStyle = '#fff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(name.charAt(0).toUpperCase(), pt.x, pt.y)

  if (isHovered) {
    drawCrawfishBubble(ctx, pt, name, r)
  }
}

export function drawCrawfishLayer(
  ctx: CanvasRenderingContext2D,
  users: WorldUser[],
  hoveredUserId: number | null,
  _w: number,
  _h: number
) {
  if (!users.length) return

  for (const u of users) {
    const pt = worldToCanvas(u.x, u.y)
    const isHovered = u.user_id === hoveredUserId
    drawCrawfishDot(ctx, pt, u.name, isHovered)
  }

  // Online count
  ctx.font = '500 13px Space Grotesk, monospace'
  ctx.textAlign = 'left'
  ctx.fillStyle = 'rgba(139,123,110,0.7)'
  ctx.fillText(`${users.length} 只龙虾在线`, 10, _h - 10)
}

export function drawHeatmapLayer(
  ctx: CanvasRenderingContext2D,
  cells: HeatmapCell[],
  _w: number,
  _h: number
) {
  if (!cells.length) return
  const maxCount = Math.max(...cells.map((c) => c.count), 1)
  const CELL = 30

  for (const c of cells) {
    const wx = c.cell_x * CELL
    const wy = c.cell_y * CELL
    const pt = worldToCanvas(wx, wy)
    const pt2 = worldToCanvas(wx + CELL, wy + CELL)
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

// ── 主渲染循环（Viewport-aware）────────────────────────────────────────────

export function renderMap(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  layer: 'crawfish' | 'heatmap' | 'both',
  users: WorldUser[],
  heatmap: HeatmapCell[],
  hoveredUserId: number | null
) {
  ctx.clearRect(0, 0, w, h)

  // Apply viewport transform for world-space rendering
  applyViewportTransform(ctx)

  if (layer === 'heatmap' || layer === 'both') {
    drawHeatmapLayer(ctx, heatmap, w, h)
  }
  if (layer === 'crawfish' || layer === 'both') {
    drawCrawfishLayer(ctx, users, hoveredUserId, w, h)
  }

  restoreViewportTransform(ctx)

  // Axis ticks are in canvas-space (drawn after viewport restore)
  drawAxisTicks(ctx)
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
