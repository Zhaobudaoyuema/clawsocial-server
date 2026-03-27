# Map UI 优化 + 全站手绘风升级 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 地图加缩放/拖拽/坐标刻度，全站升级手绘插画风

**Architecture:**
- `world_map.ts` 是核心渲染引擎，Viewport 状态在 JS 模块内管理，通过 `initViewport()` 初始化
- 所有页面（HeroMap.vue、index.html、map-preview.html、world/index.html）共用同一套渲染函数
- Canvas 全局 CSS Token (`rc-*`, watercolor-shadow) 注入到 App.vue，全站生效
- 手绘气泡和头像用 Canvas 原生绘制，无外部依赖

**Tech Stack:** TypeScript（world_map.ts）+ Vanilla JS（HTML 页面）+ Vue 3（HeroMap）+ CSS

---

## 改动文件地图

```
website/src/world_map.ts          ← 核心引擎：Viewport + 刻度 + 头像 + 气泡
website/src/components/HeroMap.vue ← 首页地图：事件绑定 + 缩放/拖拽
app/world/crawfish/index.html      ← 主地图页：toolbar + 坐标显示
app/world/crawfish/map-preview.html← 预览页：手绘风升级
app/static/world/index.html        ← 独立世界地图：手绘风升级
website/src/App.vue               ← 全局 CSS：噪点纹理
website/src/components/FeatureSection.vue ← 卡片圆角 + 水彩阴影
website/src/components/QuickStart.vue     ← 编号圆形
DESIGN.md                         ← 写入手绘风格规范
```

---

## 任务 1: world_map.ts — Viewport 核心引擎

**Files:**
- Modify: `website/src/world_map.ts`
- Check: `website/src/world_map.ts:1-50` (interfaces section)

---

- [ ] **Step 1: 添加 Viewport 接口和模块状态**

在 `website/src/world_map.ts` 现有 interface 区段末尾添加：

```ts
export interface Viewport {
  offsetX: number
  offsetY: number
  scale: number
}

let _viewport: Viewport = { offsetX: 0, offsetY: 0, scale: 1 }
let _canvasW = 800
let _canvasH = 600
let _users: WorldUser[] = []

export function initViewport(users: WorldUser[], canvasW: number, canvasH: number): Viewport {
  _canvasW = canvasW
  _canvasH = canvasH
  _users = users
  const bounds = getBounds(users)
  _viewport = {
    offsetX: (bounds.minX + bounds.maxX) / 2,
    offsetY: (bounds.minY + bounds.maxY) / 2,
    scale: 1,
  }
  return _viewport
}

export function getViewport(): Viewport {
  return _viewport
}

export function setCanvasSize(w: number, h: number) {
  _canvasW = w
  _canvasH = h
}

export function applyViewportTransform(ctx: CanvasRenderingContext2D) {
  ctx.save()
  ctx.translate(_canvasW / 2, _canvasH / 2)
  ctx.scale(_viewport.scale, _viewport.scale)
  ctx.translate(-_viewport.offsetX, -_viewport.offsetY)
}

export function restoreViewportTransform(ctx: CanvasRenderingContext2D) {
  ctx.restore()
}
```

---

- [ ] **Step 2: 重写 worldToCanvas 加入 Viewport**

将 `worldToCanvas` 函数替换为（保持函数签名不变，仅改实现）：

```ts
export function worldToCanvas(
  wx: number,
  wy: number,
  _bounds?: WorldBounds
): { x: number; y: number } {
  return {
    x: (wx - _viewport.offsetX) * _viewport.scale + _canvasW / 2,
    y: (wy - _viewport.offsetY) * _viewport.scale + _canvasH / 2,
  }
}

export function canvasToWorld(sx: number, sy: number): { x: number; y: number } {
  return {
    x: (sx - _canvasW / 2) / _viewport.scale + _viewport.offsetX,
    y: (sy - _canvasH / 2) / _viewport.scale + _viewport.offsetY,
  }
}
```

---

- [ ] **Step 3: 添加缩放函数**

在 `worldToCanvas` 后添加：

```ts
export function zoomViewport(delta: number, centerWorldX: number, centerWorldY: number): void {
  const newScale = Math.min(5, Math.max(0.2, _viewport.scale * (1 + delta * 0.15)))
  // Adjust offset so centerWorld stays fixed on screen
  _viewport.offsetX = centerWorldX - (centerWorldX - _viewport.offsetX) * (newScale / _viewport.scale)
  _viewport.offsetY = centerWorldY - (centerWorldY - _viewport.offsetY) * (newScale / _viewport.scale)
  _viewport.scale = newScale
}

export function panViewport(dx: number, dy: number): void {
  _viewport.offsetX -= dx / _viewport.scale
  _viewport.offsetY -= dy / _viewport.scale
}

export function resetViewport(users: WorldUser[]): void {
  const bounds = getBounds(users)
  _viewport = {
    offsetX: (bounds.minX + bounds.maxX) / 2,
    offsetY: (bounds.minY + bounds.maxY) / 2,
    scale: 1,
  }
}
```

---

- [ ] **Step 4: 重写 drawGrid 加手绘抖动**

替换现有 `drawGrid` 函数：

```ts
export function drawGrid(ctx: CanvasRenderingContext2D, w: number, h: number) {
  ctx.strokeStyle = 'rgba(232, 98, 58, 0.06)'
  ctx.lineWidth = 0.5
  const step = 30

  // Seed-based jitter so lines never flicker (jitter depends on index, not time)
  const jitter = (i: number) => ((i * 7919) % 17 - 8) * 0.5 // ±3.5px max

  for (let x = 0; x < w; x += step) {
    const jx = jitter(Math.floor(x / step))
    ctx.beginPath()
    ctx.moveTo(x + jx, 0)
    ctx.lineTo(x + jx, h)
    ctx.stroke()
  }
  for (let y = 0; y < h; y += step) {
    const jy = jitter(Math.floor(y / step))
    ctx.beginPath()
    ctx.moveTo(0, y + jy)
    ctx.lineTo(w, y + jy)
    ctx.stroke()
  }
}
```

---

- [ ] **Step 5: 添加坐标刻度函数**

