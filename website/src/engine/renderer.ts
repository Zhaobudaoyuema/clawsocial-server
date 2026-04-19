import type { Viewport } from './viewport'
import { drawCrawfish } from './crawfish'
import { drawTrail } from './trail'
import { drawTrailUpTo } from './trail'
import { drawHeatmap } from './heatmap'
import { drawEventMarkers, drawCrawfishBubbles } from './eventMarker'

export type MapRenderMode = 'live' | 'replay'
export type LayerMode = 'crawfish' | 'heatmap' | 'trail' | 'both'

export interface RenderState {
  layer: LayerMode
  mode: MapRenderMode
  hideHistory?: boolean
}

export interface TrailSource {
  user_id: number
  name: string
  points: Array<{ x: number; y: number; ts?: string }>
}

export interface MapUser {
  user_id: number
  name: string
  x: number
  y: number
  isMe?: boolean
}

export interface MapEvent {
  x: number
  y: number
  event_type: string
  ts?: string
  reason?: string | null
  content?: string | null
  user_id?: number
  user_name?: string
}

export function renderFrame(
  ctx: CanvasRenderingContext2D,
  vp: Viewport,
  users: MapUser[],
  trails: TrailSource[],
  events: MapEvent[],
  heatmap: Array<{ cell_x: number; cell_y: number; count: number }>,
  ownerId: number | null,
  hoveredUserId: number | null,
  state: RenderState,
  frame: number,
  replayTime?: Date,
) {
  const w = vp.canvasW, h = vp.canvasH
  ctx.clearRect(0, 0, w, h)

  // Grid
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
      if (state.mode === 'replay' && replayTime) {
        drawTrailUpTo(
          ctx,
          trail.points as Array<{ x: number; y: number; ts: string }>,
          color, vp, replayTime
        )
      } else if (state.hideHistory) {
        const realtimeOnly = trail.points.filter(p => p.ts !== undefined)
        drawTrail(ctx, realtimeOnly, color, vp, 500, false)
      } else {
        // live 全量轨迹：isHistory=false，正常亮度显示
        drawTrail(ctx, trail.points, color, vp, 500, false)
      }
    }
  }

  // Event markers layer (dots at historical positions — drawn before crawfish)
  if ((state.layer === 'crawfish' || state.layer === 'both') && events.length > 0) {
    drawEventMarkers(ctx, events, vp, null)
  }

  // Crawfish layer
  if (state.layer === 'crawfish' || state.layer === 'both') {
    for (const u of users) {
      const isMe = !!u.isMe
      const isRelated = false  // related is only used in "my虾" replay mode
      const isOwner = ownerId !== null && u.user_id === ownerId
      const isHovered = u.user_id === hoveredUserId
      drawCrawfish(ctx, u.x, u.y, u.name, isMe || isOwner, isRelated, isHovered, vp, frame, state.mode === 'live')
    }

    // Speech bubbles drawn on top of crawfish — attributed to each crawfish
    if (events.length > 0) {
      drawCrawfishBubbles(ctx, events, users, vp)
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
