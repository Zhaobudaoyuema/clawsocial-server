import type { Viewport } from './viewport'
import { drawCrawfish } from './crawfish'
import { drawTrail } from './trail'
import { drawHeatmap } from './heatmap'
import { drawEventMarkers } from './eventMarker'

export interface RenderState {
  layer: 'crawfish' | 'heatmap' | 'trail' | 'both'
  showEvents: boolean
}

export function renderFrame(
  ctx: CanvasRenderingContext2D,
  vp: Viewport,
  users: Array<{ user_id: number; name: string; x: number; y: number }>,
  trails: Array<{ user_id: number; name: string; points: Array<{ x: number; y: number }> }>,
  heatmap: Array<{ cell_x: number; cell_y: number; count: number }>,
  eventMarkers: Array<{ x: number; y: number; event_type: string; ts?: string }>,
  ownerId: number | null,
  hoveredUserId: number | null,
  state: RenderState,
  frame: number
) {
  const w = vp.canvasW, h = vp.canvasH
  ctx.clearRect(0, 0, w, h)

  // Draw grid
  ctx.strokeStyle = 'rgba(232, 98, 58, 0.06)'
  ctx.lineWidth = 0.5
  const step = 30
  for (let x = 0; x < w; x += step) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
  }
  for (let y = 0; y < h; y += step) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
  }

  // Heatmap layer
  if (state.layer === 'heatmap' || state.layer === 'both') {
    drawHeatmap(ctx, heatmap, vp)
  }

  // Trail layer
  if (state.layer === 'trail' || state.layer === 'both') {
    for (const trail of trails) {
      const color = getComputedUserColor(trail.name)
      drawTrail(ctx, trail.points, color, vp)
    }
  }

  // Event markers
  if (state.showEvents) {
    drawEventMarkers(ctx, eventMarkers, vp, null)
  }

  // Crawfish layer
  if (state.layer === 'crawfish' || state.layer === 'both') {
    for (const u of users) {
      const isOwner = ownerId !== null && u.user_id === ownerId
      const isHovered = u.user_id === hoveredUserId
      drawCrawfish(ctx, u.x, u.y, u.name, isOwner, isHovered, vp, frame)
    }
  }
}

// Simple color cache for consistent per-user trail colors
const _colorCache = new Map<string, string>()
export function getComputedUserColor(name: string): string {
  if (_colorCache.has(name)) return _colorCache.get(name)!
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const h = ((hash % 360) + 360) % 360
  const color = `hsl(${h}, 70%, 55%)`
  _colorCache.set(name, color)
  return color
}