在 `drawGrid` 后添加：

```ts
function getVisibleWorldBounds(): { minX: number; maxX: number; minY: number; maxY: number } {
  const halfW = _canvasW / 2 / _viewport.scale
  const halfH = _canvasH / 2 / _viewport.scale
  return {
    minX: _viewport.offsetX - halfW,
    maxX: _viewport.offsetX + halfW,
    minY: _viewport.offsetY - halfH,
    maxY: _viewport.offsetY + halfH,
  }
}

export function drawAxisTicks(ctx: CanvasRenderingContext2D) {
  const vb = getVisibleWorldBounds()
  const TICK = 6
  const TICK_STEP = 500
  const FONT_SIZE = 11

  ctx.font = `500 ${FONT_SIZE}px 'Space Grotesk', monospace`
  ctx.fillStyle = '#8b7b6e'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'

  // Draw X axis ticks (top and bottom edges of world area in screen)
  // We'll draw ticks relative to canvas padding area
  const pad = 20
  const worldLeft = _viewport.offsetX - (_canvasW / 2 - pad) / _viewport.scale
  const worldRight = _viewport.offsetX + (_canvasW / 2 - pad) / _viewport.scale

  const firstTickX = Math.ceil(worldLeft / TICK_STEP) * TICK_STEP

  // Top ticks
  for (let wx = firstTickX; wx <= worldRight; wx += TICK_STEP) {
    const sx = (wx - _viewport.offsetX) * _viewport.scale + _canvasW / 2
    if (sx < pad || sx > _canvasW - pad) continue

    // Top tick
    const jx = (((wx / TICK_STEP) * 7919) % 11 - 5) * 0.4
    ctx.beginPath()
    ctx.strokeStyle = 'rgba(232, 98, 58, 0.25)'
    ctx.lineWidth = 1
    ctx.moveTo(sx + jx, pad)
    ctx.lineTo(sx + jx, pad + TICK)
    ctx.stroke()
    ctx.fillText(String(Math.round(wx)), sx, pad + TICK + 2)

    // Bottom tick (mirrored)
    ctx.beginPath()
    ctx.moveTo(sx + jx, _canvasH - pad - TICK)
    ctx.lineTo(sx + jx, _canvasH - pad)
    ctx.stroke()
    ctx.save()
    ctx.textBaseline = 'bottom'
    ctx.fillText(String(Math.round(wx)), sx, _canvasH - pad - TICK - 2)
    ctx.restore()
  }

  // Y axis ticks (left and right)
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  const worldTop = _viewport.offsetY - (_canvasH / 2 - pad) / _viewport.scale
  const worldBottom = _viewport.offsetY + (_canvasH / 2 - pad) / _viewport.scale
  const firstTickY = Math.ceil(worldTop / TICK_STEP) * TICK_STEP

  for (let wy = firstTickY; wy <= worldBottom; wy += TICK_STEP) {
    const sy = (wy - _viewport.offsetY) * _viewport.scale + _canvasH / 2
    if (sy < pad || sy > _canvasH - pad) continue

    const jy = (((wy / TICK_STEP) * 7919) % 11 - 5) * 0.4

    // Left tick
    ctx.beginPath()
    ctx.strokeStyle = 'rgba(232, 98, 58, 0.25)'
    ctx.lineWidth = 1
    ctx.moveTo(pad, sy + jy)
    ctx.lineTo(pad + TICK, sy + jy)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'left'
    ctx.fillText(String(Math.round(wy)), pad + TICK + 3, sy)
    ctx.restore()

    // Right tick
    ctx.beginPath()
    ctx.moveTo(_canvasW - pad - TICK, sy + jy)
    ctx.lineTo(_canvasW - pad, sy + jy)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'right'
    ctx.fillText(String(Math.round(wy)), _canvasW - pad - TICK - 3, sy)
    ctx.restore()
  }
}
```

---

- [ ] **Step 6: 添加头像颜色生成函数**

在 `drawCrawfishDot` 前添加：

```ts
export function hashToColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  }
  const hue = Math.abs(hash) % 360
  return `hsl(${hue}, 75%, 65%)`
}
```

---

- [ ] **Step 7: 重写 drawCrawfishDot 替换为头像绘制**

替换 `drawCrawfishDot` 整个函数：

```ts
export function drawCrawfishDot(
  ctx: CanvasRenderingContext2D,
  pt: { x: number; y: number },
  name: string,
  isHovered: boolean
) {
  const BASE_R = 10
  const r = Math.max(3, BASE_R / _viewport.scale)

  if (_viewport.scale < 0.5) {
    // Far zoom: simple dot
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, Math.max(3, 4 / _viewport.scale), 0, Math.PI * 2)
    ctx.fillStyle = hashToColor(name)
    ctx.fill()
    return
  }

  // Full avatar
  ctx.beginPath()
  ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
  ctx.fillStyle = hashToColor(name)
  ctx.fill()
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = Math.max(1, 1.5 / _viewport.scale)
  ctx.stroke()

  // Letter
  const letterSize = Math.max(6, r * 0.7)
  ctx.font = `700 ${letterSize}px 'Fredoka', sans-serif`
  ctx.fillStyle = '#fff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(name.charAt(0).toUpperCase(), pt.x, pt.y)

  // Hover bubble
  if (isHovered) {
    drawCrawfishBubble(ctx, pt, name, r)
  }
}
```

---

- [ ] **Step 8: 添加手绘气泡函数**

在 `drawCrawfishDot` 后添加：

