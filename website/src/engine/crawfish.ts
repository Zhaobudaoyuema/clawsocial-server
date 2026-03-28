import { worldToCanvas } from './viewport'

const LOBSTER_RED_HOVER = '#D4542B'
const OWNER_GOLD = '#F4C430'

// Desaturate an HSL color string by reducing saturation
function desaturateColor(color: string): string {
  const match = color.match(/hsl\((\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)%?,\s*(\d+(?:\.\d+)?)%?\)/)
  if (!match) return color
  const h = parseFloat(match[1])
  const s = Math.max(30, parseFloat(match[2]) * 0.4)  // reduce saturation to 40%, min 30
  const l = parseFloat(match[3])
  return `hsl(${h}, ${s}%, ${l}%)`
}

// Get crawfish color, desaturated when not live
function getCrawfishColor(name: string, isLive: boolean): string {
  const base = nameToColor(name)
  return isLive ? base : desaturateColor(base)
}

// Generate consistent color from name hash (exported for external use)
export function nameToColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const h = ((hash % 360) + 360) % 360
  return `hsl(${h}, 65%, 55%)`
}

// Get first letter of name (capitalized)
export function nameToInitial(name: string): string {
  return (name.charAt(0) || '?').toUpperCase()
}

// Draw crawfish as dot (for zoomed-out view)
export function drawDot(
  ctx: CanvasRenderingContext2D,
  wx: number, wy: number,
  name: string,
  vp: import('./viewport').Viewport,
  isHovered = false,
  isLive = true,
) {
  const pt = worldToCanvas(wx, wy, vp)
  const r = isHovered ? 9 : 6
  const color = getCrawfishColor(name, isLive)
  ctx.shadowColor = color
  ctx.shadowBlur = isHovered ? 12 : 5
  ctx.beginPath()
  ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
  ctx.fillStyle = isHovered ? LOBSTER_RED_HOVER : color
  ctx.fill()
  ctx.shadowBlur = 0
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = 1.5
  ctx.stroke()
}

// Draw crawfish as avatar (for zoomed-in view, level 5)
export function drawAvatar(
  ctx: CanvasRenderingContext2D,
  wx: number, wy: number,
  name: string,
  isOwner: boolean,
  isHovered: boolean,
  vp: import('./viewport').Viewport,
  frame: number = 0,  // for animation
  isLive = true,
) {
  const pt = worldToCanvas(wx, wy, vp)
  const size = isHovered ? 36 : 28

  // Background circle
  const bgColor = getCrawfishColor(name, isLive)
  ctx.beginPath()
  ctx.arc(pt.x, pt.y, size, 0, Math.PI * 2)
  ctx.fillStyle = bgColor
  ctx.fill()

  // Owner gold ring with pulse
  if (isOwner) {
    const pulse = 1 + Math.sin(frame * 0.08) * 0.1
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, size + 4, 0, Math.PI * 2)
    ctx.strokeStyle = OWNER_GOLD
    ctx.lineWidth = 2.5 * pulse
    ctx.stroke()
  }

  // Draw lobster SVG-like shape (simplified crab silhouette)
  ctx.save()
  ctx.translate(pt.x - size * 0.7, pt.y - size * 0.7)
  ctx.scale(size / 28, size / 28)

  // Simple lobster body (ellipse)
  ctx.beginPath()
  ctx.ellipse(10, 14, 7, 9, 0, 0, Math.PI * 2)
  ctx.fillStyle = '#fff'
  ctx.globalAlpha = 0.85
  ctx.fill()
  ctx.globalAlpha = 1

  // Claws
  ctx.beginPath()
  ctx.ellipse(2, 8, 4, 3, -0.5, 0, Math.PI * 2)
  ctx.ellipse(18, 8, 4, 3, 0.5, 0, Math.PI * 2)
  ctx.fillStyle = '#fff'
  ctx.globalAlpha = 0.85
  ctx.fill()
  ctx.globalAlpha = 1

  ctx.restore()

  // First letter overlay
  ctx.font = `bold ${Math.round(size * 0.6)}px Fredoka, sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#fff'
  ctx.fillText(nameToInitial(name), pt.x, pt.y)
}

// Draw crawfish based on zoom level (auto-switch)
export function drawCrawfish(
  ctx: CanvasRenderingContext2D,
  wx: number, wy: number,
  name: string,
  isOwner: boolean,
  isHovered: boolean,
  vp: import('./viewport').Viewport,
  frame: number = 0,
  isLive = true,
) {
  const threshold = 0.08  // scale threshold for switching
  if (vp.scale >= threshold) {
    drawAvatar(ctx, wx, wy, name, isOwner, isHovered, vp, frame, isLive)
  } else {
    drawDot(ctx, wx, wy, name, vp, isHovered, isLive)
  }
}
