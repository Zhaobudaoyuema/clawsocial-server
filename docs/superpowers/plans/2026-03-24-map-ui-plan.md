# Map UI 优化 + 全站手绘风升级 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 地图加缩放/拖拽/坐标刻度，全站升级手绘插画风（基于 Vue 3 SPA）

**Architecture:**
- `world_map.ts` 是核心渲染引擎，Viewport 状态在 TS 模块内管理，通过 `initViewport()` 初始化
- `HeroMap.vue` 调用 world_map.ts 的渲染函数，绑定缩放/拖拽事件
- CSS Token (`rc-*`, watercolor-shadow) 注入到 `App.vue`，全站 Vue 组件生效
- 手绘气泡和头像用 Canvas 原生绘制，无外部依赖

**Tech Stack:** TypeScript（world_map.ts）+ Vue 3（website/）

---

## 改动文件地图

```
website/src/world_map.ts              ← 核心引擎：Viewport + 刻度 + 头像 + 气泡
website/src/components/HeroMap.vue     ← 首页地图：事件绑定 + 缩放/拖拽
website/src/App.vue                   ← 全局 CSS：噪点纹理 + 手绘 Token
website/src/components/FeatureSection.vue ← 卡片圆角 + 水彩阴影
website/src/components/QuickStart.vue     ← 编号圆形
website/src/components/RegisterModal.vue   ← 按钮圆角
DESIGN.md                            ← 写入手绘风格规范
```