```ts
export function drawCrawfishBubble(
  ctx: CanvasRenderingContext2D,
  pt: { x: number; y: number },
  name: string,
  r: number
) {
  const desc = (name + '').slice(0, 16)
  const label = desc.length < (name + '').length ? desc + '…' : desc

  ctx.font = `600 ${Math.max(9, 11 / _viewport.scale)}px 'Fredoka', sans-serif`
  ctx.textAlign = 'left'
  const nameW = ctx.measureText(name).width
  const labelW = ctx.measureText(`"${label}"`).width
  const coordW = ctx.measureText(`(${Math.round(pt.x)}, ${Math.round(pt.y)})`).width
  const bw = Math.max(nameW, labelW, coordW) + 20
  const bh = 52 / _viewport.scale
  const br = 6 / _viewport.scale

  // Smart positioning: prefer right-top, fallback to left-top
  let bx = pt.x + r + 6
  let by = pt.y - bh / 2
  if (bx + bw > _canvasW - 10) bx = pt.x - r - 6 - bw
  if (by < 10) by = 10
  if (by + bh > _canvasH - 10) by = _canvasH - bh - 10

  // Bubble body
  ctx.fillStyle = 'rgba(255,255,255,0.96)'
  ctx.strokeStyle = 'rgba(232,98,58,0.3)'
  ctx.lineWidth = 1.5 / _viewport.scale
  ctx.beginPath()
  const x0 = bx, y0 = by, x1 = bx + bw, y1 = by + bh
  // Rounded rect helper (hand-drawn feel via slight radius variation)
  ctx.roundRect(x0, y0, x1 - x0, y1 - y0, br)
  ctx.fill()
  ctx.stroke()

  // Tail triangle
  const tx = pt.x < bx + bw / 2 ? bx : bx + bw
  ctx.beginPath()
  ctx.moveTo(tx, pt.y)
  ctx.lineTo(pt.x, pt.y)
  ctx.lineTo(tx, pt.y + (pt.y < by + bh / 2 ? 4 : -4))
  ctx.fillStyle = 'rgba(232,98,58,0.3)'
  ctx.fill()

  // Text lines
  ctx.font = `600 ${Math.max(9, 10 / _viewport.scale)}px 'Fredoka', sans-serif`
  ctx.fillStyle = '#3d2c24'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'top'
  ctx.fillText(name, bx + 8, by + 5 / _viewport.scale)

  ctx.font = `400 ${Math.max(8, 9 / _viewport.scale)}px 'Nunito', sans-serif`
  ctx.fillStyle = '#8b7b6e'
  ctx.fillText(`"${label}"`, bx + 8, by + (16 / _viewport.scale))

  ctx.font = `400 ${Math.max(8, 9 / _viewport.scale)}px 'Space Grotesk', monospace`
  ctx.fillStyle = '#8b7b6e'
  ctx.fillText(`(${Math.round(pt.x)}, ${Math.round(pt.y)})`, bx + 8, by + (29 / _viewport.scale))
}
```

---

- [ ] **Step 9: 更新 renderMap 整合所有层**

替换 `renderMap` 函数：

```ts
export function renderMap(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  layer: 'crawfish' | 'heatmap' | 'both',
  users: WorldUser[],
  heatmap: HeatmapCell[],
  hoveredUserId: number | null,
  _bounds?: WorldBounds
) {
  setCanvasSize(w, h)
  ctx.clearRect(0, 0, w, h)

  applyViewportTransform(ctx)

  drawGrid(ctx, w, h)

  if (layer === 'heatmap' || layer === 'both') {
    drawHeatmapLayer(ctx, heatmap, w, h, worldToCanvas)
  }
  if (layer === 'crawfish' || layer === 'both') {
    drawCrawfishLayer(ctx, users, hoveredUserId, w, h, worldToCanvas, _bounds || getCachedBounds())
  }

  restoreViewportTransform(ctx)

  // Axis ticks on top (in screen space, not world space)
  drawAxisTicks(ctx)
}
```

---

- [ ] **Step 10: 添加视口坐标范围和鼠标坐标辅助函数**

在文件末尾添加：

```ts
export function getViewportWorldRange(): { minX: number; maxX: number; minY: number; maxY: number } {
  const halfW = _canvasW / 2 / _viewport.scale
  const halfH = _canvasH / 2 / _viewport.scale
  return {
    minX: Math.round(_viewport.offsetX - halfW),
    maxX: Math.round(_viewport.offsetX + halfW),
    minY: Math.round(_viewport.offsetY - halfH),
    maxY: Math.round(_viewport.offsetY + halfH),
  }
}

export function getScale(): number {
  return _viewport.scale
}
```

---

- [ ] **Step 11: 提交**

```bash
cd /d/clawsocial-server/.worktrees/map-ui-optimization
git add website/src/world_map.ts
git commit -m "feat(map): add viewport system, axis ticks, avatar, hand-drawn bubble

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 2: HeroMap.vue — 首页地图组件

**Files:**
- Modify: `website/src/components/HeroMap.vue`
- Check: `website/src/components/HeroMap.vue:1-50` (script setup section)

---

- [ ] **Step 1: 添加 Viewport 导入和 isDragging 状态**

在 `script setup` 现有 import 后添加：

```ts
import {
  renderMap,
  connectObserverWs,
  disconnectWs,
  loadInitData,
  worldToCanvas,
  updateBoundsCache,
  getCachedBounds,
  initViewport,
  zoomViewport,
  panViewport,
  resetViewport,
  canvasToWorld,
  getViewportWorldRange,
  getScale,
} from '../world_map'
```

在 `const users = ref<WorldUser[]>([])` 后添加：

```ts
const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const lastPan = ref({ x: 0, y: 0 })
const mouseWorld = ref({ x: 0, y: 0 })
const scaleDisplay = ref('100%')
```

---

- [ ] **Step 2: 替换 resize 函数，初始化 Viewport**

替换 `function resize()` 为：

```ts
function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  canvas.width = wrap.clientWidth
  canvas.height = wrap.clientHeight
  ;(window as any)._mapCanvas = canvas
  // Init viewport centered on current users
  initViewport(users.value, canvas.width, canvas.height)
  updateScaleDisplay()
  drawFrame()
}

