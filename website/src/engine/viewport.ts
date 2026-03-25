export const WORLD_SIZE = 10000

export interface Viewport {
  scale: number      // pixels per world unit, default 0.05
  offsetX: number    // canvas pan offset X
  offsetY: number    // canvas pan offset Y
  canvasW: number
  canvasH: number
}

export function createViewport(canvasW: number, canvasH: number): Viewport {
  const scale = 0.05
  return {
    scale,
    offsetX: canvasW / 2 - (WORLD_SIZE / 2) * scale,
    offsetY: canvasH / 2 - (WORLD_SIZE / 2) * scale,
    canvasW,
    canvasH,
  }
}

export function worldToCanvas(wx: number, wy: number, vp: Viewport): { x: number; y: number } {
  return {
    x: wx * vp.scale + vp.offsetX,
    y: wy * vp.scale + vp.offsetY,
  }
}

export function canvasToWorld(cx: number, cy: number, vp: Viewport): { x: number; y: number } {
  return {
    x: (cx - vp.offsetX) / vp.scale,
    y: (cy - vp.offsetY) / vp.scale,
  }
}

export function zoomViewport(vp: Viewport, delta: number, cx: number, cy: number): Viewport {
  const factor = delta > 0 ? 1.15 : 1 / 1.15
  const newScale = Math.max(0.005, Math.min(0.5, vp.scale * factor))
  // Zoom towards cursor position
  const wx = (cx - vp.offsetX) / vp.scale
  const wy = (cy - vp.offsetY) / vp.scale
  return {
    ...vp,
    scale: newScale,
    offsetX: cx - wx * newScale,
    offsetY: cy - wy * newScale,
  }
}

export function panViewport(vp: Viewport, dx: number, dy: number): Viewport {
  return { ...vp, offsetX: vp.offsetX + dx, offsetY: vp.offsetY + dy }
}

// Auto-fit viewport to show all given world users with padding
export function fitViewportToUsers(users: Array<{x: number, y: number}>, canvasW: number, canvasH: number): Viewport {
  if (!users.length) return createViewport(canvasW, canvasH)
  const PAD = 200
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const u of users) {
    if (u.x < minX) minX = u.x
    if (u.x > maxX) maxX = u.x
    if (u.y < minY) minY = u.y
    if (u.y > maxY) maxY = u.y
  }
  const w = maxX - minX + PAD * 2
  const h = maxY - minY + PAD * 2
  const scale = Math.min(canvasW / w, canvasH / h)
  return {
    scale,
    offsetX: (canvasW - w * scale) / 2 - minX * scale + PAD * scale,
    offsetY: (canvasH - h * scale) / 2 - minY * scale + PAD * scale,
    canvasW,
    canvasH,
  }
}
