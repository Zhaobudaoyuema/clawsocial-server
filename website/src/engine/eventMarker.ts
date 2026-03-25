import { worldToCanvas } from './viewport'

export type EventType = 'encounter' | 'friendship' | 'message' | 'departure' | 'blocked' | 'hotspot'

const EVENT_COLORS: Record<EventType, string> = {
  encounter: '#4ECDC4',
  friendship: '#45B7D1',
  message: '#96CEB4',
  departure: '#DDA0DD',
  blocked: '#FF6B6B',
  hotspot: '#FFEAA7',
}

export function drawEventMarker(
  ctx: CanvasRenderingContext2D,
  wx: number, wy: number,
  eventType: EventType,
  vp: import('./viewport').Viewport,
  isHovered = false
) {
  const pt = worldToCanvas(wx, wy, vp)
  const r = isHovered ? 8 : 5
  const color = EVENT_COLORS[eventType] || '#E8623A'

  ctx.beginPath()
  ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.globalAlpha = 0.7
  ctx.fill()
  ctx.globalAlpha = 1
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 1
  ctx.stroke()
}

export function drawEventMarkers(
  ctx: CanvasRenderingContext2D,
  markers: Array<{ x: number; y: number; event_type: string; ts?: string }>,
  vp: import('./viewport').Viewport,
  hoveredMarkerIndex: number | null
) {
  for (let i = 0; i < markers.length; i++) {
    const m = markers[i]
    drawEventMarker(ctx, m.x, m.y, m.event_type as EventType, vp, hoveredMarkerIndex === i)
  }
}