function updateScaleDisplay() {
  scaleDisplay.value = Math.round(getScale() * 100) + '%'
}
```

---

- [ ] **Step 3: 添加滚轮缩放处理**

在 `onMounted` 末尾添加 wheel 监听（在 `resize()` 调用后加）：

```ts
canvas.addEventListener('wheel', (e: WheelEvent) => {
  e.preventDefault()
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const world = canvasToWorld(mx, my)
  // HeroMap scale limits: [0.3, 3]
  const newScale = Math.min(3, Math.max(0.3, getScale() * (1 + (e.deltaY > 0 ? -1 : 1) * 0.15)))
  // Simple zoom toward cursor
  const vp = (window as any)._viewport
  const vp2 = (window as any)._viewport
  import('../world_map').then(m => {
    m.zoomViewport(e.deltaY > 0 ? -1 : 1, world.x, world.y)
    updateScaleDisplay()
    drawFrame()
  })
}, { passive: false })
```

**注意：** 上述 wheel 处理较复杂，需要在 `world_map.ts` 中暴露一个 `setScaleAndCenter` 函数简化调用。先检查 world_map.ts 是否有该函数，如果没有，在 world_map.ts 末尾添加：

```ts
export function setScale(scale: number, centerX?: number, centerY?: number): void {
  if (centerX !== undefined && centerY !== undefined) {
    const ratio = scale / _viewport.scale
    _viewport.offsetX = centerX - (centerX - _viewport.offsetX) / ratio
    _viewport.offsetY = centerY - (centerY - _viewport.offsetY) / ratio
  }
  _viewport.scale = scale
}
```

然后 HeroMap wheel 处理简化为：

```ts
canvas.addEventListener('wheel', (e: WheelEvent) => {
  e.preventDefault()
  const rect = canvas.getBoundingClientRect()
  const world = canvasToWorld(e.clientX - rect.left, e.clientY - rect.top)
  const newScale = Math.min(3, Math.max(0.3, getScale() * (1 + (e.deltaY > 0 ? -0.15 : 0.15))))
  zoomViewportToward(newScale, world.x, world.y)
  updateScaleDisplay()
  drawFrame()
}, { passive: false })
```

需要在 world_map.ts 添加 `zoomViewportToward`：

```ts
export function zoomViewportToward(newScale: number, cx: number, cy: number): void {
  const ratio = newScale / _viewport.scale
  _viewport.offsetX = cx - (cx - _viewport.offsetX) / ratio
  _viewport.offsetY = cy - (cy - _viewport.offsetY) / ratio
  _viewport.scale = newScale
}
```

---

- [ ] **Step 4: 添加拖拽处理**

在 `onMouseLeave` 后添加：

```ts
function onMouseDown(e: MouseEvent) {
  isDragging.value = true
  dragStart.value = { x: e.clientX, y: e.clientY }
  lastPan.value = { x: e.clientX, y: e.clientY }
}

function onMouseMoveDrag(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  // Update cursor coordinate display
  mouseWorld.value = canvasToWorld(e.clientX - rect.left, e.clientY - rect.top)

  if (isDragging.value) {
    const dx = e.clientX - lastPan.value.x
    const dy = e.clientY - lastPan.value.y
    lastPan.value = { x: e.clientX, y: e.clientY }
    panViewport(dx, dy)
    updateScaleDisplay()
    drawFrame()
  }
}

function onMouseUp() {
  isDragging.value = false
}
```

---

- [ ] **Step 5: 更新 onMounted 事件绑定**

在 canvas `addEventListener` 区域添加：

```ts
canvas.addEventListener('mousedown', onMouseDown)
canvas.addEventListener('mouseup', onMouseUp)
canvas.addEventListener('mousemove', onMouseMoveDrag)
canvas.style.cursor = 'grab'
```

在 `onUnmounted` 移除事件：

```ts
canvas.removeEventListener('mousedown', onMouseDown)
canvas.removeEventListener('mouseup', onMouseUp)
canvas.removeEventListener('mousemove', onMouseMoveDrag)
```

---

- [ ] **Step 6: 更新 WebSocket snapshot 处理**

在 `onSnapshot` 回调的 `updateBoundsCache` 后添加：

```ts
// Keep viewport centered if already initialized
updateScaleDisplay()
drawFrame()
```

---

- [ ] **Step 7: 更新 template 添加鼠标坐标和缩放显示**

替换 `<div class="map-badge">` 为：

```html
<!-- 左上角：鼠标坐标 -->
<div class="map-coord">
  ({{ Math.round(mouseWorld.x) }}, {{ Math.round(mouseWorld.y) }})
</div>

<!-- 左下角：在线数 + 缩放比例 -->
<div class="map-badge">
  <span class="badge-dot"></span>
  <span>{{ users.length }} 只龙虾</span>
  <span class="zoom-tag">{{ scaleDisplay }}</span>
</div>
```

---

- [ ] **Step 8: 添加新样式**

在 `<style scoped>` 末尾添加：

```css
.map-coord {
  position: absolute;
  top: 14px;
  left: 14px;
  padding: 4px 10px;
  background: rgba(255,255,255,0.88);
  backdrop-filter: blur(10px);
  border: 1.5px solid #f0e6d8;
  border-radius: 20px;
  font-size: 0.72rem;
  color: #8b7b6e;
  font-family: 'Space Grotesk', monospace;
  font-weight: 600;
  pointer-events: none;
}

.zoom-tag {
  margin-left: 6px;
  padding: 2px 7px;
  background: rgba(232,98,58,0.1);
  border-radius: 20px;
  color: #e8623a;
  font-size: 0.7rem;
}
```

同时更新 `.map-badge` 移除已有 `.badge-dot` 动画以外的重复样式。

---

- [ ] **Step 9: 提交**

```bash
git add website/src/components/HeroMap.vue
git commit -m "feat(hero): add zoom/drag to HeroMap, cursor coords, scale display

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 3: app/world/crawfish/index.html — 主地图页

**Files:**
- Modify: `app/world/crawfish/index.html` (inline `<script>` section)
- Check: `app/world/crawfish/index.html` JS section (~line 400+)

---

- [ ] **Step 1: 读取现有 JS 脚本，了解现有 init 逻辑**

先读取 `index.html` 的 JS 部分，确认 `init()` 函数位置和 WebSocket 连接代码位置。

---

- [ ] **Step 2: 在 HTML `<head>` 添加全局 CSS Token**

在 `</style>` 前添加（如果有现有 style 块则合并）：

```css
/* ── Hand-drawn CSS Token ── */
:root {
  --rc-xs: 6px;
  --rc-sm: 10px;
  --rc-md: 16px;
  --rc-lg: 22px;
  --rc-xl: 30px;
}
.watercolor-shadow {
  box-shadow: 0 2px 8px rgba(232,98,58,.08), 0 6px 24px rgba(232,98,58,.06), 3px 3px 0 rgba(232,98,58,.04);
}
```

