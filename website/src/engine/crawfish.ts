import { worldToCanvas } from './viewport'

const OWNER_GOLD = '#F4C430'

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

// ── SVG lobster icon (24×24, brand orange) ──────────────────────────────────

const _LOBSTER_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <ellipse cx="12" cy="14" rx="5" ry="7" fill="#E8623A" stroke="#b84020" stroke-width="0.6"/>
  <circle cx="12" cy="7" r="3.5" fill="#E8623A" stroke="#b84020" stroke-width="0.6"/>
  <ellipse cx="6.5" cy="10" rx="3.5" ry="2" fill="#E8623A" stroke="#b84020" stroke-width="0.6" transform="rotate(-20 6.5 10)"/>
  <ellipse cx="17.5" cy="10" rx="3.5" ry="2" fill="#E8623A" stroke="#b84020" stroke-width="0.6" transform="rotate(20 17.5 10)"/>
  <line x1="10.5" y1="4.2" x2="7" y2="1" stroke="#b84020" stroke-width="1" stroke-linecap="round"/>
  <line x1="13.5" y1="4.2" x2="17" y2="1" stroke="#b84020" stroke-width="1" stroke-linecap="round"/>
  <ellipse cx="9" cy="21" rx="2.5" ry="1.5" fill="#c84e28" transform="rotate(-20 9 21)"/>
  <ellipse cx="12" cy="22" rx="2.5" ry="1.5" fill="#c84e28"/>
  <ellipse cx="15" cy="21" rx="2.5" ry="1.5" fill="#c84e28" transform="rotate(20 15 21)"/>
  <ellipse cx="11" cy="12" rx="1.8" ry="2.8" fill="#ff8c5a" opacity="0.35"/>
</svg>`

// Hovered / isMe variants — same shape, different tint
const _LOBSTER_SVG_HOVER = _LOBSTER_SVG
  .replace(/#E8623A/g, '#D4452B')
  .replace(/#b84020/g, '#8a2010')
  .replace(/#c84e28/g, '#a03018')
  .replace(/#ff8c5a/g, '#ff6a3a')

function _makeImg(svg: string): HTMLImageElement {
  const img = new Image()
  img.src = `data:image/svg+xml,${encodeURIComponent(svg)}`
  return img
}

const _img = _makeImg(_LOBSTER_SVG)
const _imgHover = _makeImg(_LOBSTER_SVG_HOVER)

// ── Public draw function ──────────────────────────────────────────────────────

const ICON_SIZE = 22  // fixed canvas-pixel size — baseline at 100% zoom

export function drawCrawfish(
  ctx: CanvasRenderingContext2D,
  wx: number, wy: number,
  name: string,
  isMe: boolean,
  _isRelated: boolean,
  isHovered: boolean,
  vp: import('./viewport').Viewport,
  frame: number = 0,
  isLive = true,
) {
  const pt = worldToCanvas(wx, wy, vp)
  const half = ICON_SIZE / 2

  ctx.save()

  // isMe: animated gold ring
  if (isMe) {
    const pulse = 1 + Math.sin(frame * 0.08) * 0.12
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, half + 5 * pulse, 0, Math.PI * 2)
    ctx.strokeStyle = OWNER_GOLD
    ctx.lineWidth = 2.5
    ctx.stroke()
  }

  // Hover: orange glow
  if (isHovered) {
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, half + 7, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(232,98,58,0.22)'
    ctx.fill()
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, half + 4, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(232,98,58,0.6)'
    ctx.lineWidth = 1.5
    ctx.stroke()
  }

  // Offline: dimmed
  ctx.globalAlpha = isLive ? 1 : 0.4

  // Draw SVG icon (hover variant or normal)
  const icon = isHovered ? _imgHover : _img
  if (icon.complete && icon.naturalWidth > 0) {
    ctx.drawImage(icon, pt.x - half, pt.y - half, ICON_SIZE, ICON_SIZE)
  } else {
    // Fallback dot while image loads
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, isHovered ? 8 : 6, 0, Math.PI * 2)
    ctx.fillStyle = nameToColor(name)
    ctx.fill()
  }

  ctx.globalAlpha = 1

  // Name tag below icon when hovered
  if (isHovered) {
    const label = name
    const fontSize = 11
    ctx.font = `600 ${fontSize}px "Nunito", sans-serif`
    const tw = ctx.measureText(label).width
    const padding = 4
    const bw = tw + padding * 2
    const bh = fontSize + padding * 2
    const bx = pt.x - bw / 2
    const by = pt.y + half + 4

    // Background pill
    ctx.fillStyle = 'rgba(61,44,36,0.85)'
    ctx.beginPath()
    ctx.roundRect(bx, by, bw, bh, 4)
    ctx.fill()

    // Name text
    ctx.fillStyle = '#fff'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, pt.x, by + bh / 2)
  }

  ctx.restore()
}

// Keep old exports referenced by renderer.ts (drawDot / drawAvatar are no longer used
// but kept as thin wrappers to avoid import errors during transition)
export function drawDot(
  ctx: CanvasRenderingContext2D,
  wx: number, wy: number,
  name: string,
  vp: import('./viewport').Viewport,
  isHovered = false,
  isLive = true,
) {
  drawCrawfish(ctx, wx, wy, name, false, false, isHovered, vp, 0, isLive)
}

export function drawAvatar(
  ctx: CanvasRenderingContext2D,
  wx: number, wy: number,
  name: string,
  isMe: boolean,
  isRelated: boolean,
  isHovered: boolean,
  vp: import('./viewport').Viewport,
  frame = 0,
  isLive = true,
) {
  drawCrawfish(ctx, wx, wy, name, isMe, isRelated, isHovered, vp, frame, isLive)
}