> **注意：** `app/world/crawfish/` 下的 HTML 页面为静态 fallback 页面，不在本轮重构范围内。其样式保持独立，不强制同步 Vue 的手绘风。

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
  const PAD = 24

  // X axis ticks (top and bottom)
  ctx.textAlign = 'center'
  ctx.textBaseline = 'bottom'
  const worldLeft = _viewport.offsetX - (_canvasW / 2 - PAD) / _viewport.scale
  const worldRight = _viewport.offsetX + (_canvasW / 2 - PAD) / _viewport.scale
  const TICK_STEP = 100
  const firstTickX = Math.ceil(worldLeft / TICK_STEP) * TICK_STEP

  for (let wx = firstTickX; wx <= worldRight; wx += TICK_STEP) {
    const sx = (wx - _viewport.offsetX) * _viewport.scale + _canvasW / 2
    if (sx < PAD || sx > _canvasW - PAD) continue

    const jx = (((wx / TICK_STEP) * 7919) % 11 - 5) * 0.4

    // Bottom tick
    ctx.beginPath()
    ctx.strokeStyle = 'rgba(232, 98, 58, 0.25)'
    ctx.lineWidth = 1
    ctx.moveTo(sx + jx, _canvasH - PAD)
    ctx.lineTo(sx + jx, _canvasH - PAD + TICK)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillText(String(Math.round(wx)), sx + jx, _canvasH - PAD + TICK + 2)
    ctx.restore()

    // Top tick
    ctx.beginPath()
    ctx.moveTo(sx + jx, PAD - TICK)
    ctx.lineTo(sx + jx, PAD)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'bottom'
    ctx.fillText(String(Math.round(wx)), sx + jx, PAD - TICK - 2)
    ctx.restore()
  }

  // Y axis ticks (left and right)
  ctx.textAlign = 'right'
  ctx.textBaseline = 'middle'
  const worldTop = _viewport.offsetY - (_canvasH / 2 - PAD) / _viewport.scale
  const worldBottom = _viewport.offsetY + (_canvasH / 2 - PAD) / _viewport.scale
  const firstTickY = Math.ceil(worldTop / TICK_STEP) * TICK_STEP

  for (let wy = firstTickY; wy <= worldBottom; wy += TICK_STEP) {
    const sy = (wy - _viewport.offsetY) * _viewport.scale + _canvasH / 2
    if (sy < PAD || sy > _canvasH - PAD) continue

    const jy = (((wy / TICK_STEP) * 7919) % 11 - 5) * 0.4

    // Left tick
    ctx.beginPath()
    ctx.strokeStyle = 'rgba(232, 98, 58, 0.25)'
    ctx.lineWidth = 1
    ctx.moveTo(PAD, sy + jy)
    ctx.lineTo(PAD + TICK, sy + jy)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'left'
    ctx.fillText(String(Math.round(wy)), PAD + TICK + 3, sy)
    ctx.restore()

    // Right tick
    ctx.beginPath()
    ctx.moveTo(_canvasW - PAD - TICK, sy + jy)
    ctx.lineTo(_canvasW - PAD, sy + jy)
    ctx.stroke()
    ctx.save()
    ctx.textAlign = 'right'
    ctx.fillText(String(Math.round(wy)), _canvasW - PAD - TICK - 3, sy)
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
  return `hsl(${hue}, 65%, 55%)`
}
```

---

- [ ] **Step 7: 重写 drawCrawfishDot 支持视口缩放**

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
function drawCrawfishBubble(
  ctx: CanvasRenderingContext2D,
  pt: { x: number; y: number },
  name: string,
  r: number
) {
  ctx.save()
  ctx.translate(pt.x, pt.y - r - 14)

  const text = name.length > 12 ? name.slice(0, 11) + '…' : name
  ctx.font = '13px Fredoka, sans-serif'
  const tw = ctx.measureText(text).width
  const bw = tw + 20
  const bh = 28
  const br = 8

  // Bubble body with hand-drawn wobble
  ctx.beginPath()
  ctx.moveTo(-bw / 2 + br, -bh / 2)
  ctx.lineTo(bw / 2 - br, -bh / 2)
  ctx.quadraticCurveTo(bw / 2, -bh / 2, bw / 2, -bh / 2 + br)
  ctx.lineTo(bw / 2, bh / 2 - br)
  ctx.quadraticCurveTo(bw / 2, bh / 2, bw / 2 - br, bh / 2)
  ctx.lineTo(-bw / 2 + br, bh / 2)
  ctx.quadraticCurveTo(-bw / 2, bh / 2, -bw / 2, bh / 2 - br)
  ctx.lineTo(-bw / 2, -bh / 2 + br)
  ctx.quadraticCurveTo(-bw / 2, -bh / 2, -bw / 2 + br, -bh / 2)
  ctx.closePath()
  ctx.fillStyle = 'rgba(255, 245, 230, 0.96)'
  ctx.fill()
  ctx.strokeStyle = 'rgba(232, 98, 58, 0.35)'
  ctx.lineWidth = 1.5
  ctx.stroke()

  // Name text
  ctx.fillStyle = '#3d2c24'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 0, 0)

  ctx.restore()
}
```

---

- [ ] **Step 9: 提交**

```bash
git add website/src/world_map.ts
git commit -m "feat(map): add viewport engine, zoom/drag, hand-drawn ticks, avatar bubbles

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 2: HeroMap.vue — 缩放/拖拽事件绑定

**Files:**
- Modify: `website/src/components/HeroMap.vue`
- Check: `website/src/components/HeroMap.vue:1-50`

---

- [ ] **Step 1: 读取现有 HeroMap.vue**

了解现有结构和 ref 命名，确认 canvas ref 和渲染函数调用位置。

---

- [ ] **Step 2: 添加缩放/拖拽事件**

在 `onMounted` 中绑定 mousewheel 和 pointer 事件：

```ts
// Zoom (wheel)
canvas.addEventListener('wheel', (e: WheelEvent) => {
  e.preventDefault()
  const rect = canvas.getBoundingClientRect()
  const sx = e.clientX - rect.left
  const sy = e.clientY - rect.top
  const { x: wx, y: wy } = canvasToWorld(sx, sy)
  zoomViewport(-e.deltaY * 0.001, wx, wy)
  renderMap()
}, { passive: false })

// Pan (pointer drag)
let isPanning = false
let lastX = 0, lastY = 0

canvas.addEventListener('pointerdown', (e: PointerEvent) => {
  if (e.button !== 0) return
  isPanning = true
  lastX = e.clientX
  lastY = e.clientY
  canvas.setPointerCapture(e.pointerId)
})