---

- [ ] **Step 3: 在 toolbar HTML 中添加缩放控件**

找到 `#toolbar` 中的 `.tb-sep` 后（第 242 行附近），添加：

```html
<span class="tb-sep"></span>
<span id="zoom-display" class="tb-label" style="font-family:'Space Grotesk',monospace;font-size:0.78rem;color:var(--color-text-muted);min-width:38px;text-align:center;">100%</span>
<button id="reset-view-btn" class="icon-btn" title="重置视口" aria-label="重置视口">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
    <path d="M3 3v5h5"/>
  </svg>
</button>
```

---

- [ ] **Step 4: 在 JS 脚本中引入 world_map 模块**

在 `<script>` 块顶部（所有函数定义前）添加：

```js
// world_map engine (loaded from the built source)
const WORLD_SIZE = 10000
const PAD = 20
let viewport = { offsetX: 5000, offsetY: 5000, scale: 1 }
let canvasW = 800, canvasH = 600
let users = []
let heatmap = []
let hoveredUserId = null
let isDragging = false
let lastPan = { x: 0, y: 0 }

// --- Viewport helpers (inline copy of world_map logic for vanilla HTML) ---
function getBounds(users) {
  if (!users.length) return { minX: 0, maxX: WORLD_SIZE, minY: 0, maxY: WORLD_SIZE }
  let minX=Infinity, maxX=-Infinity, minY=Infinity, maxY=-Infinity
  for (const u of users) {
    if (u.x < minX) minX = u.x
    if (u.x > maxX) maxX = u.x
    if (u.y < minY) minY = u.y
    if (u.y > maxY) maxY = u.y
  }
  const pad = 100
  return { minX: Math.max(0,minX-pad), maxX: Math.min(WORLD_SIZE,maxX+pad), minY: Math.max(0,minY-pad), maxY: Math.min(WORLD_SIZE,maxY+pad) }
}

function worldToCanvas(wx, wy) {
  return {
    x: (wx - viewport.offsetX) * viewport.scale + canvasW / 2,
    y: (wy - viewport.offsetY) * viewport.scale + canvasH / 2,
  }
}

function canvasToWorld(sx, sy) {
  return {
    x: (sx - canvasW / 2) / viewport.scale + viewport.offsetX,
    y: (sy - canvasH / 2) / viewport.scale + viewport.offsetY,
  }
}

function hashToColor(name) {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  const hue = Math.abs(hash) % 360
  return `hsl(${hue}, 75%, 65%)`
}

function zoomViewportToward(newScale, cx, cy) {
  const ratio = newScale / viewport.scale
  viewport.offsetX = cx - (cx - viewport.offsetX) / ratio
  viewport.offsetY = cy - (cy - viewport.offsetY) / ratio
  viewport.scale = newScale
}

function panViewport(dx, dy) {
  viewport.offsetX -= dx / viewport.scale
  viewport.offsetY -= dy / viewport.scale
}

function resetViewport() {
  const bounds = getBounds(users)
  viewport.offsetX = (bounds.minX + bounds.maxX) / 2
  viewport.offsetY = (bounds.minY + bounds.maxY) / 2
  viewport.scale = 1
  updateZoomDisplay()
  drawFrame()
}

function updateZoomDisplay() {
  const el = document.getElementById('zoom-display')
  if (el) el.textContent = Math.round(viewport.scale * 100) + '%'
}

function getViewportRange() {
  const halfW = canvasW / 2 / viewport.scale
  const halfH = canvasH / 2 / viewport.scale
  return {
    minX: Math.round(viewport.offsetX - halfW),
    maxX: Math.round(viewport.offsetX + halfW),
    minY: Math.round(viewport.offsetY - halfH),
    maxY: Math.round(viewport.offsetY + halfH),
  }
}

// --- Rendering ---
function drawGrid(ctx, w, h) {
  ctx.strokeStyle = 'rgba(232,98,58,0.06)'
  ctx.lineWidth = 0.5
  const step = 30
  const jitter = (i) => ((i * 7919) % 17 - 8) * 0.5
  for (let x = 0; x < w; x += step) {
    const jx = jitter(Math.floor(x / step))
    ctx.beginPath(); ctx.moveTo(x + jx, 0); ctx.lineTo(x + jx, h); ctx.stroke()
  }
  for (let y = 0; y < h; y += step) {
    const jy = jitter(Math.floor(y / step))
    ctx.beginPath(); ctx.moveTo(0, y + jy); ctx.lineTo(w, y + jy); ctx.stroke()
  }
}

function drawAxisTicks(ctx) {
  const vb = getViewportRange()
  const TICK = 6, STEP = 500, FS = 11, PAD2 = 20
  ctx.font = `500 ${FS}px 'Space Grotesk', monospace`
  ctx.fillStyle = '#8b7b6e'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'

  const wLeft = viewport.offsetX - (canvasW / 2 - PAD2) / viewport.scale
  const wRight = viewport.offsetX + (canvasW / 2 - PAD2) / viewport.scale
  const firstX = Math.ceil(wLeft / STEP) * STEP

  for (let wx = firstX; wx <= wRight; wx += STEP) {
    const sx = (wx - viewport.offsetX) * viewport.scale + canvasW / 2
    if (sx < PAD2 || sx > canvasW - PAD2) continue
    const jx = (((wx / STEP) * 7919) % 11 - 5) * 0.4
    // Top
    ctx.beginPath(); ctx.strokeStyle = 'rgba(232,98,58,0.25)'; ctx.lineWidth = 1
    ctx.moveTo(sx + jx, PAD2); ctx.lineTo(sx + jx, PAD2 + TICK); ctx.stroke()
    ctx.fillText(String(Math.round(wx)), sx, PAD2 + TICK + 2)
    // Bottom
    ctx.beginPath()
    ctx.moveTo(sx + jx, canvasH - PAD2 - TICK); ctx.lineTo(sx + jx, canvasH - PAD2); ctx.stroke()
    ctx.save(); ctx.textBaseline = 'bottom'
    ctx.fillText(String(Math.round(wx)), sx, canvasH - PAD2 - TICK - 2); ctx.restore()
  }

  // Y ticks
  ctx.textAlign = 'right'
  const wTop = viewport.offsetY - (canvasH / 2 - PAD2) / viewport.scale
  const wBottom = viewport.offsetY + (canvasH / 2 - PAD2) / viewport.scale
  const firstY = Math.ceil(wTop / STEP) * STEP
  for (let wy = firstY; wy <= wBottom; wy += STEP) {
    const sy = (wy - viewport.offsetY) * viewport.scale + canvasH / 2
    if (sy < PAD2 || sy > canvasH - PAD2) continue
    const jy = (((wy / STEP) * 7919) % 11 - 5) * 0.4
    ctx.beginPath(); ctx.strokeStyle = 'rgba(232,98,58,0.25)'; ctx.lineWidth = 1
    ctx.moveTo(PAD2, sy + jy); ctx.lineTo(PAD2 + TICK, sy + jy); ctx.stroke()
    ctx.save(); ctx.textAlign = 'left'
    ctx.fillText(String(Math.round(wy)), PAD2 + TICK + 3, sy); ctx.restore()
    ctx.beginPath()
    ctx.moveTo(canvasW - PAD2 - TICK, sy + jy); ctx.lineTo(canvasW - PAD2, sy + jy); ctx.stroke()
    ctx.save(); ctx.textAlign = 'right'
    ctx.fillText(String(Math.round(wy)), canvasW - PAD2 - TICK - 3, sy); ctx.restore()
  }
}

function drawCrawfishDot(ctx, pt, name, isHovered) {
  const BASE_R = 10
  const r = Math.max(3, BASE_R / viewport.scale)
  if (viewport.scale < 0.5) {
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, Math.max(3, 4 / viewport.scale), 0, Math.PI * 2)
    ctx.fillStyle = hashToColor(name)
    ctx.fill()
    return
  }
  ctx.beginPath(); ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2)
  ctx.fillStyle = hashToColor(name); ctx.fill()
  ctx.strokeStyle = '#fff'; ctx.lineWidth = Math.max(1, 1.5 / viewport.scale); ctx.stroke()
  const letterSize = Math.max(6, r * 0.7)
  ctx.font = `700 ${letterSize}px 'Fredoka', sans-serif`
  ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
  ctx.fillText(name.charAt(0).toUpperCase(), pt.x, pt.y)
  if (isHovered) drawBubble(ctx, pt, name, r)
}

function drawBubble(ctx, pt, name, r) {
  const label = (name + '').slice(0, 16)
  ctx.font = `600 ${Math.max(9, 10 / viewport.scale)}px 'Fredoka', sans-serif`
  ctx.textAlign = 'left'
  const nw = ctx.measureText(name).width
  const lw = ctx.measureText(`"${label}"`).width
  const bw = Math.max(nw, lw) + 20
  const bh = 52 / viewport.scale
  const br = 6 / viewport.scale
  let bx = pt.x + r + 6
  let by = pt.y - bh / 2
  if (bx + bw > canvasW - 10) bx = pt.x - r - 6 - bw
  if (by < 10) by = 10
  if (by + bh > canvasH - 10) by = canvasH - bh - 10
  ctx.fillStyle = 'rgba(255,255,255,0.96)'
  ctx.strokeStyle = 'rgba(232,98,58,0.3)'
  ctx.lineWidth = 1.5 / viewport.scale
  ctx.beginPath(); ctx.roundRect(bx, by, bw, bh, br); ctx.fill(); ctx.stroke()
  ctx.font = `600 ${Math.max(9, 10 / viewport.scale)}px 'Fredoka', sans-serif`
  ctx.fillStyle = '#3d2c24'; ctx.textAlign = 'left'; ctx.textBaseline = 'top'
  ctx.fillText(name, bx + 8, by + 5 / viewport.scale)
  ctx.font = `400 ${Math.max(8, 9 / viewport.scale)}px 'Nunito', sans-serif`
  ctx.fillStyle = '#8b7b6e'
  ctx.fillText(`"${label}"`, bx + 8, by + (16 / viewport.scale))
  ctx.font = `400 ${Math.max(8, 9 / viewport.scale)}px 'Space Grotesk', monospace`
  ctx.fillStyle = '#8b7b6e'
  ctx.fillText(`(${Math.round(pt.x)}, ${Math.round(pt.y)})`, bx + 8, by + (29 / viewport.scale))
}

function drawCrawfishLayer(ctx) {
  if (!users.length) return
  ctx.save()
  ctx.translate(canvasW / 2, canvasH / 2)
  ctx.scale(viewport.scale, viewport.scale)
  ctx.translate(-viewport.offsetX, -viewport.offsetY)
  for (const u of users) {
    const pt = worldToCanvas(u.x, u.y)
    drawCrawfishDot(ctx, pt, u.name, u.user_id === hoveredUserId)
  }
  ctx.restore()
  ctx.font = '500 13px "Space Grotesk", monospace'
  ctx.textAlign = 'left'
  ctx.fillStyle = 'rgba(139,123,110,0.7)'
  ctx.fillText(`${users.length} 只龙虾在线`, 10, canvasH - 10)
}

function drawFrame() {
  const canvas = document.getElementById('map-canvas')
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  canvasW = canvas.width; canvasH = canvas.height
  ctx.clearRect(0, 0, canvasW, canvasH)

  ctx.save()
  ctx.translate(canvasW / 2, canvasH / 2)
  ctx.scale(viewport.scale, viewport.scale)
  ctx.translate(-viewport.offsetX, -viewport.offsetY)
  drawGrid(ctx, canvasW, canvasH)
  ctx.restore()

  drawCrawfishLayer(ctx)
  drawAxisTicks(ctx)

  // Bottom-left viewport range
  const vr = getViewportRange()
  const coordEl = document.getElementById('vp-coord')
  if (coordEl) coordEl.textContent = `x: ${vr.minX} ~ ${vr.maxX}  y: ${vr.minY} ~ ${vr.maxY}`
}

function initViewport() {
  const bounds = getBounds(users)
  viewport.offsetX = (bounds.minX + bounds.maxX) / 2
  viewport.offsetY = (bounds.minY + bounds.maxY) / 2
  viewport.scale = 1
}
```

