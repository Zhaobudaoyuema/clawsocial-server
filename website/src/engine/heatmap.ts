import { worldToCanvas } from './viewport'

const CELL_SIZE = 30  // must match server-side aggregation
const MIN_PX = 28     // minimum rendered cell size in canvas px — always larger than crawfish dot (12px)

export function drawHeatmap(
  ctx: CanvasRenderingContext2D,
  cells: Array<{ cell_x: number; cell_y: number; count: number }>,
  vp: import('./viewport').Viewport
) {
  if (!cells.length) return
  const maxCount = cells.reduce((m, c) => c.count > m ? c.count : m, 1)

  for (const c of cells) {
    const wx = c.cell_x * CELL_SIZE
    const wy = c.cell_y * CELL_SIZE

    // Cell center in canvas coords — used to anchor the minimum-size rect correctly
    const centerPt = worldToCanvas(wx + CELL_SIZE / 2, wy + CELL_SIZE / 2, vp)

    const pt1 = worldToCanvas(wx, wy, vp)
    const pt2 = worldToCanvas(wx + CELL_SIZE, wy + CELL_SIZE, vp)

    // Enforce minimum display size so cells are always visible and larger than crawfish dots
    const cw = Math.max(Math.abs(pt2.x - pt1.x), MIN_PX)
    const ch = Math.max(Math.abs(pt2.y - pt1.y), MIN_PX)

    // Render centered on the cell's world-center position
    const rx = centerPt.x - cw / 2
    const ry = centerPt.y - ch / 2

    const ratio = c.count / maxCount

    // High-contrast 4-tier color scale: bright yellow → orange → brand orange → deep red
    if (ratio < 0.25)      ctx.fillStyle = 'rgba(253,224,100, 0.55)'
    else if (ratio < 0.5)  ctx.fillStyle = 'rgba(244,162,50,  0.70)'
    else if (ratio < 0.75) ctx.fillStyle = 'rgba(232,98,58,   0.82)'
    else                   ctx.fillStyle = 'rgba(180,30,30,   0.92)'

    ctx.fillRect(rx, ry, cw, ch)

    // Cell outline for clear block boundaries (skip when cells are very small in world-space)
    if (cw > 4 && ch > 4) {
      ctx.strokeStyle = 'rgba(0,0,0,0.08)'
      ctx.lineWidth = 0.5
      ctx.strokeRect(rx, ry, cw, ch)
    }

    // Draw count number centered on the cell (only when cell is large enough)
    if (cw >= 22 && ch >= 22) {
      ctx.save()
      const fontSize = Math.max(9, Math.min(13, Math.round(cw * 0.32)))
      ctx.font = `600 ${fontSize}px "Space Grotesk", monospace`
      ctx.fillStyle = ratio >= 0.5 ? 'rgba(255,255,255,0.88)' : 'rgba(61,44,36,0.72)'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      const label = cw >= 22 ? `${c.count}次` : String(c.count)
      ctx.fillText(label, centerPt.x, centerPt.y)
      ctx.restore()
    }
  }
}
