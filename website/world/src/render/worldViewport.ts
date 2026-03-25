/**
 * worldViewport.ts — V2 世界地图视口渲染引擎
 * Viewport-based: offset + scale transform for zoom/drag
 * 被 WorldMap.vue 调用
 */

const WORLD_SIZE = 10000
const PAD = 24

export interface Viewport {
  offsetX: number
  offsetY: number
  scale: number
}

let _viewport: Viewport = { offsetX: WORLD_SIZE / 2, offsetY: WORLD_SIZE / 2, scale: 1 }
let _canvasW = 800
let _canvasH = 600

export function initViewport(canvasW: number, canvasH: number): Viewport {
  _canvasW = canvasW
  _canvasH = canvasH
  _viewport = { offsetX: WORLD_SIZE / 2, offsetY: WORLD_SIZE / 2, scale: 1 }
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

export function resetViewport(): void {
  _viewport = { offsetX: WORLD_SIZE / 2, offsetY: WORLD_SIZE / 2, scale: 1 }
}

export function worldToCanvas(wx: number, wy: number): { x: number; y: number } {
  return {
    x: (wx - _viewport.offsetX) * _viewport.scale + _canvasW / 2,
    y: (wy - _viewport.offsetY) * _viewport.scale + _canvasH / 2,
  }
}

export function canvasToWorld(sx: number, sy: number): { x: number; y: number } {
  return {
    x: (sx - _canvasW / 2) / _viewport.scale + _viewport.offsetX,
    y: (sy - _canvasH / 2) / _viewport.scale + _viewport.offsetY,
  }
}

// ── Rendering ─────────────────────────────────────────────────────────────────

/**
 * Seed-based jitter — lines never flicker on redraw.
 */
function jitter(i: number): number {
  return ((i * 7919) % 17 - 8) * 0.5 // ±3.5px
}

export function drawGrid(ctx: CanvasRenderingContext2D) {
  const PAD_VAL = PAD
  const step = 30
  ctx.strokeStyle = 'rgba(232,98,58,0.06)'
  ctx.lineWidth = 0.5

  for (let x = 0; x < _canvasW; x += step) {
    const jx = jitter(Math.floor(x / step))
    ctx.beginPath(); ctx.moveTo(x + jx, 0); ctx.lineTo(x + jx, _canvasH); ctx.stroke()
  }
  for (let y = 0; y < _canvasH; y += step) {
    const jy = jitter(Math.floor(y / step))
    ctx.beginPath(); ctx.moveTo(0, y + jy); ctx.lineTo(_canvasW, y + jy); ctx.stroke()
  }
}

export function drawAxisTicks(ctx: CanvasRenderingContext2D) {
  const PAD_VAL = PAD
  const TICK = 6
  const STEP = 100

  const halfW = _canvasW / 2 / _viewport.scale
  const halfH = _canvasH / 2 / _viewport.scale
  const minX = _viewport.offsetX - halfW
  const maxX = _viewport.offsetX + halfW
  const minY = _viewport.offsetY - halfH
  const maxY = _viewport.offsetY + halfH

  // X axis ticks
  const firstX = Math.ceil(minX / STEP) * STEP
  for (let wx = firstX; wx <= maxX; wx += STEP) {
    const sx = (wx - _viewport.offsetX) * _viewport.scale + _canvasW / 2
    if (sx < PAD_VAL || sx > _canvasW - PAD_VAL) continue
    const jx = (((wx / STEP) * 7919) % 11 - 5) * 0.4

    ctx.font = '500 10px Space Grotesk, monospace'
    ctx.fillStyle = 'rgba(139,123,110,0.7)'

    // Bottom
    ctx.beginPath(); ctx.strokeStyle = 'rgba(232,98,58,0.25)'; ctx.lineWidth = 1
    ctx.moveTo(sx + jx, _canvasH - PAD_VAL); ctx.lineTo(sx + jx, _canvasH - PAD_VAL + TICK); ctx.stroke()
    ctx.save(); ctx.textAlign = 'center'; ctx.textBaseline = 'top'
    ctx.fillText(String(Math.round(wx)), sx + jx, _canvasH - PAD_VAL + TICK + 2); ctx.restore()

    // Top
    ctx.beginPath()
    ctx.moveTo(sx + jx, PAD_VAL - TICK); ctx.lineTo(sx + jx, PAD_VAL); ctx.stroke()
    ctx.save(); ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'
    ctx.fillText(String(Math.round(wx)), sx + jx, PAD_VAL - TICK - 2); ctx.restore()
  }

  // Y axis ticks
  const firstY = Math.ceil(minY / STEP) * STEP
  for (let wy = firstY; wy <= maxY; wy += STEP) {
    const sy = (wy - _viewport.offsetY) * _viewport.scale + _canvasH / 2
    if (sy < PAD_VAL || sy > _canvasH - PAD_VAL) continue
    const jy = (((wy / STEP) * 7919) % 11 - 5) * 0.4

    ctx.font = '500 10px Space Grotesk, monospace'
    ctx.fillStyle = 'rgba(139,123,110,0.7)'

    // Left
    ctx.beginPath(); ctx.strokeStyle = 'rgba(232,98,58,0.25)'; ctx.lineWidth = 1
    ctx.moveTo(PAD_VAL, sy + jy); ctx.lineTo(PAD_VAL + TICK, sy + jy); ctx.stroke()
    ctx.save(); ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
    ctx.fillText(String(Math.round(wy)), PAD_VAL + TICK + 3, sy + jy); ctx.restore()

    // Right
    ctx.beginPath()
    ctx.moveTo(_canvasW - PAD_VAL - TICK, sy + jy); ctx.lineTo(_canvasW - PAD_VAL, sy + jy); ctx.stroke()
    ctx.save(); ctx.textAlign = 'right'; ctx.textBaseline = 'middle'
    ctx.fillText(String(Math.round(wy)), _canvasW - PAD_VAL - TICK - 3, sy + jy); ctx.restore()
  }
}

export function hashToColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  return `hsl(${Math.abs(hash) % 360}, 65%, 55%)`
}