---

- [ ] **Step 5: 添加 Canvas 鼠标事件和缩放控件绑定**

找到现有 `canvas.addEventListener('mousemove', ...)` 代码，在其后添加：

```js
canvas.addEventListener('wheel', (e) => {
  e.preventDefault()
  const world = canvasToWorld(e.clientX - canvas.getBoundingClientRect().left, e.clientY - canvas.getBoundingClientRect().top)
  const newScale = Math.min(5, Math.max(0.2, viewport.scale * (1 + (e.deltaY > 0 ? -0.15 : 0.15))))
  zoomViewportToward(newScale, world.x, world.y)
  updateZoomDisplay()
  drawFrame()
}, { passive: false })

canvas.addEventListener('mousedown', (e) => {
  isDragging = true
  lastPan = { x: e.clientX, y: e.clientY }
  canvas.style.cursor = 'grabbing'
})

canvas.addEventListener('mousemove', (e) => {
  const rect = canvas.getBoundingClientRect()
  const world = canvasToWorld(e.clientX - rect.left, e.clientY - rect.top)
  const coordEl = document.getElementById('cursor-coord')
  if (coordEl) coordEl.textContent = `(${Math.round(world.x)}, ${Math.round(world.y)})`

  if (isDragging) {
    const dx = e.clientX - lastPan.x
    const dy = e.clientY - lastPan.y
    lastPan = { x: e.clientX, y: e.clientY }
    panViewport(dx, dy)
    updateZoomDisplay()
    drawFrame()
  }
})

canvas.addEventListener('mouseup', () => {
  isDragging = false
  canvas.style.cursor = 'grab'
})

canvas.addEventListener('mouseleave', () => {
  isDragging = false
  canvas.style.cursor = 'grab'
})

document.getElementById('reset-view-btn')?.addEventListener('click', resetViewport)
```

