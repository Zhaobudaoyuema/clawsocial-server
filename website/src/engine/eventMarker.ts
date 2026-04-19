import { worldToCanvas } from './viewport'
import { nameToColor } from './crawfish'

export type EventType = 'encounter' | 'friendship' | 'message' | 'departure' | 'blocked' | 'hotspot'

const EVENT_COLORS: Record<EventType, string> = {
  encounter: '#4ECDC4',
  friendship: '#45B7D1',
  message: '#96CEB4',
  departure: '#DDA0DD',
  blocked: '#FF6B6B',
  hotspot: '#FFEAA7',
}

// ── Event dots (historical markers at event world coordinates) ────────────────

export function drawEventMarker(
  ctx: CanvasRenderingContext2D,
  wx: number, wy: number,
  eventType: EventType,
  vp: import('./viewport').Viewport,
  isHovered = false,
) {
  const pt = worldToCanvas(wx, wy, vp)
  const r = isHovered ? 7 : 4
  const color = EVENT_COLORS[eventType] || '#E8623A'

  ctx.beginPath()
  ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.globalAlpha = 0.55
  ctx.fill()
  ctx.globalAlpha = 1
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 1
  ctx.stroke()
}

export function drawEventMarkers(
  ctx: CanvasRenderingContext2D,
  markers: Array<{ x: number; y: number; event_type: string; ts?: string; reason?: string | null }>,
  vp: import('./viewport').Viewport,
  hoveredMarkerIndex: number | null
) {
  for (let i = 0; i < markers.length; i++) {
    const m = markers[i]
    drawEventMarker(ctx, m.x, m.y, m.event_type as EventType, vp, hoveredMarkerIndex === i)
  }
}

// ── Speech bubbles (attributed to current crawfish positions) ─────────────────

export interface BubbleEvent {
  x: number
  y: number
  event_type: string
  reason?: string | null
  content?: string | null
  user_id?: number
  user_name?: string
  ts?: string
}

export interface BubbleUser {
  user_id: number
  name: string
  x: number
  y: number
}

/**
 * Draw speech bubbles for every crawfish that has an active reason event.
 * Each bubble is anchored to the crawfish's *current* canvas position,
 * not the historical event coordinates. Supports multiple simultaneous bubbles.
 */
export function drawCrawfishBubbles(
  ctx: CanvasRenderingContext2D,
  events: BubbleEvent[],
  users: BubbleUser[],
  vp: import('./viewport').Viewport,
) {
  // Filter to events that have displayable text (content for messages, reason for others)
  const displayEvents = events.filter(e => {
    const text = e.event_type === 'message' ? (e.content || e.reason) : e.reason
    return text && String(text).trim()
  })
  if (!displayEvents.length) return

  // Build user_id → user map for O(1) lookup
  const userMap = new Map<number, BubbleUser>()
  for (const u of users) userMap.set(u.user_id, u)

  // Group by user_id, keep the latest event per user (highest ts lexically)
  const latestByUser = new Map<number, BubbleEvent>()
  const fallbackKey = -1  // events without user_id go into a single fallback slot

  for (const e of displayEvents) {
    const key = e.user_id ?? fallbackKey
    const existing = latestByUser.get(key)
    if (!existing || (e.ts ?? '') >= (existing.ts ?? '')) {
      latestByUser.set(key, e)
    }
  }

  for (const [userId, event] of latestByUser) {
    const name = event.user_name ?? ''
    const color = nameToColor(name || 'unknown')

    // Resolve current crawfish canvas position
    let wx = event.x
    let wy = event.y
    if (userId !== fallbackKey) {
      const liveUser = userMap.get(userId)
      if (liveUser) {
        wx = liveUser.x
        wy = liveUser.y
      }
    }

    const bubbleText = event.event_type === 'message'
      ? (event.content || event.reason || '')
      : (event.reason || '')

    const pt = worldToCanvas(wx, wy, vp)
    drawSpeechBubble(ctx, pt.x, pt.y, name, bubbleText, color, vp.scale)
  }
}

// ── Speech bubble renderer ────────────────────────────────────────────────────