function drawBubble(ctx: CanvasRenderingContext2D, pt: { x: number; y: number }, name: string, r: number) {
  ctx.save()
  ctx.translate(pt.x, pt.y - r - 16)
  const text = name.length > 12 ? name.slice(0, 11) + '…' : name
  ctx.font = '600 13px Fredoka, sans-serif'
  const tw = ctx.measureText(text).width
  const bw = tw + 20, bh = 28, br = 8
  ctx.beginPath()
  ctx.moveTo(-bw / 2 + br, -bh / 2); ctx.lineTo(bw / 2 - br, -bh / 2)
  ctx.quadraticCurveTo(bw / 2, -bh / 2, bw / 2, -bh / 2 + br)
  ctx.lineTo(bw / 2, bh / 2 - br)
  ctx.quadraticCurveTo(bw / 2, bh / 2, bw / 2 - br, bh / 2)
  ctx.lineTo(-bw / 2 + br, bh / 2)
  ctx.quadraticCurveTo(-bw / 2, bh / 2, -bw / 2, bh / 2 - br)
  ctx.lineTo(-bw / 2, -bh / 2 + br)
  ctx.quadraticCurveTo(-bw / 2, -bh / 2, -bw / 2 + br, -bh / 2)
  ctx.closePath()
  ctx.fillStyle = 'rgba(255,245,230,0.96)'; ctx.fill()
  ctx.strokeStyle = 'rgba(232,98,58,0.35)'; ctx.lineWidth = 1.5; ctx.stroke()
  ctx.fillStyle = '#3d2c24'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.fillText(text, 0, 0)
  ctx.restore()
}

export function drawCrawfishDot(
  ctx: CanvasRenderingContext2D,
  pt: { x: number; y: number },
  name: string,
  isHovered: boolean
) {
  const r = Math.max(3, 10 / _viewport.scale)

  if (_viewport.scale < 0.5) {
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, Math.max(3, 4 / _viewport.scale), 0, Math.PI * 2)
    ctx.fillStyle = hashToColor(name); ctx.fill()
    return
  }

  ctx.beginPath(); ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
  ctx.fillStyle = hashToColor(name); ctx.fill()
  ctx.strokeStyle = '#fff'; ctx.lineWidth = Math.max(1, 1.5 / _viewport.scale); ctx.stroke()

  const letterSize = Math.max(6, r * 0.7)
  ctx.font = `700 ${letterSize}px Fredoka, sans-serif`
  ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.fillText(name.charAt(0).toUpperCase(), pt.x, pt.y)

  if (isHovered) drawBubble(ctx, pt, name, r)
}

export function drawOnlineUsers(ctx: CanvasRenderingContext2D, users: { user_id: number; name: string; x: number; y: number }[], hoveredId: number | null) {
  for (const u of users) {
    const pt = worldToCanvas(u.x, u.y)
    drawCrawfishDot(ctx, pt, u.name || `用户#${u.user_id}`, u.user_id === hoveredId)
  }
  // Online count label
  ctx.font = '500 13px Space Grotesk, monospace'
  ctx.textAlign = 'left'; ctx.fillStyle = 'rgba(139,123,110,0.7)'
  ctx.fillText(`${users.length} 只龙虾在线`, 10, _canvasH - 10)
}

export function drawTrail(ctx: CanvasRenderingContext2D, pts: { x: number; y: number }[]) {
  if (pts.length < 2) return
  ctx.beginPath()
  const p0 = worldToCanvas(pts[0]!.x, pts[0]!.y)
  ctx.moveTo(p0.x, p0.y)
  for (let i = 1; i < pts.length; i++) {
    const p = worldToCanvas(pts[i]!.x, pts[i]!.y)
    ctx.lineTo(p.x, p.y)
  }
  ctx.strokeStyle = 'rgba(232,98,58,0.25)'; ctx.lineWidth = 1.5; ctx.stroke()
  for (const pt of pts) {
    const p = worldToCanvas(pt.x, pt.y)
    ctx.beginPath(); ctx.arc(p.x, p.y, 2, 0, Math.PI * 2)
    ctx.fillStyle = '#E8623A'; ctx.fill()
  }
}

export function drawHeatmap(ctx: CanvasRenderingContext2D, pts: { x: number; y: number }[]) {
  if (!pts.length) return
  const density = new Map<string, number>()
  for (const pt of pts) {
    const cx = Math.floor(pt.x / 100), cy = Math.floor(pt.y / 100)
    const key = `${cx},${cy}`
    density.set(key, (density.get(key) ?? 0) + 1)
  }
  const maxD = Math.max(...density.values(), 1)
  for (const [key, count] of density) {
    const [cx, cy] = key.split(',').map(Number)
    const p1 = worldToCanvas(cx * 100, cy * 100)
    const p2 = worldToCanvas((cx + 1) * 100, (cy + 1) * 100)
    const ratio = count / maxD
    if (ratio < 0.2) ctx.fillStyle = 'rgba(244,162,97,0.2)'
    else if (ratio < 0.5) ctx.fillStyle = 'rgba(244,162,97,0.4)'
    else if (ratio < 0.8) ctx.fillStyle = 'rgba(232,98,58,0.5)'
    else ctx.fillStyle = 'rgba(192,57,43,0.6)'
    ctx.fillRect(p1.x, p1.y, p2.x - p1.x, p2.y - p1.y)
  }
}