---

- [ ] **Step 6: 在 HTML Canvas wrapper 中添加坐标显示层**

找到 `#canvas-wrap` 内的 `#canvas-msg` 后添加：

```html
<!-- 左上角：鼠标坐标 -->
<div id="cursor-coord" style="position:absolute;top:14px;left:14px;padding:4px 10px;background:rgba(255,255,255,.88);backdrop-filter:blur(10px);border:1.5px solid #f0e6d8;border-radius:20px;font-size:.72rem;color:#8b7b6e;font-family:'Space Grotesk',monospace;font-weight:600;pointer-events:none;">—</div>

<!-- 左下角：视口范围 -->
<div id="vp-coord" style="position:absolute;bottom:16px;left:16px;padding:4px 10px;background:rgba(255,255,255,.88);backdrop-filter:blur(10px);border:1.5px solid #f0e6d8;border-radius:20px;font-size:.72rem;color:#8b7b6e;font-family:'Space Grotesk',monospace;font-weight:600;pointer-events:none;">—</div>
```

---

- [ ] **Step 7: 替换 canvas style 加 grab cursor**

找到 `#map-canvas` 的 CSS，`display: block` 后加一行：

```css
cursor: grab;
```

---

- [ ] **Step 8: WebSocket snapshot 处理中调用 initViewport 和 drawFrame**

找到 `if (msg.type === 'global_snapshot')` 的处理代码，在数据赋值后添加：

```js
if (!initDone) {
  initViewport()
  initDone = true
}
drawFrame()
```

需要先在脚本顶部加 `let initDone = false`。

---

- [ ] **Step 9: 提交**

```bash
git add app/world/crawfish/index.html
git commit -m "feat(world-page): add zoom/drag, axis ticks, avatar, bubble, coord display

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 4: App.vue — 全局 CSS 噪点纹理

**Files:**
- Modify: `website/src/App.vue`
- Check: `website/src/App.vue:95-110` (global style block)

---

- [ ] **Step 1: 在全局 `<style>` 的 body 规则后添加噪点层**

在 `App.vue` 的 `<style>` 块（无 scoped）末尾添加：

```css
/* ── Hand-drawn Texture Overlay ── */
body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: -1;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='0.025'/%3E%3C/svg%3E");
  pointer-events: none;
}
```

---

- [ ] **Step 2: 升级圆角全局 Token**

在同一 `<style>` 块添加：

```css
:root {
  --rc-xs: 6px;
  --rc-sm: 10px;
  --rc-md: 16px;
  --rc-lg: 22px;
  --rc-xl: 30px;
}

.watercolor-shadow {
  box-shadow: 0 2px 8px rgba(232,98,58,.08), 0 6px 24px rgba(232,98,58,.06), 3px 3px 0 rgba(232,98,58,.04);
}
```

---

- [ ] **Step 3: 升级 Navbar 圆角**

找到 `.navbar`，将 `border-bottom: 1.5px solid #f0e6d8` 后添加 `border-radius: var(--rc-md)`：

```css
.navbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 251, 245, 0.92);
  backdrop-filter: blur(16px);
  border-bottom: 1.5px solid #f0e6d8;
  border-radius: 0 0 var(--rc-md) var(--rc-md); /* bottom only */
}
```

---

- [ ] **Step 4: 升级 CTA 按钮**

找到 `.cta-btn` 的 `border-radius: 10px`，替换为：

```css
border-radius: var(--rc-sm);
box-shadow: 0 2px 8px rgba(232,98,58,.15);
```

在 `.cta-btn:hover` 中添加 `box-shadow` 增强：

```css
box-shadow: 0 4px 20px rgba(232,98,58,.35);
```

---

- [ ] **Step 5: 升级 Hero 地图容器**

找到 `.hero-map`，替换 `border-radius: 20px` 为：

```css
border-radius: var(--rc-xl);
overflow: hidden;
```

---

- [ ] **Step 6: 升级 .cta-primary**

找到 `.cta-primary`，将 `border-radius: 14px` 替换为 `border-radius: var(--rc-md)`。

---

- [ ] **Step 7: 提交**

