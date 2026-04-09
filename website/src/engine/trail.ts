import { worldToCanvas } from './viewport'

// Draw a smooth trail using quadratic bezier curves
export function drawTrail(
  ctx: CanvasRenderingContext2D,
  points: Array<{ x: number; y: number; ts?: string }>,
  color: string,
  vp: import('./viewport').Viewport,
  maxPoints = 500,
  isHistory = false,
) {
  if (points.length < 2) return

  const pts = points.slice(-maxPoints)
  ctx.strokeStyle = color
  ctx.lineWidth = isHistory ? 1 : 1.5
  ctx.globalAlpha = isHistory ? 0.3 : 0.8
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'

  const p0 = worldToCanvas(pts[0].x, pts[0].y, vp)
  ctx.beginPath()
  ctx.moveTo(p0.x, p0.y)

  for (let i = 1; i < pts.length - 1; i++) {
    const p1 = worldToCanvas(pts[i].x, pts[i].y, vp)
    const p2 = worldToCanvas(pts[i + 1].x, pts[i + 1].y, vp)
    const midX = (p1.x + p2.x) / 2
    const midY = (p1.y + p2.y) / 2
    ctx.quadraticCurveTo(p1.x, p1.y, midX, midY)
  }

  const last = worldToCanvas(pts[pts.length - 1].x, pts[pts.length - 1].y, vp)
  ctx.lineTo(last.x, last.y)
  ctx.stroke()
  ctx.globalAlpha = 1
}

// Progressive trail draw: only draw points up to given time
export function drawTrailUpTo(
  ctx: CanvasRenderingContext2D,
  points: Array<{ x: number; y: number; ts: string }>,
  color: string,
  vp: import('./viewport').Viewport,
  cutoffTime: Date,
  maxPoints = 500
) {
  const pts = points.filter(p => p.ts && new Date(p.ts) <= cutoffTime).slice(-maxPoints)
  drawTrail(ctx, pts, color, vp, maxPoints, false)
}
