import { worldToCanvas } from './viewport'

const CELL_SIZE = 30  // must match server-side aggregation

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
    const pt1 = worldToCanvas(wx, wy, vp)
    const pt2 = worldToCanvas(wx + CELL_SIZE, wy + CELL_SIZE, vp)
    const cw = Math.abs(pt2.x - pt1.x)
    const ch = Math.abs(pt2.y - pt1.y)
    const ratio = c.count / maxCount

    if (ratio < 0.2) ctx.fillStyle = 'rgba(244,162,97,0.2)'
    else if (ratio < 0.5) ctx.fillStyle = 'rgba(244,162,97,0.4)'
    else if (ratio < 0.8) ctx.fillStyle = 'rgba(232,98,58,0.5)'
    else ctx.fillStyle = 'rgba(192,57,43,0.6)'

    ctx.fillRect(pt1.x, pt1.y, cw, ch)
  }
}