```bash
git add website/src/App.vue
git commit -m "style(site): add noise texture, global rc-* tokens, hand-drawn shadows

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 5: FeatureSection.vue + QuickStart.vue — 卡片升级

**Files:**
- Modify: `website/src/components/FeatureSection.vue`
- Modify: `website/src/components/QuickStart.vue`

---

- [ ] **Step 1: FeatureSection — 加 watercolor-shadow 和圆角**

读取 `FeatureSection.vue`，找到卡片容器的 class，添加：

```css
/* 在 .feature-card 或对应选择器中添加 */
border-radius: var(--rc-lg);
box-shadow: var(--watercolor-shadow, 0 2px 8px rgba(232,98,58,.08), 0 6px 24px rgba(232,98,58,.06), 3px 3px 0 rgba(232,98,58,.04));
transition: transform 200ms ease, box-shadow 200ms ease;
```

添加 hover：

```css
.feature-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(232,98,58,.15), 0 2px 8px rgba(232,98,58,.1), 3px 4px 0 rgba(232,98,58,.06);
}
```

---

- [ ] **Step 2: QuickStart — 步骤编号圆形**

读取 `QuickStart.vue`，找到步骤编号的容器或数字，替换背景为：

```css
/* 编号圆形背景 */
.step-number {
  width: 36px; height: 36px;
  background: linear-gradient(135deg, #e8623a, #f4a261);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  font-family: 'Fredoka', sans-serif;
  font-weight: 700;
  font-size: 1rem;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(232,98,58,.3);
}
```

---

- [ ] **Step 3: 提交**

```bash
git add website/src/components/FeatureSection.vue website/src/components/QuickStart.vue
git commit -m "style(components): add watercolor shadow, hand-drawn card style

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 6: map-preview.html + world/index.html — 同步手绘风

**Files:**
- Modify: `app/world/crawfish/map-preview.html`
- Modify: `app/static/world/index.html`

---

- [ ] **Step 1: 读取两个文件，了解现有 CSS**

先读取这两个文件，找到 `<style>` 块中的 CSS 变量和主要样式类。

---

- [ ] **Step 2: map-preview.html — 添加 CSS Token**

在 `map-preview.html` 的 `<style>` 块顶部添加：

```css
/* Hand-drawn token */
:root {
  --rc-xs: 6px;
  --rc-sm: 10px;
  --rc-md: 16px;
  --rc-lg: 22px;
}
.watercolor-shadow {
  box-shadow: 0 2px 8px rgba(232,98,58,.08), 0 6px 24px rgba(232,98,58,.06), 3px 3px 0 rgba(232,98,58,.04);
}
```

找到主要卡片/容器元素，将 `border-radius` 替换为 `var(--rc-md)` 或 `var(--rc-lg)`。

---

- [ ] **Step 3: world/index.html — 同上**

在 `app/static/world/index.html` 的 `<style>` 块做同样处理。

---

- [ ] **Step 4: 提交**

```bash
git add app/world/crawfish/map-preview.html app/static/world/index.html
git commit -m "style(pages): sync hand-drawn tokens to preview and world index pages

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 7: DESIGN.md — 更新设计哲学章节

**Files:**
- Modify: `DESIGN.md`

---

- [ ] **Step 1: 读取 DESIGN.md 前 200 行**

确认现有章节位置。

---

- [ ] **Step 2: 替换设计哲学章节**

找到 `## 1. Design Philosophy`，将内容替换为：

```markdown
## 1. Design Philosophy

**Hand-Drawn Adventure · Living Journal**

ClawSocial feels like a travel-journal companion app crossed with a living simulation. The personality is:

- **Hand-drawn organic feel** — all borders slightly rounded, lines with subtle imperfection
- **Warm and approachable** — cream backgrounds, rounded corners, friendly typefaces
- **Playful without being childish** — Fredoka gives energy; it never looks like a corporate dashboard
- **Adventurous** — the world map is the emotional core; seeing your crawfish move in real time is the payoff
- **Honest** — no dark patterns, no gratuitous complexity; a new user can understand the whole product in 30 seconds

**Global CSS Tokens:**
```css
--rc-xs: 6px; --rc-sm: 10px; --rc-md: 16px; --rc-lg: 22px; --rc-xl: 30px;
.watercolor-shadow { box-shadow: 0 2px 8px rgba(232,98,58,.08), 0 6px 24px rgba(232,98,58,.06), 3px 3px 0 rgba(232,98,58,.04); }
```

**Emotional tone words:** warm, alive, curious, playful, hand-crafted
```

---

- [ ] **Step 3: 提交**

```bash
git add DESIGN.md
git commit -m "docs: update DESIGN.md philosophy to hand-drawn adventure style

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 8: 集成验证 — 全站构建 + 测试

**Files:**
- Run: `website/` build + `python -m pytest tests/test_api.py`

---

- [ ] **Step 1: 运行全站构建**

```bash
cd /d/clawsocial-server/.worktrees/map-ui-optimization/website && npm run build
```
预期：构建成功，产物输出到 `../app/static/`

---

- [ ] **Step 2: 运行测试**

```bash
cd /d/clawsocial-server/.worktrees/map-ui-optimization && python -m pytest tests/test_api.py -q
```
预期：51 tests passed

---

- [ ] **Step 3: 手动验证（可选）**

启动服务器：`python -m app.main`（在 worktree 目录），访问：
- `http://127.0.0.1:8000/` — 首页地图（缩放/拖拽/头像）
- `http://127.0.0.1:8000/world/` — 主地图页（刻度/坐标/头像/气泡）
- `http://127.0.0.1:8000/world/crawfish/map-preview.html` — 预览页（手绘风）

---

- [ ] **Step 4: 最终提交**

```bash
git add -A && git commit -m "feat: complete map UI optimization + hand-drawn style across all pages

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务依赖关系

```
Task 1 (world_map.ts)  ──────────────────────┐
                                              ├── Task 2 (HeroMap.vue)
Task 3 (index.html)   ───────────────────────┤
                                              ├── Task 4 (App.vue)    ── Task 5 (Feature/QuickStart)
Task 6 (preview+world)───────────────────────┤
                                              └── Task 7 (DESIGN.md)
                                                              └── Task 8 (Integration)
```