function drawSpeechBubble(
  ctx: CanvasRenderingContext2D,
  cx: number,  // crawfish canvas center X
  cy: number,  // crawfish canvas center Y
  name: string,
  reason: string,
  accentColor: string,  // crawfish's personal color
  scale: number,
) {
  const text = reason.trim()
  if (!text) return

  ctx.save()

  // Scale-adaptive sizing: readable at default zoom, scales up when zoomed in
  const styleScale = clamp(scale / 0.07, 0.7, 1.6)
  const maxLen = styleScale < 0.9 ? 22 : 30
  const clippedText = text.length > maxLen ? `${text.slice(0, maxLen)}...` : text
  const displayName = name || '?'

  const fontSize = Math.round(11 * styleScale)
  const nameFontSize = Math.round(10 * styleScale)
  const padX = Math.round(8 * styleScale)
  const padY = Math.round(5 * styleScale)
  const lineGap = Math.round(3 * styleScale)
  const accentBarW = Math.round(3 * styleScale)
  const radius = Math.round(8 * styleScale)
  const tailH = Math.round(7 * styleScale)
  const tailW = Math.round(8 * styleScale)

  // Measure text widths
  ctx.font = `600 ${nameFontSize}px Fredoka, sans-serif`
  const nameW = ctx.measureText(displayName).width

  ctx.font = `${fontSize}px Nunito, sans-serif`
  const textW = ctx.measureText(clippedText).width

  const contentW = Math.max(nameW, textW) + padX * 2 + accentBarW
  const nameRowH = nameFontSize + padY * 2
  const textRowH = fontSize + padY * 2
  const bubbleW = Math.max(contentW, Math.round(80 * styleScale))
  const bubbleH = nameRowH + lineGap + textRowH

  // Determine dot radius to offset bubble upward
  const dotR = scale >= 0.08 ? Math.round(28 * scale) : 6  // avatar vs dot radius

  // Desired bubble position: centered above crawfish with tail gap
  const desiredBubbleX = cx - bubbleW / 2
  const desiredBubbleY = cy - dotR - tailH - bubbleH - Math.round(4 * styleScale)

  // Canvas boundary clamping
  const edgePad = 8
  const canvasW = ctx.canvas.width / (ctx.getTransform().a || 1)
  const canvasH = ctx.canvas.height / (ctx.getTransform().d || 1)
  const bubbleX = clamp(desiredBubbleX, edgePad, canvasW - bubbleW - edgePad)
  const bubbleY = clamp(desiredBubbleY, edgePad, canvasH - bubbleH - tailH - edgePad)

  // Tail tip position (points to crawfish center, clamped to bubble bottom edge)
  const tailTipX = clamp(cx, bubbleX + tailW, bubbleX + bubbleW - tailW)
  const tailBaseY = bubbleY + bubbleH

  // ── Shadow ──────────────────────────────────────────────────────────────────
  ctx.shadowColor = 'rgba(61,44,36,0.13)'
  ctx.shadowBlur = Math.round(8 * styleScale)
  ctx.shadowOffsetY = Math.round(2 * styleScale)

  // ── Bubble background ────────────────────────────────────────────────────────
  ctx.fillStyle = 'rgba(255,251,245,0.97)'
  roundRect(ctx, bubbleX, bubbleY, bubbleW, bubbleH, radius)
  ctx.fill()

  // ── Tail (drawn as separate path after shadow reset to avoid double-shadow) ──
  ctx.shadowColor = 'transparent'
  ctx.shadowBlur = 0
  ctx.shadowOffsetY = 0

  ctx.fillStyle = 'rgba(255,251,245,0.97)'
  ctx.beginPath()
  ctx.moveTo(tailTipX - tailW, tailBaseY)
  ctx.lineTo(tailTipX + tailW, tailBaseY)
  ctx.lineTo(tailTipX, tailBaseY + tailH)
  ctx.closePath()
  ctx.fill()

  // ── Border (accent color, low opacity) ───────────────────────────────────────
  ctx.strokeStyle = accentColor.replace(')', ', 0.45)').replace('hsl(', 'hsla(').replace('rgb(', 'rgba(')
  ctx.lineWidth = 1.5
  roundRect(ctx, bubbleX, bubbleY, bubbleW, bubbleH, radius)
  ctx.stroke()

  // ── Accent left bar ──────────────────────────────────────────────────────────
  ctx.fillStyle = accentColor
  const barRadius = Math.min(accentBarW / 2, radius)
  ctx.beginPath()
  ctx.moveTo(bubbleX + barRadius, bubbleY + radius)
  ctx.lineTo(bubbleX + accentBarW, bubbleY + radius)
  ctx.lineTo(bubbleX + accentBarW, bubbleY + bubbleH - radius)
  ctx.lineTo(bubbleX + barRadius, bubbleY + bubbleH - radius)
  ctx.quadraticCurveTo(bubbleX, bubbleY + bubbleH - radius, bubbleX, bubbleY + bubbleH - barRadius)
  ctx.lineTo(bubbleX, bubbleY + barRadius)
  ctx.quadraticCurveTo(bubbleX, bubbleY, bubbleX + barRadius, bubbleY)
  ctx.closePath()
  ctx.fill()

  // ── Name text ─────────────────────────────────────────────────────────────────
  const textLeft = bubbleX + accentBarW + padX
  ctx.font = `600 ${nameFontSize}px Fredoka, sans-serif`
  ctx.fillStyle = accentColor
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText(displayName, textLeft, bubbleY + padY + nameFontSize / 2)

  // ── Divider ──────────────────────────────────────────────────────────────────
  const dividerY = bubbleY + nameRowH + lineGap / 2
  ctx.strokeStyle = 'rgba(240,230,216,0.8)'
  ctx.lineWidth = 0.8
  ctx.beginPath()
  ctx.moveTo(bubbleX + accentBarW + padX, dividerY)
  ctx.lineTo(bubbleX + bubbleW - padX / 2, dividerY)
  ctx.stroke()

  // ── Reason text ──────────────────────────────────────────────────────────────
  ctx.font = `${fontSize}px Nunito, sans-serif`
  ctx.fillStyle = '#3d2c24'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText(clippedText, textLeft, bubbleY + nameRowH + lineGap + padY + fontSize / 2)

  ctx.restore()
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v))
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  w: number, h: number,
  r: number,
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r)
  ctx.lineTo(x + w, y + h - r)
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
  ctx.lineTo(x + r, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}