canvas.addEventListener('pointermove', (e: PointerEvent) => {
  if (!isPanning) return
  panViewport(e.clientX - lastX, e.clientY - lastY)
  lastX = e.clientX
  lastY = e.clientY
  renderMap()
})

canvas.addEventListener('pointerup', () => { isPanning = false })
canvas.addEventListener('pointerleave', () => { isPanning = false })
```

在 `onUnmounted` 中清理事件监听器（使用 `{ passive: false }` 的 wheel listener 必须清理）。

---

- [ ] **Step 3: 初始化 Viewport**

在 onMounted 中初始化 Viewport（传入当前用户列表）：

```ts
import { initViewport, setCanvasSize, drawMap } from '../world_map'

const vp = initViewport(users.value, canvas.width, canvas.height)
```

---

- [ ] **Step 4: 提交**

```bash
git add website/src/components/HeroMap.vue
git commit -m "feat(hero): add zoom/drag to HeroMap, cursor coords, scale display

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 3: App.vue — 全局 CSS 手绘 Token + 噪点纹理

**Files:**
- Modify: `website/src/App.vue`
- Modify: `website/src/style.css`（如有必要）

---

- [ ] **Step 1: 添加手绘 Token 到 style.css**

在 `:root` 中添加：

```css
/* Hand-drawn roundness tokens */
--rc-xs: 6px;
--rc-sm: 10px;
--rc-md: 16px;
--rc-lg: 22px;
--rc-xl: 30px;
--rc-full: 999px;

.watercolor-shadow {
  box-shadow:
    0 2px 8px rgba(232, 98, 58, 0.08),
    0 6px 24px rgba(232, 98, 58, 0.06),
    3px 3px 0 rgba(232, 98, 58, 0.04);
}
```

---

- [ ] **Step 2: 添加噪点纹理到 App.vue 全局样式**

在 `App.vue` 的 `<style>` 或 `style.css` 的 `body` 规则后添加：

```css
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

- [ ] **Step 3: 提交**

```bash
git add website/src/App.vue website/src/style.css
git commit -m "style(site): add noise texture, global rc-* tokens, hand-drawn shadows

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 任务 4: FeatureSection.vue + QuickStart.vue — 卡片手绘风升级

**Files:**
- Modify: `website/src/components/FeatureSection.vue`
- Modify: `website/src/components/QuickStart.vue`

---

- [ ] **Step 1: FeatureSection — 应用 rc-* Token**

将主要卡片容器的 `border-radius` 替换为 `var(--rc-md)`，将按钮的 `border-radius` 替换为 `var(--rc-sm)`。

将 `.card` 或等效类的 `box-shadow` 替换为 `var(--watercolor-shadow)` 或内联水彩阴影。

---

- [ ] **Step 2: QuickStart — 编号圆形**

在 `QuickStart.vue` 中为步骤编号圆形添加样式：

```css
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

## 任务 5: RegisterModal.vue — 按钮圆角升级

**Files:**
- Modify: `website/src/components/RegisterModal.vue`

---

- [ ] **Step 1: 将按钮的 border-radius 升级为 var(--rc-sm)**

找到 Modal 内所有 `button` 的 `border-radius`，替换为 `var(--rc-sm)` 或 `var(--rc-md)`。

---

- [ ] **Step 2: 提交**

```bash
git add website/src/components/RegisterModal.vue
git commit -m "style(register): upgrade button border-radius to rc-sm

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 验收标准

- [ ] `npm run build` 成功，产物输出到 `app/static/`
- [ ] `python -m pytest tests/test_api.py` 全部 51 个测试通过
- [ ] 首页 HeroMap 支持鼠标滚轮缩放和拖拽，坐标刻度显示
- [ ] 所有 Vue 组件使用统一的 `rc-*` 圆角 Token
- [ ] 噪点纹理在首页背景可见
- [ ] 截图验证：首页、世界地图页面视觉符合手绘插画风格
